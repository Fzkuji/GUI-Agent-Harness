#!/usr/bin/env python3
"""v5b:对 v5a 输出做统一的验身后处理(最终配置:spatial 不切换)。

  - verify 已生效的行:保持;但 spatial+vswitch 的行按最终配置回退到切换前的点。
  - verify 损坏(NameError)的非 spatial 行:补跑放大验身。
  - spatial 行:不验身(最终配置下不可能切换,省调用)。

用法: python verify_pass_v5b.py --shards 3 --shard-index N
输出: runs/ui_vision_arbitrated/v5b_shardN.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from arbitrate_two_arms import verify_final, is_spatial, point_inside  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--shard-index", type=int, default=0)
    args = ap.parse_args()

    rows = {}
    for p in glob.glob(str(REPO / "runs/ui_vision_arbitrated/shard*.jsonl")):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            rows[r["sample_id"]] = r

    # id -> image path
    ann_dir = HERE / "data_ui_vision" / "annotations"
    img_dir = HERE / "data_ui_vision" / "raw_images"
    id2img = {}
    for ann in ann_dir.glob("ui_vision_*.json"):
        for s in json.loads(ann.read_text(encoding="utf-8")):
            id2img[s["id"]] = img_dir / s.get("raw_image_path", s.get("img_filename", ""))

    from gui_harness.openprogram_compat import create_runtime
    runtime = create_runtime(provider=args.provider, model=args.model)

    out_path = REPO / f"runs/ui_vision_arbitrated/v5b_shard{args.shard_index}.jsonl"
    work = REPO / "runs/ui_vision_arbitrated/judge_crops"
    work.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in open(out_path, encoding="utf-8"):
            try:
                done.add(json.loads(line)["sample_id"])
            except Exception:
                pass
    f = open(out_path, "a", encoding="utf-8")

    todo = [sid for i, sid in enumerate(sorted(rows))
            if i % args.shards == args.shard_index and sid not in done]
    print(f"shard {args.shard_index}/{args.shards}: {len(todo)} rows", flush=True)

    for i, sid in enumerate(todo):
        r = dict(rows[sid])
        instr = r["instruction"]
        chosen = r.get("chosen_px")
        vmeta = r.get("verify") or {}
        action = "keep"

        if is_spatial(instr):
            if "+vswitch" in r["how"]:
                # 最终配置:spatial 不切换 → 回退到切换前的点
                how = r["how"].replace("+vswitch", "")
                pre = (r["arm2_px"] if how == "agree_zoom" or how.endswith("_B")
                       else r["arm1_px"] if how.endswith("_A") else chosen)
                if pre:
                    chosen, action = list(pre), "revert_spatial_switch"
                r["how"] = how + "+vrevert"
        elif vmeta.get("choice") is None and chosen:
            img_p = id2img.get(sid)
            if img_p and img_p.exists():
                new_pt, meta = verify_final(runtime, str(img_p), instr, chosen, work, f"v5b_{sid}")
                r["verify"] = meta
                if new_pt != chosen:
                    chosen, action = list(new_pt), "vswitch"
                    r["how"] += "+vswitch"

        r["chosen_px"] = chosen
        r["correctness"] = "correct" if (chosen and point_inside(chosen[0], chosen[1], r["gt_bbox"])) else "wrong"
        r["v5b_action"] = action
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(todo)}", flush=True)
    f.close()

    out_rows = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    ok = sum(r["correctness"] == "correct" for r in out_rows)
    print(f"\nshard {args.shard_index}: {ok}/{len(out_rows)} = {ok/max(1,len(out_rows)):.1%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
