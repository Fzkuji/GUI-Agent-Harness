#!/usr/bin/env python3
"""可行性判别器(拒绝层)——附加层,不改动任何既有定位策略。

给定整张截图 + 指令,判断"当前界面上是否存在能满足该指令的可点击元素"。
输出单一标量 p_infeasible ∈ [0,1](越大=越确信无法完成),由调用方用阈值决定是否拒绝。

设计原则:保守。绝大多数指令是可完成的;只有当确信界面上不存在对应目标
(菜单/按钮/选项不存在、该功能本应用没有、指令指向未显示的东西)时才给高分。
拿不准 → 低分(默认放行,走原有定位管线),以保护可定位任务的召回。
"""
from __future__ import annotations

from gui_harness.utils import parse_json
from gui_harness.error_monitor import reraise_if_fatal

_RULES = """You are a strict feasibility checker for a GUI grounding system.

You are shown ONE full screenshot and ONE instruction. Decide whether the
instruction can be carried out by clicking some element that is ACTUALLY VISIBLE
on this screen right now.

Most instructions ARE feasible — the target is somewhere on the screen even if
small or partially hidden. Declare the task infeasible ONLY when you are
confident that NO element on this screen can satisfy it, for example:
- the named menu / button / tab / option simply does not exist in this view,
- the instruction asks for a feature this application does not provide,
- the instruction refers to content that is not present on the screen,
- the instruction is self-contradictory or impossible given what is shown.

Be conservative: if a plausible target MIGHT be present (even if you are unsure
exactly which element), treat it as feasible. When in doubt, p_infeasible is LOW.

Output ONLY JSON:
{"p_infeasible": 0.0, "verdict": "feasible|infeasible", "reasoning": "one short sentence"}
- p_infeasible: your probability in [0,1] that the task CANNOT be done on this screen.
- Reserve p_infeasible >= 0.7 for cases you are quite sure are impossible."""


def judge_infeasible(instruction: str, img_path: str, runtime, timeout_s: int = 120) -> dict:
    """返回 {'p_infeasible': float, 'verdict': str, 'reasoning': str, 'error': optional}。
    失败时 p_infeasible=0.0(放行),保证拒绝层从不因自身报错而误伤可定位任务。"""
    content = [
        {"type": "text", "text": _RULES + f"\n\nInstruction: {instruction}"},
        {"type": "image", "path": img_path},
    ]
    try:
        kwargs = {"content": content}
        if timeout_s > 0:
            kwargs["timeout_s"] = timeout_s
        parsed = parse_json(runtime.exec(**kwargs))
    except Exception as exc:
        reraise_if_fatal(exc)
        return {"p_infeasible": 0.0, "verdict": "feasible",
                "reasoning": "", "error": f"{exc.__class__.__name__}: {str(exc)[:160]}"}
    try:
        p = float(parsed.get("p_infeasible", 0.0) or 0.0)
    except (TypeError, ValueError):
        p = 0.0
    p = max(0.0, min(1.0, p))
    return {"p_infeasible": p,
            "verdict": str(parsed.get("verdict", "")).lower().strip() or ("infeasible" if p >= 0.5 else "feasible"),
            "reasoning": str(parsed.get("reasoning", ""))[:200]}
