#!/usr/bin/env python3
"""easy100：验证 best 配置会不会把 GPT-5.5 legacy 原本答对的题搞坏（掉点）。

100 个样本 = GPT-5.5 在 legacy 下答对的题（分层）。legacy 在这些题上=100% 对（基线，
不重跑）。这里只跑 GPT×best，看还剩多少对。普通并行（4 并发），不用 agent。
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
RESBASE = HERE / "results" / "easy100"
CFGBASE = HERE / "configs"
SAMPLES = [tuple(x) for x in json.load(open(HERE / "easy100_samples.json"))]
CONCURRENCY = 4
TAG, PROVIDER, MODEL, CFG = "gpt-5_5", "openai-codex", "gpt-5.5", "best"


def already_done(p: Path) -> bool:
    if not p.exists():
        return False
    rows = [l for l in p.read_text().splitlines() if l.strip()]
    if not rows:
        return False
    try:
        return json.loads(rows[-1]).get("correctness") in ("correct", "wrong", "wrong_format")
    except Exception:
        return False


def run_one(ann: str, idx: int) -> tuple:
    stem = ann[:-5] if ann.endswith(".json") else ann
    out = RESBASE / TAG / CFG / f"{stem}_{idx}.jsonl"
    work = RESBASE / TAG / CFG / "work" / f"{stem}_{idx}"
    label = f"{stem}_{idx}"
    if already_done(out):
        r = [json.loads(l) for l in out.read_text().splitlines() if l.strip()][-1]
        return (label, r.get("correctness"), "skip")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [PY, "benchmarks/screenspot_pro/run_screenspot_pro.py",
           "--annotation", ann, "--indexes", str(idx),
           "--output", str(out), "--work-dir", str(work),
           "--provider", PROVIDER, "--model", MODEL,
           "--config", str(CFGBASE / f"{CFG}.yaml"),
           "--runtime-retries", "4", "--retry-provider-errors", "2",
           "--sample-timeout-s", "1800", "--exec-timeout-s", "600",
           "--download-timeout-s", "60", "--download-retries", "5"]
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
    if not out.exists():
        return (label, f"NO_OUTPUT(exit={proc.returncode})", "err")
    try:
        r = [json.loads(l) for l in out.read_text().splitlines() if l.strip()][-1]
        return (label, r.get("correctness"), "ran")
    except Exception as e:
        return (label, f"PARSE_ERR({e})", "err")


def main() -> int:
    done = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = [ex.submit(run_one, a, i) for a, i in SAMPLES]
        for fut in as_completed(futs):
            label, corr, how = fut.result()
            done += 1
            print(f"  [{done}/{len(SAMPLES)}] {label}: {corr} ({how})", flush=True)
    print("\neasy100 跑完。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
