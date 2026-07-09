#!/usr/bin/env python3
"""GPT-5.5 单发消融:归一化坐标 × OCR/YOLO 提示 的 2×2。

同一批 50 题(baseline50_ids.json)、全单发、不套迭代裁剪。隔离两个变量:
  A_abs_nohint  绝对像素 / 无提示   (基线)
  B_norm_nohint 归一化   / 无提示   (归一化效果 = B-A)
  C_abs_hint    绝对像素 / 注入候选 (提示效果   = C-A)
  D_norm_hint   归一化   / 注入候选 (组合)

候选 = 与 harness 同源的 GPA-YOLO + OCR(detect_components),但作为静态文本提示注入
单发提示里,不做迭代裁剪。检测按图缓存。判分点∈GT框。
用法: python probe_ablation_gpt.py [workers]
"""
from __future__ import annotations
import glob, json, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from PIL import Image

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
OUT.mkdir(parents=True, exist_ok=True)
IDS_FILE = OUT / "baseline50_ids.json"
DET_CACHE = OUT / "detect_cache"; DET_CACHE.mkdir(exist_ok=True)
PROVIDER, MODEL = "openai-codex", "gpt-5.5"

CONDITIONS = [  # (tag, normalized, hints)
    ("A_abs_nohint", False, False),
    ("B_norm_nohint", True, False),
    ("C_abs_hint", False, True),
    ("D_norm_hint", True, True),
]

COORD_ABS = ('The screenshot is {W}x{H} pixels. Output ONLY JSON {{"x": <int 0-{W}>, '
             '"y": <int 0-{H}>}} — the ABSOLUTE PIXEL center of the element to click.')
COORD_NORM = ('Output ONLY JSON {{"x": <float 0-1>, "y": <float 0-1>}} — the NORMALIZED '
              'center (fractions of image width/height, top-left origin).')


def load_m3_harness():
    m3 = {}
    for f in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if f.endswith(".errors.jsonl"):
            continue
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    return m3


def get_detection(sid):
    """检测缓存:返回 {W,H,cands:[{label,x1,y1,x2,y2}]}。"""
    cf = DET_CACHE / f"{sid}.json"
    if cf.exists():
        return json.loads(cf.read_text(encoding="utf-8"))
    from gui_harness.planning.component_memory import detect_components
    from gui_harness.planning import active_localization
    img = str(IMG_DIR / f"{sid}.png")
    det = detect_components(img)
    cands = active_localization.build_candidates([], det["texts"], det["icons"])
    out = {"W": det["img_w"], "H": det["img_h"], "cands": []}
    for c in cands:
        x = c.get("x"); y = c.get("y"); w = c.get("w"); h = c.get("h")
        if None in (x, y, w, h):
            continue
        label = (c.get("label") or c.get("text") or c.get("type") or "element")
        out["cands"].append({"label": str(label)[:40], "x1": int(x), "y1": int(y),
                             "x2": int(x + w), "y2": int(y + h)})
    cf.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def build_hint(det, normalized, limit=120):
    W, H = det["W"], det["H"]
    lines = []
    for c in det["cands"][:limit]:
        if normalized:
            box = f"({c['x1']/W:.3f},{c['y1']/H:.3f},{c['x2']/W:.3f},{c['y2']/H:.3f})"
        else:
            box = f"({c['x1']},{c['y1']},{c['x2']},{c['y2']})"
        lines.append(f"- \"{c['label']}\" @ {box}")
    if not lines:
        return ""
    return ("\nDetected UI elements (OCR + icon detector) as grounding evidence — the target "
            "is usually one of these, but you may click elsewhere if none fits:\n" + "\n".join(lines))


def parse_xy(txt, W, H):
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
    else:
        nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
        if len(nums) < 2:
            return None
        x, y = float(nums[0]), float(nums[1])
    if abs(x) <= 1.5 and abs(y) <= 1.5:       # 归一化
        return x * W, y * H
    if x <= 1000 and y <= 1000 and (W > 1200 or H > 1200) and max(x, y) <= 1000 and False:
        pass
    return x, y                                # 绝对像素


def main():
    from gui_harness.openprogram_compat import create_runtime
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    m3 = load_m3_harness()
    ids = json.load(open(IDS_FILE))

    print(f"预计算 {len(ids)} 张图的 YOLO+OCR 检测(缓存)...", flush=True)
    for i, sid in enumerate(ids):
        get_detection(sid)
        if (i + 1) % 10 == 0:
            print(f"  det {i+1}/{len(ids)}", flush=True)

    rt = create_runtime(provider=PROVIDER, model=MODEL, max_retries=3)

    def run_condition(tag, normalized, hints):
        raw = []
        def work(sid):
            r = m3[sid]; gt = r["gt_bbox"]; det = get_detection(sid)
            W, H = det["W"], det["H"]
            coord = COORD_NORM if normalized else COORD_ABS.format(W=W, H=H)
            prompt = (f"This is a GUI screenshot. Find the single UI element to click for the "
                      f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                      + (build_hint(det, normalized) if hints else "") + "\n" + coord)
            rec = {"sample_id": sid, "group": r.get("group"),
                   "harness_correct": r["correctness"] == "correct"}
            try:
                content = [{"type": "text", "text": prompt},
                           {"type": "image", "path": str(IMG_DIR / f"{sid}.png")}]
                resp = rt.exec(content=content, timeout_s=150) or ""
                raw.append(resp[:60].replace("\n", " "))
                p = parse_xy(resp, W, H)
                rec["hit"] = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
                rec["pred"] = [int(p[0]), int(p[1])] if p else None
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
            return rec
        recs = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(work, s) for s in ids]
            for f in as_completed(futs):
                recs.append(f.result())
        with open(OUT / f"ablation_gpt_{tag}.jsonl", "w", encoding="utf-8") as o:
            for rr in recs:
                o.write(json.dumps(rr, ensure_ascii=False) + "\n")
        done = [x for x in recs if "hit" in x]
        return sum(x["hit"] for x in done), len(done), len(recs) - len(done), raw[:3]

    print(f"\n{'条件':16s} {'单发正确率':>10s}   (同 50 题, harness 基准 47.4% M3 / GPT-zoom 88.7%)")
    results = {}
    for tag, norm, hints in CONDITIONS:
        ok, n, err, raw = run_condition(tag, norm, hints)
        results[tag] = (ok, n, err)
        print(f"{tag:16s} {ok}/{n} = {ok/max(1,n):.0%}   err{err}  例:{raw[:2]}", flush=True)

    A = results["A_abs_nohint"]; B = results["B_norm_nohint"]
    C = results["C_abs_hint"]; D = results["D_norm_hint"]
    def pct(t): return t[0] / max(1, t[1])
    print("\n=== 消融结论(同 50 题, GPT-5.5 单发)===")
    print(f"  A 基线(绝对,无提示)     {pct(A):.0%}")
    print(f"  B 归一化效果  B-A = {(pct(B)-pct(A))*100:+.0f}pt   -> {pct(B):.0%}")
    print(f"  C 提示效果    C-A = {(pct(C)-pct(A))*100:+.0f}pt   -> {pct(C):.0%}")
    print(f"  D 组合        D-A = {(pct(D)-pct(A))*100:+.0f}pt   -> {pct(D):.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
