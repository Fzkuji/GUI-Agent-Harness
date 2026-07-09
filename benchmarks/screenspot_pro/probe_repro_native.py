#!/usr/bin/env python3
"""可复现的 Qwen 官方 grounding 协议原生单发探针。

关键:Qwen-VL 输出的是"缩放后图像空间的绝对像素坐标"。若把原图直接丢给
chat 端点,端点用未知 max_pixels 偷偷 smart_resize,坐标空间未知→无法映射回原图。
本脚本自己用 qwen_vl_utils 的 smart_resize 把图缩到已知 (w_bar,h_bar) 再发,
模型在该已知空间输出坐标,再按 W/w_bar, H/h_bar 映射回原图判分。

对两组样本各测一次(可复现基线):
  - probe50_ids.json      : 50 个 harness 判错的最难样本(与之前探针可比)
  - repro_rand50_ids.json : 从 504 已答样本里等距抽的 50 个(无偏,可与 harness 同题对比)
用法: python probe_repro_native.py <max_pixels> [workers]
  max_pixels 例: 1003520(≈1M,标准)/ 4014080(≈4M,保小图标)
"""
from __future__ import annotations
import base64, io, json, math, re, sys, glob
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMG_DIR = HERE / "data" / "images"
RES = HERE.parents[1] / "runs/sspro_aliyun/qwen3.7-plus"
KEY_FILE = Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt"
BASE_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"

import httpx
from PIL import Image

_client = httpx.Client(timeout=380)
_API_KEY = KEY_FILE.read_text(encoding="utf-8").strip()

FACTOR = 28
MIN_PIXELS = 4 * 28 * 28  # 3136


def round_by(n, f): return round(n / f) * f
def floor_by(n, f): return math.floor(n / f) * f
def ceil_by(n, f): return math.ceil(n / f) * f


def smart_resize(h, w, max_pixels, factor=FACTOR, min_pixels=MIN_PIXELS):
    """qwen_vl_utils.smart_resize 复刻:返回 (h_bar, w_bar),均为 factor 倍数,保长宽比。"""
    h_bar = max(factor, round_by(h, factor))
    w_bar = max(factor, round_by(w, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((h * w) / max_pixels)
        h_bar = max(factor, floor_by(h / beta, factor))
        w_bar = max(factor, floor_by(w / beta, factor))
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (h * w))
        h_bar = ceil_by(h * beta, factor)
        w_bar = ceil_by(w * beta, factor)
    return h_bar, w_bar


def _data_url(im: Image.Image) -> str:
    buf = io.BytesIO(); im.save(buf, "PNG"); raw = buf.getvalue()
    return f"data:image/png;base64,{base64.b64encode(raw).decode()}"


def _ask(im, instruction, rw, rh):
    prompt = (
        f"The image is {rw}x{rh} pixels. Locate the UI element for this instruction "
        f"and give the click point.\nInstruction: {instruction}\n"
        'Output ONLY JSON {"x": <int>, "y": <int>} in absolute pixels of THIS image.'
    )
    body = {"model": MODEL, "stream": False, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": _data_url(im)}}]}]}
    r = _client.post(f"{BASE_URL}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {_API_KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def _parse(txt):
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if m:
        return float(m.group(1)), float(m.group(2))
    nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
    return (float(nums[0]), float(nums[1])) if len(nums) >= 2 else None


def predict(sid, instruction, max_pixels, raw_log=None):
    im = Image.open(IMG_DIR / f"{sid}.png").convert("RGB")
    W, H = im.size
    rh, rw = smart_resize(H, W, max_pixels)
    rim = im.resize((rw, rh), Image.BICUBIC)
    txt = _ask(rim, instruction, rw, rh)
    if raw_log is not None:
        raw_log.append((rw, rh, txt[:60]))
    xy = _parse(txt)
    if not xy:
        return None, (W, H, rw, rh)
    x, y = xy
    # 约定判定:模型应输出缩放图空间绝对像素;若明显是 [0,1000] 归一化则改按 1000 映射
    if x <= 1000 and y <= 1000 and (rw > 1200 or rh > 1200):
        x_orig, y_orig = x / 1000 * W, y / 1000 * H
    else:
        x_orig, y_orig = x * W / rw, y * H / rh
    return (x_orig, y_orig), (W, H, rw, rh)


def hit(pt, gt):
    return bool(pt) and gt[0] <= pt[0] <= gt[2] and gt[1] <= pt[1] <= gt[3]


def load_results():
    seen = {}
    for p in glob.glob(str(RES / "results*.jsonl")):
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); seen[r["sample_id"]] = r
    return seen


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    max_pixels = int(sys.argv[1]) if len(sys.argv) > 1 else 1003520
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    seen = load_results()

    # 构造无偏随机 50(等距抽样已答样本,确定性)
    rand_path = RES / "repro_rand50_ids.json"
    if not rand_path.exists():
        answered = sorted(sid for sid, r in seen.items() if not r.get("error"))
        step = max(1, len(answered) // 50)
        rand_ids = answered[::step][:50]
        json.dump(rand_ids, open(rand_path, "w"))
    rand_ids = json.load(open(rand_path))
    err_ids = json.load(open(RES / "probe50_ids.json"))

    for tag, ids in [("rand50", rand_ids), ("err50", err_ids)]:
        raw_log = []
        recs = []
        def work(sid):
            r = seen[sid]; gt = r["gt_bbox"]
            try:
                pt, dims = predict(sid, r["instruction"], max_pixels, raw_log)
                return {"sample_id": sid, "group": r.get("group"), "gt_bbox": gt,
                        "harness_correct": r["correctness"] == "correct",
                        "native_pred": [int(pt[0]), int(pt[1])] if pt else None,
                        "native_hit": hit(pt, gt), "dims": dims}
            except Exception as exc:
                return {"sample_id": sid, "error": f"{exc.__class__.__name__}: {str(exc)[:100]}"}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(work, s) for s in ids]
            for i, f in enumerate(as_completed(futs)):
                recs.append(f.result())
                if (i + 1) % 10 == 0:
                    print(f"  [{tag} mp={max_pixels}] {i+1}/{len(ids)} "
                          f"native={sum(x.get('native_hit',False) for x in recs)}", flush=True)
        with open(RES / f"repro_{tag}_mp{max_pixels}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "native_hit" in x]
        nh = sum(x["native_hit"] for x in done)
        hc = sum(x.get("harness_correct", False) for x in done)
        print(f"\n[{tag}] max_pixels={max_pixels}  n={len(done)}(+{len(recs)-len(done)}err)")
        print(f"   原生(可复现协议) 命中 {nh}/{len(done)} = {nh/max(1,len(done)):.0%}")
        print(f"   harness 同题     命中 {hc}/{len(done)} = {hc/max(1,len(done)):.0%}")
        print("   前5条原始:", [f"{rw}x{rh}:{t}" for rw, rh, t in raw_log[:5]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
