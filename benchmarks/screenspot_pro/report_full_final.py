#!/usr/bin/env python3
"""Format the canonical ScreenSpot-Pro monitor report for Discord."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINAL_DIR = Path("runs/screenspot_pro/iter_zoom_recrop_full_final_20260602")


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )


def load_summary(final_dir: Path) -> dict[str, Any]:
    return json.loads((REPO_ROOT / final_dir / "summary.json").read_text())


def pct(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value * 100:.2f}%"


def accuracy(stats: dict[str, Any]) -> float | None:
    completed = int(stats.get("completed") or 0)
    if completed == 0:
        return None
    return float(stats.get("accuracy_completed") or 0)


def compact_counts(stats: dict[str, Any]) -> str:
    return (
        f"{stats.get('correct', 0)}C/"
        f"{stats.get('wrong', 0)}W/"
        f"{stats.get('wrong_format', 0)}WF"
    )


def format_subset(entry: dict[str, Any]) -> str:
    apps = []
    for app in entry.get("apps", []):
        apps.append(
            f"{app['code']} {app['completed']}/{app['expected']} {pct(accuracy(app))}"
        )
    header = (
        f"- {entry['subset']} {entry['completed']}/{entry['expected']} "
        f"{pct(accuracy(entry))}（{compact_counts(entry)}，pending {entry['pending_retry']}）"
    )
    return header + "\n  " + "；".join(apps)


def autoretry_status(payload: dict[str, Any]) -> str:
    reason = payload.get("reason")
    if payload.get("started"):
        return f"刚启动 {payload.get('screen_name')}，run {payload.get('run_dir')}"
    if reason == "already_running":
        return f"已在跑（{payload.get('screen_name')}），没有新开第二个"
    if reason == "provider_auth_cooldown":
        return "auth cooldown 暂停中；凭证恢复/冷却后会自动续跑"
    if reason == "no_pending_retry":
        return "pending 已清空，无需再开 retry"
    if reason:
        return f"未启动 retry：{reason}"
    return "未启动 retry"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-dir", default=str(DEFAULT_FINAL_DIR))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cooldown-minutes", type=int, default=180)
    parser.add_argument("--skip-autoretry", action="store_true")
    args = parser.parse_args()

    final_dir = Path(args.final_dir)
    run_command([
        args.python,
        "benchmarks/screenspot_pro/sync_full_final.py",
        "--final-dir",
        str(final_dir),
    ])
    autoretry_payload: dict[str, Any] = {"reason": "skipped"}
    if not args.skip_autoretry:
        result = run_command([
            args.python,
            "benchmarks/screenspot_pro/start_full_autoretry.py",
            "--cooldown-minutes",
            str(args.cooldown_minutes),
            "--final-dir",
            str(final_dir),
        ])
        autoretry_payload = json.loads(result.stdout)
    summary = load_summary(final_dir)

    lines = [
        "ScreenSpot-Pro canonical/final：",
        (
            f"总：{summary['completed']}/{summary['expected']}，"
            f"{summary['correct']}C / {summary['wrong']}W / {summary['wrong_format']}WF，"
            f"{pct(summary['accuracy_completed'])}；pending {summary['pending_retry']}，"
            f"ignored infra {summary['ignored_infra_rows']}"
        ),
        f"续跑：{autoretry_status(autoretry_payload)}",
        "按 subset / software：",
    ]
    lines.extend(format_subset(entry) for entry in summary.get("breakdown", []))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
