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

import json
import os
import traceback
from typing import Optional

from openprogram.agentic_programming import llm

from gui_harness.openprogram_compat import agentic_function, build_action_catalog

from gui_harness.utils import parse_json
from gui_harness.perception.observe import observe_screen
from gui_harness.action.dispatch import (
    action_fail as _action_fail,
    build_action_registry as _build_action_registry,
    dispatch_action,
)
from gui_harness.planning.component_memory import (
    record_transition,
)


# ═══════════════════════════════════════════
# 2. Verify — LLM leaf function (one exec)
# ═══════════════════════════════════════════

@agentic_function(
    render_range={"callers": 0},
    input={
        "task": {"description": "The overall task being performed"},
        "img_path": {"description": "Path to current screenshot (after previous action)"},
        "component_info": {"description": "Formatted string of detected UI components"},
        "feedback": {"description": "Dict from previous step: goal, action, target, success, error"},
    },
)
def verify_step(
    task: str,
    img_path: str,
    component_info: str,
    feedback: dict,
) -> dict:
    """Evaluate whether the previous action achieved its goal."""
    initial_observation = bool(feedback.get("initial_observation"))
    if initial_observation:
        feedback_text = (
            "No action has run. Evaluate whether the current screen already "
            "satisfies the task, including read-only inspect/describe tasks."
        )
    else:
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
        "For an initial observation, decide whether the current screen itself "
        "already satisfies the task. Otherwise, the screenshot was taken AFTER "
        "the previous action; compare the stated goal with what is visible.\n"
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

    reply = llm([
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
    input={
        "task": {"description": "The overall task being performed"},
        "img_path": {"description": "Path to current screenshot"},
        "component_info": {"description": "Formatted string of detected UI components"},
        "verification_summary": {"description": "What happened in the previous step (or empty)"},
        "transitions_info": {"description": "Known transitions from current UI state (or empty)"},
        "action_catalog": {"description": "Available actions and their parameter schemas"},
    },
)
def plan_next_action(
    task: str,
    img_path: str,
    component_info: str,
    verification_summary: str,
    transitions_info: str,
    action_catalog: str,
    allow_general: bool = False,
) -> dict:
    """Decide the next action to take toward completing the task."""
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
        "- When the active app accepts keyboard input, prefer type/press/hotkey "
        "over clicking an on-screen keypad.\n"
        "- For click targets, use the shortest exact visible label first. Do "
        "not replace a failed exact label with a longer positional description; "
        "choose a keyboard path or another control instead.\n"
        "- For a clearly visible unlabeled control or blank editing surface, "
        "include its screenshot pixel coordinates as `(x,y)` in the click "
        "target. Use the `<screen_coordinates>` bounds; do not invent "
        "coordinates when the control is not visible.\n"
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
        '- Choose "fail" when the task is genuinely infeasible or you cannot '
        "finish it and a human must act: the requested operation is "
        "impossible in the target app, requires unavailable "
        "plugins/data/hardware, contradicts itself, or the required option "
        "does not exist; you cannot do it and a human must operate "
        "(login, a physical action, or missing permission); or another try "
        "still has no GUI path. A fail action MUST provide both the concrete "
        "`blocker` and a specific `handoff_instruction` for a human. "
        "Do not use fail just because an attempt failed; recover first when "
        "there is a plausible path.\n"
        '- Before choosing "done", the app must be in a clean handoff '
        "state: no Save, Save As, Export, Open, confirmation, warning, "
        "or options dialog should be left blocking the main workspace. If "
        "such a dialog is open, either finish it completely and verify it "
        "closed, or cancel/close it before marking the task complete.\n"
        "- If the previous step failed, plan a recovery (retry or an "
        "alternative approach).\n\n"
        "- A shortcut being dispatched is not proof that the UI accepted it. "
        "If verification shows no expected change, treat that shortcut as "
        "failed. Do not choose the same failed action fingerprint more than "
        "twice unless the visible focus or dialog state has materially changed.\n"
        "- In a macOS Open/Save panel, if Shift-Command-G does not visibly "
        "open Go to Folder after one attempt, use the panel's visible location "
        "or disclosure controls instead of repeating the shortcut.\n\n"
        "- When a macOS Save panel is already open and the task names an "
        "absolute output file, use `set_save_path` with that exact full path. "
        "It sets both Where and Save As but does not save. Verify the exact "
        "filename and directory basename on the next screenshot, then use "
        "`press` with key `enter` to activate the native default Save button. "
        "Do not coordinate-click Save after `set_save_path`. A truncated or "
        "shared-prefix Where label is not proof of the requested directory.\n\n"
        "- If `<frontmost_app>` names the target app but no target window is "
        "visible, open the Window menu once and select one specific existing "
        "window title. Do not create additional windows. If selecting that "
        "title or Bring All to Front still leaves every target window outside "
        "the observed desktop/Space, choose `fail`: state that the window is "
        "outside the observable Space and the human must move or unminimize it.\n\n"
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
    registry = _build_action_registry(allow_general=allow_general)
    valid = set(registry)

    def _parse(r: str):
        try:
            return _normalize_plan(parse_json(r))
        except Exception:
            return None

    def _validation_error(candidate: dict | None) -> str:
        call_name = (candidate or {}).get("call") or (candidate or {}).get("action")
        if candidate is None or call_name not in valid:
            return f"unavailable action: {call_name or '(unparseable reply)'}"
        args = (candidate or {}).get("args") or {}
        missing = []
        for name, info in registry[call_name].get("input", {}).items():
            if info.get("source") != "llm":
                continue
            value = args.get(name, (candidate or {}).get(name))
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)
        return f"missing required arguments: {', '.join(missing)}" if missing else ""

    reply = llm(base_content)
    plan = _parse(reply)
    validation_error = _validation_error(plan)

    # The planner picked an action that is not in the registry — a
    # mode-forbidden action (e.g. "general" in GUI-only) or a
    # hallucinated name. Re-prompt ONCE, keeping the screenshot, instead
    # of letting _dispatch hard-fail the step.
    if validation_error:
        retry_msg = (
            f"Invalid plan: {validation_error}. You MUST pick exactly one "
            f"action from {sorted(valid)} and provide every argument shown "
            "for that action. Reply again with the same JSON format."
        )
        reply = llm(base_content + [{"type": "text", "text": retry_msg}])
        plan = _parse(reply)
        validation_error = _validation_error(plan)

    if validation_error:
        return {
            "call": "planner_error",
            "goal": "planner must return one valid action",
            "reasoning": str(reply)[:200],
            "reason_code": (
                "planner_invalid_arguments"
                if validation_error.startswith("missing required arguments")
                else "planner_invalid_action"
            ),
        }
    return plan


def _normalize_plan(parsed: object) -> dict:
    """Accept direct action JSON or an accidental gui_step-shaped wrapper."""
    if not isinstance(parsed, dict):
        raise TypeError("planner reply must be a JSON object")

    nested = parsed.get("plan")
    if isinstance(nested, dict):
        if parsed.get("done") is True and "call" not in nested and "action" not in nested:
            return {"call": "done", "goal": "task complete", "reasoning": "planner returned done wrapper"}
        return nested

    if parsed.get("done") is True and "call" not in parsed and "action" not in parsed:
        return {"call": "done", "goal": "task complete", "reasoning": "planner returned done"}

    return parsed


def _action_fingerprint(plan: dict) -> str:
    action = str(plan.get("call", plan.get("action", "")))
    args = plan.get("args", {})
    try:
        encoded = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        encoded = str(args)
    return f"{action}:{encoded}"


# ═══════════════════════════════════════════
# gui_step — orchestration function (no exec)
# ═══════════════════════════════════════════

@agentic_function(
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
    obs = observe_screen(app_name)

    # ── 2. Verify previous step (LLM, only if feedback exists) ──
    verification = None
    if feedback:
        verification = verify_step(
            task=task,
            img_path=obs["img_path"],
            component_info=obs["component_info"],
            feedback=feedback,
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
    recent_actions = (feedback or {}).get("recent_actions") or []
    if recent_actions:
        compact_actions = [
            {
                "action": item.get("fingerprint", ""),
                "success": bool(item.get("success")),
            }
            for item in recent_actions[-8:]
        ]
        verification_summary += (
            "\nRecent bounded action history: "
            + json.dumps(compact_actions, ensure_ascii=False)
            + f"\nConsecutive failures: {(feedback or {}).get('consecutive_failures', 0)}"
        )

    plan = plan_next_action(
        task=task,
        img_path=obs["img_path"],
        component_info=obs["component_info"],
        verification_summary=verification_summary,
        transitions_info=obs["transitions_info"],
        action_catalog=catalog,
        allow_general=allow_general,
    )

    plan = _normalize_plan(plan)
    action_name = plan.get("call", plan.get("action", "general"))

    if action_name == "planner_error":
        return {
            "done": True,
            "terminal_status": "failed",
            "reason_code": plan.get("reason_code", "planner_invalid_action"),
            "plan": plan,
            "verification": verification,
            "state": obs["current_state"],
            "img_path": obs["img_path"],
            "screenshot_artifact": obs.get("screenshot_artifact"),
        }

    # Plan says done or explicitly infeasible?
    if action_name in {"done", "fail"}:
        if action_name == "done" and verification is None:
            verification = verify_step(
                task=task,
                img_path=obs["img_path"],
                component_info=obs["component_info"],
                feedback={
                    "goal": task,
                    "action": "initial_observation",
                    "success": True,
                    "initial_observation": True,
                },
            )
        remaining = (verification or {}).get("remaining_plan") or []
        risks = (verification or {}).get("completion_risks") or []
        done_allowed = (
            (verification or {}).get("ready_to_done") is True
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
            "terminal_status": (
                "infeasible" if action_name == "fail" else "succeeded"
            ),
            "reason_code": (
                "infeasible" if action_name == "fail" else "completed"
            ),
            "handoff_instruction": (
                str((plan.get("args") or {}).get("handoff_instruction") or "")
                if action_name == "fail" else ""
            ),
            "blocker": (
                str((plan.get("args") or {}).get("blocker") or "")
                if action_name == "fail" else ""
            ),
            "plan": plan,
            "infeasible": action_name == "fail",
            "verification": verification,
            "state": obs["current_state"],
            "img_path": obs["img_path"],
            "screenshot_artifact": obs.get("screenshot_artifact"),
        }

    # ── 4. Action (pure Python dispatch) ──
    recent = (feedback or {}).get("recent_actions") or []
    fingerprint = _action_fingerprint(plan)
    failed_same_action = sum(
        item.get("fingerprint") == fingerprint and not item.get("success")
        for item in recent[-8:]
    )
    if failed_same_action >= 3:
        return {
            "done": True,
            "terminal_status": "failed",
            "reason_code": "repeated_action",
            "plan": plan,
            "exec_result": {
                "success": False,
                "error": "same failed action selected four times",
            },
            "verification": verification,
            "state": obs["current_state"],
            "img_path": obs["img_path"],
            "screenshot_artifact": obs.get("screenshot_artifact"),
        }
    exec_result = dispatch_action(
        plan,
        img_path=obs["img_path"],
        app_name=app_name,
        task=task,
        runtime=runtime,
        allow_general=allow_general,
    )

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

def build_step_feedback(
    result: dict,
    previous_feedback: Optional[dict] = None,
) -> dict:
    """Extract key information from a step result for the next iteration.

    Pure Python — no LLM. Produces a structured feedback dict that
    verify_step will receive to evaluate the previous action.
    """
    plan = result.get("plan", {})
    exec_result = result.get("exec_result", {})
    verification = result.get("verification")
    success = bool(exec_result.get("success"))
    recent_actions = list((previous_feedback or {}).get("recent_actions") or [])[-7:]
    if verification and recent_actions:
        # This step's screenshot verifies the action represented by the last
        # previous-history item. Reconcile the mechanical dispatch result with
        # the authoritative visible result before the planner sees history.
        previous_action = dict(recent_actions[-1])
        previous_action["success"] = bool(verification.get("step_succeeded"))
        previous_action["verified"] = True
        recent_actions[-1] = previous_action
    recent_actions.append({
        "fingerprint": _action_fingerprint(plan),
        "success": success,
        "state": result.get("state"),
    })
    previous_failures = int(
        (previous_feedback or {}).get("consecutive_failures") or 0
    )

    feedback = {
        "goal": plan.get("goal", ""),
        "action": plan.get("call", plan.get("action", "")),
        "target": plan.get("args", {}).get("target", plan.get("target", "")),
        "success": success,
        "error": exec_result.get("error", ""),
        "prev_state": result.get("state"),
        "recent_actions": recent_actions,
        "consecutive_failures": previous_failures + 1 if not success else 0,
    }

    if verification:
        feedback["prev_observation"] = verification.get("observation", "")
        feedback["remaining_plan"] = verification.get("remaining_plan") or []
        feedback["completion_risks"] = verification.get("completion_risks") or []
        feedback["ready_to_done"] = bool(verification.get("ready_to_done"))

    return feedback


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
