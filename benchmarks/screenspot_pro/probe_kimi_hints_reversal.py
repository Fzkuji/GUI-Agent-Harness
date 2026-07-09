#!/usr/bin/env python3
"""kimi-k2.6 探针B/C:hints on/off,在母语格式(frac01)和非母语格式(abs_pixel)各测一次。
诊断目标:证据注入效应的符号是否随格式反转(qwen 的专训头signature)。
baseline50,同 run_sspro_native.py 的 _build_hint_block 逻辑。
用法: python probe_kimi_hints_reversal.py [workers]
"""
from __future__ import annotations
import base64, io, json, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from PIL import Image
import httpx
from gui_harness.planning import coord_formats as cf

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.6"
_client = httpx.Client(timeout=380)

# (格式, 标签) — frac01 是 kimi 的母语格式(60%),abs_pixel 是它最差的格式(19%)
CONDITIONS = [("frac01", "native"), ("abs_pixel", "foreign")]


def data_url(path):
    raw = Path(path).read_bytes(); mime = "image/png"
    if len(raw) > 9 * 1024 * 1024:
        im = Image.open(io.BytesIO(raw)).convert("RGB"); buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92); raw = buf.getvalue(); mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def build_hint_block(img_path, coord_format):
    from gui_harness.planning.component_memory import detect_components
    from gui_harness.planning import active_localization
    det = detect_components(str(img_path))
    W, H = det["img_w"], det["img_h"]
    cands = active_localization.build_candidates([], det["texts"], det["icons"])
    lines = []
    for c in cands[:120]:
        x, y, w, h = c.get("x"), c.get("y"), c.get("w"), c.get("h")
        if None in (x, y, w, h):
            continue
        label = str(c.get("label") or c.get("text") or c.get("type") or "element")[:40]
        if coord_format == "abs_pixel":
            box = f"({int(x)},{int(y)},{int(x + w)},{int(y + h)})"
        else:
            box = f"({int(x/W*1000)},{int(y/H*1000)},{int((x+w)/W*1000)},{int((y+h)/H*1000)})"
        lines.append(f'- "{label}" @ {box}')
    if not lines:
        return ""
    return ("\nDetected UI elements (OCR + icon detector) as grounding evidence — the "
            "target is usually one of these, but you may click elsewhere if none fits:\n"
            + "\n".join(lines))


def ask(path, instr, fmt, hint, W, H):
    prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
              f"instruction, then give its click point.\nInstruction: {instr}\n"
              + hint + "\n" + cf.prompt_suffix(fmt, W, H))
    body = {"model": MODEL, "stream": False, "enable_thinking": False,
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
    for fmt, tag in CONDITIONS:
        for use_hint in (False, True):
            key = f"{tag}_{fmt}_{'hint' if use_hint else 'nohint'}"

            def work(sid):
                r = m3[sid]; gt = r["gt_bbox"]
                try:
                    im = Image.open(IMG_DIR / f"{sid}.png"); W, H = im.size
                    hint = build_hint_block(IMG_DIR / f"{sid}.png", fmt) if use_hint else ""
                    resp = ask(IMG_DIR / f"{sid}.png", r["instruction"], fmt, hint, W, H)
                    p = cf.parse_point(resp, fmt, W, H)
                    if not p:
                        return {"sample_id": sid, "hit": False}
                    return {"sample_id": sid,
                            "hit": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])}
                except Exception as e:
                    return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:100]}"}

            recs = []
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for f in as_completed([ex.submit(work, s) for s in ids]):
                    recs.append(f.result())
            with open(OUT / f"kimi_reversal_{key}.jsonl", "w", encoding="utf-8") as o:
                for rr in recs:
                    o.write(json.dumps(rr, ensure_ascii=False) + "\n")
            done = [x for x in recs if "hit" in x]
            ok = sum(x["hit"] for x in done)
            results[key] = (ok, len(done))
            print(f"[kimi {key:22s}] {ok}/{len(done)} = {ok/max(1,len(done)):.0%}", flush=True)

    print("\n=== 反转检验 ===")
    for tag in ("native", "foreign"):
        fmt = dict(CONDITIONS)[tag] if False else [f for f, t in CONDITIONS if t == tag][0]
        no_ok, no_n = results[f"{tag}_{fmt}_nohint"]
        hi_ok, hi_n = results[f"{tag}_{fmt}_hint"]
        delta = hi_ok / max(1, hi_n) - no_ok / max(1, no_n)
        print(f"{tag:8s}({fmt:10s}): 无提示 {no_ok}/{no_n} -> 有提示 {hi_ok}/{hi_n}  "
              f"提示效应 = {delta*100:+.0f}pt")


if __name__ == "__main__":
    raise SystemExit(main())
