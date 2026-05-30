"""
gui_harness — GUI automation powered by Agentic Programming.

Primary entry point: gui_agent() in main.py
Architecture: Phase 0-5 loop (see DESIGN_unified_actions.md)

Lazy top-level exports (PEP 562): importing ``gui_harness`` itself pulls
NO heavy/native deps. ``gui_agent``'s *definition* only needs openprogram
+ a constants module — its heavy imports (opencv / ultralytics / the OS
desktop backends) live inside the function body, imported at call time.
So ``from gui_harness.main import gui_agent`` works without cv2 installed
and registers the function; cv2 et al. are only required to actually RUN
it. The other exports (execute_task / locate_target) DO pull the heavy
perception stack, so they're loaded lazily here — touching them without
the deps raises the underlying ImportError at access time, not at
``import gui_harness`` time. This keeps OpenProgram's harness discovery
(which imports ``gui_harness.agentics``) from exploding on a machine
that hasn't run ``pip install openprogram[gui]`` yet.
"""

__all__ = [
    "GUI_SYSTEM_PROMPT",
    "gui_agent",
    "execute_task",
    "locate_target",
]


def __getattr__(name):  # PEP 562 — resolve exports on first access
    if name == "GUI_SYSTEM_PROMPT":
        from gui_harness.constants import GUI_SYSTEM_PROMPT
        return GUI_SYSTEM_PROMPT
    if name == "gui_agent":
        from gui_harness.main import gui_agent
        return gui_agent
    if name == "execute_task":
        from gui_harness.tasks.execute_task import execute_task
        return execute_task
    if name == "locate_target":
        from gui_harness.planning.component_memory import locate_target
        return locate_target
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
