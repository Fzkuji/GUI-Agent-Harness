"""
gui_harness.create — dynamically create new GUI automation functions.

Wraps agentic.meta_function.create() with GUI-specific context:
available primitives, coordinate rules, and examples.

Usage:
    from gui_harness.create import create_gui_function
    from gui_harness.runtime import GUIRuntime

    runtime = GUIRuntime()

    scroll_and_read = create_gui_function(
        "Scroll down 3 times and read all visible text after each scroll",
        runtime=runtime,
    )
    result = scroll_and_read()
"""

from __future__ import annotations

from agentic.meta_function import create, fix
from agentic.function import agentic_function

# GUI-specific context injected into the create() prompt
_GUI_CONTEXT = """
Available GUI primitives (already imported, use directly):

    # Screenshot
    from gui_harness.primitives import screenshot
    img_path = screenshot.take()                    # returns file path

    # OCR (text detection)
    from gui_harness.primitives import ocr
    texts = ocr.detect_text(img_path)               # returns [{label, cx, cy, x, y, w, h}, ...]

    # UI element detection (YOLO-based)
    from gui_harness.primitives import detector
    icons, texts, merged, w, h = detector.detect_all(img_path)  # merged has all elements

    # Mouse & keyboard
    from gui_harness.primitives import input as gui_input
    gui_input.mouse_click(x, y)                     # click at coordinates
    gui_input.mouse_double_click(x, y)
    gui_input.mouse_right_click(x, y)
    gui_input.key_press("return")                    # single key
    gui_input.key_combo("cmd", "c")                  # key combo
    gui_input.type_text("hello")                     # type ASCII text
    gui_input.paste_text("你好")                     # paste via clipboard (handles unicode)
    gui_input.activate_app("Firefox")                # bring app to front
    gui_input.get_frontmost_app()                    # returns app name

    # Template matching
    from gui_harness.primitives import template_match
    result = template_match.find_template("AppName", "button_name")  # {found, x, y, confidence}

    # Existing agentic functions (can call these too)
    from gui_harness.functions.observe import observe
    from gui_harness.functions.act import act
    from gui_harness.functions.verify import verify

Rules:
- Coordinates MUST come from OCR/detector output, never estimated
- Use runtime.exec() when you need LLM reasoning (analyzing what's on screen)
- Use primitives directly for deterministic operations (click, type, screenshot)
- Always screenshot before acting to know current state
- import time and use time.sleep(0.5) between actions for UI to update
"""


def create_gui_function(description: str, runtime=None, name: str = None):
    """Create a new @agentic_function for GUI automation.

    The generated function has access to all gui_harness primitives
    (screenshot, OCR, detector, mouse, keyboard) and can call
    runtime.exec() for LLM reasoning.

    Args:
        description: What the function should do (natural language).
        runtime:     GUIRuntime instance.
        name:        Optional function name override.

    Returns:
        A callable @agentic_function.

    Example:
        scroll_fn = create_gui_function(
            "Scroll down in the active window 3 times, "
            "take a screenshot after each scroll, "
            "and return the OCR text from each screenshot",
            runtime=runtime,
        )
        result = scroll_fn()
    """
    if runtime is None:
        from gui_harness.runtime import GUIRuntime
        runtime = GUIRuntime()

    full_description = f"{description}\n\n{_GUI_CONTEXT}"

    fn = create(description=full_description, runtime=runtime, name=name)

    # Inject GUI primitives into the function's namespace so it can use them
    import gui_harness.primitives.screenshot as _ss
    import gui_harness.primitives.ocr as _ocr
    import gui_harness.primitives.detector as _det
    import gui_harness.primitives.input as _inp
    import gui_harness.primitives.template_match as _tm
    import time

    # The generated function runs in a sandbox with limited builtins.
    # We need to make primitives available. Since create() uses exec()
    # with a restricted namespace, we patch the function's globals.
    if hasattr(fn, '_fn') and hasattr(fn._fn, '__globals__'):
        fn._fn.__globals__.update({
            'screenshot': _ss,
            'ocr': _ocr,
            'detector': _det,
            'gui_input': _inp,
            'template_match': _tm,
            'time': time,
        })

    return fn


def fix_gui_function(fn, runtime=None, instruction: str = None, **kwargs):
    """Fix a broken GUI automation function.

    Analyzes the function's Context tree (errors, failed attempts)
    and rewrites it with fixes.

    Args:
        fn:          The broken @agentic_function to fix.
        runtime:     GUIRuntime instance.
        instruction: Optional manual fix instruction.

    Returns:
        A new fixed @agentic_function.
    """
    if runtime is None:
        from gui_harness.runtime import GUIRuntime
        runtime = GUIRuntime()

    full_instruction = instruction or ""
    full_instruction += f"\n\n{_GUI_CONTEXT}"

    return fix(fn=fn, runtime=runtime, instruction=full_instruction, **kwargs)
