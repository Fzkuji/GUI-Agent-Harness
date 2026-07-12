#!/usr/bin/env python3
"""Evaluate a (LoRA-)tuned VLM on GUIAct with a PURE-MODEL zoom loop.

This is the "did the scaffold distill into the weights?" test: no detector, no
OCR, no candidate evidence, no commit gate — just the model driving its own
crop -> crop -> final -> click trajectory, exactly in the format it was trained
on (prompts.py, normalized [0,1000] displayed-image coordinates).

Modes:
  --mode zoom     iterative zoom trajectory (default)
  --mode single   single-shot point_2d click on the full image (baseline)

Scoring: predicted point (mapped back to original pixels) inside the GT box.

Talks to any OpenAI-compatible endpoint (tools/serve_qwen_vl_api.py or
serve_qwen_vl_lora_api.py, vLLM, etc.).

Example:
  python eval_zoom_traj.py --api-base http://127.0.0.1:8000/v1 --model qwen3-vl-8b \
    --val-rows ../data/guiact_zoom_sft/val_rows.json --image-dir .../GUIAct/web_imgs
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts  # noqa: E402

TOTAL_ROUNDS = 8


# ═══════════════════════════════════════════
# API + parsing helpers
# ═══════════════════════════════════════════

def img_to_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def chat(api_base: str, model: str, text: str, img: Image.Image,
         timeout: float = 180.0, max_tokens: int = 512) -> str:
    resp = requests.post(
        f"{api_base.rstrip('/')}/chat/completions",
        json={
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": img_to_data_url(img)}},
                ],
            }],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_json_reply(reply: str) -> Optional[dict[str, Any]]:
    m = re.search(r"\{.*\}", reply, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def denorm_box(bbox_norm: list[float], crop: list[float]) -> list[float]:
    """[0,1000] of displayed crop -> original coordinates."""
    x1, y1, x2, y2 = crop
    w, h = x2 - x1, y2 - y1
    bx1, by1, bx2, by2 = bbox_norm
    out = [x1 + bx1 / 1000 * w, y1 + by1 / 1000 * h,
           x1 + bx2 / 1000 * w, y1 + by2 / 1000 * h]
    if out[2] < out[0]:
        out[0], out[2] = out[2], out[0]
    if out[3] < out[1]:
        out[1], out[3] = out[3], out[1]
    return out


def denorm_point(pt: list[float], crop: list[float]) -> list[float]:
    x1, y1, x2, y2 = crop
    return [x1 + pt[0] / 1000 * (x2 - x1), y1 + pt[1] / 1000 * (y2 - y1)]


def render_display(img: Image.Image, crop: list[float],
                   min_short_side: int, max_scale: float) -> tuple[Image.Image, float]:
    region = img.crop(tuple(int(round(v)) for v in crop))
    short = max(1, min(region.width, region.height))
    scale = 1.0 if short >= min_short_side else min(max_scale, min_short_side / short)
    if scale != 1.0:
        region = region.resize(
            (max(1, int(region.width * scale)), max(1, int(region.height * scale))),
            Image.LANCZOS,
        )
    return region, scale


# ═══════════════════════════════════════════
# Per-sample runners
# ═══════════════════════════════════════════

def run_zoom(api_base: str, model: str, img: Image.Image,
             instruction: str, max_rounds: int) -> dict[str, Any]:
    img_w, img_h = img.size
    crop: list[float] = [0, 0, img_w, img_h]
    history: list[str] = []
    trace: list[dict[str, Any]] = []

    for round_idx in range(max_rounds):
        disp, scale = render_display(img, crop, 512, 5.0)
        dyn = prompts.crop_dynamic_block(
            task=instruction, target=instruction, img_w=img_w, img_h=img_h,
            crop_box=[int(v) for v in crop], display_scale=scale,
            round_idx=round_idx, total_rounds=TOTAL_ROUNDS,
            stage_idx=min(round_idx, 2),
            history_lines="\n".join(history) or "(none)",
        )
        parsed = parse_json_reply(
            chat(api_base, model, f"{prompts.CROP_RULES_NORM}\n\n{dyn}", disp))
        trace.append({"round": round_idx + 1, "crop": crop, "reply": parsed})
        if not parsed:
            break
        action = str(parsed.get("action", "")).lower()
        bbox = parsed.get("bbox")
        if action == "crop" and isinstance(bbox, list) and len(bbox) == 4:
            new_crop = denorm_box([float(v) for v in bbox], crop)
            if (new_crop[2] - new_crop[0]) < 8 or (new_crop[3] - new_crop[1]) < 8:
                break
            history.append(
                f"round {round_idx + 1}: action=crop committed crop -> "
                f"{[int(v) for v in new_crop]} (original coordinates)")
            crop = new_crop
            continue
        if action == "recrop":
            crop = [0, 0, img_w, img_h]  # back out to full image
            history.append(f"round {round_idx + 1}: action=recrop -> full image")
            continue
        break  # final (or anything else) -> go click

    # Final click on the upscaled current crop.
    disp, scale = render_display(img, crop, 640, 8.0)
    dyn = prompts.click_dynamic_block(
        task=instruction, target=instruction, img_w=img_w, img_h=img_h,
        crop_box=[int(v) for v in crop], display_scale=scale)
    parsed = parse_json_reply(
        chat(api_base, model, f"{prompts.CLICK_RULES_NORM}\n\n{dyn}", disp))
    trace.append({"stage": "click", "crop": crop, "reply": parsed})

    pt = None
    if parsed:
        raw = parsed.get("point_2d") or [parsed.get("x"), parsed.get("y")]
        if isinstance(raw, list) and len(raw) >= 2 and all(
                isinstance(v, (int, float)) for v in raw[:2]):
            pt = denorm_point([float(raw[0]), float(raw[1])], crop)
    return {"point": pt, "trace": trace}


SINGLE_SHOT_PROMPT = (
    "Locate the UI element for this instruction and return its click point.\n"
    "Instruction: {instruction}\n\n"
    + prompts.NORM_COORD_CLICK
    + "\n\nReply with ONLY JSON:\n"
    + '{{"point_2d": [x, y], "reasoning": "..."}}'
)


def run_single(api_base: str, model: str, img: Image.Image,
               instruction: str) -> dict[str, Any]:
    parsed = parse_json_reply(
        chat(api_base, model, SINGLE_SHOT_PROMPT.format(instruction=instruction), img))
    pt = None
    if parsed:
        raw = parsed.get("point_2d")
        if isinstance(raw, list) and len(raw) >= 2:
            pt = denorm_point([float(raw[0]), float(raw[1])],
                              [0, 0, img.width, img.height])
    return {"point": pt, "trace": [parsed]}


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-base", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--model", default="qwen3-vl-8b")
    ap.add_argument("--val-rows", required=True, help="val_rows.json from prepare_guiact_zoom_sft.py / prepare_zoom_sft_v2.py")
    ap.add_argument("--image-dir", default="", help="image root; v2 val rows carry a per-row image_dir which takes precedence")
    ap.add_argument("--mode", choices=["zoom", "single"], default="zoom")
    ap.add_argument("--num", type=int, default=0, help="0 = all")
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--out", default="", help="results JSONL (default: eval_<mode>_<ts>.jsonl)")
    args = ap.parse_args()

    rows = json.loads(Path(args.val_rows).read_text(encoding="utf-8"))
    if args.num > 0:
        rows = rows[: args.num]
    out_path = Path(args.out or f"eval_{args.mode}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")

    correct = wrong = failed = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for i, row in enumerate(rows):
            img_path = Path(row.get("image_dir") or args.image_dir) / row["image"]
            rec: dict[str, Any] = {
                "source_index": row["source_index"],
                "instruction": row["instruction"],
                "gt_bbox_norm": row["gt_bbox_norm"],
                "mode": args.mode,
            }
            try:
                with Image.open(img_path) as img:
                    img.load()
                    gt = [
                        row["gt_bbox_norm"][0] * img.width, row["gt_bbox_norm"][1] * img.height,
                        row["gt_bbox_norm"][2] * img.width, row["gt_bbox_norm"][3] * img.height,
                    ]
                    result = (run_zoom(args.api_base, args.model, img,
                                       row["instruction"], args.max_rounds)
                              if args.mode == "zoom"
                              else run_single(args.api_base, args.model, img,
                                              row["instruction"]))
                pt = result["point"]
                rec["prediction_px"] = pt
                rec["trace"] = result["trace"]
                if pt is None:
                    rec["correctness"] = "wrong_format"
                    failed += 1
                elif gt[0] <= pt[0] <= gt[2] and gt[1] <= pt[1] <= gt[3]:
                    rec["correctness"] = "correct"
                    correct += 1
                else:
                    rec["correctness"] = "wrong"
                    wrong += 1
            except Exception as exc:  # noqa: BLE001 - record and continue
                rec["correctness"] = "error"
                rec["error"] = f"{exc.__class__.__name__}: {exc}"
                failed += 1
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            total = correct + wrong + failed
            if total % 10 == 0 or i == len(rows) - 1:
                print(f"  [{total}/{len(rows)}] acc={correct}/{total} "
                      f"({100 * correct / max(1, total):.1f}%) "
                      f"wrong={wrong} failed={failed}", file=sys.stderr)

    total = correct + wrong + failed
    print(json.dumps({
        "mode": args.mode, "model": args.model, "total": total,
        "correct": correct, "wrong": wrong, "failed_or_format": failed,
        "accuracy": round(correct / max(1, total), 4), "out": str(out_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
