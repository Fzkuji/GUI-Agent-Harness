"""Compatibility delegation to the one desktop execution engine."""

from __future__ import annotations


def run_gui_task(
    task: str,
    *,
    app_name: str,
    runtime,
    max_steps: int = 30,
) -> dict:
    if runtime is None:
        raise ValueError("GUI task requires a runtime argument")
    from gui_harness.main import gui_agent

    implementation = getattr(gui_agent, "__wrapped__", gui_agent)
    return implementation(
        task=task,
        max_steps=max_steps,
        app_name=app_name,
        runtime=runtime,
        allow_general=False,
    )


__all__ = ["run_gui_task"]
