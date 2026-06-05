#!/usr/bin/env python3
"""聚合单变量消融结果：把 OFF / abl_reason / abl_sort / abl_dedup / abl_coords / ON
六个 arm 在 GPT-5.5 与 M3 上的逐样本对错读出来，算每个开关相对 OFF 的增量。"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent / "results" / "ablation_reason_cand"

# (annotation_stem, index, GPT-5.5 之前的对错)
SAMPLES = [
    ("android_studio_macos", 5, "wrong"), ("autocad_windows", 4, "wrong"),
    ("blender_windows", 10, "wrong"), ("davinci_macos", 6, "wrong"),
    ("eviews_windows", 7, "wrong"), ("excel_macos", 19, "wrong"),
    ("fruitloops_windows", 0, "wrong"), ("illustrator_windows", 4, "wrong"),
    ("inventor_windows", 1, "wrong"), ("linux_common_linux", 32, "wrong"),
    ("android_studio_macos", 0, "correct"), ("autocad_windows", 0, "correct"),
    ("blender_windows", 0, "correct"), ("davinci_macos", 0, "correct"),
    ("eviews_windows", 0, "correct"), ("excel_macos", 0, "correct"),
    ("fruitloops_windows", 1, "correct"), ("illustrator_windows", 0, "correct"),
    ("inventor_windows", 0, "correct"), ("linux_common_linux", 0, "correct"),
]
ARMS = ["off", "abl_reason", "abl_sort", "abl_dedup", "abl_coords",
        "abl_accum_text", "abl_accum_img", "on"]
ARM_LABEL = {
    "off": "OFF 基线", "abl_reason": "+reason", "abl_sort": "+sort",
    "abl_dedup": "+dedup", "abl_coords": "+coords",
    "abl_accum_text": "sort+累积文", "abl_accum_img": "sort+累积图",
    "on": "ON 全开",
}
MODELS = ["gpt-5_5", "MiniMax-M3"]


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
    summary: dict = {"samples": len(SAMPLES), "models": {}}
    for tag in MODELS:
        # arm -> {sample: correctness}
        data: dict[str, dict[str, str]] = {}
        for arm in ARMS:
            data[arm] = {}
            for stem, idx, _ in SAMPLES:
                data[arm][f"{stem}_{idx}"] = read_correct(tag, arm, stem, idx)

        off = data["off"]
        off_c = sum(1 for s in off.values() if s == "correct")
        summary["models"][tag] = {"off_correct": off_c, "arms": {}}

        print(f"\n========== {tag} ==========")
        # 各 arm 准确率 + 相对 OFF 增量 + 救回/掉点
        print(f"{'arm':12s} {'acc':>7s}  {'Δvs OFF':>8s}  {'救回':>4s} {'掉点':>4s}")
        for arm in ARMS:
            cur = data[arm]
            n_correct = sum(1 for s in cur.values() if s == "correct")
            n = len(cur)
            rescued = sum(1 for s in cur if off.get(s) != "correct" and cur[s] == "correct")
            lost = sum(1 for s in cur if off.get(s) == "correct" and cur[s] != "correct")
            delta = n_correct - off_c
            summary["models"][tag]["arms"][arm] = {
                "correct": n_correct, "n": n, "delta": delta,
                "rescued": rescued, "lost": lost,
            }
            dstr = "—" if arm == "off" else f"{delta:+d}"
            rstr = "—" if arm == "off" else str(rescued)
            lstr = "—" if arm == "off" else str(lost)
            print(f"{ARM_LABEL[arm]:12s} {n_correct:>3d}/{n:<3d}  {dstr:>8s}  {rstr:>4s} {lstr:>4s}")

        # 逐样本矩阵：哪些样本被哪个开关救回
        print(f"\n  逐样本（C=correct, w=wrong, f=wrong_format）：")
        hdr = f"  {'sample':24s}"
        for arm in ARMS:
            hdr += f"{arm.replace('abl_',''):>8s}"
        print(hdr)
        for stem, idx, prior in SAMPLES:
            s = f"{stem}_{idx}"
            line = f"  {s:24s}"
            for arm in ARMS:
                v = data[arm][s]
                mark = {"correct": "C", "wrong": "w", "wrong_format": "f"}.get(v, "?")
                line += f"{mark:>8s}"
            print(line)

        # 累积 arm 相对 abl_sort（而非 OFF）的净效果：累积是叠在 sort 之上的，
        # 真正想知道的是"在 sort 基础上再加累积"是涨是跌。
        sort = data.get("abl_sort", {})
        sort_c = sum(1 for v in sort.values() if v == "correct")
        accum_vs_sort: dict = {}
        if sort:
            print(f"\n  累积 vs abl_sort 基线（sort={sort_c}/{len(sort)}）：")
            for arm in ("abl_accum_text", "abl_accum_img"):
                cur = data.get(arm, {})
                if not cur:
                    continue
                c = sum(1 for v in cur.values() if v == "correct")
                resc = sum(1 for s in cur if sort.get(s) != "correct" and cur[s] == "correct")
                lst = sum(1 for s in cur if sort.get(s) == "correct" and cur[s] != "correct")
                accum_vs_sort[arm] = {"correct": c, "delta_vs_sort": c - sort_c,
                                      "rescued": resc, "lost": lst}
                print(f"    {ARM_LABEL[arm]:12s} {c:>3d}/{len(cur):<3d}  "
                      f"Δvs sort {c - sort_c:+d}  (救回 {resc}, 掉点 {lst})")
            summary["models"][tag]["accum_vs_sort"] = accum_vs_sort

    out = BASE / "ablation_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nsummary -> {out}")


if __name__ == "__main__":
    main()
