#!/usr/bin/env python3
"""Build GRPO data for the HARNESS-STAGE tasks (not bare grounding).

Every row is one real stage of the harness loop, with the REAL detector/OCR
candidate evidence in the prompt — exactly what the model sees at inference:

  * task="crop":  round-0 view (full screenshot) + candidates -> the model
    should answer {"action": "crop", "bbox": [...]} that CONTAINS the target
    and meaningfully shrinks the search area. Rule-checkable.
  * task="click": deepest upscaled view + candidates -> {"point_2d": [x, y]}
    inside the GT box. Rule-checkable.

Rows without a candidates-cache hit are SKIPPED (evidence is the point).
Prompts are byte-identical to the harness/SFT ones (prompts.py + evidence.py).

Output rows: {sample_id, task, image, prompt_text, gt_bbox_norm1000, source}
where gt_bbox_norm1000 is the GT box in the [0,1000]-normalized space of the
DISPLAYED view (the same space the model answers in).
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
import evidence  # noqa: E402
from prepare_guiact_zoom_sft import (  # noqa: E402
    TOTAL_ROUNDS,
    box_to_norm1000,
    display_scale_for,
    render_crop,
    get_instruction_and_bbox,
)
from prepare_zoom_sft_v2 import depth_for_target, synth_containing_box, parse_source  # noqa: E402


def build_rows(row: dict[str, Any], index: int, source_name: str,
               image_dir: Path, crops_dir: Path, seed: int,
               cands: list, rng_task: str) -> list[dict[str, Any]]:
    rng = random.Random(seed * 1_000_003 + index)
    instruction, bbox_norm = get_instruction_and_bbox(row)
    image_path = image_dir / row["image"]
    if not image_path.exists():
        return []

    out = []
    with Image.open(image_path) as img:
        img_w, img_h = img.size
        gt_px = [bbox_norm[0] * img_w, bbox_norm[1] * img_h,
                 bbox_norm[2] * img_w, bbox_norm[3] * img_h]
        area_frac = max((gt_px[2] - gt_px[0]) * (gt_px[3] - gt_px[1]), 1.0) / (img_w * img_h)
        depth = depth_for_target(area_frac)
        full_box = [0, 0, img_w, img_h]
        sid = f"{source_name}_ghar_{index:06d}"

        def ev_block(view_box: list[float]) -> str:
            return evidence.candidate_lines(
                cands, [int(v) for v in view_box], display_scale=1.0,
                limit=60, target=instruction, sort_mode="relevance",
            ) or "(none)"

        if rng_task == "crop":
            # Round-0 crop decision on the full screenshot (the stage where
            # v1's error analysis found 43% of SSPro failures).
            if depth == 0:
                return []  # target already large; crop stage not meaningful
            dyn = prompts.crop_dynamic_block(
                task=instruction, target=instruction, img_w=img_w, img_h=img_h,
                crop_box=full_box, display_scale=1.0, round_idx=0,
                total_rounds=TOTAL_ROUNDS, stage_idx=0,
                history_lines="(none)", candidates_block=ev_block(full_box))
            out.append({
                "sample_id": f"{sid}_crop", "task": "crop",
                "image": str(image_path),
                "prompt_text": f"{prompts.CROP_RULES_NORM}\n\n{dyn}",
                "gt_bbox_norm1000": box_to_norm1000([float(v) for v in gt_px], full_box),
                "instruction": instruction, "source": source_name,
            })
        else:
            # Click on the deepest upscaled view, WITH candidates.
            stage_fracs = {0: [], 1: [(0.18, 0.35)], 2: [(0.18, 0.35), (0.22, 0.45)],
                           3: [(0.15, 0.30), (0.20, 0.40), (0.28, 0.50)]}[depth]
            chain = [full_box]
            for fr in stage_fracs:
                chain.append(synth_containing_box(rng, chain[-1], gt_px, fr))
            deepest = chain[-1]
            clk_scale = display_scale_for(deepest, 640, 8.0)
            p = crops_dir / f"{sid}_clk.jpg"
            render_crop(img, deepest, clk_scale, p)
            dyn = prompts.click_dynamic_block(
                task=instruction, target=instruction, img_w=img_w, img_h=img_h,
                crop_box=[int(v) for v in deepest], display_scale=clk_scale,
                candidates_block=ev_block(deepest))
            out.append({
                "sample_id": f"{sid}_click", "task": "click",
                "image": str(p),
                "prompt_text": f"{prompts.CLICK_RULES_NORM}\n\n{dyn}",
                "gt_bbox_norm1000": box_to_norm1000([float(v) for v in gt_px], deepest),
                "instruction": instruction, "source": source_name,
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", required=True, help="name:json:imgdir:n (repeatable)")
    ap.add_argument("--candidates-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--crops-dir", required=True)
    ap.add_argument("--seed", type=int, default=20260712)
    ap.add_argument("--crop-frac", type=float, default=0.5,
                    help="fraction of rows becoming crop-stage tasks (rest click)")
    args = ap.parse_args()

    crops_dir = Path(args.crops_dir)
    crops_dir.mkdir(parents=True, exist_ok=True)
    cdir = Path(args.candidates_dir)

    out_rows: list[dict[str, Any]] = []
    master = random.Random(args.seed)
    for spec in args.source:
        name, json_path, img_dir, n_rows = parse_source(spec)
        cache_path = cdir / f"{name}_candidates.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        master.shuffle(rows)
        rows = rows[:n_rows] if n_rows > 0 else rows
        built = skipped_nocache = skipped_other = 0
        for i, row in enumerate(rows):
            cands = cache.get(row.get("image"))
            if not cands:
                skipped_nocache += 1
                continue
            task = "crop" if master.random() < args.crop_frac else "click"
            try:
                rs = build_rows(row, i, name, img_dir, crops_dir, args.seed, cands, task)
            except Exception:
                rs = []
            if not rs:
                skipped_other += 1
                continue
            out_rows.extend(rs)
            built += len(rs)
        print(f"[{name}] built={built} no_cache={skipped_nocache} other_skip={skipped_other}",
              file=sys.stderr)

    from collections import Counter
    print("task mix:", dict(Counter(r["task"] for r in out_rows)), file=sys.stderr)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_rows, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(out_rows)} harness-stage GRPO rows -> {out_path}")


if __name__ == "__main__":
    main()
