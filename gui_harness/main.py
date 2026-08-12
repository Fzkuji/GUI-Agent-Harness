#!/usr/bin/env python3
"""
GUI Agent — main entry point.

Usage:
    python3 -m gui_harness "Open Firefox and go to google.com"
    python3 gui_harness/main.py "Send hello to John in WeChat"
    python3 gui_harness/main.py --vm http://172.16.105.128:5000 "Click the OK button"
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
            # Integers, not strings: the param is annotated ``max_steps: int``
            # so the generated JSON schema is ``type: integer``. String options
            # here produce ``enum: ["5",...]`` which contradicts the integer
            # type and OpenAI strict-mode tool validation rejects the whole
            # request (HTTP 400 invalid_function_parameters), breaking every
            # turn — not just gui_agent calls — when an OpenAI/codex model is
            # selected. Keep enum values the same type as the param.
            "options": [5, 10, 15, 30],
        },
        "app_name": {
            "description": "App name for component memory",
            "placeholder": "e.g. firefox, libreoffice_calc, desktop",
        },
        "runtime": {"hidden": True},
    },
)
def gui_agent(
    task: str,
    max_steps: int = 15,
    app_name: str = "desktop",
    runtime=None,
    allow_general: bool = False,
) -> dict:
    """Drive the desktop GUI to complete a task.

    Loops observe -> verify -> plan -> act on the real screen until the
    task is done or max_steps is reached. Use it for work that can only
    be done through a graphical application; anything reachable from a
    shell or a file is cheaper and more reliable without it.

    The runtime's working directory must be configured before calling —
    relative paths resolve against it.

    Args:
        task: what to do, in natural language.
        max_steps: maximum number of actions (default: 15).
        app_name: app name for component memory (default: "desktop").

    Returns a dict with task, success, steps_taken, total_time, history.
    """
    if runtime is None:
        raise ValueError("gui_agent() requires a runtime argument")

    from gui_harness.tasks.execute_task import (
        gui_step, build_step_feedback, save_workflow_record, conclusion,
    )
    from gui_harness.planning.learn import has_base_memory, learn_app_components

    # ── Setup ──
    task_start = time.time()

    # Auto-learn app components if no base memory
    if not has_base_memory(app_name):
        print(f"  [learn] No base memory for '{app_name}', learning...", file=sys.stderr)
        learn_result = learn_app_components(app_name=app_name, runtime=runtime)
        saved = learn_result.get("components_saved", 0)
        t = learn_result.get("timing", {})
        print(
            f"  [learn] Saved {saved} components "
            f"(detect={t.get('detect', '?')}s, label={t.get('label', '?')}s, save={t.get('save', '?')}s)",
            file=sys.stderr,
        )

    # ── Loop: gui_step with explicit feedback ──
    history = []
    feedback = None
    completed = False
    infeasible_declared = False

    for step_num in range(1, max_steps + 1):
        print(f"  [step {step_num}/{max_steps}] ...", file=sys.stderr)

        try:
            result = gui_step(
                task=task,
                feedback=feedback,
                app_name=app_name,
                runtime=runtime,
                allow_general=allow_general,
            )
        except Exception as e:
            print(f"  [step {step_num}] ERROR: {e.__class__.__name__}: {e}", file=sys.stderr)
            result = {
                "done": False,
                "plan": {"action": "error", "goal": ""},
                "exec_result": {"success": False, "error": str(e)},
            }

        # Log
        plan = result.get("plan", {})
        action = plan.get("call", plan.get("action", "?"))
        args = plan.get("args", {})
        detail = (
            args.get("target", "")
            or args.get("text", "")
            or args.get("keys", "")
            or args.get("key", "")
            or args.get("sub_task", "")
            or plan.get("target", "")
        )
        print(f"  [step {step_num}] {action}: {str(detail)[:200]}", file=sys.stderr)

        history.append({"step": step_num, **result})

        if result.get("done"):
            completed = True
            infeasible_declared = bool(result.get("infeasible"))
            break

        # Build feedback for next iteration
        feedback = build_step_feedback(result)

        # Compress CLI session context between steps when it grows large.
        # Each gui_step adds a screenshot + detection results + tool outputs,
        # which accumulate in the persistent claude-code subprocess's session.
        # Only the `feedback` dict carries semantic state forward, so the raw
        # history is redundant. Threshold is set below the model's 80% default
        # so compact fires while the session is still responsive.
        if hasattr(runtime, "compact"):
            runtime.compact(threshold_tokens=200_000)

    # ── Conclusion: LLM summarizes the result ──
    print(f"  [conclusion] ...", file=sys.stderr)
    try:
        summary = conclusion(
            task=task,
            completed=completed,
            steps_taken=len(history),
        )
        print(f"  [conclusion] {summary.get('summary', '')[:300]}", file=sys.stderr)
    except Exception as e:
        print(f"  [conclusion] ERROR: {e}", file=sys.stderr)
        summary = {"summary": str(e), "success": completed, "issues": None}

    # ── Teardown ──
    total_time = round(time.time() - task_start, 2)
    final = {
        "task": task,
        "success": summary.get("success", completed),
        "infeasible_declared": infeasible_declared,
        "summary": summary.get("summary", ""),
        "issues": summary.get("issues"),
        "steps_taken": len(history),
        "total_time": total_time,
        "history": history,
    }
    save_workflow_record(final, app_name)

    return final


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
    parser.add_argument("--max-steps", type=int, default=15, help="Max actions (default: 15)")
    parser.add_argument("--app", default="desktop", help="App name for memory (default: desktop)")
    parser.add_argument("--no-general", action="store_true",
                        help="Disable command-line ('general') action; force GUI-only interaction.")
    args = parser.parse_args()

    # VM adapter
    if args.vm:
        from gui_harness.adapters.vm_adapter import patch_for_vm
        patch_for_vm(args.vm)
        print(f"VM mode: {args.vm}")

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
        plan = h.get("plan", {})
        action = plan.get("action", plan.get("call", "?"))
        args = plan.get("args", {})
        # Show the most relevant arg for each action type
        detail = (
            args.get("target", "")
            or args.get("text", "")
            or args.get("keys", "")
            or args.get("key", "")
            or args.get("direction", "")
            or args.get("sub_task", "")
            or args.get("reasoning", "")
            or plan.get("target", "")
        )
        exec_ok = h.get("exec_result", {}).get("success", h.get("done", False))
        v = h.get("verification")
        status = "OK" if exec_ok else "FAIL"
        print(f"  {h['step']}. [{status}] {action}: {str(detail)[:200]}")
        if plan.get("goal"):
            print(f"     goal: {plan['goal'][:200]}")
        if v and v.get("observation"):
            print(f"     observed: {v['observation'][:200]}")
    print("=" * 60)


if __name__ == "__main__":
    main()
