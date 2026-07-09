#!/usr/bin/env python3
"""Collect ScreenSpot-Pro samples that should be rerun after network failures."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


NETWORK_MARKERS = (
    "RemoteProtocolError",
    "ReadError",
    "ConnectError",
    "ReadTimeout",
    "SampleTimeoutError",
    "sample exceeded watchdog timeout",
    "incomplete chunked read",
    "Server disconnected without sending a response",
)


SAMPLE_START_RE = re.compile(r"^\[screenspot\] (?P<sample_id>[^:]+): ")


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


def read_rows_by_sample(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        sample_id = str(row.get("sample_id") or "")
        if sample_id:
            rows[sample_id] = row
    return rows


def log_segments(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    segments: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text(errors="replace").splitlines():
        match = SAMPLE_START_RE.match(line)
        if match and " -> " not in line:
            current = match.group("sample_id")
            segments.setdefault(current, []).append(line)
            continue
        if current:
            segments.setdefault(current, []).append(line)
    return {sample_id: "\n".join(lines) for sample_id, lines in segments.items()}


def has_network_marker(text: str) -> bool:
    return any(marker in text for marker in NETWORK_MARKERS)


def error_category(row: dict[str, Any]) -> str:
    error = row.get("error")
    if isinstance(error, dict):
        return str(error.get("category") or error.get("type") or "")
    return ""


def row_has_retryable_error(row: dict[str, Any]) -> bool:
    category = error_category(row)
    if category.startswith("provider_") or category in {"sample_timeout"}:
        return True
    error = row.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "")
        return has_network_marker(message)
    return False


def collect_entries(run_specs: list[tuple[str, Path, Path | None]]) -> list[dict[str, Any]]:
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for annotation_file, jsonl_path, log_path in run_specs:
        rows = read_rows_by_sample(jsonl_path)
        segments = log_segments(log_path) if log_path else {}
        for sample_id, row in rows.items():
            if row.get("correctness") == "correct":
                continue
            segment = segments.get(sample_id, "")
            reasons: list[str] = []
            if row_has_retryable_error(row):
                reasons.append("row_error")
            markers = [marker for marker in NETWORK_MARKERS if marker in segment]
            if markers:
                reasons.extend(sorted(set(markers)))
            if not reasons:
                continue
            entries[(annotation_file, sample_id)] = {
                "annotation_file": annotation_file,
                "sample_id": sample_id,
                "correctness": row.get("correctness"),
                "prediction_px": row.get("prediction_px"),
                "gt_bbox": row.get("gt_bbox"),
                "source": (row.get("location") or {}).get("source") or "none",
                "elapsed_s": row.get("elapsed_s"),
                "error_category": error_category(row),
                "reason": ",".join(reasons),
                "run_file": str(jsonl_path),
                "log_file": str(log_path) if log_path else "",
            }
    return [entries[key] for key in sorted(entries)]


def merge_manual_entries(entries: list[dict[str, Any]], manual_path: Path) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {
        (str(entry.get("annotation_file") or ""), str(entry.get("sample_id") or "")): entry
        for entry in entries
    }
    for entry in read_jsonl(manual_path):
        annotation_file = str(entry.get("annotation_file") or "")
        sample_id = str(entry.get("sample_id") or "")
        if annotation_file and sample_id:
            merged[(annotation_file, sample_id)] = entry
    return [merged[key] for key in sorted(merged)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="runs/screenspot_pro/network_retry_queue_20260528.jsonl",
    )
    parser.add_argument(
        "--csv-output",
        default="runs/screenspot_pro/network_retry_queue_20260528.csv",
    )
    parser.add_argument(
        "--manual",
        default="runs/screenspot_pro/network_retry_manual_20260528.jsonl",
        help="Optional JSONL entries to keep in the queue even if no final row exists yet.",
    )
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="annotation,jsonl,log triple. Can be passed multiple times.",
    )
    args = parser.parse_args()

    if args.run:
        run_specs: list[tuple[str, Path, Path | None]] = []
        for item in args.run:
            parts = item.split(",", 2)
            if len(parts) < 2:
                raise SystemExit(f"invalid --run value: {item}")
            annotation_file = parts[0]
            jsonl_path = Path(parts[1])
            log_path = Path(parts[2]) if len(parts) > 2 and parts[2] else None
            run_specs.append((annotation_file, jsonl_path, log_path))
    else:
        run_specs = [
            (
                "linux_common_linux.json",
                Path("runs/screenspot_pro/linux_common_screenspot_locator_20260528_1835.jsonl"),
                Path("runs/screenspot_pro/logs/linux_common_screenspot_locator_20260528_1835.continue.log"),
            ),
            (
                "macos_common_macos.json",
                Path("runs/screenspot_pro/macos_common_screenspot_locator_20260528_2038.jsonl"),
                Path("runs/screenspot_pro/logs/macos_common_screenspot_locator_20260528_2038.log"),
            ),
            (
                "windows_common_windows.json",
                Path("runs/screenspot_pro/windows_common_screenspot_locator_20260528_2038.jsonl"),
                Path("runs/screenspot_pro/logs/windows_common_screenspot_locator_20260528_2038.log"),
            ),
        ]

    entries = merge_manual_entries(collect_entries(run_specs), Path(args.manual))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    csv_path = Path(args.csv_output)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "annotation_file",
        "sample_id",
        "correctness",
        "prediction_px",
        "gt_bbox",
        "source",
        "elapsed_s",
        "error_category",
        "reason",
        "run_file",
        "log_file",
    ]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entries)

    print(f"network_retry_queue={out_path} count={len(entries)}")
    print(f"network_retry_queue_csv={csv_path}")
    for entry in entries:
        print(f"{entry['annotation_file']} {entry['sample_id']} {entry['correctness']} {entry['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
