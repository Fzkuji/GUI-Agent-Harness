"""Planner action registry and its single dispatch boundary."""

from __future__ import annotations

import inspect
import platform
import time
import traceback
from pathlib import Path

from gui_harness.action import actions
from gui_harness.action.general_action import general_action
from gui_harness.planning.component_memory import locate_target


def _location_to_click_space(location: dict) -> dict:
    """Convert screenshot pixels once, at the local input boundary."""
    if platform.system() != "Darwin":
        return location
    from gui_harness.action.input import get_default_name

    if get_default_name() != "local":
        return location
    from gui_harness.platform_info.dpi import screen_scale

    scale = float(screen_scale() or 1.0)
    if scale <= 1.0:
        return location
    converted = dict(location)
    converted["pixel_cx"] = location.get("cx")
    converted["pixel_cy"] = location.get("cy")
    converted["cx"] = int(round(float(location["cx"]) / scale))
    converted["cy"] = int(round(float(location["cy"]) / scale))
    converted["coordinate_scale"] = scale
    return converted


def _locate(target: str, *, task: str, img_path: str, app_name: str, runtime):
    location = locate_target(
        task=task,
        target=target,
        img_path=img_path,
        app_name=app_name,
        runtime=runtime,
    )
    return _location_to_click_space(location) if location else None


def click_target(target: str, task: str, img_path: str, app_name: str, runtime) -> dict:
    location = _locate(
        target, task=task, img_path=img_path, app_name=app_name, runtime=runtime,
    )
    if not location:
        return {"success": False, "error": f"Target not found: {target}"}
    result = actions.click(location["cx"], location["cy"])
    result["location"] = location
    return result


def double_click_target(target: str, task: str, img_path: str, app_name: str, runtime) -> dict:
    location = _locate(
        target, task=task, img_path=img_path, app_name=app_name, runtime=runtime,
    )
    if not location:
        return {"success": False, "error": f"Target not found: {target}"}
    result = actions.double_click(location["cx"], location["cy"])
    result["location"] = location
    return result


def right_click_target(target: str, task: str, img_path: str, app_name: str, runtime) -> dict:
    location = _locate(
        target, task=task, img_path=img_path, app_name=app_name, runtime=runtime,
    )
    if not location:
        return {"success": False, "error": f"Target not found: {target}"}
    result = actions.right_click(location["cx"], location["cy"])
    result["location"] = location
    return result


def drag_target(
    target: str,
    target_end: str,
    task: str,
    img_path: str,
    app_name: str,
    runtime,
) -> dict:
    start = _locate(
        f"Find START: {target}",
        task=task,
        img_path=img_path,
        app_name=app_name,
        runtime=runtime,
    )
    if not start:
        return {"success": False, "error": f"Start not found: {target}"}
    end = _locate(
        f"Find END: {target_end}",
        task=task,
        img_path=img_path,
        app_name=app_name,
        runtime=runtime,
    )
    if not end:
        return {"success": False, "error": f"End not found: {target_end}"}
    return actions.drag(start["cx"], start["cy"], end["cx"], end["cy"])


def action_done(reasoning: str = "") -> dict:
    return {"success": True, "done": True, "reasoning": reasoning}


def action_fail(reasoning: str = "") -> dict:
    return {
        "success": False,
        "done": True,
        "infeasible": True,
        "reasoning": reasoning,
    }


def set_macos_save_path(path: str) -> dict:
    """Populate an open native Save panel without confirming the save."""
    from gui_harness.action.input import get_target

    if get_target().platform != "darwin":
        return {
            "success": False,
            "error": "set_save_path is available only for a local macOS Save panel",
        }
    destination = Path(path).expanduser()
    if not destination.is_absolute():
        return {"success": False, "error": "save path must be absolute"}
    if not destination.parent.is_dir():
        return {
            "success": False,
            "error": f"save directory does not exist: {destination.parent}",
        }

    actions.shortcut("command+shift+g")
    time.sleep(0.8)
    actions.paste_text(str(destination.parent))
    actions.key_press("enter")
    time.sleep(0.8)
    actions.shortcut("command+a")
    actions.paste_text(destination.name)
    return {
        "success": True,
        "path": str(destination),
        "action": "set_save_path",
    }


def build_action_registry(allow_general: bool = False) -> dict:
    """Return every action the planner may select in the current mode."""
    context = {"source": "context"}
    registry = {
        "click": {
            "function": click_target,
            "description": "Click a UI element on screen (we locate it for you)",
            "input": {
                "target": {
                    "source": "llm",
                    "type": str,
                    "description": (
                        "description of element to click; for an unlabeled "
                        "control, include its visible screenshot pixel "
                        "coordinates as (x,y)"
                    ),
                },
                "task": context,
                "img_path": context,
                "app_name": context,
            },
            "output": {"success": bool},
        },
        "double_click": {
            "function": double_click_target,
            "description": "Double-click a UI element on screen",
            "input": {
                "target": {"source": "llm", "type": str, "description": "description of element to double-click"},
                "task": context,
                "img_path": context,
                "app_name": context,
            },
            "output": {"success": bool},
        },
        "right_click": {
            "function": right_click_target,
            "description": "Right-click a UI element on screen",
            "input": {
                "target": {"source": "llm", "type": str, "description": "description of element to right-click"},
                "task": context,
                "img_path": context,
                "app_name": context,
            },
            "output": {"success": bool},
        },
        "drag": {
            "function": drag_target,
            "description": "Drag from one element to another",
            "input": {
                "target": {"source": "llm", "type": str, "description": "description of drag start element"},
                "target_end": {"source": "llm", "type": str, "description": "description of drag end element"},
                "task": context,
                "img_path": context,
                "app_name": context,
            },
            "output": {"success": bool},
        },
        "type": {
            "function": actions.paste_text,
            "description": "Enter exact text through the clipboard, independent of keyboard layout",
            "input": {"text": {"source": "llm", "type": str, "description": "text to type"}},
            "output": {"success": bool},
        },
        "press": {
            "function": actions.key_press,
            "description": "Press a keyboard key (enter, tab, escape, etc.)",
            "input": {"key": {"source": "llm", "type": str, "description": "key to press"}},
            "output": {"success": bool},
        },
        "hotkey": {
            "function": actions.shortcut,
            "description": "Press a keyboard shortcut (e.g., ctrl+s, ctrl+c)",
            "input": {"keys": {"source": "llm", "type": str, "description": "key combination like ctrl+s"}},
            "output": {"success": bool},
        },
        "scroll": {
            "function": actions.scroll,
            "description": "Scroll the page up or down",
            "input": {"direction": {"source": "llm", "type": str, "description": "up or down"}},
            "output": {"success": bool},
        },
        "general": {
            "function": general_action,
            "description": "Execute command-line operations only when GUI interaction cannot do the task",
            "input": {
                "sub_task": {"source": "llm", "type": str, "description": "what to do via command line"},
                "task_context": context,
            },
            "output": {"success": bool, "output": str},
        },
        "done": {
            "function": action_done,
            "description": "Mark the task as fully complete",
            "input": {"reasoning": {"source": "llm", "type": str, "description": "why the task is complete"}},
            "output": {"success": bool},
        },
        "fail": {
            "function": action_fail,
            "description": "Declare the task infeasible and stop with an explicit blocker",
            "input": {"reasoning": {"source": "llm", "type": str, "description": "FAIL/INFEASIBLE, concrete blocker, and required human action"}},
            "output": {"success": bool, "done": bool, "infeasible": bool},
        },
    }
    if not allow_general:
        registry.pop("general")
    from gui_harness.action.input import get_default_name

    if platform.system() == "Darwin" and get_default_name() == "local":
        registry["set_save_path"] = {
            "function": set_macos_save_path,
            "description": (
                "In an already-open native macOS Save panel, set its exact "
                "absolute directory and filename without clicking Save"
            ),
            "input": {
                "path": {
                    "source": "llm",
                    "type": str,
                    "description": "exact absolute output file path requested by the task",
                },
            },
            "output": {"success": bool, "path": str},
        }
    return registry


def dispatch_action(
    plan: dict,
    *,
    img_path: str,
    app_name: str,
    task: str,
    runtime,
    allow_general: bool = False,
) -> dict:
    """Validate, bind context, and execute one selected action."""
    action_name = plan.get("call", plan.get("action", "general"))
    registry = build_action_registry(allow_general=allow_general)
    if action_name not in registry:
        return {
            "success": False,
            "error": f"Action '{action_name}' is not available. Pick one of {sorted(registry)}",
        }

    spec = registry[action_name]
    func = spec["function"]
    args = dict(plan.get("args", {}))
    context = {
        "task": task,
        "img_path": img_path,
        "app_name": app_name,
        "task_context": f"<task>{task}</task>",
    }
    for key, info in spec.get("input", {}).items():
        if key not in args and key in plan:
            args[key] = plan[key]
        if info.get("source") == "context" and key not in args:
            args[key] = context[key]
    if "runtime" in inspect.signature(func).parameters:
        args.setdefault("runtime", runtime)
    valid_params = set(inspect.signature(func).parameters)
    args = {key: value for key, value in args.items() if key in valid_params}

    try:
        return func(**args)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "error_type": exc.__class__.__name__,
            "traceback": traceback.format_exc(),
        }


__all__ = [
    "action_done",
    "action_fail",
    "build_action_registry",
    "dispatch_action",
    "set_macos_save_path",
]
