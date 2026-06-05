#!/usr/bin/env python3
"""聚合全参数单变量扫描结果：base + 10 个单翻转 arm，在 GPT-5.5 与 M3 上，
算每个 arm 相对 base 的准确率增量、救回、掉点。

判读：
  翻转后 acc 显著上升 => 该字段 base 设置不是最优，翻转值更好（值得在大样本上采用）。
  翻转后 acc 显著下降 => base 设置有用（这个步骤/开关在起作用）。
  基本持平          => 该字段对结果无影响（可按成本取舍：能关就关省钱）。
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / "results" / "param_sweep"
SAMPLES = [tuple(x) for x in json.load(open(HERE / "sweep_samples_min.json"))]
ARMS = ["base", "no_crop_check", "no_final_recheck", "no_staged_crop",
        "no_final_cand_detect", "no_final_recrop", "reason_first",
        "coords_local", "crop_check_last", "dedup_05", "scale_target_px"]
ARM_LABEL = {
    "base": "base(quality_8r)", "no_crop_check": "−crop_check",
    "no_final_recheck": "−final_recheck", "no_staged_crop": "−staged_crop",
    "no_final_cand_detect": "−final_cand_det", "no_final_recrop": "−final_recrop",
    "reason_first": "+reason_first", "coords_local": "+coords_local",
    "crop_check_last": "check=last_only", "dedup_05": "+dedup0.5",
    "scale_target_px": "scale=target_px",
}
MODELS = ["MiniMax-M3"]


def read_correct(tag: str, arm: str, stem: str, idx: int) -> str:
    p = BASE / tag / arm / f"{stem}_{idx}.jsonl"
    if not p.exists():
        return "MISSING"
    rows = [l for l in p.read_text().splitlines() if l.strip()]
    if not rows:
        return "EMPTY"
    try:
        return json.loads(rows[-1]).get("correctness", "?")
    except Exception:
        return "PARSE_ERR"


def main() -> None:
    summary = {"samples": len(SAMPLES), "models": {}}
    for tag in MODELS:
        data = {}
        for arm in ARMS:
            data[arm] = {f"{s[:-5]}_{i}": read_correct(tag, arm, s[:-5], i)
                         for s, i in SAMPLES}
        base = data["base"]
        base_c = sum(1 for v in base.values() if v == "correct")
        done = sum(1 for v in base.values() if v in ("correct", "wrong", "wrong_format"))
        summary["models"][tag] = {"base_correct": base_c, "base_done": done, "arms": {}}

        print(f"\n========== {tag}  (base {base_c}/{done} done, n={len(SAMPLES)}) ==========")
        print(f"{'arm':18s} {'acc':>8s}  {'Δvs base':>8s}  {'救回':>4s} {'掉点':>4s}  {'判读':s}")
        for arm in ARMS:
            cur = data[arm]
            c = sum(1 for v in cur.values() if v == "correct")
            n = sum(1 for v in cur.values() if v in ("correct", "wrong", "wrong_format"))
            rescued = sum(1 for s in cur if base.get(s) != "correct" and cur[s] == "correct")
            lost = sum(1 for s in cur if base.get(s) == "correct" and cur[s] != "correct")
            delta = c - base_c
            verdict = "—" if arm == "base" else (
                "翻转更好→采用" if delta >= 3 else
                ("base有用→保留" if delta <= -3 else "无显著影响"))
            summary["models"][tag]["arms"][arm] = {
                "correct": c, "n": n, "delta": delta, "rescued": rescued, "lost": lost,
                "verdict": verdict}
            dstr = "—" if arm == "base" else f"{delta:+d}"
            print(f"{ARM_LABEL[arm]:18s} {c:>3d}/{n:<4d} {dstr:>8s}  "
                  f"{('—' if arm=='base' else rescued):>4} {('—' if arm=='base' else lost):>4}  {verdict}")

    out = BASE / "sweep_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nsummary -> {out}")


if __name__ == "__main__":
    main()
