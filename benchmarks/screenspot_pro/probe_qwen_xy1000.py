#!/usr/bin/env python3
"""隔离 scale vs wrapper:{"x","y"} + [0,1000] 整数(= harness 会用的结构) + hires。
对比 [0,1]分数hires=58% 与 point_2d[0,1000]=79%。若≈79%→harness 改 [0,1000] 就能拿到。
用法: python probe_qwen_xy1000.py [workers]
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

PROMPT = ("Locate the UI element to click that fulfils the instruction, and output its center "
          "point.\nInstruction: {instr}\n"
          'Output ONLY JSON: {{"x": <int 0-1000>, "y": <int 0-1000>}} normalized to the image '
          "(0=left/top edge, 1000=right/bottom edge).")


def data_url(path):
    raw = Path(path).read_bytes(); mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        im = Image.open(io.BytesIO(raw)).convert("RGB"); buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92); raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(path, instr):
    body = {"model": MODEL, "stream": False, "vl_high_resolution_images": True,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT.format(instr=instr)},
                {"type": "image_url", "image_url": {"url": data_url(path)}}]}]}
    r = _client.post(f"{BASE}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def parse(txt, W, H):
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
    else:
        nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
        if len(nums) < 2:
            return None
        x, y = float(nums[0]), float(nums[1])
    if x <= 1000 and y <= 1000:
        return x / 1000 * W, y / 1000 * H
    return None


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
    raw = []
    def work(sid):
        r = m3[sid]; gt = r["gt_bbox"]
        try:
            im = Image.open(IMG_DIR / f"{sid}.png"); W, H = im.size
            resp = ask(str(IMG_DIR / f"{sid}.png"), r["instruction"])
            raw.append(resp[:50].replace("\n", " "))
            p = parse(resp, W, H)
            if not p:
                return {"sample_id": sid, "hit": False}
            return {"sample_id": sid, "hit": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])}
        except Exception as e:
            return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:90]}"}
    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in ids]):
            recs.append(f.result())
    with open(OUT / "qwen_xy1000.jsonl", "w", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    done = [x for x in recs if "hit" in x]
    ok = sum(x["hit"] for x in done)
    print("xy1000+hires: %d/%d = %.0f%% (+%derr)" % (ok, len(done), 100 * ok / max(1, len(done)), len(recs) - len(done)))
    print("对比: [0,1]分数hires=58%  point_2d[0,1000]=79%")
    print("前5条原始:", raw[:5])


if __name__ == "__main__":
    raise SystemExit(main())
