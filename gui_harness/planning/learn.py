"""
learn — batch-learn an app's UI components using numbered screenshot + single LLM call.

Two-phase design:
  1. Learn phase (once per app): detect all components, draw numbered screenshot,
     LLM labels everything in one call, save as "base memory".
  2. Task phase: load base memory, template match. No Phase 4 labeling needed.

Base memory is persistent across tasks and exempt from the forget mechanism.
Task-time discoveries (Phase 4) are ephemeral and NOT saved to disk.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import cv2

from agentic import agentic_function

from gui_harness.utils import parse_json
from gui_harness.perception import screenshot, detector
from gui_harness.memory import app_memory


_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


def has_base_memory(app_name: str) -> bool:
    """Check if an app already has base memory from a previous learn."""
    app_dir = app_memory.get_app_dir(app_name)
    meta = app_memory.load_meta(app_dir)
    return bool(meta.get("base_memory_learned_at"))


def learn_app_components(
    app_name: str,
    img_path: str | None = None,
    batch_size: int = 50,
    runtime=None,
    force: bool = False,
) -> dict:
    """Learn all UI components for an app via numbered screenshot + batch LLM labeling.

    Takes a screenshot, runs GPA detection, draws numbered bounding boxes,
    sends ONE annotated image to LLM for batch labeling, then crops and saves
    each labeled component as base memory.

    This replaces 60+ individual LLM calls (Phase 4) with 1-2 batch calls.

    Args:
        app_name: Name of the app (e.g., "firefox", "libreoffice_calc")
        img_path: Screenshot path. None = auto-capture from VM or local.
        batch_size: Max components per LLM call (default 50).
        runtime: GUIRuntime instance.
        force: Re-learn even if base memory exists.

    Returns:
        {"app_name": str, "components_saved": int, "components_skipped": int,
         "timing": {"detect": float, "label": float, "save": float}}
    """
    rt = runtime or _get_runtime()

    # Check existing base memory
    if not force and has_base_memory(app_name):
        return {
            "app_name": app_name,
            "components_saved": 0,
            "components_skipped": 0,
            "already_learned": True,
        }

    # Step 1: Screenshot + detection
    t0 = time.time()
    if img_path is None:
        img_path = screenshot.take()

    det = detector.detect_all(img_path, conf=0.3)
    icons = det[0] if isinstance(det, tuple) else det.get("icons", [])
    # detect_all returns (icons, texts, merged, img_w, img_h) tuple
    if isinstance(det, tuple):
        icons = det[0]
    t_detect = time.time() - t0

    # Filter tiny elements
    icons = [ic for ic in icons if ic.get("w", 0) >= 25 and ic.get("h", 0) >= 25]
    # Sort by confidence descending
    icons = sorted(icons, key=lambda e: e.get("confidence", 0), reverse=True)

    if not icons:
        return {
            "app_name": app_name,
            "components_saved": 0,
            "components_skipped": 0,
            "timing": {"detect": t_detect, "label": 0, "save": 0},
        }

    # Step 2: Create numbered annotated screenshot
    annotated_path = detector.annotate_numbered(img_path, icons)

    # Step 3: Batch LLM labeling
    t1 = time.time()
    labels = {}

    for batch_start in range(0, len(icons), batch_size):
        batch_icons = icons[batch_start:batch_start + batch_size]
        batch_labels = _batch_label(
            app_name=app_name,
            icons=batch_icons,
            annotated_path=annotated_path,
            offset=batch_start,
            runtime=rt,
        )
        labels.update(batch_labels)

    t_label = time.time() - t1

    # Step 4: Crop + save components
    t2 = time.time()
    screen_img = cv2.imread(img_path)
    app_dir = app_memory.get_app_dir(app_name)
    components_dir = app_dir / "components"
    components_dir.mkdir(parents=True, exist_ok=True)

    components = app_memory.load_components(app_dir)
    saved = 0
    skipped = 0

    for idx_str, label in labels.items():
        idx = int(idx_str)
        if idx >= len(icons):
            continue
        if label == "skip" or not label:
            skipped += 1
            continue

        icon = icons[idx]
        x, y, w, h = icon["x"], icon["y"], icon["w"], icon["h"]

        # Crop with padding
        pad = 4
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(screen_img.shape[0], y + h + pad)
        x2 = min(screen_img.shape[1], x + w + pad)
        crop = screen_img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        # Check for duplicates
        is_dup, dup_name = app_memory.is_duplicate_icon(crop, components_dir)
        if is_dup:
            skipped += 1
            continue

        # Save crop
        safe_label = label.replace("/", "-").replace(" ", "_").replace(":", "")[:50]
        final_path = str(components_dir / f"{safe_label}.png")
        if not os.path.exists(final_path):
            cv2.imwrite(final_path, crop)

        # Save to components.json with base_memory flag
        components[label] = {
            "type": icon.get("type", "icon"),
            "source": "learn_batch",
            "icon_file": f"components/{safe_label}.png",
            "label": label,
            "learned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seen_count": 1,
            "consecutive_misses": 0,
            "base_memory": True,
        }
        saved += 1

    app_memory.save_components(app_dir, components)
    t_save = time.time() - t2

    # Step 5: Mark base memory in meta
    meta = app_memory.load_meta(app_dir)
    meta["app"] = app_name
    meta["base_memory_learned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["base_memory_components"] = saved
    app_memory.save_meta(app_dir, meta)

    # Cleanup annotated image
    if annotated_path and os.path.exists(annotated_path):
        os.remove(annotated_path)

    return {
        "app_name": app_name,
        "components_saved": saved,
        "components_skipped": skipped,
        "timing": {"detect": round(t_detect, 2), "label": round(t_label, 2), "save": round(t_save, 2)},
    }


@agentic_function(summarize={"depth": 0, "siblings": 0})
def _batch_label(
    app_name: str,
    icons: list[dict],
    annotated_path: str,
    offset: int = 0,
    runtime=None,
) -> dict:
    """Send numbered screenshot to LLM for batch component labeling.

    Returns dict mapping str(index) -> label (e.g., {"0": "search_bar", "1": "skip"}).
    """
    rt = runtime or _get_runtime()

    # Build component list text
    comp_lines = []
    for i, icon in enumerate(icons):
        idx = offset + i
        ocr_hint = f" ocr='{icon['label']}'" if icon.get("label") else ""
        comp_lines.append(
            f"  [{idx}] at ({icon.get('cx', 0)}, {icon.get('cy', 0)}) "
            f"size {icon.get('w', 0)}x{icon.get('h', 0)} "
            f"conf={icon.get('confidence', 0):.2f}{ocr_hint}"
        )

    prompt = f"""You are labeling UI components in a screenshot of {app_name}.

The screenshot has numbered bounding boxes around detected UI elements.
Below is a list of each component with its number, position, size, and any OCR text.

{chr(10).join(comp_lines)}

For EACH numbered component, provide a descriptive snake_case name that describes
what the component IS and DOES (e.g., "search_bar", "close_button", "settings_icon",
"file_menu", "bold_toggle", "navigation_sidebar").

Rules:
- Use snake_case, max 30 chars
- Return "skip" for decorative, blank, or non-interactive elements
- Include the component's function in the name (e.g., "save_button" not just "button")
- If OCR text is available and descriptive, incorporate it

Return ONLY a JSON object mapping number to name:
{{"0": "search_bar", "1": "skip", "2": "close_button", ...}}"""

    reply = rt.exec(content=[
        {"type": "text", "text": prompt},
        {"type": "image", "path": annotated_path},
    ])

    try:
        result = parse_json(reply)
        # Normalize keys to strings
        return {str(k): str(v) for k, v in result.items()}
    except Exception:
        # If parsing fails, return all as skip
        return {str(offset + i): "skip" for i in range(len(icons))}
