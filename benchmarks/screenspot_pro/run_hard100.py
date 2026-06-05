#!/usr/bin/env python3
"""hard100 best-vs-legacy 对比的普通并行 runner（不用 agent / workflow）。

每个样本就是一条 run_screenspot_pro.py 子进程。GPT 和 M3 是两个独立 provider，
各开一个 4 并发的线程池，两池同时跑（共 ~8 并发）。已完成的输出文件跳过（断点续跑）。

跑 3 组：GPT×best、M3×best、M3×legacy（GPT×legacy 省略，≈0）。
"""
from __future__ import annotations
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PY = sys.executable
RESBASE = HERE / "results" / "hard100"
CFGBASE = HERE / "configs"
SAMPLES = [tuple(x) for x in json.load(open(HERE / "hard100_samples.json"))]

PER_PROVIDER_CONCURRENCY = 4

# (tag, provider, model, cfg)
COMBOS = [
    ("gpt-5_5", "openai-codex", "gpt-5.5", "best"),
    ("MiniMax-M3", "minimax-cn-coding-plan", "MiniMax-M3", "best"),
    ("MiniMax-M3", "minimax-cn-coding-plan", "MiniMax-M3", "legacy_baseline"),
]


def already_done(out_path: Path) -> bool:
    if not out_path.exists():
        return False
    rows = [l for l in out_path.read_text().splitlines() if l.strip()]
    if not rows:
        return False
    try:
        return json.loads(rows[-1]).get("correctness") in ("correct", "wrong", "wrong_format")
    except Exception:
        return False


def run_one(tag: str, provider: str, model: str, cfg: str, ann: str, idx: int) -> tuple:
    stem = ann[:-5] if ann.endswith(".json") else ann
    out_path = RESBASE / tag / cfg / f"{stem}_{idx}.jsonl"
    work_dir = RESBASE / tag / cfg / "work" / f"{stem}_{idx}"
    label = f"{tag}/{cfg}/{stem}_{idx}"
    if already_done(out_path):
        try:
            r = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()][-1]
            return (label, r.get("correctness"), "skip")
        except Exception:
            pass
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        PY, "benchmarks/screenspot_pro/run_screenspot_pro.py",
        "--annotation", ann, "--indexes", str(idx),
        "--output", str(out_path), "--work-dir", str(work_dir),
        "--provider", provider, "--model", model,
        "--config", str(CFGBASE / f"{cfg}.yaml"),
        "--runtime-retries", "4", "--retry-provider-errors", "2",
        "--sample-timeout-s", "1800", "--exec-timeout-s", "600",
        "--download-timeout-s", "60", "--download-retries", "5",
    ]
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
    if not out_path.exists():
        return (label, f"NO_OUTPUT(exit={proc.returncode})", "err")
    try:
        r = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()][-1]
        return (label, r.get("correctness"), "ran")
    except Exception as e:
        return (label, f"PARSE_ERR({e})", "err")


def run_provider_pool(combos_for_provider: list) -> None:
    """一个 provider 内：所有 (cfg, sample) 任务，PER_PROVIDER_CONCURRENCY 并发。"""
    tasks = []
    for (tag, provider, model, cfg) in combos_for_provider:
        for ann, idx in SAMPLES:
            tasks.append((tag, provider, model, cfg, ann, idx))
    done = 0
    with ThreadPoolExecutor(max_workers=PER_PROVIDER_CONCURRENCY) as ex:
        futs = [ex.submit(run_one, *t) for t in tasks]
        for fut in as_completed(futs):
            label, corr, how = fut.result()
            done += 1
            print(f"  [{done}/{len(tasks)}] {label}: {corr} ({how})", flush=True)


def main() -> int:
    # 按 provider 分组，每个 provider 一个独立线程池，两个 provider 的池并行启动。
    by_provider: dict[str, list] = {}
    for c in COMBOS:
        by_provider.setdefault(c[1], []).append(c)

    # 顶层用一个池，每个 provider 一个 worker，各自内部再开 PER_PROVIDER_CONCURRENCY 并发。
    with ThreadPoolExecutor(max_workers=len(by_provider)) as top:
        futs = {top.submit(run_provider_pool, combos): prov
                for prov, combos in by_provider.items()}
        for fut in as_completed(futs):
            prov = futs[fut]
            fut.result()
            print(f"=== provider {prov} 全部完成 ===", flush=True)
    print("\n全部跑完。用 aggregate_hard100.py 出对比表。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
