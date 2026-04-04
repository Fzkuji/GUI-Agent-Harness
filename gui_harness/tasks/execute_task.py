"""
execute_task — the main planning loop.

Takes a natural language task and autonomously loops:
  observe → plan → act → repeat

execute_task is a plain function (not @agentic_function) because it
orchestrates multiple sub-functions that each call exec() once.
"""

from __future__ import annotations

import json

from agentic import agentic_function

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


@agentic_function(summarize={"depth": 0, "siblings": 0})
def plan_next_action(task: str, obs: dict, step: int, max_steps: int,
                     history: list, runtime=None) -> dict:
    """Decide the single next GUI action to take.

    You are given:
    - The overall task to accomplish
    - The current screen observation (app, visible text, elements)
    - Previous action history

    GUI knowledge:
    - Desktop files/icons need DOUBLE_CLICK to open (single click only selects)
    - Spreadsheet cells: click to select, double_click to edit, type to input, Enter to confirm
    - If an action caused NO screen change, try a DIFFERENT approach (don't repeat the same action)
    - Dialog boxes usually have OK/Cancel buttons — click them to dismiss
    - Use keyboard shortcuts when efficient (Ctrl+S to save, Ctrl+Z to undo, etc.)
    - After typing in a cell, press Enter to commit (use key_press "return")

    Choose ONE action. Options:
    - "click": click an element (specify target name/description)
    - "type": type text into a field (specify target + text)
    - "double_click": double-click an element (use for opening files, editing cells)
    - "right_click": right-click an element
    - "shortcut": keyboard shortcut (specify keys like "ctrl+c")
    - "key_press": single key press (specify key like "return", "escape", "delete")
    - "done": task is FULLY completed (all required content has been entered/saved)

    IMPORTANT: only return "done" when the task is truly finished.
    If you still need to type content or verify results, do NOT return "done".

    Return ONLY valid JSON (no markdown, no explanation):
    {
      "action": "click" or "type" or "double_click" or "right_click" or "shortcut" or "key_press" or "done",
      "target": "what to click/interact with",
      "text": "text to type (only for type action)",
      "reasoning": "why this action"
    }
    """
    rt = runtime or _get_runtime()

    history_summary = ""
    if history:
        lines = []
        for h in history[-5:]:
            status = "✅" if h.get("success") else "❌"
            target_str = str(h.get('target', ''))[:40]
            lines.append(f"  {h['step']}. {status} {h['action']} → {target_str}")
        history_summary = f"\nRecent actions:\n" + "\n".join(lines)

    context = f"""Task: {task}

Current screen state:
  App: {obs.get('app_name', 'unknown')}
  Description: {obs.get('page_description', 'unknown')}
  Visible text: {obs.get('visible_text', [])[:20]}
  Interactive elements: {obs.get('interactive_elements', [])[:15]}
  Target visible: {obs.get('target_visible', False)}
  Target location: {obs.get('target_location')}

Step {step}/{max_steps}.{history_summary}"""

    reply = rt.exec(content=[
        {"type": "text", "text": context},
    ])

    try:
        return _parse_json(reply)
    except Exception:
        # Parse failed — try to extract action from raw text
        reply_lower = reply.lower()
        if '"done"' in reply_lower or 'task is complete' in reply_lower:
            return {"action": "done", "reasoning": f"Parsed from text: {reply[:200]}"}
        # NOT done — ask LLM to retry with stricter format
        return {"action": "retry", "reasoning": f"Could not parse plan: {reply[:200]}"}


def execute_task(task: str, runtime=None, max_steps: int = 15) -> dict:
    """Execute a GUI task autonomously.

    Runs an observe → plan → act loop until the task is complete
    or max_steps is reached.

    Args:
        task:       Natural language description of what to do.
        runtime:    Optional: GUIRuntime instance.
        max_steps:  Maximum number of actions (default: 15).

    Returns:
        dict: task, success, steps_taken, final_state, history
    """
    from gui_harness.planning.observe import observe
    from gui_harness.planning.act import act

    rt = runtime or _get_runtime()

    history = []
    completed = False

    for step in range(max_steps):
        # 1. OBSERVE
        obs = observe(
            task=f"Step {step + 1}/{max_steps}. Task: {task}. What is the current state?",
            runtime=rt,
        )

        # 2. PLAN
        plan = plan_next_action(
            task=task, obs=obs, step=step + 1, max_steps=max_steps,
            history=history, runtime=rt,
        )

        action = plan.get("action", "done")

        # 3. PARSE FAILED? Skip this step, re-observe next iteration
        if action == "retry":
            history.append({
                "step": step + 1, "action": "retry",
                "reasoning": plan.get("reasoning", "parse failed"),
                "success": False, "screen_changed": False,
            })
            continue

        # 4. DONE?
        if action == "done":
            completed = True
            history.append({"step": step + 1, "action": "done", "reasoning": plan.get("reasoning", "")})
            break

        # 4. ACT
        if action == "key_press":
            from gui_harness.action import input as _input
            _input.key_press(plan.get("target", "return"))
            act_result = {"action": "key_press", "target": plan.get("target"), "success": True, "screen_changed": True}
        elif action == "shortcut":
            from gui_harness.action import input as _input
            keys = [k.strip() for k in plan.get("target", "").split("+")]
            _input.key_combo(*keys)
            act_result = {"action": "shortcut", "target": plan.get("target"), "success": True, "screen_changed": True}
        else:
            act_result = act(
                action=action,
                target=plan.get("target", ""),
                text=plan.get("text"),
                runtime=rt,
            )

        history.append({
            "step": step + 1,
            "action": action,
            "target": plan.get("target", ""),
            "text": plan.get("text"),
            "reasoning": plan.get("reasoning", ""),
            "success": act_result.get("success", False),
            "screen_changed": act_result.get("screen_changed", False),
        })

    # Final observation
    final_obs = observe(task=f"Task was: {task}. Is it completed?", runtime=rt)

    return {
        "task": task,
        "success": completed,
        "steps_taken": len(history),
        "final_state": final_obs.get("page_description", "unknown"),
        "history": history,
    }


def _parse_json(reply: str) -> dict:
    text = reply.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)
