"""
gui_harness.action.window — window management operations.

Includes: get_frontmost_app, verify_frontmost, activate_app, get_window_bounds.

Cross-platform:
- macOS  : osascript / System Events (process-level).
- Windows: ctypes + user32 (no extra dependency); matches by window
           title substring.
- Linux  : wmctrl / xdotool (best-effort; returns None / "unknown" when
           neither tool is installed, instead of raising).
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import time

SYSTEM = platform.system()


# ───────────────────────── Windows (ctypes / user32) ─────────────────────────

def _win_title(hwnd) -> str:
    import ctypes
    u = ctypes.windll.user32
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _win_find(substr: str):
    """[(hwnd, title)] of visible windows whose title contains substr."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    needle = (substr or "").lower()
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if u.IsWindowVisible(hwnd):
            t = _win_title(hwnd)
            if t and needle in t.lower():
                out.append((hwnd, t))
        return True

    u.EnumWindows(_cb, 0)
    return out


# ───────────────────────────── public API ─────────────────────────────

def get_frontmost_app():
    """Name of the currently frontmost application / window.

    macOS returns the process name; Windows/Linux return the active
    window's title (the closest cross-platform identifier).
    """
    if SYSTEM == "Darwin":
        try:
            r = subprocess.run(["osascript", "-e",
                'tell application "System Events" to return name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except Exception:
            return "unknown"
    if SYSTEM == "Windows":
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            return _win_title(hwnd) or "unknown"
        except Exception:
            return "unknown"
    # Linux
    if shutil.which("xdotool"):
        try:
            r = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return r.stdout.strip() or "unknown"
        except Exception:
            pass
    return "unknown"


def verify_frontmost(expected_app):
    """Check if expected_app is still frontmost. Returns (is_correct, actual)."""
    actual = get_frontmost_app()
    return actual == expected_app, actual


def activate_app(app_name):
    """Bring an app/window to the front (best-effort, matched by name/title)."""
    if SYSTEM == "Darwin":
        try:
            subprocess.run(["osascript", "-e",
                f'tell application "System Events" to set frontmost of process "{app_name}" to true'],
                capture_output=True, timeout=5)
            time.sleep(0.3)
        except Exception:
            subprocess.run(["open", "-a", app_name], capture_output=True, timeout=5)
            time.sleep(0.5)
        return
    if SYSTEM == "Windows":
        try:
            import ctypes
            u = ctypes.windll.user32
            for hwnd, _t in _win_find(app_name):
                u.ShowWindow(hwnd, 9)  # SW_RESTORE
                u.SetForegroundWindow(hwnd)
                time.sleep(0.3)
                return
        except Exception:
            pass
        return
    # Linux
    if shutil.which("wmctrl"):
        subprocess.run(["wmctrl", "-a", app_name], capture_output=True, timeout=5)
        time.sleep(0.3)
    elif shutil.which("xdotool"):
        subprocess.run(["xdotool", "search", "--name", app_name,
                        "windowactivate", "%@"], capture_output=True, timeout=5)
        time.sleep(0.3)


def get_window_bounds(app_name):
    """Window position and size as (x, y, w, h), or None."""
    if SYSTEM == "Darwin":
        try:
            r = subprocess.run(["osascript", "-l", "JavaScript", "-e", f'''
var se = Application("System Events");
var ws = se.processes["{app_name}"].windows();
var best = null;
var bestArea = 0;
for (var i = 0; i < ws.length; i++) {{
    try {{
        var p = ws[i].position();
        var s = ws[i].size();
        var area = s[0] * s[1];
        if (area > bestArea) {{
            bestArea = area;
            best = [p[0], p[1], s[0], s[1]];
        }}
    }} catch(e) {{}}
}}
if (best) best.join(","); else "";
'''], capture_output=True, text=True, timeout=5)
            parts = r.stdout.strip().split(",")
            if len(parts) == 4:
                return tuple(int(x) for x in parts)
        except Exception:
            pass
        return None
    if SYSTEM == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            wins = _win_find(app_name)
            if not wins:
                return None
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(wins[0][0], ctypes.byref(rect))
            return (rect.left, rect.top,
                    rect.right - rect.left, rect.bottom - rect.top)
        except Exception:
            return None
    # Linux: `wmctrl -lG` lists "ID desktop x y w h host title".
    if shutil.which("wmctrl"):
        try:
            r = subprocess.run(["wmctrl", "-lG"], capture_output=True,
                               text=True, timeout=5)
            for line in r.stdout.splitlines():
                parts = line.split(None, 7)
                if len(parts) >= 8 and app_name.lower() in parts[7].lower():
                    return (int(parts[2]), int(parts[3]),
                            int(parts[4]), int(parts[5]))
        except Exception:
            pass
    return None
