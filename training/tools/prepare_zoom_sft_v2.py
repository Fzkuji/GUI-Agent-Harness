#!/usr/bin/env python3
"""v2 zoom-SFT data synthesis — multi-source, variable-depth, realistic negatives.

Driven by the 300-sample SSPro error analysis of the v1 pilot (61.0%):
  * 43% of failures lost the target at the FIRST crop (tiny targets invisible
    at the capped input resolution)  -> variable trajectory depth: tiny targets
    get 3 crop rounds, large targets learn to stop early (action=final on the
    first view), paired with a higher image_max_pixels in the v2 train config.
  * icon accuracy 31.8% vs text 77.9% -> mix icon-heavy sources (Wave-UI,
    UGround) alongside GUIAct.
  * recrop fired 5/300 despite 70 lost-target cases -> negatives are now
    PLAUSIBLE wrong regions (a sibling region near the target, not a random
    empty decoy), teaching "this looks right but the target is not here".
  * rigid 2-crop rhythm (300/300 trajectories identical) -> depth varies with
    target size, so the model learns to adapt, not to count.

Sources use the gui-aima packaging (conversations + normalized bbox_gt).
Sample spec: --source name:json_path:image_dir:num_rows  (repeatable)

Example (cluster):
  python prepare_zoom_sft_v2.py \
    --source guiact:$G/guiact_bbox.json:$G/GUIAct/web_imgs:8000 \
    --source waveui:$G/wave_ui_bbox.json:$G/Wave-UI/images_fixed:8000 \
    --source uground:$G/uground_bbox_single_60k.json:$G/Uground/images:4000 \
    --lf-data-dir .../LLaMA-Factory/data --dataset-key zoom_sft_v2 --workers 8
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Optional

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts  # noqa: E402
import evidence  # noqa: E402
from prepare_guiact_zoom_sft import (  # noqa: E402
    TOTAL_ROUNDS,
    norm1000,
    box_to_norm1000,
    synth_containing_box,
    synth_decoy_box,
    display_scale_for,
    render_crop,
    crop_answer,
    click_answer,
    make_messages,
    get_instruction_and_bbox,
    update_dataset_info,
)


# ═══════════════════════════════════════════
# v2: depth policy + plausible negatives
# ═══════════════════════════════════════════

def depth_for_target(area_frac: float) -> int:
    """Crop rounds before final/click, by target area fraction of the image.

    tiny targets need more zoom; large targets should stop early. Derived from
    the v1 error analysis: wrong samples' median target area was 0.018% vs
    0.065% for correct ones.
    """
    if area_frac < 0.0005:   # < 0.05% of the screen — SSPro-style tiny
        return 3
    if area_frac < 0.005:    # < 0.5%
        return 2
    if area_frac < 0.03:     # < 3%
        return 1
    return 0                 # big and obvious — teach "final immediately"


def synth_sibling_decoy(
    rng: random.Random,
    parent: list[int],
    gt_px: list[float],
    img_w: int,
    img_h: int,
) -> Optional[list[int]]:
    """A PLAUSIBLE wrong crop: same size class as a correct next crop, placed
    beside the target inside the parent view so it looks like a reasonable
    region choice — but the GT center is outside. Mimics the v1 failure mode
    (model confidently zooms into the wrong sibling region)."""
    px1, py1, px2, py2 = parent
    pw, ph = px2 - px1, py2 - py1
    gcx = (gt_px[0] + gt_px[2]) / 2
    gcy = (gt_px[1] + gt_px[3]) / 2
    for _ in range(30):
        af = rng.uniform(0.2, 0.45)
        aspect = (pw / max(ph, 1)) * rng.uniform(0.8, 1.25)
        cw = min(pw, (af * pw * ph * aspect) ** 0.5)
        ch = min(ph, cw / aspect)
        # place adjacent to the target: offset the crop center 0.6-1.5 crop
        # sizes away from the GT center, along a random direction
        ang = rng.uniform(0, 6.28318)
        import math
        dx = math.cos(ang) * cw * rng.uniform(0.6, 1.5)
        dy = math.sin(ang) * ch * rng.uniform(0.6, 1.5)
        x1 = max(px1, min(px2 - cw, gcx + dx - cw / 2))
        y1 = max(py1, min(py2 - ch, gcy + dy - ch / 2))
        box = [int(x1), int(y1), int(x1 + cw), int(y1 + ch)]
        if not (box[0] <= gcx <= box[2] and box[1] <= gcy <= box[3]):
            return box
    return None


def build_row_samples_v2(
    row: dict[str, Any],
    index: int,
    source_name: str,
    image_dir: Path,
    cfg: dict[str, Any],
    cands: Optional[list[dict]] = None,
) -> list[dict[str, Any]]:
    rng = random.Random(cfg["seed"] * 1_000_003 + index)  # per-row determinism (parallel-safe)
    crops_dir = Path(cfg["crops_dir"])

    instruction, bbox_norm = get_instruction_and_bbox(row)
    image_path = image_dir / row["image"]
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    # v3: real detector/OCR evidence in a fraction of rows (TRAINING_PLAN:
    # candidates are reference, not ground truth — the rest train evidence-free
    # so the model keeps standalone grounding).
    use_evidence = bool(cands) and rng.random() < cfg.get("evidence_frac", 0.0)

    def evidence_block(view_box: list[int]) -> str:
        if not use_evidence:
            return "(none)"
        return evidence.candidate_lines(
            cands, [int(v) for v in view_box], display_scale=1.0,
            limit=60, target=instruction, sort_mode="relevance",
        ) or "(none)"

    samples: list[dict[str, Any]] = []
    with Image.open(image_path) as img:
        img_w, img_h = img.size
        gt_px = [bbox_norm[0] * img_w, bbox_norm[1] * img_h,
                 bbox_norm[2] * img_w, bbox_norm[3] * img_h]
        gt_center = [(gt_px[0] + gt_px[2]) / 2, (gt_px[1] + gt_px[3]) / 2]
        area_frac = max((gt_px[2] - gt_px[0]) * (gt_px[3] - gt_px[1]), 1.0) / (img_w * img_h)
        depth = depth_for_target(area_frac)
        sid = f"{source_name}_v2_{index:06d}"
        full_box = [0, 0, img_w, img_h]

        def common(rt: str, msg: dict[str, Any]) -> dict[str, Any]:
            return {
                "sample_id": f"{sid}_{rt}", "record_type": rt, **msg,
                "metadata": {"source": source_name, "source_index": index,
                             "image_size": [img_w, img_h], "gt_bbox_norm": bbox_norm,
                             "depth": depth, "evidence": use_evidence},
            }

        # ── synthesize the committed crop chain ──
        # per-round area fractions of the parent, shrinking with depth
        stage_fracs = {0: [], 1: [(0.18, 0.35)], 2: [(0.18, 0.35), (0.22, 0.45)],
                       3: [(0.15, 0.30), (0.20, 0.40), (0.28, 0.50)]}[depth]
        chain = [full_box]
        for fr in stage_fracs:
            chain.append(synth_containing_box(rng, chain[-1], gt_px, fr))

        # ── crop-round samples: view chain[i] -> answer crop chain[i+1] ──
        hist_lines: list[str] = []
        for i in range(depth):
            view, nxt = chain[i], chain[i + 1]
            if i == 0:
                view_img = str(image_path)
                scale = 1.0
            else:
                scale = display_scale_for(view, cfg["min_short_side"], cfg["max_scale"])
                p = crops_dir / f"{sid}_s{i}.jpg"
                render_crop(img, view, scale, p)
                view_img = str(p)
            dyn = prompts.crop_dynamic_block(
                task=instruction, target=instruction, img_w=img_w, img_h=img_h,
                crop_box=view, display_scale=scale, round_idx=i,
                total_rounds=TOTAL_ROUNDS, stage_idx=min(i, 2),
                history_lines="\n".join(hist_lines) or "(none)",
                candidates_block=evidence_block(view))
            samples.append(common(f"crop_r{i}", make_messages(
                prompts.CROP_RULES_NORM, dyn, view_img,
            ) | {"_answer": crop_answer(
                "crop", box_to_norm1000([float(v) for v in nxt], view),
                "target region matching the instruction",
                "Crop keeps the target with enough surrounding context for the next round.")}))
            hist_lines.append(
                f"round {i + 1}: action=crop committed crop -> {nxt} (original coordinates)")

        deepest = chain[-1]

        # ── final-decision sample on the deepest view ──
        if rng.random() < cfg["final_frac"]:
            d_scale = (1.0 if depth == 0 else
                       display_scale_for(deepest, cfg["min_short_side"], cfg["max_scale"]))
            if depth == 0:
                d_img = str(image_path)
            else:
                p = crops_dir / f"{sid}_sf.jpg"
                render_crop(img, deepest, d_scale, p)
                d_img = str(p)
            pad_w = max(8.0, (gt_px[2] - gt_px[0]) * 0.4)
            pad_h = max(8.0, (gt_px[3] - gt_px[1]) * 0.4)
            tight = [max(deepest[0], gt_px[0] - pad_w), max(deepest[1], gt_px[1] - pad_h),
                     min(deepest[2], gt_px[2] + pad_w), min(deepest[3], gt_px[3] + pad_h)]
            dyn = prompts.crop_dynamic_block(
                task=instruction, target=instruction, img_w=img_w, img_h=img_h,
                crop_box=deepest, display_scale=d_scale, round_idx=depth,
                total_rounds=TOTAL_ROUNDS, stage_idx=min(depth, 2),
                history_lines="\n".join(hist_lines) or "(none)",
                candidates_block=evidence_block(deepest))
            samples.append(common("crop_final", make_messages(
                prompts.CROP_RULES_NORM, dyn, d_img,
            ) | {"_answer": crop_answer(
                "final", box_to_norm1000(tight, deepest),
                "the requested clickable control",
                "The target is clearly identifiable; further cropping risks losing context.")}))

        # ── click sample on the (upscaled) deepest view ──
        clk_scale = display_scale_for(deepest, cfg["final_min_short_side"], cfg["final_max_scale"])
        p = crops_dir / f"{sid}_clk.jpg"
        render_crop(img, deepest, clk_scale, p)
        pt = [norm1000(gt_center[0], deepest[0], deepest[2]),
              norm1000(gt_center[1], deepest[1], deepest[3])]
        dyn = prompts.click_dynamic_block(
            task=instruction, target=instruction, img_w=img_w, img_h=img_h,
            crop_box=deepest, display_scale=clk_scale,
            candidates_block=evidence_block(deepest))
        samples.append(common("click", make_messages(
            prompts.CLICK_RULES_NORM, dyn, str(p),
        ) | {"_answer": click_answer(pt, "the requested clickable control")}))

        # ── plausible-negative recrop sample ──
        if depth >= 1 and rng.random() < cfg["recrop_frac"]:
            parent = chain[-2] if depth >= 1 else full_box
            decoy = synth_sibling_decoy(rng, parent, gt_px, img_w, img_h) or \
                synth_decoy_box(rng, img_w, img_h, gt_px, (0.10, 0.25))
            if decoy is not None:
                d_scale = display_scale_for(decoy, cfg["min_short_side"], cfg["max_scale"])
                p = crops_dir / f"{sid}_neg.jpg"
                render_crop(img, decoy, d_scale, p)
                dyn = prompts.crop_dynamic_block(
                    task=instruction, target=instruction, img_w=img_w, img_h=img_h,
                    crop_box=decoy, display_scale=d_scale, round_idx=depth,
                    total_rounds=TOTAL_ROUNDS, stage_idx=min(depth, 2),
                    history_lines="\n".join(
                        hist_lines[:-1]
                        + [f"round {depth}: action=crop committed crop -> {decoy} (original coordinates)"]
                    ) or "(none)",
                    candidates_block=evidence_block(decoy))
                samples.append(common("recrop_neg", make_messages(
                    prompts.CROP_RULES_NORM, dyn, str(p),
                ) | {"_answer": crop_answer(
                    "recrop", None, "",
                    "This region looked plausible but the requested target is not "
                    "inside it; backing out to a wider view.")}))

    for s in samples:
        s["messages"].append({"role": "assistant", "content": s.pop("_answer")})
    return samples


# ═══════════════════════════════════════════
# Worker + main
# ═══════════════════════════════════════════

_WORK: dict[str, Any] = {}


def _init_worker(cfg: dict[str, Any]) -> None:
    _WORK["cfg"] = cfg


def _process_one(job: tuple[str, str, dict[str, Any], int, Optional[list]]) -> tuple[str, list, Optional[str]]:
    source_name, image_dir, row, index, cands = job
    try:
        out = build_row_samples_v2(row, index, source_name, Path(image_dir), _WORK["cfg"], cands)
        return source_name, out, None
    except Exception as exc:  # noqa: BLE001 - record and continue
        return source_name, [], f"{exc.__class__.__name__}: {exc}"


def parse_source(spec: str) -> tuple[str, Path, Path, int]:
    # "name|json|imgdir|n" (works with Windows drive letters) or POSIX "name:json:imgdir:n"
    if "|" in spec:
        name, json_path, img_dir, n = spec.split("|")
    else:
        head, n = spec.rsplit(":", 1)
        name, rest = head.split(":", 1)
        json_path, img_dir = rest.rsplit(":", 1)
    return name, Path(json_path).expanduser(), Path(img_dir).expanduser(), int(n)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", required=True,
                    help="name:json_path:image_dir:num_rows (repeatable)")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "data" / "zoom_sft_v2"))
    ap.add_argument("--lf-data-dir", default="")
    ap.add_argument("--dataset-key", default="zoom_sft_v2")
    ap.add_argument("--val-frac", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=20260712)
    ap.add_argument("--final-frac", type=float, default=0.5)
    ap.add_argument("--recrop-frac", type=float, default=0.25)
    ap.add_argument("--candidates-dir", default="",
                    help="precompute_candidates.py output dir; empty = no evidence (v2 behavior)")
    ap.add_argument("--evidence-frac", type=float, default=0.5,
                    help="fraction of rows whose samples include the detector/OCR evidence block")
    ap.add_argument("--min-short-side", type=int, default=512)
    ap.add_argument("--max-scale", type=float, default=5.0)
    ap.add_argument("--final-min-short-side", type=int, default=640)
    ap.add_argument("--final-max-scale", type=float, default=8.0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    cfg = {k: getattr(args, k.replace("-", "_")) for k in
           ("seed", "final_frac", "recrop_frac", "min_short_side", "max_scale",
            "final_min_short_side", "final_max_scale", "evidence_frac")}
    cfg["crops_dir"] = str(crops_dir)

    master = random.Random(args.seed)
    jobs: list[tuple[str, str, dict, int, Optional[list]]] = []
    val_rows: list[dict] = []
    src_stats: dict[str, int] = {}
    ev_rows = 0
    for spec in args.source:
        name, json_path, img_dir, n_rows = parse_source(spec)
        cand_cache: dict[str, list] = {}
        if args.candidates_dir:
            cand_path = Path(args.candidates_dir).expanduser() / f"{name}_candidates.json"
            if cand_path.exists():
                cand_cache = json.loads(cand_path.read_text(encoding="utf-8"))
                print(f"[{name}] candidates cache: {len(cand_cache)} images", file=sys.stderr)
            else:
                print(f"[{name}] WARNING: no candidates cache at {cand_path}", file=sys.stderr)
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        master.shuffle(rows)
        rows = rows[:n_rows] if n_rows > 0 else rows
        n_val = max(1, int(len(rows) * args.val_frac)) if args.val_frac > 0 else 0
        for i, row in enumerate(rows):
            if i < n_val:
                try:
                    instruction, bbox_norm = get_instruction_and_bbox(row)
                    val_rows.append({"source": name, "source_index": i, "image": row["image"],
                                     "image_dir": str(img_dir), "instruction": instruction,
                                     "gt_bbox_norm": bbox_norm})
                except (ValueError, KeyError):
                    pass
            else:
                rc = cand_cache.get(row.get("image", "")) or None
                ev_rows += 1 if rc else 0
                jobs.append((name, str(img_dir), row, i, rc))
        src_stats[name] = len(rows)

    print(f"sources: {src_stats}; train jobs: {len(jobs)}; val rows: {len(val_rows)}",
          file=sys.stderr)

    records: list[dict] = []
    skipped: Counter = Counter()
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker,
                             initargs=(cfg,)) as ex:
        for source_name, out, err in ex.map(_process_one, jobs, chunksize=16):
            done += 1
            if err:
                skipped[source_name] += 1
            else:
                records.extend(out)
            if done % 1000 == 0:
                print(f"  ... {done}/{len(jobs)} rows, {len(records)} samples",
                      file=sys.stderr)

    train_json = out_dir / f"{args.dataset_key}_train.json"
    train_json.write_text(json.dumps(records, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "val_rows.json").write_text(
        json.dumps(val_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.lf_data_dir:
        lf_dir = Path(args.lf_data_dir).expanduser()
        lf_dir.mkdir(parents=True, exist_ok=True)
        (lf_dir / train_json.name).write_text(
            json.dumps(records, ensure_ascii=False) + "\n", encoding="utf-8")
        update_dataset_info(lf_dir, args.dataset_key, train_json.name)

    summary = {
        "dataset_key": args.dataset_key,
        "prompt_source": prompts.PROMPT_SOURCE,
        "sources": src_stats,
        "skipped_rows": dict(skipped),
        "val_rows": len(val_rows),
        "total_records": len(records),
        "record_type_counts": dict(Counter(r["record_type"] for r in records)),
        "depth_distribution": dict(Counter(r["metadata"]["depth"] for r in records
                                           if r["record_type"] == "click")),
        "evidence": {
            "rows_with_cache": ev_rows,
            "evidence_frac": args.evidence_frac,
            "records_with_evidence": sum(1 for r in records if r["metadata"].get("evidence")),
        },
        "seed": args.seed,
        "train_json": str(train_json),
    }
    (out_dir / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
