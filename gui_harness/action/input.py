#!/usr/bin/env python3
"""
gui_harness.action.input — unified input interface with backend dispatch.

Supports two backends:
  - "local" (default): uses pynput for macOS
  - "vm": sends commands to a remote VM via HTTP API

Call configure(vm_url="http://...") at startup to select the VM backend.
All functions automatically dispatch to the correct backend.
"""

from __future__ import annotations

import base64
import json
import platform
import subprocess
import time

SYSTEM = platform.system()  # "Darwin", "Windows", "Linux"

# ═══════════════════════════════════════════
# Backend configuration
# ═══════════════════════════════════════════

_backend = "local"  # "local" or "vm"
_vm_url = None


def configure(vm_url: str = None):
    """Configure the input backend.

    Args:
        vm_url: If provided, switches to VM backend (e.g. "http://172.16.82.132:5000").
                If None, uses local backend (pynput).
    """
    global _backend, _vm_url
    if vm_url:
        _backend = "vm"
        _vm_url = vm_url.rstrip("/")
    else:
        _backend = "local"
        _vm_url = None


# ═══════════════════════════════════════════
# Public API — dispatches to active backend
# ═══════════════════════════════════════════

def mouse_click(x, y, button="left", clicks=1):
    """Click at screen coordinates."""
    if _backend == "vm":
        _vm_click(int(x), int(y), button, clicks)
    else:
        _local_click(int(x), int(y), button, clicks)


def mouse_move(x, y):
    """Move mouse to screen coordinates."""
    if _backend == "vm":
        _vm_exec(f"python3 -c \"import pyautogui; pyautogui.moveTo({int(x)}, {int(y)})\"")
    else:
        from pynput.mouse import Controller
        Controller().position = (int(x), int(y))


def mouse_double_click(x, y):
    """Double click at screen coordinates."""
    mouse_click(x, y, clicks=2)


def mouse_right_click(x, y):
    """Right click at screen coordinates."""
    mouse_click(x, y, button="right")


def mouse_drag(start_x, start_y, end_x, end_y, duration=0.5, button="left"):
    """Drag from start to end coordinates."""
    if _backend == "vm":
        _vm_exec(
            f"python3 -c \"import pyautogui; "
            f"pyautogui.moveTo({int(start_x)}, {int(start_y)}); "
            f"pyautogui.drag({int(end_x - start_x)}, {int(end_y - start_y)}, "
            f"duration={duration})\""
        )
    else:
        _local_drag(start_x, start_y, end_x, end_y, duration, button)


def key_press(key_name):
    """Press and release a single key."""
    if _backend == "vm":
        _vm_key_press(key_name)
    else:
        _local_key_press(key_name)


def key_combo(*keys):
    """Press a key combination (e.g. key_combo("ctrl", "s"))."""
    if _backend == "vm":
        _vm_key_combo(*keys)
    else:
        _local_key_combo(*keys)


def type_text(text):
    """Type text into the currently focused element.

    VM: uses xdotool (preferred) or pyautogui fallback.
    Local: uses pynput.
    """
    if _backend == "vm":
        _vm_type_text(text)
    else:
        _local_type_text(text)


def paste_text(text):
    """Paste text via clipboard (works for all languages)."""
    if _backend == "vm":
        _vm_paste_text(text)
    else:
        set_clipboard(text)
        time.sleep(0.1)
        key_combo("command" if SYSTEM == "Darwin" else "ctrl", "v")


def get_frontmost_app():
    """Get the name of the currently frontmost application."""
    if _backend == "vm":
        return "VM Desktop"
    if SYSTEM == "Darwin":
        try:
            r = subprocess.run(["osascript", "-e",
                'tell application "System Events" to return name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except Exception:
            return "unknown"
    return "unknown"


def verify_frontmost(expected_app):
    """Check if the expected app is still frontmost."""
    actual = get_frontmost_app()
    return actual == expected_app, actual


def activate_app(app_name):
    """Bring app window to front."""
    if _backend == "vm":
        _vm_exec(f"python3 -c \"import subprocess; subprocess.run(['wmctrl', '-a', '{app_name}'])\"")
        return
    if SYSTEM == "Darwin":
        try:
            subprocess.run(["osascript", "-e",
                f'tell application "System Events" to set frontmost of process "{app_name}" to true'],
                capture_output=True, timeout=5)
            time.sleep(0.3)
        except Exception:
            subprocess.run(["open", "-a", app_name], capture_output=True, timeout=5)
            time.sleep(0.5)


# ═══════════════════════════════════════════
# Clipboard operations
# ═══════════════════════════════════════════

def set_clipboard(text):
    """Set clipboard content."""
    if SYSTEM == "Darwin":
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE,
                              env={"LANG": "en_US.UTF-8"})
        p.communicate(text.encode("utf-8"))
    elif SYSTEM == "Windows":
        subprocess.run(["clip"], input=text.encode("utf-16le"), check=True)
    else:
        subprocess.run(["xclip", "-selection", "clipboard"],
                       input=text.encode("utf-8"), check=True)


def get_clipboard():
    """Get clipboard content."""
    if SYSTEM == "Darwin":
        r = subprocess.run(["pbpaste"], capture_output=True, text=True)
        return r.stdout
    elif SYSTEM == "Windows":
        r = subprocess.run(["powershell", "-command", "Get-Clipboard"],
                            capture_output=True, text=True)
        return r.stdout.strip()
    else:
        r = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                            capture_output=True, text=True)
        return r.stdout


# ═══════════════════════════════════════════
# Convenience / high-level
# ═══════════════════════════════════════════

def click_at(x, y):
    """Simple left click."""
    mouse_click(x, y)


def send_keys(combo_string):
    """Parse "command-v" or "return" and execute."""
    parts = combo_string.lower().split("-")
    if len(parts) == 1:
        key_press(parts[0])
    else:
        key_combo(*parts)


def get_window_bounds(app_name):
    """Get window position and size: (x, y, w, h)."""
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
    return None


# ═══════════════════════════════════════════
# LOCAL backend (pynput — macOS)
# ═══════════════════════════════════════════

def _local_click(x, y, button="left", clicks=1):
    from pynput.mouse import Button, Controller
    mouse = Controller()
    mouse.position = (int(x), int(y))
    time.sleep(0.05)
    btn = Button.right if button == "right" else Button.left
    mouse.click(btn, int(clicks))
    time.sleep(0.1)
    mouse.position = (1500, 970)


def _local_key_press(key_name):
    from pynput.keyboard import Controller
    kb = Controller()
    key = _resolve_key(key_name)
    if key:
        kb.press(key)
        kb.release(key)
    else:
        raise ValueError(f"Unknown key: {key_name}")


def _local_key_combo(*keys):
    from pynput.keyboard import Controller
    kb = Controller()
    resolved = [_resolve_key(k) for k in keys]
    if any(k is None for k in resolved):
        bad = [keys[i] for i, k in enumerate(resolved) if k is None]
        raise ValueError(f"Unknown keys: {bad}")
    for k in resolved:
        kb.press(k)
    time.sleep(0.05)
    for k in reversed(resolved):
        kb.release(k)


def _local_type_text(text):
    from pynput.keyboard import Controller
    kb = Controller()
    kb.type(text)


def _local_drag(start_x, start_y, end_x, end_y, duration=0.5, button="left"):
    from pynput.mouse import Button, Controller
    mouse = Controller()
    btn = Button.right if button == "right" else Button.left
    mouse.position = (int(start_x), int(start_y))
    time.sleep(0.1)
    mouse.press(btn)
    time.sleep(0.05)
    steps = max(20, int(duration * 60))
    for i in range(1, steps + 1):
        progress = i / steps
        x = start_x + (end_x - start_x) * progress
        y = start_y + (end_y - start_y) * progress
        mouse.position = (int(x), int(y))
        time.sleep(duration / steps)
    mouse.position = (int(end_x), int(end_y))
    time.sleep(0.05)
    mouse.release(btn)
    time.sleep(0.1)
    mouse.position = (1500, 970)


def _resolve_key(name):
    """Resolve a key name string to pynput Key or KeyCode."""
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


# ═══════════════════════════════════════════
# VM backend (curl → pyautogui/xdotool)
# ═══════════════════════════════════════════

def _vm_exec(command: str, timeout: int = 30) -> dict:
    """Execute a command on the VM via curl subprocess."""
    result = subprocess.run(
        ["/usr/bin/curl", "-s", "--connect-timeout", "10", "-m", str(timeout),
         "-X", "POST", f"{_vm_url}/execute",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"command": command})],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"Failed to parse: {result.stdout[:200]}"}


def _vm_exec_script(script: str, timeout: int = 30) -> dict:
    """Write a Python script to VM and execute (avoids shell quoting issues)."""
    b64 = base64.b64encode(script.encode()).decode()
    cmd = (
        f"python3 -c \""
        f"import base64; "
        f"s=base64.b64decode('{b64}').decode(); "
        f"open('/tmp/_vm_script.py','w').write(s); "
        f"exec(s)"
        f"\""
    )
    return _vm_exec(cmd, timeout=timeout)


def _vm_click(x, y, button="left", clicks=1):
    btn = "left" if button == "left" else "right"
    _vm_exec(f"python3 -c \"import pyautogui; pyautogui.click({x}, {y}, button='{btn}', clicks={clicks})\"")
    time.sleep(0.3)


def _vm_key_press(key_name):
    _vm_exec(f"python3 -c \"import pyautogui; pyautogui.press('{key_name}')\"")
    time.sleep(0.2)


def _vm_key_combo(*keys):
    key_list = "', '".join(keys)
    _vm_exec(f"python3 -c \"import pyautogui; pyautogui.hotkey('{key_list}')\"")
    time.sleep(0.3)


def _vm_type_text(text):
    """Type text on VM — xdotool preferred, pyautogui fallback."""
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
    _vm_exec_script(script)
    time.sleep(0.3)


def _vm_paste_text(text):
    """Paste text via clipboard on VM."""
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

# Fallback: xdotool type
try:
    r = subprocess.run(
        ['xdotool', 'type', '--clearmodifiers', '--delay', '25', text],
        capture_output=True, timeout=30
    )
    if r.returncode == 0:
        sys.exit(0)
except FileNotFoundError:
    pass

# Last resort: pyautogui character by character
import pyautogui

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
    _vm_exec_script(script)
    time.sleep(0.3)
