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


def get_known_pages(app_name):
    """Get list of learned pages for an app."""
    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    profile_path = app_dir / "profile.json"
    if not profile_path.exists():
        return []
    with open(profile_path) as f:
        profile = json.load(f)
    return list(profile.get("pages", {}).keys())


def revise_app(app_name, workflow=None, required_components=None):
    """Smart check: decide if memory is sufficient for current workflow.

    Decision logic based on WORKFLOW, not just app:
    1. App never learned → full learn
    2. App learned, but workflow/page is new → learn this page
    3. App learned, workflow known → template match to verify
       - Match rate ≥ 80% → memory good, skip learn
       - Match rate < 80% → incremental learn (update)

    Args:
        app_name: App name
        workflow: Task/page name (e.g., "smart_scan", "malware_removal", "send_message")
                 If None, checks overall app memory.
        required_components: Specific components needed for this task.

    Returns:
        (ready, match_info)
    """
    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    profile_path = app_dir / "profile.json"

    # Case 1: App never learned
    if not profile_path.exists():
        page = workflow or "main"
        print(f"  🧠 No memory for {app_name}, learning (page: {page})...")
        out, code = run_script("app_memory.py", ["learn", "--app", app_name, "--page", page], timeout=30)
        print(out)
        return code == 0, {"action": "full_learn", "page": page}

    with open(profile_path) as f:
        profile = json.load(f)

    known_pages = list(profile.get("pages", {}).keys())

    # Case 2: Workflow/page is new (never learned this page)
    if workflow and workflow not in known_pages:
        print(f"  🆕 New workflow '{workflow}' for {app_name} (known pages: {known_pages})")
        print(f"  🧠 Learning new page...")
        activate_app(app_name)
        out, code = run_script("app_memory.py", ["learn", "--app", app_name, "--page", workflow], timeout=30)
        print(out)
        return code == 0, {"action": "learn_new_page", "page": workflow, "known_pages": known_pages}

    # Case 3: Workflow known → verify via template match
    total_components = len(profile.get("components", {}))
    if total_components == 0:
        page = workflow or "main"
        print(f"  🧠 Empty memory for {app_name}, learning...")
        out, code = run_script("app_memory.py", ["learn", "--app", app_name, "--page", page], timeout=30)
        print(out)
        return code == 0, {"action": "full_learn", "page": page}

    activate_app(app_name)
    out, code = run_script("app_memory.py", ["detect", "--app", app_name], timeout=20)

    # Parse results
    matched_count = out.count("✅")
    unknown_count = 0
    for line in out.split("\n"):
        if "unknown" in line.lower():
            try:
                unknown_count = int(line.split()[-2])
            except:
                pass

    match_rate = matched_count / max(total_components, 1)

    info = {
        "total": total_components,
        "matched": matched_count,
        "unknown": unknown_count,
        "match_rate": round(match_rate, 2),
        "workflow": workflow,
        "known_pages": known_pages,
    }

    # Check required components
    missing_required = []
    if required_components:
        for comp in required_components:
            if comp not in profile["components"]:
                missing_required.append(comp)
            elif f"✅ {comp}" not in out:
                missing_required.append(comp)

    info["missing_required"] = missing_required

    # Decision
    if match_rate >= 0.8 and not missing_required:
        print(f"  ✅ Memory is current ({matched_count}/{total_components} matched, {match_rate:.0%})")
        info["action"] = "skip"
        return True, info
    else:
        reason = []
        if match_rate < 0.8:
            reason.append(f"low match rate ({match_rate:.0%})")
        if missing_required:
            reason.append(f"missing: {missing_required}")

        page = workflow or "main"
        print(f"  🔄 Memory outdated ({', '.join(reason)}), updating page '{page}'...")
        out, code = run_script("app_memory.py", ["learn", "--app", app_name, "--page", page], timeout=30)
        print(out)
        info["action"] = "incremental_learn"
        return code == 0, info


def ensure_app_ready(app_name, workflow=None, required_components=None):
    """Ensure app is ready for the given workflow.

    Workflow-based revise:
    - App not learned → full learn
    - New workflow/page → learn new page
    - Known workflow → verify memory, update if stale
    """
    ready, info = revise_app(app_name, workflow, required_components)
    return ready


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
    try:
        subprocess.run(["osascript", "-e",
            f'tell application "System Events" to set frontmost of process "{app_name}" to true'],
            capture_output=True, timeout=5)
        time.sleep(0.3)
    except:
        subprocess.run(["open", "-a", app_name], capture_output=True, timeout=5)
        time.sleep(0.5)


def get_window_bounds(app_name):
    """Get the MAIN window position and size (largest window, not status bar panels).

    Some apps like CleanMyMac have multiple windows (status bar panel, sidebar, main window).
    We want the largest one.
    """
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
    except:
        pass
    return None


# ═══════════════════════════════════════════
# MANDATORY: Observe → Verify → Act → Confirm
# These functions enforce the Operation Protocol
# ═══════════════════════════════════════════

def observe_state(app_name):
    """STEP 0: Observe current state before any action.

    MANDATORY. Never skip this.
    Returns: {frontmost, target_visible, window, page_state, elements}
    """
    state = {}

    # 1. What app is in front?
    try:
        r = subprocess.run(["osascript", "-e",
            'tell application "System Events" to return name of first process whose frontmost is true'],
            capture_output=True, text=True, timeout=5)
        state["frontmost"] = r.stdout.strip()
    except:
        state["frontmost"] = "unknown"

    # 2. Activate target app
    activate_app(app_name)
    state["target_activated"] = True

    # 3. Get window bounds
    bounds = get_window_bounds(app_name)
    state["window"] = bounds  # (x, y, w, h) or None

    # 4. Screenshot → resize to logical (982x1512) → OCR
    #    Resized screenshot coords = screen logical coords directly.
    #    Do NOT use retina fullscreen (3024x1964) — OCR will timeout.
    subprocess.run(["/usr/sbin/screencapture", "-x", "/tmp/_observe.png"],
                   capture_output=True, timeout=5)
    subprocess.run(["sips", "-z", "982", "1512", "/tmp/_observe.png",
                    "--out", "/tmp/_observe_s.png"],
                   capture_output=True, timeout=5)

    # 5. OCR — coords are screen logical pixels (matching cliclick)
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from gui_agent import ocr_find
        all_text = ocr_find("", img_path="/tmp/_observe_s.png")

        # Filter to target window area
        if bounds:
            wx, wy, ww, wh = bounds
            window_text = [t for t in all_text
                          if wx <= t.get("cx", 0) <= wx + ww
                          and wy <= t.get("cy", 0) <= wy + wh]
        else:
            window_text = all_text

        state["visible_text"] = [t.get("text", "") for t in window_text[:30]]
        state["all_elements"] = window_text
    except Exception as e:
        state["visible_text"] = []
        state["all_elements"] = []
        state["ocr_error"] = str(e)

    # 6. Crop window screenshot for LLM vision analysis
    if bounds:
        try:
            import cv2
            img = cv2.imread("/tmp/_observe.png")
            if img is not None:
                wx, wy, ww, wh = bounds
                # Retina: ×2
                crop = img[wy*2:(wy+wh)*2, wx*2:(wx+ww)*2]
                cv2.imwrite("/tmp/_observe_window.jpg", crop,
                           [cv2.IMWRITE_JPEG_QUALITY, 60])
                state["window_screenshot"] = "/tmp/_observe_window.jpg"
        except:
            pass

    return state


def explore(app_name, question=None):
    """Use LLM vision to understand current screen state.

    Crops the target app window, saves it for LLM to analyze.
    Returns the screenshot path — the calling LLM agent should
    use the image tool to look at it and decide next steps.

    This is NOT optional when OCR/template match fails.
    """
    state = observe_state(app_name)
    screenshot_path = state.get("window_screenshot", "/tmp/_observe_s.png")

    # Copy to workspace so LLM can access it
    import shutil
    output = str(SKILL_DIR / "detected" / "explore.jpg")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    shutil.copy(screenshot_path, output)

    result = {
        "screenshot": output,
        "window": state.get("window"),
        "ocr_text": state.get("visible_text", [])[:15],
        "question": question or "What is the current state of this app? What should I do next?",
    }

    print(f"  🔍 EXPLORE: screenshot saved to {output}", flush=True)
    print(f"  📋 OCR found: {result['ocr_text'][:5]}", flush=True)
    print(f"  ❓ Question: {result['question']}", flush=True)
    print(f"  → Agent should now use image tool to look at {output}", flush=True)

    return result


def find_element_in_window(element_text, state, exact=False, position="any"):
    """Find an element in the target window.

    Args:
        element_text: text to search for
        state: from observe_state()
        exact: if True, match exact text only (not substring).
               "Scan" won't match "Deep Scan" or "Smart Scan".
        position: "any", "bottom", "top", "left", "right"
                  Filters by position within the window.

    Returns: list of matching elements [{text, cx, cy}, ...]
    """
    bounds = state.get("window")
    results = []

    for el in state.get("all_elements", []):
        text = el.get("text", "")
        cx, cy = el.get("cx", 0), el.get("cy", 0)

        # Text matching
        if exact:
            if text.strip() != element_text.strip():
                continue
        else:
            if element_text.lower() not in text.lower():
                continue

        # Window bounds check
        if bounds:
            wx, wy, ww, wh = bounds
            if not (wx <= cx <= wx + ww and wy <= cy <= wy + wh):
                continue

            # Position filter within window
            rel_y = (cy - wy) / wh  # 0.0 = top, 1.0 = bottom
            rel_x = (cx - wx) / ww
            if position == "bottom" and rel_y < 0.7:
                continue
            elif position == "top" and rel_y > 0.3:
                continue
            elif position == "left" and rel_x > 0.4:
                continue
            elif position == "right" and rel_x < 0.6:
                continue

        results.append({"text": text, "cx": cx, "cy": cy})

    return results


def verify_element_exists(app_name, element_text, state=None, exact=False, position="any"):
    """PRE-CLICK VERIFY: Is this element actually on screen right now?

    Args:
        exact: True = exact text match only (prevents "Scan" matching "Deep Scan")
        position: filter by position in window ("bottom" for buttons)

    Returns: (exists, x, y) or (False, 0, 0)
    """
    if state is None:
        state = observe_state(app_name)

    matches = find_element_in_window(element_text, state, exact=exact, position=position)
    if matches:
        return True, matches[0]["cx"], matches[0]["cy"]
    return False, 0, 0


def safe_click(app_name, element_text, state=None, exact=False, position="any"):
    """Click with full verification: observe → verify → click → confirm.

    Args:
        exact: True = exact text match (prevents "Scan" matching "Deep Scan")
        position: "bottom" = only match elements in bottom 30% of window

    Returns: (success, message)
    """
    if state is None:
        state = observe_state(app_name)

    exists, cx, cy = verify_element_exists(app_name, element_text, state,
                                            exact=exact, position=position)
    if not exists:
        return False, f"Element '{element_text}' not found (exact={exact}, pos={position})"

    subprocess.run(["/opt/homebrew/bin/cliclick", f"c:{cx},{cy}"], check=True)

    time.sleep(0.5)
    return True, f"Clicked '{element_text}' at ({cx},{cy})"


def poll_and_click(app_name, target_text, max_wait=30, interval=2,
                   exact=False, position="any"):
    """Event-driven: poll until target appears, then click.

    Args:
        exact: True = exact match only
        position: "bottom" = button area

    Returns: (found_and_clicked, message)
    """
    for i in range(max_wait // interval):
        state = observe_state(app_name)
        exists, cx, cy = verify_element_exists(app_name, target_text, state,
                                                exact=exact, position=position)
        if exists:
            subprocess.run(["/opt/homebrew/bin/cliclick", f"c:{cx},{cy}"], check=True)
            return True, f"Clicked '{target_text}' at ({cx},{cy})"
        time.sleep(interval)

    return False, f"Timeout waiting for '{target_text}'"


# ═══════════════════════════════════════════
# Actions
# ═══════════════════════════════════════════

def wait_for_element(app_name, target, max_wait=30, interval=2):
    """Event-driven wait: poll until target element appears.

    target can be:
    - component name (template match)
    - text string (OCR search)

    Returns: (found, x, y) or (False, 0, 0) on timeout
    """
    import cv2
    sys.path.insert(0, str(SCRIPT_DIR))

    for i in range(max_wait // interval):
        # Screenshot
        subprocess.run(["/usr/sbin/screencapture", "-x", "/tmp/_wait.png"],
                       capture_output=True, timeout=5)
        subprocess.run(["sips", "-z", "982", "1512", "/tmp/_wait.png",
                        "--out", "/tmp/_wait_s.png"],
                       capture_output=True, timeout=5)

        # Try template match first
        try:
            from app_memory import match_component
            img = cv2.imread("/tmp/_wait_s.png")
            found, rx, ry, conf = match_component(app_name, target, img)
            if found and conf > 0.7:
                return True, rx, ry
        except:
            pass

        # Try OCR
        try:
            from gui_agent import ocr_find
            matches = ocr_find(target, img_path="/tmp/_wait_s.png")
            if matches:
                return True, matches[0]["cx"], matches[0]["cy"]
        except:
            pass

        time.sleep(interval)

    return False, 0, 0


def click_and_wait(x, y, app_name, next_target, max_wait=30):
    """Click at (x,y) then wait for next_target to appear.

    Returns: (found, next_x, next_y)
    """
    subprocess.run(["/opt/homebrew/bin/cliclick", f"c:{x},{y}"], check=True)
    return wait_for_element(app_name, next_target, max_wait=max_wait)


def action_send_message(app_name, contact, message):
    """Send a message in a chat app. Full protocol: observe → verify → act → confirm."""
    app_name = resolve_app_name(app_name)

    # STEP 0: Observe current state
    print(f"  👁 Observing state...")
    state = observe_state(app_name)
    print(f"    Frontmost: {state['frontmost']}, Window: {state.get('window')}")
    print(f"    Visible: {state['visible_text'][:5]}")

    # Ensure app is ready
    ensure_app_ready(app_name, workflow="send_message")

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
    ensure_app_ready(app_name, workflow="read_messages")
    activate_app(app_name)

    params = ["task", "read_messages", "--app", app_name]
    if contact:
        params.extend(["--param", f"contact={contact}"])
    out, code = run_script("gui_agent.py", params, timeout=20)
    print(out)
    return out


def action_click_component(app_name, component):
    """Click a named component. Full protocol: observe → verify → click → confirm."""
    app_name = resolve_app_name(app_name)

    # STEP 0: Observe
    print(f"  👁 Observing state...")
    state = observe_state(app_name)
    print(f"    Frontmost: {state['frontmost']}, Window: {state.get('window')}")

    # Ensure memory ready
    ensure_app_ready(app_name, required_components=[component])

    # PRE-CLICK: Verify component exists
    print(f"  🔍 Verifying '{component}' exists...")
    ok, msg = safe_click(app_name, component)
    if ok:
        print(f"  ✅ {msg}")
    else:
        # Fallback: use app_memory click (template match)
        print(f"  ⚠ Direct verify failed ({msg}), trying template match...")
        out, code = run_script("app_memory.py", [
            "click", "--app", app_name, "--component", component
        ], timeout=15)
        print(out)
        return code == 0

    # POST-ACTION: Verify
    new_state = observe_state(app_name)
    print(f"  📋 After click: {new_state['visible_text'][:5]}")
    return True


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


def action_detect(app_name, workflow=None):
    """Detect and match components in an app."""
    app_name = resolve_app_name(app_name)
    ensure_app_ready(app_name, workflow=workflow)
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
    "explore": {
        "fn": lambda app_name, **kw: explore(app_name, kw.get("question")),
        "args": ["app"],
        "desc": "Screenshot + OCR + save for LLM vision analysis",
    },
    "revise": {
        "fn": lambda app_name, workflow=None: revise_app(app_name, workflow=workflow),
        "args": ["app"],
        "optional": ["workflow"],
        "desc": "Check memory freshness for a workflow, learn if needed",
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
    parser.add_argument("--workflow", help="Workflow/page name (for revise logic)")
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
        if args.workflow:
            kwargs["workflow"] = args.workflow

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
