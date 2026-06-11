#!/usr/bin/env python3
"""easy100 回归(legacy_baseline 配置):验证今天的代码改动没有破坏 SSPro 旧路径。

与 run_easy100.py 的区别:
  - 配置用 legacy_baseline.yaml(旧 87.9% 全量同款)。这 100 题是 GPT×legacy
    答对的题,基线=100% 对;在新代码上重跑,同行翻错数 ≈ 代码回归 + 模型抖动。
  - 按 annotation 分组、批量 --indexes,一个进程跑完一个文件(省冷启动)。
  - 并发 2(与 UI-Vision zoom 臂共享 GPU/配额,保守)。
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PY = sys.executable
RESBASE = HERE / "results" / "easy100" / "gpt-5_5" / "legacy_regression"
CONCURRENCY = 2
PROVIDER, MODEL = "openai-codex", "gpt-5.5"
CFG = HERE / "configs" / "legacy_baseline.yaml"

SAMPLES = [tuple(x) for x in json.load(open(HERE / "easy100_samples.json", encoding="utf-8"))]


def run_annotation(ann: str, indexes: list[int]) -> tuple[str, int, int]:
    stem = ann[:-5] if ann.endswith(".json") else ann
    out = RESBASE / f"{stem}.jsonl"
    work = RESBASE / "work" / stem
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(HERE / "run_screenspot_pro.py"),
           "--annotation", ann,
           "--indexes", ",".join(str(i) for i in sorted(indexes)),
           "--output", str(out), "--work-dir", str(work),
           "--provider", PROVIDER, "--model", MODEL,
           "--config", str(CFG),
           "--runtime-retries", "4", "--retry-provider-errors", "2",
           "--exec-timeout-s", "600",
           "--download-timeout-s", "60", "--download-retries", "5",
           "--skip-existing"]
    subprocess.run(cmd, cwd=REPO, text=True, encoding="utf-8", errors="replace", capture_output=True)
    ok = n = 0
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            n += 1
            ok += r.get("correctness") == "correct"
    return (stem, ok, n)


def main() -> int:
    groups: dict[str, list[int]] = defaultdict(list)
    for ann, idx in SAMPLES:
        groups[ann].append(idx)
    print(f"easy100 legacy regression: {len(SAMPLES)} samples in {len(groups)} annotations", flush=True)
    tot_ok = tot_n = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = [ex.submit(run_annotation, a, idxs) for a, idxs in groups.items()]
        for fut in as_completed(futs):
            stem, ok, n = fut.result()
            tot_ok += ok
            tot_n += n
            print(f"  {stem}: {ok}/{n}  (running total {tot_ok}/{tot_n})", flush=True)
    acc = tot_ok / tot_n if tot_n else 0.0
    print(f"\neasy100 legacy regression: {tot_ok}/{tot_n} = {acc:.1%} (基线=100%,差值≈回归+抖动)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
