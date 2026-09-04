"""Capability selection and bounded execution for the GUI Agent root loop."""

from __future__ import annotations

import importlib.util
import json
import platform
import traceback
from typing import Any

from openprogram.agentic_programming import llm

from gui_harness.adapters.vm_adapter import target_session
from gui_harness.adapters.mac_window import WindowUnavailable, window_inventory, window_session, window_support
from gui_harness.openprogram_compat import agentic_function
from gui_harness.utils import parse_json


CAPABILITIES = ("computer_use", "browser_use", "vm_use")
TERMINAL_STATUSES = ("succeeded", "infeasible", "failed")


def gui_step(**kwargs):
    """Load optional desktop perception only when a screen step is requested."""
    from gui_harness.tasks.execute_task import gui_step as run_step

    return run_step(**kwargs)


def capability_status(*, vm_url: str = "", browser_backend: str = "") -> dict:
    """Return the availability information used by the next model decision."""
    browser_available = True
    page_count = 0
    missing = [name for name in ("cv2", "ultralytics") if importlib.util.find_spec(name) is None]
    try:
        from openprogram.agent import surface_context

        context = surface_context.current() or {}
        page_count = len(context.get("surfaces") or [])
    except Exception:
        browser_available = False
    desktop_status = {
        "available": not missing, "target": "local desktop", "missing_dependencies": missing,
    }
    if platform.system() == "Darwin":
        desktop_status = {**window_support(), "target": "background application window"}
        desktop_status["background_windows"] = window_inventory() if desktop_status["available"] else []
    return {
        "computer_use": {
            **desktop_status,
        },
        "browser_use": {
            "available": browser_available,
            "open_pages": page_count,
            "can_open_page": browser_available,
            "backend": browser_backend or "runtime",
        },
        "vm_use": {
            "available": bool(str(vm_url or "").strip()) and not missing,
            "target": "configured VM" if str(vm_url or "").strip() else "none",
            "missing_dependencies": missing,
        },
    }


@agentic_function(
    as_tool=False,
    input={
        "task": {"description": "Overall GUI task"},
        "history": {"description": "Complete prior capability call inputs and outputs"},
        "availability": {"description": "Current computer, browser, and VM availability"},
        "preferred_capability": {"description": "Optional compatibility hint"},
        "timeout_s": {"hidden": True},
    },
)
def plan_next_capability(
    task: str,
    history: list[dict],
    availability: dict,
    preferred_capability: str = "",
    timeout_s: float | None = None,
) -> dict:
    """Choose one capability call or submit a terminal decision."""
    prompt = f"""You control one GUI task through bounded capability functions.

Task:
{task}

Current capability availability:
{json.dumps(availability, ensure_ascii=False, default=str)}

Complete capability call history in execution order:
{json.dumps(history, ensure_ascii=False, default=str)}

Optional compatibility hint: {preferred_capability or "none"}

Choose exactly one next call:
- computer_use: perform one observe/verify/plan/action step on the local desktop.
- browser_use: complete one bounded sub-task in an exact background browser Page.
- vm_use: perform one observe/verify/plan/action step in the configured VM.
- terminal: propose succeeded, infeasible, or failed for the overall task.

The hint is not a fixed route. You may switch capabilities between iterations.
Do not propose succeeded without a recent capability result that explicitly
verified completion. For infeasible, provide blocker and handoff_instruction.

Reply with only JSON:
{{"call":"computer_use|browser_use|vm_use|terminal","args":{{...}}}}

On macOS, computer_use operates a background application window; use `app_name`
and `window_id` from background_windows. It cannot activate apps or use global input.
Select another window explicitly when the task needs it. Unsupported background
actions require a concrete handoff rather than foreground fallback.
Capability args use a concise `task` sub-task. browser_use may additionally use
`url`; terminal uses `status`, `reason`, and when infeasible, `blocker` plus
`handoff_instruction`.
"""
    reply = llm(prompt, timeout_s=timeout_s)
    try:
        decision = parse_json(reply)
    except Exception:
        return {
            "call": "terminal",
            "args": {
                "status": "failed",
                "reason": "capability planner returned invalid JSON",
                "reason_code": "planner_invalid_json",
            },
        }
    if not isinstance(decision, dict):
        return {
            "call": "terminal",
            "args": {
                "status": "failed",
                "reason": "capability planner returned a non-object",
                "reason_code": "planner_invalid_result",
            },
        }
    call = str(decision.get("call") or "")
    args = decision.get("args")
    if call not in {*CAPABILITIES, "terminal"} or not isinstance(args, dict):
        return {
            "call": "terminal",
            "args": {
                "status": "failed",
                "reason": f"capability planner selected unavailable call: {call}",
                "reason_code": "planner_invalid_capability",
            },
        }
    return {"call": call, "args": args}


def _step_result(step: dict, previous_feedback: dict | None) -> dict:
    terminal_status = str(step.get("terminal_status") or "")
    if step.get("done"):
        status = terminal_status or (
            "infeasible" if step.get("infeasible") else "succeeded"
        )
        success = status == "succeeded"
        next_feedback = None
    else:
        from gui_harness.tasks.execute_task import build_step_feedback

        status = "applied"
        success = bool((step.get("exec_result") or {}).get("success"))
        next_feedback = build_step_feedback(
            step, previous_feedback=previous_feedback,
        )
    return {
        "status": status,
        "success": success,
        "reason_code": str(step.get("reason_code") or status),
        "blocker": str(step.get("blocker") or ""),
        "handoff_instruction": str(step.get("handoff_instruction") or ""),
        "completion_verified": bool(
            step.get("done") and status == "succeeded"
        ),
        "next_feedback": next_feedback,
        "step": step,
    }


@agentic_function(as_tool=False)
def computer_use(
    task: str,
    app_name: str = "desktop",
    feedback: dict | None = None,
    runtime=None,
    allow_general: bool = False,
    max_seconds: float | None = None,
    window_id: int | None = None,
) -> dict:
    """Perform one bounded Harness step on the local desktop."""
    if runtime is None:
        raise ValueError("computer_use requires a runtime argument")
    if platform.system() == "Darwin" or window_id is not None:
        previous = (feedback or {}).get("window_target")
        if previous and (window_id is not None and window_id != previous.get("window_id")):
            previous = None
            feedback = None
        if previous and window_id is None:
            window_id = previous.get("window_id")
            app_name = previous.get("bundle_id") or app_name
        try:
            with window_session(app_name, window_id, previous) as window:
                step = gui_step(task=task, feedback=feedback, app_name=app_name,
                                runtime=runtime, allow_general=False, timeout_s=max_seconds)
                result = _step_result(step, feedback)
                result["target"] = window.identity
                if result.get("next_feedback") is not None:
                    result["next_feedback"]["window_target"] = window.identity
                return result
        except WindowUnavailable as exc:
            return {"status": "infeasible", "success": False, "completion_verified": False,
                    "reason_code": "background_window_unavailable", "blocker": str(exc),
                    "summary": str(exc), "handoff_instruction": "Check the target window and macOS permissions; perform unsupported actions manually. No foreground fallback was attempted."}
    with target_session():
        step = gui_step(
            task=task,
            feedback=feedback,
            app_name=app_name,
            runtime=runtime,
            allow_general=allow_general,
            timeout_s=max_seconds,
        )
    return _step_result(step, feedback)


@agentic_function(as_tool=False)
def browser_use(
    task: str,
    url: str = "",
    backend: str = "",
    max_steps: int = 8,
    max_seconds: float | None = None,
    runtime=None,
) -> dict:
    """Run one bounded browser sub-task without foregrounding its window."""
    if runtime is None:
        raise ValueError("browser_use requires a runtime argument")
    if backend:
        from openprogram.programs.workflow.browser import _run_browser_task_commands

        result = _run_browser_task_commands(
            task=task,
            backend=backend,
            max_steps=max_steps,
            max_seconds=max_seconds,
            runtime=runtime,
        )
    else:
        from openprogram.programs.workflow.browser import _run_browser_task

        result = _run_browser_task(
            task=task,
            url=url,
            max_steps=max_steps,
            max_seconds=max_seconds if max_seconds is not None else 300,
            runtime=runtime,
        )
    normalized = dict(result) if isinstance(result, dict) else {
        "status": "failed", "summary": str(result),
    }
    normalized["success"] = normalized.get("status") == "succeeded"
    normalized["completion_verified"] = (
        normalized.get("status") == "succeeded"
    )
    return normalized


@agentic_function(as_tool=False)
def vm_use(
    task: str,
    vm_url: str,
    app_name: str = "desktop",
    feedback: dict | None = None,
    runtime=None,
    allow_general: bool = False,
    max_seconds: float | None = None,
) -> dict:
    """Perform one bounded Harness step through an OSWorld-compatible VM API."""
    if runtime is None:
        raise ValueError("vm_use requires a runtime argument")
    if not str(vm_url or "").strip():
        return {
            "status": "failed",
            "success": False,
            "reason_code": "vm_unconfigured",
            "summary": "No VM endpoint is configured.",
        }
    try:
        with target_session(vm_url):
            step = gui_step(
                task=task,
                feedback=feedback,
                app_name=app_name,
                runtime=runtime,
                allow_general=allow_general,
                timeout_s=max_seconds,
            )
    except Exception as exc:
        return {
            "status": "failed",
            "success": False,
            "reason_code": "vm_operation_failed",
            "summary": str(exc),
            "error_type": exc.__class__.__name__,
            "traceback": traceback.format_exc(),
        }
    return _step_result(step, feedback)


def validate_terminal_decision(decision: dict, history: list[dict]) -> dict:
    """Accept only terminal decisions supported by the available evidence."""
    args = decision.get("args") if isinstance(decision, dict) else {}
    args = args if isinstance(args, dict) else {}
    status = str(args.get("status") or "").strip().lower()
    reason = str(args.get("reason") or "").strip()
    if status not in TERMINAL_STATUSES:
        return {"accepted": False, "reason": "unknown terminal status"}
    if status == "succeeded":
        latest = next(
            (
                entry.get("output")
                for entry in reversed(history)
                if entry.get("type") == "capability_call"
            ),
            None,
        )
        if not isinstance(latest, dict) or not latest.get("completion_verified"):
            return {
                "accepted": False,
                "reason": "succeeded requires a verified capability result",
            }
    elif status == "infeasible":
        if not str(args.get("blocker") or "").strip():
            return {"accepted": False, "reason": "infeasible requires blocker"}
        if not str(args.get("handoff_instruction") or "").strip():
            return {
                "accepted": False,
                "reason": "infeasible requires handoff_instruction",
            }
    elif not reason:
        return {"accepted": False, "reason": "failed requires a reason"}
    return {"accepted": True, "status": status, **args}


def call_capability(
    name: str,
    args: dict[str, Any],
    *,
    runtime,
    app_name: str,
    allow_general: bool,
    browser_backend: str,
    vm_url: str,
    feedback: dict | None,
    max_seconds: float | None,
) -> dict:
    """Bind controller-owned context and execute one selected capability."""
    task = str(args.get("task") or "").strip()
    if not task:
        return {
            "status": "failed",
            "success": False,
            "reason_code": "capability_task_missing",
            "summary": f"{name} requires a task",
        }
    if name == "computer_use":
        return computer_use(
            task=task,
            app_name=str(args.get("app_name") or app_name),
            window_id=args.get("window_id"),
            feedback=feedback,
            runtime=runtime,
            allow_general=allow_general,
            max_seconds=max_seconds,
        )
    if name == "browser_use":
        return browser_use(
            task=task,
            url=str(args.get("url") or ""),
            backend=browser_backend,
            max_seconds=max_seconds,
            runtime=runtime,
        )
    if name == "vm_use":
        return vm_use(
            task=task,
            vm_url=vm_url,
            app_name=app_name,
            feedback=feedback,
            runtime=runtime,
            allow_general=allow_general,
            max_seconds=max_seconds,
        )
    raise ValueError(f"Unknown GUI capability: {name}")


__all__ = [
    "CAPABILITIES",
    "browser_use",
    "call_capability",
    "capability_status",
    "computer_use",
    "plan_next_capability",
    "validate_terminal_decision",
    "vm_use",
]
