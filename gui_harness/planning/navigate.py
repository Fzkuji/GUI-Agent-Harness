"""Compatibility wrapper for state-navigation tasks."""

from __future__ import annotations

from gui_harness.openprogram_compat import agentic_function
from gui_harness.tasks._delegate import run_gui_task


@agentic_function()
def navigate(
    target_state: str,
    app_name: str,
    runtime=None,
    max_steps: int = 10,
) -> dict:
    """Reach a named UI state through the canonical verified GUI loop."""
    result = run_gui_task(
        f"In {app_name}, navigate to this UI state: {target_state}",
        app_name=app_name,
        runtime=runtime,
        max_steps=max_steps,
    )
    return {
        **result,
        "target_state": target_state,
        "reached_target": result.get("status") == "succeeded",
    }


__all__ = ["navigate"]
