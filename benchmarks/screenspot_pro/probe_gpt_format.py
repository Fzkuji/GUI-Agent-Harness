#!/usr/bin/env python3
"""GPT-5.5 坐标格式消融:绝对像素 / [0,1000]{x,y} / point_2d[0,1000]。单发无提示,同 50 题。
检查 GPT 是否也像 qwen 一样有"喂对格式"的隐藏余量。已知:绝对≈58%、[0,1]分数=50%。
用法: python probe_gpt_format.py [workers]
"""
from __future__ import annotations
import json, re, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from PIL import Image

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"

FORMATS = {
    "abs":     ('The screenshot is {W}x{H} pixels. Output ONLY JSON {{"x": <int 0-{W}>, '
                '"y": <int 0-{H}>}} — absolute pixel center of the element to click.'),
    "xy1000":  ('Output ONLY JSON {{"x": <int 0-1000>, "y": <int 0-1000>}} — the click point '
                'normalized to [0,1000] (0=left/top, 1000=right/bottom).'),
    "point2d": ('Output ONLY JSON {{"point_2d": [x, y]}} where x,y are integers in [0,1000] '
                'normalized to the image (0=left/top, 1000=right/bottom).'),
}


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
    if fmt == "abs":
        if x <= 1.5 and y <= 1.5:      # 模型偶尔归一化
            return x * W, y * H
        return x, y
    # 归一化格式
    if x <= 1.5 and y <= 1.5:
        return x * W, y * H
    if x <= 1000 and y <= 1000:
        return x / 1000 * W, y / 1000 * H
    return x, y


def main():
    from gui_harness.openprogram_compat import create_runtime
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    rt = create_runtime(provider="openai-codex", model="gpt-5.5", max_retries=3)

    for fmt, coord in FORMATS.items():
        raw = []
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]
            try:
                im = Image.open(IMG_DIR / f"{sid}.png"); W, H = im.size
                prompt = (f"This is a GUI screenshot. Find the single UI element to click for the "
                          f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                          + coord.format(W=W, H=H))
                content = [{"type": "text", "text": prompt},
                           {"type": "image", "path": str(IMG_DIR / f"{sid}.png")}]
                resp = rt.exec(content=content, timeout_s=150) or ""
                raw.append(resp[:50].replace("\n", " "))
                p = parse(resp, W, H, fmt)
                if not p:
                    return {"sample_id": sid, "hit": False}
                return {"sample_id": sid, "hit": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])}
            except Exception as e:
                return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:90]}"}
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in ids]):
                recs.append(f.result())
        with open(OUT / f"gpt_format_{fmt}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done)
        print("[GPT %-8s] %d/%d = %.0f%% (+%derr)  例:%s"
              % (fmt, ok, len(done), 100 * ok / max(1, len(done)), len(recs) - len(done), raw[:2]),
              flush=True)
    print("对照: 之前 GPT 绝对=58% / [0,1]分数=50%")


if __name__ == "__main__":
    raise SystemExit(main())
