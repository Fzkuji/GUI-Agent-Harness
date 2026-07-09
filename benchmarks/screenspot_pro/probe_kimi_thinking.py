#!/usr/bin/env python3
"""kimi-k2.6 enable_thinking on/off:同 qwen 的方法论,补上 kimi 缺的这块。
用它自己的最优格式(frac01,见 model_profiles.py),baseline50,thinking 独立测。
用法: python probe_kimi_thinking.py [workers]
"""
from __future__ import annotations
import base64, io, json, sys, glob, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
from gui_harness.planning import coord_formats as cf

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.6"
FMT = "frac01"
_client = httpx.Client(timeout=380)


def data_url(path):
    raw = Path(path).read_bytes(); mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        im = Image.open(io.BytesIO(raw)).convert("RGB"); buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92); raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(path, instr, thinking):
    prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
              f"instruction, then give its click point.\nInstruction: {instr}\n"
              + cf.prompt_suffix(FMT, 0, 0))
    body = {"model": MODEL, "stream": False, "enable_thinking": thinking,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url(path)}}]}]}
    t0 = time.time()
    r = _client.post(f"{BASE}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {KEY}"})
    dt = time.time() - t0
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or "", dt


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))

    for thinking in [True, False]:
        tag = "on" if thinking else "off"
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]
            try:
                im = Image.open(IMG_DIR / f"{sid}.png"); W, H = im.size
                resp, dt = ask(IMG_DIR / f"{sid}.png", r["instruction"], thinking)
                p = cf.parse_point(resp, FMT, W, H)
                hit = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
                return {"sample_id": sid, "hit": hit, "elapsed_s": round(dt, 1)}
            except Exception as e:
                return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:90]}"}
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in ids]):
                recs.append(f.result())
        with open(OUT / f"kimi_thinking_{tag}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done)
        avg_t = sum(x["elapsed_s"] for x in done) / max(1, len(done))
        print(f"[kimi thinking={tag:3s}] {ok}/{len(done)} = {ok/max(1,len(done)):.0%}  "
              f"avg={avg_t:.1f}s/call  (+{len(recs)-len(done)}err)", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
