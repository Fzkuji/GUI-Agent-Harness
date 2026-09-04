import pytest

from gui_harness.tasks import capability_loop


def test_computer_use_binds_window_without_global_target(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def session(app_name, window_id, previous):
        assert (app_name, window_id) == ("Example", 42)
        yield type("Window", (), {"identity": {"window_id": 42}})()

    monkeypatch.setattr(capability_loop, "window_session", session, raising=False)
    monkeypatch.setattr(capability_loop, "gui_step", lambda **kw: {
        "done": True, "terminal_status": "succeeded",
    })
    monkeypatch.setattr(capability_loop, "target_session", lambda: pytest.fail("global input selected"))
    result = capability_loop.computer_use(
        task="inspect", app_name="Example", window_id=42, runtime=object(),
    )
    assert result["target"]["window_id"] == 42
    assert result["completion_verified"] is True


def test_window_error_preserves_handoff_and_never_falls_back(monkeypatch):
    from gui_harness.adapters.mac_window import WindowUnavailable
    def unavailable(*args):
        raise WindowUnavailable("permission missing")
    monkeypatch.setattr(capability_loop, "window_session", unavailable)
    monkeypatch.setattr(capability_loop, "target_session", lambda: pytest.fail("global fallback"))
    result = capability_loop.computer_use(task="inspect", window_id=42, runtime=object())
    assert result["status"] == "infeasible"
    assert not result["success"] and not result["completion_verified"]
    assert result["blocker"] == "permission missing"
    assert result["handoff_instruction"]


def test_planner_selection_preserves_exact_window(monkeypatch):
    monkeypatch.setattr(capability_loop, "computer_use", lambda **kw: kw)
    result = capability_loop.call_capability("computer_use", {"task": "inspect", "app_name": "Example", "window_id": 42},
        runtime=object(), app_name="desktop", allow_general=True, browser_backend="", vm_url="", feedback=None, max_seconds=30)
    assert result["app_name"] == "Example" and result["window_id"] == 42


def test_window_dispatch_rejects_stale_controls_and_global_commands():
    from gui_harness.adapters.mac_window import MacWindow, WindowUnavailable
    window = MacWindow.__new__(MacWindow)
    window.validate = lambda: None
    window.elements = {}
    with pytest.raises(WindowUnavailable, match="stale"):
        window.dispatch({"call": "window_press", "args": {"target": "old"}})
    element = object()
    window.ax_window = element
    window.elements = {"current": (element, ["AXPress"], False)}
    for action in ("general", "click", "shortcut", "window_set_text"):
        with pytest.raises(WindowUnavailable, match="does not support"):
            window.dispatch({"call": action, "args": {"target": "current", "text": "x"}})


def test_window_control_membership_rechecked():
    from gui_harness.adapters.mac_window import MacWindow, WindowUnavailable
    window = MacWindow.__new__(MacWindow)
    window.validate = lambda: None
    window.ax_window = object()
    window.elements = {"current": (object(), ["AXPress"], False)}
    window.attr = lambda *args: None
    with pytest.raises(WindowUnavailable, match="no longer belongs"):
        window.dispatch({"call": "window_press", "args": {"target": "current"}})


def test_application_lock_rejects_concurrent_operations(monkeypatch):
    import os
    from gui_harness.adapters import mac_window
    window = type("Window", (), {"pid": os.getpid()})()
    monkeypatch.setattr(mac_window, "MacWindow", lambda *args: window)
    with mac_window.window_session("fixture"):
        assert mac_window.current_window() is window
        with pytest.raises(mac_window.WindowUnavailable, match="currently owns"):
            with mac_window.window_session("fixture"):
                pytest.fail("concurrent operation accepted")
    assert mac_window.current_window() is None


def test_switching_window_does_not_verify_old_window_feedback(monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def session(app_name, window_id, previous):
        assert previous is None
        yield type("Window", (), {"identity": {"window_id": window_id}})()
    def step(**kwargs):
        assert kwargs["feedback"] is None
        return {"done": True, "terminal_status": "succeeded"}
    monkeypatch.setattr(capability_loop, "window_session", session)
    monkeypatch.setattr(capability_loop, "gui_step", step)
    capability_loop.computer_use(task="inspect", window_id=43, runtime=object(),
        feedback={"window_target": {"window_id": 42}, "goal": "old window goal"})


def test_window_capability_status_is_not_ml_dependency_status(monkeypatch):
    monkeypatch.setattr(capability_loop.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(capability_loop, "window_support", lambda: {"available": False, "reason": "permission missing"})
    monkeypatch.setattr(capability_loop, "window_inventory", lambda: pytest.fail("inventory before permission"))
    status = capability_loop.capability_status()["computer_use"]
    assert not status["available"] and status["reason"] == "permission missing"


def test_unavailable_capture_api_returns_explicit_limit(monkeypatch):
    import sys
    import types
    from gui_harness.adapters import mac_window
    monkeypatch.setattr(mac_window.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(mac_window.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setitem(sys.modules, "ScreenCaptureKit", types.SimpleNamespace())
    result = mac_window.window_support()
    assert not result["available"] and "macOS 14" in result["reason"]


def test_background_plan_can_clear_text(monkeypatch):
    import json
    from gui_harness.tasks import execute_task
    from gui_harness.adapters.mac_window import MacWindow
    window = MacWindow.__new__(MacWindow)
    monkeypatch.setattr(execute_task, "current_window", lambda: window)
    monkeypatch.setattr(execute_task, "llm", lambda *a, **kw: json.dumps({"call": "window_set_text", "args": {"target": "control", "text": ""}}))
    result = execute_task.plan_next_action(task="clear the field", img_path="fixture.png", component_info="", verification_summary="", transitions_info="", action_catalog="")
    assert result["call"] == "window_set_text" and result["args"]["text"] == ""


def test_ax_requests_stop_on_cancellation_and_deadline(monkeypatch):
    from gui_harness.adapters import mac_window
    window = mac_window.MacWindow.__new__(mac_window.MacWindow)
    window._deadline = None
    calls = []
    window.ax = type("AX", (), {"AXUIElementCopyAttributeValue": staticmethod(lambda *a: (calls.append(a) or (0, "value")))})()
    monkeypatch.setattr(mac_window, "_cancel", lambda: None)
    assert window.attr(object(), "AXRole") == "value"
    def cancelled():
        raise RuntimeError("cancelled")
    monkeypatch.setattr(mac_window, "_cancel", cancelled)
    with pytest.raises(RuntimeError, match="cancelled"):
        window.attr(object(), "AXChildren")
    assert len(calls) == 1
    monkeypatch.setattr(mac_window, "_cancel", lambda: None)
    window._deadline = 0
    with pytest.raises(mac_window.WindowUnavailable, match="timed out"):
        window.attr(object(), "AXChildren")
    assert len(calls) == 1
