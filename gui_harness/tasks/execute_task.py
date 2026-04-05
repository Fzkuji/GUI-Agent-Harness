"""
execute_task — the main Phase 0-5 planning loop.

Each step:
  Phase 0: Screenshot → LLM sees image → decides action
    ├─ No coordinates needed (type/key_press/shortcut/paste/done) → execute directly
    └─ Coordinates needed (click/double_click/right_click/drag) → Phase 1-5
  Phase 1: GPA detection + OCR → N components
  Phase 2: Template match against memory → known components
  Phase 3: LLM finds target in known components → execute if found
  Phase 4: Label unknown components one-by-one (stop when found)
  Phase 5: Cleanup temporary files

execute_task is a plain function (not @agentic_function) because it
orchestrates the loop. Only plan_next_action is an @agentic_function.
"""

from __future__ import annotations

import time

from agentic import agentic_function

from gui_harness.utils import parse_json
from gui_harness.perception import screenshot as _screenshot
from gui_harness.action import input as _input
from gui_harness.planning.component_memory import locate_target

# Actions that require screen coordinates
COORD_ACTIONS = {"click", "double_click", "right_click", "drag"}

# Actions that execute without coordinates
NO_COORD_ACTIONS = {"type", "key_press", "shortcut", "paste", "scroll", "done"}

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


# ═══════════════════════════════════════════
# Phase 0: Screenshot → LLM decides action
# ═══════════════════════════════════════════

@agentic_function(summarize={"depth": 0, "siblings": 0})
def plan_next_action(
    task: str,
    img_path: str,
    step: int,
    max_steps: int,
    history: list,
    runtime=None,
) -> dict:
    """Phase 0: Look at the current screen and decide the next action.

    You are given a screenshot of the current screen state and the task
    to accomplish. Decide what to do next.

    GUI knowledge:
    - Desktop files/icons: DOUBLE_CLICK to open (single click only selects)
    - Spreadsheet cells: click to select, then type to input, Enter to confirm
    - Dialog boxes: click OK/Cancel to dismiss
    - If a previous action caused NO screen change, try a DIFFERENT approach
    - Use keyboard shortcuts when efficient (Ctrl+S, Ctrl+Z, etc.)
    - After typing in a cell, use key_press "return" to commit

    Available actions:

    Coordinate actions (will trigger element detection):
    - "click": click an element (describe target)
    - "double_click": double-click an element (for opening files, editing cells)
    - "right_click": right-click an element (for context menus)
    - "drag": drag from one element to another (describe both start and end targets)

    Non-coordinate actions (execute immediately):
    - "type": type text (specify text in "text" field)
    - "key_press": press a key (specify key: "return", "escape", "tab", "delete", etc.)
    - "shortcut": keyboard shortcut (specify keys: "ctrl+s", "ctrl+c", etc.)
    - "paste": paste text from description (specify text in "text" field)
    - "scroll": scroll (specify direction: "up" or "down" in target)
    - "done": task is FULLY completed

    IMPORTANT: Only return "done" when the task is truly finished.

    Return ONLY valid JSON:
    {
      "action": "click|double_click|right_click|drag|type|key_press|shortcut|paste|scroll|done",
      "target": "element to interact with (for coordinate actions) or key/direction",
      "target_end": "end element (only for drag action)",
      "text": "text to type (only for type/paste)",
      "reasoning": "brief explanation"
    }
    """
    rt = runtime or _get_runtime()

    history_summary = ""
    if history:
        lines = []
        for h in history[-5:]:
            status = "ok" if h.get("success") else "FAIL"
            target_str = str(h.get("target", ""))[:40]
            lines.append(f"  {h['step']}. [{status}] {h['action']} -> {target_str}")
        history_summary = f"\nRecent actions:\n" + "\n".join(lines)

    context = f"""Task: {task}
Step {step}/{max_steps}.{history_summary}

Look at the screenshot and decide the next action.
Return ONLY valid JSON."""

    reply = rt.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])

    try:
        return parse_json(reply)
    except Exception:
        reply_lower = reply.lower()
        if '"done"' in reply_lower or "task is complete" in reply_lower:
            return {"action": "done", "reasoning": f"Parsed from text: {reply[:200]}"}
        return {"action": "retry", "reasoning": f"Could not parse: {reply[:200]}"}


# ═══════════════════════════════════════════
# Action execution helpers
# ═══════════════════════════════════════════

def _execute_no_coord_action(action: str, plan: dict) -> dict:
    """Execute an action that does not need screen coordinates."""
    target = plan.get("target", "")
    text = plan.get("text", "")

    if action == "type":
        _input.type_text(text)
    elif action == "paste":
        _input.paste_text(text)
    elif action == "key_press":
        _input.key_press(target or "return")
    elif action == "shortcut":
        keys = [k.strip() for k in target.split("+")]
        _input.key_combo(*keys)
    elif action == "scroll":
        direction = target.lower() if target else "down"
        if direction == "up":
            _input.key_press("pageup")
        else:
            _input.key_press("pagedown")

    return {"success": True, "action": action}


def _execute_coord_action(
    action: str,
    plan: dict,
    task: str,
    img_path: str,
    app_name: str,
    runtime,
) -> dict:
    """Execute an action that requires screen coordinates via Phase 1-5."""
    target = plan.get("target", "")

    if action == "drag":
        # Drag needs two coordinates: start and end
        target_end = plan.get("target_end", "")

        start = locate_target(
            task=task,
            target=f"Find START position: {target}",
            img_path=img_path,
            app_name=app_name,
            runtime=runtime,
        )
        if not start:
            return {"success": False, "action": action, "error": f"Start target not found: {target}"}

        end = locate_target(
            task=task,
            target=f"Find END position: {target_end}",
            img_path=img_path,
            app_name=app_name,
            runtime=runtime,
        )
        if not end:
            return {"success": False, "action": action, "error": f"End target not found: {target_end}"}

        _input.mouse_drag(start["cx"], start["cy"], end["cx"], end["cy"])
        return {"success": True, "action": action, "start": start, "end": end}

    else:
        # click, double_click, right_click — single target
        location = locate_target(
            task=task,
            target=target,
            img_path=img_path,
            app_name=app_name,
            runtime=runtime,
        )

        if not location:
            return {"success": False, "action": action, "error": f"Target not found: {target}"}

        cx, cy = location["cx"], location["cy"]

        if action == "click":
            _input.mouse_click(cx, cy)
        elif action == "double_click":
            _input.mouse_double_click(cx, cy)
        elif action == "right_click":
            _input.mouse_right_click(cx, cy)

        return {"success": True, "action": action, "location": location}


# ═══════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════

def execute_task(task: str, runtime=None, max_steps: int = 15, app_name: str = "desktop") -> dict:
    """Execute a GUI task autonomously using the Phase 0-5 loop.

    Each iteration:
      Phase 0: Screenshot → LLM sees image → decides action
      If action needs coordinates → Phase 1-5 (locate_target)
      If action is no-coord → execute directly

    Args:
        task:       Natural language description of what to do.
        runtime:    GUIRuntime instance (auto-detected if None).
        max_steps:  Maximum number of actions (default: 15).
        app_name:   App name for component memory (default: "desktop").

    Returns:
        dict: task, success, steps_taken, history, timing
    """
    rt = runtime or _get_runtime()
    history = []
    completed = False
    task_start = time.time()

    for step in range(1, max_steps + 1):
        step_start = time.time()
        timing = {}

        # Phase 0: Screenshot → LLM decides
        t0 = time.time()
        img_path = _screenshot.take()
        timing["screenshot"] = round(time.time() - t0, 2)
        time.sleep(0.3)

        t0 = time.time()
        plan = plan_next_action(
            task=task,
            img_path=img_path,
            step=step,
            max_steps=max_steps,
            history=history,
            runtime=rt,
        )
        timing["plan_llm"] = round(time.time() - t0, 2)

        action = plan.get("action", "done")

        # Parse failure → retry next iteration
        if action == "retry":
            history.append({
                "step": step,
                "action": "retry",
                "reasoning": plan.get("reasoning", "parse failed"),
                "success": False,
                "timing": timing,
            })
            continue

        # Done
        if action == "done":
            completed = True
            history.append({
                "step": step,
                "action": "done",
                "reasoning": plan.get("reasoning", ""),
                "success": True,
                "timing": timing,
            })
            break

        # Execute action
        t0 = time.time()
        if action in COORD_ACTIONS:
            result = _execute_coord_action(
                action=action,
                plan=plan,
                task=task,
                img_path=img_path,
                app_name=app_name,
                runtime=rt,
            )
        elif action in NO_COORD_ACTIONS:
            result = _execute_no_coord_action(action, plan)
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}
        timing["execute"] = round(time.time() - t0, 2)

        # Brief pause for UI to respond
        time.sleep(0.5)
        timing["step_total"] = round(time.time() - step_start, 2)

        history.append({
            "step": step,
            "action": action,
            "target": plan.get("target", ""),
            "text": plan.get("text"),
            "reasoning": plan.get("reasoning", ""),
            "success": result.get("success", False),
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

    # Save workflow record for future replay
    _save_workflow_record(result, app_name)

    return result


# ═══════════════════════════════════════════
# Workflow recording
# ═══════════════════════════════════════════

def _save_workflow_record(result: dict, app_name: str):
    """Save the completed task as a workflow record.

    Records are append-only JSONL files stored per app. Each record
    captures the full step sequence so that future runs of similar
    tasks can potentially replay without LLM involvement.

    Storage: gui_harness/memory/apps/<app_name>/workflows.jsonl
    """
    import hashlib
    import json
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
                "step": h["step"],
                "action": h["action"],
                "target": h.get("target", ""),
                "text": h.get("text"),
                "success": h.get("success", False),
            }
            for h in result["history"]
        ],
    }

    try:
        with open(workflow_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Never fail the task for recording issues
