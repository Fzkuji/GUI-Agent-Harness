#!/usr/bin/env python3
"""Probe GLM-4.1V-9B-Thinking's native coordinate output convention on a
handful of real ScreenSpot-Pro-style click instructions, so we know exactly
how to parse its answers (pixel? [0,1000] fraction? <box> tag format?)
before writing a full harness-compatible serving/eval integration.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Glm4vForConditionalGeneration

PROMPT = (
    "Locate the UI element for this instruction and return its click point "
    "as pixel coordinates in the ORIGINAL image (not a cropped or resized "
    "view).\n"
    "Instruction: {instruction}\n\n"
    "Reply with ONLY JSON: {{\"point_2d\": [x, y]}}"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--val-rows", required=True)
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--num", type=int, default=6)
    args = ap.parse_args()

    rows = json.loads(Path(args.val_rows).read_text(encoding="utf-8"))[: args.num]

    print(f"loading processor+model from {args.model} ...", file=sys.stderr)
    processor = AutoProcessor.from_pretrained(args.model, use_fast=True)
    model = Glm4vForConditionalGeneration.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map="auto")

    for row in rows:
        img_path = Path(args.image_dir) / row["image"]
        with Image.open(img_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            gt = row["gt_bbox_norm"]
            gt_px = [gt[0] * w, gt[1] * h, gt[2] * w, gt[3] * h]

            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": im},
                    {"type": "text", "text": PROMPT.format(instruction=row["instruction"])},
                ],
            }]
            inputs = processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors="pt").to(model.device)
            out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
            gen = processor.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False)

            print("=" * 60)
            print(f"instruction: {row['instruction']!r}")
            print(f"image size: {w}x{h}   GT bbox (px): {[round(v) for v in gt_px]}")
            print(f"RAW OUTPUT:\n{gen}")


if __name__ == "__main__":
    main()
