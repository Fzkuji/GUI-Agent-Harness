#!/usr/bin/env python3
"""设计级消融汇总(GPT-5.5, SSPro-300 分层切片)。

五臂:full / no_prime / no_adaptive / no_verify / single,数据在
runs/sspro_stack/<arm>/*.jsonl。输出 markdown 表:准确率、Δ vs full、
中位耗时、中位 zoom 轮数、correctness 构成。

跑法:python benchmarks/screenspot_pro/reporting/report_design_ablation.py
"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]

ARMS = [
    # (显示名, runs/sspro_stack 子目录, 说明)
    ("full",        "zoom",            "①②③全开 = sspro_stack_zoom.yaml"),
    ("no_prime",    "abl_no_prime",    "去①坐标注入(no candidates / crop-local coords)"),
    ("no_adaptive", "abl_no_adaptive", "去②自适应裁剪(1轮、无retry/recrop)"),
    ("no_verify",   "abl_no_verify",   "去③视觉验证(无crop_check/final_recheck)"),
    ("single",      "single",          "single-locate 参考臂(全图+候选,单次定位)"),
]


def load(subdir: str) -> list[dict]:
    rows: list[dict] = []
    for f in sorted((REPO / "runs" / "sspro_stack" / subdir).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> int:
    stats = {}
    for name, sub, _ in ARMS:
        rows = load(sub)
        c = Counter(r["correctness"] for r in rows)
        el = [r["elapsed_s"] for r in rows if isinstance(r.get("elapsed_s"), (int, float))]
        rounds = []
        for r in rows:
            iz = (r.get("location") or {}).get("iterative_zoom") or {}
            if isinstance(iz.get("rounds"), int):
                rounds.append(iz["rounds"])
        n = len(rows)
        stats[name] = {
            "n": n,
            "correct": c["correct"],
            "acc": c["correct"] / n if n else 0.0,
            "breakdown": dict(c),
            "med_elapsed": st.median(el) if el else 0.0,
            "med_rounds": st.median(rounds) if rounds else None,
        }

    full_acc = stats["full"]["acc"]
    print("| Arm | Accuracy | Δ vs full | median s/sample | median zoom rounds |")
    print("|-----|----------|-----------|-----------------|--------------------|")
    for name, _, desc in ARMS:
        s = stats[name]
        delta = "" if name == "full" else f"{(s['acc'] - full_acc) * 100:+.1f}pt"
        mr = s["med_rounds"] if s["med_rounds"] is not None else "—"
        print(f"| {name} ({desc}) | **{s['acc']:.1%}** ({s['correct']}/{s['n']}) "
              f"| {delta or '—'} | {s['med_elapsed']:.0f}s | {mr} |")
    print()
    for name, _, _ in ARMS:
        print(f"  {name}: breakdown={stats[name]['breakdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
