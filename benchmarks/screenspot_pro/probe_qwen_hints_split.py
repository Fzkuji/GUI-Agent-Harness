#!/usr/bin/env python3
"""把 OCR 候选和 icon-detector 候选拆开单独测,看是不是合并在一起把一个正向信号平均掉了。
22 题难样本子集,thinking=False(已确认的最优),relevance 排序+top-12。
用法: python probe_qwen_hints_split.py [workers]
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
from gui_harness.planning.component_memory import detect_components
from gui_harness.planning import active_localization
from run_sspro_native import IMG_DIR

OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "hard_subset_ids.json"
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"
FMT = "point2d_1000"
_client = httpx.Client(timeout=380)


def build_hint(img_path: Path, instruction: str, source: str, topk: int = 12) -> str:
    """source: 'ocr' | 'detector' | 'both'."""
    det = detect_components(str(img_path))
    W, H = det["img_w"], det["img_h"]
    texts = det["texts"] if source in ("ocr", "both") else []
    icons = det["icons"] if source in ("detector", "both") else []
    cands = active_localization.build_candidates([], texts, icons)
    cands = sorted(
        cands,
        key=lambda c: (active_localization._candidate_relevance(instruction, c),
                       float(c.get("confidence", 0) or 0)),
        reverse=True,
    )
    lines = []
    for c in cands[:topk]:
        x, y, w, h = c.get("x"), c.get("y"), c.get("w"), c.get("h")
        if None in (x, y, w, h):
            continue
        label = str(c.get("label") or c.get("text") or c.get("type") or "element")[:40]
        nb = (f"({int(x / W * 1000)},{int(y / H * 1000)},"
              f"{int((x + w) / W * 1000)},{int((y + h) / H * 1000)})")
        lines.append(f'- "{label}" @ {nb}')
    if not lines:
        return ""
    tag = {"ocr": "OCR text", "detector": "icon detector", "both": "OCR + icon detector"}[source]
    return (f"\nMost relevant detected UI elements ({tag}, ranked by match to the instruction) — "
            "the target is usually one of these, but you may click elsewhere if none fits:\n"
            + "\n".join(lines))


def data_url(path):
    raw = Path(path).read_bytes(); mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        im = Image.open(io.BytesIO(raw)).convert("RGB"); buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92); raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def ask(path, prompt):
    body = {"model": MODEL, "stream": False, "vl_high_resolution_images": True,
            "enable_thinking": False,
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
    for source in ["ocr", "detector"]:
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]
            img_path = IMG_DIR / f"{sid}.png"
            rec = {"sample_id": sid}
            try:
                im = Image.open(img_path); W, H = im.size
                hint = build_hint(img_path, r["instruction"], source)
                prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
                          f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                          + hint + "\n" + cf.prompt_suffix(FMT, W, H))
                resp = ask(img_path, prompt)
                p = cf.parse_point(resp, FMT, W, H)
                rec["hit"] = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {str(e)[:90]}"
            return rec
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for f in as_completed([ex.submit(work, s) for s in ids]):
                recs.append(f.result())
        with open(OUT / f"qwen_hints_split_{source}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        ok = sum(x["hit"] for x in done)
        results[source] = (ok, len(done))
        print(f"[{source:9s}] {ok}/{len(done)} = {ok/max(1,len(done)):.0%}  (+{len(recs)-len(done)}err)", flush=True)

    print("\n对照(同22题子集,thinking关): 无提示64% / relevance两者合并32%")


if __name__ == "__main__":
    raise SystemExit(main())
