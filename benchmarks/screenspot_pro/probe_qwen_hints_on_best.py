#!/usr/bin/env python3
"""qwen 在【当前最优配置】(point2d_1000 + hires,单发)上单独测 OCR/YOLO 提示的增益。

之前的提示消融(probe_ablation_qwen.py)是在旧格式(abs/frac01)下测的:
  abs: 16%->42%(+26)   frac01: 54%->60%(+6)
换成真正最优的 point2d_1000 后,提示效果可能不一样(基线已经很高,边际收益可能更小,
甚至可能因为提示占用注意力而变负)——不能想当然套用旧结论,必须重测。
用法: python probe_qwen_hints_on_best.py [workers]
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
from run_sspro_native import _make_aliyun_call, _build_hint_block, IMG_DIR

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
    call = _make_aliyun_call(MODEL, hires=True)

    for use_hints in [False, True]:
        tag = "hint" if use_hints else "nohint"
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]
            img_path = IMG_DIR / f"{sid}.png"
            rec = {"sample_id": sid, "harness_correct": r["correctness"] == "correct"}
            try:
                im = Image.open(img_path); W, H = im.size
                hint = _build_hint_block(img_path, FMT) if use_hints else ""
                prompt = (
                    "This is a GUI screenshot. Find the single UI element to click for the "
                    f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                    + hint + "\n" + cf.prompt_suffix(FMT, W, H)
                )
                resp = call(prompt, img_path)
                p = cf.parse_point(resp, FMT, W, H)
                rec["hit"] = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
            return rec
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in ids]):
                recs.append(f.result())
        with open(OUT / f"qwen_hints_on_best_{tag}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done)
        print(f"[{tag}] point2d_1000+hires, use_hints={use_hints}: {ok}/{len(done)} = "
              f"{ok/max(1,len(done)):.0%}  (+{len(recs)-len(done)}err)", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
