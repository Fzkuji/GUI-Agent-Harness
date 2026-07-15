#!/usr/bin/env python3
"""Eval a (optionally LoRA-adapted) Qwen3-VL on the held-out GRPO click set.
Same correctness check as grpo_reward.py / eval_zoom_traj.py: point inside
GT bbox, both in [0,1000]-normalized space of the displayed crop.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import torch
from PIL import Image
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor


def parse_json_reply(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default="", help="LoRA adapter dir; empty = base model")
    ap.add_argument("--max-pixels", type=int, default=2097152)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = json.loads(Path(args.data).read_text(encoding="utf-8"))
    print(f"eval rows: {len(rows)}", file=sys.stderr)

    processor = AutoProcessor.from_pretrained(
        args.model, trust_remote_code=True, max_pixels=args.max_pixels)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, dtype=torch.bfloat16, trust_remote_code=True).to("cuda").eval()
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter).eval()
        print(f"loaded LoRA adapter: {args.adapter}", file=sys.stderr)
    else:
        print("using BASE model (no adapter)", file=sys.stderr)

    correct = wrong = failed = 0
    out_f = open(args.out, "w", encoding="utf-8") if args.out else None
    for i, r in enumerate(rows):
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": r["image"]},
            {"type": "text", "text": r["prompt_text"]},
        ]}]
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[Image.open(r["image"]).convert("RGB")],
                           return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=192, do_sample=False)
        gen = processor.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        parsed = parse_json_reply(gen)
        gt = r["gt_bbox_norm1000"]
        rec = {"sample_id": r["sample_id"], "raw": gen}
        if not parsed:
            failed += 1
            rec["correctness"] = "wrong_format"
        else:
            raw = parsed.get("point_2d") or [parsed.get("x"), parsed.get("y")]
            if isinstance(raw, list) and len(raw) >= 2 and all(isinstance(v, (int, float)) for v in raw[:2]):
                x, y = float(raw[0]), float(raw[1])
                if gt[0] <= x <= gt[2] and gt[1] <= y <= gt[3]:
                    correct += 1
                    rec["correctness"] = "correct"
                else:
                    wrong += 1
                    rec["correctness"] = "wrong"
            else:
                failed += 1
                rec["correctness"] = "wrong_format"
        if out_f:
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
        total = correct + wrong + failed
        if total % 20 == 0 or i == len(rows) - 1:
            print(f"  [{total}/{len(rows)}] acc={correct}/{total} ({100*correct/max(1,total):.1f}%) "
                  f"wrong={wrong} failed={failed}", file=sys.stderr)

    if out_f:
        out_f.close()
    total = correct + wrong + failed
    print(json.dumps({
        "adapter": args.adapter or "<base>", "total": total, "correct": correct,
        "wrong": wrong, "failed_or_format": failed,
        "accuracy": round(correct / max(1, total), 4),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
