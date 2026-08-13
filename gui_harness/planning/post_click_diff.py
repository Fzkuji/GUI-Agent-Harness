"""Post-click verification with screenshot/OCR diff evidence.

This is designed for real GUI-agent runs, not static localization benchmarks:
capture before -> click -> capture after -> extract visible evidence -> ask a
small verifier only when enabled.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops, ImageStat
from openprogram.agentic_programming import agentic_function, llm

from gui_harness.perception import ocr, screenshot
from gui_harness.utils import parse_json


def enabled() -> bool:
    return os.environ.get("GUI_HARNESS_POST_CLICK_VERIFY", "").lower() in {"1", "true", "yes"}


def capture_state(path: Optional[str] = None, run_ocr: bool = True) -> dict:
    """Capture screenshot plus optional OCR text for diffing."""
    img_path = path or screenshot.take(f"/tmp/gui_harness_post_click_{int(time.time() * 1000)}.png")
    texts = []
    if run_ocr:
        try:
            texts = ocr.detect_text(img_path)
        except Exception:
            texts = []
    return {
        "img_path": img_path,
        "texts": texts,
        "text_labels": [t.get("label", "") for t in texts if t.get("label")],
    }


def _text_delta(before: list[str], after: list[str], limit: int = 30) -> dict:
    before_set = {t.strip() for t in before if t and t.strip()}
    after_set = {t.strip() for t in after if t and t.strip()}
    return {
        "added": sorted(after_set - before_set)[:limit],
        "removed": sorted(before_set - after_set)[:limit],
    }


def _diff_regions(before_path: str, after_path: str, threshold: int = 28, max_regions: int = 8) -> dict:
    """Return coarse changed regions and an aggregate change score."""
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    if before.size != after.size:
        after = after.resize(before.size)

    diff = ImageChops.difference(before, after).convert("L")
    stat = ImageStat.Stat(diff)
    mean_delta = float(stat.mean[0])
    mask = diff.point(lambda p: 255 if p >= threshold else 0)

    try:
        import cv2
        import numpy as np

        arr = np.array(mask)
        num, _labels, stats, _centroids = cv2.connectedComponentsWithStats(arr, 8)
        regions = []
        for i in range(1, num):
            x, y, w, h, area = [int(v) for v in stats[i]]
            if area < 80:
                continue
            regions.append({"bbox": [x, y, x + w, y + h], "area": area})
        regions = sorted(regions, key=lambda r: r["area"], reverse=True)[:max_regions]
    except Exception:
        bbox = mask.getbbox()
        regions = [{"bbox": list(bbox), "area": (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])}] if bbox else []

    return {
        "mean_delta": round(mean_delta, 3),
        "regions": regions,
    }


def extract_evidence(before: dict, after: dict, click_location: Optional[dict] = None) -> dict:
    """Collect program-readable evidence of whether a click changed state."""
    diff = _diff_regions(before["img_path"], after["img_path"])
    text = _text_delta(before.get("text_labels", []), after.get("text_labels", []))
    evidence = {
        "before_img": before["img_path"],
        "after_img": after["img_path"],
        "pixel_diff": diff,
        "ocr_diff": text,
        "click_location": click_location or {},
    }
    return evidence


def _crop_changed_area(after_path: str, evidence: dict, out_dir: Optional[str] = None) -> Optional[str]:
    regions = evidence.get("pixel_diff", {}).get("regions", [])
    if not regions:
        return None
    bbox = regions[0].get("bbox")
    if not bbox:
        return None
    img = Image.open(after_path).convert("RGB")
    x1, y1, x2, y2 = bbox
    pad = 80
    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
    x2, y2 = min(img.size[0], x2 + pad), min(img.size[1], y2 + pad)
    crop = img.crop((x1, y1, x2, y2))
    out = Path(out_dir or "/tmp") / f"post_click_changed_{int(time.time() * 1000)}.png"
    crop.save(out)
    return str(out)


@agentic_function(as_tool=False)
def verify_after_click(
    task: str,
    action: str,
    target: str,
    before: dict,
    after: dict,
    click_location: Optional[dict] = None,
    expected_effect: str = "",
    out_dir: Optional[str] = None,
) -> dict:
    """Judge whether the click plausibly achieved the intended action."""
    evidence = extract_evidence(before, after, click_location=click_location)
    mean_delta = evidence["pixel_diff"]["mean_delta"]
    added = evidence["ocr_diff"]["added"]
    removed = evidence["ocr_diff"]["removed"]

    # Cheap rule: no visible or OCR change after an interactive click is risky.
    if mean_delta < 0.35 and not added and not removed:
        rule = "uncertain"
        rule_reason = "no meaningful screenshot or OCR change detected"
    else:
        rule = "changed"
        rule_reason = "visible screenshot or OCR change detected"

    result = {
        "verdict": rule,
        "rule_reason": rule_reason,
        "evidence": evidence,
    }
    changed_crop = _crop_changed_area(after["img_path"], evidence, out_dir=out_dir)
    context = f"""Task: {task}
Action: {action}
Target clicked: {target}
Expected effect: {expected_effect or '(infer from action and task)'}

Programmatic evidence:
- mean pixel delta: {mean_delta}
- changed regions: {evidence['pixel_diff']['regions'][:5]}
- OCR text added: {added[:20]}
- OCR text removed: {removed[:20]}
- rule verdict: {rule} ({rule_reason})

Decide whether the click appears to have achieved the intended immediate
effect. Use pass only when the evidence supports the expected UI change. Use
uncertain when the change is too small or semantically unclear.

Reply with ONLY JSON:
{{"verdict": "pass|fail|uncertain", "evidence": "...", "next_action": "continue|retry_next_candidate|zoom_search"}}"""
    content = [
        {"type": "text", "text": context},
        {"type": "image", "path": before["img_path"]},
        {"type": "image", "path": after["img_path"]},
    ]
    if changed_crop:
        content.append({"type": "image", "path": changed_crop})
    reply = llm(content)
    try:
        judged = parse_json(reply)
    except Exception:
        judged = {
            "verdict": "uncertain",
            "evidence": reply[:240],
            "next_action": "retry_next_candidate",
            "parse_error": True,
        }
    judged["programmatic_evidence"] = evidence
    judged["rule_verdict"] = rule
    if changed_crop:
        judged["changed_crop"] = changed_crop
    return judged
