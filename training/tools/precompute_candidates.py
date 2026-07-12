#!/usr/bin/env python3
"""Precompute detector+OCR candidates for v3 training rows.

Runs the harness's own perception once per FULL image (detector.detect_all:
GPA-GUI-Detector YOLO + OCR at conf=0.12 — exactly what feeds the harness's
candidate list at inference) and caches the build_candidates() output in
original-pixel coordinates. prepare_zoom_sft_v3.py later projects these into
each crop view with evidence.candidate_lines().

Must run in an env with the harness deps (torch/ultralytics/EasyOCR + the GPA
weight) — use the harness env, not the LLaMA-Factory env. GPU strongly
recommended. Uses the SAME source spec + seed + shuffle as prepare_zoom_sft_v2
so the cached rows line up with the training rows.

Output: <out-dir>/<source>_candidates.json  = {image_filename: [candidates...]}
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_zoom_sft_v2 import parse_source  # noqa: E402
from evidence import build_candidates  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", required=True,
                    help="name:json:imgdir:n — MUST match prepare_zoom_sft_v3 exactly")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "data" / "candidates_cache"))
    ap.add_argument("--seed", type=int, default=20260712, help="must match prepare seed")
    ap.add_argument("--val-frac", type=float, default=0.02, help="must match prepare (val rows also cached, used by harness eval)")
    ap.add_argument("--conf", type=float, default=0.12)
    args = ap.parse_args()

    from gui_harness.perception import detector  # heavy import; harness env only

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    master = random.Random(args.seed)
    for spec in args.source:
        name, json_path, img_dir, n_rows = parse_source(spec)
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        master.shuffle(rows)  # same order as prepare_zoom_sft_v2/v3
        rows = rows[:n_rows] if n_rows > 0 else rows

        out_path = out_dir / f"{name}_candidates.json"
        cache: dict[str, list] = {}
        if out_path.exists():
            cache = json.loads(out_path.read_text(encoding="utf-8"))
            print(f"[{name}] resuming: {len(cache)} images already cached", file=sys.stderr)

        images = []
        seen = set()
        for row in rows:
            fn = row.get("image")
            if fn and fn not in seen:
                seen.add(fn)
                images.append(fn)

        t0 = time.time()
        done = failed = 0
        for i, fn in enumerate(images):
            if fn in cache:
                continue
            p = img_dir / fn
            try:
                icons, texts, _merged, _w, _h = detector.detect_all(str(p), conf=args.conf)
                cache[fn] = build_candidates([], texts, icons, limit=240)
                done += 1
            except Exception as exc:  # noqa: BLE001 - record and continue
                cache[fn] = []
                failed += 1
                print(f"  [{name}] {fn}: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            if (done + failed) % 200 == 0:
                rate = (done + failed) / max(1e-9, time.time() - t0)
                eta = (len(images) - i - 1) / max(rate, 1e-9) / 60
                print(f"  [{name}] {i+1}/{len(images)} rate={rate:.2f}/s eta={eta:.0f}min",
                      file=sys.stderr)
                out_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

        out_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        n_cands = sum(len(v) for v in cache.values())
        print(json.dumps({"source": name, "images": len(cache), "failed": failed,
                          "total_candidates": n_cands,
                          "avg_candidates": round(n_cands / max(1, len(cache)), 1),
                          "out": str(out_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
