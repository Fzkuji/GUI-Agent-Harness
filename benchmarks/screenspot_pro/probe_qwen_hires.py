#!/usr/bin/env python3
"""决定性测试:qwen 单发、发完整原图、归一化坐标,vl_high_resolution_images on vs off。
回答"harness 里 qwen 是不是被端点降采样压低"。一次调用/题,不走 harness 多轮。
用法: python probe_qwen_hires.py [workers]
"""
from __future__ import annotations
import base64, io, json, re, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"
_client = httpx.Client(timeout=380)


def data_url(path):
    raw = Path(path).read_bytes(); mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        im = Image.open(io.BytesIO(raw)).convert("RGB"); buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92); raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(path, instr, hires):
    prompt = ("This is a GUI screenshot. Find the single UI element to click for the instruction, "
              "then give its center as NORMALIZED coordinates (fractions of image size, top-left "
              f"origin, each in [0,1]).\nInstruction: {instr}\n"
              'Output ONLY JSON {"x": <float 0-1>, "y": <float 0-1>}.')
    body = {"model": MODEL, "stream": False,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url(path)}}]}]}
    if hires:
        body["vl_high_resolution_images"] = True
    r = _client.post(f"{BASE}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def parse(txt):
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
    else:
        nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
        if len(nums) < 2:
            return None
        x, y = float(nums[0]), float(nums[1])
    if x > 1.5 or y > 1.5:
        if x <= 1000 and y <= 1000:
            x, y = x / 1000, y / 1000
        else:
            return None
    return x, y


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))

    for hires in [False, True]:
        tag = "hires" if hires else "default"
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]
            try:
                im = Image.open(IMG_DIR / f"{sid}.png"); W, H = im.size
                p = parse(ask(str(IMG_DIR / f"{sid}.png"), r["instruction"], hires))
                if not p:
                    return {"sample_id": sid, "hit": False}
                px, py = p[0] * W, p[1] * H
                return {"sample_id": sid, "hit": bool(gt[0] <= px <= gt[2] and gt[1] <= py <= gt[3])}
            except Exception as e:
                return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:90]}"}
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in ids]):
                recs.append(f.result())
        with open(OUT / f"qwen_hires_{tag}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done)
        print(f"[{tag}] vl_high_resolution_images={hires}: {ok}/{len(done)} = {ok/max(1,len(done)):.0%} "
              f"(+{len(recs)-len(done)}err)", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
