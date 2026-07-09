#!/usr/bin/env python3
"""qwen 原生单发 [0,1000]+point_2d(+hires) vs 现有 harness(绝对),同样本配对。
从 qwen 主跑 results(504)等距抽 120 题,harness 成绩现成。回答:qwen 到底还要不要 harness。
用法: python probe_qwen_native_vs_harness.py [N] [workers]
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
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"
_client = httpx.Client(timeout=380)

PROMPT = ("Locate the UI element to click that fulfils the instruction, and output its center "
          "point.\nInstruction: {instr}\n"
          'Output ONLY JSON: {{"point_2d": [x, y]}} where x and y are integers in [0, 1000] '
          "normalized to the image (0=left/top edge, 1000=right/bottom edge).")


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
    m = re.search(r'point_2d"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', txt)
    if not m:
        nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
        if len(nums) < 2:
            return None
        x, y = float(nums[0]), float(nums[1])
    else:
        x, y = float(m.group(1)), float(m.group(2))
    if x <= 1000 and y <= 1000:
        return x / 1000 * W, y / 1000 * H
    return None


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    qh = {}
    for p in glob.glob(str(REPO / "runs/sspro_aliyun/qwen3.7-plus/results*.jsonl")):
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); qh[r["sample_id"]] = r
    # 只取有预测(非error)的样本,等距抽 N
    ok_ids = sorted(sid for sid, r in qh.items() if not r.get("error"))
    step = max(1, len(ok_ids) // N)
    ids = ok_ids[::step][:N]

    def work(sid):
        r = qh[sid]; gt = r["gt_bbox"]
        rec = {"sample_id": sid, "group": r.get("group"),
               "harness_hit": r["correctness"] == "correct"}
        try:
            im = Image.open(IMG_DIR / f"{sid}.png"); W, H = im.size
            p = parse(ask(str(IMG_DIR / f"{sid}.png"), r["instruction"]), W, H)
            rec["native_hit"] = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:90]}"; rec["native_hit"] = False
        return rec

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, s) for s in ids]
        for i, f in enumerate(as_completed(futs)):
            recs.append(f.result())
            if (i + 1) % 20 == 0:
                nn = sum(x.get("native_hit") for x in recs)
                print(f"  {i+1}/{len(ids)} native={nn}", flush=True)
    with open(OUT / "qwen_native_vs_harness.jsonl", "w", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    done = [x for x in recs if "error" not in x]
    nh = sum(x["native_hit"] for x in recs)
    hh = sum(x["harness_hit"] for x in recs)
    onlyN = sum(x["native_hit"] and not x["harness_hit"] for x in recs)
    onlyH = sum(x["harness_hit"] and not x["native_hit"] for x in recs)
    n = len(recs)
    print(f"\n同 {n} 题(qwen 主跑 504 抽样, +{n-len(done)}err):")
    print(f"  原生单发 [0,1000]+point_2d+hires: {nh}/{n} = {nh/n:.0%}")
    print(f"  现有 harness(绝对)            : {hh}/{n} = {hh/n:.0%}")
    print(f"  仅原生对 {onlyN}  仅harness对 {onlyH}  并集 {sum(x['native_hit'] or x['harness_hit'] for x in recs)}/{n}")


if __name__ == "__main__":
    raise SystemExit(main())
