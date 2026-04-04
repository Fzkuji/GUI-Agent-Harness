"""
gui_harness.functions.observe — observe the current screen state.

observe() is an @agentic_function that:
  1. Takes a screenshot
  2. Runs OCR + GPA-GUI-Detector
  3. Asks the LLM to interpret the results with the screenshot
  4. Returns a structured dict
"""

from __future__ import annotations

import json

from agentic import agentic_function
from gui_harness.primitives import screenshot, ocr, detector
from gui_harness.primitives.input import get_frontmost_app

# Lazy default runtime
_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


@agentic_function(summarize={"depth": 0, "siblings": 0})
def observe(task: str, app_name: str = None, runtime=None) -> dict:
    """Observe the current screen state.

    Takes a screenshot, runs OCR and UI detection, then asks the LLM
    to interpret the combined data and return a structured analysis.

    Args:
        task:       What to look for on screen.
        app_name:   Optional: override frontmost app detection.
        runtime:    Optional: Runtime instance (uses default GUIRuntime if None).

    Returns:
        dict with keys:
            app_name, page_description, visible_text, interactive_elements,
            target_visible, target_location, screenshot_path
    """
    rt = runtime or _get_runtime()

    if not app_name:
        app_name = get_frontmost_app()

    img_path = screenshot.take()
    ocr_results = ocr.detect_text(img_path)

    try:
        _, _, merged, _, _ = detector.detect_all(img_path)
        elements = merged
    except Exception:
        elements = ocr_results

    ocr_lines = "\n".join(
        f"  '{el.get('label', '')}' at ({el.get('cx', 0)}, {el.get('cy', 0)})"
        for el in ocr_results[:60]
    )
    det_lines = "\n".join(
        f"  [{el.get('label', 'UI element')}] "
        f"at ({el.get('cx', 0)}, {el.get('cy', 0)}) "
        f"size={el.get('w', 0)}x{el.get('h', 0)} "
        f"conf={el.get('confidence', 0):.2f}"
        for el in elements[:50]
    )

    prompt = f"""Task: {task}
App: {app_name}

OCR text on screen (click-space coordinates):
{ocr_lines or '(none)'}

Detected UI elements (click-space coordinates):
{det_lines or '(none)'}

Analyze the screenshot and data above. Return JSON:
{{
  "app_name": "{app_name}",
  "page_description": "short description of current page/state",
  "visible_text": ["key", "text", "labels"],
  "interactive_elements": ["clickable", "element", "names"],
  "target_visible": true/false,
  "target_location": {{"x": 0, "y": 0, "label": "element"}} or null,
  "screenshot_path": "{img_path}"
}}

IMPORTANT: coordinates MUST come from the OCR/detector lists above."""

    reply = rt.exec(content=[
        {"type": "text", "text": prompt},
        {"type": "image", "path": img_path},
    ])

    try:
        result = _parse_json(reply)
        result.setdefault("app_name", app_name)
        result.setdefault("screenshot_path", img_path)
        result.setdefault("target_visible", False)
        result.setdefault("target_location", None)
    except Exception:
        result = {
            "app_name": app_name,
            "page_description": reply[:300],
            "visible_text": [el.get("label", "") for el in ocr_results[:10]],
            "interactive_elements": [],
            "target_visible": False,
            "target_location": None,
            "screenshot_path": img_path,
        }

    return result


def _parse_json(reply: str) -> dict:
    text = reply.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)
