"""Compatibility observation API backed by the canonical perception pass."""

from __future__ import annotations

from gui_harness.action.input import get_frontmost_app
from gui_harness.openprogram_compat import agentic_function
from gui_harness.perception.observe import observe_screen


@agentic_function(render_range={"callers": 0})
def observe(task: str, app_name: str | None = None) -> dict:
    """Return a compact semantic view without taking a second screenshot."""
    app_name = app_name or get_frontmost_app()
    observation = observe_screen(app_name)
    texts = observation.get("texts", [])
    matched = observation.get("matched", [])

    task_lower = task.lower()
    candidates = [
        item for item in [*texts, *matched]
        if str(item.get("label") or item.get("name") or "").strip()
        and str(item.get("label") or item.get("name") or "").lower() in task_lower
    ]
    target = candidates[0] if candidates else None
    return {
        "app_name": app_name,
        "page_description": f"Current {app_name} screen",
        "visible_text": [
            item.get("label", "") for item in texts if item.get("label")
        ],
        "interactive_elements": [
            item.get("name", "") for item in matched if item.get("name")
        ],
        "target_visible": target is not None,
        "target_location": (
            {
                "x": target.get("cx", 0),
                "y": target.get("cy", 0),
                "label": target.get("label") or target.get("name") or "",
            }
            if target else None
        ),
        "screenshot_path": observation["img_path"],
    }


__all__ = ["observe"]
