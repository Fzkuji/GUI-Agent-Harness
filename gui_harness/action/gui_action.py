#!/usr/bin/env python3
"""
Unified GUI Action Interface.

Usage:
    # Local (default — operates on this machine)
    python3 gui_action.py click 500 300
    python3 gui_action.py type "hello world"
    python3 gui_action.py screenshot /tmp/s.png
    python3 gui_action.py shortcut ctrl+s
    python3 gui_action.py key enter
    python3 gui_action.py focus "LibreOffice Calc"
    python3 gui_action.py close "window title"
    python3 gui_action.py list_windows

    # Remote (add --remote URL)
    python3 gui_action.py click 500 300 --remote http://172.16.105.128:5000
    python3 gui_action.py type "hello" --remote http://172.16.105.128:5000

The script auto-detects local platform (macOS/Windows/Linux) and routes
to the correct backend. For remote targets, it uses the URL protocol
(http/ssh) to select the backend.
"""

import sys
import os
import argparse

def get_local_backend():
    """Select local backend based on current platform.

    macOS uses a dedicated backend (screencapture / osascript / cliclick).
    Windows and Linux share the cross-platform ``local`` backend
    (pynput + Pillow + ctypes/wmctrl).
    """
    if sys.platform == "darwin":
        from gui_harness.action.backends import mac_local
        return mac_local
    from gui_harness.action.backends import local
    return local


def get_remote_backend(remote_url):
    """Select remote backend based on URL protocol."""
    if remote_url.startswith("http"):
        from gui_harness.action.backends import http_remote
        return http_remote
    elif remote_url.startswith("ssh"):
        raise NotImplementedError("SSH remote backend not yet implemented")
    else:
        raise ValueError(f"Unknown remote protocol: {remote_url}")


def main():
    parser = argparse.ArgumentParser(description="Unified GUI Action")
    parser.add_argument("action", choices=[
        "click", "double_click", "right_click",
        "type", "key", "shortcut",
        "screenshot", "focus", "close", "list_windows"
    ])
    parser.add_argument("args", nargs="*", help="Action arguments")
    parser.add_argument("--remote", type=str, default=None,
                        help="Remote target URL (e.g., http://172.16.105.128:5000)")

    args = parser.parse_args()

    # Select backend
    if args.remote:
        backend = get_remote_backend(args.remote)
        remote_url = args.remote
    else:
        backend = get_local_backend()
        remote_url = None

    # Dispatch action
    action_args = args.args
    
    if args.action == "click":
        if len(action_args) != 2:
            print("Usage: click X Y"); sys.exit(1)
        fn_args = [int(action_args[0]), int(action_args[1])]
        if remote_url: fn_args.append(remote_url)
        backend.click(*fn_args) if not remote_url else backend.click(fn_args[0], fn_args[1], remote_url=remote_url)

    elif args.action == "double_click":
        if len(action_args) != 2:
            print("Usage: double_click X Y"); sys.exit(1)
        if remote_url:
            backend.double_click(int(action_args[0]), int(action_args[1]), remote_url=remote_url)
        else:
            backend.double_click(int(action_args[0]), int(action_args[1]))

    elif args.action == "right_click":
        if len(action_args) != 2:
            print("Usage: right_click X Y"); sys.exit(1)
        if remote_url:
            backend.right_click(int(action_args[0]), int(action_args[1]), remote_url=remote_url)
        else:
            backend.right_click(int(action_args[0]), int(action_args[1]))

    elif args.action == "type":
        if len(action_args) < 1:
            print("Usage: type \"text\""); sys.exit(1)
        text = " ".join(action_args)
        if remote_url:
            backend.type_text(text, remote_url=remote_url)
        else:
            backend.type_text(text)

    elif args.action == "key":
        if len(action_args) != 1:
            print("Usage: key <keyname>"); sys.exit(1)
        if remote_url:
            backend.key(action_args[0], remote_url=remote_url)
        else:
            backend.key(action_args[0])

    elif args.action == "shortcut":
        if len(action_args) != 1:
            print("Usage: shortcut <keys> (e.g., ctrl+s)"); sys.exit(1)
        if remote_url:
            backend.shortcut(action_args[0], remote_url=remote_url)
        else:
            backend.shortcut(action_args[0])

    elif args.action == "screenshot":
        import tempfile
        path = action_args[0] if action_args else os.path.join(
            tempfile.gettempdir(), "gui_screenshot.png")
        if remote_url:
            backend.screenshot(path, remote_url=remote_url)
        else:
            backend.screenshot(path)

    elif args.action == "focus":
        if len(action_args) < 1:
            print("Usage: focus \"window title\""); sys.exit(1)
        title = " ".join(action_args)
        if remote_url:
            backend.focus(title, remote_url=remote_url)
        else:
            backend.focus(title)

    elif args.action == "close":
        if len(action_args) < 1:
            print("Usage: close \"window title\""); sys.exit(1)
        title = " ".join(action_args)
        if remote_url:
            backend.close(title, remote_url=remote_url)
        else:
            backend.close(title)

    elif args.action == "list_windows":
        if remote_url:
            backend.list_windows(remote_url=remote_url)
        else:
            backend.list_windows()


if __name__ == "__main__":
    main()
