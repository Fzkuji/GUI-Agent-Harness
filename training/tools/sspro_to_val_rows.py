#!/usr/bin/env python3
"""Convert ScreenSpot-Pro annotations into eval_zoom_traj.py's val_rows format.

Reads the harness's sample index (full1581_samples.json — a list of
[annotation_file, row_index] pairs) plus the ScreenSpot-Pro annotations dir,
and writes val_rows.json rows: {source_index, image, instruction, gt_bbox_norm}
with gt_bbox_norm in [0,1] fractions of the full image (same convention as the
GUIAct val rows produced by prepare_guiact_zoom_sft.py).

Example (cluster):
  python sspro_to_val_rows.py \
    --samples ../../benchmarks/screenspot_pro/full1581_samples.json \
    --annotations ~/data/ScreenSpot-Pro/annotations \
    --out ../data/sspro_val_rows.json --shuffle
Then:
  eval_zoom_traj.py --val-rows .../sspro_val_rows.json \
    --image-dir ~/data/ScreenSpot-Pro/images ...
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", required=True, help="full1581_samples.json ([annotation_file, index] pairs)")
    ap.add_argument("--annotations", required=True, help="ScreenSpot-Pro annotations directory")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shuffle", action="store_true", help="shuffle rows (index is app-ordered; shuffle so --num N is representative)")
    ap.add_argument("--seed", type=int, default=20260711)
    args = ap.parse_args()

    ann_dir = Path(args.annotations).expanduser()
    pairs = json.loads(Path(args.samples).expanduser().read_text(encoding="utf-8"))

    cache: dict[str, list] = {}
    rows = []
    for i, (ann_file, idx) in enumerate(pairs):
        if ann_file not in cache:
            cache[ann_file] = json.loads((ann_dir / ann_file).read_text(encoding="utf-8"))
        r = cache[ann_file][idx]
        w, h = r["img_size"]
        x1, y1, x2, y2 = r["bbox"]
        rows.append({
            "source_index": i,
            "sample_id": r.get("id", f"{ann_file}:{idx}"),
            "image": r["img_filename"],
            "instruction": r["instruction"],
            "gt_bbox_norm": [x1 / w, y1 / h, x2 / w, y2 / h],
            "group": r.get("group"),
            "ui_type": r.get("ui_type"),
        })

    if args.shuffle:
        random.Random(args.seed).shuffle(rows)

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
