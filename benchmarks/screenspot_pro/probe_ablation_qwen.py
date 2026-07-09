#!/usr/bin/env python3
"""qwen3.7-plus 单发消融:归一化坐标 × OCR/YOLO 提示 的 2×2(与 GPT 版对齐)。

同一批 50 题(baseline50_ids.json)、同一检测缓存。为隔离"坐标格式/提示"两个变量、
保持分辨率恒定:4 条件都把原图 smart_resize 到 max_pixels=4M 后发同一张图。
  绝对模式:模型输出缩放图像素 → ×W/rw、×H/rh 回原图。
  归一化模式:模型输出 [0,1] → ×W,H(尺寸无关)。
提示框同样按当前坐标空间给(绝对=缩放图像素;归一化=[0,1])。
用法: python probe_ablation_qwen.py [workers] [max_pixels]
"""
from __future__ import annotations
import base64, io, json, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from PIL import Image
import httpx
from probe_repro_native import smart_resize, BASE_URL, MODEL, KEY_FILE

OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
DET_CACHE = OUT / "detect_cache"
IMG_DIR = HERE / "data" / "images"
_API_KEY = KEY_FILE.read_text(encoding="utf-8").strip()
_client = httpx.Client(timeout=380)

CONDITIONS = [("A_abs_nohint", False, False), ("B_norm_nohint", True, False),
              ("C_abs_hint", False, True), ("D_norm_hint", True, True)]


def load_m3_harness():
    import glob
    m3 = {}
    for f in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if f.endswith(".errors.jsonl"):
            continue
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    return m3


def get_det(sid):
    return json.loads((DET_CACHE / f"{sid}.json").read_text(encoding="utf-8"))


def _data_url(im):
    buf = io.BytesIO(); im.save(buf, "PNG"); raw = buf.getvalue()
    mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=92)
        raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(im, prompt):
    body = {"model": MODEL, "stream": False, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": _data_url(im)}}]}]}
    r = _client.post(f"{BASE_URL}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {_API_KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def parse(txt):
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if m:
        return float(m.group(1)), float(m.group(2))
    nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
    return (float(nums[0]), float(nums[1])) if len(nums) >= 2 else None


def build_hint(det, normalized, rw, rh, limit=120):
    W, H = det["W"], det["H"]
    lines = []
    for c in det["cands"][:limit]:
        if normalized:
            b = f"({c['x1']/W:.3f},{c['y1']/H:.3f},{c['x2']/W:.3f},{c['y2']/H:.3f})"
        else:  # 缩放图像素
            b = f"({int(c['x1']*rw/W)},{int(c['y1']*rh/H)},{int(c['x2']*rw/W)},{int(c['y2']*rh/H)})"
        lines.append(f"- \"{c['label']}\" @ {b}")
    if not lines:
        return ""
    return ("\nDetected UI elements (OCR + icon detector) as grounding evidence — the target is "
            "usually one of these, but you may click elsewhere if none fits:\n" + "\n".join(lines))


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    max_pixels = int(sys.argv[2]) if len(sys.argv) > 2 else 4014080
    m3 = load_m3_harness()
    ids = json.load(open(IDS_FILE))

    def run_condition(tag, normalized, hints):
        raw = []
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]; det = get_det(sid)
            im = Image.open(IMG_DIR / f"{sid}.png").convert("RGB")
            W, H = im.size
            rh, rw = smart_resize(H, W, max_pixels)
            sent = im.resize((rw, rh), Image.BICUBIC)
            if normalized:
                coord = ('Output ONLY JSON {"x": <float 0-1>, "y": <float 0-1>} — the NORMALIZED '
                         'center (fractions of image width/height, top-left origin).')
            else:
                coord = (f'The image is {rw}x{rh} pixels. Output ONLY JSON {{"x": <int 0-{rw}>, '
                         f'"y": <int 0-{rh}>}} — the ABSOLUTE PIXEL center of the element to click.')
            prompt = (f"This is a GUI screenshot. Find the single UI element to click for the "
                      f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                      + (build_hint(det, normalized, rw, rh) if hints else "") + "\n" + coord)
            rec = {"sample_id": sid, "group": r.get("group"),
                   "harness_correct": r["correctness"] == "correct"}
            try:
                resp = ask(sent, prompt)
                raw.append(resp[:60].replace("\n", " "))
                p = parse(resp)
                if not p:
                    rec["hit"] = False; rec["pred"] = None; return rec
                x, y = p
                if normalized or (abs(x) <= 1.5 and abs(y) <= 1.5):
                    ox, oy = x * W, y * H
                else:
                    ox, oy = x * W / rw, y * H / rh
                rec["pred"] = [int(ox), int(oy)]
                rec["hit"] = bool(gt[0] <= ox <= gt[2] and gt[1] <= oy <= gt[3])
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
            return rec
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(work, s) for s in ids]
            for i, f in enumerate(as_completed(futs)):
                recs.append(f.result())
                if (i + 1) % 20 == 0:
                    print(f"  [{tag}] {i+1}/{len(ids)}", flush=True)
        with open(OUT / f"ablation_qwen_{tag}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        return sum(x["hit"] for x in done), len(done), len(recs) - len(done), raw[:3]

    results = {}
    for tag, norm, hints in CONDITIONS:
        ok, n, err, raw = run_condition(tag, norm, hints)
        results[tag] = (ok, n)
        print(f"{tag:16s} {ok}/{n} = {ok/max(1,n):.0%}   err{err}  例:{raw[:2]}", flush=True)

    def pct(t): return t[0] / max(1, t[1])
    A, B, C, D = (results[k] for k in ["A_abs_nohint", "B_norm_nohint", "C_abs_hint", "D_norm_hint"])
    print("\n=== qwen 消融结论(同 50 题,单发,4M)===")
    print(f"  A 绝对·无提示     {pct(A):.0%}")
    print(f"  B 归一化  B-A = {(pct(B)-pct(A))*100:+.0f}pt -> {pct(B):.0%}")
    print(f"  C 提示    C-A = {(pct(C)-pct(A))*100:+.0f}pt -> {pct(C):.0%}")
    print(f"  D 组合    D-A = {(pct(D)-pct(A))*100:+.0f}pt -> {pct(D):.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
