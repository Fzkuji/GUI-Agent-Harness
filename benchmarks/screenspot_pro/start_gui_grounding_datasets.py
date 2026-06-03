#!/usr/bin/env python3
"""Start GUI grounding dataset evaluation in a detached screen session."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PYTHON = os.environ.get("GUI_HARNESS_PYTHON", sys.executable)
DEFAULT_PROVIDER = "openai-codex"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_SCREEN = "gui_grounding_full"
DEFAULT_PROXY = "http://127.0.0.1:6152"

DATA_DIRS = {
    "ui_vision": Path("benchmarks/screenspot_pro/data_ui_vision"),
    "mmbench_gui_l2": Path("benchmarks/screenspot_pro/data_mmbench_gui_l2"),
}


def parse_datasets(value: str) -> list[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names or names == ["all"]:
        names = list(DATA_DIRS.keys())
    unknown = [name for name in names if name not in DATA_DIRS]
    if unknown:
        raise ValueError(f"unknown dataset(s): {', '.join(unknown)}")
    return names


def run_prepare_metadata(python: str, datasets: list[str]) -> None:
    env = dict(os.environ)
    env.setdefault("HTTPS_PROXY", DEFAULT_PROXY)
    env.setdefault("HTTP_PROXY", DEFAULT_PROXY)
    subprocess.run(
        [
            python,
            "benchmarks/screenspot_pro/prepare_gui_grounding_datasets.py",
            "--datasets",
            ",".join(datasets),
            "--metadata-only",
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )


def screen_exists(screen_name: str) -> bool:
    result = subprocess.run(["screen", "-ls"], cwd=REPO_ROOT, text=True, capture_output=True)
    return screen_name in result.stdout


def read_annotation(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def build_plan(out_dir: Path, datasets: list[str], shards: int) -> dict[str, Any]:
    per_shard: list[dict[tuple[str, str], list[int]]] = [defaultdict(list) for _ in range(shards)]
    lines: list[str] = []
    counts: dict[str, int] = {}
    for dataset in datasets:
        ann_dir = REPO_ROOT / DATA_DIRS[dataset] / "annotations"
        total = 0
        for ann_path in sorted(ann_dir.glob("*.json")):
            rows = read_annotation(ann_path)
            for index, sample in enumerate(rows):
                shard = len(lines) % shards
                per_shard[shard][(dataset, ann_path.name)].append(index)
                split = str(sample.get("split") or ann_path.stem)
                lines.append(f"{dataset}\t{ann_path.name}\t{index}\t{sample['id']}\t{split}\t{shard}")
                total += 1
        counts[dataset] = total
    (out_dir / "plan.tsv").write_text("\n".join(lines) + ("\n" if lines else ""))
    for shard, grouped in enumerate(per_shard):
        shard_lines = []
        for (dataset, annotation), indexes in sorted(grouped.items()):
            shard_lines.append(
                f"{dataset}\t{annotation}\t{','.join(str(i) for i in indexes)}\t{len(indexes)}"
            )
        (out_dir / f"shard_{shard}.plan").write_text(
            "\n".join(shard_lines) + ("\n" if shard_lines else "")
        )
    return {"counts": counts, "total": sum(counts.values())}


def shell_quote(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def iterative_env_lines() -> list[str]:
    return [
        "export GUI_HARNESS_SCREENSPOT_LOCATOR_MODE=iterative_zoom",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_ROUNDS=8",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_REVIEW_FINAL=1",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_VERIFY_FINAL=0",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_FALLBACK_TO_CROP=0",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_CROP_COMMIT_GATE=1",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_CROP_RETRIES=6",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGED_CROP=1",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGE1_MIN_AREA_PCT=20",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGE2_MIN_AREA_PCT=8",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_MAX_SIDE=2048",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_MAX_SCALE=5",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_MIN_SHORT_SIDE=512",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_MAX_SIDE=4096",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_MAX_SCALE=8",
        "export GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_MIN_SHORT_SIDE=640",
    ]


def build_screen_script(
    *,
    out_dir: Path,
    datasets: list[str],
    shards: int,
    python: str,
    provider: str,
    model: str,
    app_name: str,
    sample_timeout_s: int,
    exec_timeout_s: int,
    runtime_retries: int,
    retry_provider_errors: int,
    image_workers: int,
) -> str:
    lines = [
        "set -u",
        f"cd {shlex.quote(str(REPO_ROOT))}",
        "export PYTHONUNBUFFERED=1",
        f"export HTTPS_PROXY=${{HTTPS_PROXY:-{shlex.quote(DEFAULT_PROXY)}}}",
        f"export HTTP_PROXY=${{HTTP_PROXY:-{shlex.quote(DEFAULT_PROXY)}}}",
        "export https_proxy=\"$HTTPS_PROXY\"",
        "export http_proxy=\"$HTTP_PROXY\"",
        *iterative_env_lines(),
        "status=0",
        (
            shell_quote(
                [
                    python,
                    "benchmarks/screenspot_pro/prepare_gui_grounding_datasets.py",
                    "--datasets",
                    ",".join(datasets),
                    "--image-workers",
                    str(image_workers),
                ]
            )
            + f" 2>&1 | tee -a {shlex.quote(str(out_dir / 'prepare.log'))} || exit 1"
        ),
    ]
    for dataset in datasets:
        lines.extend(
            [
                f"mkdir -p {shlex.quote(str(out_dir / dataset / 'shards'))}",
                f"mkdir -p {shlex.quote(str(out_dir / dataset / 'logs'))}",
                f"mkdir -p {shlex.quote(str(out_dir / dataset / 'work'))}",
            ]
        )
    for shard in range(shards):
        lines.extend(
            [
                "(",
                f"  plan_file={shlex.quote(str(out_dir / f'shard_{shard}.plan'))}",
                "  while IFS=$'\\t' read -r dataset annotation indexes count; do",
                "    [ -z \"${dataset:-}\" ] && continue",
                "    case \"$dataset\" in",
                "      ui_vision) data_dir=\"benchmarks/screenspot_pro/data_ui_vision\" ;;",
                "      mmbench_gui_l2) data_dir=\"benchmarks/screenspot_pro/data_mmbench_gui_l2\" ;;",
                "      *) echo \"unknown dataset: $dataset\" >&2; exit 1 ;;",
                "    esac",
                f"    output={shlex.quote(str(out_dir))}/\"$dataset\"/shards/shard_{shard}.jsonl",
                f"    log={shlex.quote(str(out_dir))}/\"$dataset\"/logs/shard_{shard}.log",
                f"    work={shlex.quote(str(out_dir))}/\"$dataset\"/work/shard_{shard}/\"${{annotation%.json}}\"",
                (
                    f"    echo '[gui-grounding {shard}] dataset='\"$dataset\"' annotation='\"$annotation\"' count='\"$count\" "
                    "| tee -a \"$log\" >&2"
                ),
                (
                    f"    {shlex.quote(python)} benchmarks/screenspot_pro/run_screenspot_pro.py "
                    "--data-dir \"$data_dir\" "
                    "--annotation \"$annotation\" "
                    "--indexes \"$indexes\" "
                    "--output \"$output\" "
                    "--work-dir \"$work\" "
                    f"--app-name {shlex.quote(app_name)} "
                    f"--provider {shlex.quote(provider)} "
                    f"--model {shlex.quote(model)} "
                    f"--runtime-retries {runtime_retries} "
                    f"--retry-provider-errors {retry_provider_errors} "
                    f"--sample-timeout-s {sample_timeout_s} "
                    f"--exec-timeout-s {exec_timeout_s} "
                    "--download-timeout-s 60 "
                    "--download-retries 5 "
                    "--skip-existing "
                    "2>&1 | tee -a \"$log\" || exit 1"
                ),
                "  done < \"$plan_file\"",
                f") & pids_{shard}=$!",
            ]
        )
    lines.append("for pid in " + " ".join(f"$pids_{shard}" for shard in range(shards)) + "; do")
    lines.append("  wait \"$pid\" || status=1")
    lines.append("done")
    lines.append(
        shell_quote(
            [
                python,
                "benchmarks/screenspot_pro/report_gui_grounding_datasets.py",
                "--run-dir",
                str(out_dir),
            ]
        )
        + f" > {shlex.quote(str(out_dir / 'final_report.txt'))} || true"
    )
    lines.append("exit \"$status\"")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", default="ui_vision,mmbench_gui_l2")
    parser.add_argument("--screen-name", default=DEFAULT_SCREEN)
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--app-name", default="screenspot_pro")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--sample-timeout-s", type=int, default=1500)
    parser.add_argument("--exec-timeout-s", type=int, default=300)
    parser.add_argument("--runtime-retries", type=int, default=4)
    parser.add_argument("--retry-provider-errors", type=int, default=2)
    parser.add_argument("--image-workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    datasets = parse_datasets(args.datasets)
    if screen_exists(args.screen_name) and not args.force:
        print(json.dumps({"started": False, "reason": "already_running", "screen_name": args.screen_name}))
        return 0
    run_prepare_metadata(args.python, datasets)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    run_label = "gui_grounding_" + "_".join(datasets) + "_full"
    out_dir = REPO_ROOT / "runs/gui_grounding" / f"{run_label}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_summary = build_plan(out_dir, datasets, args.shards)
    script = build_screen_script(
        out_dir=out_dir,
        datasets=datasets,
        shards=args.shards,
        python=args.python,
        provider=args.provider,
        model=args.model,
        app_name=args.app_name,
        sample_timeout_s=args.sample_timeout_s,
        exec_timeout_s=args.exec_timeout_s,
        runtime_retries=args.runtime_retries,
        retry_provider_errors=args.retry_provider_errors,
        image_workers=args.image_workers,
    )
    (out_dir / "run.sh").write_text(script)
    subprocess.run(["screen", "-dmS", args.screen_name, "bash", "-lc", script], cwd=REPO_ROOT, check=True)
    print(
        json.dumps(
            {
                "started": True,
                "screen_name": args.screen_name,
                "run_dir": str(out_dir.relative_to(REPO_ROOT)),
                "datasets": datasets,
                "plan": plan_summary,
                "provider": args.provider,
                "model": args.model,
                "shards": args.shards,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
