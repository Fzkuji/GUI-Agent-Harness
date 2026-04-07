"""
execute_task — the main planning loop.

Full workflow per step:
  Phase 0: Screenshot → LLM sees image → decides action type
  Phase 1-5: (only if coordinates needed) detect → match → label → locate
  Execute: call atomic action function

Actions are pure execution functions in gui_harness.action.actions.
Component memory accumulates across steps and tasks.
"""

from __future__ import annotations

from gui_harness.utils import parse_json
from agentic import agentic_function

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


# Actions that require screen coordinates
COORDINATE_ACTIONS = {"click", "single_click", "double_click", "right_click", "drag"}

# Actions that don't require coordinates
NO_COORDINATE_ACTIONS = {"type", "key_press", "shortcut", "paste", "scroll", "done"}

# Action descriptions for the LLM planner
ACTION_DESCRIPTIONS = """
Available actions:

  click(x, y)        — Single click at coordinates. Needs coordinates.
  double_click(x, y)  — Double click. Needs coordinates. Use to open files, enter cell edit mode.
  right_click(x, y)   — Right click. Needs coordinates.
  drag(x1, y1, x2, y2) — Drag from one point to another. Needs two sets of coordinates.
  type(text)          — Type text into currently focused element. NO coordinates needed.
                        Does NOT click first, does NOT press Enter after.
  key_press(key)      — Press a key ("return", "escape", "tab", "delete", etc.). NO coordinates needed.
  shortcut(keys)      — Keyboard shortcut ("ctrl+s", "ctrl+z", etc.). NO coordinates needed.
  paste(text)         — Paste via clipboard. NO coordinates needed.
  done                — Task fully completed.

RULES:
- To input text: click the target first, then type, then key_press "return" if needed.
- To save: shortcut "ctrl+s".
- If a previous action failed, try a DIFFERENT approach.
""".strip()


@agentic_function(summarize={"depth": 0, "siblings": 0})
def phase0_decide_action(task: str, img_path: str, step: int, max_steps: int,
                         history: list, runtime=None) -> dict:
    """Phase 0: LLM sees the screenshot and decides what action to take.

    If the action needs coordinates, the coordinates field will be null
    and the locate workflow will run next.

    Return ONLY JSON:
    {
      "action": "click|double_click|right_click|drag|type|key_press|shortcut|paste|done",
      "target": "description of what to interact with (for coordinate actions)",
      "text": "text to type (for type/paste)",
      "key": "key name (for key_press)",
      "keys": "shortcut keys (for shortcut)",
      "reasoning": "brief explanation"
    }
    """
    rt = runtime or _get_runtime()

    history_summary = ""
    if history:
        lines = []
        for h in history[-5:]:
            status = "✅" if h.get("success") else "❌"
            desc = h.get("description", h.get("action", ""))
            lines.append(f"  {h['step']}. {status} {desc}")
        history_summary = f"\nRecent actions:\n" + "\n".join(lines)

    steps_left = max_steps - step
    urgency = ""
    if steps_left <= 3:
        urgency = f"\n⚠️ Only {steps_left} steps left! Prioritize completing and SAVING now."

    context = f"""Task: {task}

{ACTION_DESCRIPTIONS}

Look at the screenshot and decide: what is the SINGLE next action to take?

Step {step}/{max_steps}.{history_summary}{urgency}"""

    reply = rt.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])

    try:
        return parse_json(reply)
    except Exception:
        reply_lower = reply.lower()
        if '"done"' in reply_lower or 'task is complete' in reply_lower:
            return {"action": "done", "reasoning": f"Parsed from text: {reply[:200]}"}
        return {"action": "retry", "reasoning": f"Could not parse: {reply[:200]}"}


def execute_task(task: str, runtime=None, max_steps: int = 20,
                 app_name: str = None) -> dict:
    """Execute a GUI task autonomously.

    Per-step workflow:
      Phase 0: Screenshot → LLM decides action
      If needs coordinates:
        Phase 1: GPA detect components
        Phase 2: Match against saved memory
        Phase 3: LLM checks matched components for target
        Phase 4: Label unknowns until target found
        Phase 5: Cleanup
      Execute atomic action

    Args:
        task:       Natural language description of what to do.
        runtime:    Optional: GUIRuntime instance.
        max_steps:  Maximum number of actions (default: 20).
        app_name:   App name for component memory (auto-detected if None).

    Returns:
        dict: task, success, steps_taken, final_state, history
    """
    from gui_harness.perception import screenshot as ss
    from gui_harness.action import actions
    from gui_harness.action.input import get_frontmost_app
    from gui_harness.planning.component_memory import locate_target

    rt = runtime or _get_runtime()
    if not app_name:
        app_name = get_frontmost_app()

    history = []
    completed = False

    for step in range(1, max_steps + 1):
        # ─── Phase 0: Screenshot → LLM decides action ───
        img_path = ss.take()

        plan = phase0_decide_action(
            task=task, img_path=img_path,
            step=step, max_steps=max_steps,
            history=history, runtime=rt,
        )

        action = plan.get("action", "done").lower()

        # Parse failed → retry
        if action == "retry":
            history.append({
                "step": step, "action": "retry",
                "description": f"retry — {plan.get('reasoning', '')[:60]}",
                "success": False,
            })
            continue

        # Done
        if action == "done":
            completed = True
            history.append({
                "step": step, "action": "done",
                "description": f"done — {plan.get('reasoning', '')[:60]}",
            })
            break

        # ─── Actions that DON'T need coordinates ───
        if action not in COORDINATE_ACTIONS:
            result = _execute_no_coord_action(actions, action, plan)
            history.append({
                "step": step, "action": action,
                "description": _describe_action(action, plan, result),
                "success": result.get("success", False),
            })
            continue

        # ─── Actions that NEED coordinates: run locate workflow ───
        target_desc = plan.get("target", task)

        if action == "drag":
            # Drag needs two positions — locate both
            # First: locate start position
            all_comps_1, start_target = locate_target(
                task=f"Find the START position for drag: {target_desc}",
                app_name=app_name, img_path=img_path, runtime=rt,
            )
            if not start_target:
                history.append({
                    "step": step, "action": action,
                    "description": f"drag — start position not found ❌",
                    "success": False,
                })
                continue

            # Second: locate end position
            all_comps_2, end_target = locate_target(
                task=f"Find the END position for drag: {target_desc}",
                app_name=app_name, img_path=img_path, runtime=rt,
            )
            if not end_target:
                history.append({
                    "step": step, "action": action,
                    "description": f"drag — end position not found ❌",
                    "success": False,
                })
                continue

            result = actions.drag(
                start_target["x"], start_target["y"],
                end_target["x"], end_target["y"],
            ) if hasattr(actions, 'drag') else {
                "action": "drag", "success": False, "error": "drag not implemented"
            }
        else:
            # click / double_click / right_click — locate target
            all_comps, target = locate_target(
                task=f"{action}: {target_desc}",
                app_name=app_name, img_path=img_path, runtime=rt,
            )

            if not target:
                history.append({
                    "step": step, "action": action,
                    "description": f"{action} — target not found ❌",
                    "success": False,
                })
                continue

            # Execute the coordinate action
            if action in ("click", "single_click"):
                result = actions.click(target["x"], target["y"])
            elif action == "double_click":
                result = actions.double_click(target["x"], target["y"])
            elif action == "right_click":
                result = actions.right_click(target["x"], target["y"])
            else:
                result = {"action": action, "success": False, "error": f"Unknown: {action}"}

        coord_str = ""
        if action == "drag" and start_target and end_target:
            coord_str = f" ({start_target['x']},{start_target['y']})→({end_target['x']},{end_target['y']})"
        elif action != "drag" and target:
            coord_str = f" ({target['x']},{target['y']})"

        history.append({
            "step": step, "action": action,
            "description": f"{action}{coord_str} {plan.get('target', '')[:30]} {'✅' if result.get('success') else '❌'}",
            "success": result.get("success", False),
        })

        # ─── Emergency save ───
        if step == max_steps - 1 and not completed:
            actions.shortcut("ctrl+s")
            history.append({
                "step": step, "action": "shortcut",
                "description": "shortcut(ctrl+s) — emergency auto-save",
                "success": True,
            })

    # Final screenshot for status
    final_img = ss.take("/tmp/gui_agent_final.png")

    return {
        "task": task,
        "success": completed,
        "steps_taken": len(history),
        "final_state": f"Screenshot saved: {final_img}",
        "history": history,
    }


def _execute_no_coord_action(actions, action: str, plan: dict) -> dict:
    """Execute an action that doesn't need coordinates."""
    if action == "type":
        return actions.type_text(plan.get("text", ""))
    elif action == "key_press":
        return actions.key_press(plan.get("key", plan.get("target", "return")))
    elif action == "shortcut":
        return actions.shortcut(plan.get("keys", plan.get("target", "")))
    elif action == "paste":
        return actions.paste_text(plan.get("text", ""))
    elif action == "scroll":
        return actions.scroll(plan.get("direction", "down"))
    else:
        return {"action": action, "success": False, "error": f"Unknown: {action}"}


def _describe_action(action: str, plan: dict, result: dict) -> str:
    """Human-readable description of an executed action."""
    status = "✅" if result.get("success") else "❌"
    if action == "type":
        text = plan.get("text", "")
        short = text[:30] + "..." if len(text) > 30 else text
        return f"type(\"{short}\") {status}"
    elif action == "key_press":
        return f"key_press({plan.get('key', plan.get('target', ''))}) {status}"
    elif action == "shortcut":
        return f"shortcut({plan.get('keys', plan.get('target', ''))}) {status}"
    elif action == "paste":
        return f"paste(\"{plan.get('text', '')[:20]}\") {status}"
    elif action == "scroll":
        return f"scroll({plan.get('direction', 'down')}) {status}"
    else:
        return f"{action} {status}"
