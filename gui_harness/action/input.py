#!/usr/bin/env python3
"""
gui_harness.action.input — unified input with multi-target dispatch.

Supports multiple action targets (local, VM, etc.) with platform-aware
key mapping. Each target knows its platform and how to execute actions.

Usage:
    # Register targets at startup
    from gui_harness.action.input import register, set_default
    register("host", LocalTarget())
    register("vm", VMTarget("http://172.16.82.132:5000", platform="linux"))
    set_default("vm")

    # All actions go to default target
    mouse_click(100, 200)
    type_text("hello")
    key_combo("ctrl", "s")

    # Or specify target explicitly
    mouse_click(100, 200, target="host")
"""

from __future__ import annotations

import abc
import base64
import json
import platform
import subprocess
import time
from typing import Optional

HOST_SYSTEM = platform.system()  # "Darwin", "Windows", "Linux"

# ═══════════════════════════════════════════
# Semantic key mapping
# ═══════════════════════════════════════════

SEMANTIC_KEYS = {
    "copy":       {"darwin": ("command", "c"), "linux": ("ctrl", "c"), "windows": ("ctrl", "c")},
    "paste":      {"darwin": ("command", "v"), "linux": ("ctrl", "v"), "windows": ("ctrl", "v")},
    "cut":        {"darwin": ("command", "x"), "linux": ("ctrl", "x"), "windows": ("ctrl", "x")},
    "save":       {"darwin": ("command", "s"), "linux": ("ctrl", "s"), "windows": ("ctrl", "s")},
    "undo":       {"darwin": ("command", "z"), "linux": ("ctrl", "z"), "windows": ("ctrl", "z")},
    "redo":       {"darwin": ("command", "shift", "z"), "linux": ("ctrl", "shift", "z"), "windows": ("ctrl", "y")},
    "select_all": {"darwin": ("command", "a"), "linux": ("ctrl", "a"), "windows": ("ctrl", "a")},
    "find":       {"darwin": ("command", "f"), "linux": ("ctrl", "f"), "windows": ("ctrl", "f")},
    "new_tab":    {"darwin": ("command", "t"), "linux": ("ctrl", "t"), "windows": ("ctrl", "t")},
    "close_tab":  {"darwin": ("command", "w"), "linux": ("ctrl", "w"), "windows": ("ctrl", "w")},
    "refresh":    {"darwin": ("command", "r"), "linux": ("ctrl", "r"), "windows": ("ctrl", "r")},
}


# ═══════════════════════════════════════════
# ActionTarget base class
# ═══════════════════════════════════════════

class ActionTarget(abc.ABC):
    """Base class for action execution targets."""

    def __init__(self, platform_name: str = "unknown"):
        self.platform = platform_name.lower()  # "darwin", "linux", "windows"

    def resolve_semantic_key(self, key_name: str) -> Optional[tuple]:
        """Resolve a semantic key name to platform-specific combo."""
        lower = key_name.lower()
        if lower in SEMANTIC_KEYS:
            return SEMANTIC_KEYS[lower].get(self.platform)
        return None

    @abc.abstractmethod
    def click(self, x, y, button="left", clicks=1): ...
    @abc.abstractmethod
    def move(self, x, y): ...
    @abc.abstractmethod
    def drag(self, sx, sy, ex, ey, duration=0.5, button="left"): ...
    @abc.abstractmethod
    def key_press(self, key_name): ...
    @abc.abstractmethod
    def key_combo(self, *keys): ...
    @abc.abstractmethod
    def type_text(self, text): ...
    @abc.abstractmethod
    def paste_text(self, text): ...
    @abc.abstractmethod
    def activate_app(self, app_name): ...
    @abc.abstractmethod
    def set_clipboard(self, text): ...
    @abc.abstractmethod
    def get_clipboard(self) -> str: ...


# ═══════════════════════════════════════════
# LocalTarget — pynput on host machine
# ═══════════════════════════════════════════

class LocalTarget(ActionTarget):
    """Execute actions on the local machine via pynput."""

    def __init__(self, platform_name: str = None):
        super().__init__(platform_name or HOST_SYSTEM.lower())

    def _resolve_key(self, name):
        from pynput.keyboard import Key, KeyCode
        key_map = {
            "return": Key.enter, "enter": Key.enter,
            "tab": Key.tab,
            "esc": Key.esc, "escape": Key.esc,
            "space": Key.space,
            "delete": Key.backspace, "backspace": Key.backspace,
            "fwd-delete": Key.delete,
            "up": Key.up, "arrow-up": Key.up,
            "down": Key.down, "arrow-down": Key.down,
            "left": Key.left, "arrow-left": Key.left,
            "right": Key.right, "arrow-right": Key.right,
            "home": Key.home, "end": Key.end,
            "page-up": Key.page_up, "page-down": Key.page_down,
            "pageup": Key.page_up, "pagedown": Key.page_down,
            "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
            "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
            "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
            "shift": Key.shift, "ctrl": Key.ctrl, "control": Key.ctrl,
            "alt": Key.alt, "option": Key.alt,
            "command": Key.cmd, "cmd": Key.cmd, "super": Key.cmd,
        }
        lower = name.lower()
        if lower in key_map:
            return key_map[lower]
        if len(name) == 1:
            return KeyCode.from_char(name)
        return None

    def click(self, x, y, button="left", clicks=1):
        from pynput.mouse import Button, Controller
        mouse = Controller()
        mouse.position = (int(x), int(y))
        time.sleep(0.05)
        btn = Button.right if button == "right" else Button.left
        mouse.click(btn, int(clicks))
        time.sleep(0.1)

    def move(self, x, y):
        from pynput.mouse import Controller
        Controller().position = (int(x), int(y))

    def drag(self, sx, sy, ex, ey, duration=0.5, button="left"):
        from pynput.mouse import Button, Controller
        mouse = Controller()
        btn = Button.right if button == "right" else Button.left
        mouse.position = (int(sx), int(sy))
        time.sleep(0.1)
        mouse.press(btn)
        time.sleep(0.05)
        steps = max(20, int(duration * 60))
        for i in range(1, steps + 1):
            progress = i / steps
            x = sx + (ex - sx) * progress
            y = sy + (ey - sy) * progress
            mouse.position = (int(x), int(y))
            time.sleep(duration / steps)
        mouse.position = (int(ex), int(ey))
        time.sleep(0.05)
        mouse.release(btn)
        time.sleep(0.1)

    def key_press(self, key_name):
        from pynput.keyboard import Controller
        kb = Controller()
        key = self._resolve_key(key_name)
        if key:
            kb.press(key)
            kb.release(key)
        else:
            raise ValueError(f"Unknown key: {key_name}")

    def key_combo(self, *keys):
        from pynput.keyboard import Controller
        kb = Controller()
        resolved = [self._resolve_key(k) for k in keys]
        if any(k is None for k in resolved):
            bad = [keys[i] for i, k in enumerate(resolved) if k is None]
            raise ValueError(f"Unknown keys: {bad}")
        for k in resolved:
            kb.press(k)
        time.sleep(0.05)
        for k in reversed(resolved):
            kb.release(k)

    def type_text(self, text):
        from pynput.keyboard import Controller
        Controller().type(text)

    def paste_text(self, text):
        self.set_clipboard(text)
        time.sleep(0.1)
        mod = "command" if self.platform == "darwin" else "ctrl"
        self.key_combo(mod, "v")

    def activate_app(self, app_name):
        if self.platform == "darwin":
            try:
                subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to set frontmost of process "{app_name}" to true'],
                    capture_output=True, timeout=5)
                time.sleep(0.3)
            except Exception:
                subprocess.run(["open", "-a", app_name], capture_output=True, timeout=5)
                time.sleep(0.5)

    def set_clipboard(self, text):
        if self.platform == "darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE,
                                  env={"LANG": "en_US.UTF-8"})
            p.communicate(text.encode("utf-8"))
        elif self.platform == "windows":
            subprocess.run(["clip"], input=text.encode("utf-16le"), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=text.encode("utf-8"), check=True)

    def get_clipboard(self) -> str:
        if self.platform == "darwin":
            return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        elif self.platform == "windows":
            return subprocess.run(["powershell", "-command", "Get-Clipboard"],
                                   capture_output=True, text=True).stdout.strip()
        else:
            return subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                   capture_output=True, text=True).stdout


# ═══════════════════════════════════════════
# VMTarget — remote VM via HTTP API
# ═══════════════════════════════════════════

class VMTarget(ActionTarget):
    """Execute actions on a remote VM via HTTP API."""

    def __init__(self, url: str, platform_name: str = "linux"):
        super().__init__(platform_name)
        self.url = url.rstrip("/")

    def _exec(self, command: str, timeout: int = 30) -> dict:
        result = subprocess.run(
            ["/usr/bin/curl", "-s", "--connect-timeout", "10", "-m", str(timeout),
             "-X", "POST", f"{self.url}/execute",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"command": command})],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"error": f"Failed to parse: {result.stdout[:200]}"}

    def _exec_script(self, script: str, timeout: int = 30) -> dict:
        b64 = base64.b64encode(script.encode()).decode()
        cmd = (
            f"python3 -c \""
            f"import base64; "
            f"s=base64.b64decode('{b64}').decode(); "
            f"open('/tmp/_vm_script.py','w').write(s); "
            f"exec(s)"
            f"\""
        )
        return self._exec(cmd, timeout=timeout)

    def click(self, x, y, button="left", clicks=1):
        btn = "left" if button == "left" else "right"
        self._exec(f"python3 -c \"import pyautogui; pyautogui.click({int(x)}, {int(y)}, button='{btn}', clicks={clicks})\"")
        time.sleep(0.3)

    def move(self, x, y):
        self._exec(f"python3 -c \"import pyautogui; pyautogui.moveTo({int(x)}, {int(y)})\"")

    def drag(self, sx, sy, ex, ey, duration=0.5, button="left"):
        self._exec(
            f"python3 -c \"import pyautogui; "
            f"pyautogui.moveTo({int(sx)}, {int(sy)}); "
            f"pyautogui.drag({int(ex - sx)}, {int(ey - sy)}, duration={duration})\""
        )

    def key_press(self, key_name):
        self._exec(f"python3 -c \"import pyautogui; pyautogui.press('{key_name}')\"")
        time.sleep(0.2)

    def key_combo(self, *keys):
        key_list = "', '".join(keys)
        self._exec(f"python3 -c \"import pyautogui; pyautogui.hotkey('{key_list}')\"")
        time.sleep(0.3)

    def type_text(self, text):
        b64 = base64.b64encode(text.encode()).decode()
        script = f"""
import base64, subprocess, sys

text = base64.b64decode('{b64}').decode()

# Try xdotool first (handles all characters)
try:
    r = subprocess.run(
        ['xdotool', 'type', '--clearmodifiers', '--delay', '25', text],
        capture_output=True, timeout=30
    )
    if r.returncode == 0:
        sys.exit(0)
except FileNotFoundError:
    pass

# Fallback: pyautogui character by character
import pyautogui, time

SHIFT_MAP = {{
    '(': '9', ')': '0', ':': ';', '!': '1', '@': '2', '#': '3',
    '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '_': '-',
    '+': '=', '{{': '[', '}}': ']', '|': '\\\\', '~': '`', '<': ',',
    '>': '.', '?': '/', '"': "'",
}}

for ch in text:
    if ch in SHIFT_MAP:
        pyautogui.hotkey('shift', SHIFT_MAP[ch])
    elif ch == ' ':
        pyautogui.press('space')
    elif ch == '\\n':
        pyautogui.press('return')
    elif ch == '\\t':
        pyautogui.press('tab')
    elif ch.isupper():
        pyautogui.hotkey('shift', ch.lower())
    else:
        try:
            pyautogui.press(ch)
        except Exception:
            pass
    time.sleep(0.02)
"""
        self._exec_script(script)
        time.sleep(0.3)

    def paste_text(self, text):
        b64 = base64.b64encode(text.encode()).decode()
        script = f"""
import base64, subprocess, sys, time

text = base64.b64decode('{b64}').decode()

with open('/tmp/_vm_clip.txt', 'w') as f:
    f.write(text)

# Try xclip
try:
    r = subprocess.run(
        'xclip -selection clipboard < /tmp/_vm_clip.txt',
        shell=True, capture_output=True, timeout=5
    )
    if r.returncode == 0:
        import pyautogui
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)
        sys.exit(0)
except Exception:
    pass

# Try xsel
try:
    r = subprocess.run(
        'xsel --clipboard --input < /tmp/_vm_clip.txt',
        shell=True, capture_output=True, timeout=5
    )
    if r.returncode == 0:
        import pyautogui
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)
        sys.exit(0)
except Exception:
    pass

# Fallback: type it
import pyautogui
pyautogui.typewrite(text[:200], interval=0.02)
"""
        self._exec_script(script)
        time.sleep(0.3)

    def activate_app(self, app_name):
        self._exec(f"python3 -c \"import subprocess; subprocess.run(['wmctrl', '-a', '{app_name}'])\"")

    def set_clipboard(self, text):
        b64 = base64.b64encode(text.encode()).decode()
        self._exec(f"python3 -c \"import base64; open('/tmp/_clip.txt','w').write(base64.b64decode('{b64}').decode()); __import__('subprocess').run('xclip -selection clipboard < /tmp/_clip.txt', shell=True)\"")

    def get_clipboard(self) -> str:
        r = self._exec("xclip -selection clipboard -o")
        return r.get("output", "")


# ═══════════════════════════════════════════
# Target registry + dispatch
# ═══════════════════════════════════════════

_targets: dict[str, ActionTarget] = {}
_default_target: str = "local"

# Auto-register local target
_targets["local"] = LocalTarget()


def register(name: str, target: ActionTarget):
    """Register a named action target."""
    _targets[name] = target


def set_default(name: str):
    """Set the default action target."""
    global _default_target
    if name not in _targets:
        raise ValueError(f"Unknown target: {name}. Registered: {list(_targets.keys())}")
    _default_target = name


def get_target(name: str = None) -> ActionTarget:
    """Get a target by name, or the default."""
    name = name or _default_target
    if name not in _targets:
        raise ValueError(f"Unknown target: {name}. Registered: {list(_targets.keys())}")
    return _targets[name]


def get_default_name() -> str:
    """Get the name of the default target."""
    return _default_target


# ═══════════════════════════════════════════
# Backwards-compatible configure()
# ═══════════════════════════════════════════

# Keep _vm_url and _backend for code that reads them directly
_backend = "local"
_vm_url = None


def configure(vm_url: str = None):
    """Configure the input backend. Backwards-compatible wrapper.

    Args:
        vm_url: If provided, registers a VM target and sets it as default.
    """
    global _backend, _vm_url
    if vm_url:
        url = vm_url.rstrip("/")
        _backend = "vm"
        _vm_url = url
        register("vm", VMTarget(url, platform_name="linux"))
        set_default("vm")
    else:
        _backend = "local"
        _vm_url = None
        set_default("local")


# ═══════════════════════════════════════════
# Public API — dispatches to active target
# ═══════════════════════════════════════════

def mouse_click(x, y, button="left", clicks=1, target=None):
    get_target(target).click(x, y, button, clicks)

def mouse_move(x, y, target=None):
    get_target(target).move(x, y)

def mouse_double_click(x, y, target=None):
    mouse_click(x, y, clicks=2, target=target)

def mouse_right_click(x, y, target=None):
    mouse_click(x, y, button="right", target=target)

def mouse_drag(start_x, start_y, end_x, end_y, duration=0.5, button="left", target=None):
    get_target(target).drag(start_x, start_y, end_x, end_y, duration, button)

def key_press(key_name, target=None):
    t = get_target(target)
    # Check semantic keys first
    combo = t.resolve_semantic_key(key_name)
    if combo:
        t.key_combo(*combo)
    else:
        t.key_press(key_name)

def key_combo(*keys, target=None):
    t = get_target(target)
    # If single semantic key, resolve it
    if len(keys) == 1:
        combo = t.resolve_semantic_key(keys[0])
        if combo:
            t.key_combo(*combo)
            return
    t.key_combo(*keys)

def type_text(text, target=None):
    get_target(target).type_text(text)

def paste_text(text, target=None):
    get_target(target).paste_text(text)

def activate_app(app_name, target=None):
    get_target(target).activate_app(app_name)

def set_clipboard(text, target=None):
    get_target(target).set_clipboard(text)

def get_clipboard(target=None) -> str:
    return get_target(target).get_clipboard()

def get_frontmost_app(target=None):
    t = get_target(target)
    if isinstance(t, VMTarget):
        return "VM Desktop"
    if HOST_SYSTEM == "Darwin":
        try:
            r = subprocess.run(["osascript", "-e",
                'tell application "System Events" to return name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except Exception:
            return "unknown"
    return "unknown"

def verify_frontmost(expected_app, target=None):
    actual = get_frontmost_app(target)
    return actual == expected_app, actual

def click_at(x, y, target=None):
    mouse_click(x, y, target=target)

def send_keys(combo_string, target=None):
    parts = combo_string.lower().split("-")
    if len(parts) == 1:
        key_press(parts[0], target=target)
    else:
        key_combo(*parts, target=target)

def get_window_bounds(app_name):
    if HOST_SYSTEM == "Darwin":
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
