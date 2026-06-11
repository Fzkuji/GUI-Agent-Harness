#!/usr/bin/env python3
"""v5c 挑战赛:把三臂(快答/慢答/旧全量)的相异答案与当前答案同台放大辨认。

对每行:
  挑战者 = {arm1, arm2, old} 中与当前答案距离 >18px 的去重点。
  无挑战者 → 零调用直接沿用。
  非 spatial → 放大缩略图列队([0]=当前 + 挑战者),conf>=0.75 才换。
  spatial   → 宽上下文图(包含全部点 + 320px 边距)+ 全图概览,conf>=0.80 才换。

输出 runs/ui_vision_arbitrated/v5c_shard{N}.jsonl,支持断点续跑。
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from PIL import Image, ImageDraw  # noqa: E402

from arbitrate_two_arms import (  # noqa: E402
    _zoom_thumb, draw_marker, is_spatial, point_inside,
)


def dist(p, q):
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def build_sheet(img, entries, out_path):
    """[0]=当前 + 挑战者的放大缩略图,竖排。entries: [{'id','pt'}...]"""
    thumbs = []
    for e in entries:
        x, y = e["pt"]
        t = _zoom_thumb(img, [x - 28, y - 28, x + 28, y + 28])
        d = ImageDraw.Draw(t)
        d.ellipse([t.width / 2 - 7, t.height / 2 - 7, t.width / 2 + 7, t.height / 2 + 7],
                  outline="#ff9900", width=3)
        thumbs.append((e["id"], t))
    pad_y, label_h = 8, 18
    width = max(t.width for _, t in thumbs) + 90
    height = sum(t.height + label_h + pad_y for _, t in thumbs)
    sheet = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(sheet)
    y = 0
    for tid, t in thumbs:
        d.text((4, y + 2), f"[{tid}]", fill="#cc0000")
        sheet.paste(t, (60, y + label_h))
        y += t.height + label_h + pad_y
    sheet.save(out_path)


def build_spatial_views(img, entries, out1, out2):
    """spatial 用:宽上下文图(含全部点+边距,字母标记)+ 缩放全图。"""
    xs = [e["pt"][0] for e in entries]
    ys = [e["pt"][1] for e in entries]
    pad = 320
    box = [max(0, min(xs) - pad), max(0, min(ys) - pad),
           min(img.width, max(xs) + pad), min(img.height, max(ys) + pad)]
    crop = img.crop(box)
    scale = 1.0
    if max(crop.size) < 900:
        scale = 900 / max(crop.size)
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(crop)
    colors = ["#ff9900", "#ff2222", "#2255ff", "#11aa33"]
    for i, e in enumerate(entries):
        lx = (e["pt"][0] - box[0]) * scale
        ly = (e["pt"][1] - box[1]) * scale
        draw_marker(d, lx, ly, e["id"], colors[i % 4], 1.0)
    crop.save(out1)
    ov_scale = 1.0
    if max(img.size) > 1600:
        ov_scale = 1600 / max(img.size)
    ov = img.resize((int(img.width * ov_scale), int(img.height * ov_scale)), Image.LANCZOS)
    d = ImageDraw.Draw(ov)
    for i, e in enumerate(entries):
        draw_marker(d, e["pt"][0] * ov_scale, e["pt"][1] * ov_scale, e["id"], colors[i % 4], 1.0)
    ov.save(out2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--shard-index", type=int, default=0)
    args = ap.parse_args()

    rows = {}
    for p in glob.glob(str(REPO / "runs/ui_vision_arbitrated/v5b_shard*.jsonl")):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            rows[r["sample_id"]] = r
    old = {}
    for line in open(HERE / "results/ui_vision_gpt_5_5/results.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["sample_id"] in rows:
            old[r["sample_id"]] = r.get("prediction_px")

    ann_dir = HERE / "data_ui_vision" / "annotations"
    img_dir = HERE / "data_ui_vision" / "raw_images"
    id2img = {}
    for ann in ann_dir.glob("ui_vision_*.json"):
        for s in json.loads(ann.read_text(encoding="utf-8")):
            id2img[s["id"]] = img_dir / s.get("raw_image_path", s.get("img_filename", ""))

    from gui_harness.openprogram_compat import create_runtime
    from gui_harness.utils import parse_json
    runtime = create_runtime(provider=args.provider, model=args.model)

    out_path = REPO / f"runs/ui_vision_arbitrated/v5c_shard{args.shard_index}.jsonl"
    work = REPO / "runs/ui_vision_arbitrated/judge_crops"
    work.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in open(out_path, encoding="utf-8"):
            try:
                done.add(json.loads(line)["sample_id"])
            except Exception:
                pass
    f = open(out_path, "a", encoding="utf-8")

    todo = [sid for i, sid in enumerate(sorted(rows))
            if i % args.shards == args.shard_index and sid not in done]
    print(f"shard {args.shard_index}/{args.shards}: {len(todo)} rows", flush=True)

    for i, sid in enumerate(todo):
        r = dict(rows[sid])
        instr = r["instruction"]
        chosen = r.get("chosen_px")
        action = "keep"
        meta = None
        challengers = []
        if chosen:
            seen_pts = [chosen]
            for tag, pt in (("arm1", r.get("arm1_px")), ("arm2", r.get("arm2_px")), ("old", old.get(sid))):
                if pt and all(dist(pt, q) > 18 for q in seen_pts):
                    challengers.append({"tag": tag, "pt": [int(pt[0]), int(pt[1])]})
                    seen_pts.append(pt)
        if chosen and challengers:
            img_p = id2img.get(sid)
            if img_p and img_p.exists():
                img = Image.open(str(img_p)).convert("RGB")
                entries = [{"id": "0", "pt": [int(chosen[0]), int(chosen[1])]}]
                entries += [{"id": str(j + 1), "pt": c["pt"]} for j, c in enumerate(challengers)]
                spatial = is_spatial(instr)
                conf_bar = 0.80 if spatial else 0.75
                try:
                    if spatial:
                        v1 = work / f"v5c_{sid}_ctx.png"
                        v2 = work / f"v5c_{sid}_ov.png"
                        build_spatial_views(img, entries, v1, v2)
                        content_imgs = [{"type": "image", "path": str(v1)},
                                        {"type": "image", "path": str(v2)}]
                        view_note = ("Image 1 is a wide crop containing all marked points (use it to "
                                     "find the named anchor element and verify the relation). Image 2 "
                                     "is the full screen for context.")
                    else:
                        sheet = work / f"v5c_{sid}_sheet.png"
                        build_sheet(img, entries, sheet)
                        content_imgs = [{"type": "image", "path": str(sheet)}]
                        view_note = ("The sheet shows ZOOMED views of each numbered point "
                                     "(orange dot = the exact point).")
                    prompt = f"""Target element: {instr}

Several methods proposed different click points, numbered [0] to [{len(entries)-1}].
{view_note}

Which numbered point is on the element the target names? Keep [0] unless you
can clearly see that [0] is a different element AND another numbered point
clearly IS the named element.

Reply with ONLY JSON: {{"choice": 0, "confidence": 0.0, "reasoning": "..."}}"""
                    reply = runtime.exec(content=[{"type": "text", "text": prompt}, *content_imgs],
                                         timeout_s=120)
                    parsed = parse_json(reply)
                    choice = int(parsed.get("choice", 0))
                    conf = float(parsed.get("confidence", 0) or 0)
                    meta = {"choice": choice, "confidence": conf,
                            "n_challengers": len(challengers),
                            "tags": [c["tag"] for c in challengers],
                            "reasoning": str(parsed.get("reasoning"))[:150]}
                    if 1 <= choice < len(entries) and conf >= conf_bar:
                        chosen = entries[choice]["pt"]
                        action = f"switch_{challengers[choice-1]['tag']}"
                except Exception as exc:
                    meta = {"error": exc.__class__.__name__}
        r["chosen_px"] = chosen
        r["correctness"] = "correct" if (chosen and point_inside(chosen[0], chosen[1], r["gt_bbox"])) else "wrong"
        r["v5c_action"] = action
        r["v5c_meta"] = meta
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(todo)}", flush=True)
    f.close()

    out_rows = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    ok = sum(r["correctness"] == "correct" for r in out_rows)
    print(f"\nshard {args.shard_index}: {ok}/{len(out_rows)} = {ok/max(1,len(out_rows)):.1%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
