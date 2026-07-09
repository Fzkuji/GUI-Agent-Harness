#!/usr/bin/env python3
"""qwen 在【当前最终配置】(point2d_1000+hires,无提示)上重跑,这次把预测坐标也存下来。

之前几轮探针(qwen_official / qwen_native_vs_harness / qwen_hints_on_best)图省事只存了
hit 布尔,没法做失败构成分析(近失 vs 选错元素)。这次一次性补上坐标,供后续设计"harness
如何在 native single-shot 之上再涨一截"用。
用法: python probe_qwen_best_with_coords.py [workers]
"""
from __future__ import annotations
import json, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from PIL import Image

from gui_harness.planning import coord_formats as cf
from run_sspro_native import _make_aliyun_call, IMG_DIR

OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
MODEL = "qwen3.7-plus"
FMT = "point2d_1000"


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    call = _make_aliyun_call(MODEL, hires=True)  # 当前 qwen profile: hires on, use_hints off

    def work(sid):
        r = m3[sid]; gt = r["gt_bbox"]
        img_path = IMG_DIR / f"{sid}.png"
        rec = {"sample_id": sid, "group": r.get("group"), "instruction": r["instruction"], "gt_bbox": gt}
        try:
            im = Image.open(img_path); W, H = im.size
            prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
                      f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                      + cf.prompt_suffix(FMT, W, H))
            resp = call(prompt, img_path)
            p = cf.parse_point(resp, FMT, W, H)
            if p is None:
                rec["prediction_px"] = None; rec["hit"] = False
            else:
                cx, cy = int(p[0]), int(p[1])
                rec["prediction_px"] = [cx, cy]
                rec["hit"] = bool(gt[0] <= cx <= gt[2] and gt[1] <= cy <= gt[3])
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        return rec

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in ids]):
            recs.append(f.result())
    with open(OUT / "qwen_best_with_coords.jsonl", "w", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    done = [x for x in recs if "hit" in x]
    ok = sum(x["hit"] for x in done)
    print(f"point2d_1000+hires,no-hint(带坐标): {ok}/{len(done)} = {ok/max(1,len(done)):.0%} "
          f"(+{len(recs)-len(done)}err)", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
