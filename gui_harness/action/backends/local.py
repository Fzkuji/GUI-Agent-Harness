"""Cross-platform local backend.

Input via pynput, screenshots via Pillow/native, window control via
``gui_harness.action.window`` (Windows ctypes / Linux wmctrl/xdotool).

Used by ``gui_action.get_local_backend()`` on Windows and Linux. macOS
keeps its dedicated ``mac_local`` backend (screencapture / osascript /
cliclick) for native fidelity. All three back the same action surface:
click / double_click / right_click / type_text / key / shortcut /
screenshot / focus / close / list_windows.
"""

import os
import platform

SYSTEM = platform.system()


def click(x, y):
    from gui_harness.action.input import mouse_click
    mouse_click(int(x), int(y))
    print(f"clicked ({x}, {y})")


def double_click(x, y):
    from gui_harness.action.input import mouse_double_click
    mouse_double_click(int(x), int(y))
    print(f"double_clicked ({x}, {y})")


def right_click(x, y):
    from gui_harness.action.input import mouse_right_click
    mouse_right_click(int(x), int(y))
    print(f"right_clicked ({x}, {y})")


def type_text(text):
    from gui_harness.action.input import paste_text
    paste_text(text)
    print(f"typed: {text[:50]}{'...' if len(text) > 50 else ''}")


def key(keyname):
    from gui_harness.action.input import key_press
    key_press(keyname)
    print(f"key: {keyname}")


def shortcut(keys):
    from gui_harness.action.input import key_combo
    parts = keys.replace("+", " ").split()
    # Normalize mac-isms to the portable names pynput resolves everywhere.
    mapping = {"cmd": "ctrl", "command": "ctrl", "option": "alt"}
    parts = [mapping.get(k.lower(), k.lower()) for k in parts]
    key_combo(*parts)
    print(f"shortcut: {keys}")


def screenshot(path=None):
    from gui_harness.perception.screenshot import screenshot as _shot
    p = _shot(path)
    print(f"screenshot: {p}" if os.path.exists(p) else f"screenshot failed: {p}")


def focus(title):
    from gui_harness.action.window import activate_app
    activate_app(title)
    print(f"focused: {title}")


def close(title):
    """Best-effort close-window-by-title (no portable primitive)."""
    if SYSTEM == "Windows":
        try:
            import ctypes
            from gui_harness.action.window import _win_find
            for hwnd, _t in _win_find(title):
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            print(f"closed: {title}")
            return
        except Exception as e:
            print(f"close failed: {e}")
            return
    if SYSTEM == "Linux":
        import shutil
        import subprocess
        if shutil.which("wmctrl"):
            subprocess.run(["wmctrl", "-c", title], capture_output=True, timeout=5)
            print(f"closed: {title}")
            return
    print(f"close not supported on {SYSTEM}: {title}")


def list_windows():
    if SYSTEM == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            from gui_harness.action.window import _win_title
            u = ctypes.windll.user32
            titles = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def _cb(hwnd, _lparam):
                if u.IsWindowVisible(hwnd):
                    t = _win_title(hwnd)
                    if t:
                        titles.append(t)
                return True

            u.EnumWindows(_cb, 0)
            print("\n".join(titles))
            return
        except Exception as e:
            print(f"list_windows failed: {e}")
            return
    if SYSTEM == "Linux":
        import shutil
        import subprocess
        if shutil.which("wmctrl"):
            r = subprocess.run(["wmctrl", "-l"], capture_output=True,
                               text=True, timeout=5)
            print(r.stdout.strip())
            return
    print(f"list_windows not supported on {SYSTEM}")
