#!/usr/bin/env python3
"""Start a high-retry ScreenSpot-Pro rerun for all wrong_format OS samples.

The normal OS sweep writes separate result files for Linux, macOS, and Windows.
This helper waits until those files cover the full OS subset, collects the
latest wrong_format rows, and starts one detached screen that reruns only those
sample indexes with more provider retries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PYTHON = "../GUI-Agent-Harness-run-origin-main/.venv/bin/python"
DEFAULT_SCREEN_NAME = "screenspot_wf_retry"
DEFAULT_METADATA = Path("runs/screenspot_pro/wf_retry_latest.json")


@dataclass(frozen=True)
class RunSpec:
    annotation: str
    expected: int
    outputs: tuple[Path, ...]
    label: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", self.annotation.removesuffix(".json"))


RUN_SPECS = (
    RunSpec(
        annotation="linux_common_linux.json",
        expected=50,
        outputs=(Path("runs/screenspot_pro/linux_common_screenspot_locator_20260528_1835.jsonl"),),
    ),
    RunSpec(
        annotation="macos_common_macos.json",
        expected=65,
        outputs=(
            Path("runs/screenspot_pro/macos_common_screenspot_locator_20260528_2038.jsonl"),
            Path("runs/screenspot_pro/macos_common_macos32_retry_20260528_2320.jsonl"),
        ),
    ),
    RunSpec(
        annotation="windows_common_windows.json",
        expected=81,
        outputs=(Path("runs/screenspot_pro/windows_common_screenspot_locator_20260528_2038.jsonl"),),
    ),
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def latest_rows(spec: RunSpec) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for output in spec.outputs:
        for row in read_jsonl(REPO_ROOT / output):
            sample_id = str(row.get("sample_id") or "")
            if sample_id:
                rows[sample_id] = row
    return rows


def sample_index(sample_id: str) -> int:
    match = re.search(r"_(\d+)$", sample_id)
    if not match:
        raise ValueError(f"cannot parse sample index from {sample_id!r}")
    return int(match.group(1))


def collect_wrong_format() -> tuple[dict[str, list[int]], list[str], dict[str, dict[str, int]]]:
    indexes_by_annotation: dict[str, list[int]] = {}
    incomplete: list[str] = []
    counts: dict[str, dict[str, int]] = {}
    for spec in RUN_SPECS:
        rows = latest_rows(spec)
        correctness_counts = {
            "total": len(rows),
            "correct": sum(1 for row in rows.values() if row.get("correctness") == "correct"),
            "wrong": sum(1 for row in rows.values() if row.get("correctness") == "wrong"),
            "wrong_format": sum(1 for row in rows.values() if row.get("correctness") == "wrong_format"),
            "incomplete": sum(1 for row in rows.values() if row.get("correctness") == "incomplete"),
        }
        counts[spec.annotation] = correctness_counts
        if len(rows) < spec.expected:
            incomplete.append(f"{spec.annotation} {len(rows)}/{spec.expected}")
        wf_indexes = sorted(
            sample_index(sample_id)
            for sample_id, row in rows.items()
            if row.get("correctness") == "wrong_format"
        )
        if wf_indexes:
            indexes_by_annotation[spec.annotation] = wf_indexes
    return indexes_by_annotation, incomplete, counts


def screen_exists(screen_name: str) -> bool:
    result = subprocess.run(["screen", "-ls"], cwd=REPO_ROOT, text=True, capture_output=True)
    return screen_name in result.stdout


def quote_indexes(indexes: list[int]) -> str:
    return ",".join(str(index) for index in indexes)


def build_screen_script(
    *,
    screen_name: str,
    timestamp: str,
    indexes_by_annotation: dict[str, list[int]],
    python: str,
    sample_timeout_s: int,
    runtime_retries: int,
    retry_provider_errors: int,
) -> str:
    lines = [
        "set -e",
        f"cd {shlex.quote(str(REPO_ROOT))}",
        "mkdir -p runs/screenspot_pro/logs",
        f"echo '[wf_retry] start {timestamp}'",
    ]
    for annotation, indexes in indexes_by_annotation.items():
        label = annotation.removesuffix(".json")
        output = f"runs/screenspot_pro/wf_retry_{label}_{timestamp}.jsonl"
        work_dir = f"runs/screenspot_pro/work_wf_retry_{label}_{timestamp}"
        log = f"runs/screenspot_pro/logs/wf_retry_{label}_{timestamp}.log"
        lines.extend(
            [
                f"echo '[wf_retry] {annotation} indexes {quote_indexes(indexes)}'",
                "PYTHONUNBUFFERED=1 "
                + " ".join(
                    shlex.quote(part)
                    for part in [
                        python,
                        "benchmarks/screenspot_pro/run_screenspot_pro.py",
                        "--annotation",
                        annotation,
                        "--indexes",
                        quote_indexes(indexes),
                        "--output",
                        output,
                        "--work-dir",
                        work_dir,
                        "--provider",
                        "openai-codex",
                        "--model",
                        "gpt-5.5",
                        "--sample-timeout-s",
                        str(sample_timeout_s),
                        "--runtime-retries",
                        str(runtime_retries),
                        "--retry-provider-errors",
                        str(retry_provider_errors),
                        "--skip-existing",
                    ]
                )
                + f" 2>&1 | tee -a {shlex.quote(log)}",
            ]
        )
    lines.append(f"echo '[wf_retry] done {timestamp}'")
    return "\n".join(lines) + "\n"


def start_screen(screen_name: str, script: str) -> None:
    subprocess.run(
        ["screen", "-dmS", screen_name, "bash", "-lc", script],
        cwd=REPO_ROOT,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-if-ready", action="store_true")
    parser.add_argument("--screen-name", default=DEFAULT_SCREEN_NAME)
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--sample-timeout-s", type=int, default=900)
    parser.add_argument("--runtime-retries", type=int, default=8)
    parser.add_argument("--retry-provider-errors", type=int, default=5)
    args = parser.parse_args()

    indexes_by_annotation, incomplete, counts = collect_wrong_format()
    payload: dict[str, Any] = {
        "ready": not incomplete,
        "started": False,
        "screen_name": args.screen_name,
        "counts": counts,
        "wrong_format_indexes": indexes_by_annotation,
        "incomplete": incomplete,
        "retry_settings": {
            "sample_timeout_s": args.sample_timeout_s,
            "runtime_retries": args.runtime_retries,
            "retry_provider_errors": args.retry_provider_errors,
        },
    }

    if incomplete:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    if not indexes_by_annotation:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if screen_exists(args.screen_name):
        payload["already_running"] = True
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    metadata_path = REPO_ROOT / args.metadata
    if metadata_path.exists():
        try:
            previous = json.loads(metadata_path.read_text())
        except json.JSONDecodeError:
            previous = {}
        if previous.get("screen_name") == args.screen_name and previous.get("started"):
            payload["already_started"] = True
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

    if args.start_if_ready:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        payload["timestamp"] = timestamp
        script = build_screen_script(
            screen_name=args.screen_name,
            timestamp=timestamp,
            indexes_by_annotation=indexes_by_annotation,
            python=args.python,
            sample_timeout_s=args.sample_timeout_s,
            runtime_retries=args.runtime_retries,
            retry_provider_errors=args.retry_provider_errors,
        )
        start_screen(args.screen_name, script)
        payload["started"] = True
        payload["script"] = script
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
