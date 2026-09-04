"""
gui_harness.perception — screen sensing: screenshot, OCR, detection, template matching.
"""
from importlib import import_module

__all__ = ["screenshot", "ocr", "detector", "template_match"]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(name)
    module = import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module
