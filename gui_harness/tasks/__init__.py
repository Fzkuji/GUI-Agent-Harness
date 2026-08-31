"""High-level task APIs, loaded lazily to avoid registration side effects."""

from __future__ import annotations

__all__ = ["execute_task", "send_message", "read_messages"]


def __getattr__(name):
    if name == "execute_task":
        from gui_harness.tasks.execute_task import execute_task
        return execute_task
    if name == "send_message":
        from gui_harness.tasks.send_message import send_message
        return send_message
    if name == "read_messages":
        from gui_harness.tasks.read_messages import read_messages
        return read_messages
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
