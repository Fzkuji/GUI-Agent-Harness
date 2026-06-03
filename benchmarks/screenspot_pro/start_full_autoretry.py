#!/usr/bin/env python3
"""Start an automatic retry pass for the canonical ScreenSpot-Pro full result."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINAL_DIR = Path("runs/screenspot_pro/iter_zoom_recrop_full_final_20260602")
DEFAULT_SCREEN = "screenspot_full_final_autoretry"
DEFAULT_PYTHON = os.environ.get("GUI_HARNESS_PYTHON", sys.executable)
DEFAULT_PROVIDER = "openai-codex"
DEFAULT_MODEL = "gpt-5.5"


def run_sync(final_dir: Path, python: str) -> dict[str, Any]:
    subprocess.run(
        [python, "benchmarks/screenspot_pro/sync_full_final.py", "--final-dir", str(final_dir)],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    summary_path = REPO_ROOT / final_dir / "summary.json"
    return json.loads(summary_path.read_text())


def screen_exists(screen_name: str) -> bool:
    result = subprocess.run(["screen", "-ls"], cwd=REPO_ROOT, text=True, capture_output=True)
    return screen_name in result.stdout


def latest_auth_failure_is_fresh(runs_dir: Path, cooldown_minutes: int, provider: str) -> bool:
    cutoff = datetime.now() - timedelta(minutes=cooldown_minutes)
    logs = sorted(runs_dir.glob("iter_zoom_recrop_full_autoretry_*/logs/shard_*.log"))
    for log in reversed(logs[-20:]):
        if datetime.fromtimestamp(log.stat().st_mtime) < cutoff:
            continue
        text = log.read_text(errors="replace")[-12000:]
        if "token_revoked" in text or "provider_auth" in text or "invalidated oauth token" in text:
            return True
    return False


def read_pending(final_dir: Path) -> list[tuple[str, int, str]]:
    pending_path = REPO_ROOT / final_dir / "pending_retry.tsv"
    if not pending_path.exists():
        return []
    rows: list[tuple[str, int, str]] = []
    for line in pending_path.read_text().splitlines():
        if not line.strip():
            continue
        annotation, index, sample_id = line.split("\t")[:3]
        rows.append((annotation, int(index), sample_id))
    return rows


def build_plan(out_dir: Path, pending: list[tuple[str, int, str]], shards: int) -> None:
    per_shard: list[dict[str, list[int]]] = [defaultdict(list) for _ in range(shards)]
    lines: list[str] = []
    for global_i, (annotation, index, sample_id) in enumerate(pending):
        shard = global_i % shards
        per_shard[shard][annotation].append(index)
        lines.append(f"{annotation}\t{index}\t{sample_id}\t{shard}")
    (out_dir / "plan.tsv").write_text("\n".join(lines) + ("\n" if lines else ""))
    for shard, grouped in enumerate(per_shard):
        shard_lines = []
        for annotation in sorted(grouped):
            indexes = ",".join(str(index) for index in grouped[annotation])
            shard_lines.append(f"{annotation}\t{indexes}\t{len(grouped[annotation])}")
        (out_dir / f"shard_{shard}.plan").write_text(
            "\n".join(shard_lines) + ("\n" if shard_lines else "")
        )


def shell_quote(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def build_screen_script(
    *,
    out_dir: Path,
    final_dir: Path,
    shards: int,
    python: str,
    sample_timeout_s: int,
    exec_timeout_s: int,
    runtime_retries: int,
    retry_provider_errors: int,
    provider: str,
    model: str,
) -> str:
    lines = [
        "set -u",
        f"cd {shlex.quote(str(REPO_ROOT))}",
        "export PYTHONUNBUFFERED=1",
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
        "status=0",
    ]
    for shard in range(shards):
        work_prefix = shlex.quote(str(out_dir / "work" / f"shard_{shard}"))
        run_cmd = (
            f"    {shlex.quote(python)} benchmarks/screenspot_pro/run_screenspot_pro.py "
            "--annotation \"$annotation\" "
            "--indexes \"$indexes\" "
            "--output \"$output\" "
            f"--work-dir {work_prefix}/\"${{annotation%.json}}\" "
            f"--provider {shlex.quote(provider)} "
            f"--model {shlex.quote(model)} "
            f"--runtime-retries {runtime_retries} "
            f"--retry-provider-errors {retry_provider_errors} "
            f"--sample-timeout-s {sample_timeout_s} "
            f"--exec-timeout-s {exec_timeout_s} "
            "--download-timeout-s 60 "
            "--download-retries 5 "
            "2>&1 | tee -a \"$log\" || exit 1"
        )
        lines.extend([
            "(",
            f"  plan_file={shlex.quote(str(out_dir / f'shard_{shard}.plan'))}",
            f"  output={shlex.quote(str(out_dir / 'shards' / f'shard_{shard}.jsonl'))}",
            f"  log={shlex.quote(str(out_dir / 'logs' / f'shard_{shard}.log'))}",
            "  while IFS=$'\\t' read -r annotation indexes count; do",
            "    [ -z \"${annotation:-}\" ] && continue",
            f"    echo '[final-autoretry shard {shard}] annotation='\"$annotation\"' indexes='\"$indexes\" | tee -a \"$log\" >&2",
            run_cmd,
            "  done < \"$plan_file\"",
            f") & pids_{shard}=$!",
        ])
    lines.append("for pid in " + " ".join(f"$pids_{shard}" for shard in range(shards)) + "; do")
    lines.append("  wait \"$pid\" || status=1")
    lines.append("done")
    lines.append(
        shell_quote([python, "benchmarks/screenspot_pro/sync_full_final.py", "--final-dir", str(final_dir)])
    )
    lines.append("exit \"$status\"")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-dir", default=str(DEFAULT_FINAL_DIR))
    parser.add_argument("--screen-name", default=DEFAULT_SCREEN)
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--cooldown-minutes", type=int, default=30)
    parser.add_argument("--sample-timeout-s", type=int, default=1500)
    parser.add_argument("--exec-timeout-s", type=int, default=300)
    parser.add_argument("--runtime-retries", type=int, default=4)
    parser.add_argument("--retry-provider-errors", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    final_dir = Path(args.final_dir)
    summary = run_sync(final_dir, args.python)
    pending = read_pending(final_dir)
    payload: dict[str, Any] = {
        "started": False,
        "screen_name": args.screen_name,
        "summary": summary,
        "pending_count": len(pending),
    }
    if not pending:
        payload["reason"] = "no_pending_retry"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if screen_exists(args.screen_name):
        payload["reason"] = "already_running"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    runs_dir = REPO_ROOT / "runs/screenspot_pro"
    if not args.force and latest_auth_failure_is_fresh(runs_dir, args.cooldown_minutes, args.provider):
        payload["reason"] = "provider_auth_cooldown"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = runs_dir / f"iter_zoom_recrop_full_autoretry_{timestamp}"
    (out_dir / "shards").mkdir(parents=True, exist_ok=True)
    (out_dir / "work").mkdir(parents=True, exist_ok=True)
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    build_plan(out_dir, pending, args.shards)
    script = build_screen_script(
        out_dir=out_dir,
        final_dir=final_dir,
        shards=args.shards,
        python=args.python,
        sample_timeout_s=args.sample_timeout_s,
        exec_timeout_s=args.exec_timeout_s,
        runtime_retries=args.runtime_retries,
        retry_provider_errors=args.retry_provider_errors,
        provider=args.provider,
        model=args.model,
    )
    (out_dir / "run.sh").write_text(script)
    subprocess.run(["screen", "-dmS", args.screen_name, "bash", "-lc", script], cwd=REPO_ROOT, check=True)
    payload.update({
        "started": True,
        "run_dir": str(out_dir.relative_to(REPO_ROOT)),
        "plan": str((out_dir / "plan.tsv").relative_to(REPO_ROOT)),
        "provider": args.provider,
        "model": args.model,
    })
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
