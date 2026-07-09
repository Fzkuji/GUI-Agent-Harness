#!/usr/bin/env python3
"""方案①:固定两轮,裁剪区域由模型自己决定(point_2d+bbox_2d 同时问),不是代码算的窗口。

Round1: 全图 -> 同一次调用问 point_2d(落点)+ bbox_2d(它有把握包含目标的区域)。
Round2: 按模型自己给的 bbox_2d 裁原生分辨率小图 -> 再问一次 point_2d,映射回原图。
严格 2 次调用/题,不循环、不设 commit gate、不用候选证据(那条路已证明对 qwen 是负的)。
用法: python probe_qwen_2round_modelcrop.py [workers] [n]
"""
from __future__ import annotations
import base64, io, json, re, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))

from gui_harness.planning import coord_formats as cf
from run_sspro_native import IMG_DIR

OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"
_client = httpx.Client(timeout=380)

MIN_CROP = 200  # 裁剪最小边长(原图像素),避免模型给的框太小丢失上下文
_BBOX_RE = re.compile(r'bbox_2d"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*'
                      r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)')
_POINT_RE = re.compile(r'point_2d"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)')


def data_url_pil(im: Image.Image) -> str:
    buf = io.BytesIO(); im.save(buf, "PNG"); raw = buf.getvalue()
    mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=92)
        raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(im: Image.Image, prompt: str) -> str:
    body = {"model": MODEL, "stream": False, "vl_high_resolution_images": True,
            "enable_thinking": False,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url_pil(im)}}]}]}
    r = _client.post(f"{BASE}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def round1(im: Image.Image, instruction: str):
    """返回 (point_orig_xy, bbox_orig_xyxy) 或 (None, None)。"""
    W, H = im.size
    prompt = (
        f"The image is {W}x{H} pixels. Locate the UI element to click for the instruction.\n"
        f"Instruction: {instruction}\n"
        "First give a bounding box that you are confident fully contains the target element — "
        "tight enough to be useful for zooming in, but generous enough that you are sure the "
        "target is inside. Then give your best point estimate for the exact click location.\n"
        'Output ONLY JSON: {"bbox_2d": [x1,y1,x2,y2], "point_2d": [x,y]} both normalized to '
        "[0,1000] (0=left/top edge, 1000=right/bottom edge)."
    )
    txt = ask(im, prompt)
    bm = _BBOX_RE.search(txt)
    pm = _POINT_RE.search(txt)
    bbox = None
    if bm:
        bx1, by1, bx2, by2 = [float(v) / 1000 for v in bm.groups()]
        bbox = [bx1 * W, by1 * H, bx2 * W, by2 * H]
    point = None
    if pm:
        px, py = float(pm.group(1)), float(pm.group(2))
        if px <= 1.5 and py <= 1.5:
            point = (px * W, py * H)
        elif px <= 1000 and py <= 1000:
            point = (px / 1000 * W, py / 1000 * H)
    return point, bbox


def round2(full_im: Image.Image, bbox, point, instruction: str):
    """按模型自己给的 bbox 裁原生分辨率小图,再问一次精确点,映射回原图。"""
    W, H = full_im.size
    if bbox is None:
        return point  # 没给框,退化为直接用 round1 的点
    x1, y1, x2, y2 = bbox
    cw, ch = x2 - x1, y2 - y1
    if cw < MIN_CROP:
        pad = (MIN_CROP - cw) / 2; x1 -= pad; x2 += pad
    if ch < MIN_CROP:
        pad = (MIN_CROP - ch) / 2; y1 -= pad; y2 += pad
    x1 = max(0, min(x1, W - 1)); y1 = max(0, min(y1, H - 1))
    x2 = max(x1 + 1, min(x2, W)); y2 = max(y1 + 1, min(y2, H))
    crop = full_im.crop((int(x1), int(y1), int(x2), int(y2)))
    cw2, ch2 = crop.size
    prompt = (
        f"This is a zoomed-in crop ({cw2}x{ch2} pixels) of a larger screenshot. Locate the exact "
        f"click point for the instruction.\nInstruction: {instruction}\n"
        + cf.prompt_suffix("point2d_1000", cw2, ch2)
    )
    txt = ask(crop, prompt)
    p = cf.parse_point(txt, "point2d_1000", cw2, ch2)
    if p is None:
        return point  # 精修失败,退化为 round1 的点
    return (x1 + p[0], y1 + p[1])


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    if n > 0:
        ids = ids[:n]

    def work(sid):
        r = m3[sid]; gt = r["gt_bbox"]
        img_path = IMG_DIR / f"{sid}.png"
        rec = {"sample_id": sid}
        try:
            full_im = Image.open(img_path).convert("RGB")
            p1, bbox = round1(full_im, r["instruction"])
            rec["round1_point"] = list(map(int, p1)) if p1 else None
            rec["round1_bbox"] = list(map(int, bbox)) if bbox else None
            rec["round1_hit"] = bool(p1 and gt[0] <= p1[0] <= gt[2] and gt[1] <= p1[1] <= gt[3])
            p2 = round2(full_im, bbox, p1, r["instruction"])
            rec["final_point"] = list(map(int, p2)) if p2 else None
            rec["hit"] = bool(p2 and gt[0] <= p2[0] <= gt[2] and gt[1] <= p2[1] <= gt[3])
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        return rec

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, s) for s in ids]
        for i, f in enumerate(as_completed(futs)):
            recs.append(f.result())
            if (i + 1) % 10 == 0:
                nh = sum(x.get("hit", False) for x in recs)
                print(f"  {i+1}/{len(ids)}  hit={nh}", flush=True)
    with open(OUT / "qwen_2round_modelcrop.jsonl", "w", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")

    done = [x for x in recs if "hit" in x]
    r1_ok = sum(x.get("round1_hit", False) for x in done)
    ok = sum(x["hit"] for x in done)
    print(f"\n方案①(两轮,模型自选裁剪): round1单独={r1_ok}/{len(done)}={r1_ok/max(1,len(done)):.0%}  "
          f"两轮最终={ok}/{len(done)}={ok/max(1,len(done)):.0%}  (+{len(recs)-len(done)}err)")


if __name__ == "__main__":
    raise SystemExit(main())
