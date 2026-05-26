"""
GUI step — observe → verify → plan → action.

Design principle:
  The LLM is the decision maker — it decides WHAT to do freely.
  We only enforce HOW for things the LLM can't do well (GUI clicking).

Architecture:
  gui_step(task, feedback)        ← @agentic_function, one step (orchestration)
    1. Observe: screenshot + detect + match + state identification  (Python)
    2. Verify: check previous step result, judge task completion    (LLM leaf)
    3. Plan: decide next action based on verification + state       (LLM leaf)
    4. Action: execute the planned action                           (Python)

  gui_agent(task) in main.py      ← @agentic_function, drives the loop
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import time
import traceback
from typing import Optional

from gui_harness.openprogram_compat import agentic_function, build_action_catalog

from gui_harness.utils import parse_json
from gui_harness.perception import screenshot as _screenshot
from gui_harness.action import input as _input
from gui_harness.action.general_action import general_action
from gui_harness.planning.component_memory import (
    locate_target,
    detect_components,
    match_memory_components,
    identify_state,
    record_transition,
    get_available_transitions,
)


def _artifact_dir() -> str | None:
    path = os.environ.get("GUI_HARNESS_ARTIFACT_DIR")
    if path:
        os.makedirs(path, exist_ok=True)
    return path


def _copy_artifact(src: str | None, name: str) -> str | None:
    if not src or not os.path.exists(src):
        return None
    out_dir = _artifact_dir()
    if not out_dir:
        return None
    dst = os.path.join(out_dir, name)
    try:
        import shutil
        shutil.copy2(src, dst)
        return dst
    except Exception:
        return None
def build_catalog(available: dict) -> str:
    """Format an action registry into a catalog string for the planner prompt.

    Shows only parameters with source="llm" — the args the planner must decide.
    Context-filled and runtime params are hidden.
    """
    lines = []
    for name, spec in available.items():
        description = spec.get("description", "")
        input_spec = spec.get("input", {})
        llm_params = []
        param_details = []
        for param_name, param_info in input_spec.items():
            if param_info.get("source") != "llm":
                continue
            type_obj = param_info.get("type", str)
            type_name = getattr(type_obj, "__name__", None) or str(type_obj)
            llm_params.append(f"{param_name}: {type_name}")
            detail = f"    {param_name}"
            if "description" in param_info:
                detail += f": {param_info['description']}"
            opts = param_info.get("options")
            if opts:
                detail += f" (options: {', '.join(f'\"{o}\"' for o in opts)})"
            param_details.append(detail)
        sig = f"{name}({', '.join(llm_params)})" if llm_params else f"{name}()"
        lines.append(sig)
        if description:
            lines.append(f"    {description}")
        lines.extend(param_details)
        if llm_params:
            example_args = ", ".join(
                f'"{p.split(":")[0].strip()}": "..."' for p in llm_params
            )
            lines.append(f'    call: {{"call": "{name}", "args": {{{example_args}}}}}')
        else:
            lines.append(f'    call: {{"call": "{name}"}}')
        lines.append("")
    return "\n".join(lines)


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


def _action_done(reasoning: str = "") -> dict:
    return {"success": True, "done": True, "reasoning": reasoning}


def _action_fail(reasoning: str = "") -> dict:
    return {"success": True, "done": True, "infeasible": True, "reasoning": reasoning}


def _normalize_plan(plan: dict) -> dict:
    """Accept accidental nested step-shaped JSON and extract the action plan."""
    if not isinstance(plan, dict):
        return {"call": "general", "args": {"sub_task": str(plan)[:200]}}
    inner = plan.get("plan")
    if (
        isinstance(inner, dict)
        and ("call" in inner or "action" in inner or inner.get("done") is True)
        and "call" not in plan
        and "action" not in plan
    ):
        return inner
    return plan


def _build_action_registry(allow_general: bool = False):
    """Build the action function registry for LLM dispatch.

    When allow_general=False, the "general" (command-line) action is omitted,
    forcing the planner to accomplish the task via GUI primitives only.
    Used for benchmarks (OSWorld GIMP etc.) whose evaluators require that
    the change happen inside the target app's live state, not on disk.
    """
    registry = {
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
        "fail": {
            "function": _action_fail,
            "description": "Declare the task infeasible and stop with an explicit FAIL/INFEASIBLE reason",
            "input": {
                "reasoning": {"source": "llm", "type": str, "description": "explicit reason containing FAIL/INFEASIBLE and the blocker"},
            },
            "output": {"success": bool, "done": bool, "infeasible": bool},
        },
    }
    if not allow_general:
        registry.pop("general", None)
    return registry


# ═══════════════════════════════════════════
# 1. Observe — pure Python, no LLM
# ═══════════════════════════════════════════

def _observe(app_name: str) -> dict:
    """Take screenshot, detect components, match memory, identify state.

    Pure Python — no LLM calls. Produces all observation data needed
    by verify_step and plan_next_action.
    """
    t_start = time.time()

    # Screenshot
    img_path = _screenshot.take()
    time.sleep(0.3)

    # Component detection (GPA + OCR)
    t0 = time.time()
    detection = detect_components(img_path)
    icons = detection.get("icons", []) if isinstance(detection, dict) else []
    texts = detection.get("texts", []) if isinstance(detection, dict) else []
    t_detect = round(time.time() - t0, 2)

    # Memory matching (template match against saved components)
    t0 = time.time()
    matched = match_memory_components(app_name, img_path)
    matched_names = {c["name"] for c in matched}
    t_match = round(time.time() - t0, 2)

    # State identification (Jaccard similarity against known states)
    current_state, _ = identify_state(app_name, img_path)

    # Known transitions from current state
    transitions = get_available_transitions(app_name, current_state) if current_state else []

    t_total = round(time.time() - t_start, 2)
    print(
        f"    [observe] {len(icons)} icons, {len(texts)} texts, "
        f"{len(matched)} matched, state={current_state}, "
        f"{len(transitions)} transitions ({t_total}s: detect={t_detect}s, match={t_match}s)",
        file=sys.stderr,
    )

    # Build component info string for LLM
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

    # Build transitions info string for LLM
    transitions_info = ""
    if transitions:
        trans_lines = [
            f"  {t['action']}:{t['target']} -> state {t['to_state']} (used {t['use_count']}x)"
            for t in transitions[:10]
        ]
        transitions_info = "\n<known_transitions>\n" + "\n".join(trans_lines) + "\n</known_transitions>"

    return {
        "img_path": img_path,
        "screenshot_artifact": _copy_artifact(img_path, f"observe_{int(time.time() * 1000)}.png"),
        "icons": icons,
        "texts": texts,
        "matched": matched,
        "matched_names": matched_names,
        "current_state": current_state,
        "transitions": transitions,
        "component_info": component_info,
        "transitions_info": transitions_info,
    }


# ═══════════════════════════════════════════
# 2. Verify — LLM leaf function (one exec)
# ═══════════════════════════════════════════

@agentic_function(
    render_range={"depth": 0, "siblings": 0},
    input={
        "task": {"description": "The overall task being performed"},
        "img_path": {"description": "Path to current screenshot (after previous action)"},
        "component_info": {"description": "Formatted string of detected UI components"},
        "feedback": {"description": "Dict from previous step: goal, action, target, success, error"},
        "runtime": {"hidden": True},
    },
)
def verify_step(
    task: str,
    img_path: str,
    component_info: str,
    feedback: dict,
    runtime=None,
) -> dict:
    """Evaluate whether the previous action achieved its goal."""
    if runtime is None:
        raise ValueError("verify_step() requires a runtime argument")

    feedback_text = f"Previous step goal: {feedback.get('goal', 'unknown')}\n"
    feedback_text += f"Action taken: {feedback.get('action', 'unknown')}"
    if feedback.get("target"):
        feedback_text += f" on '{feedback['target']}'"
    feedback_text += f"\nExecution: {'succeeded' if feedback.get('success') else 'failed'}"
    if feedback.get("error"):
        feedback_text += f"\nError: {feedback['error']}"

    context = (
        f"<task>{task}</task>\n\n"
        f"<previous_step>\n{feedback_text}\n</previous_step>"
        f"{component_info}\n\n"
        "The screenshot was taken AFTER the previous action ran. Compare "
        "the step's stated goal with what is now visible and decide "
        "whether the action achieved it.\n"
        "- step_succeeded=true when the expected change is visible (app "
        "opened, text appeared, button state changed, file listed).\n"
        "- step_succeeded=false when there is no visible change, a wrong "
        "result, or an error message on screen.\n"
        '- For a command-line ("general") action: it runs in the '
        "background and does NOT change the GUI, so the screenshot looks "
        "unchanged — that is NORMAL. Trust Execution=succeeded "
        "(step_succeeded=true); set false only on Execution=failed or an "
        "actual on-screen error.\n"
        "Also maintain a task-level execution checklist for the planner. "
        "This is not a final authority, but it should identify what remains "
        "before the original task can be safely marked done. Do not treat a "
        "menu opening, dialog preview, transient visual change, or local "
        "tool response as enough evidence of final completion unless the "
        "original task goal itself is visibly satisfied in the final app "
        "state.\n"
        "Set ready_to_done=true only when the original task appears fully "
        "satisfied, the app is in a clean final state, and there are no "
        "specific completion risks left. For visual edit tasks, the evidence "
        "must be the final visible result in the main workspace, not merely "
        "that a tool was opened, a preview changed, a checkerboard appeared, "
        "or a dialog reported success. If the visible result could still be "
        "a partial/weak edit, set ready_to_done=false and describe the next "
        "inspection or refinement needed.\n\n"
        "Reply with ONLY this JSON object:\n"
        '{"step_succeeded": true, "observation": "one factual sentence '
        'describing the current screen", '
        '"completion_evidence": "specific visible evidence that the original task is or is not complete", '
        '"remaining_plan": ["short checklist item still needed before done"], '
        '"completion_risks": ["specific reason done may be premature"], '
        '"ready_to_done": false}'
    )

    reply = runtime.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])

    try:
        result = parse_json(reply)
        result.pop("task_completed", None)  # verify no longer decides completion
        result.setdefault("completion_evidence", "")
        result.setdefault("remaining_plan", [])
        result.setdefault("completion_risks", [])
        result.setdefault("ready_to_done", False)
        return result
    except Exception:
        return {
            "step_succeeded": True,
            "observation": reply[:300],
            "completion_evidence": "",
            "remaining_plan": [],
            "completion_risks": ["verify reply could not be parsed; planner should be conservative before done"],
            "ready_to_done": False,
            "parse_error": traceback.format_exc(),
            "raw_reply": reply[:1000],
        }


# ═══════════════════════════════════════════
# 3. Plan — LLM leaf function (one exec)
# ═══════════════════════════════════════════

@agentic_function(
    render_range={"depth": 0, "siblings": 0},
    input={
        "task": {"description": "The overall task being performed"},
        "img_path": {"description": "Path to current screenshot"},
        "component_info": {"description": "Formatted string of detected UI components"},
        "verification_summary": {"description": "What happened in the previous step (or empty)"},
        "transitions_info": {"description": "Known transitions from current UI state (or empty)"},
        "action_catalog": {"description": "Available actions and their parameter schemas"},
        "runtime": {"hidden": True},
    },
)
def plan_next_action(
    task: str,
    img_path: str,
    component_info: str,
    verification_summary: str,
    transitions_info: str,
    action_catalog: str,
    runtime=None,
    allow_general: bool = False,
) -> dict:
    """Decide the next action to take toward completing the task."""
    if runtime is None:
        raise ValueError("plan_next_action() requires a runtime argument")

    parts = [f"<task>{task}</task>"]
    if verification_summary:
        parts.append(f"\n<previous_result>\n{verification_summary}\n</previous_result>")
    parts.append(component_info)
    if transitions_info:
        parts.append(transitions_info)
    parts.append(f"\n== Available Actions ==\n{action_catalog}")
    parts.append(
        "\nPick exactly ONE action from the list above as the next step "
        "toward the task.\n"
        "Guidelines:\n"
        "- Prefer GUI interaction (click, type, hotkey) over command-line "
        '("general").\n'
        "- If <known_transitions> lists a relevant action, prefer it — "
        "it worked before.\n"
        '- If a "general" sub-task already succeeded in a previous step, '
        "do not repeat it; move on or verify its output.\n"
        "- Never generate or paraphrase content from your own knowledge "
        "— all data must come from the screen or actual files.\n"
        "- Do not save, export, overwrite, or rename files unless the task "
        "explicitly asks for that file operation or named output path. For "
        "benchmark/evaluator workflows, a visible completed edit in the app "
        "can be the correct handoff state; avoid opening save/export dialogs "
        "just to prove completion.\n"
        '- Choose "done" ONLY with strong evidence the task is fully '
        "complete; if a command ran but its output is unverified, plan a "
        "verify action instead.\n"
        '- Choose "fail" when the task is genuinely infeasible: the requested '
        "operation is impossible in the target app, requires unavailable "
        "plugins/data/hardware, contradicts itself, or the required option "
        "does not exist. The fail reasoning MUST explicitly include "
        "FAIL/INFEASIBLE and the concrete blocker. Do not use fail just "
        "because an attempt failed; recover first when there is a plausible "
        "path.\n"
        '- Before choosing "done", the app must be in a clean handoff '
        "state: no Save, Save As, Export, Open, confirmation, warning, "
        "or options dialog should be left blocking the main workspace. If "
        "such a dialog is open, either finish it completely and verify it "
        "closed, or cancel/close it before marking the task complete.\n"
        "- If the previous step failed, plan a recovery (retry or an "
        "alternative approach).\n\n"
        "- Treat the verification checklist as the current running plan. "
        "If it lists remaining_plan or completion_risks, choose the next "
        "action that resolves the highest-impact item. Do not choose "
        '"done" while unresolved completion_risks remain unless you can '
        "explain why they are no longer valid from the current screenshot.\n"
        "- Keep planning beyond the immediately successful UI operation: "
        "after opening a dialog, plan to apply it and verify the final main "
        "workspace; after applying an edit, plan to inspect whether the "
        "original task goal is visibly satisfied; after creating or changing "
        "content, plan to check the actual result rather than the fact that "
        "a tool was used.\n\n"
        "Reply with ONLY this JSON for one action:\n"
        '{"call": "<action_name>", "args": { ... }, "goal": "what this '
        'action should achieve, one specific sentence", "reasoning": '
        '"why this is the right next step"}\n'
        "The `goal` is used to verify this action next step — be "
        "specific (\"Type 'Calculator' into the Spotlight field\", not "
        '"Continue the task").'
    )

    base_content = [
        {"type": "text", "text": "\n".join(parts)},
        {"type": "image", "path": img_path},
    ]
    valid = set(_build_action_registry(allow_general=allow_general))

    def _parse(r: str):
        try:
            return _normalize_plan(parse_json(r))
        except Exception:
            rl = (r or "").lower()
            if '"done"' in rl or "task is complete" in rl:
                return {"call": "done", "goal": "task complete", "reasoning": (r or "")[:200]}
            return None

    reply = runtime.exec(content=base_content)
    plan = _parse(reply)
    call = (plan or {}).get("call") or (plan or {}).get("action")

    # The planner picked an action that is not in the registry — a
    # mode-forbidden action (e.g. "general" in GUI-only) or a
    # hallucinated name. Re-prompt ONCE, keeping the screenshot, instead
    # of letting _dispatch hard-fail the step.
    if plan is None or call not in valid:
        bad = call or "(unparseable reply)"
        retry_msg = (
            f'"{bad}" is not an available action. You MUST pick exactly '
            f"one action from this list: {sorted(valid)}. "
            "Reply again with the same JSON format."
        )
        reply = runtime.exec(
            content=base_content + [{"type": "text", "text": retry_msg}]
        )
        plan = _parse(reply)
        call = (plan or {}).get("call") or (plan or {}).get("action")

    if plan is None or call not in valid:
        # Retry exhausted — end the loop cleanly rather than dispatching
        # an unknown action.
        return {"call": "done", "goal": "planner did not pick a valid action",
                "reasoning": str(reply)[:200]}
    return plan


def _normalize_plan(parsed: dict) -> dict:
    """Accept direct action JSON or an accidental gui_step-shaped wrapper."""
    if not isinstance(parsed, dict):
        return {"action": "general", "sub_task": str(parsed)[:200], "goal": str(parsed)[:100]}

    nested = parsed.get("plan")
    if isinstance(nested, dict):
        if parsed.get("done") and "call" not in nested and "action" not in nested:
            return {"call": "done", "goal": "task complete", "reasoning": "planner returned done wrapper"}
        return nested

    if parsed.get("done") and "call" not in parsed and "action" not in parsed:
        return {"call": "done", "goal": "task complete", "reasoning": "planner returned done"}

    return parsed


# ═══════════════════════════════════════════
# 4. Dispatch — pure Python, execute planned action
# ═══════════════════════════════════════════

def _dispatch(plan: dict, img_path: str, app_name: str, task: str, runtime, allow_general: bool = False) -> dict:
    """Execute the planned action. Pure Python dispatch (no LLM except via locate_target)."""
    plan = _normalize_plan(plan)
    action_name = plan.get("call", plan.get("action", "general"))
    registry = _build_action_registry(allow_general=allow_general)

    dispatch_context = {
        "task": task,
        "img_path": img_path,
        "app_name": app_name,
        "task_context": f"<task>{task}</task>",
    }

    try:
        if action_name in registry:
            spec = registry[action_name]
            func = spec["function"]
            args = dict(plan.get("args", {}))
            # Accept flat plan keys for backward compatibility
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
                args["runtime"] = runtime
            valid_params = set(sig.parameters.keys())
            args = {k: v for k, v in args.items() if k in valid_params}
            result = func(**args)
        elif allow_general:
            sub_task = plan.get("sub_task", plan.get("task", plan.get("target", str(plan)[:200])))
            result = general_action(sub_task=sub_task, task_context=f"<task>{task}</task>", runtime=runtime)
        else:
            result = {
                "success": False,
                "error": f"Action '{action_name}' not available in GUI-only mode. "
                         f"Pick a GUI action: {sorted(registry)}",
            }
    except Exception as e:
        result = {
            "success": False,
            "error": str(e),
            "error_type": e.__class__.__name__,
            "traceback": traceback.format_exc(),
        }

    return result


# ═══════════════════════════════════════════
# gui_step — orchestration function (no exec)
# ═══════════════════════════════════════════

@agentic_function(
    render_range={"siblings": -1},
    input={
        "task": {"description": "The overall task being performed"},
        "feedback": {"description": "Structured result from previous step (None for first step)"},
        "app_name": {"description": "App name for component memory lookup"},
        "runtime": {"hidden": True},
    },
)
def gui_step(
    task: str,
    feedback: Optional[dict],
    app_name: str,
    runtime=None,
    allow_general: bool = False,
) -> dict:
    """Execute one step of a GUI task: observe -> verify -> plan -> action.

    Orchestration function — coordinates four phases without calling
    runtime.exec() directly. Each LLM-calling child is a separate
    @agentic_function (verify_step, plan_next_action).

    Flow:
      1. Observe  (Python): screenshot + detect + match + identify_state
      2. Verify   (LLM):    check previous step result + task completion
      3. Plan     (LLM):    decide next action
      4. Action   (Python): dispatch and execute the planned action

    Args:
        task: The overall task description.
        feedback: Result summary from the previous step (None for first step).
        app_name: App name for component memory.
        runtime: LLM runtime instance.

    Returns:
        dict with keys:
          - done (bool): Whether the task is complete (decided by plan, not verify).
          - plan (dict): The planned action {action, args, goal, reasoning}.
          - exec_result (dict): Dispatch result {success, error, ...}.
          - verification (dict|None): Verify result {step_succeeded, observation}.
          - state (str|None): Current UI state ID.
    """
    if runtime is None:
        raise ValueError("gui_step() requires a runtime argument")

    # ── 1. Observe (pure Python) ──
    obs = _observe(app_name)

    # ── 2. Verify previous step (LLM, only if feedback exists) ──
    verification = None
    if feedback:
        verification = verify_step(
            task=task,
            img_path=obs["img_path"],
            component_info=obs["component_info"],
            feedback=feedback,
            runtime=runtime,
        )

        # Record state transition: previous state → current state
        prev_state = feedback.get("prev_state")
        if prev_state and obs["current_state"]:
            record_transition(
                app_name=app_name,
                from_state=prev_state,
                action=feedback.get("action", ""),
                action_target=feedback.get("target", ""),
                to_state=obs["current_state"],
            )

        # NOTE: verify does NOT decide task completion.
        # Plan always runs and makes the final "done" decision.

    # ── 3. Plan next action (LLM) ──
    registry = _build_action_registry(allow_general=allow_general)
    catalog = build_action_catalog(registry)

    verification_summary = ""
    if verification:
        succeeded = "succeeded" if verification.get("step_succeeded") else "failed"
        remaining = verification.get("remaining_plan") or []
        risks = verification.get("completion_risks") or []
        verification_summary = (
            f"Previous step {succeeded}. "
            f"Observation: {verification.get('observation', '')}\n"
            f"Completion evidence: {verification.get('completion_evidence', '')}\n"
            f"Ready to done: {bool(verification.get('ready_to_done'))}\n"
            f"Remaining plan: {json.dumps(remaining, ensure_ascii=False)}\n"
            f"Completion risks: {json.dumps(risks, ensure_ascii=False)}"
        )

    plan = plan_next_action(
        task=task,
        img_path=obs["img_path"],
        component_info=obs["component_info"],
        verification_summary=verification_summary,
        transitions_info=obs["transitions_info"],
        action_catalog=catalog,
        runtime=runtime,
        allow_general=allow_general,
    )

    plan = _normalize_plan(plan)
    action_name = plan.get("call", plan.get("action", "general"))

    # Plan says done or explicitly infeasible?
    if action_name in {"done", "fail"}:
        remaining = (verification or {}).get("remaining_plan") or []
        risks = (verification or {}).get("completion_risks") or []
        done_allowed = (
            bool((verification or {}).get("ready_to_done"))
            and not remaining
            and not risks
        )
        if action_name == "done" and verification and not done_allowed:
            risks = risks or ["verification did not mark the task ready to done"]
            plan = {
                "call": "done",
                "goal": plan.get("goal", ""),
                "reasoning": (
                    "Planner requested done, but verify did not mark the task ready. "
                    f"Risks: {risks}"
                ),
                "blocked_by_completion_verify": True,
            }
            return {
                "done": False,
                "plan": plan,
                "exec_result": {
                    "success": False,
                    "error": "done blocked by completion verification",
                    "completion_risks": risks,
                    "remaining_plan": verification.get("remaining_plan") or [],
                },
                "verification": verification,
                "state": obs["current_state"],
                "img_path": obs["img_path"],
                "screenshot_artifact": obs.get("screenshot_artifact"),
            }
        return {
            "done": True,
            "plan": plan,
            "infeasible": action_name == "fail",
            "verification": verification,
            "state": obs["current_state"],
            "img_path": obs["img_path"],
            "screenshot_artifact": obs.get("screenshot_artifact"),
        }

    # ── 4. Action (pure Python dispatch) ──
    exec_result = _dispatch(plan, obs["img_path"], app_name, task, runtime, allow_general=allow_general)

    return {
        "done": False,
        "plan": plan,
        "exec_result": exec_result,
        "verification": verification,
        "state": obs["current_state"],
        "img_path": obs["img_path"],
        "screenshot_artifact": obs.get("screenshot_artifact"),
    }


# ═══════════════════════════════════════════
# build_step_feedback — pure Python
# ═══════════════════════════════════════════

def build_step_feedback(result: dict) -> dict:
    """Extract key information from a step result for the next iteration.

    Pure Python — no LLM. Produces a structured feedback dict that
    verify_step will receive to evaluate the previous action.
    """
    plan = result.get("plan", {})
    exec_result = result.get("exec_result", {})
    verification = result.get("verification")

    feedback = {
        "goal": plan.get("goal", ""),
        "action": plan.get("call", plan.get("action", "")),
        "target": plan.get("args", {}).get("target", plan.get("target", "")),
        "success": exec_result.get("success", False),
        "error": exec_result.get("error", ""),
        "prev_state": result.get("state"),
    }

    if verification:
        feedback["prev_observation"] = verification.get("observation", "")
        feedback["remaining_plan"] = verification.get("remaining_plan") or []
        feedback["completion_risks"] = verification.get("completion_risks") or []
        feedback["ready_to_done"] = bool(verification.get("ready_to_done"))

    return feedback


# ═══════════════════════════════════════════
# conclusion — LLM summarizes the task result
# ═══════════════════════════════════════════

@agentic_function(render_range={"depth": 0, "siblings": 0})
def conclusion(task: str, completed: bool, steps_taken: int, runtime=None) -> dict:
    """Summarize what was accomplished during the GUI task."""
    if runtime is None:
        raise ValueError("conclusion() requires a runtime argument")

    img_path = _screenshot.take()

    status = "COMPLETED" if completed else f"INCOMPLETE (used all {steps_taken} steps)"
    context = (
        f"<task>{task}</task>\n\n"
        f"Status: {status}\nSteps used: {steps_taken}\n\n"
        "Your job: write a `summary` that DIRECTLY ANSWERS the user's <task> "
        "above, using concrete details visible in the current screenshot.\n\n"
        "Rules for `summary` — MUST follow:\n"
        "1. Answer the user's actual question first, with SPECIFIC content "
        "from the screen. Do NOT just say 'I observed the screen' / 'task "
        "completed as requested' / 'no modifications were made'. Those are "
        "empty and will be rejected.\n"
        "2. Examples of the required style:\n"
        "   - task='what is on the screen' → summary must name the app, "
        "window title, visible UI elements, text content. e.g. 'Screen "
        "shows Chrome with Baidu Tieba open; top menu has New chat / "
        "Functions / Skills tabs; main pane lists 5 threads, the first is "
        "...'\n"
        "   - task='open app X' → summary must say 'Opened X; current view "
        "shows Y (specific elements)'.\n"
        "   - task='search Y in X' → summary must say 'Searched Y in X; "
        "found N results; first result is ...'.\n"
        "3. After answering, you may add 1 short clause about the actions "
        "taken. But the answer to the user's question comes FIRST and "
        "dominates the summary.\n"
        "4. If the task was a pure observation ('look', 'check', 'see'), "
        "then the summary IS the observation — describe what is on screen "
        "in concrete detail. Never write 'observed the screen as "
        "requested' without saying WHAT was observed.\n\n"
        "Reply with ONLY this JSON object:\n"
        '{"summary": "<concrete answer to the user\'s task, grounded in '
        'the screenshot>", "success": true, "issues": "any problems '
        'encountered, or null"}'
    )

    reply = runtime.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])

    try:
        return parse_json(reply)
    except Exception:
        return {
            "summary": reply[:500],
            "success": completed,
            "issues": None,
            "parse_error": traceback.format_exc(),
            "raw_reply": reply[:1000],
        }


# ═══════════════════════════════════════════
# Workflow recording
# ═══════════════════════════════════════════

def save_workflow_record(result: dict, app_name: str):
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


# ═══════════════════════════════════════════
# Backward-compatible wrapper (for benchmarks)
# ═══════════════════════════════════════════

def execute_task(
    task: str,
    runtime=None,
    max_steps: int = 30,
    app_name: str = "desktop",
    work_dir: Optional[str] = None,
    allow_general: bool = False,
) -> dict:
    """Execute a GUI task. Thin wrapper around gui_agent for backward compatibility.

    Prefer using gui_agent() directly for new code — configure the runtime's
    work_dir on the runtime before calling.

    If work_dir is omitted, a fresh tempdir is created and set on the runtime.
    """
    import os, tempfile
    from gui_harness.main import gui_agent
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix="gui_harness_")
    work_dir = os.path.abspath(os.path.expanduser(work_dir))
    os.makedirs(work_dir, exist_ok=True)
    if runtime is not None and hasattr(runtime, "set_workdir"):
        runtime.set_workdir(work_dir)
    return gui_agent(task=task, max_steps=max_steps, app_name=app_name, runtime=runtime, allow_general=allow_general)
