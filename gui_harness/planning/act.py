"""
gui_harness.planning.act — DEPRECATED.

Action execution has moved to gui_harness.action.actions.
Actions are now pure execution functions (no LLM calls).
The LLM planner in execute_task provides all parameters directly.

Import from gui_harness.action.actions instead:
    from gui_harness.action.actions import click, type_text, key_press, shortcut
"""

# Re-export for backward compatibility with navigate.py etc.
from gui_harness.action.actions import (
    click as _click,
    double_click as _double_click,
    type_text as _type_text,
    key_press as _key_press,
    shortcut as _shortcut,
)


def act(action: str, target: str, text: str = None,
        app_name: str = None, runtime=None) -> dict:
    """Legacy wrapper — dispatches to gui_harness.action.actions.

    Note: click/double_click/right_click require coordinates now.
    This wrapper cannot provide them (no LLM), so it returns an error
    for coordinate-based actions.
    """
    if action in ("click", "single_click"):
        return {"action": action, "success": False,
                "error": "act() is deprecated. Use actions.click(x, y) with coordinates."}
    elif action == "double_click":
        return {"action": action, "success": False,
                "error": "act() is deprecated. Use actions.double_click(x, y) with coordinates."}
    elif action == "type":
        return _type_text(text or "")
    elif action == "key_press":
        return _key_press(target)
    elif action == "shortcut":
        return _shortcut(target)
    else:
        return {"action": action, "success": False, "error": f"Unknown action: {action}"}
