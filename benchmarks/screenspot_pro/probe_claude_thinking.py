#!/usr/bin/env python3
"""Claude 4.7 探针A:thinking 对单发 grounding 的影响(baseline50,abs_pixel,无提示)。

动机:6月79%那次走的是 Meridian 代理→Claude Code SDK(thinking 默认开),
现在直连 API thinking 默认 off(30%)。若 thinking=high 显著höher,6月差距的
主因就是 thinking,不是管线。
用法: python probe_claude_thinking.py [workers]
输出: runs/sspro_baseline/claude47_thinking_high.jsonl
"""
from __future__ import annotations
import json, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from PIL import Image
from gui_harness.planning import coord_formats as cf
from gui_harness.openprogram_compat import create_runtime

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"

_rt = create_runtime(provider="claude-code", model="claude-opus-4-7", max_retries=3)
_rt.thinking_level = "high"  # GPT探针A验证过的开法:实例属性,exec前设置


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    meta = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                meta[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    out_path = OUT / "claude47_thinking_high.jsonl"
    done = set()
    if out_path.exists():
        for l in open(out_path, encoding="utf-8"):
            if l.strip():
                rr = json.loads(l)
                if "hit" in rr:
                    done.add(rr["sample_id"])
    todo = [s for s in ids if s not in done]

    def work(sid):
        r = meta[sid]
        gt = r["gt_bbox"]
        try:
            img = IMG_DIR / f"{sid}.png"
            W, H = Image.open(img).size
            prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
                      f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                      + cf.prompt_suffix("abs_pixel", W, H))
            resp = _rt.exec(content=[{"type": "text", "text": prompt},
                                     {"type": "image", "path": str(img)}], timeout_s=300) or ""
            p = cf.parse_point(resp, "abs_pixel", W, H)
            if not p:
                return {"sample_id": sid, "hit": False, "raw": resp[:150]}
            return {"sample_id": sid, "pred": [p[0], p[1]],
                    "hit": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])}
        except Exception as e:
            return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:100]}"}

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in todo]):
            recs.append(f.result())
    with open(out_path, "a", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    all_recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    done_r = [x for x in all_recs if "hit" in x]
    ok = sum(x["hit"] for x in done_r)
    print("[claude47 thinking=high abs] %d/%d = %.0f%% (err=%d)  [对照 thinking=off: 30%%]"
          % (ok, len(done_r), 100 * ok / max(1, len(done_r)),
             len(all_recs) - len(done_r)), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
