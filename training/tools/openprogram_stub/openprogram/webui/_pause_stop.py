"""Headless no-op cancellation check."""


def check_cancelled(*_args, **_kwargs):
    return None


__all__ = ["check_cancelled"]
