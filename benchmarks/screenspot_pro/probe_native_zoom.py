#!/usr/bin/env python3
"""诊断探针:在 50 个 harness 判错的样本上,对比 qwen3.7-plus 的
   ① 原生单发(全图直答坐标)  ② ZoomClick(全图粗定位 → 多步 ×0.5 裁剪精修)。

旧 harness 在这 50 个上按定义 0/50,故任何命中都是净救回。
用法: python probe_native_zoom.py [native|zoom|both]
坐标约定:提示要绝对像素并给出 W×H;同时打印前若干条原始输出人工确认,
         若明显是归一化 [0,1000] 则整批按 w/1000,h/1000 重标(全局判定,不用标签)。
"""
from __future__ import annotations
import base64, io, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMG_DIR = HERE / "data" / "images"
RES = HERE.parents[1] / "runs/sspro_aliyun/qwen3.7-plus"
KEY_FILE = Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt"
BASE_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"
MAX_IMG_BYTES = 9 * 1024 * 1024

import httpx
from PIL import Image

_client = httpx.Client(timeout=380)
_API_KEY = KEY_FILE.read_text(encoding="utf-8").strip()


def _data_url_from_pil(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    raw = buf.getvalue()
    mime = "image/png"
    if len(raw) > MAX_IMG_BYTES:
        buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=92)
        raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _ask(im: Image.Image, instruction: str) -> str:
    w, h = im.size
    prompt = (
        f"You are a precise GUI grounding model. The screenshot is {w}x{h} pixels.\n"
        f"Instruction: {instruction}\n"
        "Identify the single UI element to click that fulfils the instruction, and "
        "return the ABSOLUTE PIXEL coordinates of its center.\n"
        'Output ONLY JSON: {"x": <int 0..%d>, "y": <int 0..%d>}' % (w - 1, h - 1)
    )
    body = {"model": MODEL, "stream": False, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": _data_url_from_pil(im)}},
    ]}]}
    r = _client.post(f"{BASE_URL}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {_API_KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def _parse_xy(txt: str):
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if not m:
        nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
        if len(nums) >= 2:
            return float(nums[0]), float(nums[1])
        return None
    return float(m.group(1)), float(m.group(2))


def native_predict(im, instruction, raw_log=None):
    txt = _ask(im, instruction)
    if raw_log is not None:
        raw_log.append(txt[:80])
    xy = _parse_xy(txt)
    return xy  # 像素(相对传入 im 尺寸)


def zoomclick_predict(full_im, instruction, steps=2, floor=768):
    """ZoomClick:全图粗定位 → 以预测点为心多步 ×0.5 裁剪(不小于 floor)→ 在原生分辨率裁剪上重定位。"""
    W, H = full_im.size
    xy = native_predict(full_im, instruction)
    if not xy:
        return None
    cx, cy = xy
    side = max(W, H)
    for _ in range(steps):
        side = max(floor, side * 0.5)
        half = side / 2
        # 以 (cx,cy) 为心裁剪,clip 到图内
        l = int(max(0, min(cx - half, W - side)))
        t = int(max(0, min(cy - half, H - side)))
        r = int(min(W, l + side)); b = int(min(H, t + side))
        if r - l < 8 or b - t < 8:
            break
        crop = full_im.crop((l, t, r, b))
        sub = native_predict(crop, instruction)
        if not sub:
            break
        cx, cy = l + sub[0], t + sub[1]   # 映射回全图
    return (cx, cy)


def hit(pt, gt):
    return pt and gt[0] <= pt[0] <= gt[2] and gt[1] <= pt[1] <= gt[3]


def _work_one(r, mode, raw_log):
    sid = r["sample_id"]; gt = r["gt_bbox"]; instr = r["instruction"]
    im = Image.open(IMG_DIR / f"{sid}.png").convert("RGB")
    rec = {"sample_id": sid, "group": r.get("group"), "gt_bbox": gt,
           "old_pred": r.get("prediction_px")}
    try:
        if mode in ("native", "both"):
            p = native_predict(im, instr, raw_log)
            rec["native_pred"] = list(map(int, p)) if p else None
            rec["native_hit"] = bool(hit(p, gt))
        if mode in ("zoom", "both"):
            pz = zoomclick_predict(im, instr)
            rec["zoom_pred"] = list(map(int, pz)) if pz else None
            rec["zoom_hit"] = bool(hit(pz, gt))
    except Exception as exc:
        rec["error"] = f"{exc.__class__.__name__}: {str(exc)[:120]}"
    return rec


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    ids = json.load(open(RES / "probe50_ids.json"))
    seen = {}
    import glob
    for p in glob.glob(str(RES / "results*.jsonl")):
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); seen[r["sample_id"]] = r
    rows = [seen[i] for i in ids]

    raw_log = []
    recs = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_work_one, r, mode, raw_log): r for r in rows}
        for fut in as_completed(futs):
            recs.append(fut.result()); done += 1
            if done % 10 == 0:
                nn = sum(x.get("native_hit", False) for x in recs)
                nz = sum(x.get("zoom_hit", False) for x in recs)
                print(f"  {done}/{len(rows)}  native={nn} zoom={nz}", flush=True)

    with open(RES / f"probe50_{mode}.jsonl", "w", encoding="utf-8") as out:
        for rec in recs:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_native = sum(x.get("native_hit", False) for x in recs)
    n_zoom = sum(x.get("zoom_hit", False) for x in recs)
    done_native = sum(1 for x in recs if "native_hit" in x)
    done_zoom = sum(1 for x in recs if "zoom_hit" in x)

    print("\n=== 前 8 条原生原始输出(确认坐标约定:应是像素、非 0-1000 归一化)===")
    for s in raw_log[:8]:
        print("   ", s.replace("\n", " "))
    print(f"\n结果(50 个旧 harness 判错样,旧基线 0/50):")
    if mode in ("native", "both"):
        print(f"  原生单发     救回 {n_native}/{done_native} = {n_native/max(1,done_native):.0%}")
    if mode in ("zoom", "both"):
        print(f"  ZoomClick    救回 {n_zoom}/{done_zoom} = {n_zoom/max(1,done_zoom):.0%}")


if __name__ == "__main__":
    raise SystemExit(main())
