#!/usr/bin/env python3
"""kimi-k2.6 坐标格式消融:绝对像素 / [0,1] 分数 / {x,y}[0,1000] / point_2d[0,1000]。
单发无提示,同 baseline50 题,走阿里云 Token Plan 端点(与 qwen 同端点,不同 model)。
用法: python probe_kimi_format.py [workers]
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
MODEL = "kimi-k2.6"
_client = httpx.Client(timeout=380)

FORMATS = {
    "abs":     ('The screenshot is {W}x{H} pixels. Output ONLY JSON {{"x": <int 0-{W}>, '
                '"y": <int 0-{H}>}} — absolute pixel center of the element to click.'),
    "frac01":  ('Output ONLY JSON {{"x": <float 0-1>, "y": <float 0-1>}} — the NORMALIZED '
                'center (fractions of image width/height, top-left origin).'),
    "xy1000":  ('Output ONLY JSON {{"x": <int 0-1000>, "y": <int 0-1000>}} — the click point '
                'normalized to [0,1000] (0=left/top, 1000=right/bottom).'),
    "point2d": ('Output ONLY JSON {{"point_2d": [x, y]}} where x,y are integers in [0,1000] '
                'normalized to the image (0=left/top, 1000=right/bottom).'),
}


def data_url(path):
    raw = Path(path).read_bytes(); mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        im = Image.open(io.BytesIO(raw)).convert("RGB"); buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92); raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(path, instr, coord_instr):
    body = {"model": MODEL, "stream": False, "messages": [{"role": "user", "content": [
        {"type": "text", "text": (f"This is a GUI screenshot. Find the single UI element to "
                                  f"click for the instruction, then give its click point.\n"
                                  f"Instruction: {instr}\n" + coord_instr)},
        {"type": "image_url", "image_url": {"url": data_url(path)}}]}]}
    r = _client.post(f"{BASE}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def parse(txt, W, H, fmt):
    if fmt == "point2d":
        m = re.search(r'point_2d"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', txt)
    else:
        m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
    else:
        nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
        if len(nums) < 2:
            return None
        x, y = float(nums[0]), float(nums[1])
    if x <= 1.5 and y <= 1.5:
        return x * W, y * H
    if x <= 1000 and y <= 1000 and fmt != "abs":
        return x / 1000 * W, y / 1000 * H
    return x, y


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

    for fmt, coord in FORMATS.items():
        raw = []
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]
            try:
                im = Image.open(IMG_DIR / f"{sid}.png"); W, H = im.size
                resp = ask(str(IMG_DIR / f"{sid}.png"), r["instruction"], coord.format(W=W, H=H))
                raw.append(resp[:60].replace("\n", " "))
                p = parse(resp, W, H, fmt)
                if not p:
                    return {"sample_id": sid, "hit": False}
                return {"sample_id": sid, "hit": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])}
            except Exception as e:
                return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:100]}"}
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in ids]):
                recs.append(f.result())
        with open(OUT / f"kimi_format_{fmt}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done)
        print("[kimi %-8s] %d/%d = %.0f%% (+%derr)  例:%s"
              % (fmt, ok, len(done), 100 * ok / max(1, len(done)), len(recs) - len(done), raw[:2]),
              flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
