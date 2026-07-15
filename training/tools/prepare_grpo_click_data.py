#!/usr/bin/env python3
"""Build a click-only GRPO dataset: prompt (rules + dynamic text + crop image)
with NO gold answer, plus the GT bbox in the SAME [0,1000]-normalized space
the model's point_2d output refers to, for the reward function to score.

Reuses the exact same "deepest view" construction as prepare_zoom_sft_v2.py's
build_row_samples_v2 (variable depth by target area, synthesized crop chain,
upscaled final click view) so this GRPO task matches what the SFT click stage
— and the real harness click stage — actually sees. Sources use the gui-aima
packaging (same --source name:json:imgdir:n spec as prepare_zoom_sft_v2.py).

Output: a JSON list of {"image": path, "prompt_text": str, "gt_bbox_norm1000": [x1,y1,x2,y2]}
consumed by train_grpo_click.py. Also writes crop images to --crops-dir.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts  # noqa: E402
from prepare_guiact_zoom_sft import (  # noqa: E402
    TOTAL_ROUNDS,
    box_to_norm1000,
    display_scale_for,
    render_crop,
    get_instruction_and_bbox,
)
from prepare_zoom_sft_v2 import depth_for_target, synth_containing_box, parse_source  # noqa: E402


def build_click_row(row: dict[str, Any], index: int, source_name: str,
                    image_dir: Path, crops_dir: Path, seed: int,
                    min_short_side: int, max_scale: float,
                    final_min_short_side: int, final_max_scale: float) -> dict[str, Any] | None:
    rng = random.Random(seed * 1_000_003 + index)
    instruction, bbox_norm = get_instruction_and_bbox(row)
    image_path = image_dir / row["image"]
    if not image_path.exists():
        return None

    with Image.open(image_path) as img:
        img_w, img_h = img.size
        gt_px = [bbox_norm[0] * img_w, bbox_norm[1] * img_h,
                 bbox_norm[2] * img_w, bbox_norm[3] * img_h]
        area_frac = max((gt_px[2] - gt_px[0]) * (gt_px[3] - gt_px[1]), 1.0) / (img_w * img_h)
        depth = depth_for_target(area_frac)
        full_box = [0, 0, img_w, img_h]

        stage_fracs = {0: [], 1: [(0.18, 0.35)], 2: [(0.18, 0.35), (0.22, 0.45)],
                       3: [(0.15, 0.30), (0.20, 0.40), (0.28, 0.50)]}[depth]
        chain = [full_box]
        for fr in stage_fracs:
            chain.append(synth_containing_box(rng, chain[-1], gt_px, fr))
        deepest = chain[-1]

        clk_scale = display_scale_for(deepest, final_min_short_side, final_max_scale)
        sid = f"{source_name}_grpo_{index:06d}"
        p = crops_dir / f"{sid}_clk.jpg"
        render_crop(img, deepest, clk_scale, p)

        gt_bbox_view = box_to_norm1000([float(v) for v in gt_px], deepest)
        dyn = prompts.click_dynamic_block(
            task=instruction, target=instruction, img_w=img_w, img_h=img_h,
            crop_box=[int(v) for v in deepest], display_scale=clk_scale,
            candidates_block="(none)")
        prompt_text = f"{prompts.CLICK_RULES_NORM}\n\n{dyn}"
        return {
            "sample_id": sid, "image": str(p), "prompt_text": prompt_text,
            "instruction": instruction, "gt_bbox_norm1000": gt_bbox_view,
            "source": source_name, "depth": depth,
        }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", required=True, help="name:json:imgdir:n (repeatable)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--crops-dir", required=True)
    ap.add_argument("--seed", type=int, default=20260712)
    ap.add_argument("--min-short-side", type=int, default=512)
    ap.add_argument("--max-scale", type=float, default=5.0)
    ap.add_argument("--final-min-short-side", type=int, default=640)
    ap.add_argument("--final-max-scale", type=float, default=8.0)
    args = ap.parse_args()

    crops_dir = Path(args.crops_dir)
    crops_dir.mkdir(parents=True, exist_ok=True)

    out_rows: list[dict[str, Any]] = []
    master = random.Random(args.seed)
    for spec in args.source:
        name, json_path, img_dir, n_rows = parse_source(spec)
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        master.shuffle(rows)
        rows = rows[:n_rows] if n_rows > 0 else rows
        done = skipped = 0
        for i, row in enumerate(rows):
            try:
                r = build_click_row(row, i, name, img_dir, crops_dir, args.seed,
                                    args.min_short_side, args.max_scale,
                                    args.final_min_short_side, args.final_max_scale)
            except Exception:
                r = None
            if r is None:
                skipped += 1
                continue
            out_rows.append(r)
            done += 1
        print(f"[{name}] {done} rows built, {skipped} skipped", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_rows, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(out_rows)} GRPO click rows -> {out_path}")


if __name__ == "__main__":
    main()
