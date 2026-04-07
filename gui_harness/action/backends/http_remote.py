"""HTTP remote backend — for VMs with HTTP execute/screenshot API (e.g., OSWorld)."""

import requests
import time
import os

_NO_PROXY = {"http": None, "https": None}


def _exec(remote_url, command, timeout=30):
    """Execute a command on remote VM via HTTP API."""
    for attempt in range(3):
        try:
            r = requests.post(f"{remote_url}/execute", json={"command": command}, timeout=timeout, proxies=_NO_PROXY)
            result = r.json()
            if result.get("error"):
                print(f"remote error: {result['error'][:200]}")
            return result
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"remote connection failed: {e}")
                return {"error": str(e)}


def click(x, y, remote_url=None):
    _exec(remote_url, ["python3", "-c", f"import pyautogui; pyautogui.click({int(x)}, {int(y)})"])
    print(f"clicked ({x}, {y})")


def double_click(x, y, remote_url=None):
    _exec(remote_url, ["python3", "-c", f"import pyautogui; pyautogui.click({int(x)}, {int(y)}, clicks=2)"])
    print(f"double_clicked ({x}, {y})")


def right_click(x, y, remote_url=None):
    _exec(remote_url, ["python3", "-c", f"import pyautogui; pyautogui.click({int(x)}, {int(y)}, button='right')"])
    print(f"right_clicked ({x}, {y})")


def type_text(text, remote_url=None):
    # Use pyautogui.typewrite() — the same method OSWorld uses internally.
    # Available on all OSWorld VMs without extra installs.
    # typewrite handles uppercase via shift automatically.
    result = _exec(remote_url, ["python3", "-c",
        f"import pyautogui; pyautogui.typewrite({repr(text)}, interval=0.02)"])
    if result and result.get("status") == "error":
        print(f"ERROR: type_text failed: {result.get('message', 'unknown')}")
        return
    print(f"typed: {text[:50]}{'...' if len(text) > 50 else ''}")


def key(keyname, remote_url=None):
    # Map common key names to pyautogui names
    _exec(remote_url, ["python3", "-c", f"import pyautogui; pyautogui.press('{keyname}')"])
    print(f"key: {keyname}")


def shortcut(keys, remote_url=None):
    # Parse "ctrl+s" → pyautogui.hotkey("ctrl", "s")
    key_list = keys.split("+")
    args = ", ".join(f"'{k.strip()}'" for k in key_list)
    _exec(remote_url, ["python3", "-c", f"import pyautogui; pyautogui.hotkey({args})"])
    print(f"shortcut: {keys}")


def screenshot(path="/tmp/gui_screenshot.png", remote_url=None):
    """Download screenshot from remote VM."""
    try:
        r = requests.get(f"{remote_url}/screenshot", timeout=10, proxies=_NO_PROXY)
        with open(path, "wb") as f:
            f.write(r.content)
        print(f"screenshot: {path} ({len(r.content)} bytes)")
    except Exception as e:
        print(f"screenshot failed: {e}")


def focus(title, remote_url=None):
    _exec(remote_url, ["python3", "-c",
        f"import subprocess; subprocess.run(['wmctrl', '-a', '{title}'], capture_output=True)"])
    print(f"focused: {title}")


def close(title, remote_url=None):
    _exec(remote_url, ["python3", "-c",
        f"import subprocess; subprocess.run(['wmctrl', '-c', '{title}'], capture_output=True)"])
    print(f"closed: {title}")


def list_windows(remote_url=None):
    result = _exec(remote_url, ["wmctrl", "-l"])
    print(result.get("output", "").strip())
