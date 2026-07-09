#!/usr/bin/env python3
"""OSWorld-G (564) × GPT-5.5 × iterative-zoom (sspro_stack_zoom.yaml, control 惯例)。
串行,单进程,--skip-existing 续跑。输出 runs/osworld_g/results.jsonl。
refusal 类(gt=[-1,-1,-1,-1])管线照样出点击 → 必然算错(方法无拒绝能力,如实计)。
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


def main() -> int:
    import dataclasses
    import glob
    import os
    from gui_harness.openprogram_compat import create_runtime
    from gui_harness.planning.component_memory import detect_components
    from gui_harness.planning import active_localization, screenspot_locator
    from run_screenspot_pro import load_locator_config

    # 拒绝层开关:GUI_HARNESS_ALLOW_REFUSE=1 → 给模型加 action="refuse" 选项。
    # 既有定位策略不变,只是多一个动作;结果写到单独文件,不覆盖基线 results.jsonl。
    refuse = os.environ.get("GUI_HARNESS_ALLOW_REFUSE", "").lower() in {"1", "true", "yes"}
    # 可选分片并行:GUI_HARNESS_OSWG_SHARDS=2 + GUI_HARNESS_OSWG_SHARD=0/1。
    # 每片只处理 index%shards==shard 的样本,写自己的结果文件;启动时从所有
    # results_refuse*.jsonl 读已完成,跨片去重,安全续跑。
    shards = int(os.environ.get("GUI_HARNESS_OSWG_SHARDS", "1") or "1")
    shard = int(os.environ.get("GUI_HARNESS_OSWG_SHARD", "0") or "0")
    sharded = refuse and shards > 1 and 0 <= shard < shards

    samples = json.loads((DATA / "annotations" / "osworld_g.json").read_text(encoding="utf-8"))
    if sharded:
        out = REPO / f"runs/osworld_g/results_refuse_s{shard}.jsonl"
    elif refuse:
        out = REPO / "runs/osworld_g/results_refuse.jsonl"
    else:
        out = REPO / "runs/osworld_g/results.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    work = REPO / f"runs/osworld_g/work{('_s'+str(shard)) if sharded else ''}"
    work.mkdir(parents=True, exist_ok=True)

    # 已完成集合:分片模式下汇总所有 results_refuse*.jsonl(含原单进程文件 + 各分片)
    done = set()
    done_files = (sorted(glob.glob(str(REPO / "runs/osworld_g/results_refuse*.jsonl")))
                  if refuse else [str(out)])
    for df in done_files:
        if os.path.exists(df):
            for l in open(df, encoding="utf-8"):
                try:
                    done.add(json.loads(l)["sample_id"])
                except Exception:
                    pass
    cfg = load_locator_config(str(HERE / "configs" / "sspro_stack_zoom.yaml"))
    if refuse:
        cfg = dataclasses.replace(cfg, allow_refuse=True)
    tag = f"拒绝层 ON shard {shard}/{shards}" if sharded else ("拒绝层 ON" if refuse else "基线(无拒绝)")
    print(f"模式: {tag} -> {out.name}", flush=True)
    rt = create_runtime(provider="openai-codex", model="gpt-5.5")

    f = open(out, "a", encoding="utf-8")
    # 可选:只跑 refusal 样本(GUI_HARNESS_OSWG_REFUSAL_ONLY=1)——验证拒绝召回 R 用
    refusal_only = os.environ.get("GUI_HARNESS_OSWG_REFUSAL_ONLY", "").lower() in {"1", "true", "yes"}
    # 分片:按样本全局序号取模,两片处理不相交的一半;再排除已完成
    todo = [s for i, s in enumerate(samples)
            if s["id"] not in done and (not sharded or i % shards == shard)
            and (not refusal_only or s.get("osworld_box_type") == "refusal")]
    print(f"OSWorld-G: {len(todo)} 待跑(总 {len(samples)},已完成 {len(done)}"
          f"{', refusal-only' if refusal_only else ''})", flush=True)
    for i, s in enumerate(todo):
        sid = s["id"]
        img = DATA / "raw_images" / s["raw_image_path"]
        gt = s["bbox"]
        t0 = time.time()
        rec = {"sample_id": sid, "instruction": s["instruction"], "gt_bbox": gt,
               "osworld_box_type": s.get("osworld_box_type"),
               "osworld_polygon": s.get("osworld_polygon"),
               "ui_type": s.get("ui_type")}
        is_refusal_task = s.get("osworld_box_type") == "refusal"
        # 基线模式(无拒绝层):refusal 题无目标、管线总会点 → 必错。直接短路记 wrong,
        # 避免徒劳耗尽 8 轮+recrop(单题十几分钟)。拒绝层模式下不短路——要让模型
        # 自己在管线里决定是否 action="refuse"。
        if is_refusal_task and not refuse:
            rec["prediction_px"] = None
            rec["correctness"] = "wrong"
            rec["location"] = {"grounding_type": "refusal_not_supported"}
            rec["elapsed_s"] = 0.0
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            continue
        try:
            if not img.exists():
                raise FileNotFoundError(img.name)
            det = detect_components(str(img))
            cands = active_localization.build_candidates([], det["texts"], det["icons"])
            located = screenspot_locator.screenspot_locate(
                task=s["instruction"], target=s["instruction"], img_path=str(img),
                img_w=det["img_w"], img_h=det["img_h"], candidates=cands, runtime=rt,
                work_dir=str(work), config=cfg)
            if located and located.get("refused"):
                # 模型主动拒绝:不点击。refusal 题=对,可定位题=错(误拒)。
                rec["prediction_px"] = None
                rec["refused"] = True
                rec["correctness"] = "correct" if is_refusal_task else "wrong"
                rec["location"] = {k: located.get(k) for k in ("grounding_type", "reasoning")}
            elif located:
                cx, cy = int(located["cx"]), int(located["cy"])
                rec["prediction_px"] = [cx, cy]
                # 点击了:refusal 题=错(本该拒绝),可定位题按命中判
                rec["correctness"] = "correct" if (not is_refusal_task and gt[0] <= cx <= gt[2] and gt[1] <= cy <= gt[3]) else "wrong"
                rec["location"] = {k: located.get(k) for k in ("name", "grounding_type", "reasoning")}
            else:
                rec["prediction_px"] = None
                rec["correctness"] = "wrong"
        except Exception as exc:
            from gui_harness.error_monitor import reraise_if_fatal
            reraise_if_fatal(exc)
            rec["error"] = {"type": exc.__class__.__name__, "message": str(exc)[:200]}
            rec["correctness"] = "wrong"
        rec["elapsed_s"] = round(time.time() - t0, 1)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(todo)}", flush=True)
    f.close()

    rows = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
    ok = sum(r["correctness"] == "correct" for r in rows)
    gnd = [r for r in rows if r.get("osworld_box_type") != "refusal"]
    gok = sum(r["correctness"] == "correct" for r in gnd)
    print(f"\nOSWorld-G 全量: {ok}/{len(rows)} = {ok/max(1,len(rows)):.1%}", flush=True)
    print(f"  可定位子集(非 refusal): {gok}/{len(gnd)} = {gok/max(1,len(gnd)):.1%}", flush=True)
    if refuse:
        ref = [r for r in rows if r.get("osworld_box_type") == "refusal"]
        R = sum(1 for r in ref if r.get("refused"))
        F = sum(1 for r in gnd if r.get("refused"))
        print(f"  拒绝召回 R={R}/{len(ref)}(正确弃权);误拒 F={F}/{len(gnd)}(可定位题被错误拒绝)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
