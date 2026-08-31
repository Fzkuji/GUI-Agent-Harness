from __future__ import annotations

import sys
from types import SimpleNamespace

import gui_harness.main as main_module


def test_cli_returns_nonzero_for_failed_task(monkeypatch, tmp_path):
    runtime = SimpleNamespace(set_workdir=lambda _path: None)
    monkeypatch.setattr(main_module, "create_runtime", lambda **_kwargs: runtime)
    monkeypatch.setattr(
        main_module,
        "gui_agent",
        lambda **kwargs: {
            "task": kwargs["task"],
            "success": False,
            "steps_taken": 1,
            "total_time": 0.1,
            "history": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["gui-agent", "--work-dir", str(tmp_path), "impossible task"],
    )

    assert main_module.main() == 1


def test_cli_returns_zero_for_successful_task(monkeypatch, tmp_path):
    runtime = SimpleNamespace(set_workdir=lambda _path: None)
    monkeypatch.setattr(main_module, "create_runtime", lambda **_kwargs: runtime)
    monkeypatch.setattr(
        main_module,
        "gui_agent",
        lambda **kwargs: {
            "task": kwargs["task"],
            "success": True,
            "steps_taken": 1,
            "total_time": 0.1,
            "history": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["gui-agent", "--work-dir", str(tmp_path), "completed task"],
    )

    assert main_module.main() == 0
