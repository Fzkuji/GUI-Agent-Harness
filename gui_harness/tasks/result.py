"""User-facing result rendering and runtime workflow persistence."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from openprogram.agentic_programming import llm

from gui_harness.openprogram_compat import agentic_function
from gui_harness.perception import screenshot as _screenshot
from gui_harness.utils import parse_json


@agentic_function(render_range={"callers": 0})
def conclusion(
    task: str,
    completed: bool,
    steps_taken: int,
    infeasible: bool = False,
    status: str = "",
    handoff_instruction: str = "",
    img_path: str = "",
) -> dict:
    """Summarize what was accomplished during the GUI task."""
    img_path = img_path or _screenshot.take()

    if not status:
        status = "infeasible" if infeasible else "succeeded" if completed else "failed"
    internal_status = status.upper()
    infeasible_rule = (
        "In `summary`, state the exact human handoff instruction below.\n"
        f"<handoff_instruction>{handoff_instruction}</handoff_instruction>\n\n"
        if status == "infeasible" else ""
    )
    context = (
        f"<original_user_task>{task}</original_user_task>\n\n"
        f"(Internal run status — DO NOT mention this in the summary: "
        f"status={internal_status}, steps={steps_taken})\n\n"
        f"{infeasible_rule}"
        "Your job: write a `summary` that DIRECTLY ANSWERS the user's "
        "<original_user_task>, grounded in the attached screenshot.\n\n"
        "REQUIRED STRUCTURE for `summary` (must follow exactly):\n"
        "  Sentence 1: restate what the user asked, in your own words. "
        "Start with 'User asked: ...'.\n"
        "  Sentence 2+: answer it using SPECIFIC visible content from the "
        "screenshot — app/window name, visible text strings, UI elements, "
        "values, counts. Quote on-screen text where useful.\n"
        "  Final clause (optional, ≤1 sentence): briefly note what was done.\n\n"
        "HARD BANS — these will be rejected:\n"
        "  - Do NOT use the words 'COMPLETED', 'INCOMPLETE', 'Steps used', "
        "'状态显示为', '状态为', 'Status:', or any reference to step counts "
        "or internal run status. The user does not care about that.\n"
        "  - Do NOT write meta-descriptions like '当前可见内容为任务状态/说明文本' "
        "or 'task completed as requested' or 'observed the screen' "
        "WITHOUT then stating what is actually on the screen.\n"
        "  - Do NOT invent content not visible in the screenshot.\n\n"
        "GOOD examples:\n"
        "  task='看一下屏幕里有什么内容' →\n"
        "    'User asked what is on screen. Screen shows Chrome on the "
        "Baidu Tieba homepage; top nav has 首页/分类/我的; main pane lists "
        "5 thread titles, first is \"今日热门话题\".'\n"
        "  task='open Calculator' →\n"
        "    'User asked to open Calculator. Calculator window is now in "
        "the foreground, display reads 0, standard layout visible.'\n\n"
        "HONEST-FALLBACK example — use this style ONLY if the screenshot "
        "is truly blank/black/unreadable or you genuinely cannot see "
        "content:\n"
        "  'User asked what is on screen. The captured screenshot is "
        "blank/unreadable, so I cannot describe actual on-screen content. "
        "No reliable answer can be given from the available data.'\n"
        "  (Do NOT use this fallback just because the run had few steps "
        "— if the screenshot shows anything, describe it.)\n\n"
        "Reply with ONLY this JSON object:\n"
        '{"summary": "<sentence-1 restating task + sentences answering '
        'it from the screenshot>", "issues": "any problems encountered, or null"}'
    )

    reply = llm([
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])

    try:
        result = parse_json(reply)
        result["success"] = status == "succeeded"
        return result
    except Exception:
        return {
            "summary": reply[:500],
            "success": status == "succeeded",
            "issues": None,
            "parse_error": traceback.format_exc(),
            "raw_reply": reply[:1000],
        }


def save_workflow_record(result: dict, app_name: str) -> None:
    """Save runtime history outside the source/package tree."""
    try:
        configured = os.environ.get("GUI_HARNESS_STATE_DIR")
        if configured:
            state_dir = Path(configured).expanduser()
        else:
            try:
                from openprogram.paths import get_state_dir

                state_dir = get_state_dir() / "gui_harness"
            except Exception:
                state_dir = Path.home() / ".gui_harness"
        safe_app_name = app_name.lower().replace(" ", "_").replace("/", "_")
        workflows_dir = state_dir / "workflows" / safe_app_name
        workflows_dir.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        record_path = workflows_dir / f"workflow_{ts}.json"
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
    except Exception as e:
        print(f"  [workflow] save error: {e}", file=sys.stderr)
