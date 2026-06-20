#!/usr/bin/env python3
"""SSPro 全量 1581 × MiniMax-M3,串行(一次一题),输出沿用 runs/sspro_stack/m3_zoom/
(skip-existing 自动复用切片已跑的行)。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PY = sys.executable

# 凭证注入
cred = Path.home() / ".openprogram" / "auth" / "minimax-cn-coding-plan" / "default.json"
if cred.exists():
    d = json.loads(cred.read_text(encoding="utf-8"))
    os.environ.setdefault("MINIMAX_CN_API_KEY", d["credentials"][0]["payload"]["api_key"])

samples = json.loads((HERE / "full1581_samples.json").read_text(encoding="utf-8"))
annotations = sorted({ann for ann, _ in samples})
print(f"SSPro full x M3: {len(annotations)} annotations, {len(samples)} samples", flush=True)

tot_ok = tot_n = 0
for ann in annotations:
    stem = ann[:-5]
    out = REPO / "runs/sspro_stack/m3_zoom" / f"{stem}.jsonl"
    work = REPO / "runs/sspro_stack/m3_zoom/work" / stem
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(HERE / "run_screenspot_pro.py"),
           "--annotation", ann, "--indexes", "all",
           "--output", str(out), "--work-dir", str(work),
           "--provider", "minimax-cn-coding-plan", "--model", "MiniMax-M3",
           "--app-name", "screenspot_pro",
           "--config", str(HERE / "configs" / "sspro_stack_zoom.yaml"),
           "--runtime-retries", "4", "--retry-provider-errors", "2",
           "--exec-timeout-s", "300",
           "--download-timeout-s", "120", "--download-retries", "5",
           "--skip-existing"]
    subprocess.run(cmd, cwd=REPO, text=True, encoding="utf-8", errors="replace",
                   capture_output=True)
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
    tot_ok += ok
    tot_n += n
    print(f"  {stem}: {ok}/{n}  (total {tot_ok}/{tot_n})", flush=True)
print(f"\nM3 SSPro FULL DONE: {tot_ok}/{tot_n} = {tot_ok/max(1,tot_n):.1%}", flush=True)
