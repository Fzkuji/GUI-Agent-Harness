#!/usr/bin/env python3
"""Zero-shot single-shot click eval for GLM-4.1V-9B-Thinking on ScreenSpot-Pro
(full image, no zoom) — directly comparable to Qwen3-VL-4B's single-shot
baseline (~59.5%/35.3% under our zoom protocol's round-0 single-shot mode).

GLM-4.1V's native answer format: <think>...</think><answer><|begin_of_box|>
{"point_2d": [x, y]}<|end_of_box|></answer>, point_2d in [0,1000]-normalized
space of the FULL input image (verified empirically against 5 GT boxes).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Glm4vForConditionalGeneration

PROMPT = (
    "Locate the UI element for this instruction and return its click point.\n"
    "Instruction: {instruction}\n\n"
    "Reply with your reasoning, then a final answer in this exact format:\n"
    '<answer>{{"point_2d": [x, y]}}</answer>\n'
    "x and y are integers in [0, 1000], the fraction of image width/height "
    "(NOT raw pixels)."
)


def parse_point(text: str) -> list[float] | None:
    m = re.search(r"\{[^{}]*\"point_2d\"[^{}]*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    pt = d.get("point_2d")
    if isinstance(pt, list) and len(pt) >= 2 and all(isinstance(v, (int, float)) for v in pt[:2]):
        return [float(pt[0]), float(pt[1])]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--val-rows", required=True)
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--num", type=int, default=80)
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = json.loads(Path(args.val_rows).read_text(encoding="utf-8"))[: args.num]
    print(f"eval rows: {len(rows)}", file=sys.stderr)

    processor = AutoProcessor.from_pretrained(args.model, use_fast=True)
    model = Glm4vForConditionalGeneration.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map="auto").eval()

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

                messages = [{"role": "user", "content": [
                    {"type": "image", "image": im},
                    {"type": "text", "text": PROMPT.format(instruction=row["instruction"])},
                ]}]
                inputs = processor.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True,
                    return_dict=True, return_tensors="pt").to(model.device)
                with torch.no_grad():
                    out = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
                gen = processor.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

            pt = parse_point(gen)
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
        "model": "GLM-4.1V-9B-Thinking", "mode": "single_shot_zero_shot",
        "total": total, "correct": correct, "wrong": wrong, "failed_or_format": failed,
        "accuracy": round(correct / max(1, total), 4),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
