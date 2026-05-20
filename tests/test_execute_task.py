"""Tests for execute_task planning helpers."""

from gui_harness.tasks.execute_task import _normalize_plan


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

