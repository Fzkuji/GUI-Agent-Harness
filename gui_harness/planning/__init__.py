"""Planner APIs, loaded lazily to keep perception imports acyclic."""

from __future__ import annotations

__all__ = ["observe", "verify", "learn", "navigate", "remember"]


def __getattr__(name):
    if name == "observe":
        from gui_harness.planning.observe import observe
        return observe
    if name == "verify":
        from gui_harness.planning.verify import verify
        return verify
    if name == "learn":
        from gui_harness.planning.learn import learn_app_components
        return learn_app_components
    if name == "navigate":
        from gui_harness.planning.navigate import navigate
        return navigate
    if name == "remember":
        from gui_harness.planning.remember import remember
        return remember
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
