#!/usr/bin/env python3
"""UI-Venus-1.5 + OUR zoom-refine method on ScreenSpot-Pro.

The experiment this project exists for: take a model whose OWN method
(native single-shot) scores X, wrap it in OUR iterative-zoom method, show > X.

Design — the model keeps its native dialect at every step (it only knows
"[x,y]"); the CROPPING POLICY is ours:
  round 1: native single-shot on the full image -> coarse point P1
  round 2: crop a region centered on P1 (--crop-frac of each dimension),
           ask again natively on the crop, map the point back to full image
  (optional round 3 with a tighter crop, --rounds 3)

Scoring identical to every other number in this project: final point inside
GT bbox, fixed seed-20260711 300-row subset.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

Image.MAX_IMAGE_PIXELS = None

PROMPT = ("Output the center point of the position corresponding to the following "
          "instruction: \n{instruction}. \n\nThe output should just be the coordinates "
          "of a point, in the format [x,y].")


def parse_point(text: str) -> list[float] | None:
    pattern_bbox = r"\[\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\]"
    pattern_point = r"\[\s*-?\d+\s*,\s*-?\d+\s*\]"
    text = text.strip()
    try:
        if re.fullmatch(pattern_bbox, text, re.DOTALL):
            box = json.loads(text)
            return [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
        if re.fullmatch(pattern_point, text, re.DOTALL):
            return [float(v) for v in json.loads(text)]
        return [float(v) for v in text.split("]")[0].split("[")[1].split(",")]
    except Exception:
        return None


def ask(model, processor, img: Image.Image, instruction: str) -> list[float] | None:
    """One native UI-Venus call; returns point in PIXELS of `img`."""
    if instruction.endswith("."):
        instruction = instruction[:-1]
    messages = [{"role": "user", "content": [
        {"type": "image", "image": img},
        {"type": "text", "text": PROMPT.format(instruction=instruction)},
    ]}]
    inputs = processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=128, do_sample=False)
    gen = processor.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
    pt = parse_point(gen)
    if pt is None:
        return None
    return [pt[0] / 1000 * img.width, pt[1] / 1000 * img.height]


def crop_around(img: Image.Image, cx: float, cy: float, frac: float) -> tuple[Image.Image, float, float]:
    """Crop a frac-of-each-dimension window centered on (cx, cy), clamped."""
    w, h = img.size
    cw, ch = max(64, w * frac), max(64, h * frac)
    x1 = min(max(0.0, cx - cw / 2), w - cw)
    y1 = min(max(0.0, cy - ch / 2), h - ch)
    region = img.crop((int(x1), int(y1), int(x1 + cw), int(y1 + ch)))
    return region, x1, y1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--val-rows", required=True)
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--num", type=int, default=300)
    ap.add_argument("--rounds", type=int, default=2, help="total rounds incl. the full-image shot")
    ap.add_argument("--crop-frac", type=float, default=0.35,
                    help="refine-crop size as a fraction of each image dimension")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = json.loads(Path(args.val_rows).read_text(encoding="utf-8"))[: args.num]
    print(f"eval rows: {len(rows)} rounds={args.rounds} crop_frac={args.crop_frac}", file=sys.stderr)

    processor = AutoProcessor.from_pretrained(args.model)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, dtype=torch.bfloat16, low_cpu_mem_usage=True).to("cuda").eval()

    correct = wrong = failed = 0
    refine_changed_verdict = 0
    out_f = open(args.out, "w", encoding="utf-8") if args.out else None
    for i, row in enumerate(rows):
        img_path = Path(args.image_dir) / row["image"]
        rec = {"source_index": row.get("source_index", i), "instruction": row["instruction"]}
        try:
            with Image.open(img_path) as im:
                im = im.convert("RGB")
                w, h = im.size
                gt = row["gt_bbox_norm"]
                gt_px = [gt[0] * w, gt[1] * h, gt[2] * w, gt[3] * h]

                pt = ask(model, processor, im, row["instruction"])
                rec["round_points"] = [pt]
                frac = args.crop_frac
                for _r in range(args.rounds - 1):
                    if pt is None:
                        break
                    region, ox, oy = crop_around(im, pt[0], pt[1], frac)
                    pt2 = ask(model, processor, region, row["instruction"])
                    if pt2 is not None:
                        pt = [ox + pt2[0], oy + pt2[1]]
                    rec["round_points"].append(pt)
                    frac *= 0.5  # tighter each extra round

            if pt is None:
                failed += 1
                rec["correctness"] = "wrong_format"
            else:
                rec["prediction_px"] = pt
                hit = gt_px[0] <= pt[0] <= gt_px[2] and gt_px[1] <= pt[1] <= gt_px[3]
                p1 = rec["round_points"][0]
                hit1 = (p1 is not None and
                        gt_px[0] <= p1[0] <= gt_px[2] and gt_px[1] <= p1[1] <= gt_px[3])
                if hit != hit1:
                    refine_changed_verdict += 1
                rec["round1_hit"] = hit1
                if hit:
                    correct += 1
                    rec["correctness"] = "correct"
                else:
                    wrong += 1
                    rec["correctness"] = "wrong"
        except Exception as exc:  # noqa: BLE001
            failed += 1
            rec["correctness"] = "error"
            rec["error"] = f"{exc.__class__.__name__}: {exc}"

        if out_f:
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
        total = correct + wrong + failed
        if total % 10 == 0 or i == len(rows) - 1:
            print(f"  [{total}/{len(rows)}] acc={correct}/{total} ({100*correct/max(1,total):.1f}%) "
                  f"wrong={wrong} failed={failed} verdict_flips={refine_changed_verdict}",
                  file=sys.stderr)

    if out_f:
        out_f.close()
    total = correct + wrong + failed
    print(json.dumps({
        "model": "UI-Venus-1.5-8B", "mode": f"ours_zoomrefine_r{args.rounds}_f{args.crop_frac}",
        "total": total, "correct": correct, "wrong": wrong, "failed_or_format": failed,
        "accuracy": round(correct / max(1, total), 4),
        "verdict_flips_vs_round1": refine_changed_verdict,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
