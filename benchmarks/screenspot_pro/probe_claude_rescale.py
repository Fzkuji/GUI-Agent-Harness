#!/usr/bin/env python3
"""Claude 4.7 母语坐标系假设验证:abs_pixel 提问,预测点按两种空间判分。

假设:Anthropic API 把长边>1568 或 >1.15Mpx 的图服务端缩小,Claude 答的是
缩放后图像的像素空间(computer-use 母语),不是 prompt 声明的原图空间。
判分:hit_orig(点按原图像素) vs hit_rescaled(点×缩放系数还原到原图)。
用法: python probe_claude_rescale.py [workers]
输出: runs/sspro_baseline/claude47_rescale.jsonl
"""
from __future__ import annotations
import json, sys, glob, math
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

_rt = create_runtime(provider="claude-code", model="claude-opus-4-7", max_retries=3)


def api_scale(W: int, H: int) -> float:
    """Anthropic 服务端缩放系数:长边≤1568 且 ≤~1.15Mpx。"""
    return min(1.0, 1568 / max(W, H), math.sqrt(1_150_000 / (W * H)))


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    meta = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                meta[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    out_path = OUT / "claude47_rescale.jsonl"
    done = set()
    if out_path.exists():
        for l in open(out_path, encoding="utf-8"):
            if l.strip():
                rr = json.loads(l)
                if "pred" in rr:
                    done.add(rr["sample_id"])
    todo = [s for s in ids if s not in done]

    def work(sid):
        r = meta[sid]
        gt = r["gt_bbox"]
        try:
            img = IMG_DIR / f"{sid}.png"
            W, H = Image.open(img).size
            prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
                      f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                      + cf.prompt_suffix("abs_pixel", W, H))
            resp = _rt.exec(content=[{"type": "text", "text": prompt},
                                     {"type": "image", "path": str(img)}], timeout_s=150) or ""
            p = cf.parse_point(resp, "abs_pixel", W, H)
            if not p:
                return {"sample_id": sid, "pred": None, "raw": resp[:150]}
            s = api_scale(W, H)
            rx, ry = p[0] / s, p[1] / s
            return {"sample_id": sid, "pred": [p[0], p[1]], "W": W, "H": H, "scale": round(s, 4),
                    "hit_orig": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3]),
                    "hit_rescaled": bool(gt[0] <= rx <= gt[2] and gt[1] <= ry <= gt[3])}
        except Exception as e:
            return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:100]}"}

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in todo]):
            recs.append(f.result())
    with open(out_path, "a", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    all_recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    scored = [x for x in all_recs if x.get("pred")]
    n = len(scored)
    print("[claude47 rescale] orig %d/%d = %.0f%%   rescaled %d/%d = %.0f%%   (noparse=%d err=%d)"
          % (sum(x["hit_orig"] for x in scored), n, 100 * sum(x["hit_orig"] for x in scored) / max(1, n),
             sum(x["hit_rescaled"] for x in scored), n, 100 * sum(x["hit_rescaled"] for x in scored) / max(1, n),
             sum(1 for x in all_recs if x.get("pred") is None and "error" not in x),
             sum(1 for x in all_recs if "error" in x)), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
