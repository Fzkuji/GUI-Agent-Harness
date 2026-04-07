"""
gui_harness.action.actions — atomic GUI actions.

Every function here is a pure execution function — NO LLM calls.
Coordinates, text, and key names are all passed as parameters.
The LLM planner decides what to call and with what arguments.

Usage:
    from gui_harness.action.actions import click, type_text, key_press, shortcut

    click(500, 300)                    # single click at (500, 300)
    double_click(500, 300)             # double click
    type_text("hello world")           # type into currently focused element
    key_press("return")                # press Enter
    shortcut("ctrl+s")                 # keyboard shortcut
"""

from __future__ import annotations

import time
from gui_harness.action import input as _input


def click(x: int, y: int) -> dict:
    """Single click at screen coordinates (x, y)."""
    try:
        _input.mouse_click(int(x), int(y))
        time.sleep(0.3)
        return {"action": "click", "x": x, "y": y, "success": True}
    except Exception as e:
        return {"action": "click", "x": x, "y": y, "success": False, "error": str(e)}


def double_click(x: int, y: int) -> dict:
    """Double click at screen coordinates (x, y)."""
    try:
        _input.mouse_double_click(int(x), int(y))
        time.sleep(0.3)
        return {"action": "double_click", "x": x, "y": y, "success": True}
    except Exception as e:
        return {"action": "double_click", "x": x, "y": y, "success": False, "error": str(e)}


def right_click(x: int, y: int) -> dict:
    """Right click at screen coordinates (x, y)."""
    try:
        _input.mouse_right_click(int(x), int(y))
        time.sleep(0.3)
        return {"action": "right_click", "x": x, "y": y, "success": True}
    except Exception as e:
        return {"action": "right_click", "x": x, "y": y, "success": False, "error": str(e)}


def type_text(text: str) -> dict:
    """Type text into the currently focused element.

    ONLY types the given text. Does NOT click, does NOT press Enter.
    Caller must ensure the target is already focused/selected.
    """
    try:
        _input.type_text(text)
        time.sleep(0.3)
        return {"action": "type", "text": text, "success": True}
    except Exception as e:
        return {"action": "type", "text": text, "success": False, "error": str(e)}


def key_press(key: str) -> dict:
    """Press and release a single key.

    Common keys: "return", "escape", "delete", "tab", "space",
                 "up", "down", "left", "right", "f2", etc.
    """
    try:
        _input.key_press(key)
        time.sleep(0.2)
        return {"action": "key_press", "key": key, "success": True}
    except Exception as e:
        return {"action": "key_press", "key": key, "success": False, "error": str(e)}


def shortcut(keys: str) -> dict:
    """Press a keyboard shortcut.

    Args:
        keys: '+' separated key names, e.g. "ctrl+s", "ctrl+shift+s", "alt+f4"
    """
    key_list = [k.strip() for k in keys.split("+")]
    try:
        _input.key_combo(*key_list)
        time.sleep(0.3)
        return {"action": "shortcut", "keys": keys, "success": True}
    except Exception as e:
        return {"action": "shortcut", "keys": keys, "success": False, "error": str(e)}


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> dict:
    """Drag from (x1, y1) to (x2, y2).

    Args:
        x1, y1: start coordinates
        x2, y2: end coordinates
        duration: drag duration in seconds
    """
    try:
        _input.mouse_drag(int(x1), int(y1), int(x2), int(y2), duration=duration)
        time.sleep(0.3)
        return {"action": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "success": True}
    except Exception as e:
        return {"action": "drag", "success": False, "error": str(e)}


def paste_text(text: str) -> dict:
    """Paste text via clipboard (more reliable for special characters/unicode)."""
    try:
        _input.paste_text(text)
        time.sleep(0.3)
        return {"action": "paste", "text": text, "success": True}
    except Exception as e:
        return {"action": "paste", "text": text, "success": False, "error": str(e)}


def scroll(direction: str = "down", clicks: int = 3) -> dict:
    """Scroll in the given direction.

    Args:
        direction: "up" or "down"
        clicks: number of scroll clicks (default 3)
    """
    try:
        _input.mouse_scroll(direction, clicks)
        time.sleep(0.3)
        return {"action": "scroll", "direction": direction, "clicks": clicks, "success": True}
    except Exception as e:
        return {"action": "scroll", "direction": direction, "success": False, "error": str(e)}
