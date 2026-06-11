#!/usr/bin/env python3
"""v5b:对仲裁输出的每行最终答案跑"放大验身"后处理(修复 NameError 后的
verify_final),重新计分。诚实语义:验身既可救错行、也可能破坏对行。

用法:
  python verify_pass.py --in-glob "runs/ui_vision_arbitrated/shard*.jsonl" \
      --out runs/ui_vision_verify_pass/shardN.jsonl --shards 3 --shard-index N
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from arbitrate_two_arms import verify_final, image_path_for, point_inside  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-glob", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--shard-index", type=int, default=0)
    args = ap.parse_args()

    import glob as _glob
    rows = []
    for p in sorted(_glob.glob(str(REPO / args.in_glob))):
        for line in open(p, encoding="utf-8"):
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r["sample_id"])
    if args.shards > 1:
        rows = [r for i, r in enumerate(rows) if i % args.shards == args.shard_index]
    print(f"shard {args.shard_index}/{args.shards}: {len(rows)} rows", flush=True)

    from gui_harness.openprogram_compat import create_runtime
    runtime = create_runtime(provider=args.provider, model=args.model)

    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent / "lineups"
    work.mkdir(exist_ok=True)

    ann_cache: dict = {}
    done_ids = set()
    if out_path.exists():
        for line in open(out_path, encoding="utf-8"):
            try:
                done_ids.add(json.loads(line)["sample_id"])
            except Exception:
                pass
    f = out_path.open("a", encoding="utf-8")
    stats = {"kept": 0, "switched": 0, "rescued": 0, "broken": 0, "err": 0}
    for i, r in enumerate(rows):
        sid = r["sample_id"]
        if sid in done_ids:
            continue
        chosen = r.get("chosen_px")
        gt = r["gt_bbox"]
        was_correct = r["correctness"] == "correct"
        new_pt, meta = chosen, None
        if chosen:
            img_p = image_path_for(sid, ann_cache)
            if img_p is not None:
                new_pt, meta = verify_final(runtime, str(img_p), r["instruction"], chosen, work, sid)
        if meta and "error" in meta:
            stats["err"] += 1
        if new_pt != chosen:
            stats["switched"] += 1
        else:
            stats["kept"] += 1
        now_correct = bool(new_pt) and point_inside(new_pt[0], new_pt[1], gt)
        if now_correct and not was_correct:
            stats["rescued"] += 1
        elif not now_correct and was_correct:
            stats["broken"] += 1
        out = dict(r)
        out["chosen_px"] = new_pt
        out["correctness"] = "correct" if now_correct else "wrong"
        out["verify"] = meta
        out["pre_verify_correct"] = was_correct
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
        f.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(rows)} {stats}", flush=True)
    f.close()
    print(f"done: {stats}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
