#!/usr/bin/env python3
"""
GUI Agent — main entry point.

Usage:
    python3 -m gui_harness --work-dir /tmp/gui-firefox "Open Firefox and go to google.com"
    python3 gui_harness/main.py --work-dir /tmp/gui-wechat "Send hello to John in WeChat"
    python3 gui_harness/main.py --work-dir /tmp/gui-vm --vm http://172.16.105.128:5000 "Click the OK button"
"""

import argparse
import sys
import os
import time

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui_harness.constants import GUI_SYSTEM_PROMPT
from gui_harness.openprogram_compat import agentic_function, create_runtime


def _default_runtime_retries() -> int:
    try:
        return max(1, int(os.environ.get("GUI_HARNESS_OPENPROGRAM_MAX_RETRIES", "5")))
    except ValueError:
        return 5


# ═══════════════════════════════════════════
# gui_agent — top-level @agentic_function with loop
# ═══════════════════════════════════════════

@agentic_function(
    as_tool=True,
    toolset=("harness",),
    system=GUI_SYSTEM_PROMPT,
    input={
        "task": {
            "source": "llm",
            "description": "What to do (natural language)",
            "placeholder": "e.g. Open Firefox and go to google.com",
            "multiline": True,
        },
        "max_steps": {
            "description": "Maximum number of actions before giving up",
            "hidden": True,
        },
        "app_name": {
            "description": "App name for component memory",
            "placeholder": "e.g. firefox, libreoffice_calc, desktop",
            "hidden": True,
        },
        "allow_general": {"hidden": True},
        "max_seconds": {"hidden": True},
        "browser_backend": {"hidden": True},
        "vm_url": {"hidden": True},
        "preferred_capability": {"hidden": True},
        "runtime": {"hidden": True},
    },
)
def gui_agent(
    task: str,
    max_steps: int | None = None,
    app_name: str = "desktop",
    runtime=None,
    allow_general: bool = False,
    max_seconds: float | None = None,
    browser_backend: str = "",
    vm_url: str = "",
    preferred_capability: str = "",
) -> dict:
    """Complete a GUI task through model-selected bounded capabilities.

    Each iteration sees the complete prior capability history, then selects
    computer_use, browser_use, vm_use, or a terminal decision. ``max_steps``
    and ``max_seconds`` are safety boundaries, not normal completion rules.

    The runtime's working directory must be configured before calling —
    relative paths resolve against it.

    Args:
        task: what to do, in natural language.
        max_steps: maximum number of actions (default: 150). None uses
            150; 0 or a negative value means no cap.
        app_name: app name for component memory (default: "desktop").

    Returns a dict with task, success, steps_taken, total_time, history.
    """
    if runtime is None:
        raise ValueError("gui_agent() requires a runtime argument")
    if max_steps is None:
        max_steps = 150
    else:
        n = int(max_steps)
        max_steps = n if n > 0 else None

    from gui_harness.tasks import capability_loop
    from gui_harness.tasks.result import conclusion, save_workflow_record
    task_start = time.time()
    deadline = (
        task_start + float(max_seconds)
        if max_seconds is not None and float(max_seconds) > 0
        else None
    )

    history: list[dict] = []
    feedback_by_capability: dict[str, dict | None] = {
        "computer_use": None,
        "vm_use": None,
    }
    status = "running"
    reason_code = ""
    blocker = ""
    handoff_instruction = ""
    terminal_reason = ""
    iterations = 0
    capability_calls = 0
    decision_limit = max_steps * 3 + 3 if max_steps is not None else None

    while status == "running":
        if decision_limit is not None and iterations >= decision_limit:
            status = "failed"
            reason_code = "decision_limit"
            terminal_reason = "GUI Agent reached its Runtime decision limit."
            break
        if deadline is not None and time.time() >= deadline:
            status = "failed"
            reason_code = "timeout"
            terminal_reason = "GUI Agent exceeded its Runtime time limit."
            break
        iterations += 1
        print(f"  [decision {iterations}] ...", file=sys.stderr)
        availability = capability_loop.capability_status(
            vm_url=vm_url,
            browser_backend=browser_backend,
        )
        try:
            remaining_seconds = (
                max(0.001, deadline - time.time())
                if deadline is not None else None
            )
            decision = capability_loop.plan_next_capability(
                task=task,
                history=history,
                availability=availability,
                preferred_capability=preferred_capability,
                timeout_s=remaining_seconds,
            )
        except Exception as exc:
            decision = {
                "call": "terminal",
                "args": {
                    "status": "failed",
                    "reason": str(exc),
                    "reason_code": "planner_error",
                },
            }
        if deadline is not None and time.time() >= deadline:
            status = "failed"
            reason_code = "timeout"
            terminal_reason = "GUI Agent exceeded its Runtime time limit."
            break
        call = str(decision.get("call") or "")
        args = decision.get("args")
        args = dict(args) if isinstance(args, dict) else {}
        if call == "terminal":
            terminal = capability_loop.validate_terminal_decision(
                decision, history,
            )
            if not terminal.get("accepted"):
                history.append({
                    "type": "terminal_rejected",
                    "decision": decision,
                    "reason": terminal.get("reason", "unsupported terminal"),
                })
                continue
            status = str(terminal["status"])
            reason_code = str(
                terminal.get("reason_code")
                or ("completed" if status == "succeeded" else status)
            )
            terminal_reason = str(terminal.get("reason") or "")
            blocker = str(terminal.get("blocker") or "")
            handoff_instruction = str(
                terminal.get("handoff_instruction") or ""
            )
            break
        if call not in capability_loop.CAPABILITIES:
            history.append({
                "type": "terminal_rejected",
                "decision": decision,
                "reason": f"unknown capability: {call}",
            })
            continue
        if max_steps is not None and capability_calls >= max_steps:
            status = "failed"
            reason_code = "safety_step_limit"
            terminal_reason = "GUI Agent reached its Runtime action limit."
            break
        if not availability.get(call, {}).get("available"):
            result = {
                "status": "failed",
                "success": False,
                "reason_code": "capability_unavailable",
                "summary": f"{call} is not currently available",
            }
        else:
            remaining_seconds = (
                max(1.0, deadline - time.time()) if deadline is not None else None
            )
            try:
                result = capability_loop.call_capability(
                    call,
                    args,
                    runtime=runtime,
                    app_name=app_name,
                    allow_general=allow_general,
                    browser_backend=browser_backend,
                    vm_url=vm_url,
                    feedback=feedback_by_capability.get(call),
                    max_seconds=remaining_seconds,
                )
            except Exception as exc:
                result = {
                    "status": "failed",
                    "success": False,
                    "reason_code": "capability_operation_failed",
                    "summary": str(exc),
                    "error_type": exc.__class__.__name__,
                }
        capability_calls += 1
        history.append({
            "type": "capability_call",
            "step": capability_calls,
            "capability": call,
            "input": args,
            "output": result,
        })
        if call in feedback_by_capability:
            feedback_by_capability[call] = result.get("next_feedback")
        if hasattr(runtime, "compact"):
            runtime.compact(threshold_tokens=200_000)

    # ── Conclusion: LLM summarizes the result ──
    print("  [conclusion] ...", file=sys.stderr)
    if deadline is not None and time.time() >= deadline:
        summary = {
            "summary": handoff_instruction or terminal_reason or "GUI Agent timed out.",
            "success": status == "succeeded",
            "issues": "Conclusion skipped because the Runtime deadline expired.",
        }
    else:
        try:
            remaining_seconds = (
                max(0.001, deadline - time.time())
                if deadline is not None else None
            )
            summary = conclusion(
                task=task,
                completed=status == "succeeded",
                steps_taken=capability_calls,
                infeasible=status == "infeasible",
                status=status,
                handoff_instruction=handoff_instruction,
                img_path=_last_image_path(history),
                timeout_s=remaining_seconds,
                history=history,
            )
            print(f"  [conclusion] {summary.get('summary', '')[:300]}", file=sys.stderr)
        except Exception as e:
            print(f"  [conclusion] ERROR: {e}", file=sys.stderr)
            if status == "succeeded":
                status = "failed"
                reason_code = "conclusion_error"
            summary = {
                "summary": handoff_instruction or terminal_reason or str(e),
                "success": status == "succeeded",
                "issues": None,
            }
    if status == "infeasible" and handoff_instruction:
        summary["summary"] = handoff_instruction

    # ── Teardown ──
    total_time = round(time.time() - task_start, 2)
    final = {
        "task": task,
        "status": status,
        "success": status == "succeeded",
        "reason_code": reason_code,
        "blocker": blocker,
        "infeasible_declared": status == "infeasible",
        "handoff_instruction": handoff_instruction,
        "summary": summary.get("summary", ""),
        "issues": summary.get("issues"),
        "steps_taken": capability_calls,
        "iterations": iterations,
        "total_time": total_time,
        "history": history,
    }
    save_workflow_record(final, app_name)

    return final


def _last_image_path(history: list[dict]) -> str:
    for entry in reversed(history):
        output = entry.get("output")
        if not isinstance(output, dict):
            continue
        step = output.get("step")
        if isinstance(step, dict) and step.get("img_path"):
            return str(step["img_path"])
        return ""
    return ""


# ═══════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="GUI Agent — autonomous GUI task execution")
    parser.add_argument("task", help="What to do (natural language)")
    parser.add_argument("--work-dir", required=True,
                        help="Absolute path for agent file writes (runtime's codex --cd target).")
    parser.add_argument("--vm", help="VM HTTP API URL (for OSWorld)")
    parser.add_argument("--provider", help="Force LLM provider: openai-codex, claude-code, anthropic, openai, gemini-cli, gemini")
    parser.add_argument("--model", help="Override model name")
    parser.add_argument(
        "--runtime-retries",
        type=int,
        default=_default_runtime_retries(),
        help="OpenProgram exec attempts per model call for retryable provider failures.",
    )
    parser.add_argument("--max-steps", type=int, default=150, help="Max actions (default: 150)")
    parser.add_argument("--max-seconds", type=float, help="Runtime safety time limit")
    parser.add_argument("--app", default="desktop", help="App name for memory (default: desktop)")
    parser.add_argument("--no-general", action="store_true",
                        help="Disable command-line ('general') action; force GUI-only interaction.")
    args = parser.parse_args()

    if args.vm:
        print(f"VM capability: {args.vm}")

    # Runtime — delegate auto-detection to openprogram.providers
    kwargs = {}
    if args.model:
        kwargs["model"] = args.model
    kwargs["max_retries"] = max(1, args.runtime_retries)
    runtime = create_runtime(provider=args.provider or "auto", **kwargs)
    work_dir = os.path.abspath(os.path.expanduser(args.work_dir))
    os.makedirs(work_dir, exist_ok=True)
    runtime.set_workdir(work_dir)
    print(f"Runtime: {type(runtime).__name__}")
    print(f"Runtime retries: {max(1, args.runtime_retries)}")
    print(f"Task: {args.task}")
    print(f"Max steps: {args.max_steps}")
    print()

    # Execute
    result = gui_agent(
        task=args.task,
        max_steps=args.max_steps,
        app_name=args.app,
        runtime=runtime,
        allow_general=not args.no_general,
        max_seconds=args.max_seconds,
        vm_url=args.vm or "",
    )

    # Report
    print()
    print("=" * 60)
    success = result.get("success", False)
    print(f"{'OK' if success else 'FAIL'} | Task: {result.get('task', args.task)}")
    print(f"Steps: {result.get('steps_taken', '?')}")
    print(f"Time: {result.get('total_time', '?')}s")
    print()
    for h in result.get("history", []):
        if h.get("type") != "capability_call":
            continue
        capability = h.get("capability", "?")
        capability_input = h.get("input") or {}
        capability_output = h.get("output") or {}
        print(
            f"  {h.get('step', '?')}. [{capability_output.get('status', '?')}] "
            f"{capability}: {str(capability_input.get('task', ''))[:200]}"
        )
    print("=" * 60)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
