#!/usr/bin/env python3
"""GPT-5.5 探针A:reasoning_effort(thinking_level)off vs high,同 qwen/kimi 的方法论。
真正的开关是 Runtime 实例的 `thinking_level` 属性(调用 exec() 前设置),不是
create_runtime()/exec() 的关键字参数——之前误判为不可控,已订正。
用它自己的母语格式(abs_pixel,见 model_profiles.py),baseline50,thinking 独立测。
用法: python probe_gpt_thinking.py [workers]
"""
from __future__ import annotations
import json, sys, glob, time
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
PROVIDER = "openai-codex"
MODEL = "gpt-5.5"
FMT = "abs_pixel"


def ask(rt, img_path, instr, W, H):
    prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
              f"instruction, then give its click point.\nInstruction: {instr}\n"
              + cf.prompt_suffix(FMT, W, H))
    content = [{"type": "text", "text": prompt}, {"type": "image", "path": str(img_path)}]
    t0 = time.time()
    resp = rt.exec(content=content, timeout_s=150) or ""
    return resp, time.time() - t0


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))

    for level in ("off", "high"):
        out_path = OUT / f"gpt_thinking_{level}.jsonl"
        done = set()
        if out_path.exists():
            for l in open(out_path, encoding="utf-8"):
                if l.strip():
                    try:
                        done.add(json.loads(l)["sample_id"])
                    except Exception:
                        pass
        todo = [sid for sid in ids if sid not in done]

        rt = create_runtime(provider=PROVIDER, model=MODEL, max_retries=3)
        rt.thinking_level = level

        def work(sid):
            r = m3[sid]
            gt = r["gt_bbox"]
            try:
                im = Image.open(IMG_DIR / f"{sid}.png")
                W, H = im.size
                resp, dt = ask(rt, IMG_DIR / f"{sid}.png", r["instruction"], W, H)
                p = cf.parse_point(resp, FMT, W, H)
                hit = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
                return {"sample_id": sid, "hit": hit, "elapsed_s": round(dt, 1)}
            except Exception as e:
                return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:100]}"}

        out_f = open(out_path, "a", encoding="utf-8")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in todo]):
                rr = f.result()
                out_f.write(json.dumps(rr, ensure_ascii=False) + "\n")
                out_f.flush()
        out_f.close()

        recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
        done_r = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done_r)
        avg_t = sum(x["elapsed_s"] for x in done_r) / max(1, len(done_r))
        print(f"[GPT thinking={level:5s}] {ok}/{len(done_r)} = {ok/max(1,len(done_r)):.0%}  "
              f"avg={avg_t:.1f}s/call  (+{len(recs)-len(done_r)}err)", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
