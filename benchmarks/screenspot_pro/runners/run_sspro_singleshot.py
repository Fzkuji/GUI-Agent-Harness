#!/usr/bin/env python3
"""ScreenSpot-Pro 纯 API 单发基线:GPT-5.5 一次调用直接出坐标,无脚手架/无工具/无缩放。

对照我们的 harness(迭代缩放,88.7%)与 codex agentic 框架。测的是模型的原始 grounding
能力:给整张截图 + 指令 + 图像尺寸,要求直接输出目标中心的像素坐标(原图坐标系)。

分片:GUI_HARNESS_SSPRO_SHARDS + GUI_HARNESS_SSPRO_SHARD;skip-existing 续跑。
输出:runs/sspro_singleshot/results.jsonl(分片写 results_s{shard}.jsonl)。
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

ANN_DIR = HERE / "data" / "annotations"
IMG_DIR = HERE / "data" / "images"

_PROMPT = """You are a precise GUI grounding model. You are given a screenshot and an
instruction naming one UI target to click. Output the pixel coordinates of the
CENTER of that target, in the ORIGINAL image coordinate system.

Image size: width={w}, height={h} pixels. Coordinates must be integers with
0 <= x < {w} and 0 <= y < {h}.

Instruction: {instr}

Reply with ONLY JSON: {{"x": <int>, "y": <int>}}"""


def main() -> int:
    from gui_harness.openprogram_compat import create_runtime
    from gui_harness.utils import parse_json
    from gui_harness.error_monitor import reraise_if_fatal

    shards = int(os.environ.get("GUI_HARNESS_SSPRO_SHARDS", "1") or "1")
    shard = int(os.environ.get("GUI_HARNESS_SSPRO_SHARD", "0") or "0")
    sharded = shards > 1 and 0 <= shard < shards

    samples = []
    for af in sorted(ANN_DIR.glob("*.json")):
        for s in json.loads(af.read_text(encoding="utf-8")):
            s["_ann_file"] = af.name
            samples.append(s)
    samples.sort(key=lambda s: s["id"])

    outdir = REPO / "runs/sspro_singleshot"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / (f"results_s{shard}.jsonl" if sharded else "results.jsonl")

    done = set()
    for df in glob.glob(str(outdir / "results*.jsonl")):
        for l in open(df, encoding="utf-8"):
            try:
                done.add(json.loads(l)["sample_id"])
            except Exception:
                pass

    rt = create_runtime(provider="openai-codex", model="gpt-5.5")
    todo = [s for i, s in enumerate(samples)
            if s["id"] not in done and (not sharded or i % shards == shard)]
    print(f"SSPro single-shot: {len(todo)} 待跑(总 {len(samples)},已完成 {len(done)}"
          f"{f', shard {shard}/{shards}' if sharded else ''})", flush=True)

    f = open(out, "a", encoding="utf-8")
    for i, s in enumerate(todo):
        img = IMG_DIR / f"{s['id']}.png"
        w, h = s["img_size"]
        gt = s["bbox"]
        t0 = time.time()
        rec = {"sample_id": s["id"], "instruction": s["instruction"], "gt_bbox": gt,
               "group": s.get("group"), "ui_type": s.get("ui_type"), "img_size": s["img_size"]}
        try:
            if not img.exists():
                raise FileNotFoundError(s["img_filename"])
            content = [
                {"type": "text", "text": _PROMPT.format(w=w, h=h, instr=s["instruction"])},
                {"type": "image", "path": str(img)},
            ]
            parsed = parse_json(rt.exec(content=content, timeout_s=240))
            x, y = int(parsed["x"]), int(parsed["y"])
            rec["prediction_px"] = [x, y]
            rec["correctness"] = "correct" if (gt[0] <= x <= gt[2] and gt[1] <= y <= gt[3]) else "wrong"
        except Exception as exc:
            # A single-sample stream timeout must NOT crash the shard (codex
            # streams hang on some 4K images). Record it and continue; only
            # auth/quota/transport LLMErrors are fatal and re-raised.
            is_timeout = ("Timeout" in exc.__class__.__name__
                          or "timeout" in str(exc).lower()
                          or "StreamTotalTimeout" in str(exc))
            if not is_timeout:
                reraise_if_fatal(exc)
            rec["prediction_px"] = None
            rec["correctness"] = "wrong"
            rec["error"] = {"type": exc.__class__.__name__,
                            "message": str(exc)[:200], "timeout": is_timeout}
        rec["elapsed_s"] = round(time.time() - t0, 1)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(todo)}", flush=True)
    f.close()

    rows = {}
    for df in glob.glob(str(outdir / "results*.jsonl")):
        for l in open(df, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); rows[r["sample_id"]] = r
    ok = sum(r["correctness"] == "correct" for r in rows.values())
    print(f"\nSSPro single-shot: {ok}/{len(rows)} = {ok/max(1,len(rows)):.1%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
