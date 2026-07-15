#!/usr/bin/env python3
"""Rule-based GRPO reward: 1.0 if the model's point_2d lands inside the GT
bbox (both in [0,1000]-normalized space of the displayed crop), else 0.0.

Same correctness check as eval_zoom_traj.py / run_screenspot_pro.evaluate_point
— no reward model, no LLM judge, deterministic and free to compute.
"""
from __future__ import annotations

import json
import re
from typing import Any


def _extract_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list) and completion:
        last = completion[-1]
        if isinstance(last, dict):
            return str(last.get("content", ""))
    return str(completion)


def _parse_json_reply(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def click_bbox_reward(completions: list, gt_bbox_norm1000: list, **kwargs) -> list[float]:
    rewards = []
    for completion, gt_box in zip(completions, gt_bbox_norm1000):
        text = _extract_text(completion)
        parsed = _parse_json_reply(text)
        if not parsed:
            rewards.append(0.0)
            continue
        raw = parsed.get("point_2d") or [parsed.get("x"), parsed.get("y")]
        if not (isinstance(raw, list) and len(raw) >= 2
                and all(isinstance(v, (int, float)) for v in raw[:2])):
            rewards.append(0.0)
            continue
        x, y = float(raw[0]), float(raw[1])
        x1, y1, x2, y2 = gt_box
        rewards.append(1.0 if (x1 <= x <= x2 and y1 <= y <= y2) else 0.0)
    return rewards
