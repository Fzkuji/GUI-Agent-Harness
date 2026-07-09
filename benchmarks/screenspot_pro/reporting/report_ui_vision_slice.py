#!/usr/bin/env python3
"""Row-controlled comparison: routed-locator slice vs the recorded single-shot run.

Reads the slice run's jsonl files plus the old full results, joins on
sample_id, and reports:
  * overall + per-split accuracy, old vs new, with flip counts (fixed/broken)
  * failure texture for the new run: near-miss (<=25px outside gt) vs
    medium (25-100px) vs far (>100px), plus the label-vs-control signature
    (prediction within 30px LEFT of a small text-like gt box — the checkbox
    case) to size the annotation-convention mismatch
  * per-sample table of regressions (old correct -> new wrong) for mining

Usage:
  python report_ui_vision_slice.py --run-dir runs/ui_vision_slice_m3_optimal
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OLD_RESULTS = HERE.parent / "ui_vision" / "results" / "gpt-5.5" / "results.jsonl"
SPLITS = ("basic", "functional", "spatial")


def dist_to_box(px: float, py: float, b: list[float]) -> float:
    dx = max(b[0] - px, 0, px - b[2])
    dy = max(b[1] - py, 0, py - b[3])
    return (dx * dx + dy * dy) ** 0.5


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--dump-misses", action="store_true",
                    help="print every wrong row with its miss geometry")
    args = ap.parse_args()
    run_dir = (HERE / args.run_dir) if not Path(args.run_dir).is_absolute() else Path(args.run_dir)
    if not run_dir.exists():
        run_dir = Path(args.run_dir).resolve()

    old_by_id: dict[str, dict] = {}
    for line in OLD_RESULTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            old_by_id[row["sample_id"]] = row

    new_rows: list[dict] = []
    for split in SPLITS:
        new_rows.extend(load_jsonl(run_dir / f"{split}.jsonl"))

    per_split = {s: {"n": 0, "new_ok": 0, "old_ok": 0, "fixed": 0, "broken": 0} for s in SPLITS}
    texture = {"near<=25": 0, "mid25-100": 0, "far>100": 0, "no_point": 0}
    label_control_sig = 0
    regressions: list[dict] = []
    near_misses: list[dict] = []

    for row in new_rows:
        sid = row["sample_id"]
        split = next((s for s in SPLITS if f"_{s}_" in sid), None)
        if split is None:
            continue
        st = per_split[split]
        st["n"] += 1
        new_ok = row.get("correctness") == "correct"
        old = old_by_id.get(sid)
        old_ok = bool(old and old.get("correctness") == "correct")
        st["new_ok"] += new_ok
        st["old_ok"] += old_ok
        if new_ok and not old_ok:
            st["fixed"] += 1
        if old_ok and not new_ok:
            st["broken"] += 1
            regressions.append(row)
        if not new_ok:
            pt = row.get("prediction_px")
            gt = row.get("gt_bbox")
            if not pt or not gt:
                texture["no_point"] += 1
                continue
            d = dist_to_box(pt[0], pt[1], gt)
            if d <= 25:
                texture["near<=25"] += 1
                near_misses.append(row)
            elif d <= 100:
                texture["mid25-100"] += 1
            else:
                texture["far>100"] += 1
            # checkbox/control-left-of-label signature: clicked within 40px
            # to the LEFT of a small gt box (text label annotation)
            gw, gh = gt[2] - gt[0], gt[3] - gt[1]
            if gh <= 40 and 0 < gt[0] - pt[0] <= 40 and gt[1] - 10 <= pt[1] <= gt[3] + 10:
                label_control_sig += 1

    total_n = sum(s["n"] for s in per_split.values())
    total_new = sum(s["new_ok"] for s in per_split.values())
    total_old = sum(s["old_ok"] for s in per_split.values())

    print(f"rows compared: {total_n}")
    print(f"NEW (routed locator): {total_new}/{total_n} = {total_new/total_n:.1%}" if total_n else "no rows")
    print(f"OLD (single-shot)   : {total_old}/{total_n} = {total_old/total_n:.1%}" if total_n else "")
    for s in SPLITS:
        st = per_split[s]
        if st["n"]:
            print(f"  {s:10s} n={st['n']:3d}  new={st['new_ok']/st['n']:.1%}  old={st['old_ok']/st['n']:.1%}"
                  f"  fixed={st['fixed']}  broken={st['broken']}")
    print(f"\nnew-run failure texture: {texture}")
    print(f"label-vs-control signature (clicked <=40px LEFT of small gt): {label_control_sig}")

    if regressions:
        print(f"\n=== regressions (old correct -> new wrong): {len(regressions)} ===")
        for r in regressions[:40]:
            loc = r.get("location") or {}
            pt, gt = r.get("prediction_px"), r.get("gt_bbox")
            d = dist_to_box(pt[0], pt[1], gt) if pt and gt else -1
            print(f"  {r['sample_id']}  d={d:.0f}px  instr={r['instruction'][:60]!r}")
            print(f"    -> picked: {str(loc.get('name'))[:70]} | {str(loc.get('reasoning'))[:110]}")

    if args.dump_misses and near_misses:
        print(f"\n=== near-misses (<=25px): {len(near_misses)} ===")
        for r in near_misses:
            loc = r.get("location") or {}
            print(f"  {r['sample_id']}  pred={r.get('prediction_px')} gt={r.get('gt_bbox')}"
                  f"  instr={r['instruction'][:60]!r}")
            print(f"    -> {str(loc.get('name'))[:70]}")


if __name__ == "__main__":
    main()
