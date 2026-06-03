#!/usr/bin/env python3
"""Summarize ScreenSpot v1/v2 evaluation progress."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"[screenspot-report] skip invalid JSONL {path}:{line_no}")
    return rows


def load_plan(run_dir: Path) -> list[dict[str, Any]]:
    plan_path = run_dir / "plan.tsv"
    entries = []
    for line in plan_path.read_text().splitlines():
        if not line.strip():
            continue
        dataset, annotation, index, sample_id, shard_or_reason = line.split("\t")[:5]
        split = annotation.removeprefix(f"screenspot_{dataset}_").removesuffix(".json")
        try:
            shard = int(shard_or_reason)
            retry_reason = None
        except ValueError:
            shard = None
            retry_reason = shard_or_reason
        entries.append({
            "dataset": dataset,
            "annotation": annotation,
            "split": split,
            "index": int(index),
            "sample_id": sample_id,
            "shard": shard,
            "retry_reason": retry_reason,
        })
    return entries


def load_annotation_rows(dataset: str, annotation: str) -> list[dict[str, Any]]:
    path = REPO_ROOT / "benchmarks/screenspot_pro" / f"data_screenspot_{dataset}" / "annotations" / annotation
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data if isinstance(data, list) else []


def result_rows(run_dir: Path, dataset: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    shard_dirs = [run_dir / dataset / "shards"]
    if not shard_dirs[0].exists():
        shard_dirs.append(run_dir / "shards")
    for shard_dir in shard_dirs:
        if not shard_dir.exists():
            continue
        for path in sorted(shard_dir.glob("*.jsonl")):
            if path.name.endswith(".errors.jsonl"):
                continue
            rows.extend(read_jsonl(path))
    return rows


def load_run_metadata(run_dir: Path) -> dict[str, Any]:
    metadata_path = run_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            return {
                "provider": metadata.get("provider"),
                "model": metadata.get("model"),
            }
        except json.JSONDecodeError:
            pass

    run_script = run_dir / "run.sh"
    metadata: dict[str, Any] = {"provider": None, "model": None}
    if not run_script.exists():
        return metadata
    text = run_script.read_text(errors="replace")
    provider = re.search(r"--provider\s+([^\s\\]+)", text)
    model = re.search(r"--model\s+([^\s\\]+)", text)
    if provider:
        metadata["provider"] = provider.group(1).strip("'\"")
    if model:
        metadata["model"] = model.group(1).strip("'\"")
    return metadata


def latest_by_sample(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = row.get("sample_id")
        if sample_id:
            latest[str(sample_id)] = row
    return latest


def empty_stats() -> dict[str, Any]:
    return {
        "expected": 0,
        "completed": 0,
        "correct": 0,
        "wrong": 0,
        "wrong_format": 0,
        "pending": 0,
    }


def add_row(stats: dict[str, Any], row: dict[str, Any] | None) -> None:
    stats["expected"] += 1
    if row is None:
        stats["pending"] += 1
        return
    stats["completed"] += 1
    correctness = row.get("correctness")
    if correctness in ("correct", "wrong", "wrong_format"):
        stats[correctness] += 1


def pct(stats: dict[str, Any]) -> str:
    completed = stats["completed"]
    if completed == 0:
        return "--"
    return f"{stats['correct'] / completed * 100:.2f}%"


def compact(stats: dict[str, Any]) -> str:
    return f"{stats['correct']}C/{stats['wrong']}W/{stats['wrong_format']}WF"


def screen_alive(screen_name: str | None) -> bool | None:
    if not screen_name:
        return None
    result = subprocess.run(["screen", "-ls"], cwd=REPO_ROOT, text=True, capture_output=True)
    return screen_name in result.stdout


def summarize(run_dir: Path) -> dict[str, Any]:
    plan = load_plan(run_dir)
    datasets = sorted({entry["dataset"] for entry in plan})
    payload: dict[str, Any] = {
        "run_dir": str(run_dir.relative_to(REPO_ROOT)),
        **load_run_metadata(run_dir),
        "datasets": {},
    }
    for dataset in datasets:
        latest = latest_by_sample(result_rows(run_dir, dataset))
        dataset_stats = empty_stats()
        split_stats: dict[str, dict[str, Any]] = defaultdict(empty_stats)
        type_stats: dict[str, dict[str, Any]] = defaultdict(empty_stats)
        split_type_stats: dict[str, dict[str, Any]] = defaultdict(empty_stats)
        annotation_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        error_categories: Counter[str] = Counter()
        for entry in plan:
            if entry["dataset"] != dataset:
                continue
            row = latest.get(entry["sample_id"])
            cache_key = (entry["dataset"], entry["annotation"])
            annotation_rows = annotation_cache.setdefault(
                cache_key,
                load_annotation_rows(entry["dataset"], entry["annotation"]),
            )
            annotation_row = (
                annotation_rows[entry["index"]]
                if 0 <= entry["index"] < len(annotation_rows)
                else {}
            )
            ui_type = str(annotation_row.get("ui_type") or annotation_row.get("data_type") or "unknown")
            ui_type = ui_type.lower()
            add_row(dataset_stats, row)
            add_row(split_stats[entry["split"]], row)
            add_row(type_stats[ui_type], row)
            add_row(split_type_stats[f"{entry['split']}-{ui_type}"], row)
            if row and isinstance(row.get("error"), dict):
                category = row["error"].get("category")
                if category:
                    error_categories[str(category)] += 1
        payload["datasets"][dataset] = {
            **dataset_stats,
            "accuracy_completed": (dataset_stats["correct"] / dataset_stats["completed"])
            if dataset_stats["completed"]
            else None,
            "splits": dict(sorted(split_stats.items())),
            "types": dict(sorted(type_stats.items())),
            "split_types": dict(sorted(split_type_stats.items())),
            "error_categories": dict(error_categories),
        }
    return payload


def format_report(payload: dict[str, Any], alive: bool | None) -> str:
    dataset_names = "/".join(payload["datasets"].keys())
    lines = [f"ScreenSpot {dataset_names} full:"]
    lines.append(f"run: {payload['run_dir']}")
    if payload.get("provider") or payload.get("model"):
        lines.append(f"model: {payload.get('provider') or '?'} / {payload.get('model') or '?'}")
    if alive is not None:
        lines.append(f"screen: {'alive' if alive else 'not alive'}")
    for dataset, stats in payload["datasets"].items():
        lines.append(
            f"{dataset}: {stats['completed']}/{stats['expected']}，"
            f"{compact(stats)}，{pct(stats)}；pending {stats['pending']}"
        )
        split_parts = []
        for split, split_stat in stats["splits"].items():
            split_parts.append(
                f"{split} {split_stat['completed']}/{split_stat['expected']} {pct(split_stat)}"
            )
        if split_parts:
            lines.append("  " + "；".join(split_parts))
        type_parts = []
        for key, type_stat in stats.get("split_types", {}).items():
            type_parts.append(f"{key} {type_stat['completed']}/{type_stat['expected']} {pct(type_stat)}")
        if type_parts:
            lines.append("  by type: " + "；".join(type_parts))
        if stats["error_categories"]:
            errors = "，".join(f"{k}={v}" for k, v in sorted(stats["error_categories"].items()))
            lines.append(f"  errors: {errors}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--screen-name", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    run_dir = (REPO_ROOT / args.run_dir).resolve() if not Path(args.run_dir).is_absolute() else Path(args.run_dir)
    payload = summarize(run_dir)
    alive = screen_alive(args.screen_name) if args.screen_name else None
    if args.json:
        print(json.dumps({"screen_alive": alive, **payload}, ensure_ascii=False, indent=2))
    else:
        print(format_report(payload, alive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
