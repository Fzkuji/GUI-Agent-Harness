"""
execute_task — autonomous GUI task execution with visual memory.

Design principle:
  The LLM is the decision maker — it decides WHAT to do freely.
  We only enforce HOW for things the LLM can't do well (GUI clicking).

Each step:
  1. Screenshot → identify current state → get transition hints
  2. LLM sees screenshot + context → decides what to do next
  3. If LLM wants a GUI action (click/double_click/right_click/drag):
     → Our detection pipeline locates the target (Phase 1-5)
  4. If LLM wants anything else (type, command, shortcut, etc.):
     → Execute directly, no intervention
  5. Record state transition for future hints
"""

from __future__ import annotations

import json
import sys
import time

from agentic import agentic_function

from gui_harness.utils import parse_json
from gui_harness.perception import screenshot as _screenshot
from gui_harness.action import input as _input
from gui_harness.action.general_action import general_action
from gui_harness.planning.component_memory import (
    locate_target,
    identify_state,
    record_transition,
    get_available_transitions,
)

# GUI actions that need our visual detection pipeline for coordinates
GUI_ACTIONS = {"click", "double_click", "right_click", "drag"}

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


# ═══════════════════════════════════════════
# LLM decision function
# ═══════════════════════════════════════════

@agentic_function(summarize={"depth": 0, "siblings": 0})
def decide_next_action(
    task: str,
    img_path: str,
    step: int,
    max_steps: int,
    history: list,
    known_transitions: list = None,
    runtime=None,
) -> dict:
    """Look at the current screen and decide what to do next.

    You are a GUI agent. Prioritize visual GUI interactions.

    1. GUI actions (PREFERRED — we handle precise coordinate locating):
      {"action": "click", "target": "description of element to click"}
      {"action": "double_click", "target": "description of element to open"}
      {"action": "right_click", "target": "description of element"}
      {"action": "drag", "target": "start element", "target_end": "end element"}

    2. General action (only when task does NOT require GUI interaction):
      {"action": "general", "task": "description of what to do"}
      Use this for: reading file contents, editing code, running commands,
      or any task that is purely text/code-based with no visual UI needed.

    3. Done:
      {"action": "done", "reasoning": "task is complete"}

    Decision guide:
    - Need to interact with a visible UI element? → GUI action
    - Need to open a file on desktop? → double_click
    - Need to navigate menus? → click
    - Need to read/edit file contents without GUI? → general
    - Need to fix code? → general
    - Be efficient — minimize the number of steps

    Return ONLY valid JSON.
    """
    rt = runtime or _get_runtime()

    history_summary = ""
    if history:
        lines = []
        for h in history[-5:]:
            status = "ok" if h.get("success") else "FAIL"
            act = h.get("action", "?")
            detail = h.get("target", h.get("code", ""))
            if detail:
                detail = str(detail)[:50]
            lines.append(f"  {h['step']}. [{status}] {act}: {detail}")
            # Include execute output if available
            if h.get("output"):
                lines.append(f"     output: {str(h['output'])[:200]}")
        history_summary = f"\nRecent actions:\n" + "\n".join(lines)

    hints = ""
    if known_transitions:
        hint_lines = "\n".join(
            f"  - {t['action']}:{t['target']} (used {t['use_count']}x before)"
            for t in known_transitions[:5]
        )
        hints = f"\nKnown transitions from this screen state (hints):\n{hint_lines}"

    context = f"""Task: {task}
Step {step}/{max_steps}.{history_summary}{hints}

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
# GUI action execution
# ═══════════════════════════════════════════

def _execute_gui_action(action, plan, task, img_path, app_name, runtime):
    """Execute a GUI action that needs our visual detection pipeline."""
    target = plan.get("target", "")

    if action == "drag":
        target_end = plan.get("target_end", "")
        start = locate_target(task=task, target=f"Find START: {target}",
                              img_path=img_path, app_name=app_name, runtime=runtime)
        if not start:
            return {"success": False, "error": f"Start not found: {target}"}
        end = locate_target(task=task, target=f"Find END: {target_end}",
                            img_path=img_path, app_name=app_name, runtime=runtime)
        if not end:
            return {"success": False, "error": f"End not found: {target_end}"}
        _input.mouse_drag(start["cx"], start["cy"], end["cx"], end["cy"])
        return {"success": True}
    else:
        location = locate_target(task=task, target=target,
                                 img_path=img_path, app_name=app_name, runtime=runtime)
        if not location:
            return {"success": False, "error": f"Target not found: {target}"}
        cx, cy = location["cx"], location["cy"]
        if action == "click":
            _input.mouse_click(cx, cy)
        elif action == "double_click":
            _input.mouse_double_click(cx, cy)
        elif action == "right_click":
            _input.mouse_right_click(cx, cy)
        return {"success": True, "location": location}


def _execute_code(code, vm_url=None):
    """Execute arbitrary code/command. Routes through VM API if patched."""
    try:
        if vm_url or _is_vm_mode():
            return _execute_on_vm(code)
        else:
            import subprocess
            result = subprocess.run(
                code, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr:
                output += f"\nSTDERR: {result.stderr.strip()}"
            return {"success": result.returncode == 0, "output": output}
    except Exception as e:
        return {"success": False, "output": f"Error: {e}"}


def _is_vm_mode():
    """Check if we're in VM mode (vm_adapter patched the screenshot function)."""
    return hasattr(_screenshot, 'take') and 'vm_screenshot' in str(_screenshot.take)


def _execute_on_vm(code):
    """Execute code on the VM via HTTP API."""
    import requests
    from gui_harness.adapters import vm_adapter
    if vm_adapter._VM_URL is None:
        return {"success": False, "output": "VM not configured"}
    try:
        r = requests.post(
            f"{vm_adapter._VM_URL}/execute",
            json={"command": code, "shell": True},
            timeout=30,
        )
        data = r.json()
        output = data.get("output", "").strip()
        if data.get("error"):
            output += f"\nERROR: {data['error']}"
        return {
            "success": data.get("returncode", 1) == 0,
            "output": output[:500],
        }
    except Exception as e:
        return {"success": False, "output": f"VM exec error: {e}"}


# ═══════════════════════════════════════════
# Agent session initialization
# ═══════════════════════════════════════════

def _init_agent_context(rt, task, app_name):
    """Send initial context to the agent session.

    This runs once at the start of execute_task to give the agent
    a complete picture of the environment before any actions.
    """
    vm_info = ""
    try:
        from gui_harness.adapters import vm_adapter
        if vm_adapter._VM_URL:
            vm_info = f"""
You are operating a remote VM at {vm_adapter._VM_URL}.
All files and applications are on the VM, not on your local machine.
To execute commands on the VM:
  curl -s -X POST {vm_adapter._VM_URL}/execute -H 'Content-Type: application/json' -d '{{"command": "your_command", "shell": true}}'
To read a file: use the command above with "cat /path/to/file".
To write a file: use the command above with appropriate shell commands.
"""
    except Exception:
        pass

    init_message = f"""You are a GUI automation agent. Your task: {task}

Application: {app_name}
{vm_info}
You have visual perception capabilities:
- Screenshot analysis (you will see screenshots each step)
- GPA-GUI-Detector for UI element detection
- OCR for text recognition
- Component memory for recognizing previously seen UI elements

You will be asked to decide actions step by step. Prioritize GUI interactions
(click, double_click, etc.) when the task involves visual UI elements.
Use general actions only when the task clearly doesn't require GUI interaction
(e.g., pure code editing, file content analysis).

Reply OK to confirm you understand."""

    try:
        rt.exec(content=[{"type": "text", "text": init_message}])
    except Exception:
        pass  # Best effort — don't fail if init message fails


# ═══════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════

def execute_task(task: str, runtime=None, max_steps: int = 30, app_name: str = "desktop") -> dict:
    """Execute a GUI task autonomously with experience-augmented decisions.

    The LLM freely decides what to do. GUI click operations go through
    our visual detection pipeline. Everything else executes directly.

    Args:
        task:       Natural language description of what to do.
        runtime:    GUIRuntime instance (auto-detected if None).
        max_steps:  Maximum number of actions (default: 30).
        app_name:   App name for component memory (default: "desktop").

    Returns:
        dict: task, success, steps_taken, total_time, history
    """
    rt = runtime or _get_runtime()
    history = []
    completed = False

    # Initialize agent session with full context
    _init_agent_context(rt, task, app_name)
    task_start = time.time()

    for step in range(1, max_steps + 1):
        step_start = time.time()
        timing = {}

        # Screenshot
        t0 = time.time()
        img_path = _screenshot.take()
        timing["screenshot"] = round(time.time() - t0, 2)
        time.sleep(0.3)

        # Identify state (skip for consecutive free/execute actions)
        last_action = history[-1].get("action") if history else None
        skip_state = (
            last_action in ("general", "execute")
            and len(history) >= 2
            and history[-1].get("state_before") == history[-1].get("state_after")
        )

        if skip_state:
            current_state = history[-1].get("state_after")
            timing["state_identify"] = 0
        else:
            t0 = time.time()
            current_state, _ = identify_state(app_name, img_path)
            timing["state_identify"] = round(time.time() - t0, 2)

        # Transition hints
        known_transitions = []
        if current_state is not None:
            known_transitions = get_available_transitions(app_name, current_state)

        # LLM decides
        t0 = time.time()
        try:
            plan = decide_next_action(
                task=task, img_path=img_path, step=step, max_steps=max_steps,
                history=history, known_transitions=known_transitions, runtime=rt,
            )
        except Exception as e:
            print(f"  [step {step}] LLM ERROR: {e.__class__.__name__}, resetting", file=sys.stderr)
            if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
                rt._inner.reset()
            plan = {"action": "retry", "reasoning": str(e)}
        timing["plan_llm"] = round(time.time() - t0, 2)

        action = plan.get("action", "done")
        print(f"  [step {step}] {action} (hints={'yes' if known_transitions else 'no'})", file=sys.stderr)

        # Retry
        if action == "retry":
            history.append({
                "step": step, "action": "retry",
                "reasoning": plan.get("reasoning", ""),
                "success": False, "timing": timing,
                "state_before": current_state, "state_after": current_state,
            })
            continue

        # Done
        if action == "done":
            completed = True
            history.append({
                "step": step, "action": "done",
                "reasoning": plan.get("reasoning", ""),
                "success": True, "timing": timing,
                "state_before": current_state, "state_after": current_state,
            })
            break

        # Execute
        t0 = time.time()
        result = {}
        try:
            if action in GUI_ACTIONS:
                result = _execute_gui_action(
                    action, plan, task, img_path, app_name, rt)
            elif action == "general":
                # Agent executes freely — can use any tools
                sub_task = plan.get("task", plan.get("target", ""))
                result = general_action(sub_task=sub_task, runtime=rt)
            elif action == "execute":
                result = _execute_code(plan.get("code", ""))
            else:
                # Unknown action — treat as free action
                sub_task = plan.get("task", plan.get("target", plan.get("code", "")))
                result = general_action(sub_task=sub_task, runtime=rt)
        except Exception as e:
            print(f"  [step {step}] Execute ERROR: {e.__class__.__name__}", file=sys.stderr)
            if hasattr(rt, '_inner') and hasattr(rt._inner, 'reset'):
                rt._inner.reset()
            result = {"success": False, "output": str(e)}
        timing["execute"] = round(time.time() - t0, 2)

        time.sleep(0.5)

        # Record state transition (only for GUI actions that change state)
        new_state = current_state
        if action in GUI_ACTIONS:
            t0 = time.time()
            after_img = _screenshot.take("/tmp/gui_agent_after.png")
            new_state, _ = identify_state(app_name, after_img)
            timing["state_record"] = round(time.time() - t0, 2)

            if result.get("success") and current_state is not None:
                record_transition(
                    app_name=app_name, from_state=current_state,
                    action=action, action_target=plan.get("target", ""),
                    to_state=new_state,
                )

        timing["step_total"] = round(time.time() - step_start, 2)

        history.append({
            "step": step,
            "action": action,
            "target": plan.get("target", ""),
            "code": plan.get("code", ""),
            "output": result.get("output", ""),
            "reasoning": plan.get("reasoning", ""),
            "success": result.get("success", False),
            "state_before": current_state,
            "state_after": new_state,
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
    _save_workflow_record(result, app_name)
    return result


# ═══════════════════════════════════════════
# Workflow recording
# ═══════════════════════════════════════════

def _save_workflow_record(result: dict, app_name: str):
    """Save completed task as a workflow record (JSONL, append-only)."""
    import hashlib
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
                "step": h["step"], "action": h["action"],
                "target": h.get("target", ""), "code": h.get("code", ""),
                "success": h.get("success", False),
            }
            for h in result["history"]
        ],
    }
    try:
        with open(workflow_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
