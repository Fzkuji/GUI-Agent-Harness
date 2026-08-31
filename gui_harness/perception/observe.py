"""Canonical screen observation for the desktop runner."""

from __future__ import annotations

import os
import shutil
import sys
import time

from gui_harness.perception import screenshot
from gui_harness.action.input import get_frontmost_app
from gui_harness.planning.component_memory import (
    detect_components,
    get_available_transitions,
    identify_state,
    match_memory_components,
)

try:
    from openprogram.agent.run_control import check_cancelled
except Exception:  # standalone use without the OpenProgram host layer
    def check_cancelled() -> None:
        return None


def _copy_artifact(src: str, name: str) -> str | None:
    out_dir = os.environ.get("GUI_HARNESS_ARTIFACT_DIR")
    if not out_dir or not src or not os.path.exists(src):
        return None
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, name)
    try:
        shutil.copy2(src, dst)
        return dst
    except Exception:
        return None


def observe_screen(app_name: str) -> dict:
    """Capture one screen and derive all state used by verify and plan."""
    started = time.time()
    check_cancelled()
    settle_seconds = max(
        0.0, float(os.environ.get("GUI_HARNESS_UI_SETTLE_SECONDS", "0.8")),
    )
    time.sleep(settle_seconds)
    img_path = screenshot.take()

    check_cancelled()
    phase_started = time.time()
    detection = detect_components(img_path)
    icons = detection.get("icons", []) if isinstance(detection, dict) else []
    texts = detection.get("texts", []) if isinstance(detection, dict) else []
    detect_seconds = round(time.time() - phase_started, 2)
    frontmost_app = get_frontmost_app()

    check_cancelled()
    if app_name.strip().lower() == "desktop":
        matched = []
        matched_names = set()
        match_seconds = 0.0
        current_state = None
        transitions = []
    else:
        phase_started = time.time()
        matched = match_memory_components(app_name, img_path)
        matched_names = {component["name"] for component in matched}
        match_seconds = round(time.time() - phase_started, 2)

        check_cancelled()
        current_state, _ = identify_state(app_name, img_path)
        transitions = (
            get_available_transitions(app_name, current_state)
            if current_state else []
        )

    total_seconds = round(time.time() - started, 2)
    print(
        f"    [observe] {len(icons)} icons, {len(texts)} texts, "
        f"{len(matched)} matched, state={current_state}, "
        f"{len(transitions)} transitions ({total_seconds}s: "
        f"detect={detect_seconds}s, match={match_seconds}s)",
        file=sys.stderr,
    )

    component_lines = [
        f"  [{component['name']}] at ({component['cx']}, {component['cy']})"
        for component in matched[:30]
    ]
    text_lines = [
        f"  '{item.get('label', '')}' at "
        f"({item.get('cx', 0)}, {item.get('cy', 0)})"
        for item in texts[:40]
        if item.get("label") and len(item.get("label", "")) > 1
    ]
    component_info = (
        "\n<screen_coordinates "
        f"width=\"{int(detection.get('img_w', 0) or 0)}\" "
        f"height=\"{int(detection.get('img_h', 0) or 0)}\" />"
        f"\n<frontmost_app>{frontmost_app}</frontmost_app>"
    )
    if component_lines:
        component_info += (
            "\n<known_components>\n"
            + "\n".join(component_lines)
            + "\n</known_components>"
        )
    if text_lines:
        component_info += (
            "\n<screen_text>\n"
            + "\n".join(text_lines)
            + "\n</screen_text>"
        )

    transitions_info = ""
    if transitions:
        transition_lines = [
            f"  {item['action']}:{item['target']} -> state "
            f"{item['to_state']} (used {item['use_count']}x)"
            for item in transitions[:10]
        ]
        transitions_info = (
            "\n<known_transitions>\n"
            + "\n".join(transition_lines)
            + "\n</known_transitions>"
        )

    return {
        "img_path": img_path,
        "screenshot_artifact": _copy_artifact(
            img_path, f"observe_{int(time.time() * 1000)}.png",
        ),
        "icons": icons,
        "texts": texts,
        "matched": matched,
        "matched_names": matched_names,
        "current_state": current_state,
        "frontmost_app": frontmost_app,
        "transitions": transitions,
        "component_info": component_info,
        "transitions_info": transitions_info,
    }


__all__ = ["observe_screen"]
