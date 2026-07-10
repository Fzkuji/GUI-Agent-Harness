#!/usr/bin/env python3
"""Build full-trajectory GUI-Lens zoom SFT data from GUIAct ground-truth boxes.

Upgrades over the old first-crop-only package (qwen3vl8b first_crop_1k):
  1. Full trajectory, not just round 1 — per GUIAct row it emits:
       r0  full image      -> {"action": "crop",  "bbox": stage-1 region}
       r1  stage-1 crop    -> {"action": "crop",  "bbox": stage-2 group}
       r2  stage-2 crop    -> {"action": "final", "bbox": tight target}   (--final-frac)
       clk upscaled final  -> {"action": "click", ..., "point_2d": [x,y]}
       neg decoy crop      -> {"action": "recrop", ...}                   (--recrop-frac)
  2. All supervised coordinates are NORMALIZED [0,1000] integers relative to
     the DISPLAYED image — Qwen3-VL's native grounding convention. The old
     package supervised displayed-crop *pixels*, which fights the base model's
     training distribution and is the prime suspect for its weak results.
  3. Crop boxes are jittered (size, aspect, placement) so the target is NOT
     always centered — otherwise the model learns "answer = center of my crop".
  4. Trajectories are synthesized deterministically from the GT box (seeded
     RNG); no teacher LLM, no manual annotation.

Each round is a SINGLE-TURN sample: the harness runs each zoom round as an
independent LLM call (best.yaml: context_mode=single), so training mirrors
inference. Prompts are imported from gui_harness when available (byte-identical
to inference), else verbatim embedded copies — see prompts.py.

Typical use (cluster paths):
  python prepare_guiact_zoom_sft.py \
    --source-json .../gui-aima-data/guiact_bbox.json \
    --image-dir   .../GUIAct/web_imgs \
    --lf-data-dir .../training/LLaMA-Factory/data
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts  # noqa: E402

TOTAL_ROUNDS = 8  # harness best.yaml iterative_rounds — keeps Round: r/8 realistic


# ═══════════════════════════════════════════
# Geometry helpers
# ═══════════════════════════════════════════

def norm1000(v: float, lo: float, hi: float) -> int:
    """Map original-coordinate v into [0,1000] of the [lo,hi] display window."""
    span = max(hi - lo, 1e-6)
    return max(0, min(1000, int(round((v - lo) / span * 1000))))


def box_to_norm1000(box_px: list[float], crop: list[int]) -> list[int]:
    x1, y1, x2, y2 = box_px
    cx1, cy1, cx2, cy2 = crop
    return [
        norm1000(x1, cx1, cx2), norm1000(y1, cy1, cy2),
        norm1000(x2, cx1, cx2), norm1000(y2, cy1, cy2),
    ]


def synth_containing_box(
    rng: random.Random,
    bounds: list[int],
    gt_px: list[float],
    area_frac_range: tuple[float, float],
    margin_frac: float = 0.06,
    min_w: int = 240,
    min_h: int = 80,
) -> list[int]:
    """A jittered box inside `bounds` fully containing gt_px with a margin.

    Size is drawn as a fraction of the bounds area, aspect jittered around the
    bounds aspect, and placement drawn uniformly over all positions that keep
    the GT box inside with `margin_frac` clearance — the target lands anywhere
    in the crop, not just the center.
    """
    bx1, by1, bx2, by2 = bounds
    bw, bh = bx2 - bx1, by2 - by1
    gx1, gy1, gx2, gy2 = gt_px
    gw, gh = gx2 - gx1, gy2 - gy1

    af = rng.uniform(*area_frac_range)
    aspect = (bw / max(bh, 1)) * rng.uniform(0.8, 1.25)
    cw = math.sqrt(af * bw * bh * aspect)
    ch = cw / aspect

    # Grow until the GT box plus margin fits, then clamp to bounds.
    cw = max(cw, min_w, gw * (1 + 2 * margin_frac) + 8)
    ch = max(ch, min_h, gh * (1 + 2 * margin_frac) + 8)
    cw = min(cw, bw)
    ch = min(ch, bh)

    mx, my = margin_frac * cw, margin_frac * ch
    # Feasible top-left range keeping GT inside with margin.
    lo_x = max(bx1, gx2 + mx - cw)
    hi_x = min(bx2 - cw, gx1 - mx)
    lo_y = max(by1, gy2 + my - ch)
    hi_y = min(by2 - ch, gy1 - my)
    left = rng.uniform(lo_x, hi_x) if lo_x < hi_x else min(max(bx1, gx1 - (cw - gw) / 2), bx2 - cw)
    top = rng.uniform(lo_y, hi_y) if lo_y < hi_y else min(max(by1, gy1 - (ch - gh) / 2), by2 - ch)

    x1 = int(round(max(bx1, left)))
    y1 = int(round(max(by1, top)))
    x2 = int(round(min(bx2, x1 + cw)))
    y2 = int(round(min(by2, y1 + ch)))
    return [x1, y1, max(x2, x1 + 1), max(y2, y1 + 1)]


def synth_decoy_box(
    rng: random.Random,
    img_w: int,
    img_h: int,
    gt_px: list[float],
    area_frac_range: tuple[float, float],
) -> Optional[list[int]]:
    """A crop that does NOT intersect the GT box (recrop negative), or None."""
    for _ in range(25):
        af = rng.uniform(*area_frac_range)
        aspect = (img_w / max(img_h, 1)) * rng.uniform(0.8, 1.25)
        cw = min(img_w, math.sqrt(af * img_w * img_h * aspect))
        ch = min(img_h, cw / aspect)
        x1 = rng.uniform(0, img_w - cw)
        y1 = rng.uniform(0, img_h - ch)
        box = [int(x1), int(y1), int(x1 + cw), int(y1 + ch)]
        gx1, gy1, gx2, gy2 = gt_px
        if box[2] <= gx1 or box[0] >= gx2 or box[3] <= gy1 or box[1] >= gy2:
            return box
    return None


def display_scale_for(crop: list[int], min_short_side: int, max_scale: float) -> float:
    w, h = crop[2] - crop[0], crop[3] - crop[1]
    short = max(1, min(w, h))
    if short >= min_short_side:
        return 1.0  # preserve mode: never downscale
    return min(max_scale, min_short_side / short)


# ═══════════════════════════════════════════
# Rendering & record assembly
# ═══════════════════════════════════════════

def render_crop(
    img: Image.Image, crop: list[int], scale: float, out_path: Path
) -> None:
    region = img.crop(tuple(crop))
    if scale != 1.0:
        region = region.resize(
            (max(1, int(round(region.width * scale))), max(1, int(round(region.height * scale)))),
            Image.LANCZOS,
        )
    region.convert("RGB").save(out_path, "JPEG", quality=92)


def crop_answer(action: str, bbox_norm: Optional[list[int]], visible: str, reasoning: str) -> str:
    return json.dumps(
        {
            "action": action,
            "bbox": bbox_norm if bbox_norm is not None else [0, 0, 1000, 1000],
            "target_visible_element": visible,
            "confidence": 0.9,
            "reasoning": reasoning,
        },
        ensure_ascii=False,
    )


def click_answer(pt_norm: list[int], visible: str) -> str:
    return json.dumps(
        {
            "action": "click",
            "candidate_id": "",
            "x": pt_norm[0],
            "y": pt_norm[1],
            "point_2d": pt_norm,
            "target_visible_element": visible,
            "confidence": 0.9,
            "reasoning": "The upscaled crop shows the requested control; clicking its center.",
        },
        ensure_ascii=False,
    )


def make_messages(rules: str, dynamic: str, image_path: str) -> dict[str, Any]:
    # Cache layout at inference = [rules block][dynamic block][image]; as one
    # training turn that concatenates to rules + blank line + dynamic + image.
    return {
        "messages": [
            {"role": "user", "content": f"{rules}\n\n{dynamic}<image>"},
        ],
        "images": [image_path],
    }


def get_instruction_and_bbox(row: dict[str, Any]) -> tuple[str, list[float]]:
    instruction, bbox = "", None
    for turn in row.get("conversations", []):
        if turn.get("from") == "human":
            instruction = str(turn.get("value", "")).replace("<image>", "").strip()
        elif turn.get("from") == "gpt":
            bbox = turn.get("bbox_gt")
    if not instruction or bbox is None:
        raise ValueError("missing GUIAct instruction or bbox_gt")
    return instruction, [float(x) for x in bbox]


# ═══════════════════════════════════════════
# Per-row trajectory synthesis
# ═══════════════════════════════════════════

def build_row_samples(
    row: dict[str, Any],
    index: int,
    args: argparse.Namespace,
    rng: random.Random,
    crops_dir: Path,
    image_dir: Path,
) -> list[dict[str, Any]]:
    instruction, bbox_norm = get_instruction_and_bbox(row)
    image_path = image_dir / row["image"]
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    with Image.open(image_path) as img:
        img_w, img_h = img.size
        gt_px = [
            bbox_norm[0] * img_w, bbox_norm[1] * img_h,
            bbox_norm[2] * img_w, bbox_norm[3] * img_h,
        ]
        gt_center = [(gt_px[0] + gt_px[2]) / 2, (gt_px[1] + gt_px[3]) / 2]
        sid = f"guiact_zoom_{index:06d}"
        full_box = [0, 0, img_w, img_h]
        samples: list[dict[str, Any]] = []

        # ── stage boxes ──
        stage1 = synth_containing_box(rng, full_box, gt_px, (0.18, 0.35))
        stage2 = synth_containing_box(rng, stage1, gt_px, (0.22, 0.45))

        def common(record_type: str, msg: dict[str, Any]) -> dict[str, Any]:
            return {
                "sample_id": f"{sid}_{record_type}",
                "record_type": record_type,
                **msg,
                "metadata": {
                    "source": "GUIAct",
                    "source_index": index,
                    "image_size": [img_w, img_h],
                    "gt_bbox_norm": bbox_norm,
                },
            }

        # ── r0: full image → stage-1 crop ──
        dyn = prompts.crop_dynamic_block(
            task=instruction, target=instruction, img_w=img_w, img_h=img_h,
            crop_box=full_box, display_scale=1.0,
            round_idx=0, total_rounds=TOTAL_ROUNDS, stage_idx=0,
        )
        samples.append(common("crop_r0", make_messages(
            prompts.CROP_RULES_NORM, dyn, str(image_path),
        ) | {"_answer": crop_answer(
            "crop", box_to_norm1000([float(v) for v in stage1], full_box),
            "target region matching the instruction",
            "Stage-1 region crop keeping the target with surrounding context.",
        )}))

        # ── r1: stage-1 crop → stage-2 crop ──
        s1_scale = display_scale_for(stage1, args.min_short_side, args.max_scale)
        s1_img = crops_dir / f"{sid}_s1.jpg"
        render_crop(img, stage1, s1_scale, s1_img)
        hist1 = f"round 1: action=crop committed crop -> {stage1} (original coordinates)"
        dyn = prompts.crop_dynamic_block(
            task=instruction, target=instruction, img_w=img_w, img_h=img_h,
            crop_box=stage1, display_scale=s1_scale,
            round_idx=1, total_rounds=TOTAL_ROUNDS, stage_idx=1,
            history_lines=hist1,
        )
        samples.append(common("crop_r1", make_messages(
            prompts.CROP_RULES_NORM, dyn, str(s1_img),
        ) | {"_answer": crop_answer(
            "crop", box_to_norm1000([float(v) for v in stage2], stage1),
            "control group containing the target",
            "Stage-2 crop narrowing to the local control group around the target.",
        )}))

        # ── r2: stage-2 crop → action=final (subset) ──
        s2_scale = display_scale_for(stage2, args.min_short_side, args.max_scale)
        s2_img = crops_dir / f"{sid}_s2.jpg"
        render_crop(img, stage2, s2_scale, s2_img)
        if rng.random() < args.final_frac:
            pad_w = max(8.0, (gt_px[2] - gt_px[0]) * 0.4)
            pad_h = max(8.0, (gt_px[3] - gt_px[1]) * 0.4)
            tight = [
                max(stage2[0], gt_px[0] - pad_w), max(stage2[1], gt_px[1] - pad_h),
                min(stage2[2], gt_px[2] + pad_w), min(stage2[3], gt_px[3] + pad_h),
            ]
            hist2 = (
                hist1 + "\n"
                + f"round 2: action=crop committed crop -> {stage2} (original coordinates)"
            )
            dyn = prompts.crop_dynamic_block(
                task=instruction, target=instruction, img_w=img_w, img_h=img_h,
                crop_box=stage2, display_scale=s2_scale,
                round_idx=2, total_rounds=TOTAL_ROUNDS, stage_idx=2,
                history_lines=hist2,
            )
            samples.append(common("crop_final", make_messages(
                prompts.CROP_RULES_NORM, dyn, str(s2_img),
            ) | {"_answer": crop_answer(
                "final", box_to_norm1000(tight, stage2),
                "the requested clickable control",
                "The target is clearly identifiable; further cropping risks losing context.",
            )}))

        # ── click: upscaled stage-2 crop → point ──
        clk_scale = display_scale_for(stage2, args.final_min_short_side, args.final_max_scale)
        clk_img = crops_dir / f"{sid}_clk.jpg"
        render_crop(img, stage2, clk_scale, clk_img)
        pt = [
            norm1000(gt_center[0], stage2[0], stage2[2]),
            norm1000(gt_center[1], stage2[1], stage2[3]),
        ]
        dyn = prompts.click_dynamic_block(
            task=instruction, target=instruction, img_w=img_w, img_h=img_h,
            crop_box=stage2, display_scale=clk_scale,
        )
        samples.append(common("click", make_messages(
            prompts.CLICK_RULES_NORM, dyn, str(clk_img),
        ) | {"_answer": click_answer(pt, "the requested clickable control")}))

        # ── recrop negative: decoy crop missing the target (subset) ──
        if rng.random() < args.recrop_frac:
            decoy = synth_decoy_box(rng, img_w, img_h, gt_px, (0.10, 0.25))
            if decoy is not None:
                d_scale = display_scale_for(decoy, args.min_short_side, args.max_scale)
                d_img = crops_dir / f"{sid}_neg.jpg"
                render_crop(img, decoy, d_scale, d_img)
                dyn = prompts.crop_dynamic_block(
                    task=instruction, target=instruction, img_w=img_w, img_h=img_h,
                    crop_box=decoy, display_scale=d_scale,
                    round_idx=1, total_rounds=TOTAL_ROUNDS, stage_idx=1,
                    history_lines=f"round 1: action=crop committed crop -> {decoy} (original coordinates)",
                )
                samples.append(common("recrop_neg", make_messages(
                    prompts.CROP_RULES_NORM, dyn, str(d_img),
                ) | {"_answer": crop_answer(
                    "recrop", None,
                    "",
                    "The requested target is not visible in this crop; backing out to a wider view.",
                )}))

    # Move _answer into the assistant turn.
    for s in samples:
        s["messages"].append({"role": "assistant", "content": s.pop("_answer")})
    return samples


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def update_dataset_info(lf_data_dir: Path, dataset_key: str, file_name: str) -> None:
    info_path = lf_data_dir / "dataset_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    info[dataset_key] = {
        "file_name": file_name,
        "formatting": "sharegpt",
        "columns": {"messages": "messages", "images": "images"},
        "tags": {
            "role_tag": "role",
            "content_tag": "content",
            "user_tag": "user",
            "assistant_tag": "assistant",
        },
    }
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-json", required=True, help="guiact_bbox.json (gui-aima packaging)")
    ap.add_argument("--image-dir", required=True, help="GUIAct web_imgs directory")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "data" / "guiact_zoom_sft"))
    ap.add_argument("--lf-data-dir", default="", help="LLaMA-Factory/data; if set, write train JSON + dataset_info there")
    ap.add_argument("--dataset-key", default="guiact_zoom_sft")
    ap.add_argument("--num-samples", type=int, default=0, help="0 = all rows")
    ap.add_argument("--val-frac", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--final-frac", type=float, default=0.5)
    ap.add_argument("--recrop-frac", type=float, default=0.15)
    ap.add_argument("--min-short-side", type=int, default=512)
    ap.add_argument("--max-scale", type=float, default=5.0)
    ap.add_argument("--final-min-short-side", type=int, default=640)
    ap.add_argument("--final-max-scale", type=float, default=8.0)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    image_dir = Path(args.image_dir)

    rows = json.loads(Path(args.source_json).read_text(encoding="utf-8"))
    if args.num_samples > 0:
        rows = rows[: args.num_samples]

    rng = random.Random(args.seed)
    n_val = max(1, int(len(rows) * args.val_frac)) if args.val_frac > 0 else 0
    val_indices = set(rng.sample(range(len(rows)), n_val)) if n_val else set()

    records: list[dict[str, Any]] = []
    val_rows: list[dict[str, Any]] = []
    skipped = 0
    for idx, row in enumerate(rows):
        if idx in val_indices:
            try:
                instruction, bbox_norm = get_instruction_and_bbox(row)
                val_rows.append({
                    "source_index": idx,
                    "image": row["image"],
                    "instruction": instruction,
                    "gt_bbox_norm": bbox_norm,
                })
            except (ValueError, KeyError):
                skipped += 1
            continue
        try:
            records.extend(build_row_samples(row, idx, args, rng, crops_dir, image_dir))
        except (ValueError, KeyError, FileNotFoundError, OSError) as exc:
            skipped += 1
            print(f"  skip row {idx}: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        if idx and idx % 500 == 0:
            print(f"  ... {idx}/{len(rows)} rows, {len(records)} samples", file=sys.stderr)

    train_json = out_dir / f"{args.dataset_key}_train.json"
    train_json.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "val_rows.json").write_text(
        json.dumps(val_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.lf_data_dir:
        lf_dir = Path(args.lf_data_dir)
        lf_dir.mkdir(parents=True, exist_ok=True)
        (lf_dir / train_json.name).write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        update_dataset_info(lf_dir, args.dataset_key, train_json.name)

    counts = Counter(r["record_type"] for r in records)
    summary = {
        "dataset_key": args.dataset_key,
        "prompt_source": prompts.PROMPT_SOURCE,
        "coordinate_convention": "normalized [0,1000] of displayed image (Qwen3-VL native)",
        "source_rows": len(rows),
        "train_rows": len(rows) - len(val_rows) - skipped,
        "val_rows": len(val_rows),
        "skipped_rows": skipped,
        "total_records": len(records),
        "record_type_counts": dict(counts),
        "seed": args.seed,
        "train_json": str(train_json),
    }
    (out_dir / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
