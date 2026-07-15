#!/usr/bin/env python3
"""Evaluate UI-Venus-1.5 on ScreenSpot-Pro using its OFFICIAL protocol,
reproduced from models/grounding/ui_venus1_5_gd.py in the UI-Venus repo:

  * prompt: "Output the center point of the position corresponding to the
    following instruction: \\n{instruction}. \\n\\nThe output should just be
    the coordinates of a point, in the format [x,y]."
  * full-resolution image (NO max_pixels cap — official eval doesn't cap)
  * output: plain "[x, y]" in [0,1000]-normalized space of the full image
  * scoring: point inside GT bbox

Purpose: validate the advertised 69.6 SSPro score on OUR fixed 300-row subset
so it's comparable with the rest of our numbers.
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

Image.MAX_IMAGE_PIXELS = None  # some SSPro screenshots exceed PIL's default DecompressionBomb limit

PROMPT = ("Output the center point of the position corresponding to the following "
          "instruction: \n{instruction}. \n\nThe output should just be the coordinates "
          "of a point, in the format [x,y].")


def parse_point(text: str) -> list[float] | None:
    """Faithful port of UIVenusGroundV15._parse_point (sans the /1000 step)."""
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--val-rows", required=True)
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--num", type=int, default=300)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = json.loads(Path(args.val_rows).read_text(encoding="utf-8"))[: args.num]
    print(f"eval rows: {len(rows)}", file=sys.stderr)

    processor = AutoProcessor.from_pretrained(args.model)  # official: default pixel budget, NO cap
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, dtype=torch.bfloat16, low_cpu_mem_usage=True).to("cuda").eval()

    correct = wrong = failed = 0
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

                instruction = row["instruction"]
                if instruction.endswith("."):
                    instruction = instruction[:-1]
                messages = [{"role": "user", "content": [
                    {"type": "image", "image": im},
                    {"type": "text", "text": PROMPT.format(instruction=instruction)},
                ]}]
                inputs = processor.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True,
                    return_dict=True, return_tensors="pt").to(model.device)
                with torch.no_grad():
                    out = model.generate(**inputs, max_new_tokens=128, do_sample=False)
                gen = processor.batch_decode(
                    out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]

            pt = parse_point(gen)
            rec["raw"] = gen[:120]
            if pt is None:
                failed += 1
                rec["correctness"] = "wrong_format"
            else:
                px, py = pt[0] / 1000 * w, pt[1] / 1000 * h
                rec["prediction_px"] = [px, py]
                if gt_px[0] <= px <= gt_px[2] and gt_px[1] <= py <= gt_px[3]:
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
                  f"wrong={wrong} failed={failed}", file=sys.stderr)

    if out_f:
        out_f.close()
    total = correct + wrong + failed
    print(json.dumps({
        "model": "UI-Venus-1.5-8B", "mode": "official_native_protocol",
        "total": total, "correct": correct, "wrong": wrong, "failed_or_format": failed,
        "accuracy": round(correct / max(1, total), 4),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
