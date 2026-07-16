#!/usr/bin/env python3
"""Filter gui-aima bbox.json rows down to icon-like targets — zero annotation.

Heuristic (from GT boxes we already have): icons are SMALL and roughly
SQUARE; text elements are wide and flat. Keep rows where
  * target area fraction of the screen < --max-area-frac (default 0.5%)
  * bbox aspect ratio (w/h) within [--min-ar, --max-ar] (default 0.4..2.5)

Needs image sizes to compute area fraction: reads each row's image header
(fast, no decode). Writes a filtered bbox.json usable as a prepare_zoom_sft_v2
--source.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_guiact_zoom_sft import get_instruction_and_bbox  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-json", required=True)
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--max-area-frac", type=float, default=0.005)
    ap.add_argument("--min-ar", type=float, default=0.4)
    ap.add_argument("--max-ar", type=float, default=2.5)
    ap.add_argument("--limit", type=int, default=0, help="stop after N kept rows (0=all)")
    args = ap.parse_args()

    rows = json.loads(Path(args.in_json).read_text(encoding="utf-8"))
    img_dir = Path(args.image_dir)
    size_cache: dict[str, tuple[int, int]] = {}
    kept, skipped = [], 0
    for row in rows:
        try:
            _, bbox = get_instruction_and_bbox(row)
        except Exception:
            skipped += 1
            continue
        img = row.get("image")
        if img not in size_cache:
            p = img_dir / img
            if not p.exists():
                skipped += 1
                continue
            try:
                with Image.open(p) as im:  # header only, no decode
                    size_cache[img] = im.size
            except Exception:
                skipped += 1
                continue
        w, h = size_cache[img]
        bw, bh = (bbox[2] - bbox[0]) * w, (bbox[3] - bbox[1]) * h
        if bw <= 0 or bh <= 0:
            skipped += 1
            continue
        area_frac = (bw * bh) / (w * h)
        ar = bw / bh
        if area_frac < args.max_area_frac and args.min_ar <= ar <= args.max_ar:
            kept.append(row)
            if args.limit and len(kept) >= args.limit:
                break

    Path(args.out_json).write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
    print(f"kept {len(kept)} icon-like rows (of {len(rows)}, skipped {skipped}) -> {args.out_json}")


if __name__ == "__main__":
    main()
