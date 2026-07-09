#!/usr/bin/env python3
"""MiniMax-M3 坐标格式消融:abs_pixel / frac01 / xy1000 / point2d_1000。
同 gpt/qwen/kimi 的 SOP,baseline50,单发无提示。走 openprogram Runtime.exec()
(provider=minimax-cn-coding-plan),与 run_sspro_native.py 的 M3 全量跑法完全一致的调用路径。
用法: python probe_m3_format.py [workers]
"""
from __future__ import annotations
import json, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from PIL import Image
from gui_harness.planning import coord_formats as cf
from gui_harness.openprogram_compat import create_runtime

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
PROVIDER = "minimax-cn-coding-plan"
MODEL = "MiniMax-M3"
FORMATS = ("abs_pixel", "frac01", "xy1000", "point2d_1000")

_rt = create_runtime(provider=PROVIDER, model=MODEL, max_retries=3)


def ask(img_path, instr, fmt, W, H):
    prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
              f"instruction, then give its click point.\nInstruction: {instr}\n"
              + cf.prompt_suffix(fmt, W, H))
    content = [{"type": "text", "text": prompt}, {"type": "image", "path": str(img_path)}]
    return _rt.exec(content=content, timeout_s=150) or ""


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))

    for fmt in FORMATS:
        raw = []

        def work(sid):
            r = m3[sid]
            gt = r["gt_bbox"]
            try:
                im = Image.open(IMG_DIR / f"{sid}.png")
                W, H = im.size
                resp = ask(IMG_DIR / f"{sid}.png", r["instruction"], fmt, W, H)
                raw.append(resp[:60].replace("\n", " "))
                p = cf.parse_point(resp, fmt, W, H)
                if not p:
                    return {"sample_id": sid, "hit": False}
                return {"sample_id": sid,
                        "hit": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])}
            except Exception as e:
                return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:100]}"}

        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in ids]):
                recs.append(f.result())
        with open(OUT / f"m3_format_{fmt}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done)
        print("[M3 %-13s] %d/%d = %.0f%%  (+%derr)  例:%s"
              % (fmt, ok, len(done), 100 * ok / max(1, len(done)),
                 len(recs) - len(done), raw[:2]), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
