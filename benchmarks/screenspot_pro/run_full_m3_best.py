#!/usr/bin/env python3
"""best 配置 + MiniMax-M3 跑 ScreenSpot-Pro 全量 1581。

普通并行（4 并发），不用 agent。断点续跑（已完成的输出文件跳过）。
M3 单次慢，全量会跑很久；每完成 25 个打一次进度汇总。
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
RESBASE = HERE / "results" / "full_m3_best"
CFG = HERE / "configs" / "best.yaml"
SAMPLES = [tuple(x) for x in json.load(open(HERE / "full1581_samples.json"))]
PROVIDER, MODEL = "minimax-cn-coding-plan", "MiniMax-M3"
# 16 并发实测：带图重请求互相拖慢，68% 样本撞 1800s 看门狗超时 → 废样本。
# best 是 8 轮精跑、单样本本就慢（4 并发中位 ~553s）。降到 6：比 4 快又不超时。
CONCURRENCY = 6


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
    out = RESBASE / f"{stem}_{idx}.jsonl"
    work = RESBASE / "work" / f"{stem}_{idx}"
    label = f"{stem}_{idx}"
    if already_done(out):
        r = [json.loads(l) for l in out.read_text().splitlines() if l.strip()][-1]
        return (label, r.get("correctness"), "skip")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [PY, "benchmarks/screenspot_pro/run_screenspot_pro.py",
           "--annotation", ann, "--indexes", str(idx),
           "--output", str(out), "--work-dir", str(work),
           "--provider", PROVIDER, "--model", MODEL, "--config", str(CFG),
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
    correct = 0
    wrong = 0
    other = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = [ex.submit(run_one, a, i) for a, i in SAMPLES]
        for fut in as_completed(futs):
            label, corr, how = fut.result()
            done += 1
            if corr == "correct":
                correct += 1
            elif corr == "wrong":
                wrong += 1
            else:
                other += 1
            if done % 25 == 0 or done == len(SAMPLES):
                acc = correct / (correct + wrong) * 100 if (correct + wrong) else 0
                print(f"[{done}/{len(SAMPLES)}] correct={correct} wrong={wrong} "
                      f"other={other}  acc(non-other)={acc:.1f}%", flush=True)
    print(f"\n全量跑完: correct={correct} wrong={wrong} other={other}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
