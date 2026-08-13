"""Pre-click active localization.

This module keeps the expensive "look again" logic outside the main locator.
It is deliberately optional: callers can use it as a gate around a proposed
click point, or ask it to run a top-k region search when the first proposal is
not supported by local visual evidence.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageDraw
from openprogram.agentic_programming import agentic_function, llm

from gui_harness.perception import detector
from gui_harness.utils import parse_json
from gui_harness.error_monitor import reraise_if_fatal


def enabled() -> bool:
    return os.environ.get("GUI_HARNESS_PRE_CLICK_ACTIVE", "").lower() in {"1", "true", "yes"}


def is_rejected(location: Optional[dict]) -> bool:
    """Whether active verification explicitly rejected this candidate."""
    return bool(location and location.get("active_rejected"))


def _rejected(reason: str, verifier: Optional[dict] = None) -> dict:
    result = {"active_rejected": True, "reasoning": reason}
    if verifier:
        result["pre_click_verifier"] = verifier
    return result


def _clamp_box(box: Iterable[int], img_w: int, img_h: int) -> list[int]:
    x1, y1, x2, y2 = [int(v) for v in box]
    return [max(0, x1), max(0, y1), min(img_w, x2), min(img_h, y2)]


def _candidate_box(candidate: dict, fallback: int = 96) -> list[int]:
    if all(k in candidate for k in ("x", "y", "w", "h")):
        x, y, w, h = [int(candidate.get(k, 0) or 0) for k in ("x", "y", "w", "h")]
        return [x, y, x + max(1, w), y + max(1, h)]
    cx, cy = int(candidate.get("cx", 0) or 0), int(candidate.get("cy", 0) or 0)
    return [cx - fallback, cy - fallback, cx + fallback, cy + fallback]


def _target_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", (text or "").lower()) if len(token) > 1}


def _candidate_relevance(target: str, candidate: dict) -> float:
    label = (candidate.get("label") or candidate.get("name") or "").lower()
    if not label:
        return 0.0
    target_text = (target or "").lower()
    score = 0.0
    if label in target_text or target_text in label:
        score += 8.0
    target_tokens = _target_tokens(target_text)
    label_tokens = _target_tokens(label)
    if target_tokens and label_tokens:
        score += 2.0 * len(target_tokens & label_tokens)
    source = str(candidate.get("source") or candidate.get("type") or "")
    if source in {"ocr", "text"}:
        score += 1.0
    return score


def _rank_candidates_for_target(candidates: list[dict], target: str, limit: int) -> list[dict]:
    indexed = list(enumerate(candidates))
    indexed.sort(
        key=lambda item: (
            -_candidate_relevance(target, item[1]),
            0 if (item[1].get("label") or item[1].get("name")) else 1,
            item[0],
        )
    )
    return [dict(cand, id=cand.get("id") or f"c{idx}") for idx, cand in indexed[:limit]]


def _candidate_context_lines(
    candidates: list[dict],
    *,
    target: str,
    limit: int,
    crop_box: Optional[list[int]] = None,
    scale: int = 1,
) -> str:
    lines: list[str] = []
    ranked = _rank_candidates_for_target(candidates, target, limit)
    for cand in ranked:
        label = cand.get("label") or cand.get("name") or "(unlabeled)"
        box = _candidate_box(cand)
        cx = int(cand.get("cx", (box[0] + box[2]) / 2) or 0)
        cy = int(cand.get("cy", (box[1] + box[3]) / 2) or 0)
        extra = ""
        if crop_box is not None:
            x1, y1, _x2, _y2 = crop_box
            local_box = [
                int(round((box[0] - x1) * scale)),
                int(round((box[1] - y1) * scale)),
                int(round((box[2] - x1) * scale)),
                int(round((box[3] - y1) * scale)),
            ]
            local_center = [
                int(round((cx - x1) * scale)),
                int(round((cy - y1) * scale)),
            ]
            extra = f" crop_bbox={local_box} crop_center={local_center}"
        lines.append(
            f"{cand.get('id')}: {label} source={cand.get('source')} type={cand.get('type')} "
            f"bbox=[{box[0]},{box[1]},{box[2]},{box[3]}] center=({cx},{cy}){extra}"
        )
    return "\n".join(lines)


def _expand_region_box(box: list[int], img_w: int, img_h: int) -> list[int]:
    """Add enough context around LLM-proposed regions for local verification."""
    x1, y1, x2, y2 = _clamp_box(box, img_w, img_h)
    min_w = max(_env_int_or_default("GUI_HARNESS_SCREENSPOT_REGION_MIN_W", 360), int(img_w * 0.10))
    min_h = max(_env_int_or_default("GUI_HARNESS_SCREENSPOT_REGION_MIN_H", 220), int(img_h * 0.08))
    pad = max(_env_int_or_default("GUI_HARNESS_SCREENSPOT_REGION_PAD", 96), int(min(img_w, img_h) * 0.03))
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    width = max(x2 - x1 + 2 * pad, min_w)
    height = max(y2 - y1 + 2 * pad, min_h)
    return _clamp_box(
        [
            int(round(cx - width / 2)),
            int(round(cy - height / 2)),
            int(round(cx + width / 2)),
            int(round(cy + height / 2)),
        ],
        img_w,
        img_h,
    )


def _env_int_or_default(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


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


def build_candidates(
    known_components: list[dict],
    texts: list[dict],
    icons: list[dict],
    limit: int = 240,
) -> list[dict]:
    """Normalize memory/OCR/detector outputs into bbox candidates."""
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


def _crop_with_marker(
    img_path: str,
    box: list[int],
    marker: Optional[list[int]] = None,
    pad: int = 96,
    out_dir: Optional[str] = None,
) -> tuple[str, list[int]]:
    img = Image.open(img_path).convert("RGB")
    img_w, img_h = img.size
    x1, y1, x2, y2 = _clamp_box([box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad], img_w, img_h)
    crop = img.crop((x1, y1, x2, y2))
    draw = ImageDraw.Draw(crop)
    if marker:
        mx, my = int(marker[0]) - x1, int(marker[1]) - y1
        r = 10
        draw.ellipse([mx - r, my - r, mx + r, my + r], outline="blue", width=3)
        draw.line([mx - 2 * r, my, mx + 2 * r, my], fill="blue", width=2)
        draw.line([mx, my - 2 * r, mx, my + 2 * r], fill="blue", width=2)
    draw.rectangle([box[0] - x1, box[1] - y1, box[2] - x1, box[3] - y1], outline="red", width=3)
    out = Path(out_dir or tempfile.gettempdir()) / f"active_loc_{os.getpid()}_{abs(hash((img_path, tuple(box))))}.png"
    crop.save(out)
    return str(out), [x1, y1, x2, y2]


def _full_image_with_marker(
    img_path: str,
    marker: list[int],
    box: Optional[list[int]] = None,
    out_dir: Optional[str] = None,
) -> str:
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    mx, my = int(marker[0]), int(marker[1])
    r = max(14, min(img.size) // 120)
    draw.ellipse([mx - r, my - r, mx + r, my + r], outline="blue", width=4)
    draw.line([mx - 2 * r, my, mx + 2 * r, my], fill="blue", width=3)
    draw.line([mx, my - 2 * r, mx, my + 2 * r], fill="blue", width=3)
    if box:
        draw.rectangle(box, outline="red", width=4)
    out = Path(out_dir or tempfile.gettempdir()) / f"active_full_{os.getpid()}_{abs(hash((img_path, mx, my, tuple(box or []))))}.png"
    img.save(out)
    return str(out)


def _full_image_with_box(img_path: str, box: list[int], out_dir: Optional[str] = None) -> str:
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle(box, outline="red", width=5)
    out = Path(out_dir or tempfile.gettempdir()) / f"active_region_full_{os.getpid()}_{abs(hash((img_path, tuple(box))))}.png"
    img.save(out)
    return str(out)


def _scaled_region_crop(
    img_path: str,
    box: list[int],
    out_dir: str,
    name: str,
    scale: Optional[int] = None,
) -> tuple[str, list[int], int]:
    scale = scale or int(os.environ.get("GUI_HARNESS_SCREENSPOT_CROP_SCALE", "3"))
    img = Image.open(img_path).convert("RGB")
    img_w, img_h = img.size
    x1, y1, x2, y2 = _clamp_box(box, img_w, img_h)
    crop = img.crop((x1, y1, x2, y2))
    if scale > 1:
        crop = crop.resize(((x2 - x1) * scale, (y2 - y1) * scale), Image.Resampling.BICUBIC)
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)[:60]
    out = Path(out_dir) / f"active_region_scaled_{os.getpid()}_{safe_name}.png"
    crop.save(out)
    return str(out), [x1, y1, x2, y2], scale


@agentic_function(as_tool=False)
def verify_region_crop(
    task: str,
    target: str,
    img_path: str,
    region: dict,
    out_dir: str,
) -> dict:
    box = region["bbox"]
    full_path = _full_image_with_box(img_path, box, out_dir=out_dir)
    crop_path, crop_box, scale = _scaled_region_crop(
        img_path, box, out_dir, f"verify_{region.get('name', 'region')}"
    )
    context = f"""Task: {task}
Target: {target}

You will see:
1. the full screenshot with a red rectangle marking a proposed crop region;
2. a {scale}x enlarged crop of that red rectangle.

Decide whether this crop contains the requested clickable target with enough
local visual evidence to choose a precise click point. Do not choose a final
point yet. Answer yes only if the target itself is visible in the crop, not
merely a related label or neighboring control.

Reply with ONLY JSON:
{{"contains_target": "yes|no|uncertain", "target_visible_element": "...", "evidence": "...", "risk": "...", "suggestion": "refine|try_next"}}"""
    try:
        reply = llm([
            {"type": "text", "text": context},
            {"type": "text", "text": "Full screenshot with proposed crop:"},
            {"type": "image", "path": full_path},
            {"type": "text", "text": "Enlarged local crop:"},
            {"type": "image", "path": crop_path},
        ])
        result = parse_json(reply)
    except Exception as exc:
        reraise_if_fatal(exc)  # auth/timeout/transport must reach the runner
        result = {
            "contains_target": "uncertain",
            "evidence": f"parse/runtime error: {exc.__class__.__name__}",
            "suggestion": "try_next",
        }
    result["crop_path"] = crop_path
    result["crop_box"] = crop_box
    result["full_marked_path"] = full_path
    result["scale"] = scale
    return result


@agentic_function(as_tool=False)
def refine_click_in_region(
    task: str,
    target: str,
    img_path: str,
    region: dict,
    out_dir: str,
    candidates: Optional[list[dict]] = None,
) -> Optional[dict]:
    crop_path, crop_box, scale = _scaled_region_crop(
        img_path, region["bbox"], out_dir, f"refine_{region.get('name', 'region')}"
    )
    x1, y1, x2, y2 = crop_box
    crop_candidates: list[dict] = []
    for cand in candidates or []:
        cbox = _candidate_box(cand)
        ccx = int(cand.get("cx", (cbox[0] + cbox[2]) / 2) or 0)
        ccy = int(cand.get("cy", (cbox[1] + cbox[3]) / 2) or 0)
        if _iou(cbox, crop_box) > 0 or (x1 <= ccx <= x2 and y1 <= ccy <= y2):
            crop_candidates.append(dict(cand))
    if os.environ.get("GUI_HARNESS_SCREENSPOT_DETECT_REFINE_CROP", "1").lower() in {"1", "true", "yes"}:
        crop_candidates.extend(_detect_region_candidates(img_path, {"name": region.get("name", "region"), "bbox": crop_box}, out_dir))
    for i, cand in enumerate(crop_candidates):
        cand["id"] = f"r{i}"
    candidate_lines = _candidate_context_lines(
        crop_candidates,
        target=target,
        limit=_env_int_or_default("GUI_HARNESS_SCREENSPOT_REFINE_CANDIDATES", 80),
        crop_box=crop_box,
        scale=scale,
    )
    context = f"""Task: {task}
Target: {target}
Original screenshot crop box: [{x1}, {y1}, {x2}, {y2}]
This image is the crop enlarged by {scale}x.

Detected OCR/component candidates inside or overlapping this crop:
{candidate_lines or "(none)"}

Choose the exact center of the requested clickable target. Prefer returning a
candidate_id from the list when a candidate matches the target. If no candidate
is exact enough, return x/y in the ENLARGED CROP image coordinate system. For
split controls, choose the requested sub-control such as a chevron/detail
arrow, not the neighboring status text or main toggle. For menu/list targets,
choose the row or text candidate matching the target label, not a neighboring
row or parent application icon.

Reply with ONLY JSON:
{{"candidate_id": "r0 or empty", "x": 0, "y": 0, "target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}}"""
    try:
        reply = llm([
            {"type": "text", "text": context},
            {"type": "image", "path": crop_path},
        ])
        parsed = parse_json(reply)
        selected_candidate = None
        selected_id = str(parsed.get("candidate_id") or "").strip()
        if selected_id:
            selected_candidate = _candidate_by_id(crop_candidates, selected_id)
        confidence = float(parsed.get("confidence", 0) or 0)
    except Exception as exc:
        reraise_if_fatal(exc)  # auth/timeout/transport must reach the runner
        return None
    if selected_candidate:
        selected_box = _candidate_box(selected_candidate)
        cx = int(round((selected_box[0] + selected_box[2]) / 2))
        cy = int(round((selected_box[1] + selected_box[3]) / 2))
        local_x = (cx - x1) * scale
        local_y = (cy - y1) * scale
        label = selected_candidate.get("label") or selected_candidate.get("name") or parsed.get("target_visible_element", "crop_first")
        grounding_type = "crop_structured_candidate_refine"
    else:
        try:
            local_x = float(parsed.get("x", 0))
            local_y = float(parsed.get("y", 0))
        except (TypeError, ValueError):
            return None
        if local_x <= 0 or local_y <= 0 or local_x > (x2 - x1) * scale or local_y > (y2 - y1) * scale:
            return None
        cx = int(round(x1 + local_x / scale))
        cy = int(round(y1 + local_y / scale))
        label = parsed.get("target_visible_element", "crop_first")
        grounding_type = "crop_verify_zoom_refine"
    return {
        "id": "crop_first",
        "label": label,
        "name": label,
        "source": "screenspot_crop_first",
        "grounding_type": grounding_type,
        "cx": cx,
        "cy": cy,
        "x": cx - 24,
        "y": cy - 24,
        "w": 48,
        "h": 48,
        "confidence": confidence,
        "reasoning": parsed.get("reasoning", ""),
        "crop_refinement": {
            "crop_path": crop_path,
            "crop_box": crop_box,
            "scale": scale,
            "local_point_scaled": [round(local_x, 2), round(local_y, 2)],
            "candidate_count": len(crop_candidates),
            "selected_candidate_id": selected_id if selected_candidate else "",
            "selected_candidate": selected_candidate,
        },
    }


@agentic_function(as_tool=False)
def verify_candidate(
    task: str,
    target: str,
    img_path: str,
    candidate: dict,
    out_dir: Optional[str] = None,
) -> dict:
    """Ask a local crop verifier whether one candidate is really the target."""
    box = _candidate_box(candidate)
    marker = [candidate.get("cx", 0), candidate.get("cy", 0)]
    crop_path, crop_box = _crop_with_marker(
        img_path,
        box,
        marker=marker,
        out_dir=out_dir,
    )
    full_path = _full_image_with_marker(img_path, marker, box=box, out_dir=out_dir)
    context = f"""Task: {task}
Target: {target}

You will see two images:
1. the full screenshot with a blue cross marking the proposed click point and a
   red rectangle marking the candidate bounding box;
2. a local crop around the same proposed click point/candidate box.

Decide whether this candidate is the target that should be clicked. Be strict:
answer yes only when BOTH are true:
- the red rectangle/click point is on the correct UI element for the target;
- the blue cross is inside that element's clickable area and reasonably close
  to the visual center of the component/text box.

Use the full screenshot to judge global context and nearby competing elements.
Use the crop to judge local precision. First identify the actual visible
text/icon directly under or nearest to the blue cross, then compare it with the
target. Semantic match alone is not enough. If the blue cross is above, below,
on the edge of, or between elements, answer no or uncertain. If the clicked
text/icon differs from the target text/icon, answer no even if a nearby element
would be correct. If the images do not contain enough visual evidence, answer
uncertain.

Reply with ONLY JSON:
{{"is_target": "yes|no|uncertain", "clicked_visible_element": "text/icon under the blue cross", "target_visible_element": "expected target text/icon", "evidence": "...", "risk": "...", "suggestion": "click|zoom|try_next"}}"""
    reply = llm([
        {"type": "text", "text": context},
        {"type": "text", "text": "Full screenshot with proposed click marker:"},
        {"type": "image", "path": full_path},
        {"type": "text", "text": "Local crop with proposed click marker:"},
        {"type": "image", "path": crop_path},
    ])
    try:
        result = parse_json(reply)
    except Exception:
        result = {"is_target": "uncertain", "evidence": reply[:240], "risk": "parse_error", "suggestion": "zoom"}
    result["crop_path"] = crop_path
    result["crop_box"] = crop_box
    result["full_marked_path"] = full_path
    return result


def _os_prior_regions(target: str, img_w: int, img_h: int) -> list[dict]:
    text = (target or "").lower()
    regions = []
    def add(name: str, box: list[int], reason: str) -> None:
        regions.append({"name": name, "bbox": _clamp_box(box, img_w, img_h), "reasoning": reason, "confidence": 0.55})

    if any(k in text for k in ("taskbar", "tray", "hidden icons", "wlan", "bluetooth", "touch keyboard")):
        add("windows_taskbar_right", [int(img_w * 0.72), int(img_h * 0.78), img_w, img_h], "Windows system tray/taskbar target")
        add("windows_taskbar_full", [0, int(img_h * 0.84), img_w, img_h], "Windows taskbar target")
    if any(k in text for k in ("menu", "finder", "dock", "fullscreen", "wifi", "screen recording")):
        add("mac_menu_bar", [0, 0, img_w, int(img_h * 0.13)], "macOS menu bar/window control target")
        add("mac_dock", [0, int(img_h * 0.78), img_w, img_h], "macOS dock target")
    if any(k in text for k in ("toolbar", "ribbon", "button", "icon")):
        add("top_toolbar", [0, 0, img_w, int(img_h * 0.25)], "toolbar/ribbon target")
    return regions


@agentic_function(as_tool=False)
def propose_regions(
    task: str,
    target: str,
    img_path: str,
    img_w: int,
    img_h: int,
    max_regions: int = 4,
    candidates: Optional[list[dict]] = None,
) -> list[dict]:
    """Ask the LLM for coarse search regions, then add cheap OS priors."""
    regions = _os_prior_regions(target, img_w, img_h)
    candidate_lines = _candidate_context_lines(
        candidates or [],
        target=target,
        limit=_env_int_or_default("GUI_HARNESS_SCREENSPOT_REGION_CANDIDATES", 80),
    )
    min_w = max(_env_int_or_default("GUI_HARNESS_SCREENSPOT_REGION_MIN_W", 360), int(img_w * 0.10))
    min_h = max(_env_int_or_default("GUI_HARNESS_SCREENSPOT_REGION_MIN_H", 220), int(img_h * 0.08))
    context = f"""Task: {task}
Target: {target}
Screenshot size: {img_w}x{img_h}

Detected OCR/component candidates that may be useful for region selection:
{candidate_lines or "(none)"}

Identify up to {max_regions} coarse regions where the target may be. Do not
give a final click point. Prefer high-recall regions; include alternatives when
there are similar UI areas or uncertainty. Use the candidate list as structured
evidence: regions should include relevant candidate boxes plus surrounding UI
context, not tiny boxes around one glyph. Each region should usually be at
least about {min_w}x{min_h} pixels unless the whole screenshot is smaller.

Reply with ONLY JSON:
{{"regions": [
  {{"name": "short_name", "bbox": [x1, y1, x2, y2], "candidate_ids": ["c0"], "confidence": 0.0, "reasoning": "..."}}
]}}"""
    try:
        reply = llm([
            {"type": "text", "text": context},
            {"type": "image", "path": img_path},
        ])
        parsed = parse_json(reply)
        for item in parsed.get("regions", [])[:max_regions]:
            bbox = item.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4:
                regions.append({
                    "name": item.get("name", "llm_region"),
                    "bbox": _expand_region_box(bbox, img_w, img_h),
                    "raw_bbox": _clamp_box(bbox, img_w, img_h),
                    "candidate_ids": item.get("candidate_ids", []),
                    "confidence": float(item.get("confidence", 0) or 0),
                    "reasoning": item.get("reasoning", ""),
                })
    except Exception as exc:
        reraise_if_fatal(exc)  # auth/timeout/transport must reach the runner
        print(
            f"  [crop_first] region proposal failed: {exc.__class__.__name__}: {exc}",
            file=__import__("sys").stderr,
        )

    deduped: list[dict] = []
    for region in sorted(regions, key=lambda r: float(r.get("confidence", 0)), reverse=True):
        region = dict(region)
        region["bbox"] = _expand_region_box(region["bbox"], img_w, img_h)
        box = region["bbox"]
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        if any(_iou(box, old["bbox"]) > 0.70 for old in deduped):
            continue
        deduped.append(region)
        if len(deduped) >= max_regions:
            break
    return deduped


def _detect_region_candidates(img_path: str, region: dict, out_dir: Optional[str]) -> list[dict]:
    img = Image.open(img_path).convert("RGB")
    x1, y1, x2, y2 = region["bbox"]
    crop = img.crop((x1, y1, x2, y2))
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(region.get("name", "r")))[:60]
    crop_path = Path(out_dir or tempfile.gettempdir()) / f"active_region_{os.getpid()}_{safe_name}.png"
    crop.save(crop_path)
    try:
        icons, texts, _merged, _w, _h = detector.detect_all(str(crop_path), conf=0.12)
    except Exception:
        icons, texts = [], []
    candidates = build_candidates([], texts, icons, limit=80)
    for cand in candidates:
        cand["cx"] += x1
        cand["cy"] += y1
        cand["x"] += x1
        cand["y"] += y1
        cand["region"] = region.get("name", "")
        cand["crop_path"] = str(crop_path)
    return candidates


@agentic_function(as_tool=False)
def rerank_candidates(
    task: str,
    target: str,
    img_path: str,
    candidates: list[dict],
) -> Optional[dict]:
    if not candidates:
        return None
    lines = []
    for cand in candidates[:120]:
        label = cand.get("label") or "(unlabeled)"
        lines.append(
            f"{cand['id']}: {label} source={cand.get('source')} type={cand.get('type')} "
            f"bbox=[{cand.get('x')},{cand.get('y')},{cand.get('x',0)+cand.get('w',0)},{cand.get('y',0)+cand.get('h',0)}] "
            f"center=({cand.get('cx')},{cand.get('cy')}) region={cand.get('region','')}"
        )
    context = f"""Task: {task}
Target: {target}

Candidate UI elements:
{chr(10).join(lines)}

Choose the candidate that best satisfies the full target description. If none
is supported by the screenshot, answer with candidate_id="" and uncertain.
Prefer an exact text/menu/list-row candidate when the target names visible
text. Do not choose a parent app icon, neighboring row, toolbar group, or
nearby related control when a more specific candidate exists. For targets like
menu items, context-menu commands, list rows, buttons, checkboxes, chevrons, or
plus/add controls, the chosen candidate must be the actual clickable element or
the row containing the exact target label, not merely the app/window that owns
it.

Reply with ONLY JSON:
{{"candidate_id": "c0", "confidence": 0.0, "reasoning": "..."}}"""
    reply = llm([
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])
    try:
        parsed = parse_json(reply)
    except Exception:
        return None
    selected_id = (parsed.get("candidate_id") or "").strip()
    for cand in candidates:
        if cand["id"] == selected_id:
            result = dict(cand)
            result.update({
                "name": cand.get("label") or cand["id"],
                "source": "active_localization",
                "grounding_type": "active_candidate_rerank",
                "reasoning": parsed.get("reasoning", ""),
                "active_confidence": float(parsed.get("confidence", 0) or 0),
            })
            return result
    return None


def _candidate_lines(candidates: list[dict], limit: int) -> str:
    lines = []
    for cand in candidates[:limit]:
        label = cand.get("label") or cand.get("name") or "(unlabeled)"
        lines.append(
            f"{cand.get('id')}: {label} source={cand.get('source')} type={cand.get('type')} "
            f"bbox=[{cand.get('x')},{cand.get('y')},{cand.get('x', 0) + cand.get('w', 0)},{cand.get('y', 0) + cand.get('h', 0)}] "
            f"center=({cand.get('cx')},{cand.get('cy')}) region={cand.get('region', '')}"
        )
    return "\n".join(lines)


def _candidate_by_id(candidates: list[dict], candidate_id: str) -> Optional[dict]:
    for cand in candidates:
        if cand.get("id") == candidate_id:
            return cand
    return None


def _remove_rejected_candidate(pool: list[dict], selected: dict) -> None:
    """Remove a verifier-rejected candidate so the next round explores others."""
    selected_id = selected.get("id")
    selected_box = _candidate_box(selected)
    selected_cx = int(selected.get("cx", 0) or 0)
    selected_cy = int(selected.get("cy", 0) or 0)
    kept: list[dict] = []
    for cand in pool:
        if selected_id and cand.get("id") == selected_id:
            continue
        cand_cx = int(cand.get("cx", 0) or 0)
        cand_cy = int(cand.get("cy", 0) or 0)
        if abs(cand_cx - selected_cx) <= 2 and abs(cand_cy - selected_cy) <= 2:
            continue
        if _iou(_candidate_box(cand), selected_box) > 0.88:
            continue
        kept.append(cand)
    pool[:] = kept


def _centered_location(candidate: dict) -> dict:
    """Return a copy whose click point is the center of its bbox."""
    result = dict(candidate)
    box = _candidate_box(result)
    cx = int(round((box[0] + box[2]) / 2))
    cy = int(round((box[1] + box[3]) / 2))
    result.update({
        "cx": cx,
        "cy": cy,
        "x": box[0],
        "y": box[1],
        "w": max(1, box[2] - box[0]),
        "h": max(1, box[3] - box[1]),
    })
    return result


def _snap_direct_click_to_candidate(
    selected: dict,
    candidates: list[dict],
    max_distance: Optional[int] = None,
) -> dict:
    """Snap free-form LLM coordinates to the nearest detected component center.

    Direct pixels are useful for discovery but too easy to land near a tiny
    text/link target without being inside it. When a detected OCR/component box
    is close to the direct point, use the component center and verify that
    instead.
    """
    max_distance = max_distance or int(os.environ.get("GUI_HARNESS_SCREENSPOT_SNAP_PX", "80"))
    cx = int(selected.get("cx", 0) or 0)
    cy = int(selected.get("cy", 0) or 0)
    best: Optional[tuple[float, dict]] = None
    for cand in candidates:
        box = _candidate_box(cand)
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        ccx = int(round((box[0] + box[2]) / 2))
        ccy = int(round((box[1] + box[3]) / 2))
        inside = box[0] <= cx <= box[2] and box[1] <= cy <= box[3]
        dist2 = float((ccx - cx) ** 2 + (ccy - cy) ** 2)
        if not inside and dist2 > max_distance ** 2:
            continue
        label = (cand.get("label") or cand.get("name") or "").strip()
        source = str(cand.get("source") or cand.get("type") or "")
        # Prefer text/OCR boxes for tiny textual ScreenSpot targets, then
        # prefer closer centers.
        source_bonus = -10000.0 if source in {"ocr", "text"} or label else 0.0
        inside_bonus = -20000.0 if inside else 0.0
        score = dist2 + source_bonus + inside_bonus
        if best is None or score < best[0]:
            best = (score, cand)
    if best is None:
        result = dict(selected)
        result["direct_unsnapped"] = True
        result["snap_reason"] = "no nearby detected OCR/component candidate for direct click"
        return result
    snapped = _centered_location(best[1])
    snapped.update({
        "id": snapped.get("id") or "direct_snapped",
        "name": snapped.get("label") or snapped.get("name") or "direct_snapped",
        "source": "screenspot_active_loop",
        "grounding_type": "active_loop_direct_snapped_to_candidate",
        "active_confidence": selected.get("confidence", selected.get("active_confidence", 0.0)),
        "original_direct_click": [cx, cy],
        "snap_reason": "direct click snapped to nearest detected component center before verification",
    })
    return snapped


def improve_location(
    task: str,
    target: str,
    img_path: str,
    img_w: int,
    img_h: int,
    candidates: list[dict],
    proposed: Optional[dict],
    work_dir: Optional[str] = None,
) -> Optional[dict]:
    """Validate a proposed location and optionally run top-k region search."""
    if not enabled():
        return proposed

    out_dir = work_dir or os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR") or tempfile.gettempdir()
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    proposed_rejected = False
    if proposed:
        verifier = verify_candidate(task, target, img_path, proposed, out_dir=out_dir)
        proposed = dict(proposed)
        proposed["pre_click_verifier"] = verifier
        verdict = str(verifier.get("is_target", "")).lower()
        if verdict == "yes" and verifier.get("suggestion") != "zoom":
            proposed["source"] = proposed.get("source", "pre_click_verified")
            return proposed
        if verdict == "no":
            proposed_rejected = True
            proposed = None

    max_regions = int(os.environ.get("GUI_HARNESS_ACTIVE_LOC_REGIONS", "4"))
    regions = propose_regions(task, target, img_path, img_w, img_h, max_regions=max_regions, candidates=candidates)
    region_candidates: list[dict] = []
    for region in regions:
        rbox = region["bbox"]
        for cand in candidates:
            cbox = _candidate_box(cand)
            if _iou(cbox, rbox) > 0 or (rbox[0] <= cand.get("cx", -1) <= rbox[2] and rbox[1] <= cand.get("cy", -1) <= rbox[3]):
                enriched = dict(cand)
                enriched["region"] = region.get("name", "")
                region_candidates.append(enriched)
        if os.environ.get("GUI_HARNESS_ACTIVE_LOC_DETECT_CROPS", "1").lower() in {"1", "true", "yes"}:
            region_candidates.extend(_detect_region_candidates(img_path, region, out_dir))

    for i, cand in enumerate(region_candidates):
        cand["id"] = f"c{i}"
    selected = rerank_candidates(task, target, img_path, region_candidates)
    if selected:
        selected["active_regions"] = regions
        if os.environ.get("GUI_HARNESS_ACTIVE_VERIFY_SELECTED", "1").lower() in {"1", "true", "yes"}:
            verifier = verify_candidate(task, target, img_path, selected, out_dir=out_dir)
            selected["pre_click_verifier"] = verifier
            verdict = str(verifier.get("is_target", "")).lower()
            if verdict == "yes" and verifier.get("suggestion") != "zoom":
                return selected
            if verdict == "no" and proposed is None:
                return _rejected("selected active candidate rejected by verifier", verifier)
            return proposed
        return selected
    if proposed is None and proposed_rejected:
        return _rejected("proposed candidate rejected by verifier")
    return proposed
