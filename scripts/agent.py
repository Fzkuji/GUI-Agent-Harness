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
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
MEMORY_DIR = SKILL_DIR / "memory" / "apps"

BROWSER_APPS = {"Google Chrome", "Safari", "Firefox", "Arc", "Microsoft Edge", "Brave Browser"}

# Tracker integration — auto-tick workflow counters
def _tick(counter, n=1):
    """Tick a tracker counter. Best-effort, never fails."""
    try:
        tracker_scripts = str(SKILL_DIR / "skills" / "gui-report" / "scripts")
        if tracker_scripts not in sys.path:
            sys.path.insert(0, tracker_scripts)
        from tracker import tick_counter
        tick_counter(counter, n)
    except Exception:
        pass

def _auto_report():
    """Get auto-report summary string. Best-effort."""
    try:
        tracker_scripts = str(SKILL_DIR / "skills" / "gui-report" / "scripts")
        if tracker_scripts not in sys.path:
            sys.path.insert(0, tracker_scripts)
        from tracker import auto_report
        return auto_report()
    except Exception:
        return ""

# Session tracker — logs every action for final report
SESSION_LOG = SKILL_DIR / "memory" / ".session_log.json"


def _load_session_log():
    """Load session log from disk."""
    import json
    if SESSION_LOG.exists():
        try:
            with open(SESSION_LOG) as f:
                return json.load(f)
        except:
            pass
    return {"baseline_tokens": None, "actions": []}


def _save_session_log(log):
    """Save session log to disk."""
    import json
    SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION_LOG, "w") as f:
        json.dump(log, f)


def _log_action(action_name, elapsed, success, app=None):
    """Append action to session log."""
    log = _load_session_log()
    log["actions"].append({
        "action": action_name,
        "app": app,
        "elapsed": round(elapsed, 1),
        "success": success,
        "time": time.strftime("%H:%M:%S"),
    })
    _save_session_log(log)


def action_baseline(tokens=None):
    """Record baseline token count at start of GUI task."""
    log = _load_session_log()
    if tokens:
        log["baseline_tokens"] = int(tokens)
    else:
        log["baseline_tokens"] = None
    log["actions"] = []  # reset actions for new task
    _save_session_log(log)
    if tokens:
        print(f"  📊 Baseline set: {int(tokens)//1000}k tokens")
    else:
        print(f"  📊 Baseline set (no token count)")
    return True


def _print_session_tally():
    """Print a one-line cumulative session summary after every action."""
    log = _load_session_log()
    actions = log.get("actions", [])
    if not actions:
        return

    total_time = sum(a["elapsed"] for a in actions)
    counts = {}
    for a in actions:
        counts[a["action"]] = counts.get(a["action"], 0) + 1

    parts = []
    for name, label in [("learn", "learn"), ("learn_site", "learn_site"),
                         ("read_screen", "screenshot"), ("click", "click"),
                         ("navigate", "nav"), ("key", "key"), ("type", "type"),
                         ("open", "open"), ("wait_for", "wait")]:
        if counts.get(name):
            parts.append(f"{counts[name]}×{label}")

    if total_time < 60:
        t = f"{total_time:.0f}s"
    else:
        t = f"{total_time/60:.1f}min"

    print(f"📊 Session: {len(actions)} actions, {t} total | {', '.join(parts)}")


def action_report(tokens=None):
    """Print session summary with optional token delta, then clear the log."""
    log = _load_session_log()
    actions = log.get("actions", [])

    if not actions:
        print("  📊 No actions logged this session.")
        return True

    total_time = sum(a["elapsed"] for a in actions)
    counts = {}
    for a in actions:
        counts[a["action"]] = counts.get(a["action"], 0) + 1

    parts = []
    for name, label in [("learn", "learn"), ("learn_site", "learn_site"),
                         ("read_screen", "screenshot"), ("click", "click"),
                         ("navigate", "nav"), ("key", "key"), ("type", "type"),
                         ("open", "open"), ("wait_for", "wait")]:
        if counts.get(name):
            parts.append(f"{counts[name]} {label}")

    if total_time < 60:
        time_str = f"{total_time:.1f}s"
    else:
        time_str = f"{total_time/60:.1f}min"

    # Token delta
    token_str = ""
    baseline = log.get("baseline_tokens")
    if tokens and baseline:
        current = int(tokens)
        delta = current - baseline
        token_str = f" | 📊 +{delta//1000}k tokens ({baseline//1000}k→{current//1000}k)"
    elif tokens:
        token_str = f" | 📊 {int(tokens)//1000}k tokens (no baseline)"

    print(f"\n📊 Session Report")
    print(f"⏱ {time_str}{token_str} | 🔧 {', '.join(parts) or 'no actions'}")
    print(f"Actions: {len(actions)} total")
    for a in actions:
        status = "✅" if a["success"] else "❌"
        app_str = f" ({a['app']})" if a.get("app") else ""
        print(f"  {a['time']} {status} {a['action']}{app_str} — {a['elapsed']}s")

    # Clear log
    SESSION_LOG.unlink(missing_ok=True)
    return True


def get_retina_scale():
    """DEPRECATED: use ui_detector.detect_to_click() / click_to_detect() instead.

    Returns an approximate integer scale factor for backwards compatibility.
    New code should use the dual-space coordinate system in ui_detector.py.
    """
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from ui_detector import get_screen_info
        info = get_screen_info()
        if info["scale_x"] != 1.0:
            return max(1, round(info["scale_x"]))
    except Exception:
        pass
    # Fallback: probe OS
    import platform as _plat
    if _plat.system() == "Darwin":
        try:
            r = subprocess.run(
                ["swift", "-e", 'import AppKit; print(NSScreen.main!.backingScaleFactor)'],
                capture_output=True, text=True, timeout=10
            )
            return max(1, round(float(r.stdout.strip())))
        except Exception:
            return 2
    return 1


# DEPRECATED: use ui_detector.detect_to_click() / click_to_detect() instead.
RETINA_SCALE = get_retina_scale()

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


def get_known_states(app_name):
    """Get list of learned states for an app."""
    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    profile_path = app_dir / "profile.json"
    if not profile_path.exists():
        return []
    with open(profile_path) as f:
        profile = json.load(f)
    return list(profile.get("states", {}).keys())


def eval_app(app_name, workflow=None, required_components=None):
    """Smart check: decide if memory is sufficient.

    Decision logic based on STATE:
    1. App never learned → full learn (creates "initial" state)
    2. App learned → check if memory is fresh
       - Has states? → memory good
       - No states or empty? → re-learn
    3. Required components missing? → re-learn

    Args:
        app_name: App name
        workflow: Optional workflow name (kept for compatibility, not used for state logic)
        required_components: Specific components needed for this task.

    Returns:
        (ready, match_info)
    """
    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    profile_path = app_dir / "profile.json"

    # Case 1: App never learned → learn (creates initial state)
    if not profile_path.exists():
        print(f"  🧠 No memory for {app_name}, learning...")
        out, code = run_script("app_memory.py", ["learn", "--app", app_name], timeout=30)
        print(out)
        return code == 0, {"action": "learn"}

    with open(profile_path) as f:
        profile = json.load(f)

    # Case 2: Check if we have components and states
    total_components = len(profile.get("components", {}))
    total_states = len(profile.get("states", {}))
    
    if total_components == 0 or total_states == 0:
        print(f"  🧠 Empty memory for {app_name} (components: {total_components}, states: {total_states}), learning...")
        out, code = run_script("app_memory.py", ["learn", "--app", app_name], timeout=30)
        print(out)
        return code == 0, {"action": "learn"}

    # Case 3: Check if required components exist
    missing_required = []
    if required_components:
        for comp in required_components:
            if comp not in profile["components"]:
                missing_required.append(comp)

    if missing_required:
        print(f"  🔄 Missing components: {missing_required}, re-learning...")
        activate_app(app_name)
        out, code = run_script("app_memory.py", ["learn", "--app", app_name], timeout=30)
        print(out)
        return code == 0, {"action": "learn", "missing": missing_required}

    print(f"  ✅ Memory ready: {total_components} components, {total_states} states")

    # Case 4: Browser → also check per-site memory
    if app_name in BROWSER_APPS:
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from app_memory import get_current_url, get_domain_from_url, get_site_dir
            url = get_current_url(app_name)
            domain = get_domain_from_url(url)
            if domain:
                site_dir = get_site_dir(app_name, domain)
                site_profile = site_dir / "profile.json"
                if not site_profile.exists():
                    print(f"  🌐 No site memory for {domain}, learning site...")
                    out, code = run_script("app_memory.py", ["learn_site", "--app", app_name], timeout=30)
                    print(out)
                else:
                    with open(site_profile) as f:
                        site_data = json.load(f)
                    site_comps = len(site_data.get("components", {}))
                    print(f"  🌐 Site memory for {domain}: {site_comps} components")
        except Exception as e:
            print(f"  ⚠️ Could not check site memory: {e}")

    return True, {"action": "skip", "components": total_components, "states": total_states}


def ensure_app_ready(app_name, workflow=None, required_components=None):
    """Ensure app is ready.

    State-based approach:
    - App not learned → full learn (creates initial state + components)
    - App learned → check memory freshness
    - Missing components → re-learn
    """
    ready, info = eval_app(app_name, workflow, required_components)
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
    from platform_input import activate_app as pi_activate
    pi_activate(app_name)


def get_window_bounds(app_name):
    """Get the MAIN window position and size (largest window)."""
    from platform_input import get_window_bounds as pi_get_bounds
    return pi_get_bounds(app_name)


# ═══════════════════════════════════════════
# MANDATORY: Observe → Verify → Act → Confirm
# These functions enforce the Operation Protocol
# ═══════════════════════════════════════════

def observe_state(app_name, include_gpa=False):
    """STEP 0: Observe current state before any action.

    MANDATORY. Never skip this.

    Args:
        app_name: target app
        include_gpa: if True, also run GPA-GUI-Detector icon detection (slower but finds buttons)
                     Default False for speed. Set True when OCR can't find target.

    Returns: {frontmost, window, visible_text, all_elements, icon_count, ...}
    """
    state = {}

    # 1. What app is in front?
    from platform_input import get_frontmost_app
    state["frontmost"] = get_frontmost_app()

    # 2. Activate target app
    activate_app(app_name)
    state["target_activated"] = True

    # 3. Get window bounds
    bounds = get_window_bounds(app_name)
    state["window"] = bounds  # (x, y, w, h) or None

    # 4. Screenshot (retina) → OCR on original retina image → coords ÷2 = logical
    #    IMPORTANT: Do NOT resize before OCR. Resized images give wrong coordinates.
    #    Use ui_detector.detect_text() which handles retina coords correctly.
    subprocess.run(["/usr/sbin/screencapture", "-x", "/tmp/_observe.png"],
                   capture_output=True, timeout=5)
    # Also save resized version for explore/display
    subprocess.run(["sips", "-z", "982", "1512", "/tmp/_observe.png",
                    "--out", "/tmp/_observe_s.png"],
                   capture_output=True, timeout=5)

    # 5. Detection: OCR + GPA-GUI-Detector (both on original retina, auto-convert to logical)
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import ui_detector

        # OCR: text elements
        raw_text = ui_detector.detect_text("/tmp/_observe.png", return_logical=True)
        all_text = []
        for t in raw_text:
            all_text.append({
                "text": t.get("label", ""),
                "cx": t.get("cx", 0),
                "cy": t.get("cy", 0),
                "x": t.get("x", 0),
                "y": t.get("y", 0),
                "w": t.get("w", 0),
                "h": t.get("h", 0),
                "type": "text",
            })

        # GPA-GUI-Detector: icon/button elements (only if requested)
        state["icon_count"] = 0
        if include_gpa:
            try:
                icon_elements, img_w, img_h = ui_detector.detect_icons(
                    "/tmp/_observe.png", conf=0.2, iou=0.3)
                from ui_detector import detect_to_click
                for el in icon_elements:
                    cx, cy = detect_to_click(el.get("cx", 0), el.get("cy", 0))
                    x, y = detect_to_click(el.get("x", 0), el.get("y", 0))
                    w, h = detect_to_click(el.get("w", 0), el.get("h", 0))
                    all_text.append({
                        "text": "",
                        "cx": cx, "cy": cy,
                        "x": x, "y": y,
                        "w": w, "h": h,
                        "type": "icon",
                        "confidence": el.get("confidence", 0),
                    })
                state["icon_count"] = len(icon_elements)
            except:
                pass

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
            from ui_detector import click_to_detect
            img = cv2.imread("/tmp/_observe.png")
            if img is not None:
                wx, wy, ww, wh = bounds
                # Convert click-space bounds to detection-space for cropping
                dx, dy = click_to_detect(wx, wy)
                dw, dh = click_to_detect(ww, wh)
                crop = img[dy:dy+dh, dx:dx+dw]
                cv2.imwrite("/tmp/_observe_window.jpg", crop,
                           [cv2.IMWRITE_JPEG_QUALITY, 60])
                state["window_screenshot"] = "/tmp/_observe_window.jpg"
        except:
            pass
    
    # 7. Identify current state (click-graph matching)
    try:
        from app_memory import identify_state
        current_state, match_ratio = identify_state(app_name, state.get("visible_text", []))
        if current_state:
            state["current_state"] = current_state
            state["state_match_ratio"] = match_ratio
    except:
        pass
    
    return state


# ═══════════════════════════════════════════
# Workflow Recording — save steps for reuse
# ═══════════════════════════════════════════

def save_workflow(app_name, workflow_name, target_state, description=None, notes=None):
    """Save a workflow as a named task with a target state.

    A workflow is NOT a linear step list. It's a target state in the app's
    state graph. Execution uses find_path() to navigate from any current state.

    Workflows are stored in workflows.json (one file per app, not scattered files).

    Args:
        app_name: App name
        workflow_name: e.g., "open_宋文涛_chat", "go_to_contacts"
        target_state: e.g., "click:宋文涛" — the state to reach
        description: one-line summary for intent matching (max 30 words)
        notes: lessons learned
    """
    from app_memory import load_workflows, save_workflows

    if description and len(description.split()) > 30:
        description = " ".join(description.split()[:30])

    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    app_dir.mkdir(parents=True, exist_ok=True)

    workflows = load_workflows(app_dir)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    existing = workflows.get(workflow_name, {})
    workflows[workflow_name] = {
        "target_state": target_state,
        "description": description or workflow_name.replace("_", " "),
        "notes": notes or existing.get("notes", []),
        "created_at": existing.get("created_at", now),
        "last_run": now,
        "run_count": existing.get("run_count", 0),
        "success_count": existing.get("success_count", 0),
    }

    save_workflows(app_dir, workflows)
    print(f"  💾 Workflow '{workflow_name}' saved → target: {target_state}")
    update_app_summary(app_name)


def execute_workflow(app_name, target_state, domain=None, img_path=None):
    """Execute workflow with tiered verification.

    1. Identify current state (Level 1: detect_all)
    2. find_path to target
    3. For each step:
       a. Execute click (via click_component or click_at)
       b. Level 0: quick_template_check target state's defining_components
          - matched_ratio > 0.7 → confirmed, next step
       c. Level 1: detect_all + identify_current_state
          - matches expected → continue
          - matches different known state → re-route
       d. Level 2: return fallback for LLM

    Args:
        app_name: app name
        target_state: target state ID (s_xxxxx)
        domain: website domain (browser)
        img_path: current screenshot (remote VM; None = auto capture)

    Returns:
        ("success", state_id)
        ("fallback", current_state_id, step_index, reason)
        ("error", message)
    """
    import cv2
    from app_memory import (
        find_path, identify_current_state, quick_template_check,
        click_component, get_app_dir, get_site_dir,
        load_components, load_states, load_transitions,
        load_workflows, save_workflows,
    )

    app_name = resolve_app_name(app_name)

    # Resolve app/site directory
    if domain:
        app_dir = get_site_dir(app_name, domain)
    else:
        app_dir = get_app_dir(app_name)

    states = load_states(app_dir)
    components_data = load_components(app_dir)

    if target_state not in states:
        return ("error", f"Target state '{target_state}' not found in states.json")

    # --- Step 1: Identify current state (Level 1 — full detect_all) ---
    activate_app(app_name)
    time.sleep(0.5)

    sys.path.insert(0, str(SCRIPT_DIR))
    import ui_detector

    # Take screenshot (or use provided)
    if img_path:
        screen_img = cv2.imread(str(img_path))
    else:
        import platform
        if platform.system() == "Darwin":
            screen_path = "/tmp/gui_agent_wf_screen.png"
            subprocess.run(["screencapture", "-x", screen_path],
                           capture_output=True, timeout=5)
            screen_img = cv2.imread(screen_path)
            img_path = screen_path
        else:
            return ("error", "No screenshot provided (non-Mac, pass img_path)")

    if screen_img is None:
        return ("error", "Could not load screenshot")

    # Full detection for initial state identification
    try:
        icon_els, text_els, all_els, det_w, det_h = ui_detector.detect_all(str(img_path))
    except Exception as e:
        return ("error", f"detect_all failed: {e}")

    # Match all components against screenshot
    detected_names = set()
    gray_img = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
    for comp_name, comp_data in components_data.items():
        if not comp_data.get("icon_file"):
            continue
        tpl_path = Path(app_dir) / comp_data["icon_file"]
        if not tpl_path.exists():
            continue
        template = cv2.imread(str(tpl_path))
        if template is None:
            continue
        gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        if (gray_tpl.shape[0] > gray_img.shape[0] or
                gray_tpl.shape[1] > gray_img.shape[1]):
            continue
        try:
            result = cv2.matchTemplate(gray_img, gray_tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= 0.8:
                detected_names.add(comp_name)
        except Exception:
            continue

    current_state_id, jaccard = identify_current_state(states, detected_names, components_data)
    print(f"  📍 Current state: {current_state_id} (jaccard={jaccard:.2f}, {len(detected_names)} components matched)")

    # Already at target?
    if current_state_id == target_state:
        print(f"  ✅ Already at target state '{target_state}'")
        return ("success", target_state)

    if current_state_id is None:
        return ("fallback", None, -1, f"Cannot identify current state ({len(detected_names)} components detected)")

    # --- Step 2: Find path ---
    path = find_path(app_name, current_state_id, target_state)
    if path is None:
        return ("error", f"No path from '{current_state_id}' to '{target_state}'")
    if not path:
        return ("success", target_state)

    print(f"  🗺️ Path: {current_state_id} → {' → '.join(s for _, s in path)}")
    print(f"  📍 {len(path)} steps needed")

    # Get target state's defining components for Level 0 checks
    target_defining = states[target_state].get("defining_components", [])

    # --- Step 3: Execute each step ---
    for i, (action, expected_next_state) in enumerate(path):
        # Extract click component from action string "click:component_name"
        if action.startswith("click:"):
            click_target = action[len("click:"):]
        else:
            click_target = action

        print(f"  [{i+1}/{len(path)}] {action} → {expected_next_state}")

        # Execute click
        ok, msg = click_component(app_name, click_target)
        if not ok:
            # Try click_at via match if click_component fails
            return ("fallback", current_state_id, i, f"Click failed: {msg}")

        time.sleep(0.5)

        # --- Level 0: Quick template check (target state's defining components) ---
        if target_defining:
            # Take fresh screenshot
            if img_path and not (platform.system() == "Darwin"):
                # Remote VM: caller must provide new screenshot
                # For now, skip Level 0 on remote
                pass
            else:
                screen_path_l0 = "/tmp/gui_agent_wf_l0.png"
                subprocess.run(["screencapture", "-x", screen_path_l0],
                               capture_output=True, timeout=5)
                l0_img = cv2.imread(screen_path_l0)

                if l0_img is not None:
                    matched, total, ratio = quick_template_check(
                        app_dir, target_defining, img=l0_img)
                    # quick_template_check auto-ticks workflow_level0
                    if ratio > 0.7:
                        print(f"  ✅ Level 0: Target state confirmed ({len(matched)}/{total} = {ratio:.0%})")
                        _tick("workflow_auto_steps")
                        summary = _auto_report()
                        if summary:
                            print(f"\n{summary}")
                        return ("success", target_state)

        # --- Level 1: Full detect_all + identify_current_state ---
        if not (platform.system() == "Darwin"):
            # Remote VM: can't auto-screenshot, fallback
            return ("fallback", current_state_id, i, "Remote VM: need new screenshot for verification")

        screen_path_l1 = "/tmp/gui_agent_wf_l1.png"
        subprocess.run(["screencapture", "-x", screen_path_l1],
                       capture_output=True, timeout=5)
        l1_img = cv2.imread(screen_path_l1)

        if l1_img is None:
            return ("fallback", current_state_id, i, "Could not capture screenshot for Level 1")

        # Re-detect components
        l1_detected = set()
        gray_l1 = cv2.cvtColor(l1_img, cv2.COLOR_BGR2GRAY)
        for comp_name, comp_data in components_data.items():
            if not comp_data.get("icon_file"):
                continue
            tpl_path = Path(app_dir) / comp_data["icon_file"]
            if not tpl_path.exists():
                continue
            template = cv2.imread(str(tpl_path))
            if template is None:
                continue
            gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            if (gray_tpl.shape[0] > gray_l1.shape[0] or
                    gray_tpl.shape[1] > gray_l1.shape[1]):
                continue
            try:
                result = cv2.matchTemplate(gray_l1, gray_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                if max_val >= 0.8:
                    l1_detected.add(comp_name)
            except Exception:
                continue

        new_state_id, new_jaccard = identify_current_state(states, l1_detected, components_data)
        _tick("workflow_level1")

        if new_state_id == expected_next_state:
            print(f"  ✅ Level 1: Reached expected state '{expected_next_state}' (jaccard={new_jaccard:.2f})")
            _tick("workflow_auto_steps")
            current_state_id = new_state_id
            continue
        elif new_state_id == target_state:
            print(f"  ✅ Level 1: Already at target '{target_state}' (jaccard={new_jaccard:.2f})")
            _tick("workflow_auto_steps")
            summary = _auto_report()
            if summary:
                print(f"\n{summary}")
            return ("success", target_state)
        elif new_state_id and new_state_id != current_state_id:
            # Landed on a different known state — try to re-route
            print(f"  🔀 Level 1: Landed on '{new_state_id}' instead of '{expected_next_state}', re-routing...")
            reroute_path = find_path(app_name, new_state_id, target_state)
            if reroute_path is not None:
                # Recursively execute from new state (but use iteration to avoid deep recursion)
                current_state_id = new_state_id
                # Replace remaining path with reroute
                path = path[:i+1] + reroute_path
                print(f"  🗺️ New path: {' → '.join(s for _, s in reroute_path)}")
                continue
            else:
                return ("fallback", new_state_id, i, f"Re-route failed: no path from '{new_state_id}' to '{target_state}'")
        else:
            # --- Level 2: Unknown state, return for LLM ---
            _tick("workflow_level2")
            _tick("workflow_explore_steps")
            return ("fallback", new_state_id, i,
                    f"Unknown state after step {i+1} (detected {len(l1_detected)} components, jaccard={new_jaccard:.2f})")

    # If we've gone through all steps but haven't confirmed target
    # Do a final Level 0 check
    if target_defining:
        screen_path_final = "/tmp/gui_agent_wf_final.png"
        subprocess.run(["screencapture", "-x", screen_path_final],
                       capture_output=True, timeout=5)
        final_img = cv2.imread(screen_path_final)
        if final_img is not None:
            matched, total, ratio = quick_template_check(app_dir, target_defining, img=final_img)
            # quick_template_check auto-ticks workflow_level0
            if ratio > 0.7:
                print(f"  ✅ Final check: Target state confirmed ({len(matched)}/{total} = {ratio:.0%})")
                summary = _auto_report()
                if summary:
                    print(f"\n{summary}")
                return ("success", target_state)

    _tick("workflow_explore_steps")
    return ("fallback", current_state_id, len(path) - 1,
            f"Completed all steps but could not confirm target state '{target_state}'")


def run_workflow(app_name, workflow_name):
    """Run a saved workflow by name.

    Loads the workflow from workflows.json, then delegates to execute_workflow.

    Returns: (success, message)
    """
    from app_memory import load_workflows, save_workflows, get_app_dir

    app_name = resolve_app_name(app_name)
    app_dir = get_app_dir(app_name)

    # Try workflows.json first (new format)
    workflows = load_workflows(app_dir)
    wf = workflows.get(workflow_name)

    # Fall back to old scattered file format
    if not wf:
        old_path = app_dir / "workflows" / f"{workflow_name}.json"
        if old_path.exists():
            wf = json.load(open(old_path))

    if not wf:
        return False, f"Workflow '{workflow_name}' not found"

    target = wf.get("target_state")
    if not target:
        return False, f"Workflow '{workflow_name}' has no target_state"

    result = execute_workflow(app_name, target)

    # Update run stats
    if workflow_name in workflows:
        workflows[workflow_name]["run_count"] = workflows[workflow_name].get("run_count", 0) + 1
        workflows[workflow_name]["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if result[0] == "success":
            workflows[workflow_name]["success_count"] = workflows[workflow_name].get("success_count", 0) + 1
        save_workflows(app_dir, workflows)

    if result[0] == "success":
        return True, f"Reached '{target}' ✅"
    elif result[0] == "fallback":
        return False, f"Fallback at step {result[2]}: {result[3]}"
    else:
        return False, f"Error: {result[1]}"


def list_all_workflows():
    """List all workflows across all apps. Returns compact summary."""
    from app_memory import load_workflows as _load_wf
    results = []

    if MEMORY_DIR.exists():
        for app_dir in sorted(MEMORY_DIR.iterdir()):
            if not app_dir.is_dir():
                continue
            app_name = app_dir.name

            # New format: workflows.json
            wf_data = _load_wf(app_dir)
            for name, wf in wf_data.items():
                results.append({
                    "app": app_name,
                    "name": name,
                    "description": wf.get("description", ""),
                    "target_state": wf.get("target_state", ""),
                })

            # Old format: workflows/*.json
            old_dir = app_dir / "workflows"
            if old_dir.exists():
                for f in sorted(old_dir.glob("*.json")):
                    if f.stem not in wf_data:
                        with open(f) as fh:
                            wf = json.load(fh)
                        results.append({
                            "app": wf.get("app", app_name),
                            "name": wf.get("workflow", f.stem),
                            "description": wf.get("description", ""),
                            "target_state": wf.get("target_state", ""),
                        })

    return results


def _show_all_workflows():
    """Print all workflows across all apps."""
    results = list_all_workflows()
    if not results:
        print("No workflows found")
        return
    
    current_app = None
    for wf in results:
        if wf["app"] != current_app:
            current_app = wf["app"]
            print(f"\n{current_app}:")
        print(f"  {wf['name']} — {wf['description']} ({wf['steps']} steps)")


def _show_transitions(app_name):
    """Show state transition graph for an app."""
    app_name = resolve_app_name(app_name)
    sys.path.insert(0, str(SCRIPT_DIR))
    from app_memory import get_transitions
    transitions = get_transitions(app_name)
    if not transitions:
        print(f"No transitions recorded for {app_name}.")
        print("Click through the app to build the state graph.")
        return
    print(f"State graph for {app_name} ({len(transitions)} edges):")
    for t in transitions:
        print(f"  {t['from']} --{t['click']}--> {t['to']} (×{t.get('count', 1)})")


def _show_workflows(app_name, workflow_name=""):
    """List workflows (name + description) or show a specific workflow's full steps."""
    if workflow_name:
        wf = load_workflow(app_name, workflow_name)
        if wf:
            print(json.dumps(wf, indent=2, ensure_ascii=False))
        else:
            print(f"Workflow '{workflow_name}' not found for {app_name}")
        return

    from app_memory import load_workflows as _load_wf, get_app_dir
    app_dir = get_app_dir(app_name)

    # New format: workflows.json
    workflows_data = _load_wf(app_dir)
    workflows = []
    for name, wf in workflows_data.items():
        workflows.append({
            "name": name,
            "description": wf.get("description", ""),
            "target_state": wf.get("target_state", ""),
            "last_run": wf.get("last_run", ""),
            "run_count": wf.get("run_count", 0),
            "success_count": wf.get("success_count", 0),
        })

    # Also check old format: workflows/*.json
    old_dir = app_dir / "workflows"
    if old_dir.exists():
        for f in sorted(old_dir.glob("*.json")):
            if f.stem not in workflows_data:
                with open(f) as fh:
                    wf = json.load(fh)
                workflows.append({
                    "name": wf.get("workflow", f.stem),
                    "description": wf.get("description", ""),
                    "target_state": wf.get("target_state", ""),
                    "last_run": wf.get("last_run", ""),
                    "run_count": 0,
                    "success_count": 0,
                })

    if not workflows:
        print(f"No workflows for {app_name}")
        return

    print(f"Workflows for {app_name}:")
    for wf in workflows:
        stats = f"runs={wf['run_count']}, success={wf['success_count']}" if wf['run_count'] else "never run"
        print(f"  {wf['name']} — {wf['description']} → {wf['target_state']} ({stats})")


def load_workflow(app_name, workflow_name):
    """Load a saved workflow. Returns None if not found.

    Checks workflows.json first, then falls back to old scattered file format.
    """
    from app_memory import load_workflows, get_app_dir
    app_dir = get_app_dir(app_name)

    # New format: workflows.json
    workflows = load_workflows(app_dir)
    if workflow_name in workflows:
        wf = workflows[workflow_name].copy()
        wf["workflow"] = workflow_name
        wf["app"] = app_name
        return wf

    # Old format: workflows/<name>.json
    old_path = app_dir / "workflows" / f"{workflow_name}.json"
    if old_path.exists():
        with open(old_path) as f:
            return json.load(f)
    return None


def update_app_summary(app_name):
    """Update the app-level summary — overview of all known states, workflows and components.

    This summary acts as a skill reference: any agent reading it knows
    what the app can do and how to operate it.
    """
    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    app_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "app": app_name,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workflows": {},
        "component_count": 0,
        "states": [],
    }

    # Load profile for components/states
    profile_path = app_dir / "profile.json"
    if profile_path.exists():
        with open(profile_path) as f:
            profile = json.load(f)
        summary["component_count"] = len(profile.get("components", {}))
        summary["states"] = list(profile.get("states", {}).keys())

    # Load all workflows
    workflows_dir = app_dir / "workflows"
    if workflows_dir.exists():
        for wf_file in workflows_dir.glob("*.json"):
            with open(wf_file) as f:
                wf = json.load(f)
            summary["workflows"][wf_file.stem] = {
                "steps_count": len(wf.get("steps", [])),
                "notes": wf.get("notes", []),
                "last_run": wf.get("last_run"),
            }

    with open(app_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


def explore(app_name, question=None):
    """Screenshot the target app window for the agent (me) to analyze.

    The agent calling this script IS the LLM — it uses its own image tool
    to look at the screenshot. No external API calls needed.

    Saves cropped window screenshot to a known path.
    Returns: state dict with screenshot_path for the agent to view.
    """
    state = observe_state(app_name)
    screenshot_path = state.get("window_screenshot", "/tmp/_observe_s.png")

    # Save to per-app pages directory
    import shutil
    app_slug = app_name.lower().replace(" ", "_")
    pages_dir = SKILL_DIR / "memory" / "apps" / app_slug / "pages"
    os.makedirs(str(pages_dir), exist_ok=True)
    output = str(pages_dir / "explore.jpg")
    shutil.copy(screenshot_path, output)

    state["screenshot_path"] = output
    state["question"] = question or "What is the current state? What should I do next?"

    print(f"  🔍 EXPLORE: screenshot saved to {output}", flush=True)
    print(f"  📋 OCR: {state.get('visible_text', [])[:5]}", flush=True)
    print(f"  ❓ {state['question']}", flush=True)

    return state


def find_element_in_window(element_text, state, exact=False, position="any",
                           element_type=None, min_rel_y=None):
    """Find an element in the target window.

    Args:
        element_text: text to search for. Use "" to find icons by position.
        state: from observe_state()
        exact: if True, match exact text only (not substring).
        position: "any", "bottom", "top", "left", "right"
        element_type: "text", "icon", or None for both
        min_rel_y: minimum relative y position (0.0-1.0). Use to skip toolbar/search area.

    Returns: list of matching elements [{text, cx, cy, type}, ...]
    """
    bounds = state.get("window")
    results = []

    for el in state.get("all_elements", []):
        text = el.get("text", "")
        cx, cy = el.get("cx", 0), el.get("cy", 0)

        # Type filter
        if element_type and el.get("type") != element_type:
            continue

        # Text matching (skip for icon-only search)
        if element_text:
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

            # min_rel_y filter (skip toolbar/search area)
            if min_rel_y is not None and rel_y < min_rel_y:
                continue
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


def wait_for_component(app_name, component, timeout=120, interval=10):
    """Wait for a component to appear on screen using template matching.
    
    Polls every `interval` seconds using template match (fast, ~0.3s).
    If component appears, returns (True, x, y).
    If timeout, saves a screenshot for the agent to inspect and returns (False, 0, 0).
    
    Args:
        app_name: App name
        component: Component name (must exist in app memory)
        timeout: Max wait time in seconds (default 120)
        interval: Poll interval in seconds (default 10)
    """
    from app_memory import get_app_dir
    
    comp_img = get_app_dir(app_name) / "components" / f"{component}.png"
    if not comp_img.exists():
        print(f"❌ Component '{component}' not found in memory", flush=True)
        return False, 0, 0
    
    print(f"⏳ Waiting for '{component}' (timeout={timeout}s, poll={interval}s)...", flush=True)
    
    import cv2
    template = cv2.imread(str(comp_img))
    if template is None:
        print(f"❌ Could not load template image: {comp_img}", flush=True)
        return False, 0, 0
    
    from ui_detector import detect_to_click
    gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    
    start = time.time()
    attempt = 0
    while time.time() - start < timeout:
        attempt += 1
        
        # Screenshot
        subprocess.run(["/usr/sbin/screencapture", "-x", "/tmp/_wait_screen.png"],
                      capture_output=True, timeout=5)
        screenshot = cv2.imread("/tmp/_wait_screen.png")
        if screenshot is None:
            time.sleep(interval)
            continue
        
        gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # Template match
        if (gray_template.shape[0] <= gray_screen.shape[0] and
            gray_template.shape[1] <= gray_screen.shape[1]):
            result = cv2.matchTemplate(gray_screen, gray_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= 0.85:
                # Convert detection-space pixels to click space
                cx, cy = detect_to_click(
                    max_loc[0] + gray_template.shape[1] // 2,
                    max_loc[1] + gray_template.shape[0] // 2)
                elapsed = time.time() - start
                print(f"✅ Found '{component}' at ({int(cx)},{int(cy)}) conf={max_val:.2f} after {elapsed:.1f}s ({attempt} polls)", flush=True)
                return True, int(cx), int(cy)
        
        elapsed = time.time() - start
        print(f"  ... not found ({elapsed:.0f}s/{timeout}s, conf={max_val:.2f})", flush=True)
        time.sleep(interval)
    
    # Timeout — save screenshot for agent inspection
    elapsed = time.time() - start
    app_slug = app_name.lower().replace(" ", "_")
    pages_dir = SKILL_DIR / "memory" / "apps" / app_slug / "pages"
    os.makedirs(str(pages_dir), exist_ok=True)
    timeout_img = str(pages_dir / "wait_timeout.jpg")
    import shutil
    shutil.copy("/tmp/_wait_screen.png", timeout_img)
    print(f"❌ Timeout after {elapsed:.1f}s ({attempt} polls). Screenshot saved: {timeout_img}", flush=True)
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

    from platform_input import click_at; click_at(cx, cy)

    # POST-CLICK: verify state changed
    time.sleep(0.5)
    new_state = observe_state(app_name)
    old_texts = set(state.get("visible_text", []))
    new_texts = set(new_state.get("visible_text", []))
    changed = old_texts != new_texts
    if not changed:
        print(f"  ⚠ POST-CLICK: screen did not change after clicking '{element_text}' at ({cx},{cy})", flush=True)
        # Save screenshot to per-app pages directory
        ss = new_state.get("window_screenshot", "/tmp/_observe_s.png")
        import shutil
        app_slug = app_name.lower().replace(" ", "_")
        pages_dir = SKILL_DIR / "memory" / "apps" / app_slug / "pages"
        os.makedirs(str(pages_dir), exist_ok=True)
        output = str(pages_dir / "post_click.jpg")
        shutil.copy(ss, output)
        return False, f"Clicked ({cx},{cy}) but screen unchanged — check {output}"
    
    # Save new state after click
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from app_memory import save_state, load_profile, learn_app
        
        before_texts = set(state.get("visible_text", []))
        after_texts = set(new_state.get("visible_text", []))
        
        # What appeared and disappeared
        appeared = sorted(after_texts - before_texts)
        disappeared = sorted(before_texts - after_texts)
        
        if appeared or disappeared:
            print(f"  📝 State changed: +{len(appeared)} texts appeared, -{len(disappeared)} disappeared", flush=True)
            if appeared:
                print(f"     Appeared: {appeared[:5]}", flush=True)
            if disappeared:
                print(f"     Disappeared: {disappeared[:5]}", flush=True)
            
            # Save new state as "click:ElementName"
            comp_name = element_text.replace(" ", "_").replace("/", "-")[:30]
            state_name = f"click:{comp_name}"
            
            save_state(
                app_name,
                state_name,
                list(after_texts),
                trigger=element_text,
                trigger_pos=[cx, cy],
                disappeared=disappeared,
                description=f"State after clicking '{element_text}'"
            )
            print(f"  📊 Saved state '{state_name}' with {len(after_texts)} visible texts", flush=True)
            
            # Learn new components that appeared
            print(f"  📸 Learning new components...", flush=True)
            learn_app(app_name)
    except Exception as e:
        import traceback
        print(f"  ⚠ Could not save state: {e}", flush=True)
        traceback.print_exc()

    return True, f"Clicked '{element_text}' at ({cx},{cy}), state changed ✅"


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
            from platform_input import click_at; click_at(cx, cy)
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
    from platform_input import click_at
    click_at(x, y)
    return wait_for_element(app_name, next_target, max_wait=max_wait)


def action_send_message(app_name, contact, message):
    """Send a message in a chat app.

    This is a HELPER that prints guidance for the agent to follow.
    The actual sending should be done step-by-step by the agent using
    click, type, key, and screenshot verification at each step.

    New AI without workflow: follow the printed steps manually.
    With saved workflow: load and follow it.

    Returns: False (agent must execute steps manually and verify each one)
    """
    app_name = resolve_app_name(app_name)

    # Check for saved workflow first
    workflow_dir = SKILL_DIR / "memory" / "apps" / app_name.lower().replace(" ", "_") / "workflows"
    send_wf = workflow_dir / "send_message.json" if workflow_dir.exists() else None

    if send_wf and send_wf.exists():
        import json
        wf = json.load(open(send_wf))
        print(f"  📋 Found workflow: send_message")
        print(f"  📋 Steps: {json.dumps(wf.get('steps', []), indent=2, ensure_ascii=False)}")
        print(f"  ℹ️ Follow these steps. Screenshot and verify after EACH step.")
        return True

    # No workflow — print generic guidance
    print(f"""
  📨 SEND MESSAGE: {app_name} → {contact}: "{message}"

  ⚠️ No saved workflow. Follow these steps manually:

  1. SCREENSHOT full screen — confirm {app_name} is visible
  2. SEARCH for contact "{contact}" (use search bar or scroll chat list)
  3. SCREENSHOT — verify search results, find CONTACT result (not internet search)
  4. CLICK the correct contact result
  5. SCREENSHOT — verify chat header shows "{contact}"
     If wrong contact → Esc, re-search
  6. CLICK the message input field (bottom of chat area)
  7. PASTE the message: "{message}"
  8. SCREENSHOT — verify message text is in the input field
  9. PRESS Enter to send
  10. SCREENSHOT — verify message appears as sent bubble (green, right side)

  ⚠️ CRITICAL RULES:
  - Screenshot BEFORE and AFTER every click
  - If screen doesn't change after click → click failed, retry
  - If wrong app comes to front → Esc, re-activate target app
  - Never skip verification steps

  After success, save workflow:
    python3 agent.py save_workflow --app {app_name} --name send_message --steps <json>
""")
    return False


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
    """Click a named component via template matching.
    
    Uses app_memory.click_component directly (template match + auto state verification).
    No OCR fallback — template match is the primary method.
    """
    app_name = resolve_app_name(app_name)

    # Ensure memory ready (learn if needed)
    ensure_app_ready(app_name, required_components=[component])

    # Click via template match (app_memory handles everything:
    # match → click → state detection → verification → state saving)
    out, code = run_script("app_memory.py", [
        "click", "--app", app_name, "--component", component
    ], timeout=20)
    print(out)
    
    if code != 0:
        print(f"  ❌ Click failed. Component '{component}' not found or mismatch.")
    
    return code == 0


def action_open_app(app_name):
    """Open/activate an app."""
    app_name = resolve_app_name(app_name)
    activate_app(app_name)
    print(f"  ✅ Opened {app_name}")
    return True


def action_navigate_browser(url):
    """Navigate browser to URL — visually: activate, Cmd+L, paste URL, Enter."""
    from platform_input import send_keys, paste_text, set_clipboard, key_press, key_combo
    app_name = "Google Chrome"
    activate_app(app_name)
    time.sleep(0.5)

    # Cmd+L to focus address bar
    key_combo("command", "l")
    time.sleep(0.3)

    # Paste URL
    set_clipboard(url)
    time.sleep(0.1)
    key_combo("command", "v")
    time.sleep(0.3)

    # Dismiss autocomplete dropdown, re-select URL, then Enter
    key_press("esc")
    time.sleep(0.2)
    key_combo("command", "l")
    time.sleep(0.2)
    key_press("return")
    time.sleep(3)

    print(f"  🌐 Navigated to {url}")
    return True


def action_learn_app(app_name):
    """Learn an app's UI. For browsers, also learns the current site."""
    app_name = resolve_app_name(app_name)
    print(f"  🧠 Learning {app_name}...")
    out, code = run_script("app_memory.py", ["learn", "--app", app_name], timeout=30)
    print(out)

    # If browser, also learn current site
    if app_name in BROWSER_APPS:
        print(f"  🌐 Also learning current site...")
        site_out, site_code = run_script("app_memory.py", ["learn_site", "--app", app_name], timeout=30)
        print(site_out)

    return code == 0


def action_learn_site(app_name=None):
    """Learn the current website's UI in a browser (per-domain memory)."""
    app_name = resolve_app_name(app_name or "Google Chrome")
    print(f"  🌐 Learning current site in {app_name}...")
    out, code = run_script("app_memory.py", ["learn_site", "--app", app_name], timeout=30)
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


def action_key_press(key, app_name=None):
    """Press a key or key combo via pynput."""
    from platform_input import send_keys, activate_app as pi_activate
    if app_name:
        pi_activate(resolve_app_name(app_name))
        time.sleep(0.3)

    send_keys(key)
    print(f"  ⌨️ Pressed {key}")
    return True


def action_type_text(text, app_name=None):
    """Type or paste text. ASCII → type, CJK/special → paste via clipboard."""
    from platform_input import type_text as pi_type, paste_text, activate_app as pi_activate
    if app_name:
        pi_activate(resolve_app_name(app_name))
        time.sleep(0.3)

    if all(ord(c) < 128 for c in text):
        pi_type(text)
    else:
        paste_text(text)

    print(f"  ⌨️ Typed: {text[:50]}{'...' if len(text) > 50 else ''}")
    return True


def action_screenshot_and_read(app_name=None):
    """Take a full-screen screenshot. No OCR — use image tool to analyze.

    Returns the screenshot path for the agent to inspect visually.
    """
    if app_name:
        app_name = resolve_app_name(app_name)
        activate_app(app_name)
        time.sleep(0.3)

    screenshot_path = f"/tmp/gui_agent_screen.png"
    subprocess.run(["screencapture", "-x", screenshot_path], capture_output=True, timeout=5)
    print(f"  📸 Screenshot saved: {screenshot_path}")
    print(f"  ℹ️ Use image tool to analyze (OCR removed)")
    return screenshot_path


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
    "wait_for": {
        "fn": lambda app_name, component, **kw: wait_for_component(app_name, component),
        "args": ["app", "component"],
        "desc": "Wait for a component to appear (template match polling, 120s timeout, 10s interval)",
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
    "key": {
        "fn": action_key_press,
        "args": ["key"],
        "optional": ["app"],
        "desc": "Press a key or combo (e.g., return, esc, command-v, command-shift-s)",
    },
    "type": {
        "fn": action_type_text,
        "args": ["text"],
        "optional": ["app"],
        "desc": "Type or paste text (auto-detects ASCII vs CJK)",
    },
    "learn": {
        "fn": action_learn_app,
        "args": ["app"],
        "desc": "Learn an app's UI elements",
    },
    "learn_site": {
        "fn": action_learn_site,
        "optional": ["app"],
        "desc": "Learn current website's UI (per-domain memory, default: Chrome)",
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
    "run_workflow": {
        "fn": lambda app_name, workflow, **kw: run_workflow(app_name, workflow),
        "args": ["app", "workflow"],
        "desc": "Run a workflow (navigate state graph to target state)",
    },
    "transitions": {
        "fn": lambda app_name, **kw: _show_transitions(app_name),
        "args": ["app"],
        "desc": "Show state transition graph",
    },
    "workflows": {
        "fn": lambda app_name, **kw: _show_workflows(app_name, kw.get("workflow", "")),
        "args": ["app"],
        "optional": ["workflow"],
        "desc": "List or view saved workflows for an app",
    },
    "all_workflows": {
        "fn": lambda **kw: _show_all_workflows(),
        "desc": "List ALL workflows across all apps + meta-workflows",
    },
    "report": {
        "fn": action_report,
        "optional": ["tokens"],
        "desc": "Print session summary (timing, token delta) and clear log",
    },
    "baseline": {
        "fn": action_baseline,
        "optional": ["tokens"],
        "desc": "Set baseline token count for this GUI task",
    },
    "summary": {
        "fn": lambda app_name: print(json.dumps(
            json.load(open(MEMORY_DIR / app_name.lower().replace(" ", "_") / "summary.json"))
            if (MEMORY_DIR / app_name.lower().replace(" ", "_") / "summary.json").exists()
            else {"error": "No summary found"}, indent=2, ensure_ascii=False)),
        "args": ["app"],
        "desc": "Show app summary (all workflows + components overview)",
    },
    "explore": {
        "fn": lambda app_name, **kw: explore(app_name, kw.get("question")),
        "args": ["app"],
        "desc": "Screenshot + OCR + save for LLM vision analysis",
    },
    "eval": {
        "fn": lambda app_name, workflow=None: eval_app(app_name, workflow=workflow),
        "args": ["app"],
        "optional": ["workflow"],
        "desc": "Check memory freshness for a workflow, learn if needed",
    },
    "read_screen": {
        "fn": action_screenshot_and_read,
        "optional": ["app"],
        "desc": "Screenshot and OCR current screen",
    },
    "cleanup": {
        "fn": lambda app_name: _cleanup_unlabeled(app_name),
        "args": ["app"],
        "desc": "Remove unlabeled components (call after agent finishes identifying)",
    },
}


def _cleanup_unlabeled(app_name):
    """Remove unlabeled components from app memory after workflow completes."""
    app_slug = app_name.lower().replace(" ", "_")
    app_dir = SKILL_DIR / "memory" / "apps" / app_slug
    components_dir = app_dir / "components"
    profile_path = app_dir / "profile.json"

    if not components_dir.exists():
        return

    # Find and remove unlabeled image files
    removed = []
    for f in components_dir.iterdir():
        if f.name.startswith("unlabeled_") and f.suffix == ".png":
            f.unlink()
            removed.append(f.name)

    if not removed:
        return

    # Also remove from profile.json
    if profile_path.exists():
        import json
        with open(profile_path, "r") as fh:
            profile = json.load(fh)
        if "components" in profile:
            for name in removed:
                key = name.replace(".png", "")
                profile["components"].pop(key, None)
            # Also clean page component lists
            for page_info in profile.get("pages", {}).values():
                if "components" in page_info:
                    page_info["components"] = [
                        c for c in page_info["components"]
                        if not c.startswith("unlabeled_")
                    ]
            with open(profile_path, "w") as fh:
                json.dump(profile, fh, ensure_ascii=False, indent=2)

    print(f"  🧹 Cleaned {len(removed)} unlabeled components from {app_name}")


def main():
    parser = argparse.ArgumentParser(description="GUI Agent — unified desktop automation")
    parser.add_argument("action", nargs="?", help="Action name or natural language task")
    parser.add_argument("--app", help="App name")
    parser.add_argument("--contact", help="Contact name (for messaging)")
    parser.add_argument("--message", help="Message text")
    parser.add_argument("--component", help="Component name to click")
    parser.add_argument("--url", help="URL to navigate to")
    parser.add_argument("--key", help="Key or combo to press (e.g., return, command-v)")
    parser.add_argument("--text", help="Text to type or paste")
    parser.add_argument("--workflow", help="Workflow/page name (for revise logic)")
    parser.add_argument("--tokens", help="Current token count (for baseline/report)")
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
        import time as _time
        _start_time = _time.time()
        
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
        if args.key:
            kwargs["key"] = args.key
        if args.text:
            kwargs["text"] = args.text
        if args.tokens:
            kwargs["tokens"] = args.tokens
        if args.workflow:
            kwargs["workflow"] = args.workflow

        # Handle app_name vs app parameter naming
        if "app_name" in fn.__code__.co_varnames and "app" in kwargs:
            kwargs["app_name"] = kwargs.pop("app")

        result = fn(**kwargs)
        _elapsed = _time.time() - _start_time
        if _elapsed < 60:
            _time_str = f"{_elapsed:.1f}s"
        else:
            _time_str = f"{_elapsed/60:.1f}min"
        
        # Log action to session tracker
        _log_action(action_name, _elapsed, result is not False, 
                    app=kwargs.get("app_name") or kwargs.get("app"))

        if result is True:
            print(f"\n✅ Done ({_time_str})")
        elif result is False:
            print(f"\n❌ Failed ({_time_str})")
        else:
            print(f"\n⏱ Completed ({_time_str})")

        # Auto-print cumulative session stats after every action
        _print_session_tally()
    else:
        print(f"Unknown action: {action_name}")
        print(f"Available: {', '.join(ACTIONS.keys())}")
        print(f"Run with --list-actions for details")


if __name__ == "__main__":
    main()
