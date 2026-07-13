"""Exception types the harness references in isinstance checks."""


class LLMError(Exception):
    """Provider-side LLM failure."""


class ExecInterrupt(Exception):
    """User/webui cancellation — never raised headless."""


__all__ = ["LLMError", "ExecInterrupt"]
