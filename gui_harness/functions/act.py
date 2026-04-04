"""
gui_harness.functions.act — perform a GUI action.

act() is an @agentic_function that:
  1. Uses summarize() to see what observe() found (via Context tree)
  2. Takes a before screenshot + detection
  3. Asks the LLM to locate the target
  4. Executes the action via primitives
  5. Checks if the screen changed
"""

from __future__ import annotations

import json
import time

from agentic import agentic_function
from gui_harness.primitives import screenshot, ocr, detector
from gui_harness.primitives import input as _input

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


@agentic_function(summarize={"depth": 0, "siblings": 0})
def act(action: str, target: str, text: str = None,
        app_name: str = None, runtime=None) -> dict:
    """Perform a GUI action on a target element.

    The Context tree (via summarize()) provides what observe() found,
    so the LLM has full situational awareness without re-observing.

    Args:
        action:   One of "click", "double_click", "right_click", "type", "shortcut".
        target:   Description of the element to interact with.
        text:     Text to type (for "type" action).
        app_name: Optional: override frontmost app detection.
        runtime:  Optional: Runtime instance.

    Returns:
        dict with keys:
            action, target, coordinates, success, screen_changed, error
    """
    rt = runtime or _get_runtime()

    if not app_name:
        app_name = _input.get_frontmost_app()

    # Before screenshot + detection
    img_path = screenshot.take()
    ocr_results = ocr.detect_text(img_path)

    try:
        _, _, elements, _, _ = detector.detect_all(img_path)
    except Exception:
        elements = ocr_results

    ocr_lines = "\n".join(
        f"  '{el.get('label', '')}' at ({el.get('cx', 0)}, {el.get('cy', 0)})"
        for el in ocr_results[:60]
    )
    det_lines = "\n".join(
        f"  [{el.get('label', 'UI element')}] "
        f"at ({el.get('cx', 0)}, {el.get('cy', 0)}) "
        f"size={el.get('w', 0)}x{el.get('h', 0)}"
        for el in elements[:50]
    )

    prompt = f"""Action: {action}
Target: {target}
{f'Text to type: {text}' if text else ''}
App: {app_name}

OCR text on screen:
{ocr_lines or '(none)'}

Detected UI elements:
{det_lines or '(none)'}

Find the target "{target}" in the lists above and return its EXACT coordinates.
Do NOT estimate from the image — use only coordinates from the lists.

Return JSON:
{{
  "action": "{action}",
  "target": "{target}",
  "coordinates": {{"x": 0, "y": 0}} or null if not found,
  "success": true/false,
  "error": null or "reason why not found"
}}"""

    reply = rt.exec(content=[
        {"type": "text", "text": prompt},
        {"type": "image", "path": img_path},
    ])

    try:
        data = _parse_json(reply)
    except Exception:
        data = {
            "action": action, "target": target,
            "coordinates": None, "success": False,
            "error": f"Failed to parse LLM response: {reply[:200]}"
        }

    # Execute the action
    if data.get("success") and data.get("coordinates"):
        coords = data["coordinates"]
        cx, cy = int(coords.get("x", 0)), int(coords.get("y", 0))

        try:
            if action.lower() in ("click", "single_click"):
                _input.mouse_click(cx, cy)
            elif action.lower() == "double_click":
                _input.mouse_double_click(cx, cy)
            elif action.lower() == "right_click":
                _input.mouse_right_click(cx, cy)
            elif action.lower() == "type":
                _input.mouse_click(cx, cy)
                time.sleep(0.3)
                _input.paste_text(text or "")
            elif action.lower() == "shortcut":
                keys = [k.strip() for k in target.split("+")]
                _input.key_combo(*keys)

            time.sleep(0.5)

            # Check if screen changed
            after_ocr = ocr.detect_text(screenshot.take("/tmp/gui_act_after.png"))
            before_texts = {el.get("label", "") for el in ocr_results}
            after_texts = {el.get("label", "") for el in after_ocr}
            data["screen_changed"] = before_texts != after_texts

        except Exception as e:
            data["success"] = False
            data["error"] = str(e)
            data["screen_changed"] = False
    else:
        data["screen_changed"] = False

    data.setdefault("action", action)
    data.setdefault("target", target)
    return data


def _parse_json(reply: str) -> dict:
    text = reply.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)
