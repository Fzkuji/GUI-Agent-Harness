"""
execute_task — autonomous GUI task execution with visual memory.

Design principle:
  The LLM is the decision maker — it decides WHAT to do freely.
  We only enforce HOW for things the LLM can't do well (GUI clicking).

Architecture:
  gui_agent(task)        <- @agentic_function, ONE step per call
    1. Screenshot + detect components
    2. LLM decides what to do (decide_next_action)
    3. Execute the action (dispatch)
    4. Return result

  execute_task(task)     <- plain Python loop, drives gui_agent
    - Setup (analysis, base memory, system context)
    - Loop gui_agent until done or max_steps
    - Teardown + workflow recording
"""

from __future__ import annotations

import inspect
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
from agentic.functions.build_catalog import build_catalog
from agentic.functions.parse_action import parse_action

# ═══════════════════════════════════════════
# Action wrappers (callable from dispatch)
# ═══════════════════════════════════════════

def _action_click(target: str, task: str, img_path: str, app_name: str, runtime) -> dict:
    location = locate_target(task=task, target=target, img_path=img_path, app_name=app_name, runtime=runtime)
    if not location:
        return {"success": False, "error": f"Target not found: {target}"}
    _input.mouse_click(location["cx"], location["cy"])
    return {"success": True, "location": location}

def _action_double_click(target: str, task: str, img_path: str, app_name: str, runtime) -> dict:
    location = locate_target(task=task, target=target, img_path=img_path, app_name=app_name, runtime=runtime)
    if not location:
        return {"success": False, "error": f"Target not found: {target}"}
    _input.mouse_double_click(location["cx"], location["cy"])
    return {"success": True, "location": location}

def _action_right_click(target: str, task: str, img_path: str, app_name: str, runtime) -> dict:
    location = locate_target(task=task, target=target, img_path=img_path, app_name=app_name, runtime=runtime)
    if not location:
        return {"success": False, "error": f"Target not found: {target}"}
    _input.mouse_right_click(location["cx"], location["cy"])
    return {"success": True, "location": location}

def _action_drag(target: str, target_end: str, task: str, img_path: str, app_name: str, runtime) -> dict:
    start = locate_target(task=task, target=f"Find START: {target}", img_path=img_path, app_name=app_name, runtime=runtime)
    if not start:
        return {"success": False, "error": f"Start not found: {target}"}
    end = locate_target(task=task, target=f"Find END: {target_end}", img_path=img_path, app_name=app_name, runtime=runtime)
    if not end:
        return {"success": False, "error": f"End not found: {target_end}"}
    _input.mouse_drag(start["cx"], start["cy"], end["cx"], end["cy"])
    return {"success": True}

def _action_type(text: str) -> dict:
    _input.type_text(text)
    return {"success": True}

def _action_press(key: str) -> dict:
    _input.key_press(key)
    return {"success": True}

def _action_hotkey(keys: str) -> dict:
    key_list = [k.strip() for k in keys.split("+")]
    _input.key_combo(*key_list)
    return {"success": True}

def _action_scroll(direction: str) -> dict:
    _input.key_press("pageup" if direction.lower() == "up" else "pagedown")
    return {"success": True}

def _action_done(reasoning: str) -> dict:
    return {"success": True, "done": True, "reasoning": reasoning}


def _build_action_registry():
    """Build the action function registry for LLM dispatch."""
    return {
        "click": {
            "function": _action_click,
            "description": "Click a UI element on screen (we locate it for you)",
            "input": {
                "target": {"source": "llm", "type": str, "description": "description of element to click"},
                "task": {"source": "context"},
                "img_path": {"source": "context"},
                "app_name": {"source": "context"},
            },
            "output": {"success": bool},
        },
        "double_click": {
            "function": _action_double_click,
            "description": "Double-click a UI element on screen",
            "input": {
                "target": {"source": "llm", "type": str, "description": "description of element to double-click"},
                "task": {"source": "context"},
                "img_path": {"source": "context"},
                "app_name": {"source": "context"},
            },
            "output": {"success": bool},
        },
        "right_click": {
            "function": _action_right_click,
            "description": "Right-click a UI element on screen",
            "input": {
                "target": {"source": "llm", "type": str, "description": "description of element to right-click"},
                "task": {"source": "context"},
                "img_path": {"source": "context"},
                "app_name": {"source": "context"},
            },
            "output": {"success": bool},
        },
        "drag": {
            "function": _action_drag,
            "description": "Drag from one element to another",
            "input": {
                "target": {"source": "llm", "type": str, "description": "description of drag start element"},
                "target_end": {"source": "llm", "type": str, "description": "description of drag end element"},
                "task": {"source": "context"},
                "img_path": {"source": "context"},
                "app_name": {"source": "context"},
            },
            "output": {"success": bool},
        },
        "type": {
            "function": _action_type,
            "description": "Type text using keyboard",
            "input": {
                "text": {"source": "llm", "type": str, "description": "text to type"},
            },
            "output": {"success": bool},
        },
        "press": {
            "function": _action_press,
            "description": "Press a keyboard key (enter, tab, escape, etc.)",
            "input": {
                "key": {"source": "llm", "type": str, "description": "key to press"},
            },
            "output": {"success": bool},
        },
        "hotkey": {
            "function": _action_hotkey,
            "description": "Press a keyboard shortcut (e.g., ctrl+s, ctrl+c)",
            "input": {
                "keys": {"source": "llm", "type": str, "description": "key combination like ctrl+s"},
            },
            "output": {"success": bool},
        },
        "scroll": {
            "function": _action_scroll,
            "description": "Scroll the page up or down",
            "input": {
                "direction": {"source": "llm", "type": str, "description": "up or down"},
            },
            "output": {"success": bool},
        },
        "general": {
            "function": general_action,
            "description": "Execute command-line operations on the VM (only for tasks that cannot be done via GUI)",
            "input": {
                "sub_task": {"source": "llm", "type": str, "description": "what to do via command line"},
                "task_context": {"source": "context"},
            },
            "output": {"success": bool, "output": str},
        },
        "done": {
            "function": _action_done,
            "description": "Mark the task as fully complete",
            "input": {
                "reasoning": {"source": "llm", "type": str, "description": "why the task is complete"},
            },
            "output": {"success": bool},
        },
    }

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


# ═══════════════════════════════════════════
# gui_agent — single step @agentic_function
# ═══════════════════════════════════════════

@agentic_function(compress=True, summarize={"siblings": -1})
def gui_agent(task: str, runtime=None) -> dict:
    """Autonomous GUI agent. Execute one step of a GUI task.

    Takes a screenshot, detects UI components, asks the LLM what to do,
    then executes the chosen action. Returns the result.

    The caller is responsible for looping until done.

    Args:
        task: What to do, in natural language.
        runtime: LLM runtime instance.

    Returns:
        dict with: action, success, done, and action-specific fields.
    """
    rt = runtime or _get_runtime()
    timing = {}

    # 1. Screenshot
    t0 = time.time()
    img_path = _screenshot.take()
    timing["screenshot"] = round(time.time() - t0, 2)
    time.sleep(0.3)

    # 2. Component detection + matching
    t0 = time.time()
    from gui_harness.planning.component_memory import detect_components, match_memory_components
    detection = detect_components(img_path)
    icons = detection.get("icons", []) if isinstance(detection, dict) else []
    texts = detection.get("texts", []) if isinstance(detection, dict) else []
    matched = match_memory_components("desktop", img_path)
    timing["detect"] = round(time.time() - t0, 2)

    # Build component context
    comp_lines = []
    for c in matched[:30]:
        comp_lines.append(f"  [{c['name']}] at ({c['cx']}, {c['cy']})")
    text_lines = []
    for t_item in texts[:40]:
        label = t_item.get("label", "")
        if label and len(label) > 1:
            text_lines.append(f"  '{label}' at ({t_item.get('cx', 0)}, {t_item.get('cy', 0)})")

    component_info = ""
    if comp_lines:
        component_info += "\n<known_components>\n" + "\n".join(comp_lines) + "\n</known_components>"
    if text_lines:
        component_info += "\n<screen_text>\n" + "\n".join(text_lines) + "\n</screen_text>"

    # 3. LLM decides
    t0 = time.time()
    available = _build_action_registry()
    catalog = build_catalog(available)

    plan = decide_next_action(
        task=task, img_path=img_path,
        system_context=component_info,
        action_catalog=catalog,
        runtime=rt,
    )
    timing["decide"] = round(time.time() - t0, 2)

    # 4. Parse + dispatch
    action_name = plan.get("call", plan.get("action", "general"))

    if action_name == "done":
        return {
            "action": "done", "done": True, "success": True,
            "reasoning": plan.get("args", plan).get("reasoning", plan.get("reasoning", "")),
            "timing": timing,
        }

    t0 = time.time()
    result = {}
    try:
        dispatch_context = {
            "task": task,
            "img_path": img_path,
            "app_name": "desktop",
            "task_context": f"<task>{task}</task>",
        }

        if action_name in available:
            spec = available[action_name]
            func = spec["function"]
            args = dict(plan.get("args", {}))
            # Also accept flat plan keys for backward compatibility
            for key in spec.get("input", {}):
                if key not in args and key in plan:
                    args[key] = plan[key]
            # Fill context params
            for key, info in spec.get("input", {}).items():
                if info.get("source") == "context" and key not in args:
                    if key in dispatch_context:
                        args[key] = dispatch_context[key]
            # Inject runtime if needed
            sig = inspect.signature(func)
            if "runtime" in sig.parameters and "runtime" not in args:
                args["runtime"] = rt
            valid_params = set(sig.parameters.keys())
            args = {k: v for k, v in args.items() if k in valid_params}
            result = func(**args)
        else:
            sub_task = plan.get("task", plan.get("target", str(plan)[:200]))
            result = general_action(sub_task=sub_task, task_context=f"<task>{task}</task>", runtime=rt)
    except Exception as e:
        result = {"success": False, "output": str(e)}
    timing["execute"] = round(time.time() - t0, 2)

    return {
        "action": action_name,
        "target": plan.get("target", ""),
        "reasoning": plan.get("reasoning", ""),
        "success": result.get("success", False),
        "output": result.get("output", ""),
        "done": False,
        "timing": timing,
    }


# ═══════════════════════════════════════════
# LLM decision function (called by gui_agent)
# ═══════════════════════════════════════════

@agentic_function(summarize={"depth": 0, "siblings": 0})
def decide_next_action(
    task: str,
    img_path: str,
    system_context: str = "",
    action_catalog: str = "",
    runtime=None,
) -> dict:
    """Look at the screenshot and decide the next action.

    You are a GUI agent. Always prefer GUI actions over command-line operations.
    - If a browser is visible with relevant content, interact via GUI: scroll,
      click elements, read from the screen.
    - Only use "general" (command-line) when the information CANNOT be obtained
      through GUI interaction (e.g., reading/writing files not open on screen).
    - Do NOT use "general" to scrape websites or run Python scripts when the
      same data is visible in the browser on screen.
    - Do NOT generate or paraphrase content from your own knowledge — extract
      data from what you see on screen or from actual files.

    Choose one action from the available list and return the corresponding JSON.
    """
    rt = runtime or _get_runtime()

    sys_ctx = f"\n{system_context}" if system_context else ""

    context = f"""<task>{task}</task>{sys_ctx}

== Available Actions ==
{action_catalog}"""

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
# execute_task — Python loop (NOT @agentic_function)
# ═══════════════════════════════════════════

def execute_task(task: str, runtime=None, max_steps: int = 30, app_name: str = "desktop") -> dict:
    """Execute a GUI task autonomously by looping gui_agent().

    Plain Python function. Handles setup, loops gui_agent until done,
    then records the workflow.

    Args:
        task:       Natural language description of what to do.
        runtime:    GUIRuntime instance (auto-detected if None).
        max_steps:  Maximum number of actions (default: 30).
        app_name:   App name for component memory (default: "desktop").

    Returns:
        dict: task, success, steps_taken, total_time, history
    """
    rt = runtime or _get_runtime()

    # Reset runtime
    if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
        rt._inner.reset()
    if hasattr(rt, '_planner') and hasattr(rt._planner, 'reset'):
        rt._planner.reset()

    try:
        return _execute_task_loop(task, rt, max_steps, app_name)
    finally:
        if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
            rt._inner.reset()
        if hasattr(rt, '_planner') and hasattr(rt._planner, 'reset'):
            rt._planner.reset()


def _ensure_base_memory(app_name: str, rt) -> None:
    """Auto-learn app components if no base memory exists."""
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


def _execute_task_loop(task, rt, max_steps, app_name):
    """Internal task loop."""
    history = []
    completed = False
    task_start = time.time()

    # Auto-learn app components
    _ensure_base_memory(app_name, rt)

    for step in range(1, max_steps + 1):
        print(f"  [step {step}] ...", file=sys.stderr)

        try:
            result = gui_agent(task=task, runtime=rt)
        except Exception as e:
            print(f"  [step {step}] ERROR: {e.__class__.__name__}", file=sys.stderr)
            if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
                rt._inner.reset()
            if hasattr(rt, '_planner') and hasattr(rt._planner, 'reset'):
                rt._planner.reset()
            result = {"action": "error", "success": False, "output": str(e), "done": False}

        action_name = result.get("action", "?")
        target = result.get("target", "")
        print(f"  [step {step}] {action_name}: {str(target)[:100]}", file=sys.stderr)

        history.append({"step": step, **result})

        if result.get("done"):
            completed = True
            break

    total_time = round(time.time() - task_start, 2)
    final = {
        "task": task,
        "success": completed,
        "steps_taken": len(history),
        "total_time": total_time,
        "history": history,
        "final_state": history[-1].get("output", "") if history else "",
    }
    _save_workflow_record(final, app_name)
    return final


# ═══════════════════════════════════════════
# Workflow recording
# ═══════════════════════════════════════════

def _save_workflow_record(result: dict, app_name: str):
    """Save the workflow record for future reference."""
    from gui_harness.memory import app_memory
    try:
        app_dir = app_memory.get_app_dir(app_name)
        workflows_dir = app_dir / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        record_path = workflows_dir / f"workflow_{ts}.json"
        with open(record_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
    except Exception as e:
        print(f"  [workflow] save error: {e}", file=sys.stderr)


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

    Rules:
    - Only extract what you can ACTUALLY SEE on the screen right now
    - Do NOT make up or guess any data
    - Do NOT use your own knowledge to fill in missing information
    - If you can't read something clearly, skip it
    - Use a consistent format (e.g., "1. Title (Year) - Rating")
    - If this is a continuation, only extract NEW items not in previous data
    - If nothing relevant is visible, return "NO_DATA"
    """
    rt = runtime or _get_runtime()

    content_parts = [
        {"type": "text", "text": f"Task: {task}"},
    ]
    if existing_data:
        content_parts[0]["text"] += f"\n\nAlready extracted:\n{existing_data[-2000:]}\n\nExtract only NEW items."

    content_parts.append({"type": "image", "path": img_path})

    return rt.exec(content=content_parts)
