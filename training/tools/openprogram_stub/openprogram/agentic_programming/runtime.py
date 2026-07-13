"""ContextVar the compat layer toggles around exec calls."""

import contextvars

_current_tools = contextvars.ContextVar("_current_tools", default=None)

__all__ = ["_current_tools"]
