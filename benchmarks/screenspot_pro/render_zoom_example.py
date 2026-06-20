#!/usr/bin/env python3
"""把一道真题的逐轮裁剪渲染成"放大序列"小图(给 pipeline 图当例子)。
每个面板:当前视野 + 红框标出下一轮要裁的区域;最后一张标出点击点(命中绿框)。
输出 runs/figures/example/round{i}.png,统一高度便于横排。
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "runs" / "figures" / "example"
OUT.mkdir(parents=True, exist_ok=True)

SID = sys.argv[1] if len(sys.argv) > 1 else "excel_macos_56"
PANEL_H = 240   # 每个面板统一高度


def find_row(sid):
    for p in (glob.glob(str(REPO / "benchmarks/screenspot_pro/results/gpt_5_5/results.jsonl"))
              + glob.glob(str(REPO / "runs/ui_vision_full/*_s*.jsonl"))):
        for l in open(p, encoding="utf-8"):
            if not l.strip():
                continue
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get("sample_id") == sid:
                return r
    return None


def panel(img, view_box, next_box, click=None, gt=None):
    """裁出 view_box,画上 next_box(红)/click(橙点)/gt(绿框),缩到统一高度。"""
    crop = img.crop(view_box).convert("RGB")
    d = ImageDraw.Draw(crop)
    ox, oy = view_box[0], view_box[1]
    if next_box:
        d.rectangle([next_box[0] - ox, next_box[1] - oy, next_box[2] - ox, next_box[3] - oy],
                    outline="#e23b3b", width=max(3, crop.width // 180))
    if gt:
        d.rectangle([gt[0] - ox, gt[1] - oy, gt[2] - ox, gt[3] - oy],
                    outline="#1bb35c", width=max(3, crop.width // 200))
    if click:
        cx, cy = click[0] - ox, click[1] - oy
        r = max(7, crop.width // 90)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline="#ff9000", width=max(3, crop.width // 160))
        d.line([cx - r - 4, cy, cx + r + 4, cy], fill="#ff9000", width=2)
        d.line([cx, cy - r - 4, cx, cy + r + 4], fill="#ff9000", width=2)
    scale = PANEL_H / crop.height
    return crop.resize((max(1, int(crop.width * scale)), PANEL_H), Image.LANCZOS)


def main():
    r = find_row(SID)
    if not r:
        print("NOT FOUND", SID)
        return 1
    img = Image.open(REPO / "benchmarks/screenspot_pro/data/images" / f"{SID}.png").convert("RGB")
    h = ((r.get("location") or {}).get("iterative_zoom") or {}).get("history") or []
    crops = [e["next_box"] for e in h if e.get("next_box")]
    gt = r["gt_bbox"]
    click = r.get("prediction_px") or [r["location"]["cx"], r["location"]["cy"]]
    full = [0, 0, img.width, img.height]
    views = [full] + crops          # 每个面板的视野
    seq = []
    for i, v in enumerate(views):
        nb = crops[i] if i < len(crops) else None
        is_last = i == len(views) - 1
        seq.append(panel(img, v, nb, click=click if is_last else None,
                         gt=gt if is_last else None))
    for i, im in enumerate(seq):
        im.save(OUT / f"round{i}.png")
    meta = {"sid": SID, "instruction": r["instruction"], "n_panels": len(seq),
            "img_wh": [img.width, img.height], "gt": gt, "click": click,
            "panel_w": [im.width for im in seq]}
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{SID}: {len(seq)} panels, instr={r['instruction'][:50]!r}, sizes={[im.width for im in seq]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
