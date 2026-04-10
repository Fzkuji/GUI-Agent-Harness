"""
execute_task — autonomous GUI task execution with visual memory.

Design principle:
  The LLM is the decision maker — it decides WHAT to do freely.
  We only enforce HOW for things the LLM can't do well (GUI clicking).

Each step:
  1. Screenshot → identify current state → get transition hints
  2. LLM sees screenshot + context → decides what to do next
  3. If LLM wants a GUI action (click/double_click/right_click/drag):
     → Our detection pipeline locates the target (Phase 1-5)
  4. If LLM wants anything else (type, command, shortcut, etc.):
     → Execute directly, no intervention
  5. Record state transition for future hints
"""

from __future__ import annotations

import json
import sys
import time

from agentic import agentic_function

from gui_harness.utils import parse_json
from gui_harness.perception import screenshot as _screenshot
from gui_harness.action import input as _input
from gui_harness.action.general_action import general_action
from gui_harness.planning.component_memory import (
    locate_target,
    identify_state,
    record_transition,
    get_available_transitions,
)

# GUI actions that need our visual detection pipeline for coordinates
GUI_ACTIONS = {"click", "double_click", "right_click", "drag"}

# Direct actions that execute immediately without detection
DIRECT_ACTIONS = {"type", "press", "hotkey", "scroll"}

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


# ═══════════════════════════════════════════
# LLM decision function
# ═══════════════════════════════════════════

def _build_history_summary(history):
    """Build a text summary of recent action history."""
    if not history:
        return ""
    lines = []
    for h in history[-5:]:
        status = "ok" if h.get("success") else "FAIL"
        act = h.get("action", "?")
        detail = h.get("target", h.get("code", ""))
        if detail:
            detail = str(detail)[:50]
        lines.append(f"  {h['step']}. [{status}] {act}: {detail}")
        if h.get("output"):
            lines.append(f"     output: {str(h['output'])[:200]}")
    return f"\nRecent actions:\n" + "\n".join(lines)


@agentic_function(summarize={"depth": 0, "siblings": 0})
def decide_next_action(
    task: str,
    img_path: str,
    step: int,
    max_steps: int,
    history: list,
    system_context: str = "",
    runtime=None,
) -> dict:
    """Look at the screenshot and decide the next action.

    You can see the current screen. Choose one action:

    GUI actions (we locate the target for you):
      {"action": "click", "target": "description of element to click"}
      {"action": "double_click", "target": "description of element"}
      {"action": "right_click", "target": "description of element"}

    Keyboard/input actions:
      {"action": "type", "text": "text to type"}
      {"action": "press", "key": "enter"}
      {"action": "hotkey", "keys": "ctrl+s"}
      {"action": "scroll", "direction": "down"}

    General action (command-line operations on the VM, no screen needed):
      {"action": "general", "task": "description of what to do via command line"}

    Task complete:
      {"action": "done", "reasoning": "why the task is fully complete"}

    Return ONLY valid JSON.
    """
    rt = runtime or _get_runtime()

    history_summary = _build_history_summary(history)
    sys_ctx = f"\n{system_context}" if system_context else ""

    context = f"""<task>{task}</task>
<progress>Step {step}/{max_steps}</progress>{sys_ctx}{history_summary}

IMPORTANT: You are a GUI agent. Always prefer GUI actions (click, scroll, type, hotkey) over command-line operations.
- If a browser is visible with relevant content, interact with it via GUI: scroll to load content, click elements, read from the screen.
- Only use "general" (command-line) when the information CANNOT be obtained through GUI interaction (e.g., reading/writing files that are not open on screen).
- Do NOT use "general" to scrape websites or run Python scripts when the same data is visible in the browser on screen.
- Do NOT generate or paraphrase content from your own knowledge — extract data from what you see on screen or from actual files.

Look at the screenshot and decide the NEXT action. Return ONLY valid JSON."""

    reply = rt.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])

    try:
        return parse_json(reply)
    except Exception:
        reply_lower = reply.lower()
        if '"done"' in reply_lower or "task is complete" in reply_lower:
            return {"action": "done", "reasoning": reply[:200]}
        return {"action": "general", "task": reply[:200]}


# ═══════════════════════════════════════════
# Direct actions (no coordinate detection)
# ═══════════════════════════════════════════

def _execute_direct_action(action, plan):
    """Execute a direct action that doesn't need coordinate detection.

    Uses gui_harness.action.input which routes to VM when configured.
    """
    from gui_harness.action import input as _input

    if action == "type":
        text = plan.get("text", "")
        _input.type_text(text)
        return {"success": True}
    elif action == "press":
        key = plan.get("key", plan.get("target", "return"))
        _input.key_press(key)
        return {"success": True}
    elif action == "hotkey":
        keys_str = plan.get("keys", plan.get("target", ""))
        keys = [k.strip() for k in keys_str.split("+")]
        _input.key_combo(*keys)
        return {"success": True}
    elif action == "scroll":
        direction = plan.get("direction", plan.get("target", "down")).lower()
        _input.key_press("pageup" if direction == "up" else "pagedown")
        return {"success": True}
    else:
        return {"success": False, "error": f"Unknown direct action: {action}"}


# ═══════════════════════════════════════════
# GUI action execution
# ═══════════════════════════════════════════

def _execute_gui_action(action, plan, task, img_path, app_name, runtime):
    """Execute a GUI action that needs our visual detection pipeline."""
    target = plan.get("target", "")

    if action == "drag":
        target_end = plan.get("target_end", "")
        start = locate_target(task=task, target=f"Find START: {target}",
                              img_path=img_path, app_name=app_name, runtime=runtime)
        if not start:
            return {"success": False, "error": f"Start not found: {target}"}
        end = locate_target(task=task, target=f"Find END: {target_end}",
                            img_path=img_path, app_name=app_name, runtime=runtime)
        if not end:
            return {"success": False, "error": f"End not found: {target_end}"}
        _input.mouse_drag(start["cx"], start["cy"], end["cx"], end["cy"])
        return {"success": True}
    else:
        location = locate_target(task=task, target=target,
                                 img_path=img_path, app_name=app_name, runtime=runtime)
        if not location:
            return {"success": False, "error": f"Target not found: {target}"}
        cx, cy = location["cx"], location["cy"]
        if action == "click":
            _input.mouse_click(cx, cy)
        elif action == "double_click":
            _input.mouse_double_click(cx, cy)
        elif action == "right_click":
            _input.mouse_right_click(cx, cy)
        return {"success": True, "location": location}


def _check_web_access_needed(sub_task: str) -> str | None:
    """Check if a general action involves web scraping, and if so, test access.

    Returns None if no web access needed or access works.
    Returns error description string if web access is blocked.
    """
    import re
    task_lower = sub_task.lower()

    # Detect if the task involves fetching from a URL
    url_patterns = re.findall(r'https?://[^\s\'")\]]+', sub_task)
    web_keywords = ["scrape", "fetch", "requests.get", "curl", "beautifulsoup",
                    "web page", "webpage", "website", "imdb", "wikipedia"]
    needs_web = bool(url_patterns) or any(kw in task_lower for kw in web_keywords)

    if not needs_web:
        return None

    # Test if we can actually fetch the URL from the VM
    test_url = url_patterns[0] if url_patterns else None
    if not test_url:
        # Try to guess URL from keywords
        if "imdb" in task_lower and "top" in task_lower:
            test_url = "https://www.imdb.com/chart/top/"
        else:
            return None  # Can't determine URL, let it try

    try:
        import json, urllib.request
        from gui_harness.action import input as _action_input
        vm_url = getattr(_action_input, '_vm_url', None)
        if not vm_url:
            return None

        # Quick curl test on VM
        cmd = (f'curl -sL --proxy http://172.16.82.1:6152 -o /tmp/_web_test.html '
               f'-w "%{{http_code}} %{{size_download}}" '
               f'-H "User-Agent: Mozilla/5.0" '
               f'--max-time 15 "{test_url}"')
        payload = json.dumps({"command": cmd, "shell": True}).encode()
        req = urllib.request.Request(
            f"{vm_url}/execute",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=20).read())
        output = resp.get("output", "").strip()

        # Parse: "200 12345" or "202 0"
        parts = output.split()
        if len(parts) >= 2:
            status_code = int(parts[0])
            size = int(parts[1])
            if status_code == 202 or size < 1000:
                return f"HTTP {status_code}, {size} bytes — WAF/challenge blocked"

        return None  # Access seems OK
    except Exception as e:
        return None  # Can't test, let it try


def _execute_code(code, vm_url=None):
    """Execute arbitrary code/command. Routes through VM API if patched."""
    try:
        if vm_url or _is_vm_mode():
            return _execute_on_vm(code)
        else:
            import subprocess
            result = subprocess.run(
                code, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr:
                output += f"\nSTDERR: {result.stderr.strip()}"
            return {"success": result.returncode == 0, "output": output}
    except Exception as e:
        return {"success": False, "output": f"Error: {e}"}


def _is_vm_mode():
    """Check if we're in VM mode (vm_adapter patched the screenshot function)."""
    return hasattr(_screenshot, 'take') and 'vm_screenshot' in str(_screenshot.take)


def _execute_on_vm(code):
    """Execute code on the VM via HTTP API."""
    import requests
    from gui_harness.adapters import vm_adapter
    if vm_adapter._VM_URL is None:
        return {"success": False, "output": "VM not configured"}
    try:
        r = requests.post(
            f"{vm_adapter._VM_URL}/execute",
            json={"command": code, "shell": True},
            timeout=30,
        )
        data = r.json()
        output = data.get("output", "").strip()
        if data.get("error"):
            output += f"\nERROR: {data['error']}"
        return {
            "success": data.get("returncode", 1) == 0,
            "output": output[:500],
        }
    except Exception as e:
        return {"success": False, "output": f"VM exec error: {e}"}


# ═══════════════════════════════════════════
# Agent session initialization
# ═══════════════════════════════════════════

def _kill_stale_processes():
    """Kill any lingering claude stream-json processes from previous runs."""
    import subprocess as _sp
    try:
        result = _sp.run(
            ["pkill", "-f", "claude.*stream-json"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass  # Best effort
    time.sleep(0.5)


def _detect_platform() -> dict:
    """Detect the platform environment (OS, resolution, etc.).

    For remote VMs, queries the VM API. For local, uses system info.
    Returns a dict with os, resolution, desktop_environment, etc.
    """
    platform_info = {
        "os": "unknown",
        "resolution": "unknown",
        "desktop": "unknown",
    }

    # Check if we're using a VM backend
    vm_url = None
    try:
        from gui_harness.action import input as _action_input
        vm_url = getattr(_action_input, '_vm_url', None)
    except Exception:
        pass

    if vm_url:
        import urllib.request, json
        url = vm_url.rstrip("/")

        # Get VM resolution from screenshot
        try:
            from PIL import Image
            import io
            img_data = urllib.request.urlopen(f"{url}/screenshot", timeout=10).read()
            img = Image.open(io.BytesIO(img_data))
            platform_info["resolution"] = f"{img.width}x{img.height}"
        except Exception:
            pass

        # Get OS info
        try:
            payload = json.dumps({"command": "lsb_release -d -s 2>/dev/null || uname -s", "shell": True}).encode()
            req = urllib.request.Request(f"{url}/execute", data=payload,
                                        headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            os_name = resp.get("output", "").strip()
            if os_name:
                platform_info["os"] = os_name
        except Exception:
            pass

        # Get desktop environment
        try:
            payload = json.dumps({"command": "echo $XDG_CURRENT_DESKTOP; wmctrl -m 2>/dev/null | head -1", "shell": True}).encode()
            req = urllib.request.Request(f"{url}/execute", data=payload,
                                        headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
            de = resp.get("output", "").strip()
            if de:
                # Clean up: pick first meaningful line, strip "Name: " prefix
                for line in de.split("\n"):
                    line = line.strip().replace("Name: ", "")
                    if line:
                        platform_info["desktop"] = line
                        break
        except Exception:
            pass

        return platform_info

    # Local platform
    import platform as _platform
    platform_info["os"] = f"{_platform.system()} {_platform.release()}"
    return platform_info


def _build_system_context(task, app_name):
    """Build the system context string for the agent session.

    Returns a context string with VM info, platform details, and capabilities.
    This is prepended to the first decide_next_action call.
    """
    # Check if we're operating on a remote VM
    vm_url = None
    try:
        from gui_harness.action import input as _action_input
        vm_url = getattr(_action_input, '_vm_url', None)
    except Exception:
        pass

    # Detect platform
    platform = _detect_platform()

    if vm_url:
        return f"""You are a GUI automation agent operating on a REMOTE Ubuntu VM.

IMPORTANT: You are running on macOS locally, but ALL your actions target a remote Ubuntu Linux VM.
- The screenshots you see are from the VM ({platform['os']})
- All GUI actions (click, type, etc.) are executed on the VM
- All files are on the VM filesystem, NOT on your local macOS
- To run shell commands on the VM: curl -s -X POST {vm_url}/execute -H 'Content-Type: application/json' -d '{{"command": "CMD", "shell": true}}'
- Do NOT use local macOS commands (open, osascript, pbcopy, etc.)

VM: {vm_url}
OS: {platform['os']}
Resolution: {platform['resolution']}
Desktop: {platform['desktop']}
Application: {app_name}"""
    else:
        return f"""You are a GUI automation agent.
Application: {app_name}
Platform: {platform['os']}
Resolution: {platform['resolution']}
Desktop: {platform['desktop']}"""


# ═══════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════

def execute_task(task: str, runtime=None, max_steps: int = 30, app_name: str = "desktop") -> dict:
    """Execute a GUI task autonomously with experience-augmented decisions.

    The LLM freely decides what to do. GUI click operations go through
    our visual detection pipeline. Everything else executes directly.

    Args:
        task:       Natural language description of what to do.
        runtime:    GUIRuntime instance (auto-detected if None).
        max_steps:  Maximum number of actions (default: 30).
        app_name:   App name for component memory (default: "desktop").

    Returns:
        dict: task, success, steps_taken, total_time, history
    """
    rt = runtime or _get_runtime()

    # Reset runtime to ensure clean session for this task
    if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
        rt._inner.reset()
    if hasattr(rt, '_planner') and hasattr(rt._planner, 'reset'):
        rt._planner.reset()

    try:
        return _execute_task_loop(task, rt, max_steps, app_name)
    finally:
        # Always close runtime when task ends (success or error)
        if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
            rt._inner.reset()
        if hasattr(rt, '_planner') and hasattr(rt._planner, 'reset'):
            rt._planner.reset()


def _ensure_base_memory(app_name: str, rt) -> None:
    """Auto-learn app components if no base memory exists.

    Opens a separate session to learn, so the task session stays clean.
    """
    from gui_harness.planning.learn import has_base_memory, learn_app_components

    if has_base_memory(app_name):
        return

    print(f"  [learn] No base memory for '{app_name}', learning components...", file=sys.stderr)
    result = learn_app_components(app_name=app_name, runtime=rt)
    saved = result.get("components_saved", 0)
    t = result.get("timing", {})
    print(f"  [learn] Saved {saved} components "
          f"(detect={t.get('detect', '?')}s, label={t.get('label', '?')}s, save={t.get('save', '?')}s)",
          file=sys.stderr)


def _analyze_task(task: str, system_context: str, runtime) -> str:
    """Step 0: Analyze the task before execution.

    Ask the agent to think through what needs to be done, identify
    potential pitfalls, and create a rough plan. The analysis is
    passed to every subsequent step as context.
    """
    rt = runtime

    # Take a screenshot so the agent can see the current screen state
    try:
        img_path = _screenshot.take()
    except Exception:
        img_path = None

    context = f"""<task>{task}</task>

Look at the current screen and analyze this task. Then create a CONCRETE step-by-step execution plan using GUI actions.

1. What are ALL the requirements? List each one.
2. What applications are currently open on screen? They were set up for this task — you MUST use them.
3. What files/resources need to be examined or modified?
4. Create a detailed step-by-step plan using SPECIFIC GUI actions. For each step, specify the exact action type:
   - click: what to click
   - scroll: which direction, how many times
   - hotkey: which keys
   - type: what text
   - general: ONLY for file read/write operations that cannot be done via GUI

CRITICAL RULES for your plan:
- If a browser is open with relevant content, you MUST plan to read data from it via GUI (scroll to load, select text, copy, etc.)
- Do NOT plan to use command-line tools (curl, requests, wget, python scraping) to fetch data that is already visible in the browser
- "general" actions should ONLY be used for local file operations (read xlsx, write xlsx, etc.), NOT for fetching web content
- Many web pages use lazy loading — plan to scroll down multiple times to load all content

Return your analysis as plain text (not JSON). Be thorough and specific about each GUI step."""

    try:
        # Use plan() — no tools, pure text analysis, with screenshot
        content = [{"type": "text", "text": context}]
        if img_path:
            content.append({"type": "image", "path": img_path})
        analysis = rt.plan(content=content)
        if analysis and "API Error" in analysis:
            print(f"  [analysis] API error, skipping: {analysis[:100]}", file=sys.stderr)
            return ""
        return analysis.strip()
    except Exception as e:
        print(f"  [analysis] ERROR: {e}", file=sys.stderr)
        return ""


@agentic_function(summarize={"depth": 0, "siblings": 0})
def _extract_screen_data(task: str, img_path: str, existing_data: str, runtime=None) -> str:
    """Extract structured data visible on the current screen.

    Look at the screenshot carefully. Extract ALL data items visible on screen
    that are relevant to the task. Return the data in a simple structured format.

    For example, if viewing a list of movies, extract each movie's:
    - Rank/position number
    - Title
    - Year
    - Rating
    - Any other visible details

    IMPORTANT:
    - Only extract what you can ACTUALLY SEE on the screen right now
    - Do NOT make up or guess any data
    - Do NOT use your own knowledge to fill in missing information
    - If you can't read something clearly, skip it

    Return the extracted data as plain text, one item per line.
    If nothing relevant is visible, return "NO_DATA".
    """
    rt = runtime or _get_runtime()

    prompt = f"""<task>{task}</task>

Previously extracted data:
{existing_data if existing_data else "(none yet)"}

Look at the screenshot and extract ALL relevant data items visible on screen.
- Extract ONLY what you can see, do NOT generate from memory
- Use a consistent format (e.g., "1. Title (Year) - Rating")
- If this is a continuation, only extract NEW items not already in the previous data
- If nothing relevant is visible, return "NO_DATA"

Return extracted data as plain text."""

    reply = rt.exec(content=[
        {"type": "text", "text": prompt},
        {"type": "image", "path": img_path},
    ])
    return reply.strip() if reply else "NO_DATA"


def _execute_task_loop(task, rt, max_steps, app_name):
    """Internal task loop. Separated so execute_task can wrap with try-finally."""
    history = []
    completed = False
    task_start = time.time()
    extracted_data = ""  # Accumulated data extracted from screen during browsing

    # Step 0: Analyze task before execution (first exec call, clean session)
    analysis = _analyze_task(task, "", rt)
    if analysis:
        print(f"  [analysis] {analysis[:500]}", file=sys.stderr)

    # Build system context (may download screenshot for platform detection)
    system_context = _build_system_context(task, app_name)

    # Auto-learn app components
    _ensure_base_memory(app_name, rt)

    for step in range(1, max_steps + 1):
        step_start = time.time()
        timing = {}
        current_state = None

        # Take screenshot + detect components + decide next action
        print(f"  [step {step}] taking screenshot...", file=sys.stderr)
        t0 = time.time()
        img_path = _screenshot.take()
        timing["screenshot"] = round(time.time() - t0, 2)
        time.sleep(0.3)

        # Run component detection (Phase 1 + 2)
        t0 = time.time()
        from gui_harness.planning.component_memory import detect_components, match_memory_components
        detection = detect_components(img_path)
        icons = detection.get("icons", []) if isinstance(detection, dict) else []
        texts = detection.get("texts", []) if isinstance(detection, dict) else []
        matched = match_memory_components(app_name, img_path)
        timing["detect"] = round(time.time() - t0, 2)

        # Build component context for LLM
        comp_lines = []
        for c in matched[:30]:
            comp_lines.append(f"  [{c['name']}] at ({c['cx']}, {c['cy']})")
        text_lines = []
        for t in texts[:40]:
            label = t.get("label", "")
            if label and len(label) > 1:
                text_lines.append(f"  '{label}' at ({t.get('cx', 0)}, {t.get('cy', 0)})")

        component_info = ""
        if comp_lines:
            component_info += "\n<known_components>\n" + "\n".join(comp_lines) + "\n</known_components>"
        if text_lines:
            component_info += "\n<screen_text>\n" + "\n".join(text_lines) + "\n</screen_text>"

        print(f"  [step {step}] {len(matched)} components, {len(texts)} texts", file=sys.stderr)

        t0 = time.time()
        ctx = system_context if step == 1 else ""
        if analysis:
            ctx += f"\n<analysis>{analysis}</analysis>"
        if extracted_data:
            ctx += (f"\n\n<extracted_data_available>"
                    f"You have already extracted {len(extracted_data)} chars of data from the browser by scrolling. "
                    f"This data will be automatically provided to any 'general' action. "
                    f"You can now use 'general' for file operations using this extracted data."
                    f"</extracted_data_available>")
        ctx += component_info
        try:
            plan = decide_next_action(
                task=task, img_path=img_path, step=step, max_steps=max_steps,
                history=history, system_context=ctx, runtime=rt,
            )
        except Exception as e:
            print(f"  [step {step}] decide ERROR: {e.__class__.__name__}, resetting", file=sys.stderr)
            if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
                rt._inner.reset()
            if hasattr(rt, '_planner') and hasattr(rt._planner, 'reset'):
                rt._planner.reset()
            plan = {"action": "general", "task": "retry the previous step"}
        timing["decide"] = round(time.time() - t0, 2)

        action = plan.get("action", "general")
        print(f"  [step {step}] {action}", file=sys.stderr)

        # Done
        if action == "done":
            completed = True
            history.append({
                "step": step, "action": "done",
                "reasoning": plan.get("reasoning", ""),
                "success": True, "timing": timing,
                "state_before": current_state, "state_after": current_state,
            })
            break

        # Execute the action
        t0 = time.time()
        result = {}
        try:
            if action == "general":
                sub_task = plan.get("task", "")
                print(f"  [step {step}] general: {sub_task[:200]}", file=sys.stderr)

                gen_context = f"<task>{task}</task>"
                if analysis:
                    gen_context += f"\n<analysis>{analysis}</analysis>"
                if extracted_data:
                    gen_context += (
                        f"\n\n<extracted_screen_data>\n"
                        f"The following data was extracted from the browser screen by scrolling through it. "
                        f"USE THIS DATA — do NOT use your own knowledge or hardcode data.\n\n"
                        f"{extracted_data}\n"
                        f"</extracted_screen_data>"
                    )
                result = general_action(sub_task=sub_task, task_context=gen_context, runtime=rt)

                # After execution, verify: if this task involved web scraping,
                # check if the web data was actually accessible.
                # Skip check if we have extracted_data (agent is using screen-extracted data, not web scraping)
                if result.get("success") and not extracted_data:
                    web_blocked = _check_web_access_needed(sub_task)
                    if web_blocked:
                        print(f"  [step {step}] post-check: web data was not accessible ({web_blocked}), overriding to FAIL", file=sys.stderr)
                        result = {
                            "success": False,
                            "output": f"The command-line approach appeared to succeed but the web data was NOT actually accessible ({web_blocked}). "
                                      "The data written is likely fabricated from LLM knowledge, not from the real website. "
                                      "You MUST use the browser GUI (scroll down to load content, read from screen) to get real data from the website.",
                        }
            elif action in GUI_ACTIONS:
                result = _execute_gui_action(
                    action, plan, task, img_path, app_name, rt)
            elif action in DIRECT_ACTIONS:
                result = _execute_direct_action(action, plan)
            else:
                # Unknown action — treat as general
                sub_task = plan.get("task", plan.get("target", plan.get("code", "")))
                gen_context = f"<task>{task}</task>"
                if analysis:
                    gen_context += f"\n<analysis>{analysis}</analysis>"
                result = general_action(sub_task=sub_task, task_context=gen_context, runtime=rt)
        except Exception as e:
            print(f"  [step {step}] Execute ERROR: {e.__class__.__name__}", file=sys.stderr)
            if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
                rt._inner.reset()
            if hasattr(rt, '_planner') and hasattr(rt._planner, 'reset'):
                rt._planner.reset()
            result = {"success": False, "output": str(e)}
        timing["execute"] = round(time.time() - t0, 2)

        time.sleep(0.5)

        # After scroll/hotkey on browser, extract visible data from screen
        if action in ("scroll", "hotkey") and result.get("success"):
            task_lower = task.lower()
            # Check if the task involves web data extraction
            web_data_keywords = ["imdb", "website", "web page", "browser", "top 250", "top 30",
                                 "rankings", "movie", "wikipedia"]
            if any(kw in task_lower for kw in web_data_keywords):
                try:
                    after_img = _screenshot.take("/tmp/gui_agent_extract.png")
                    time.sleep(0.3)
                    new_data = _extract_screen_data(
                        task=task, img_path=after_img,
                        existing_data=extracted_data, runtime=rt,
                    )
                    if new_data and new_data != "NO_DATA":
                        extracted_data += "\n" + new_data if extracted_data else new_data
                        print(f"  [step {step}] extracted {len(new_data)} chars of screen data", file=sys.stderr)
                except Exception as e:
                    print(f"  [step {step}] extraction error: {e}", file=sys.stderr)

        # Record state transition (only for GUI actions that change state)
        new_state = current_state
        if action in GUI_ACTIONS:
            t0 = time.time()
            after_img = _screenshot.take("/tmp/gui_agent_after.png")
            new_state, _ = identify_state(app_name, after_img)
            timing["state_record"] = round(time.time() - t0, 2)

            if result.get("success") and current_state is not None:
                record_transition(
                    app_name=app_name, from_state=current_state,
                    action=action, action_target=plan.get("target", ""),
                    to_state=new_state,
                )

        timing["step_total"] = round(time.time() - step_start, 2)

        history.append({
            "step": step,
            "action": action,
            "target": plan.get("target", ""),
            "code": plan.get("code", ""),
            "output": result.get("output", ""),
            "reasoning": plan.get("reasoning", ""),
            "success": result.get("success", False),
            "state_before": current_state,
            "state_after": new_state,
            "timing": timing,
        })

    total_time = round(time.time() - task_start, 2)
    result = {
        "task": task,
        "success": completed,
        "steps_taken": len(history),
        "total_time": total_time,
        "history": history,
    }
    _save_workflow_record(result, app_name)
    return result


# ═══════════════════════════════════════════
# Workflow recording
# ═══════════════════════════════════════════

def _save_workflow_record(result: dict, app_name: str):
    """Save completed task as a workflow record (JSONL, append-only)."""
    import hashlib
    from gui_harness.memory import app_memory

    app_dir = app_memory.get_app_dir(app_name)
    app_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = app_dir / "workflows.jsonl"

    task_hash = hashlib.sha256(result["task"].encode()).hexdigest()[:12]
    record = {
        "task_hash": task_hash,
        "task": result["task"],
        "success": result["success"],
        "steps_taken": result["steps_taken"],
        "total_time": result.get("total_time"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [
            {
                "step": h["step"], "action": h["action"],
                "target": h.get("target", ""), "code": h.get("code", ""),
                "success": h.get("success", False),
            }
            for h in result["history"]
        ],
    }
    try:
        with open(workflow_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
