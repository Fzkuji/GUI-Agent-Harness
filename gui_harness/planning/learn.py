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

from gui_harness.openprogram_compat import agentic_function

from gui_harness.utils import parse_json
from gui_harness.perception import screenshot, detector
from gui_harness.memory import app_memory


def has_base_memory(app_name: str) -> bool:
    """Check if an app already has base memory from a previous learn."""
    app_dir = app_memory.get_app_dir(app_name)
    meta = app_memory.load_meta(app_dir)
    return bool(meta.get("base_memory_learned_at"))


def learn_app_components(
    app_name: str,
    img_path: str | None = None,
    tour: list | None = None,
    batch_size: int = 50,
    runtime=None,
    force: bool = False,
    settle: float = 1.0,
) -> dict:
    """Learn all UI components for an app via numbered screenshot + batch LLM labeling.

    Three modes:
    1. Single-shot (default): capture one screenshot, label, save.
    2. Explicit tour: caller passes a list of tour steps; the function drives
       the UI through each state and learns at every screen, accumulating into
       the same base memory. This covers menus/dialogs that the startup screen
       can't show.
    3. Auto tour: if tour is None and TOURS[app_name] is registered, that tour
       is used automatically. Pass tour=[] to force single-shot.

    Args:
        app_name: Name of the app (e.g., "firefox", "gimp", "libreoffice_calc").
        img_path: Screenshot path (single-shot mode only). None = auto-capture.
        tour: List of tour steps. Each step is a dict:
                {"state": "human-readable name",
                 "setup": [action, ...],          # actions to reach this state
                 "reset": [action, ...]}          # optional; default = 2× Escape
              Each action is a tuple:
                ("hotkey", "alt+f") | ("key", "Escape") | ("click", x, y) |
                ("type", "hello") | ("wait", 0.5)
        batch_size: Max components per LLM call (default 50).
        runtime: openprogram Runtime instance.
        force: Re-learn even if base memory exists.
        settle: Seconds to wait between setup and screenshot (default 1.0).

    Returns:
        {"app_name": str, "components_saved": int, "components_skipped": int,
         "states_visited": int, "timing": {"detect": float, "label": float,
         "save": float}}
    """
    if runtime is None:
        raise ValueError("This function requires a runtime argument")

    # Check existing base memory
    if not force and has_base_memory(app_name):
        return {
            "app_name": app_name,
            "components_saved": 0,
            "components_skipped": 0,
            "already_learned": True,
        }

    # Resolve tour (explicit > registry > single-shot)
    if tour is None:
        from gui_harness.planning.tours import TOURS
        tour = TOURS.get(app_name)

    # Collect per-screen results
    screens: list[tuple[str, str | None]] = []  # (state_name, img_path)
    if tour:
        for step in tour:
            state_name = step.get("state", "unnamed")
            for action in step.get("setup", []):
                _run_tour_action(action)
            time.sleep(settle)
            shot = screenshot.take()
            screens.append((state_name, shot))
            reset = step.get("reset")
            if reset is None:
                reset = [("key", "Escape"), ("key", "Escape")]
            for action in reset:
                _run_tour_action(action)
            time.sleep(0.3)
    else:
        screens.append(("initial", img_path))  # None triggers capture below

    # Accumulate across all screens
    totals = {"saved": 0, "skipped": 0, "detect": 0.0, "label": 0.0, "save": 0.0}
    for state_name, shot in screens:
        r = _learn_one_screen(app_name, shot, runtime, batch_size)
        print(
            f"  [learn/{state_name}] saved={r['saved']} skipped={r['skipped']} "
            f"(detect={r['t_detect']:.1f}s label={r['t_label']:.1f}s)",
            file=sys.stderr,
        )
        totals["saved"] += r["saved"]
        totals["skipped"] += r["skipped"]
        totals["detect"] += r["t_detect"]
        totals["label"] += r["t_label"]
        totals["save"] += r["t_save"]

    # Mark base memory once (regardless of how many screens learned)
    app_dir = app_memory.get_app_dir(app_name)
    meta = app_memory.load_meta(app_dir)
    meta["app"] = app_name
    meta["base_memory_learned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["base_memory_components"] = totals["saved"]
    meta["base_memory_states_visited"] = len(screens)
    app_memory.save_meta(app_dir, meta)

    return {
        "app_name": app_name,
        "components_saved": totals["saved"],
        "components_skipped": totals["skipped"],
        "states_visited": len(screens),
        "timing": {
            "detect": round(totals["detect"], 2),
            "label": round(totals["label"], 2),
            "save": round(totals["save"], 2),
        },
    }


def _learn_one_screen(
    app_name: str,
    img_path: str | None,
    runtime,
    batch_size: int,
) -> dict:
    """Label and save components from a single screenshot. Returns per-call counts."""
    t0 = time.time()
    if img_path is None:
        img_path = screenshot.take()

    det = detector.detect_all(img_path, conf=0.3)
    icons = det[0] if isinstance(det, tuple) else det.get("icons", [])
    if isinstance(det, tuple):
        icons = det[0]
    t_detect = time.time() - t0

    icons = [ic for ic in icons if ic.get("w", 0) >= 25 and ic.get("h", 0) >= 25]
    icons = sorted(icons, key=lambda e: e.get("confidence", 0), reverse=True)

    if not icons:
        return {"saved": 0, "skipped": 0, "t_detect": t_detect, "t_label": 0.0, "t_save": 0.0}

    annotated_path = detector.annotate_numbered(img_path, icons)

    t1 = time.time()
    labels = {}
    for batch_start in range(0, len(icons), batch_size):
        batch_icons = icons[batch_start:batch_start + batch_size]
        batch_labels = _batch_label(
            app_name=app_name,
            icons=batch_icons,
            annotated_path=annotated_path,
            offset=batch_start,
            runtime=runtime,
        )
        labels.update(batch_labels)
    t_label = time.time() - t1

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
        pad = 4
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(screen_img.shape[0], y + h + pad)
        x2 = min(screen_img.shape[1], x + w + pad)
        crop = screen_img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        is_dup, _ = app_memory.is_duplicate_icon(crop, components_dir)
        if is_dup:
            skipped += 1
            continue

        safe_label = label.replace("/", "-").replace(" ", "_").replace(":", "")[:50]
        final_path = str(components_dir / f"{safe_label}.png")
        if not os.path.exists(final_path):
            cv2.imwrite(final_path, crop)

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

    if annotated_path and os.path.exists(annotated_path):
        os.remove(annotated_path)

    return {"saved": saved, "skipped": skipped, "t_detect": t_detect, "t_label": t_label, "t_save": t_save}


def _run_tour_action(action) -> None:
    """Execute one tour action. Supports tuple form."""
    from gui_harness.action import input as _input
    kind = action[0]
    if kind == "hotkey":
        keys = action[1].split("+")
        _input.key_combo(*keys)
    elif kind == "key":
        _input.key_press(action[1])
    elif kind == "click":
        _input.mouse_click(action[1], action[2])
    elif kind == "type":
        _input.type_text(action[1])
    elif kind == "wait":
        time.sleep(action[1])
    else:
        raise ValueError(f"Unknown tour action: {kind}")


@agentic_function(render_range={"depth": 0, "siblings": 0})
def _batch_label(
    app_name: str,
    icons: list[dict],
    annotated_path: str,
    offset: int = 0,
    runtime=None,
) -> dict:
    """Label every UI component in a numbered screenshot."""
    if runtime is None:
        raise ValueError("This function requires a runtime argument")
    rt = runtime

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

    data = f"""App: {app_name}

Components:
{chr(10).join(comp_lines)}

The screenshot has numbered bounding boxes around the detected UI
elements above. For EACH numbered component, give a descriptive
snake_case name (max 30 chars) that says what it IS and DOES — e.g.
"search_bar", "save_button" (not just "button"), "settings_icon",
"file_menu", "bold_toggle". Incorporate the OCR text when it is
descriptive. Use "skip" for decorative, blank, or non-interactive
elements.

Reply with ONLY a JSON object mapping each number to its name:
{{"0": "search_bar", "1": "skip", "2": "close_button"}}"""

    reply = rt.exec(content=[
        {"type": "text", "text": data},
        {"type": "image", "path": annotated_path},
    ])

    try:
        result = parse_json(reply)
        # Normalize keys to strings
        return {str(k): str(v) for k, v in result.items()}
    except Exception:
        # If parsing fails, return all as skip
        return {str(offset + i): "skip" for i in range(len(icons))}
