#!/usr/bin/env python3
"""Build a slice manifest for run_sspro_slice_arm.py matching sspro_val_rows.

Applies the SAME shuffle as sspro_to_val_rows.py (seed 20260711 over the
full1581 [annotation_file, index] pairs) and takes the first N, so the full
harness runs exactly the rows that eval_zoom_traj.py scored with --num N —
the two protocols stay comparable sample-for-sample.

Output format (what run_sspro_slice_arm.py expects):
  {"samples": [[ann, idx], ...], "index_args": {ann: "i1,i2,..."}, "total": N}

Example:
  python training/tools/make_sspro_manifest.py --num 300 \
    --out benchmarks/screenspot_pro/runs/sspro_slice/sspro300_v3.json
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", default=str(REPO_ROOT / "benchmarks/screenspot_pro/full1581_samples.json"))
    ap.add_argument("--num", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260711, help="must match sspro_to_val_rows.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--val-rows", default="",
                    help="optional sspro_val_rows.json to cross-check row alignment (needs --annotations)")
    ap.add_argument("--annotations", default="", help="ScreenSpot-Pro annotations dir for the cross-check")
    args = ap.parse_args()

    pairs = json.loads(Path(args.samples).expanduser().read_text(encoding="utf-8"))
    random.Random(args.seed).shuffle(pairs)  # same permutation as the val rows
    subset = pairs[: args.num] if args.num > 0 else pairs

    if args.val_rows and args.annotations:
        rows = json.loads(Path(args.val_rows).expanduser().read_text(encoding="utf-8"))
        ann_dir = Path(args.annotations).expanduser()
        cache: dict[str, list] = {}
        for i, (ann, idx) in enumerate(subset):
            if ann not in cache:
                cache[ann] = json.loads((ann_dir / ann).read_text(encoding="utf-8"))
            want = rows[i].get("sample_id", f"{ann}:{idx}")
            got = cache[ann][idx].get("id", f"{ann}:{idx}")
            if want != got:
                raise SystemExit(f"row {i} mismatch: manifest {got} vs val_rows {want}")
        print(f"cross-check OK: {len(subset)} rows align with {args.val_rows}")

    groups: dict[str, list[int]] = defaultdict(list)
    for ann, idx in subset:
        groups[ann].append(idx)
    manifest = {
        "samples": subset,
        "index_args": {ann: ",".join(str(i) for i in sorted(idxs))
                       for ann, idxs in sorted(groups.items())},
        "total": len(subset),
        "seed": args.seed,
    }
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(subset)} samples across {len(groups)} annotations -> {out}")


if __name__ == "__main__":
    main()
