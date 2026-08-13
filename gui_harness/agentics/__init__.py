"""Agentic entry points for the GUI harness.

Discovered automatically by OpenProgram via the
``AGENTIC_FUNCTIONS`` convention — when this package is symlinked
into ``openprogram/programs/agentic_functions/``, the loader walks for any
``<pkg>/agentics/__init__.py`` exporting an ``AGENTIC_FUNCTIONS``
list and imports it (the ``@agentic_function`` decorators fire as
side effects and self-register).
"""
from __future__ import annotations

try:
    from ..main import gui_agent
    AGENTIC_FUNCTIONS = [gui_agent]
except ImportError:
    AGENTIC_FUNCTIONS = []

__all__ = ["AGENTIC_FUNCTIONS"]
