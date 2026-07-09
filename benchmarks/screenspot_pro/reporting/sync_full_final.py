#!/usr/bin/env python3
"""Maintain one canonical ScreenSpot-Pro full-run result.

This folds the original full sweep, targeted retries, and any later automatic
retry runs into one rolling result directory. Infrastructure/auth failures are
left out of the canonical result so they can be retried instead of being counted
as model-format failures.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE_RUN = Path("runs/screenspot_pro/iter_zoom_recrop_full_parallel_20260601_2056")
DEFAULT_FINAL_DIR = Path("runs/screenspot_pro/iter_zoom_recrop_full_final_20260602")
DEFAULT_LEGACY_OVERLAYS = (
    Path("runs/screenspot_pro/iter_zoom_recrop_wf_recovery_20260601_2335"),
)
AUTORETRY_GLOBS = (
    "iter_zoom_recrop_full_autoretry_*",
    "iter_zoom_recrop_full_final_retry_*",
)
INFRA_ERROR_CATEGORIES = {
    "provider_auth",
}

APP_GROUPS = (
    ("Development", (
        ("android_studio_macos.json", "AS", "Android Studio"),
        ("pycharm_macos.json", "PYC", "PyCharm"),
        ("vscode_macos.json", "VSC", "VS Code"),
        ("vmware_macos.json", "VM", "VMware"),
        ("unreal_engine_windows.json", "UE", "Unreal Engine"),
    )),
    ("Creative", (
        ("photoshop_windows.json", "PS", "Photoshop"),
        ("blender_windows.json", "BL", "Blender"),
        ("premiere_windows.json", "PR", "Premiere"),
        ("davinci_macos.json", "DR", "DaVinci Resolve"),
        ("illustrator_windows.json", "AI", "Illustrator"),
        ("fruitloops_windows.json", "FL", "FL Studio"),
    )),
    ("CAD", (
        ("autocad_windows.json", "CAD", "AutoCAD"),
        ("solidworks_windows.json", "SW", "SolidWorks"),
        ("inventor_windows.json", "INV", "Inventor"),
        ("quartus_windows.json", "QRS", "Quartus"),
        ("vivado_windows.json", "VVD", "Vivado"),
    )),
    ("Scientific", (
        ("matlab_macos.json", "MAT", "MATLAB"),
        ("origin_windows.json", "ORG", "Origin"),
        ("eviews_windows.json", "EVW", "EViews"),
        ("stata_windows.json", "STT", "Stata"),
    )),
    ("Office", (
        ("powerpoint_windows.json", "PPT", "PowerPoint"),
        ("excel_macos.json", "EXC", "Excel"),
        ("word_macos.json", "WRD", "Word"),
    )),
    ("Operating Systems", (
        ("linux_common_linux.json", "LNX", "Linux"),
        ("macos_common_macos.json", "MAC", "macOS"),
        ("windows_common_windows.json", "WIN", "Windows"),
    )),
)

APP_LOOKUP = {
    annotation: {"subset": subset, "code": code, "name": name}
    for subset, apps in APP_GROUPS
    for annotation, code, name in apps
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL") from exc
    return rows


def result_files(run_dir: Path) -> list[Path]:
    shard_dir = run_dir / "shards"
    if shard_dir.exists():
        return sorted(
            p for p in shard_dir.glob("shard_*.jsonl")
            if not p.name.endswith(".errors.jsonl")
        )
    result_path = run_dir / "results.jsonl"
    return [result_path] if result_path.exists() else []


def read_result_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in result_files(run_dir):
        rows.extend(read_jsonl(path))
    return rows


def error_category(row: dict[str, Any]) -> str:
    error = row.get("error") or {}
    if isinstance(error, dict):
        return str(error.get("category") or "no_error")
    if isinstance(error, str):
        return error
    return "no_error"


def is_infra_row(row: dict[str, Any]) -> bool:
    return row.get("correctness") == "wrong_format" and error_category(row) in INFRA_ERROR_CATEGORIES


def load_plan(base_run: Path, data_dir: Path) -> list[dict[str, Any]]:
    plan_path = base_run / "plan.tsv"
    entries: list[dict[str, Any]] = []
    annotation_cache: dict[str, list[dict[str, Any]]] = {}
    for line_no, line in enumerate(plan_path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            raise ValueError(f"{plan_path}:{line_no}: expected annotation and index")
        annotation = parts[0]
        index = int(parts[1])
        if annotation not in annotation_cache:
            ann_path = data_dir / "annotations" / annotation
            annotation_cache[annotation] = json.loads(ann_path.read_text())
        sample = annotation_cache[annotation][index]
        entries.append({
            "annotation": annotation,
            "index": index,
            "sample_id": sample["id"],
            "original_shard": int(parts[2]) if len(parts) > 2 and parts[2] else None,
        })
    return entries


def discover_overlays(runs_dir: Path, extra_runs: list[Path]) -> list[Path]:
    overlays = list(DEFAULT_LEGACY_OVERLAYS)
    for pattern in AUTORETRY_GLOBS:
        overlays.extend(sorted(runs_dir.glob(pattern)))
    overlays.extend(extra_runs)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in overlays:
        resolved = (REPO_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )


def empty_stats() -> dict[str, Any]:
    return {
        "expected": 0,
        "completed": 0,
        "correct": 0,
        "wrong": 0,
        "wrong_format": 0,
        "pending_retry": 0,
        "accuracy_completed": 0,
    }


def add_result(stats: dict[str, Any], row: dict[str, Any] | None, pending: bool) -> None:
    stats["expected"] += 1
    if row is not None:
        stats["completed"] += 1
        correctness = row.get("correctness")
        if correctness in ("correct", "wrong", "wrong_format"):
            stats[correctness] += 1
    if pending:
        stats["pending_retry"] += 1


def finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    completed = stats["completed"]
    stats["accuracy_completed"] = stats["correct"] / completed if completed else 0
    return stats


def build_breakdown(
    plan_entries: list[dict[str, Any]],
    latest: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    app_stats: dict[str, dict[str, Any]] = {
        annotation: {
            "annotation": annotation,
            "code": code,
            "name": name,
            **empty_stats(),
        }
        for _subset, apps in APP_GROUPS
        for annotation, code, name in apps
    }
    subset_stats: dict[str, dict[str, Any]] = {
        subset: {
            "subset": subset,
            **empty_stats(),
        }
        for subset, _apps in APP_GROUPS
    }
    unknown_apps: dict[str, dict[str, Any]] = {}

    for entry in plan_entries:
        annotation = entry["annotation"]
        row = latest.get(entry["sample_id"])
        pending = row is None or row.get("correctness") == "wrong_format"
        meta = APP_LOOKUP.get(annotation)
        if meta is None:
            meta = {"subset": "Other", "code": Path(annotation).stem, "name": Path(annotation).stem}
            app_stats_for_entry = unknown_apps.setdefault(annotation, {
                "annotation": annotation,
                "code": meta["code"],
                "name": meta["name"],
                **empty_stats(),
            })
            subset_stats.setdefault("Other", {"subset": "Other", **empty_stats()})
        else:
            app_stats_for_entry = app_stats[annotation]
        add_result(app_stats_for_entry, row, pending)
        add_result(subset_stats[meta["subset"]], row, pending)

    for stats in app_stats.values():
        finalize_stats(stats)
    for stats in unknown_apps.values():
        finalize_stats(stats)
    for stats in subset_stats.values():
        finalize_stats(stats)

    breakdown: list[dict[str, Any]] = []
    for subset, apps in APP_GROUPS:
        subset_entry = dict(subset_stats[subset])
        subset_entry["apps"] = [dict(app_stats[annotation]) for annotation, _code, _name in apps]
        breakdown.append(subset_entry)
    if "Other" in subset_stats:
        subset_entry = dict(subset_stats["Other"])
        subset_entry["apps"] = sorted((dict(stats) for stats in unknown_apps.values()), key=lambda s: s["code"])
        breakdown.append(subset_entry)
    return breakdown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-run", default=str(DEFAULT_BASE_RUN))
    parser.add_argument("--final-dir", default=str(DEFAULT_FINAL_DIR))
    parser.add_argument("--data-dir", default="benchmarks/screenspot_pro/data")
    parser.add_argument("--extra-run", action="append", default=[])
    args = parser.parse_args()

    base_run = (REPO_ROOT / args.base_run).resolve()
    final_dir = (REPO_ROOT / args.final_dir).resolve()
    data_dir = (REPO_ROOT / args.data_dir).resolve()
    runs_dir = REPO_ROOT / "runs/screenspot_pro"
    extra_runs = [Path(p) for p in args.extra_run]

    plan_entries = load_plan(base_run, data_dir)
    plan_by_id = {entry["sample_id"]: entry for entry in plan_entries}

    sources = [base_run, *discover_overlays(runs_dir, extra_runs)]
    latest: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = {}
    ignored_infra_rows = 0
    for source in sources:
        rows = read_result_rows(source)
        source_counts[str(source.relative_to(REPO_ROOT))] = len(rows)
        for row in rows:
            sample_id = row.get("sample_id")
            if not sample_id or sample_id not in plan_by_id:
                continue
            if is_infra_row(row):
                ignored_infra_rows += 1
                continue
            latest[sample_id] = row

    ordered_rows = [
        latest[entry["sample_id"]]
        for entry in plan_entries
        if entry["sample_id"] in latest
    ]
    final_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(final_dir / "results.jsonl", ordered_rows)

    pending_entries = [
        entry for entry in plan_entries
        if entry["sample_id"] not in latest
        or latest[entry["sample_id"]].get("correctness") == "wrong_format"
    ]
    pending_lines = [
        f"{entry['annotation']}\t{entry['index']}\t{entry['sample_id']}"
        for entry in pending_entries
    ]
    (final_dir / "pending_retry.tsv").write_text("\n".join(pending_lines) + ("\n" if pending_lines else ""))

    counts = Counter(row.get("correctness") for row in ordered_rows)
    wf_categories = Counter(error_category(row) for row in ordered_rows if row.get("correctness") == "wrong_format")
    summary = {
        "expected": len(plan_entries),
        "completed": len(ordered_rows),
        "correct": counts.get("correct", 0),
        "wrong": counts.get("wrong", 0),
        "wrong_format": counts.get("wrong_format", 0),
        "accuracy_completed": counts.get("correct", 0) / len(ordered_rows) if ordered_rows else 0,
        "pending_retry": len(pending_entries),
        "missing_or_infra": len(plan_entries) - len(ordered_rows),
        "ignored_infra_rows": ignored_infra_rows,
        "wrong_format_categories": dict(wf_categories),
        "sources": source_counts,
        "breakdown": build_breakdown(plan_entries, latest),
    }
    (final_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
