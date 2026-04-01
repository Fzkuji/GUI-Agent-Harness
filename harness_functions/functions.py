"""
GUI Agent Functions — 6 core + sub-functions for desktop automation.

Architecture:
    High-level functions (LLM reasoning):
        observe, learn, act, remember, navigate, verify

    Low-level functions (Python deterministic):
        screenshot, ocr, detect, template_match, click, type_text, ...

    High-level calls low-level to gather data, then asks LLM to reason.
    Functions can call each other (observe calls screenshot + ocr + detect).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

# Setup paths
SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Framework import
_harness_path = str(SKILL_DIR.parent.parent.parent / "Documents" / "LLM Agent Harness" / "llm-agent-harness")
if _harness_path not in sys.path:
    sys.path.insert(0, _harness_path)
from harness import function, Session


# ═══════════════════════════════════════════
# Return types
# ═══════════════════════════════════════════

class ScreenshotResult(BaseModel):
    path: str
    width: int = 0
    height: int = 0

class OCRResult(BaseModel):
    texts: list[dict]      # [{label, cx, cy, x, y, w, h}, ...]
    count: int

class DetectResult(BaseModel):
    elements: list[dict]   # [{cx, cy, x, y, w, h, confidence, label}, ...]
    count: int

class DetectAllResult(BaseModel):
    """Combined detection: OCR + GPA-GUI-Detector + (optional) Accessibility."""
    elements: list[dict]   # merged elements in click-space coordinates
    count: int
    screenshot_path: str
    screen_info: dict      # {detect_w, detect_h, click_w, click_h, scale_x, scale_y}

class TemplateMatchResult(BaseModel):
    matched: list[dict]    # [{name, cx, cy, confidence}, ...]
    count: int

class StateResult(BaseModel):
    state_name: Optional[str] = None
    confidence: float = 0.0
    visible_components: list[str] = []

class ObserveResult(BaseModel):
    app_name: str
    page_description: str
    visible_text: list[str]
    interactive_elements: list[str]
    state_name: Optional[str] = None
    state_confidence: Optional[float] = None
    target_visible: bool = False
    target_location: Optional[dict] = None
    screenshot_path: Optional[str] = None

class LearnResult(BaseModel):
    app_name: str
    components_found: int
    components_saved: int
    component_names: list[str]
    page_name: str
    already_known: bool = False

class ActResult(BaseModel):
    action: str
    target: str
    coordinates: Optional[dict] = None
    success: bool
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    screen_changed: bool = False
    error: Optional[str] = None

class RememberResult(BaseModel):
    operation: str
    app_name: str
    details: str

class NavigateResult(BaseModel):
    start_state: str
    target_state: str
    path: list[str]
    steps_taken: int
    reached_target: bool
    current_state: str

class VerifyResult(BaseModel):
    expected: str
    actual: str
    verified: bool
    evidence: str
    screenshot_path: Optional[str] = None


# ═══════════════════════════════════════════
# Low-level functions (deterministic, no LLM)
# ═══════════════════════════════════════════

def take_screenshot(app_name: str = None, fullscreen: bool = True) -> ScreenshotResult:
    """Take a screenshot. Returns path and dimensions."""
    from platform_input import screenshot as _screenshot, capture_window
    import cv2

    if app_name and not fullscreen:
        path = capture_window(app_name)
    else:
        path = _screenshot()

    if path and Path(path).exists():
        img = cv2.imread(path)
        h, w = img.shape[:2] if img is not None else (0, 0)
        return ScreenshotResult(path=path, width=w, height=h)

    return ScreenshotResult(path=path or "/tmp/gui_agent_screen.png")


def run_ocr(image_path: str) -> OCRResult:
    """Run Apple Vision OCR on an image. Returns text elements with coordinates."""
    from ui_detector import detect_text
    texts = detect_text(image_path)
    return OCRResult(texts=texts, count=len(texts))


def run_detector(image_path: str, conf: float = 0.1) -> DetectResult:
    """Run GPA-GUI-Detector on an image. Returns UI elements with bounding boxes."""
    from ui_detector import detect_icons
    elements = detect_icons(image_path, conf=conf)
    return DetectResult(elements=elements, count=len(elements))


def detect_all(image_path: str, conf: float = 0.1) -> DetectAllResult:
    """Run full detection pipeline: OCR + GPA-GUI-Detector + merge.
    Returns all elements in click-space coordinates.
    Gracefully degrades if detector is unavailable (OCR-only mode)."""
    try:
        from ui_detector import detect_all as _detect_all, get_screen_info
        elements = _detect_all(image_path, conf=conf)
        info = get_screen_info()
    except (ImportError, Exception):
        # Fallback: OCR-only
        ocr = run_ocr(image_path)
        elements = ocr.texts
        info = {}
    return DetectAllResult(
        elements=elements,
        count=len(elements),
        screenshot_path=image_path,
        screen_info=info,
    )


def template_match(app_name: str, image_path: str = None) -> TemplateMatchResult:
    """Match known components from memory against the current screen."""
    from app_memory import quick_template_check, get_app_dir, load_components
    app_dir = get_app_dir(app_name)
    if not app_dir or not Path(app_dir).exists():
        return TemplateMatchResult(matched=[], count=0)

    components = load_components(app_dir)
    comp_names = [c["name"] for c in components if "name" in c]

    # quick_template_check returns (matched_names: set, total: int, ratio: float)
    matched_names, total, ratio = quick_template_check(app_dir, comp_names, img=image_path)

    # Convert to list of dicts with component info
    matched = []
    for comp in components:
        if comp.get("name") in matched_names:
            matched.append({
                "name": comp["name"],
                "cx": comp.get("cx", 0),
                "cy": comp.get("cy", 0),
            })

    return TemplateMatchResult(matched=matched, count=len(matched))


def identify_state(app_name: str) -> StateResult:
    """Identify the current state of an app from visual memory."""
    from app_memory import (
        identify_state_by_components, get_app_dir,
        load_components, load_states, quick_template_check
    )

    app_dir = get_app_dir(app_name)
    if not app_dir or not Path(app_dir).exists():
        return StateResult()

    components = load_components(app_dir)
    comp_names = [c["name"] for c in components if "name" in c]

    # quick_template_check returns (matched_names: set, total: int, ratio: float)
    matched_names, total, ratio = quick_template_check(app_dir, comp_names)
    visible_names = list(matched_names)

    state_name, conf = identify_state_by_components(app_name, visible_names)
    return StateResult(
        state_name=state_name,
        confidence=conf,
        visible_components=visible_names,
    )


def click(x: int, y: int, button: str = "left", clicks: int = 1):
    """Click at screen coordinates."""
    from platform_input import mouse_click
    mouse_click(x, y, button=button, clicks=clicks)


def type_text(text: str):
    """Type text using keyboard."""
    from platform_input import type_text as _type
    _type(text)


def paste(text: str):
    """Paste text via clipboard."""
    from platform_input import paste_text
    paste_text(text)


def press_key(key: str):
    """Press a single key."""
    from platform_input import key_press
    key_press(key)


def key_combo(*keys: str):
    """Press a key combination (e.g., key_combo('cmd', 'c'))."""
    from platform_input import key_combo as _combo
    _combo(*keys)


def get_frontmost_app() -> str:
    """Get the name of the frontmost application."""
    from platform_input import get_frontmost_app as _get
    return _get()


def activate_app(app_name: str):
    """Bring an app to the foreground."""
    from platform_input import activate_app as _activate
    _activate(app_name)


def learn_from_screenshot(image_path: str, app_name: str,
                          page_name: str, domain: str = None) -> dict:
    """Run detection on a screenshot and save all components to memory."""
    from app_memory import learn_from_screenshot as _learn
    return _learn(
        img_path=image_path,
        domain=domain,
        app_name=app_name,
        page_name=page_name,
    )


def record_transition(before_img: str, after_img: str,
                      click_label: str, click_pos: tuple,
                      app_name: str, domain: str = None) -> dict:
    """Record a state transition (before/after a click)."""
    from app_memory import record_page_transition
    return record_page_transition(
        before_img_path=before_img,
        after_img_path=after_img,
        click_label=click_label,
        click_pos=click_pos,
        domain=domain,
        app_name=app_name,
    )


# ═══════════════════════════════════════════
# High-level functions (LLM reasoning)
# ═══════════════════════════════════════════

def observe(session: Session, task: str, app_name: str = None) -> ObserveResult:
    """Observe the current screen. Calls low-level functions, then LLM interprets.

    Flow: screenshot → OCR → detector → memory check → LLM interprets
    """
    # 1. Deterministic: gather data
    if not app_name:
        app_name = get_frontmost_app()

    shot = take_screenshot()
    ocr = run_ocr(shot.path)
    detection = detect_all(shot.path)
    state = identify_state(app_name)

    # Format for LLM
    ocr_lines = [f"  '{t.get('label','')}' at ({t.get('cx',0)}, {t.get('cy',0)})"
                 for t in ocr.texts[:50]]
    det_lines = [f"  [{e.get('label','component')}] at ({e.get('cx',0)}, {e.get('cy',0)}) conf={e.get('confidence',0):.2f}"
                 for e in detection.elements[:40]]
    state_line = f"State: {state.state_name} (conf={state.confidence:.2f}), visible: {state.visible_components[:10]}" if state.state_name else "(unknown state)"

    # 2. LLM: interpret
    prompt = f"""You are observing the current screen.

## Task
{task}

## Frontmost app
{app_name}

## OCR text (with click-space coordinates)
{chr(10).join(ocr_lines) if ocr_lines else '(none)'}

## Detected UI elements (with click-space coordinates)
{chr(10).join(det_lines) if det_lines else '(none)'}

## Visual memory
{state_line}

Based on ALL data above, report what you see.
Coordinates MUST come from the OCR/detector lists above, never estimated.

Return JSON:
{json.dumps(ObserveResult.model_json_schema(), indent=2)}"""

    reply = session.send({"text": prompt, "images": [shot.path]})

    # 3. Parse
    try:
        data = _parse_json(reply)
        data.setdefault("app_name", app_name)
        data.setdefault("screenshot_path", shot.path)
        data.setdefault("state_name", state.state_name)
        data.setdefault("state_confidence", state.confidence)
        return ObserveResult(**data)
    except Exception:
        return ObserveResult(
            app_name=app_name,
            page_description=reply[:300],
            visible_text=[t.get("label", "") for t in ocr.texts[:10]],
            interactive_elements=[],
            state_name=state.state_name,
            state_confidence=state.confidence,
            screenshot_path=shot.path,
        )


def learn(session: Session, app_name: str) -> LearnResult:
    """Learn a new app's UI. Calls detection, then LLM labels components.

    Flow: screenshot → detect_all → LLM labels each component → save to memory
    """
    shot = take_screenshot()
    detection = detect_all(shot.path)

    det_lines = [f"  Component {i}: at ({e.get('cx',0)}, {e.get('cy',0)}), size={e.get('w',0)}x{e.get('h',0)}, conf={e.get('confidence',0):.2f}"
                 for i, e in enumerate(detection.elements[:40])]

    ocr = run_ocr(shot.path)
    ocr_lines = [f"  '{t.get('label','')}' at ({t.get('cx',0)}, {t.get('cy',0)})"
                 for t in ocr.texts[:50]]

    prompt = f"""You are learning the UI of "{app_name}" for the first time.

## Detected UI components (need labels)
{chr(10).join(det_lines) if det_lines else '(none)'}

## OCR text on screen
{chr(10).join(ocr_lines) if ocr_lines else '(none)'}

## Screenshot
(attached)

For each component, give it a descriptive snake_case name based on what it is.
Filter out decorative/non-interactive elements.
Identify the current page name.

Return JSON:
{json.dumps(LearnResult.model_json_schema(), indent=2)}"""

    reply = session.send({"text": prompt, "images": [shot.path]})

    try:
        data = _parse_json(reply)
        data.setdefault("app_name", app_name)

        # Save to memory
        result = learn_from_screenshot(shot.path, app_name, data.get("page_name", "unknown"))
        data.setdefault("components_found", result.get("saved", 0) + result.get("existing", 0))
        data.setdefault("components_saved", result.get("saved", 0))

        return LearnResult(**data)
    except Exception as e:
        return LearnResult(
            app_name=app_name,
            components_found=detection.count,
            components_saved=0,
            component_names=[],
            page_name="unknown",
        )


def act(session: Session, action: str, target: str,
        text: str = None, app_name: str = None) -> ActResult:
    """Perform a GUI action. Detects target, LLM confirms, Python executes.

    Flow: screenshot → OCR + template match → LLM finds target → click/type → verify diff
    """
    if not app_name:
        app_name = get_frontmost_app()

    # Before screenshot
    before_shot = take_screenshot()
    ocr = run_ocr(before_shot.path)
    tmatch = template_match(app_name, before_shot.path)

    ocr_lines = [f"  '{t.get('label','')}' at ({t.get('cx',0)}, {t.get('cy',0)})"
                 for t in ocr.texts[:50]]
    match_lines = [f"  '{m.get('name','')}' at ({m.get('cx',0)}, {m.get('cy',0)}) conf={m.get('confidence',0):.2f}"
                   for m in tmatch.matched[:20]]

    before_state = identify_state(app_name)

    prompt = f"""You are performing a GUI action.

## Action: {action}
## Target: {target}
{f'## Text to type: {text}' if text else ''}

## App: {app_name}

## OCR text (with coordinates)
{chr(10).join(ocr_lines) if ocr_lines else '(none)'}

## Known components from memory (template matched)
{chr(10).join(match_lines) if match_lines else '(none)'}

Find the target "{target}" in the lists above.
Report EXACT coordinates from the list. Do NOT estimate from image.
If not found, set success=false.

Return JSON:
{json.dumps(ActResult.model_json_schema(), indent=2)}"""

    reply = session.send({"text": prompt, "images": [before_shot.path]})

    try:
        data = _parse_json(reply)
        result = ActResult(**{**data, "action": action, "target": target})

        # Execute if LLM found the target
        if result.success and result.coordinates:
            cx, cy = result.coordinates.get("x", 0), result.coordinates.get("y", 0)

            if action.lower() in ("click", "single_click"):
                click(cx, cy)
            elif action.lower() == "double_click":
                click(cx, cy, clicks=2)
            elif action.lower() == "right_click":
                click(cx, cy, button="right")
            elif action.lower() == "type" and text:
                click(cx, cy)
                time.sleep(0.3)
                paste(text)

            # After screenshot + diff
            time.sleep(0.5)
            after_shot = take_screenshot()
            after_ocr = run_ocr(after_shot.path)
            before_texts = {t.get("label", "") for t in ocr.texts}
            after_texts = {t.get("label", "") for t in after_ocr.texts}
            result.screen_changed = before_texts != after_texts

            after_state = identify_state(app_name)
            result.before_state = before_state.state_name
            result.after_state = after_state.state_name

            # Record transition
            if result.screen_changed:
                try:
                    record_transition(
                        before_shot.path, after_shot.path,
                        target, (cx, cy), app_name,
                    )
                except Exception:
                    pass

        return result

    except Exception as e:
        return ActResult(
            action=action, target=target, success=False,
            error=f"Failed: {e}",
        )


def remember(session: Session, operation: str, app_name: str,
             details: str = None) -> RememberResult:
    """Manage visual memory. LLM decides what to save/merge/forget.

    Flow: load memory → LLM reviews → execute operation
    """
    from app_memory import (
        get_app_dir, load_components, load_states,
        save_components, save_states, forget_stale_components,
        merge_similar_states, load_meta, save_meta
    )

    app_dir = get_app_dir(app_name)

    if operation == "list":
        components = load_components(app_dir) if app_dir else []
        states = load_states(app_dir) if app_dir else {}
        return RememberResult(
            operation="list", app_name=app_name,
            details=f"{len(components)} components, {len(states)} states",
        )

    if operation == "forget":
        if not app_dir:
            return RememberResult(operation="forget", app_name=app_name, details="No memory found")
        components = load_components(app_dir)
        meta = load_meta(app_dir)
        states = load_states(app_dir)
        transitions = {}
        try:
            from app_memory import load_transitions
            transitions = load_transitions(app_dir)
        except Exception:
            pass
        removed = forget_stale_components(app_dir, components, meta, states, transitions)
        return RememberResult(
            operation="forget", app_name=app_name,
            details=f"Removed {removed} stale components",
        )

    if operation == "merge":
        if not app_dir:
            return RememberResult(operation="merge", app_name=app_name, details="No memory found")
        states = load_states(app_dir)
        transitions = {}
        try:
            from app_memory import load_transitions
            transitions = load_transitions(app_dir)
        except Exception:
            pass
        merged = merge_similar_states(states, transitions)
        save_states(app_dir, states)
        return RememberResult(
            operation="merge", app_name=app_name,
            details=f"Merged {merged} similar states",
        )

    return RememberResult(
        operation=operation, app_name=app_name,
        details=f"Unknown operation: {operation}",
    )


def navigate(session: Session, target_state: str, app_name: str) -> NavigateResult:
    """Navigate through an app's state graph to reach a target state.

    Flow: identify current state → BFS path → execute steps → verify each transition
    """
    from app_memory import (
        get_app_dir, load_states, load_transitions, load_workflows,
    )

    current = identify_state(app_name)
    start = current.state_name or "unknown"

    app_dir = get_app_dir(app_name)
    if not app_dir:
        return NavigateResult(
            start_state=start, target_state=target_state,
            path=[], steps_taken=0, reached_target=False, current_state=start,
        )

    states = load_states(app_dir)
    transitions = {}
    try:
        transitions = load_transitions(app_dir)
    except Exception:
        pass

    # BFS to find path
    path = _bfs_path(states, transitions, start, target_state)

    if not path:
        # No known path — ask LLM what to try
        prompt = f"""You need to navigate from "{start}" to "{target_state}" in {app_name}.
No known path exists in the state graph.
Known states: {list(states.keys())[:20]}

What element should I click to explore? Suggest a target name from the current screen.
Return JSON: {{"suggestion": "element_name"}}"""

        reply = session.send(prompt)
        return NavigateResult(
            start_state=start, target_state=target_state,
            path=[], steps_taken=0, reached_target=False, current_state=start,
        )

    # Follow the path
    steps = 0
    current_state = start
    traversed = [start]

    for next_state in path[1:]:
        # Find the transition action
        trans_key = f"{current_state}→{next_state}"
        action_info = transitions.get(trans_key, {})
        click_target = action_info.get("click_component", next_state)

        # Execute the step
        result = act(session, "click", click_target, app_name=app_name)
        steps += 1

        # Verify
        new_state = identify_state(app_name)
        current_state = new_state.state_name or "unknown"
        traversed.append(current_state)

        if current_state == target_state:
            break

    return NavigateResult(
        start_state=start,
        target_state=target_state,
        path=traversed,
        steps_taken=steps,
        reached_target=current_state == target_state,
        current_state=current_state,
    )


def verify(session: Session, expected: str) -> VerifyResult:
    """Verify whether a previous action succeeded.

    Flow: screenshot → OCR → LLM judges success
    """
    shot = take_screenshot()
    ocr = run_ocr(shot.path)
    ocr_lines = [f"  '{t.get('label', '')}'" for t in ocr.texts[:30]]

    prompt = f"""Verify whether the expected outcome was achieved.

## Expected
{expected}

## OCR text on screen
{chr(10).join(ocr_lines) if ocr_lines else '(none)'}

## Screenshot
(attached)

Was the expected outcome achieved? Provide evidence.

Return JSON:
{json.dumps(VerifyResult.model_json_schema(), indent=2)}"""

    reply = session.send({"text": prompt, "images": [shot.path]})

    try:
        data = _parse_json(reply)
        data.setdefault("screenshot_path", shot.path)
        return VerifyResult(**data)
    except Exception:
        return VerifyResult(
            expected=expected, actual=reply[:200],
            verified=False, evidence="Failed to parse LLM response",
            screenshot_path=shot.path,
        )


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def _parse_json(reply: str) -> dict:
    """Parse JSON from LLM reply, handling markdown code blocks."""
    text = reply.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _bfs_path(states: dict, transitions: dict, start: str, target: str) -> list[str]:
    """BFS shortest path through the state graph."""
    if start == target:
        return [start]

    from collections import deque
    queue = deque([(start, [start])])
    visited = {start}

    # Build adjacency from transitions
    adj = {}
    for key in transitions:
        if "→" in key:
            src, dst = key.split("→", 1)
            adj.setdefault(src, []).append(dst)

    while queue:
        current, path = queue.popleft()
        for neighbor in adj.get(current, []):
            if neighbor == target:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return []  # no path found
