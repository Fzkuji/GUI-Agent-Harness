"""Compatibility wrapper for message-sending tasks."""

from __future__ import annotations

from gui_harness.openprogram_compat import agentic_function
from gui_harness.tasks._delegate import run_gui_task


@agentic_function()
def send_message(
    app_name: str,
    recipient: str,
    message: str,
    runtime=None,
) -> dict:
    """Send a message through the canonical verified GUI task loop."""
    result = run_gui_task(
        f"In {app_name}, send this exact message to {recipient}: {message}",
        app_name=app_name,
        runtime=runtime,
    )
    return {**result, "recipient": recipient, "message": message}


__all__ = ["send_message"]
