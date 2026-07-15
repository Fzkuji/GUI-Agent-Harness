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


def _click_score(parsed: dict, gt_box: list) -> float:
    raw = parsed.get("point_2d") or [parsed.get("x"), parsed.get("y")]
    if not (isinstance(raw, list) and len(raw) >= 2
            and all(isinstance(v, (int, float)) for v in raw[:2])):
        return 0.0
    x, y = float(raw[0]), float(raw[1])
    x1, y1, x2, y2 = gt_box
    return 1.0 if (x1 <= x <= x2 and y1 <= y <= y2) else 0.0


def _crop_score(parsed: dict, gt_box: list) -> float:
    """Reward a round-0 crop decision: the proposed crop (in the same
    [0,1000] displayed-view space as gt_box) must CONTAIN the whole GT box
    and meaningfully shrink the search area (5%..60% of the view)."""
    if str(parsed.get("action", "")).lower() != "crop":
        return 0.0  # crop-stage rows are built only for small targets; final/recrop here is wrong
    bbox = parsed.get("bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4
            and all(isinstance(v, (int, float)) for v in bbox)):
        return 0.0
    cx1, cy1, cx2, cy2 = (float(v) for v in bbox)
    if cx2 <= cx1 or cy2 <= cy1:
        return 0.0
    gx1, gy1, gx2, gy2 = gt_box
    contains = cx1 <= gx1 and cy1 <= gy1 and cx2 >= gx2 and cy2 >= gy2
    area_frac = (cx2 - cx1) * (cy2 - cy1) / (1000.0 * 1000.0)
    return 1.0 if (contains and 0.05 <= area_frac <= 0.60) else 0.0


def harness_stage_reward(completions: list, gt_bbox_norm1000: list, task: list, **kwargs) -> list[float]:
    """Rule reward for harness-stage GRPO rows (task='crop' | 'click')."""
    rewards = []
    for completion, gt_box, t in zip(completions, gt_bbox_norm1000, task):
        parsed = _parse_json_reply(_extract_text(completion))
        if not parsed:
            rewards.append(0.0)
            continue
        rewards.append(_crop_score(parsed, gt_box) if t == "crop"
                       else _click_score(parsed, gt_box))
    return rewards
