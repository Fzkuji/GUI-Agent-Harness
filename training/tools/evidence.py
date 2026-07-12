"""Candidate-evidence utilities for v3 training data.

Self-contained verbatim ports of the harness's candidate machinery so the
training-time evidence block is byte-identical to what the harness feeds the
model at inference (with best.yaml settings: candidate_sort=relevance,
candidate_limit=60, dedup off, coords_normalized=True, crop_local=False):

  - build_candidates            <- gui_harness/planning/active_localization.py:165
  - candidate_lines(normalized) <- gui_harness/planning/screenspot_locator.py:_iterative_candidate_lines

Kept dependency-light (no cv2/torch) so it runs inside the LLaMA-Factory env.
"""
from __future__ import annotations

import re


def _iou(a: list[int], b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / float(area_a + area_b - inter)


def _candidate_box(candidate: dict, fallback: int = 96) -> list[int]:
    if all(k in candidate for k in ("x", "y", "w", "h")):
        x, y, w, h = [int(candidate.get(k, 0) or 0) for k in ("x", "y", "w", "h")]
        return [x, y, x + max(1, w), y + max(1, h)]
    cx, cy = int(candidate.get("cx", 0) or 0), int(candidate.get("cy", 0) or 0)
    return [cx - fallback, cy - fallback, cx + fallback, cy + fallback]


def _target_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", (text or "").lower()) if len(t) > 1}


def _candidate_relevance(target: str, candidate: dict) -> float:
    label = (candidate.get("label") or candidate.get("name") or "").lower()
    if not label:
        return 0.0
    target_text = (target or "").lower()
    score = 0.0
    if label in target_text or target_text in label:
        score += 8.0
    tt, lt = _target_tokens(target_text), _target_tokens(label)
    if tt and lt:
        score += 2.0 * len(tt & lt)
    source = str(candidate.get("source") or candidate.get("type") or "")
    if source in {"ocr", "text"}:
        score += 1.0
    return score


def build_candidates(
    known_components: list[dict],
    texts: list[dict],
    icons: list[dict],
    limit: int = 240,
) -> list[dict]:
    """Normalize memory/OCR/detector outputs into bbox candidates (verbatim)."""
    out: list[dict] = []
    seen: list[list[int]] = []

    def add(raw: dict, source: str, label_key: str = "name") -> None:
        if len(out) >= limit:
            return
        cx, cy = int(raw.get("cx", 0) or 0), int(raw.get("cy", 0) or 0)
        if cx <= 0 or cy <= 0:
            return
        box = _candidate_box(raw)
        if any(_iou(box, old) > 0.82 for old in seen):
            return
        seen.append(box)
        label = (raw.get(label_key) or raw.get("label") or raw.get("name") or "").strip()
        out.append({
            "id": f"c{len(out)}",
            "label": label,
            "source": raw.get("source") or source,
            "type": raw.get("type") or source,
            "cx": cx,
            "cy": cy,
            "x": box[0],
            "y": box[1],
            "w": max(1, box[2] - box[0]),
            "h": max(1, box[3] - box[1]),
            "confidence": raw.get("confidence", 0.0),
        })

    for item in known_components:
        add(item, "memory", "name")
    for item in texts[:160]:
        add(item, "ocr", "label")
    for item in icons[:120]:
        add(item, "detector", "label")
    return out


def candidate_lines(
    candidates: list[dict],
    crop_box: list[int],
    display_scale: float,
    limit: int = 60,
    target: str = "",
    sort_mode: str = "relevance",
    dedup_iou: float = 0.0,
) -> str:
    """The normalized (coords_normalized=True, crop_local=False) evidence block —
    verbatim logic from _iterative_candidate_lines with best.yaml settings."""
    x1, y1, x2, y2 = crop_box
    pool: list[dict] = []
    for cand in candidates:
        cbox = _candidate_box(cand)
        ccx = int(cand.get("cx", (cbox[0] + cbox[2]) / 2) or 0)
        ccy = int(cand.get("cy", (cbox[1] + cbox[3]) / 2) or 0)
        if _iou(cbox, crop_box) <= 0 and not (x1 <= ccx <= x2 and y1 <= ccy <= y2):
            continue
        pool.append(dict(cand))
    if sort_mode == "relevance" and target:
        pool.sort(key=lambda c: (_candidate_relevance(target, c),
                                 float(c.get("confidence", 0) or 0)), reverse=True)
    elif sort_mode == "confidence":
        pool.sort(key=lambda c: float(c.get("confidence", 0) or 0), reverse=True)
    if dedup_iou and dedup_iou > 0:
        kept: list[dict] = []
        for cand in pool:
            cb = _candidate_box(cand)
            if any(_iou(cb, _candidate_box(k)) >= dedup_iou for k in kept):
                continue
            kept.append(cand)
        pool = kept
    scoped: list[dict] = []
    for cand in pool[:limit]:
        cand["id"] = f"z{len(scoped)}"
        scoped.append(cand)
    lines = []
    cw = max(1, x2 - x1)
    ch = max(1, y2 - y1)
    for cand in scoped:
        cbox = _candidate_box(cand)
        ccx = int(cand.get("cx", (cbox[0] + cbox[2]) / 2) or 0)
        ccy = int(cand.get("cy", (cbox[1] + cbox[3]) / 2) or 0)
        label = cand.get("label") or cand.get("name") or "(unlabeled)"
        nb = [int(round((cbox[0] - x1) / cw * 1000)), int(round((cbox[1] - y1) / ch * 1000)),
              int(round((cbox[2] - x1) / cw * 1000)), int(round((cbox[3] - y1) / ch * 1000))]
        nc = [int(round((ccx - x1) / cw * 1000)), int(round((ccy - y1) / ch * 1000))]
        lines.append(
            f"{cand['id']}: {label} source={cand.get('source')} type={cand.get('type')} "
            f"norm_bbox={nb} norm_center={nc} original_center=({ccx},{ccy})"
        )
    return "\n".join(lines)
