#!/usr/bin/env python3
"""跑完后收尾:统计 UI-Vision 全量 + SSPro-M3 全量的最终成绩,生成 markdown 报告片段,
写入 results 目录,并把 benchmarks/ui_vision/README.md 的"全量重跑"段更新为真·全量数字。

仅做统计与文档生成,不 commit/push(由调用方决定)。
用 --check 只打印不写文件。
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
OLD_SP = {"basic": 73.1, "functional": 67.0, "spatial": 66.0}


def load(glob_pat):
    rows = {}
    for p in glob.glob(str(REPO / glob_pat)):
        for l in open(p, encoding="utf-8"):
            if not l.strip():
                continue
            try:
                r = json.loads(l)
                rows[r["sample_id"]] = r
            except Exception:
                continue
    return rows


def uiv_stats():
    old = {}
    f = HERE.parent / "ui_vision" / "results" / "gpt-5.5" / "results.jsonl"
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        old[r["sample_id"]] = r
    rows = load("runs/ui_vision_full/*_s*.jsonl")
    by = collections.defaultdict(lambda: [0, 0, 0, 0])  # ok,n,err,old_ok
    for k, r in rows.items():
        sp = k.split("_")[2]
        by[sp][1] += 1
        by[sp][0] += r.get("correctness") == "correct"
        by[sp][2] += 1 if r.get("error") else 0
        by[sp][3] += 1 if old.get(k, {}).get("correctness") == "correct" else 0
    return by, rows


def m3_stats():
    rows = load("runs/sspro_stack/m3_zoom/*.jsonl")
    ok = sum(r.get("correctness") == "correct" for r in rows.values())
    err = sum(1 for r in rows.values() if r.get("error"))
    return ok, len(rows), err, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    by, uiv_rows = uiv_stats()
    uiv_total = sum(v[1] for v in by.values())
    uiv_ok = sum(v[0] for v in by.values())
    uiv_oldok = sum(v[3] for v in by.values())
    uiv_done = uiv_total >= 5479

    mok, mn, merr, _ = m3_stats()
    m3_done = mn >= 1581

    lines = []
    lines.append("# UI-Vision 全量重跑结果(GPT-5.5 × iterative-zoom best)\n")
    lines.append(f"状态:{'完成' if uiv_done else f'进行中 {uiv_total}/5479'}  错误行:{sum(v[2] for v in by.values())}\n")
    lines.append("| Split | 样本 | 新方法 | 旧全量(单次) | 同题旧成绩 | Δ(同题) |")
    lines.append("|---|---|---|---|---|---|")
    for sp in ("basic", "functional", "spatial"):
        ok, n, err, ook = by[sp]
        if not n:
            continue
        lines.append(f"| {sp} | {n} | **{ok/n:.1%}** | {OLD_SP[sp]}% | {ook/n:.1%} | +{(ok-ook)/n*100:.1f} |")
    if uiv_total:
        lines.append(f"| **总计** | **{uiv_total}** | **{uiv_ok/uiv_total:.1%}** | 68.64% | {uiv_oldok/uiv_total:.1%} | +{(uiv_ok-uiv_oldok)/uiv_total*100:.1f} |")
    lines.append("")
    lines.append("# SSPro 全量 × MiniMax-M3(首次,无历史基线)\n")
    lines.append(f"状态:{'完成' if m3_done else f'进行中 {mn}/1581'}  ")
    lines.append(f"成绩:**{mok}/{mn} = {mok/max(1,mn):.1%}**  错误行:{merr}\n")
    report = "\n".join(lines)

    print(report)
    print(f"\n[uiv_done={uiv_done} m3_done={m3_done}]")
    if args.check:
        return 0

    out = HERE / "results" / "FULL_RERUN_RESULTS.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
