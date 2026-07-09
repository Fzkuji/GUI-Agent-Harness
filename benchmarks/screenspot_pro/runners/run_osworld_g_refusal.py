#!/usr/bin/env python3
"""拒绝层评测(附加,不改既有策略)。

流程:
  1) 复用 runs/osworld_g/results.jsonl 里已有的点击预测(既有迭代缩放策略,原封不动)。
  2) 对全部 564 题各跑一次可行性判别器,结果缓存到 runs/osworld_g/refusal_judge.jsonl
     (skip-existing 续跑)。判别器对所有题一视同仁,不看 box_type 标签。
  3) 组合判分并扫阈值:p_infeasible >= 阈值 → 改判"拒绝";否则沿用原点击。
     - refusal 题:拒绝=对,点击=错
     - 可定位题(bbox/polygon):放行且原点击正确=对;被误拒=错(损失)
  4) 报告每个阈值下:拒绝召回 R/54、误拒 F/510、全量正确率、可定位子集正确率,
     对比无拒绝层基线(全量 82.1% / 可定位 90.8%)。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

DATA = HERE / "data_osworld_g"
RESULTS = REPO / "runs/osworld_g/results.jsonl"
JUDGE_OUT = REPO / "runs/osworld_g/refusal_judge.jsonl"
THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]


def pip(pt, poly):
    if not poly or not pt:
        return None
    x, y = pt
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def click_correct(r):
    bt = r.get("osworld_box_type") or "bbox"
    if bt == "refusal":
        return False
    pt = r.get("prediction_px")
    if not pt:
        return False
    if bt == "polygon" and r.get("osworld_polygon"):
        return bool(pip(pt, r["osworld_polygon"]))
    gt = r.get("gt_bbox") or [-1, -1, -1, -1]
    return gt[0] <= pt[0] <= gt[2] and gt[1] <= pt[1] <= gt[3]


def main() -> int:
    from gui_harness.openprogram_compat import create_runtime
    from refusal_judge import judge_infeasible

    samples = {s["id"]: s for s in
               json.loads((DATA / "annotations" / "osworld_g.json").read_text(encoding="utf-8"))}
    clicks = {}
    for l in open(RESULTS, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            clicks[r["sample_id"]] = r
    print(f"已有点击结果 {len(clicks)}/564", flush=True)

    judged = {}
    if JUDGE_OUT.exists():
        for l in open(JUDGE_OUT, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                judged[r["sample_id"]] = r
    todo = [sid for sid in samples if sid not in judged]
    print(f"判别器待跑 {len(todo)}/{len(samples)}", flush=True)

    if todo:
        rt = create_runtime(provider="openai-codex", model="gpt-5.5")
        f = open(JUDGE_OUT, "a", encoding="utf-8")
        for i, sid in enumerate(todo):
            s = samples[sid]
            img = DATA / "raw_images" / s["raw_image_path"]
            t0 = time.time()
            v = judge_infeasible(s["instruction"], str(img), rt)
            rec = {"sample_id": sid, "osworld_box_type": s.get("osworld_box_type"),
                   "p_infeasible": v["p_infeasible"], "verdict": v["verdict"],
                   "reasoning": v.get("reasoning", ""), "elapsed_s": round(time.time() - t0, 1)}
            if v.get("error"):
                rec["error"] = v["error"]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            judged[sid] = rec
            if (i + 1) % 20 == 0:
                print(f"  judge {i+1}/{len(todo)}", flush=True)
        f.close()

    # ---- 组合判分 + 阈值扫描 ----
    n_ref = sum(1 for s in samples.values() if s.get("osworld_box_type") == "refusal")
    n_gnd = len(samples) - n_ref
    base_gnd_ok = sum(click_correct(clicks[sid]) for sid in samples if clicks.get(sid)
                      and samples[sid].get("osworld_box_type") != "refusal")
    base_overall = base_gnd_ok / len(samples)
    print(f"\n基线(无拒绝层):可定位 {base_gnd_ok}/{n_gnd}="
          f"{base_gnd_ok/n_gnd:.1%},全量 {base_gnd_ok}/{len(samples)}={base_overall:.1%}")
    print(f"refusal 题数={n_ref},可定位题数={n_gnd}\n")

    def score(refuse_fn):
        """refuse_fn(sid)->bool。返回 (R, F, gnd_ok, all_ok)。"""
        R = F = gnd_ok = all_ok = 0
        for sid, s in samples.items():
            bt = s.get("osworld_box_type") or "bbox"
            refuse = refuse_fn(sid)
            if bt == "refusal":
                if refuse:
                    R += 1; all_ok += 1
            else:
                cc = click_correct(clicks[sid]) if clicks.get(sid) else False
                if refuse:
                    if cc:
                        F += 1                 # 本来对、被误拒 → 净损失
                elif cc:
                    gnd_ok += 1; all_ok += 1
        return R, F, gnd_ok, all_ok

    # ===== 正式成绩:零调参操作点(事先定死,不看分数挑) =====
    # 操作点 = 判别器自己的二元结论(verdict==infeasible → 拒绝)。
    # 这就是真实部署时的行为:模型自己拍板,不用测试集答案调任何阈值。
    print("== 正式成绩:判别器二元结论(verdict, 零调参)==")
    R, F, gnd_ok, all_ok = score(lambda sid: judged.get(sid, {}).get("verdict") == "infeasible")
    print(f"拒绝召回 R={R}/{n_ref} | 误拒 F={F}/{n_gnd} | "
          f"可定位子集 {gnd_ok}/{n_gnd}={gnd_ok/n_gnd:.1%} | "
          f"全量 {all_ok}/{len(samples)}={all_ok/len(samples):.1%} "
          f"(vs 基线 {base_overall:.1%}, {(all_ok/len(samples)-base_overall)*100:+.1f})")
    # 先验默认阈值 0.5(概率中点)作为对照,同样零调参
    R5, F5, g5, a5 = score(lambda sid: judged.get(sid, {}).get("p_infeasible", 0.0) >= 0.5)
    print(f"对照·固定阈值0.5: R={R5}/{n_ref} F={F5}/{n_gnd} "
          f"可定位 {g5/n_gnd:.1%} 全量 {a5/len(samples):.1%}\n")

    # ===== 敏感性分析(仅展示稳健性,不用于挑选操作点)=====
    print("== 敏感性分析:阈值扫描(NOT used for selection,仅证明对阈值不敏感)==")
    print("| 阈值 | 拒绝召回 R/54 | 误拒 F/510 | 可定位子集 | 全量 | vs 基线 |")
    print("|---|---|---|---|---|---|")
    for th in THRESHOLDS:
        R, F, gnd_ok, all_ok = score(lambda sid, th=th: judged.get(sid, {}).get("p_infeasible", 0.0) >= th)
        print(f"| {th:.1f} | {R}/{n_ref} | {F}/{n_gnd} | {gnd_ok}/{n_gnd}={gnd_ok/n_gnd:.1%} | "
              f"{all_ok}/{len(samples)}={all_ok/len(samples):.1%} | "
              f"{(all_ok/len(samples)-base_overall)*100:+.1f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
