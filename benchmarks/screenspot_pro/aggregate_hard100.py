#!/usr/bin/env python3
"""聚合 hard100（100 难题 = GPT-5.5 legacy 答错的题）的 best vs legacy 对比。

跑了 3 组：GPT×best、M3×best、M3×legacy。GPT×legacy 省略（这 100 题就是从它
答错的题里挑的，≈0）。

解读：
  - GPT×best 的 correct 数 = best 在 GPT 全错的难题上救回了多少（baseline=0）。
  - M3：best vs legacy 同批对比，看 best 在难题上比 legacy 强多少（救回/掉点）。
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / "results" / "hard100"
SAMPLES = [tuple(x) for x in json.load(open(HERE / "hard100_samples.json"))]
COMBOS = [("gpt-5_5", "best"), ("MiniMax-M3", "best"), ("MiniMax-M3", "legacy_baseline")]


def read_correct(tag: str, cfg: str, stem: str, idx: int) -> str:
    p = BASE / tag / cfg / f"{stem}_{idx}.jsonl"
    if not p.exists():
        return "MISSING"
    rows = [l for l in p.read_text().splitlines() if l.strip()]
    if not rows:
        return "EMPTY"
    try:
        return json.loads(rows[-1]).get("correctness", "?")
    except Exception:
        return "PARSE_ERR"


def stats(data: dict):
    c = sum(1 for v in data.values() if v == "correct")
    done = sum(1 for v in data.values() if v in ("correct", "wrong", "wrong_format"))
    return c, done


def main() -> None:
    res = {}
    for tag, cfg in COMBOS:
        d = {f"{s[:-5]}_{i}": read_correct(tag, cfg, s[:-5], i) for s, i in SAMPLES}
        res[(tag, cfg)] = d

    print(f"\n===== hard100（{len(SAMPLES)} 难题 = GPT-5.5 legacy 答错的题）=====\n")
    print(f"{'组':24s} {'acc':>10s}  说明")
    for tag, cfg in COMBOS:
        c, done = stats(res[(tag, cfg)])
        note = ""
        if tag == "gpt-5_5" and cfg == "best":
            note = "GPT best 救回（GPT legacy 在这些题=0）"
        elif cfg == "legacy_baseline":
            note = "M3 legacy 基线"
        elif tag == "MiniMax-M3":
            note = "M3 best"
        acc = f"{c}/{done}" if done else "0/0"
        print(f"{tag+' / '+cfg:24s} {acc:>10s}  {note}")

    # M3 best vs legacy 同批对比
    mb = res[("MiniMax-M3", "best")]
    ml = res[("MiniMax-M3", "legacy_baseline")]
    common = [k for k in mb if mb[k] in ("correct", "wrong", "wrong_format")
              and ml[k] in ("correct", "wrong", "wrong_format")]
    if common:
        bc = sum(1 for k in common if mb[k] == "correct")
        lc = sum(1 for k in common if ml[k] == "correct")
        rescued = sum(1 for k in common if ml[k] != "correct" and mb[k] == "correct")
        lost = sum(1 for k in common if ml[k] == "correct" and mb[k] != "correct")
        print(f"\n--- M3: best vs legacy（{len(common)} 个两组都完成的难题）---")
        print(f"  best   {bc}/{len(common)}")
        print(f"  legacy {lc}/{len(common)}")
        print(f"  Δ = {bc - lc:+d}   (best 救回 {rescued}, 掉点 {lost})")

    # GPT best 救回
    gb = res[("gpt-5_5", "best")]
    gc, gdone = stats(gb)
    if gdone:
        print(f"\n--- GPT-5.5: best 在难题上救回 {gc}/{gdone}（legacy 基线≈0）---")

    out = BASE / "hard100_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {"n_samples": len(SAMPLES),
               "groups": {f"{t}/{c}": dict(zip(["correct", "done"], stats(res[(t, c)]))) for t, c in COMBOS}}
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nsummary -> {out}")


if __name__ == "__main__":
    main()
