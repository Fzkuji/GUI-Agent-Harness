#!/usr/bin/env python3
"""ZoomClick(做对版):建立在可复现 smart_resize 原生协议之上。

全图粗定位(可复现映射)→ 以预测点为心在【原图原生分辨率】裁剪窗口 → 在裁剪上重定位
→ 多步 ×0.5 收窄。裁剪取自原图(非缩放图),故小图标是全清晰度。与 probe_repro_native
共用 smart_resize/_ask/_parse,坐标始终按"当前所发图像空间→其原图/裁剪空间"映射。

用法: python probe_repro_zoom.py <max_pixels> [workers] [steps] [floor]
对 rand50 + err50 各测,和 harness 同题对比。
"""
from __future__ import annotations
import json, sys, glob
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from probe_repro_native import (smart_resize, _ask, _parse, hit, load_results,
                                RES, IMG_DIR)


def predict_img(im: Image.Image, instruction: str, max_pixels: int):
    """在传入图像 im 上定位,返回 im 自身像素坐标(已从缩放空间映射回 im)。"""
    W, H = im.size
    rh, rw = smart_resize(H, W, max_pixels)
    rim = im.resize((rw, rh), Image.BICUBIC)
    txt = _ask(rim, instruction, rw, rh)
    xy = _parse(txt)
    if not xy:
        return None
    x, y = xy
    if x <= 1000 and y <= 1000 and (rw > 1200 or rh > 1200):
        return (x / 1000 * W, y / 1000 * H)
    return (x * W / rw, y * H / rh)


def zoomclick(sid, instruction, max_pixels, steps=2, floor=768):
    full = Image.open(IMG_DIR / f"{sid}.png").convert("RGB")
    W, H = full.size
    p = predict_img(full, instruction, max_pixels)   # 全图粗定位
    if not p:
        return None
    cx, cy = p
    side = max(W, H)
    for _ in range(steps):
        side = max(floor, side * 0.5)
        half = side / 2
        l = int(max(0, min(cx - half, W - side)))
        t = int(max(0, min(cy - half, H - side)))
        r = int(min(W, l + side)); b = int(min(H, t + side))
        if r - l < 16 or b - t < 16:
            break
        crop = full.crop((l, t, r, b))              # 原图原生分辨率裁剪
        sub = predict_img(crop, instruction, max_pixels)
        if not sub:
            break
        cx, cy = l + sub[0], t + sub[1]             # 映射回全图
    return (cx, cy)


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    max_pixels = int(sys.argv[1]) if len(sys.argv) > 1 else 4014080
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    floor = int(sys.argv[4]) if len(sys.argv) > 4 else 768
    seen = load_results()
    rand_ids = json.load(open(RES / "repro_rand50_ids.json"))
    err_ids = json.load(open(RES / "probe50_ids.json"))

    for tag, ids in [("rand50", rand_ids), ("err50", err_ids)]:
        recs = []
        def work(sid):
            r = seen[sid]; gt = r["gt_bbox"]
            try:
                p = zoomclick(sid, r["instruction"], max_pixels, steps, floor)
                return {"sample_id": sid, "group": r.get("group"), "gt_bbox": gt,
                        "harness_correct": r["correctness"] == "correct",
                        "zoom_pred": [int(p[0]), int(p[1])] if p else None,
                        "zoom_hit": hit(p, gt)}
            except Exception as exc:
                return {"sample_id": sid, "error": f"{exc.__class__.__name__}: {str(exc)[:100]}"}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(work, s) for s in ids]
            for i, f in enumerate(as_completed(futs)):
                recs.append(f.result())
                if (i + 1) % 10 == 0:
                    print(f"  [{tag}] {i+1}/{len(ids)} zoom={sum(x.get('zoom_hit',False) for x in recs)}", flush=True)
        with open(RES / f"repro_zoom_{tag}_mp{max_pixels}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "zoom_hit" in x]
        zh = sum(x["zoom_hit"] for x in done); hc = sum(x.get("harness_correct", False) for x in done)
        print(f"\n[{tag}] ZoomClick(做对版) mp={max_pixels} steps={steps} floor={floor} n={len(done)}(+{len(recs)-len(done)}err)")
        print(f"   ZoomClick 命中 {zh}/{len(done)} = {zh/max(1,len(done)):.0%}")
        print(f"   harness 同题  命中 {hc}/{len(done)} = {hc/max(1,len(done)):.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
