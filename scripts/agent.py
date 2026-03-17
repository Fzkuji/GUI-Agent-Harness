#!/usr/bin/env python3
"""
GUI Agent — unified entry point for all desktop automation.

Usage:
    python3 agent.py "给小明发微信消息说明天见"
    python3 agent.py "打开Discord的设置"
    python3 agent.py "查看Chrome里JupyterLab的GPU状态"

This script:
1. Parses the natural language intent
2. Checks app memory (learn if needed)
3. Executes the action (navigate, click, type, verify)
4. Returns result

It bridges SKILL.md rules and the underlying scripts (app_memory, ui_detector, gui_agent).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
MEMORY_DIR = SKILL_DIR / "memory" / "apps"

# Python env
VENV = os.path.expanduser("~/gui-actor-env/bin/python3")
if not os.path.exists(VENV):
    VENV = "python3"


def run_script(script_name, args_list, timeout=30):
    """Run a script from the scripts directory."""
    cmd = [VENV, str(SCRIPT_DIR / script_name)] + args_list
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"})
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "Timeout", 1


def app_has_memory(app_name):
    """Check if an app has been learned."""
    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    profile = app_dir / "profile.json"
    if not profile.exists():
        return False
    with open(profile) as f:
        data = json.load(f)
    return len(data.get("components", {})) > 5


def ensure_app_learned(app_name):
    """Learn an app if not in memory."""
    if app_has_memory(app_name):
        return True
    print(f"  🧠 First time with {app_name}, learning UI...")
    out, code = run_script("app_memory.py", ["learn", "--app", app_name], timeout=30)
    print(out)
    return code == 0


def resolve_app_name(raw_name):
    """Resolve common app name aliases."""
    aliases = {
        "微信": "WeChat", "wechat": "WeChat",
        "chrome": "Google Chrome", "谷歌浏览器": "Google Chrome", "浏览器": "Google Chrome",
        "discord": "Discord",
        "telegram": "Telegram", "tg": "Telegram",
        "设置": "System Settings", "系统设置": "System Settings",
    }
    return aliases.get(raw_name.lower(), raw_name)


def activate_app(app_name):
    """Bring app to front."""
    subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'],
                   capture_output=True, timeout=5)
    time.sleep(0.5)


def get_window_bounds(app_name):
    """Get window position and size."""
    try:
        r = subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to tell process "{app_name}" '
             f'to return {{position, size}} of window 1'],
            capture_output=True, text=True, timeout=5)
        nums = [int(n.strip()) for n in r.stdout.split(",") if n.strip()]
        if len(nums) == 4:
            return tuple(nums)
    except:
        pass
    return None


# ═══════════════════════════════════════════
# Actions
# ═══════════════════════════════════════════

def action_send_message(app_name, contact, message):
    """Send a message in a chat app."""
    app_name = resolve_app_name(app_name)
    ensure_app_learned(app_name)
    activate_app(app_name)

    print(f"  📨 Sending to {contact}: {message}")
    out, code = run_script("gui_agent.py", [
        "task", "send_message", "--app", app_name,
        "--param", f"contact={contact}",
        "--param", f"message={message}",
    ], timeout=30)
    print(out)
    return code == 0


def action_read_messages(app_name, contact=None):
    """Read messages in a chat app."""
    app_name = resolve_app_name(app_name)
    ensure_app_learned(app_name)
    activate_app(app_name)

    params = ["task", "read_messages", "--app", app_name]
    if contact:
        params.extend(["--param", f"contact={contact}"])
    out, code = run_script("gui_agent.py", params, timeout=20)
    print(out)
    return out


def action_click_component(app_name, component):
    """Click a named component in an app."""
    app_name = resolve_app_name(app_name)
    ensure_app_learned(app_name)
    activate_app(app_name)

    print(f"  🖱️ Clicking {component} in {app_name}")
    out, code = run_script("app_memory.py", [
        "click", "--app", app_name, "--component", component
    ], timeout=15)
    print(out)
    return code == 0


def action_open_app(app_name):
    """Open/activate an app."""
    app_name = resolve_app_name(app_name)
    activate_app(app_name)
    print(f"  ✅ Opened {app_name}")
    return True


def action_navigate_browser(url):
    """Navigate browser to URL."""
    subprocess.run(["open", "-a", "Google Chrome", url], capture_output=True, timeout=10)
    time.sleep(3)
    print(f"  🌐 Navigated to {url}")
    return True


def action_learn_app(app_name):
    """Learn an app's UI."""
    app_name = resolve_app_name(app_name)
    print(f"  🧠 Learning {app_name}...")
    out, code = run_script("app_memory.py", ["learn", "--app", app_name], timeout=30)
    print(out)
    return code == 0


def action_detect(app_name):
    """Detect and match components in an app."""
    app_name = resolve_app_name(app_name)
    ensure_app_learned(app_name)
    activate_app(app_name)

    out, code = run_script("app_memory.py", ["detect", "--app", app_name], timeout=20)
    print(out)
    return out


def action_list_components(app_name):
    """List known components for an app."""
    app_name = resolve_app_name(app_name)
    out, code = run_script("app_memory.py", ["list", "--app", app_name], timeout=10)
    print(out)
    return out


def action_screenshot_and_read(app_name=None):
    """Take screenshot and OCR the current screen/window."""
    if app_name:
        app_name = resolve_app_name(app_name)
        activate_app(app_name)

    out, code = run_script("gui_agent.py", [
        "task", "read_screen", "--app", app_name or "Finder"
    ], timeout=15)
    print(out)
    return out


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

ACTIONS = {
    "send_message": {
        "fn": action_send_message,
        "args": ["app", "contact", "message"],
        "desc": "Send a message in a chat app",
    },
    "read_messages": {
        "fn": action_read_messages,
        "args": ["app"],
        "optional": ["contact"],
        "desc": "Read messages in a chat app",
    },
    "click": {
        "fn": action_click_component,
        "args": ["app", "component"],
        "desc": "Click a named UI component",
    },
    "open": {
        "fn": action_open_app,
        "args": ["app"],
        "desc": "Open/activate an app",
    },
    "navigate": {
        "fn": action_navigate_browser,
        "args": ["url"],
        "desc": "Navigate browser to URL",
    },
    "learn": {
        "fn": action_learn_app,
        "args": ["app"],
        "desc": "Learn an app's UI elements",
    },
    "detect": {
        "fn": action_detect,
        "args": ["app"],
        "desc": "Detect and match components",
    },
    "list": {
        "fn": action_list_components,
        "args": ["app"],
        "desc": "List known components",
    },
    "read_screen": {
        "fn": action_screenshot_and_read,
        "optional": ["app"],
        "desc": "Screenshot and OCR current screen",
    },
}


def main():
    parser = argparse.ArgumentParser(description="GUI Agent — unified desktop automation")
    parser.add_argument("action", nargs="?", help="Action name or natural language task")
    parser.add_argument("--app", help="App name")
    parser.add_argument("--contact", help="Contact name (for messaging)")
    parser.add_argument("--message", help="Message text")
    parser.add_argument("--component", help="Component name to click")
    parser.add_argument("--url", help="URL to navigate to")
    parser.add_argument("--list-actions", action="store_true", help="List available actions")
    args = parser.parse_args()

    if args.list_actions or not args.action:
        print("GUI Agent — Available Actions:")
        print()
        for name, info in ACTIONS.items():
            req = ", ".join(info.get("args", []))
            opt = ", ".join(info.get("optional", []))
            print(f"  {name:20s} {info['desc']}")
            if req:
                print(f"  {'':20s} required: {req}")
            if opt:
                print(f"  {'':20s} optional: {opt}")
            print()
        return

    action_name = args.action.lower()

    if action_name in ACTIONS:
        action_info = ACTIONS[action_name]
        fn = action_info["fn"]

        # Build kwargs from args
        kwargs = {}
        if args.app:
            kwargs["app_name" if "app_name" in fn.__code__.co_varnames else "app"] = args.app
        if args.contact:
            kwargs["contact"] = args.contact
        if args.message:
            kwargs["message"] = args.message
        if args.component:
            kwargs["component"] = args.component
        if args.url:
            kwargs["url"] = args.url

        # Handle app_name vs app parameter naming
        if "app_name" in fn.__code__.co_varnames and "app" in kwargs:
            kwargs["app_name"] = kwargs.pop("app")

        result = fn(**kwargs)
        if result is True:
            print("\n✅ Done")
        elif result is False:
            print("\n❌ Failed")
    else:
        print(f"Unknown action: {action_name}")
        print(f"Available: {', '.join(ACTIONS.keys())}")
        print(f"Run with --list-actions for details")


if __name__ == "__main__":
    main()
