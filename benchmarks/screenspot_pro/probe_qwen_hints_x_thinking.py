#!/usr/bin/env python3
"""hints x thinking 2x2,只测 22 题难样本子集(之前提示条件下有分歧的题)。
控制 enable_thinking 变量,看"提示拖累qwen"是不是因为 thinking 状态没控制住导致的假象。
用法: python probe_qwen_hints_x_thinking.py [workers]
"""
from __future__ import annotations
import base64, io, json, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))

from gui_harness.planning import coord_formats as cf
from probe_qwen_hints_relevance import build_relevance_hint
from run_sspro_native import IMG_DIR

OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "hard_subset_ids.json"
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"
FMT = "point2d_1000"
_client = httpx.Client(timeout=380)


def data_url(path):
    raw = Path(path).read_bytes(); mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        im = Image.open(io.BytesIO(raw)).convert("RGB"); buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92); raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(path, prompt, thinking):
    body = {"model": MODEL, "stream": False, "vl_high_resolution_images": True,
            "enable_thinking": thinking,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url(path)}}]}]}
    r = _client.post(f"{BASE}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))

    results = {}
    for use_hint in [False, True]:
        for thinking in [False, True]:
            tag = f"{'hint' if use_hint else 'nohint'}_{'think' if thinking else 'nothink'}"
            def work(sid):
                r = m3[sid]; gt = r["gt_bbox"]
                img_path = IMG_DIR / f"{sid}.png"
                rec = {"sample_id": sid}
                try:
                    im = Image.open(img_path); W, H = im.size
                    hint = build_relevance_hint(img_path, r["instruction"], 12) if use_hint else ""
                    prompt = ("This is a GUI screenshot. Find the single UI element to click for "
                              f"the instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                              + hint + "\n" + cf.prompt_suffix(FMT, W, H))
                    resp = ask(img_path, prompt, thinking)
                    p = cf.parse_point(resp, FMT, W, H)
                    rec["hit"] = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
                except Exception as e:
                    rec["error"] = f"{type(e).__name__}: {str(e)[:90]}"
                return rec
            recs = []
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for f in as_completed([ex.submit(work, s) for s in ids]):
                    recs.append(f.result())
            with open(OUT / f"qwen_hintsxthink_{tag}.jsonl", "w", encoding="utf-8") as o:
                for rr in recs:
                    o.write(json.dumps(rr, ensure_ascii=False) + "\n")
            done = [x for x in recs if "hit" in x]
            ok = sum(x["hit"] for x in done)
            results[tag] = (ok, len(done))
            print(f"[{tag:16s}] {ok}/{len(done)} = {ok/max(1,len(done)):.0%}  (+{len(recs)-len(done)}err)", flush=True)

    print("\n=== 2x2 汇总(22题难样本子集)===")
    print(f"{'':10s} {'thinking关':>12s} {'thinking开':>12s}")
    for use_hint, label in [(False,'无提示'),(True,'relevance提示')]:
        row = []
        for thinking in [False, True]:
            tag = f"{'hint' if use_hint else 'nohint'}_{'think' if thinking else 'nothink'}"
            ok, n = results[tag]
            row.append(f"{ok}/{n}={ok/max(1,n):.0%}")
        print(f"{label:10s} {row[0]:>12s} {row[1]:>12s}")


if __name__ == "__main__":
    raise SystemExit(main())
