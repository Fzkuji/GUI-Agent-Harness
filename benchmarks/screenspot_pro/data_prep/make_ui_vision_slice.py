#!/usr/bin/env python3
"""Build a stratified UI-Vision slice for locator-pipeline validation runs.

Why this exists: the recorded UI-Vision full run (results/ui_vision_gpt_5_5,
68.64%) never went through the iterative-zoom locator — every row came from
the single-shot Phase-3 path. Before paying for a full 5479-sample re-run we
validate the routed pipeline on a stratified slice and compare against the
SAME sample ids in the old results, so the delta is row-controlled.

Outputs (under --out-dir):
  * slice_manifest.json — seed, per-split indexes, sample ids, and the old
    run's accuracy on exactly these ids (the row-controlled baseline)
  * per-split index strings ready for run_screenspot_pro.py --indexes
  * downloads the slice's raw images into data_ui_vision/raw_images/

Usage:
  python make_ui_vision_slice.py --size 60          # pilot
  python make_ui_vision_slice.py --size 300         # main slice (same seed
                                                    # ⇒ pilot is a subset)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from prepare_gui_grounding_datasets import (  # noqa: E402
    UI_VISION_REPO,
    curl_download,
    image_file_is_valid,
    repo_url,
)

SPLITS = ("basic", "functional", "spatial")
DATA_DIR = HERE / "data_ui_vision"
OLD_RESULTS = HERE.parent / "ui_vision" / "results" / "gpt-5.5" / "results.jsonl"


def stratified_indexes(sizes: dict[str, int], total: int, seed: int) -> dict[str, list[int]]:
    """Proportionally allocate ``total`` across splits, then sample WITHOUT
    replacement with one seeded RNG per split (so a bigger --size with the
    same seed yields a superset of a smaller one)."""
    grand = sum(sizes.values())
    alloc = {s: max(1, round(total * n / grand)) for s, n in sizes.items()}
    # Rounding drift → trim/pad against the largest split.
    drift = sum(alloc.values()) - total
    biggest = max(alloc, key=lambda s: alloc[s])
    alloc[biggest] -= drift
    out: dict[str, list[int]] = {}
    for split, n in alloc.items():
        rng = random.Random(f"{seed}:{split}")
        pool = list(range(sizes[split]))
        rng.shuffle(pool)
        out[split] = sorted(pool[:n])
    return out


def old_run_baseline(ids: set[str]) -> dict:
    """Accuracy of the recorded single-shot run on exactly these ids."""
    if not OLD_RESULTS.exists():
        return {"available": False}
    correct = wrong = 0
    per_split = {s: [0, 0] for s in SPLITS}
    for line in OLD_RESULTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sid = row.get("sample_id", "")
        if sid not in ids:
            continue
        ok = row.get("correctness") == "correct"
        correct += ok
        wrong += not ok
        for s in SPLITS:
            if sid.startswith(f"ui_vision_{s}_"):
                per_split[s][0] += ok
                per_split[s][1] += 1
    n = correct + wrong
    return {
        "available": True,
        "matched": n,
        "correct": correct,
        "accuracy": round(correct / n, 4) if n else None,
        "per_split": {
            s: {"correct": c, "n": t, "accuracy": round(c / t, 4) if t else None}
            for s, (c, t) in per_split.items()
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260610)
    ap.add_argument("--out-dir", default=str(HERE / "runs" / "ui_vision_slice"))
    ap.add_argument("--image-workers", type=int, default=8)
    ap.add_argument("--skip-images", action="store_true")
    args = ap.parse_args()

    ann_dir = DATA_DIR / "annotations"
    samples_by_split: dict[str, list[dict]] = {}
    for split in SPLITS:
        path = ann_dir / f"ui_vision_{split}.json"
        samples_by_split[split] = json.loads(path.read_text(encoding="utf-8"))

    sizes = {s: len(rows) for s, rows in samples_by_split.items()}
    chosen = stratified_indexes(sizes, args.size, args.seed)

    ids: set[str] = set()
    images: set[str] = set()
    for split, idxs in chosen.items():
        rows = samples_by_split[split]
        for i in idxs:
            ids.add(rows[i]["id"])
            images.add(rows[i]["raw_image_path"])

    manifest = {
        "seed": args.seed,
        "size": args.size,
        "split_sizes": sizes,
        "indexes": {s: chosen[s] for s in SPLITS},
        "index_args": {
            f"ui_vision_{s}.json": ",".join(str(i) for i in chosen[s]) for s in SPLITS
        },
        "sample_ids": sorted(ids),
        "unique_images": len(images),
        "old_run_baseline": old_run_baseline(ids),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "slice_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({k: v for k, v in manifest.items() if k not in ("sample_ids", "indexes", "index_args")},
                     ensure_ascii=False, indent=2))

    if args.skip_images:
        return

    raw_dir = DATA_DIR / "raw_images"
    missing = [p for p in sorted(images) if not image_file_is_valid(raw_dir / p)]
    print(f"[slice] downloading {len(missing)}/{len(images)} missing images "
          f"with {args.image_workers} workers", file=sys.stderr, flush=True)

    def fetch(rel: str) -> bool:
        dest = raw_dir / rel
        try:
            curl_download(repo_url(UI_VISION_REPO, f"images/{rel}"), dest)
            return image_file_is_valid(dest)
        except Exception as exc:
            print(f"[slice] FAILED {rel}: {exc}", file=sys.stderr, flush=True)
            return False

    ok = 0
    with ThreadPoolExecutor(max_workers=args.image_workers) as pool:
        futures = {pool.submit(fetch, rel): rel for rel in missing}
        for i, fut in enumerate(as_completed(futures), 1):
            ok += bool(fut.result())
            if i % 10 == 0 or i == len(futures):
                print(f"[slice] images {i}/{len(futures)} done", file=sys.stderr, flush=True)
    print(f"[slice] image download complete: {ok}/{len(missing)} ok", file=sys.stderr)


if __name__ == "__main__":
    main()
