"""Minimal openprogram stand-in for cluster runs of the GUI harness.

The real OpenProgram package provides execution tracing, provider runtimes,
and a webui. The harness's ScreenSpot-Pro benchmark path only touches a thin
slice of that surface, and with ``--provider local-openai`` the runtime lives
in gui_harness.openprogram_compat itself — so on machines without OpenProgram
(the GPU cluster) this stub satisfies the imports:

- ``agentic_function``: pass-through decorator (tracing is a no-op here)
- ``functions.agentics.json_parsing.parse_json``: verbatim copy of the real one
- ``providers.utils.errors``: exception types used in isinstance checks
- ``agentic_programming.runtime._current_tools``: ContextVar the compat layer
  toggles around exec calls
- ``webui._pause_stop.check_cancelled``: no-op (nothing to cancel headless)

Use by prepending this directory's parent to PYTHONPATH:
  PYTHONPATH=training/tools/openprogram_stub:$PYTHONPATH
Never install this next to the real package.
"""

from __future__ import annotations


def agentic_function(*args, **kwargs):
    """Pass-through for @agentic_function and @agentic_function(...)."""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    def deco(fn):
        return fn

    return deco


__all__ = ["agentic_function"]
