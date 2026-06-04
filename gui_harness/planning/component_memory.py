"""
Component Memory — Phase 1-5 locate_target workflow.

This module implements the core loop for finding a target element on screen
by combining GPA detection, template matching against saved memory, and
LLM-driven labeling of unknown components.

Design (from DESIGN doc):
  Phase 1:   GPA detection + OCR → N components (sorted by confidence)
  Phase 2:   Template match against memory → known components list
  Phase 3:   LLM sees known components → found target? → return coordinates
  Phase 3.5: Deterministic OCR-text fuzzy match (Python fallback when Phase 3
             LLM returns False — catches menu/label texts the LLM misjudges)
  Phase 4:   Label unknown components one-by-one (stop when target found)
  Phase 5:   Cleanup (delete unlabeled screenshots)

This module is called by execute_task.py whenever an action needs
screen coordinates (click, double_click, right_click, drag).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from gui_harness.openprogram_compat import agentic_function

from gui_harness.perception import screenshot, ocr, detector
from gui_harness.memory import app_memory
from gui_harness.planning import active_localization, screenspot_locator

# ═══════════════════════════════════════════
# Phase 1: Detection
# ═══════════════════════════════════════════

def _dedupe_components(elements: list[dict], iou_threshold: float = 0.65) -> list[dict]:
    """Deduplicate mapped detector/OCR elements, keeping higher-confidence boxes."""
    kept: list[dict] = []
    for element in sorted(elements, key=lambda e: e.get("confidence", 0), reverse=True):
        if any(detector.compute_iou(element, existing) >= iou_threshold for existing in kept):
            continue
        kept.append(element)
    return kept


def _multiscale_regions(img_w: int, img_h: int) -> list[tuple[str, int, int, int, int]]:
    """Return UI-biased regions for crop-and-resize detection."""
    left_w = max(int(img_w * 0.28), 320)
    right_x = min(int(img_w * 0.70), max(0, img_w - 480))
    top_h = max(int(img_h * 0.22), 220)
    bottom_y = min(int(img_h * 0.72), max(0, img_h - 320))
    regions = [
        ("top", 0, 0, img_w, min(img_h, top_h)),
        ("left", 0, 0, min(img_w, left_w), img_h),
        ("right", right_x, 0, img_w, img_h),
        ("bottom", 0, bottom_y, img_w, img_h),
        ("center", int(img_w * 0.18), int(img_h * 0.16), int(img_w * 0.82), int(img_h * 0.84)),
    ]
    unique: list[tuple[str, int, int, int, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for name, x1, y1, x2, y2 in regions:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img_w, x2), min(img_h, y2)
        key = (x1, y1, x2, y2)
        if x2 - x1 < 120 or y2 - y1 < 120 or key in seen:
            continue
        unique.append((name, x1, y1, x2, y2))
        seen.add(key)
    return unique


def _detect_multiscale_components(
    img_path: str,
    img_w: int,
    img_h: int,
    conf: float = 0.18,
    scale: int = 2,
) -> tuple[list[dict], list[dict]]:
    """Detect on enlarged UI regions and map boxes back to original pixels."""
    img = cv2.imread(img_path)
    if img is None:
        return [], []

    icons: list[dict] = []
    texts: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="gui_harness_multiscale_") as tmp_dir:
        for region_name, x1, y1, x2, y2 in _multiscale_regions(img_w, img_h):
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crop_scaled = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            crop_path = str(Path(tmp_dir) / f"{region_name}.png")
            cv2.imwrite(crop_path, crop_scaled)
            try:
                crop_icons, crop_texts, _merged, _cw, _ch = detector.detect_all(crop_path, conf=conf)
            except Exception as exc:
                print(
                    f"  [locate] multiscale region {region_name} failed: {exc.__class__.__name__}: {exc}",
                    file=sys.stderr,
                )
                continue

            for icon in crop_icons:
                mapped = dict(icon)
                mapped["x"] = int(round(x1 + icon.get("x", 0) / scale))
                mapped["y"] = int(round(y1 + icon.get("y", 0) / scale))
                mapped["w"] = max(1, int(round(icon.get("w", 0) / scale)))
                mapped["h"] = max(1, int(round(icon.get("h", 0) / scale)))
                mapped["cx"] = mapped["x"] + mapped["w"] // 2
                mapped["cy"] = mapped["y"] + mapped["h"] // 2
                mapped["source"] = "gpa_detector_multiscale"
                mapped["region"] = region_name
                mapped["source_scale"] = scale
                icons.append(mapped)

            for text in crop_texts:
                mapped = dict(text)
                mapped["x"] = int(round(x1 + text.get("x", 0) / scale))
                mapped["y"] = int(round(y1 + text.get("y", 0) / scale))
                mapped["w"] = max(1, int(round(text.get("w", 0) / scale)))
                mapped["h"] = max(1, int(round(text.get("h", 0) / scale)))
                mapped["cx"] = mapped["x"] + mapped["w"] // 2
                mapped["cy"] = mapped["y"] + mapped["h"] // 2
                mapped["source"] = "vision_ocr_multiscale"
                mapped["region"] = region_name
                mapped["source_scale"] = scale
                texts.append(mapped)

    return icons, texts


def _rank_icons_for_screenspot(icons: list[dict]) -> list[dict]:
    """Prioritize plausible ScreenSpot-Pro UI controls for expensive labeling."""
    def score(icon: dict) -> tuple[int, int, float]:
        area = max(1, icon.get("w", 0) * icon.get("h", 0))
        multiscale_rank = 0 if icon.get("source") == "gpa_detector_multiscale" else 1
        # Prefer small/medium controls over full panels and huge containers.
        if 64 <= area <= 12000:
            area_rank = 0
        elif area < 64:
            area_rank = 1
        else:
            area_rank = 2
        return (multiscale_rank, area_rank, -float(icon.get("confidence", 0)))

    ranked = sorted(icons, key=score)
    return ranked[: int(os.environ.get("GUI_HARNESS_SCREENSPOT_ICON_LIMIT", "40"))]


def detect_components(img_path: str, conf: float = 0.3, multiscale: bool = False) -> dict:
    """Run GPA-GUI-Detector + OCR on a screenshot.

    Returns a dict with:
      - icons: list[dict] — GPA-detected UI components, sorted by confidence desc
      - texts: list[dict] — OCR text elements with coordinates
      - img_w, img_h: image dimensions
    """
    icons, texts, _merged, img_w, img_h = detector.detect_all(img_path, conf=conf)
    if multiscale:
        t0 = time.time()
        extra_icons, extra_texts = _detect_multiscale_components(img_path, img_w, img_h)
        icons = _dedupe_components(list(icons) + extra_icons)
        texts = _dedupe_components(list(texts) + extra_texts, iou_threshold=0.75)
        print(
            f"  [locate] multiscale: +{len(extra_icons)} icons +{len(extra_texts)} texts "
            f"-> {len(icons)} icons, {len(texts)} texts ({time.time() - t0:.2f}s)",
            file=sys.stderr,
        )

    # Sort icons by confidence descending — higher confidence = more likely interactive
    icons = sorted(icons, key=lambda e: e.get("confidence", 0), reverse=True)

    return {
        "icons": icons,
        "texts": texts,
        "img_w": img_w,
        "img_h": img_h,
    }


# ═══════════════════════════════════════════
# Phase 2: Memory Matching
# ═══════════════════════════════════════════

FORGET_THRESHOLD = 30  # Delete component after this many consecutive misses


def match_memory_components(
    app_name: str,
    img_path: str,
    threshold: float = 0.8,
) -> list[dict]:
    """Match saved component templates against the current screenshot.

    For each saved component, run template matching on the full screenshot.
    Also updates activity tracking: matched components get seen_count++,
    unmatched components get consecutive_misses++. Components that miss
    FORGET_THRESHOLD times in a row are automatically deleted.

    Returns:
        list[dict]: Each dict has keys:
            - name: str — component label
            - cx, cy: int — click-space center coordinates
            - confidence: float — match confidence
            - source: "memory"
    """
    app_dir = app_memory.get_app_dir(app_name)
    components_dir = app_dir / "components"

    if not components_dir.exists():
        return []

    screen_img = cv2.imread(img_path)
    if screen_img is None:
        return []

    screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
    matched = []
    matched_names = set()

    for icon_file in components_dir.glob("*.png"):
        template = cv2.imread(str(icon_file))
        if template is None:
            continue

        th, tw = template.shape[:2]
        if th < 10 or tw < 10 or th > screen_gray.shape[0] or tw > screen_gray.shape[1]:
            continue

        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            matched.append({
                "name": icon_file.stem,
                "cx": cx,
                "cy": cy,
                "w": tw,
                "h": th,
                "confidence": round(float(max_val), 3),
                "source": "memory",
            })
            matched_names.add(icon_file.stem)

    # Update activity tracking and forget stale components
    _update_activity(app_dir, matched_names)

    # Sort by confidence descending
    matched.sort(key=lambda m: m["confidence"], reverse=True)
    return matched


def _update_activity(app_dir: Path, matched_names: set[str]):
    """Update component activity tracking after a match round.

    - Matched components: seen_count++, consecutive_misses = 0, last_seen = now
    - Unmatched components: consecutive_misses++
    - Components with consecutive_misses >= FORGET_THRESHOLD: deleted
    """
    components = app_memory.load_components(app_dir)
    if not components:
        return

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    to_delete = []

    for name, comp in components.items():
        if name in matched_names:
            comp["last_seen"] = now
            comp["seen_count"] = comp.get("seen_count", 0) + 1
            comp["consecutive_misses"] = 0
        else:
            comp["consecutive_misses"] = comp.get("consecutive_misses", 0) + 1
            if comp["consecutive_misses"] >= FORGET_THRESHOLD:
                to_delete.append(name)

    # Delete stale components
    components_dir = app_dir / "components"
    for name in to_delete:
        # Remove icon file
        icon_file = components[name].get("icon_file", "")
        if icon_file:
            icon_path = app_dir / icon_file
            if icon_path.exists():
                try:
                    icon_path.unlink()
                except OSError:
                    pass
        # Also try by name
        png_path = components_dir / f"{name}.png"
        if png_path.exists():
            try:
                png_path.unlink()
            except OSError:
                pass
        del components[name]

    if to_delete:
        import sys
        print(f"  [memory] Forgot {len(to_delete)} stale components: {to_delete}", file=sys.stderr)

    app_memory.save_components(app_dir, components)


# ═══════════════════════════════════════════
# Deterministic OCR Text Matching
# ═══════════════════════════════════════════

_MATCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "bar",
    "button",
    "click",
    "clicking",
    "corner",
    "current",
    "dialog",
    "icon",
    "in",
    "item",
    "label",
    "left",
    "menu",
    "on",
    "open",
    "right",
    "text",
    "the",
    "top",
}

_CONTROL_ROLE_PHRASES = (
    "menu entry",
    "menu item",
    "menu label",
    "menu text",
    "text field",
    "input field",
    "text button",
    "button",
    "checkbox",
    "field",
    "label",
    "dialog",
)

_MENU_BAR_WORDS = {
    "file",
    "edit",
    "select",
    "view",
    "image",
    "layer",
    "colors",
    "tools",
    "filters",
    "windows",
    "help",
}


def _normalize_match_text(value: str) -> str:
    """Normalize UI target text for OCR label matching."""
    value = re.sub(r"\([^)]*\)", " ", value.lower())
    value = re.sub(r"\bat\s+\d+\s*,\s*\d+\b", " ", value)
    value = re.sub(r"_+", " ", value)
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    words = [word for word in value.split() if word not in _MATCH_STOPWORDS]
    return " ".join(words)


def _normalize_target_text(target: str) -> str:
    value = re.sub(r"\([^)]*\)", " ", target.lower())
    for phrase in _CONTROL_ROLE_PHRASES:
        marker = f" {phrase}"
        idx = value.find(marker)
        if idx > 0:
            value = value[:idx]
            break
    return _normalize_match_text(value)


def _parse_target_hint_coords(target: str) -> Optional[tuple[int, int]]:
    match = re.search(r"\((\d+)\s*,\s*(\d+)\)", target)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _split_combined_menu_text(target_norm: str, text: dict, label_norm: str) -> Optional[dict]:
    words = label_norm.split()
    if len(target_norm.split()) != 1 or target_norm not in words:
        return None
    if int(text.get("cy", 0) or 0) > 130:
        return None
    if len(_MENU_BAR_WORDS.intersection(words)) < 2:
        return None

    x = int(text.get("x", 0) or 0)
    w = int(text.get("w", 0) or 0)
    cy = int(text.get("cy", 0) or 0)
    if w <= 0 or cy <= 0:
        return None

    start = label_norm.find(target_norm)
    if start < 0 or not label_norm:
        return None
    center_ratio = (start + len(target_norm) / 2) / len(label_norm)
    cx = int(x + w * center_ratio)
    return {
        "found": True,
        "name": target_norm,
        "cx": cx,
        "cy": cy,
        "reasoning": "split combined OCR menu-bar text deterministically",
    }


def _deterministic_text_match(target: str, texts: list[dict]) -> Optional[dict]:
    """Return coordinates when the target text/name is already visible."""
    target_norm = _normalize_target_text(target)
    if not target_norm:
        return None

    hint = _parse_target_hint_coords(target)
    target_word_count = len(target_norm.split())
    candidates = []

    for text in texts[:80]:
        label = (text.get("label") or text.get("name") or "").strip()
        label_norm = _normalize_match_text(label)
        if len(label_norm.replace(" ", "")) < 2:
            continue

        cx = int(text.get("cx", 0) or 0)
        cy = int(text.get("cy", 0) or 0)
        if cx <= 0 or cy <= 0:
            continue

        match_rank = 0
        match_label = label
        if label_norm != target_norm:
            split = _split_combined_menu_text(target_norm, text, label_norm)
            if not split:
                continue
            cx = split["cx"]
            cy = split["cy"]
            match_label = split["name"]
            match_rank = 1

        distance = abs(cx - hint[0]) + abs(cy - hint[1]) if hint else 0
        length_delta = abs(len(label_norm.split()) - target_word_count)
        candidates.append((match_rank, distance, length_delta, -len(label_norm), match_label, cx, cy))

    if not candidates:
        return None

    _rank, _distance, _delta, _length, label, cx, cy = sorted(candidates)[0]
    return {
        "found": True,
        "name": label,
        "cx": cx,
        "cy": cy,
        "reasoning": "matched OCR text deterministically",
    }


# ═══════════════════════════════════════════
# Phase 3: LLM decides from known components
# ═══════════════════════════════════════════

@agentic_function(render_range={"callers": 0})
def find_target_in_known(
    task: str,
    target: str,
    known_components: list[dict],
    texts: list[dict],
    img_path: str,
    img_w: int,
    img_h: int,
    runtime=None,
) -> dict:
    """Locate a target element from candidates or direct screenshot grounding."""
    from gui_harness.utils import parse_json

    if runtime is None:
        raise ValueError("find_target_in_known() requires a runtime argument")
    rt = runtime

    comp_lines = "\n".join(
        f"  [{c['name']}] at ({c['cx']}, {c['cy']}) conf={c.get('confidence', 0):.2f}"
        for c in known_components
    ) or "(none)"

    text_lines = "\n".join(
        f"  '{t.get('label', '')}' at ({t.get('cx', 0)}, {t.get('cy', 0)})"
        for t in texts[:60]
    ) or "(none)"

    context = f"""Task: {task}
Target: {target}

Known UI components (labeled, with coordinates):
{comp_lines}

OCR text on screen:
{text_lines}

You may locate the target in either of two ways:
1. Pick one entry from the known components or OCR text. Use the exact label
   as written in the lists above.
2. If the target is visible in the screenshot but is not represented by any
   listed entry, estimate its click coordinates directly from the screenshot
   and the coordinate references above.

Choose a listed entry only if it satisfies the full target description. Do not
choose an entry merely because its label matches one word from the target. For
visual objects, shapes, image contents, document contents, canvas objects, or
other things that may not be UI components, direct x/y grounding is allowed.

Reply with ONLY this JSON object:
{{"reasoning": "one short sentence explaining why the target is satisfied",
  "name": "exact label from the lists if using a listed entry, otherwise \\"\\"",
  "x": 0,
  "y": 0,
  "grounding_type": "listed_entry or direct_pixel",
  "confidence": 0.0}}"""

    reply = rt.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])

    try:
        result = parse_json(reply)
    except Exception as _e:
        print(
            f"  [phase3] parse FAILED ({_e.__class__.__name__}); raw reply:\n{reply[:800]}",
            file=sys.stderr,
        )
        return {"found": False, "reasoning": f"Parse failed: {reply[:200]}"}

    reasoning = result.get("reasoning", "")
    name = (result.get("name") or "").strip()
    grounding_type = (result.get("grounding_type") or "").strip()

    lookup: dict[str, tuple[int, int]] = {}
    for c in known_components:
        lookup[c["name"]] = (c["cx"], c["cy"])
    for t in texts[:60]:
        label = t.get("label", "")
        if label:
            lookup[label] = (t.get("cx", 0), t.get("cy", 0))

    if name:
        if name not in lookup:
            print(
                f"  [phase3] name={name!r} not in lists. reasoning: {reasoning[:400]}",
                file=sys.stderr,
            )
            return {"found": False, "reasoning": reasoning}

        cx, cy = lookup[name]
        if cx <= 0 or cy <= 0:
            print(
                f"  [phase3] entry {name!r} has bad coords ({cx},{cy})",
                file=sys.stderr,
            )
            return {"found": False, "reasoning": f"entry {name!r} has bad coords"}

        return {
            "found": True,
            "name": name,
            "cx": cx,
            "cy": cy,
            "source": "listed_entry",
            "grounding_type": grounding_type or "listed_entry",
            "reasoning": reasoning,
        }

    try:
        cx = int(round(float(result.get("x", 0))))
        cy = int(round(float(result.get("y", 0))))
    except (TypeError, ValueError):
        cx = cy = 0

    if cx <= 0 or cy <= 0 or cx > img_w or cy > img_h:
        print(
            f"  [phase3] no listed entry and bad direct coords ({cx},{cy}). reasoning: {reasoning[:400]}",
            file=sys.stderr,
        )
        return {"found": False, "reasoning": reasoning}

    return {
        "found": True,
        "name": "direct_pixel",
        "cx": cx,
        "cy": cy,
        "source": "direct_pixel_grounding",
        "grounding_type": grounding_type or "direct_pixel",
        "reasoning": reasoning,
    }


# ═══════════════════════════════════════════
# Phase 4: Label unknown components one by one
# ═══════════════════════════════════════════

@agentic_function(render_range={"callers": 0})
def label_single_component(
    task: str,
    target: str,
    component_crop_path: str,
    component_index: int,
    component_bbox: dict,
    runtime=None,
) -> dict:
    """Identify a single UI component from its cropped screenshot."""
    from gui_harness.utils import parse_json

    if runtime is None:
        raise ValueError("label_single_component() requires a runtime argument")
    rt = runtime

    context = f"""Task: {task}
Target element: {target}

This is component #{component_index} at position ({component_bbox['cx']}, {component_bbox['cy']}), size {component_bbox['w']}x{component_bbox['h']}.

You see a cropped image of this one UI component. Decide what it is and
give it a descriptive snake_case name (e.g. "search_bar",
"close_button"); if it is blank, decorative, or meaningless use "skip".
Also decide whether it is the target element described above.

Reply with ONLY this JSON object:
{{"label": "descriptive_name or skip", "is_target": true,
  "reasoning": "what this component appears to be"}}"""

    reply = rt.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": component_crop_path},
    ])

    try:
        return parse_json(reply)
    except Exception:
        return {"label": "skip", "is_target": False, "reasoning": f"Parse failed: {reply[:200]}"}


def label_unknown_components(
    task: str,
    target: str,
    icons: list[dict],
    known_names: set[str],
    img_path: str,
    app_name: str,
    runtime=None,
) -> Optional[dict]:
    """Phase 4: Label unknown components one by one until target is found.

    Iterates through detected icons (sorted by confidence descending).
    For each unknown component:
      1. Crop it from the screenshot
      2. Send to LLM for labeling
      3. If labeled (not "skip"), save to memory
      4. If it's the target, stop and return coordinates

    Args:
        task: The overall task description
        target: Description of the target element
        icons: GPA-detected components, sorted by confidence desc
        known_names: Set of component names already matched from memory
        img_path: Path to the full screenshot
        app_name: App name for memory storage
        runtime: openprogram Runtime instance

    Returns:
        dict with {cx, cy, name} if target found, None otherwise.
    """
    screen_img = cv2.imread(img_path)
    if screen_img is None:
        return None

    app_dir = app_memory.get_app_dir(app_name)
    components_dir = app_dir / "components"
    components_dir.mkdir(parents=True, exist_ok=True)

    # Track temporary crop files for cleanup (Phase 5)
    temp_crops = []

    for i, icon in enumerate(icons):
        # Skip tiny elements. Multiscale detections have already been enlarged
        # before detection, so keep smaller mapped boxes.
        min_size = 8 if icon.get("source") == "gpa_detector_multiscale" else 25
        if icon.get("w", 0) < min_size or icon.get("h", 0) < min_size:
            continue

        # Skip already-known components (matched in Phase 2)
        # We check by approximate position overlap with known components
        # (A more sophisticated check could use IoU)

        # Crop this component from the screenshot
        x = icon.get("x", 0)
        y = icon.get("y", 0)
        w = icon.get("w", 0)
        h = icon.get("h", 0)

        # Add padding
        pad = 16 if icon.get("source") == "gpa_detector_multiscale" else 4
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(screen_img.shape[0], y + h + pad)
        x2 = min(screen_img.shape[1], x + w + pad)

        crop = screen_img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        # Check if this crop duplicates an existing saved component
        is_dup, dup_name = app_memory.is_duplicate_icon(crop, components_dir)
        if is_dup:
            continue

        # Save temporary crop for LLM to see
        crop_path = str(components_dir / f"_unlabeled_{i:03d}.png")
        cv2.imwrite(crop_path, crop)
        temp_crops.append(crop_path)

        # Ask LLM to label this component
        result = label_single_component(
            task=task,
            target=target,
            component_crop_path=crop_path,
            component_index=i,
            component_bbox={
                "cx": icon.get("cx", 0),
                "cy": icon.get("cy", 0),
                "w": w,
                "h": h,
            },
            runtime=runtime,
        )

        label = result.get("label", "skip")
        is_target = result.get("is_target", False)

        if label and label != "skip":
            # Rename temporary crop to proper label
            safe_label = label.replace("/", "-").replace(" ", "_").replace(":", "")[:50]
            final_path = str(components_dir / f"{safe_label}.png")

            # Don't overwrite existing components
            if not os.path.exists(final_path):
                os.rename(crop_path, final_path)
                temp_crops.remove(crop_path)

                # Save to components.json (no position — it changes every time)
                components = app_memory.load_components(app_dir)
                components[label] = {
                    "type": icon.get("type", "icon"),
                    "source": "gpa_detector",
                    "icon_file": f"components/{safe_label}.png",
                    "label": label,
                    "learned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "seen_count": 1,
                    "consecutive_misses": 0,
                }
                app_memory.save_components(app_dir, components)

        if is_target:
            # Phase 5: Cleanup before returning
            _cleanup_temp_crops(temp_crops)
            return {
                "cx": icon.get("cx", 0),
                "cy": icon.get("cy", 0),
                "name": label if label != "skip" else f"component_{i}",
            }

    # Phase 5: Cleanup all remaining temp crops
    _cleanup_temp_crops(temp_crops)
    return None


# ═══════════════════════════════════════════
# Phase 5: Cleanup
# ═══════════════════════════════════════════

def _cleanup_temp_crops(temp_crops: list[str]):
    """Delete temporary unlabeled crop files."""
    for path in temp_crops:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _active_localization_confident(location: Optional[dict]) -> bool:
    """Return True when active localization produced enough evidence to stop."""
    if not location or not active_localization.enabled():
        return False
    if os.environ.get("GUI_HARNESS_ACTIVE_EARLY_RETURN", "1").lower() not in {"1", "true", "yes"}:
        return False

    verifier = location.get("pre_click_verifier") or {}
    if (
        str(verifier.get("is_target", "")).lower() == "yes"
        and str(verifier.get("suggestion", "")).lower() != "zoom"
    ):
        return True
    return False


# ═══════════════════════════════════════════
# Main entry point: locate_target
# ═══════════════════════════════════════════

def locate_target(
    task: str,
    target: str,
    img_path: str,
    app_name: str = "desktop",
    runtime=None,
    config=None,
) -> Optional[dict]:
    """Complete Phase 1-5 flow to find a target element on screen.

    ``config`` is an optional ScreenSpotLocatorConfig forwarded to the
    ScreenSpot locator. When None the locator falls back to from_env(), so
    existing callers are unaffected.

    This is the single entry point called by execute_task when an action
    needs coordinates.

    Phase 1: Detect all components (GPA + OCR)
    Phase 2: Match against saved memory
    Phase 3: Ask LLM if target is among known components
    Phase 4: Label unknown components (stop when target found)
    Phase 5: Cleanup

    Args:
        task: Natural language task description
        target: Description of the element to locate
        img_path: Path to the current screenshot
        app_name: App name for memory lookup/storage
        runtime: openprogram Runtime instance

    Returns:
        dict with {cx, cy, name, timing} if found, None if not found.
    """
    _timing = {}

    # Diagnostic: log the verbatim target string so we can see if Plan wrote
    # noisy content (coordinates, "menu item" suffixes, etc.) into it.
    print(f"  [locate] target={target!r}", file=sys.stderr)

    # Phase 1: Detection
    t0 = time.time()
    use_multiscale = os.environ.get("GUI_HARNESS_MULTISCALE_DETECT", "").lower() in {"1", "true", "yes"}
    detection = detect_components(img_path, multiscale=use_multiscale)
    icons = detection["icons"]
    if use_multiscale:
        icons = _rank_icons_for_screenspot(icons)
        print(f"  [locate] multiscale shortlist: {len(icons)} icons for Phase 4", file=sys.stderr)
    texts = detection["texts"]
    base_active_candidates = active_localization.build_candidates([], texts, icons)
    _timing["phase1_detect"] = round(time.time() - t0, 2)
    print(f"  [locate] Phase 1: {len(icons)} icons, {len(texts)} texts ({_timing['phase1_detect']}s)", file=sys.stderr)

    coord_hit = _extract_target_coordinates(target, detection["img_w"], detection["img_h"])
    if coord_hit:
        coord_hit["timing"] = _timing
        print(
            f"  [locate] coordinate fallback: ({coord_hit['cx']}, {coord_hit['cy']})",
            file=sys.stderr,
        )
        return coord_hit

    # Diagnostic: dump a preview of OCR texts so we can compare against what
    # Plan referenced and see whether the target's words appear on screen.
    ocr_snippets = [
        f"'{(t.get('label') or '')[:40]}'@({t.get('cx', 0)},{t.get('cy', 0)})"
        for t in texts[:20]
        if len(t.get("label") or "") > 1
    ]
    if ocr_snippets:
        print(f"  [locate] OCR[:20] = {' | '.join(ocr_snippets)}", file=sys.stderr)

    if app_name == "screenspot_pro":
        print("  [locate] ScreenSpot locator enabled; skipping memory/Phase4", file=sys.stderr)
        located = screenspot_locator.screenspot_locate(
            task=task,
            target=target,
            img_path=img_path,
            img_w=detection["img_w"],
            img_h=detection["img_h"],
            candidates=base_active_candidates,
            runtime=runtime,
            work_dir=os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR"),
            config=config,
        )
        if located:
            located["timing"] = _timing
            print(
                f"  [locate] ScreenSpot locator result: name='{located.get('name', '?')}' "
                f"at ({located.get('cx', 0)}, {located.get('cy', 0)})",
                file=sys.stderr,
            )
            return located
        print("  [locate] ScreenSpot locator found no verified target", file=sys.stderr)
        return None

    # Phase 1.5: OCR labels have coordinates already, so handle obvious text
    # targets before spending a model call on the same list.
    t0 = time.time()
    text_match = _deterministic_text_match(target, texts)
    _timing["phase1_5_ocr"] = round(time.time() - t0, 2)
    if text_match:
        print(
            f"  [locate] OCR match: name='{text_match.get('name', '?')}' at ({text_match.get('cx', 0)}, {text_match.get('cy', 0)})",
            file=sys.stderr,
        )
        located = {
            "cx": text_match.get("cx", 0),
            "cy": text_match.get("cy", 0),
            "name": text_match.get("name", target),
            "timing": _timing,
        }
        located = active_localization.improve_location(
            task=task,
            target=target,
            img_path=img_path,
            img_w=detection["img_w"],
            img_h=detection["img_h"],
            candidates=base_active_candidates,
            proposed=located,
            runtime=runtime,
            work_dir=os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR"),
        ) or located
        located["timing"] = _timing
        return located

    # Phase 2: Memory matching
    t0 = time.time()
    known_components = match_memory_components(app_name, img_path)
    known_names = {c["name"] for c in known_components}
    _timing["phase2_memory"] = round(time.time() - t0, 2)
    print(f"  [locate] Phase 2: {len(known_components)} matched ({_timing['phase2_memory']}s)", file=sys.stderr)

    t0 = time.time()
    known_match = _deterministic_text_match(target, known_components)
    _timing["phase2_5_known"] = round(time.time() - t0, 2)
    if known_match:
        print(
            f"  [locate] Known match: name='{known_match.get('name', '?')}' at ({known_match.get('cx', 0)}, {known_match.get('cy', 0)})",
            file=sys.stderr,
        )
        active_candidates = active_localization.build_candidates(known_components, texts, icons)
        located = {
            "cx": known_match.get("cx", 0),
            "cy": known_match.get("cy", 0),
            "name": known_match.get("name", target),
            "timing": _timing,
        }
        located = active_localization.improve_location(
            task=task,
            target=target,
            img_path=img_path,
            img_w=detection["img_w"],
            img_h=detection["img_h"],
            candidates=active_candidates,
            proposed=located,
            runtime=runtime,
            work_dir=os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR"),
        ) or located
        located["timing"] = _timing
        return located

    # Also include OCR texts as "known" elements (they have labels + coordinates)
    all_known = list(known_components)
    for t in texts:
        all_known.append({
            "name": t.get("label", ""),
            "cx": t.get("cx", 0),
            "cy": t.get("cy", 0),
            "w": t.get("w", 0),
            "h": t.get("h", 0),
            "confidence": 1.0,
            "source": "ocr",
        })
    active_candidates = active_localization.build_candidates(known_components, texts, icons)

    # Phase 3: Ask LLM to find target in known components
    t0 = time.time()
    phase3_direct_pixel_fallback = None
    if all_known:
        result = find_target_in_known(
            task=task,
            target=target,
            known_components=all_known,
            texts=texts,
            img_path=img_path,
            img_w=detection["img_w"],
            img_h=detection["img_h"],
            runtime=runtime,
        )
        _timing["phase3_llm"] = round(time.time() - t0, 2)
        print(f"  [locate] Phase 3: found={result.get('found', False)} ({_timing['phase3_llm']}s)", file=sys.stderr)
        if result.get("found"):
            print(f"  [locate] Phase 3 result: name='{result.get('name', '?')}' at ({result.get('cx', 0)}, {result.get('cy', 0)})", file=sys.stderr)
            located = {
                "cx": result.get("cx", 0),
                "cy": result.get("cy", 0),
                "name": result.get("name", target),
                "source": result.get("source", "phase3_llm"),
                "grounding_type": result.get("grounding_type", ""),
                "reasoning": result.get("reasoning", ""),
                "timing": _timing,
            }
            located = active_localization.improve_location(
                task=task,
                target=target,
                img_path=img_path,
                img_w=detection["img_w"],
                img_h=detection["img_h"],
                candidates=active_candidates,
                proposed=located,
                runtime=runtime,
                work_dir=os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR"),
            ) or located
            located["timing"] = _timing
            if _active_localization_confident(located):
                print("  [locate] active localization confident; skipping Phase 4", file=sys.stderr)
                return located
            if use_multiscale:
                phase3_direct_pixel_fallback = located
                print(
                    "  [locate] Phase 3 result deferred; trying multiscale candidates",
                    file=sys.stderr,
                )
            else:
                return located

    # Phase 4: Label unknown components one by one
    t0 = time.time()
    found = label_unknown_components(
        task=task,
        target=target,
        icons=icons,
        known_names=known_names,
        img_path=img_path,
        app_name=app_name,
        runtime=runtime,
    )
    _timing["phase4_label"] = round(time.time() - t0, 2)
    print(f"  [locate] Phase 4: found={'yes' if found else 'no'} ({_timing['phase4_label']}s)", file=sys.stderr)
    if found:
        print(f"  [locate] Phase 4 result: name='{found.get('name', '?')}' at ({found.get('cx', 0)}, {found.get('cy', 0)})", file=sys.stderr)

    if found:
        found["timing"] = _timing
        found = active_localization.improve_location(
            task=task,
            target=target,
            img_path=img_path,
            img_w=detection["img_w"],
            img_h=detection["img_h"],
            candidates=active_candidates,
            proposed=found,
            runtime=runtime,
            work_dir=os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR"),
        ) or found
        found["timing"] = _timing
        return found
    if phase3_direct_pixel_fallback:
        print("  [locate] using deferred Phase 3 direct pixel fallback", file=sys.stderr)
        phase3_direct_pixel_fallback = active_localization.improve_location(
            task=task,
            target=target,
            img_path=img_path,
            img_w=detection["img_w"],
            img_h=detection["img_h"],
            candidates=active_candidates,
            proposed=phase3_direct_pixel_fallback,
            runtime=runtime,
            work_dir=os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR"),
        ) or phase3_direct_pixel_fallback
        phase3_direct_pixel_fallback["timing"] = _timing
        return phase3_direct_pixel_fallback
    return None


def _extract_target_coordinates(target: str, img_w: int, img_h: int) -> Optional[dict]:
    """Return explicit coordinates embedded in a target string, if valid."""
    match = re.search(r"\((\d{1,4})\s*,\s*(\d{1,4})\)", target or "")
    if not match:
        return None
    cx, cy = int(match.group(1)), int(match.group(2))
    if cx <= 0 or cy <= 0 or cx > img_w or cy > img_h:
        return None
    return {
        "cx": cx,
        "cy": cy,
        "name": target,
        "source": "target_coordinates",
    }


# ═══════════════════════════════════════════
# State identification & transition graph
# ═══════════════════════════════════════════

def identify_state(app_name: str, img_path: str) -> tuple[Optional[str], set[str]]:
    """Identify the current state by matching components on screen.

    Takes a screenshot, runs template matching against saved components,
    then uses the matched component set to identify the state via Jaccard.

    If the state is new (Jaccard < 0.7 against all known states), creates
    a new state entry.

    Returns:
        (state_id, matched_component_names)
        state_id is None if no components are saved yet.
    """
    app_dir = app_memory.get_app_dir(app_name)

    # Template match to find visible components
    matched = match_memory_components(app_name, img_path)
    matched_names = {c["name"] for c in matched}

    if not matched_names:
        return None, matched_names

    # Load state and component data
    states = app_memory.load_states(app_dir)
    components = app_memory.load_components(app_dir)

    # Identify or create state
    state_id, states = app_memory.identify_or_create_state(
        states, matched_names, components
    )
    app_memory.save_states(app_dir, states)

    return state_id, matched_names


def record_transition(
    app_name: str,
    from_state: Optional[str],
    action: str,
    action_target: str,
    to_state: Optional[str],
):
    """Record a state transition in the transition graph.

    Stores: (from_state, action:target) → to_state

    Only records if both states are identified (not None).
    Deduplicates by key — same transition overwrites.
    """
    if from_state is None or to_state is None:
        return

    app_dir = app_memory.get_app_dir(app_name)
    transitions = app_memory.load_transitions(app_dir)

    key = f"{from_state}|{action}:{action_target}"
    transitions[key] = {
        "from": from_state,
        "to": to_state,
        "action": action,
        "target": action_target,
        "last_used": time.strftime("%Y-%m-%d %H:%M:%S"),
        "use_count": transitions.get(key, {}).get("use_count", 0) + 1,
    }

    app_memory.save_transitions(app_dir, transitions)


def get_available_transitions(app_name: str, current_state: str) -> list[dict]:
    """Get all known transitions from the current state.

    Returns a list of possible actions with their expected next states.
    Sorted by use_count descending (most used first).

    Returns:
        list[dict]: Each dict has keys:
            - action: str (e.g., "click", "shortcut")
            - target: str (e.g., "save_button", "ctrl+s")
            - to_state: str (state ID)
            - use_count: int
    """
    if current_state is None:
        return []

    app_dir = app_memory.get_app_dir(app_name)
    transitions = app_memory.load_transitions(app_dir)

    available = []
    for key, trans in transitions.items():
        if trans.get("from") == current_state:
            available.append({
                "action": trans["action"],
                "target": trans["target"],
                "to_state": trans["to"],
                "use_count": trans.get("use_count", 1),
            })

    available.sort(key=lambda t: t["use_count"], reverse=True)
    return available


@agentic_function(render_range={"callers": 0})
def select_transition(
    task: str,
    current_state: str,
    available_transitions: list[dict],
    runtime=None,
) -> dict:
    """Select the best known transition from the current state for the task."""
    from gui_harness.utils import parse_json

    if runtime is None:
        raise ValueError("select_transition() requires a runtime argument")
    rt = runtime

    trans_lines = "\n".join(
        f"  [{i}] {t['action']}:{t['target']} → state {t['to_state']} (used {t['use_count']}x)"
        for i, t in enumerate(available_transitions)
    )

    context = f"""Task: {task}
Current state: {current_state}

Known transitions from this state (each: action, target, expected next
state, use_count):
{trans_lines}

If one transition is clearly the right next step for the task, select
it; if none are relevant, return selected=false.

Reply with ONLY this JSON object:
{{"selected": true, "index": 0, "reasoning": "why this transition"}}"""

    reply = rt.exec(content=[{"type": "text", "text": context}])

    try:
        return parse_json(reply)
    except Exception:
        return {"selected": False, "reasoning": f"Parse failed: {reply[:200]}"}
