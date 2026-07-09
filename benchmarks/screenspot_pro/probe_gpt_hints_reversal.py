#!/usr/bin/env python3
"""GPT-5.5 探针B/C:hints on/off,在母语格式(abs_pixel)和非母语格式(frac01)各测一次。
诊断目标:证据注入效应的符号是否随格式反转(qwen 的专训头signature,GPT 预期不反转)。
同 probe_m3_hints_reversal.py 的方法论,走 openprogram Runtime.exec()(provider=openai-codex)。
用法: python probe_gpt_hints_reversal.py [workers]
"""
from __future__ import annotations
import json, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from PIL import Image
from gui_harness.planning import coord_formats as cf
from gui_harness.openprogram_compat import create_runtime

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
PROVIDER = "openai-codex"
MODEL = "gpt-5.5"

# abs_pixel 是 GPT 的母语格式(62%,消融最优),frac01 是它最差的格式(50%)
CONDITIONS = [("abs_pixel", "native"), ("frac01", "foreign")]

_rt = create_runtime(provider=PROVIDER, model=MODEL, max_retries=3)


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


def ask(img_path, instr, fmt, hint, W, H):
    prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
              f"instruction, then give its click point.\nInstruction: {instr}\n"
              + hint + "\n" + cf.prompt_suffix(fmt, W, H))
    content = [{"type": "text", "text": prompt}, {"type": "image", "path": str(img_path)}]
    return _rt.exec(content=content, timeout_s=150) or ""


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))

    results = {}
    for fmt, tag in CONDITIONS:
        for use_hint in (False, True):
            key = f"{tag}_{fmt}_{'hint' if use_hint else 'nohint'}"
            out_path = OUT / f"gpt_reversal_{key}.jsonl"
            done = set()
            if out_path.exists():
                for l in open(out_path, encoding="utf-8"):
                    if l.strip():
                        try:
                            done.add(json.loads(l)["sample_id"])
                        except Exception:
                            pass
            todo = [sid for sid in ids if sid not in done]

            def work(sid):
                r = m3[sid]
                gt = r["gt_bbox"]
                try:
                    im = Image.open(IMG_DIR / f"{sid}.png")
                    W, H = im.size
                    hint = build_hint_block(IMG_DIR / f"{sid}.png", fmt) if use_hint else ""
                    resp = ask(IMG_DIR / f"{sid}.png", r["instruction"], fmt, hint, W, H)
                    p = cf.parse_point(resp, fmt, W, H)
                    if not p:
                        return {"sample_id": sid, "hit": False}
                    return {"sample_id": sid,
                            "hit": bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])}
                except Exception as e:
                    return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:100]}"}

            out_f = open(out_path, "a", encoding="utf-8")
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for f in as_completed([ex.submit(work, s) for s in todo]):
                    rr = f.result()
                    out_f.write(json.dumps(rr, ensure_ascii=False) + "\n")
                    out_f.flush()
            out_f.close()

            recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
            done_r = [x for x in recs if "hit" in x]
            ok = sum(x["hit"] for x in done_r)
            results[key] = (ok, len(done_r))
            print(f"[GPT {key:22s}] {ok}/{len(done_r)} = {ok/max(1,len(done_r)):.0%}", flush=True)

    print("\n=== 反转检验 ===")
    for tag in ("native", "foreign"):
        fmt = [f for f, t in CONDITIONS if t == tag][0]
        no_ok, no_n = results[f"{tag}_{fmt}_nohint"]
        hi_ok, hi_n = results[f"{tag}_{fmt}_hint"]
        delta = hi_ok / max(1, hi_n) - no_ok / max(1, no_n)
        print(f"{tag:8s}({fmt:10s}): 无提示 {no_ok}/{no_n} -> 有提示 {hi_ok}/{hi_n}  "
              f"提示效应 = {delta*100:+.0f}pt")


if __name__ == "__main__":
    raise SystemExit(main())
