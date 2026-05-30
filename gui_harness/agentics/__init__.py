"""Agentic entry points for the GUI harness.

Exposes the top-level ``@agentic_function`` — :func:`gui_agent` — the
perceive → plan → act loop that drives the desktop for a given task.

This module is the registration contract OpenProgram looks for: drop the
harness under ``functions/agentics/`` and OpenProgram imports
``<package>/agentics/__init__.py`` and reads ``AGENTIC_FUNCTIONS`` — the
decorators fire on import and self-register. See
``docs/installing-harnesses.md`` in the OpenProgram repo.

Import is guarded: ``gui_agent`` pulls heavy / platform-specific deps
(opencv, ultralytics, OS desktop-control backends). If those aren't
installed, or the current OS isn't supported yet, the import fails
softly and the harness simply registers no agentic function rather than
breaking OpenProgram's startup. (Cross-platform desktop backends are a
work in progress — see the harness README.)
"""
from __future__ import annotations

try:
    from gui_harness.main import gui_agent
    AGENTIC_FUNCTIONS = [gui_agent]
except Exception:  # noqa: BLE001 — heavy/native/platform import may fail
    AGENTIC_FUNCTIONS = []

__all__ = ["AGENTIC_FUNCTIONS"]
