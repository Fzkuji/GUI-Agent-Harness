"""Tests for execute_task planning helpers."""

import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from gui_harness.tasks.execute_task import _action_fail, _normalize_plan

module = importlib.import_module("gui_harness.tasks.execute_task")
result_module = importlib.import_module("gui_harness.tasks.result")
component_memory = importlib.import_module("gui_harness.planning.component_memory")
dispatch = importlib.import_module("gui_harness.action.dispatch")
observe_module = importlib.import_module("gui_harness.perception.observe")


def test_fail_action_is_unsuccessful_and_preserves_handoff_reason():
    result = _action_fail("FAIL/INFEASIBLE: human must log in")

    assert result == {
        "success": False,
        "done": True,
        "infeasible": True,
        "reasoning": "FAIL/INFEASIBLE: human must log in",
    }


def test_normalize_plan_accepts_direct_action():
    parsed = {"call": "click", "args": {"target": "OK button"}, "goal": "confirm"}
    assert _normalize_plan(parsed) == parsed


def test_normalize_plan_unwraps_gui_step_shape():
    parsed = {
        "done": False,
        "plan": {
            "call": "click",
            "args": {"target": "Export button"},
            "goal": "confirm export",
        },
    }
    assert _normalize_plan(parsed) == parsed["plan"]


def test_normalize_plan_done_wrapper():
    assert _normalize_plan({"done": True, "plan": {}})["call"] == "done"


def test_invalid_planner_reply_is_not_converted_to_done(monkeypatch):
    replies = iter(["invalid", "still invalid"])
    monkeypatch.setattr(module, "llm", lambda *_args, **_kwargs: next(replies))

    result = module.plan_next_action._fn(
        task="task",
        img_path="screen.png",
        component_info="",
        verification_summary="",
        transitions_info="",
        action_catalog="",
    )

    assert result["call"] == "planner_error"
    assert result["reason_code"] == "planner_invalid_action"


def test_planner_action_missing_required_arguments_is_rejected(monkeypatch):
    replies = iter([
        '{"call":"fail","args":{},"goal":"stop"}',
        '{"call":"fail","args":{},"goal":"stop"}',
    ])
    monkeypatch.setattr(module, "llm", lambda *_args, **_kwargs: next(replies))

    result = module.plan_next_action._fn(
        task="task",
        img_path="screen.png",
        component_info="",
        verification_summary="",
        transitions_info="",
        action_catalog="",
    )

    assert result["call"] == "planner_error"
    assert result["reason_code"] == "planner_invalid_arguments"


def _observation():
    return {
        "img_path": "screen.png",
        "component_info": "",
        "transitions_info": "",
        "current_state": "state-1",
        "screenshot_artifact": None,
    }


def test_first_step_done_requires_current_screen_verification(monkeypatch):
    seen = {}
    monkeypatch.setattr(module, "observe_screen", lambda _app: _observation())

    def verify(**kwargs):
        seen.update(kwargs["feedback"])
        return {
            "step_succeeded": True,
            "observation": "app is not open",
            "completion_evidence": "",
            "remaining_plan": ["open the app"],
            "completion_risks": ["task has not started"],
            "ready_to_done": False,
        }

    monkeypatch.setattr(module, "verify_step", verify)
    monkeypatch.setattr(
        module,
        "plan_next_action",
        lambda **_kwargs: {"call": "done", "reasoning": "already complete"},
    )

    result = module.gui_step._fn(
        task="open Calculator", feedback=None, app_name="desktop", runtime=object(),
    )

    assert seen["initial_observation"] is True
    assert result["done"] is False
    assert result["plan"]["blocked_by_completion_verify"] is True


def test_first_step_read_only_done_can_pass_current_screen_verification(monkeypatch):
    monkeypatch.setattr(module, "observe_screen", lambda _app: _observation())
    monkeypatch.setattr(
        module,
        "verify_step",
        lambda **_kwargs: {
            "step_succeeded": True,
            "observation": "screen content is visible",
            "completion_evidence": "the requested content is visible",
            "remaining_plan": [],
            "completion_risks": [],
            "ready_to_done": True,
        },
    )
    monkeypatch.setattr(
        module,
        "plan_next_action",
        lambda **_kwargs: {"call": "done", "reasoning": "content described"},
    )

    result = module.gui_step._fn(
        task="describe the screen", feedback=None, app_name="desktop", runtime=object(),
    )

    assert result["done"] is True
    assert result["terminal_status"] == "succeeded"


def test_fourth_identical_failed_action_stops_even_when_interleaved(monkeypatch):
    monkeypatch.setattr(module, "observe_screen", lambda _app: _observation())
    monkeypatch.setattr(
        module,
        "verify_step",
        lambda **_kwargs: {
            "step_succeeded": False,
            "observation": "button is unchanged",
            "completion_evidence": "",
            "remaining_plan": ["use a different control"],
            "completion_risks": ["same click failed"],
            "ready_to_done": False,
        },
    )
    plan = {"call": "click", "args": {"target": "Missing"}, "goal": "continue"}
    monkeypatch.setattr(module, "plan_next_action", lambda **_kwargs: plan)
    monkeypatch.setattr(
        module,
        "dispatch_action",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )
    feedback = {
        "goal": "continue",
        "action": "click",
        "target": "Missing",
        "success": False,
        "recent_actions": [
            {"fingerprint": 'click:{"target":"Missing"}', "success": False},
            {"fingerprint": 'press:{"key":"tab"}', "success": True},
            {"fingerprint": 'click:{"target":"Missing"}', "success": False},
            {"fingerprint": 'click:{"target":"Other"}', "success": True},
            {"fingerprint": 'click:{"target":"Missing"}', "success": False},
        ],
    }

    result = module.gui_step._fn(
        task="long task", feedback=feedback, app_name="desktop", runtime=object(),
    )

    assert result["done"] is True
    assert result["terminal_status"] == "failed"
    assert result["reason_code"] == "repeated_action"


def test_step_feedback_keeps_bounded_recent_action_state():
    previous = {
        "recent_actions": [
            {"fingerprint": f"click:{index}", "success": True}
            for index in range(12)
        ],
        "consecutive_failures": 2,
    }
    result = {
        "plan": {"call": "click", "args": {"target": "Missing"}},
        "exec_result": {"success": False, "error": "not found"},
        "state": "state-1",
    }

    feedback = module.build_step_feedback(result, previous_feedback=previous)

    assert len(feedback["recent_actions"]) == 8
    assert feedback["consecutive_failures"] == 3


def test_step_feedback_reconciles_previous_action_with_visual_verification():
    previous = {
        "recent_actions": [{
            "fingerprint": 'hotkey:{"keys":"command+shift+g"}',
            "success": True,
        }],
    }
    result = {
        "plan": {"call": "click", "args": {"target": "Where"}},
        "exec_result": {"success": True},
        "verification": {"step_succeeded": False},
    }

    feedback = module.build_step_feedback(result, previous_feedback=previous)

    assert feedback["recent_actions"][0] == {
        "fingerprint": 'hotkey:{"keys":"command+shift+g"}',
        "success": False,
        "verified": True,
    }
    assert feedback["recent_actions"][1]["success"] is True


def test_macos_printable_shortcut_uses_system_events(monkeypatch):
    input_module = importlib.import_module("gui_harness.action.input")
    calls = []
    monkeypatch.setattr(
        input_module.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    input_module.LocalTarget(platform_name="darwin").key_combo(
        "command", "shift", "g",
    )

    assert calls == [(([
        "osascript",
        "-e",
        'tell application "System Events" to key code 5 using {command down, shift down}',
    ],), {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 5,
    })]


def test_macos_screenshot_retries_timeout_without_returning_stale_file(
    tmp_path, monkeypatch,
):
    screenshot_module = importlib.import_module(
        "gui_harness.perception.screenshot",
    )
    output = tmp_path / "screen.png"
    output.write_bytes(b"stale")
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 5)
        Path(command[-1]).write_bytes(b"fresh")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(screenshot_module, "SYSTEM", "Darwin")
    monkeypatch.setattr(screenshot_module.subprocess, "run", run)
    monkeypatch.setattr(screenshot_module.time, "sleep", lambda _seconds: None)

    assert screenshot_module.screenshot(str(output)) == str(output)
    assert output.read_bytes() == b"fresh"
    assert len(calls) == 2


def test_set_macos_save_path_populates_directory_and_filename_without_saving(
    tmp_path, monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        dispatch,
        "time",
        SimpleNamespace(sleep=lambda seconds: calls.append(("wait", seconds))),
    )
    monkeypatch.setattr(
        dispatch.actions,
        "shortcut",
        lambda keys: calls.append(("shortcut", keys)),
    )
    monkeypatch.setattr(
        dispatch.actions,
        "paste_text",
        lambda text: calls.append(("paste", text)),
    )
    monkeypatch.setattr(
        dispatch.actions,
        "key_press",
        lambda key: calls.append(("press", key)),
    )
    input_module = importlib.import_module("gui_harness.action.input")
    monkeypatch.setattr(
        input_module,
        "get_target",
        lambda: SimpleNamespace(platform="darwin"),
    )
    destination = tmp_path / "exact.txt"

    result = dispatch.set_macos_save_path(str(destination))

    assert result == {
        "success": True,
        "path": str(destination),
        "action": "set_save_path",
    }
    assert calls == [
        ("shortcut", "command+shift+g"),
        ("wait", 0.8),
        ("paste", str(tmp_path)),
        ("press", "enter"),
        ("wait", 0.8),
        ("shortcut", "command+a"),
        ("paste", "exact.txt"),
    ]


def test_desktop_observation_exposes_frontmost_app_and_screen_bounds(
    monkeypatch,
):
    monkeypatch.setenv("GUI_HARNESS_UI_SETTLE_SECONDS", "0")
    monkeypatch.setattr(observe_module.screenshot, "take", lambda: "screen.png")
    monkeypatch.setattr(
        observe_module,
        "detect_components",
        lambda _path: {
            "icons": [],
            "texts": [],
            "img_w": 3024,
            "img_h": 1964,
        },
    )
    monkeypatch.setattr(observe_module, "get_frontmost_app", lambda: "TextEdit")

    result = observe_module.observe_screen("desktop")

    assert result["frontmost_app"] == "TextEdit"
    assert '<screen_coordinates width="3024" height="1964" />' in result["component_info"]
    assert "<frontmost_app>TextEdit</frontmost_app>" in result["component_info"]


def test_workflow_record_uses_runtime_state_not_package_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("GUI_HARNESS_STATE_DIR", str(tmp_path))

    result_module.save_workflow_record({"status": "failed"}, "Example App")

    records = list((tmp_path / "workflows" / "example_app").glob("workflow_*.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text()) == {"status": "failed"}


def test_type_action_uses_layout_independent_paste():
    registry = module._build_action_registry()

    assert registry["type"]["function"].__name__ == "paste_text"


def test_deterministic_text_match_accepts_short_keypad_labels():
    texts = [
        {"label": "AC", "cx": 10, "cy": 20},
        {"label": "7", "cx": 30, "cy": 40},
    ]

    assert component_memory._deterministic_text_match(
        "AC all clear button", texts,
    )["name"] == "AC"
    assert component_memory._deterministic_text_match(
        "gray number 7 button", texts,
    )["name"] == "7"


def test_deterministic_text_match_does_not_accept_incidental_long_token():
    assert component_memory._deterministic_text_match(
        "Calculator result in Spotlight search results",
        [{"label": "Calculator", "cx": 10, "cy": 20}],
    ) is None


def test_deterministic_text_match_accepts_operator_only_labels():
    texts = [
        {"label": "×", "cx": 10, "cy": 20},
        {"label": "÷", "cx": 30, "cy": 40},
        {"label": "=", "cx": 50, "cy": 60},
    ]

    assert component_memory._deterministic_text_match("×", texts)["name"] == "×"
    assert component_memory._deterministic_text_match("divide ÷", texts)["name"] == "÷"
    assert component_memory._deterministic_text_match("equals =", texts)["name"] == "="


def test_retina_location_is_converted_only_at_click_boundary(monkeypatch):
    monkeypatch.setattr(dispatch.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        "gui_harness.action.input.get_default_name", lambda: "local",
    )
    monkeypatch.setattr(
        "gui_harness.platform_info.dpi.screen_scale", lambda: 2.0,
    )

    result = dispatch._location_to_click_space({"cx": 2388, "cy": 1288})

    assert result == {
        "cx": 1194,
        "cy": 644,
        "pixel_cx": 2388,
        "pixel_cy": 1288,
        "coordinate_scale": 2.0,
    }
