#!/usr/bin/env python3
"""Claude 通道复刻探针:直连 API + Claude Code 式图片协议。

复刻 Claude Code Read 工具的两个要素:
  1. 大图预缩到 2000px 长边(仅当超限)
  2. prompt 注入 CC 原话元数据:[Image: original WxH, displayed at wxh.
     Multiply coordinates by k to map to original image.]
模型在 displayed 空间定位、自己乘回原图空间;判分仍在原图空间。
对照:直连原图 30%,CLI 通道 68%。若本探针≈68%,通道魔法即可移植进 harness。
用法: python probe_claude_ccstyle.py [workers]
输出: runs/sspro_baseline/claude47_ccstyle_1m.jsonl
"""
from __future__ import annotations
import io, json, sys, glob, time
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
CC_MAX_SIDE = 2000
CACHE = IMG_DIR.parent / "images_cc2000_cache"

_rt = create_runtime(provider="claude-code", model="claude-opus-4-7[1m]", max_retries=3)


def cc_prepare(img_path: Path) -> tuple[Path, int, int, int, int, float]:
    """Return (send_path, W, H, w, h, k) per the Claude Code Read protocol."""
    im = Image.open(img_path)
    W, H = im.size
    if max(W, H) <= CC_MAX_SIDE:
        return img_path, W, H, W, H, 1.0
    k = max(W, H) / CC_MAX_SIDE
    w, h = round(W / k), round(H / k)
    CACHE.mkdir(exist_ok=True)
    out = CACHE / (img_path.stem + ".png")
    if not out.exists():
        im.resize((w, h), Image.LANCZOS).save(out, "PNG")
    return out, W, H, w, h, k


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
    out_path = OUT / "claude47_ccstyle_1m.jsonl"
    done = set()
    if out_path.exists():
        for l in open(out_path, encoding="utf-8"):
            if l.strip():
                rr = json.loads(l)
                if "hit" in rr:
                    done.add(rr["sample_id"])
    todo = [s for s in ids if s not in done]

    def work(sid):
        r = meta[sid]
        gt = r["gt_bbox"]
        try:
            send, W, H, w, h, k = cc_prepare(IMG_DIR / f"{sid}.png")
            meta_line = (f"[Image: original {W}x{H}, displayed at {w}x{h}. "
                         f"Multiply coordinates by {k:.2f} to map to original image.]"
                         if k != 1.0 else f"[Image: {W}x{H}]")
            prompt = (meta_line + "\n"
                      "This is a GUI screenshot. Find the single UI element to click for the "
                      f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                      + cf.prompt_suffix("abs_pixel", W, H))
            t0 = time.time()
            resp = _rt.exec(content=[{"type": "text", "text": prompt},
                                     {"type": "image", "path": str(send)}],
                            timeout_s=180) or ""
            p = cf.parse_point(resp, "abs_pixel", W, H)
            rec = {"sample_id": sid, "k": round(k, 3),
                   "elapsed_s": round(time.time() - t0, 1)}
            if not p:
                rec.update(hit=False, raw=resp[:150])
            else:
                rec.update(pred=[p[0], p[1]],
                           hit=bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3]))
            return rec
        except Exception as e:
            return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:120]}"}

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in todo]):
            recs.append(f.result())
            if len(recs) % 10 == 0:
                print(f"  progress {len(recs)}/{len(todo)}", flush=True)
    with open(out_path, "a", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    all_recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    done_r = [x for x in all_recs if "hit" in x]
    ok = sum(x["hit"] for x in done_r)
    print("[claude CC-style 1m] %d/%d = %.0f%% (err=%d)  [直连原图 30%% | CLI通道 68%%]"
          % (ok, len(done_r), 100 * ok / max(1, len(done_r)),
             len(all_recs) - len(done_r)), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
