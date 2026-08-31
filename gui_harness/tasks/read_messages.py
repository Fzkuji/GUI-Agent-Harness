"""Compatibility wrapper for message-reading tasks."""

from __future__ import annotations

from gui_harness.openprogram_compat import agentic_function
from gui_harness.tasks._delegate import run_gui_task


@agentic_function()
def read_messages(
    app_name: str,
    contact: str | None = None,
    runtime=None,
) -> dict:
    """Read visible messages through the canonical verified GUI task loop."""
    scope = f" with {contact}" if contact else ""
    result = run_gui_task(
        f"In {app_name}, read and report all currently visible messages{scope}",
        app_name=app_name,
        runtime=runtime,
    )
    return {
        **result,
        "contact": contact,
        "messages": [result.get("summary", "")],
    }


__all__ = ["read_messages"]
