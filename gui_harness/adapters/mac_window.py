"""Window-scoped macOS capture and Accessibility actions; never global input."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
import importlib.util
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
import uuid


class WindowUnavailable(RuntimeError):
    """A window operation cannot run safely in the background."""


_current = ContextVar("gui_background_window", default=None)


def current_window():
    return _current.get()


def _cancel():
    from openprogram.agent.run_control import check_cancelled
    check_cancelled()


class _WindowControlIndicator:
    """Small client for the native indicator process; failures stay visual."""

    def __init__(self, identity):
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "gui_harness.adapters.mac_indicator",
                str(identity["window_id"]),
                str(identity["pid"]),
                identity["app_name"],
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    def show_action(self, action, bounds):
        if self.process.stdin is None:
            return
        payload = {"action": action, "bounds": bounds}
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def close(self):
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                self.process.terminate()
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
                self.process.wait()


def window_support():
    missing = [name for name in ("AppKit", "ApplicationServices", "Quartz", "ScreenCaptureKit")
               if importlib.util.find_spec(name) is None]
    result = {"available": False, "missing_dependencies": missing}
    if platform.system() != "Darwin" or missing:
        return {**result, "reason": "macOS window dependencies unavailable"}
    import Quartz
    import ApplicationServices
    import ScreenCaptureKit
    if not hasattr(ScreenCaptureKit, "SCScreenshotManager"):
        return {**result, "reason": "macOS 14 or newer is required"}
    granted = bool(Quartz.CGPreflightScreenCaptureAccess() and ApplicationServices.AXIsProcessTrusted())
    return {**result, "available": granted, "reason": "" if granted else "Screen Recording or Accessibility permission missing"}


class MacWindow:
    def __init__(self, app_name, window_id=None, previous=None):
        self._deadline = time.monotonic() + 15
        if platform.system() != "Darwin":
            raise WindowUnavailable("Background application windows require macOS")
        if not isinstance(app_name, str) or (window_id is not None and (type(window_id) is not int or window_id <= 0)):
            raise WindowUnavailable("Invalid application or window identifier")
        support = window_support()
        if not support["available"]:
            raise WindowUnavailable(support["reason"])
        try:
            import AppKit
            import ApplicationServices
            import Quartz
            import ScreenCaptureKit
        except ImportError as exc:
            raise WindowUnavailable("Install the Harness macOS window dependencies") from exc
        self.appkit, self.ax, self.cg, self.sc = AppKit, ApplicationServices, Quartz, ScreenCaptureKit
        # Initialize the WindowServer connection before asynchronous capture in
        # a headless worker. This does not activate an application.
        AppKit.NSApplication.sharedApplication()
        self.check_permissions()
        content = self._await(lambda cb: self.sc.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True, False, cb))
        if not app_name or app_name == "desktop":
            app_name = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication().bundleIdentifier()
        matches = [w for w in content.windows() if w.owningApplication()
                   and app_name in (w.owningApplication().applicationName(), w.owningApplication().bundleIdentifier())
                   and w.windowLayer() == 0 and w.frame().size.width > 1
                   and (window_id is None or w.windowID() == window_id)]
        if len(matches) != 1:
            raise WindowUnavailable("Select one exact window_id from the current window inventory")
        self.window = matches[0]
        self.pid = int(self.window.owningApplication().processID())
        self.app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(self.pid)
        self.identity = {"pid": self.pid, "window_id": int(self.window.windowID()),
                         "app_name": str(self.window.owningApplication().applicationName()),
                         "bundle_id": str(self.window.owningApplication().bundleIdentifier()),
                         "launch_time": str(self.app.launchDate())}
        if self.app.launchDate() is None:
            raise WindowUnavailable("Cannot determine target application launch identity")
        if previous and previous != self.identity:
            raise WindowUnavailable("The application/window identity changed; observe a new target explicitly")
        self.root = self.ax.AXUIElementCreateApplication(self.pid)
        self.ax.AXUIElementSetMessagingTimeout(self.root, 2.0)
        bounds = self.window.frame()
        candidates = []
        for window in self.attr(self.root, "AXWindows") or []:
            pos, size = self.attr(window, "AXPosition"), self.attr(window, "AXSize")
            if pos is None or size is None:
                continue
            ok1, point = self.ax.AXValueGetValue(pos, self.ax.kAXValueCGPointType, None)
            ok2, extent = self.ax.AXValueGetValue(size, self.ax.kAXValueCGSizeType, None)
            if ok1 and ok2 and max(abs(point.x-bounds.origin.x), abs(point.y-bounds.origin.y),
                                   abs(extent.width-bounds.size.width), abs(extent.height-bounds.size.height)) < 2:
                candidates.append(window)
        if len(candidates) != 1:
            raise WindowUnavailable("Cannot uniquely associate the captured window with Accessibility")
        self.ax_window = candidates[0]
        self.elements = {}
        self.element_bounds = {}
        self._indicator = None
        self.validate()
        self._deadline = None

    def check_permissions(self):
        if not self.cg.CGPreflightScreenCaptureAccess() or not self.ax.AXIsProcessTrusted():
            raise WindowUnavailable("Grant Screen Recording and Accessibility permissions in System Settings")

    def _await(self, start):
        completed, result = threading.Event(), []
        def callback(value, error):
            result.extend((value, error))
            completed.set()
        start(callback)
        deadline = time.monotonic() + 8
        while not completed.wait(0.02):
            _cancel()
            if time.monotonic() >= deadline:
                raise WindowUnavailable("Window capture timed out")
        if result[1] or result[0] is None:
            raise WindowUnavailable(f"Window capture failed: {result[1]}")
        return result[0]

    def attr(self, element, name):
        _cancel()
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise WindowUnavailable("Window Accessibility observation timed out")
        code, value = self.ax.AXUIElementCopyAttributeValue(element, name, None)
        return value if code == 0 else None

    def element_frame(self, element):
        position, size = self.attr(element, "AXPosition"), self.attr(element, "AXSize")
        if position is None or size is None:
            return None
        ok1, point = self.ax.AXValueGetValue(position, self.ax.kAXValueCGPointType, None)
        ok2, extent = self.ax.AXValueGetValue(size, self.ax.kAXValueCGSizeType, None)
        if not ok1 or not ok2:
            return None
        return {
            "x": float(point.x), "y": float(point.y),
            "width": float(extent.width), "height": float(extent.height),
        }

    def start_indicator(self):
        try:
            self._indicator = _WindowControlIndicator(self.identity)
        except Exception:
            self._indicator = None

    def close_indicator(self):
        indicator, self._indicator = getattr(self, "_indicator", None), None
        if indicator is not None:
            try:
                indicator.close()
            except Exception:
                pass

    def validate(self):
        _cancel()
        self.check_permissions()
        app = self.appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(self.pid)
        if not app or app.isTerminated() or str(app.launchDate()) != self.identity["launch_time"]:
            raise WindowUnavailable("Target application exited or restarted")
        windows = self.attr(self.root, "AXWindows") or []
        if self.ax_window not in windows or self.attr(self.ax_window, "AXMinimized"):
            raise WindowUnavailable("Target window closed or minimized")

    def observe(self):
        self._deadline = time.monotonic() + 15
        try:
            return self._observe()
        finally:
            self._deadline = None

    def _observe(self):
        self.validate()
        config = self.sc.SCStreamConfiguration.alloc().init()
        config.setWidth_(int(self.window.frame().size.width))
        config.setHeight_(int(self.window.frame().size.height))
        config.setShowsCursor_(False)
        content_filter = self.sc.SCContentFilter.alloc().initWithDesktopIndependentWindow_(self.window)
        image = self._await(lambda cb: self.sc.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(content_filter, config, cb))
        bitmap = self.appkit.NSBitmapImageRep.alloc().initWithCGImage_(image)
        data = bitmap.representationUsingType_properties_(self.appkit.NSBitmapImageFileTypePNG, {})
        directory = tempfile.mkdtemp(prefix="gui-window-")
        path = Path(directory) / "observation.png"
        path.write_bytes(bytes(data))
        self.elements = {}
        self.element_bounds = {}
        controls, pending = [], [(self.ax_window, 0)]
        while pending and len(controls) < 400:
            _cancel()
            element, depth = pending.pop()
            role = str(self.attr(element, "AXRole") or "")
            # Do not expose secure text fields or their values.
            if role == "AXSecureTextField" or self.attr(element, "AXSubrole") == "AXSecureTextField":
                continue
            token = uuid.uuid4().hex[:12]
            code, actions = self.ax.AXUIElementCopyActionNames(element, None)
            code_value, writable = self.ax.AXUIElementIsAttributeSettable(element, "AXValue", None)
            allowed = [str(a) for a in (actions or []) if a in ("AXPress", "AXScrollUpByPage", "AXScrollDownByPage")]
            can_write = code_value == 0 and bool(writable) and role in ("AXTextField", "AXTextArea", "AXComboBox")
            self.elements[token] = (element, allowed, can_write)
            bounds = self.element_frame(element)
            self.element_bounds[token] = bounds
            controls.append({"id": token, "role": role, "label": str(self.attr(element, "AXTitle") or self.attr(element, "AXDescription") or "")[:500],
                             "value": str(self.attr(element, "AXValue") or "")[:1500], "actions": allowed, "writable_text": can_write,
                             "bounds": bounds})
            if depth < 20:
                pending.extend((child, depth+1) for child in reversed(self.attr(element, "AXChildren") or []))
        self.validate()
        return {"img_path": str(path), "screenshot_artifact": str(path), "current_state": None,
                "transitions_info": "", "component_info": "\n<background_window>" + json.dumps({"target": self.identity, "controls": controls,
                "rule": "Use exact control ids. No foreground activation, global input or clipboard. Unsupported actions require human handoff."}, ensure_ascii=False) + "</background_window>"}

    def registry(self):
        def entry(description, fields):
            return {"description": description, "function": self.dispatch,
                    "input": {name: {"source": "llm", "type": str, "description": desc, "allow_empty": name == "text"} for name, desc in fields.items()}}
        return {
            "window_press": entry("Perform AXPress on a supported control without global mouse input", {"target": "exact control id"}),
            "window_set_text": entry("Replace the entire writable text value without keyboard or clipboard", {"target": "exact control id", "text": "complete replacement text"}),
            "window_scroll": entry("Perform a supported Accessibility page-scroll action", {"target": "exact control id", "direction": "up or down"}),
            "done": entry("Task visibly completed", {"reasoning": "completion evidence"}),
            "fail": entry("Background operation unavailable", {"blocker": "concrete limitation", "handoff_instruction": "human takeover instructions"}),
        }

    def dispatch(self, plan):
        self._deadline = time.monotonic() + 10
        try:
            return self._dispatch(plan)
        finally:
            self._deadline = None

    def _dispatch(self, plan):
        self.validate()
        name, args = plan.get("call"), plan.get("args") or {}
        token = args.get("target")
        if token not in self.elements:
            raise WindowUnavailable("Unknown or stale control id; observe the window again")
        element, allowed, writable = self.elements[token]
        ancestor = element
        for _ in range(64):
            if ancestor == self.ax_window:
                break
            ancestor = self.attr(ancestor, "AXParent")
            if ancestor is None:
                raise WindowUnavailable("Control no longer belongs to the target window")
        else:
            raise WindowUnavailable("Cannot verify control ownership")
        if name == "window_set_text" and writable:
            value = args.get("text")
            if not isinstance(value, str) or len(value) > 10000:
                raise WindowUnavailable("Text must be a string of at most 10000 characters")
            code = self.ax.AXUIElementSetAttributeValue(element, "AXValue", value)
        else:
            action = {"window_press": "AXPress", "window_scroll": {"up": "AXScrollUpByPage", "down": "AXScrollDownByPage"}.get(args.get("direction"))}.get(name)
            if action not in allowed:
                raise WindowUnavailable("This control does not support the requested background action")
            code = self.ax.AXUIElementPerformAction(element, action)
        if code != 0:
            raise WindowUnavailable(f"Accessibility action failed ({code}); no foreground fallback")
        bounds = self.element_frame(element)
        getattr(self, "element_bounds", {})[token] = bounds
        indicator = getattr(self, "_indicator", None)
        if indicator is not None:
            try:
                indicator.show_action(name, bounds)
            except Exception:
                pass
        return {"success": True, "action_status": "applied", "target": self.identity,
                "control_id": token, "control_bounds": bounds}


def window_inventory():
    """Read window identities, without capture, focus changes or permission prompts."""
    if platform.system() != "Darwin":
        return []
    try:
        import Quartz as cg
        import AppKit
        rows = []
        for w in cg.CGWindowListCopyWindowInfo(cg.kCGWindowListOptionAll, cg.kCGNullWindowID) or []:
            if w.get("kCGWindowLayer") != 0 or not w.get("kCGWindowName"):
                continue
            app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(w["kCGWindowOwnerPID"])
            rows.append({"window_id": int(w["kCGWindowNumber"]), "pid": int(w["kCGWindowOwnerPID"]),
                         "app_name": w.get("kCGWindowOwnerName"), "bundle_id": app.bundleIdentifier() if app else None,
                         "title": w["kCGWindowName"]})
        return rows
    except ImportError:
        return []


@contextmanager
def window_session(app_name, window_id=None, previous=None):
    import fcntl
    window = MacWindow(app_name, window_id, previous)
    directory = Path(tempfile.gettempdir()) / f"gui-window-locks-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise WindowUnavailable("Unsafe window lock directory")
    fd = os.open(directory / f"{window.pid}.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WindowUnavailable("Another GUI operation currently owns this application") from exc
        token = _current.set(window)
        start_indicator = getattr(window, "start_indicator", None)
        if start_indicator is not None:
            start_indicator()
        try:
            yield window
        finally:
            try:
                close_indicator = getattr(window, "close_indicator", None)
                if close_indicator is not None:
                    close_indicator()
            finally:
                _current.reset(token)
    finally:
        os.close(fd)
