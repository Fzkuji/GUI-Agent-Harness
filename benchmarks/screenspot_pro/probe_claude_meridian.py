#!/usr/bin/env python3
"""Claude 通道对照探针:同样 baseline50+abs_pixel 单发,走 Meridian→Claude Code SDK。

对照组:直连 API 同条件 30%(claude47_format_abs_pixel.jsonl)。
唯一变量是通道——若显著höher,6月79%的谜底就是 SDK 通道的图片预处理。
用法: python probe_claude_meridian.py [workers] [model]
输出: runs/sspro_baseline/claude47_meridian.jsonl
"""
from __future__ import annotations
import base64, json, sys, glob, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from PIL import Image
from gui_harness.planning import coord_formats as cf

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
BASE = "http://127.0.0.1:3456/v1"

_client = httpx.Client(timeout=380)


def ask(model: str, prompt: str, img_path: Path) -> tuple[str, str]:
    raw = img_path.read_bytes()
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    r = _client.post(f"{BASE}/chat/completions", json={
        "model": model, "stream": False,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]}],
    })
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
    d = r.json()
    return (d["choices"][0]["message"].get("content") or "", d.get("model") or "")


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    model = sys.argv[2] if len(sys.argv) > 2 else "claude-opus-4-7"
    meta = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                meta[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    out_path = OUT / "claude47_meridian.jsonl"
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
            t0 = time.time()
            resp, used_model = ask(model, prompt, img)
            p = cf.parse_point(resp, "abs_pixel", W, H)
            rec = {"sample_id": sid, "model_used": used_model,
                   "elapsed_s": round(time.time() - t0, 1)}
            if not p:
                rec.update(hit=False, raw=resp[:150])
            else:
                rec.update(pred=[p[0], p[1]],
                           hit=bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3]))
            return rec
        except Exception as e:
            return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:120]}"}

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in todo]):
            recs.append(f.result())
            n_done = sum(1 for x in recs if "hit" in x)
            if len(recs) % 10 == 0:
                print(f"  progress {len(recs)}/{len(todo)}", flush=True)
    with open(out_path, "a", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    all_recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    done_r = [x for x in all_recs if "hit" in x]
    ok = sum(x["hit"] for x in done_r)
    models = {x.get("model_used") for x in done_r}
    print("[claude meridian abs] %d/%d = %.0f%% (err=%d) models=%s  [对照 直连: 30%%]"
          % (ok, len(done_r), 100 * ok / max(1, len(done_r)),
             len(all_recs) - len(done_r), models), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
