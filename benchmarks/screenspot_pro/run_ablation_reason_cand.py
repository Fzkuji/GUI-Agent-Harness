#!/usr/bin/env python3
"""消融实验驱动：在固定的 10 错 + 10 对样本集上，对比

  - ablation_off.yaml （旧行为：reasoning_first=off, sort=none, dedup=0, crop_local=off）
  - ablation_on.yaml  （新行为：reasoning_first=on,  sort=relevance, dedup=0.5, crop_local=on）

对照集来自 GPT-5.5 自己之前的逐样本结果（results.jsonl）：10 个它之前答错的
+ 10 个它之前答对的，验证新优化能否救回错的、且不让对的掉点。

用 --provider/--model 切换模型，可分别在 GPT-5.5 和 M3 上跑：
  python3 -u benchmarks/screenspot_pro/run_ablation_reason_cand.py --provider openai-codex --model gpt-5.5
  python3 -u benchmarks/screenspot_pro/run_ablation_reason_cand.py --provider minimax-cn-coding-plan --model MiniMax-M3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "benchmarks" / "screenspot_pro" / "configs"
OUT_BASE = REPO_ROOT / "benchmarks" / "screenspot_pro" / "results" / "ablation_reason_cand"

# (annotation_file, index, GPT-5.5 之前的对错)
SAMPLES = [
    # GPT-5.5 之前答错的（看新策略能否救回）
    ("android_studio_macos.json", 5, "wrong"),
    ("autocad_windows.json", 4, "wrong"),
    ("blender_windows.json", 10, "wrong"),
    ("davinci_macos.json", 6, "wrong"),
    ("eviews_windows.json", 7, "wrong"),
    ("excel_macos.json", 19, "wrong"),
    ("fruitloops_windows.json", 0, "wrong"),
    ("illustrator_windows.json", 4, "wrong"),
    ("inventor_windows.json", 1, "wrong"),
    ("linux_common_linux.json", 32, "wrong"),
    # GPT-5.5 之前答对的（验证不掉点）
    ("android_studio_macos.json", 0, "correct"),
    ("autocad_windows.json", 0, "correct"),
    ("blender_windows.json", 0, "correct"),
    ("davinci_macos.json", 0, "correct"),
    ("eviews_windows.json", 0, "correct"),
    ("excel_macos.json", 0, "correct"),
    ("fruitloops_windows.json", 1, "correct"),
    ("illustrator_windows.json", 0, "correct"),
    ("inventor_windows.json", 0, "correct"),
    ("linux_common_linux.json", 0, "correct"),
]

ARMS = [
    ("off", CONFIG_DIR / "ablation_off.yaml"),
    ("on", CONFIG_DIR / "ablation_on.yaml"),
]


def run_one(out_dir: Path, arm: str, config: Path, annotation: str, index: int,
            provider: str, model: str) -> dict | None:
    stem = annotation[:-5] if annotation.endswith(".json") else annotation
    out_path = out_dir / arm / f"{stem}_{index}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / arm / "work" / f"{stem}_{index}"
    cmd = [
        sys.executable,
        "benchmarks/screenspot_pro/run_screenspot_pro.py",
        "--annotation", annotation,
        "--indexes", str(index),
        "--output", str(out_path),
        "--work-dir", str(work_dir),
        "--provider", provider,
        "--model", model,
        "--config", str(config),
        "--runtime-retries", "4",
        "--retry-provider-errors", "2",
        "--sample-timeout-s", "1800",
        "--exec-timeout-s", "600",
        "--download-timeout-s", "60",
        "--download-retries", "5",
    ]
    print(f"[{arm}] {stem}_{index} ...", flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        print(f"  ! exit {proc.returncode}\n{proc.stderr[-1500:]}", flush=True)
    if not out_path.exists():
        print("  ! no output", flush=True)
        return None
    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    if not rows:
        return None
    r = rows[-1]
    res = {
        "arm": arm,
        "annotation": stem,
        "index": index,
        "correctness": r.get("correctness"),
        "ui_type": r.get("ui_type"),
        "instruction": r.get("instruction", "")[:60],
        "elapsed_s": r.get("elapsed_s"),
        "error": r.get("error"),
    }
    print(f"  -> {res['correctness']}  ({res['elapsed_s']}s)", flush=True)
    return res


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="openai-codex")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--tag", default="", help="输出子目录后缀，默认用 model 名")
    args = parser.parse_args()

    tag = args.tag or args.model.replace("/", "_").replace(".", "_")
    out_dir = OUT_BASE / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for arm, config in ARMS:
        for annotation, index, _prior in SAMPLES:
            r = run_one(out_dir, arm, config, annotation, index, args.provider, args.model)
            if r:
                results.append(r)

    by_key: dict[tuple[str, int], dict[str, str]] = {}
    for r in results:
        key = (r["annotation"], r["index"])
        by_key.setdefault(key, {})[r["arm"]] = r["correctness"]

    table = []
    for (a_full, i, prior) in SAMPLES:
        a = a_full[:-5] if a_full.endswith(".json") else a_full
        row = by_key.get((a, i), {})
        table.append({
            "sample": f"{a}_{i}",
            "ui": next((r["ui_type"] for r in results if r["annotation"] == a and r["index"] == i), "?"),
            "prior_gpt": prior,
            "off": row.get("off", "MISSING"),
            "on": row.get("on", "MISSING"),
        })

    payload = {"provider": args.provider, "model": args.model, "results": results, "table": table}
    (out_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    print(f"\n=== ABLATION RESULT  ({args.model}) ===")
    print(f"{'sample':28s} {'ui':5s} {'priorGPT':9s} {'OFF':9s} {'ON':9s}")
    off_c = on_c = 0
    rescued = lost = 0
    for t in table:
        print(f"{t['sample']:28s} {t['ui']:5s} {t['prior_gpt']:9s} {t['off']:9s} {t['on']:9s}")
        if t["off"] == "correct":
            off_c += 1
        if t["on"] == "correct":
            on_c += 1
        if t["off"] != "correct" and t["on"] == "correct":
            rescued += 1
        if t["off"] == "correct" and t["on"] != "correct":
            lost += 1
    n = len(table)
    print(f"\nOFF: {off_c}/{n}   ON: {on_c}/{n}   delta: {on_c - off_c:+d}   (救回 {rescued}, 掉点 {lost})")
    print(f"summary -> {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
