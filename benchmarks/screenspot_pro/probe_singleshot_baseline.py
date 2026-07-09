#!/usr/bin/env python3
"""单发 baseline(归一化 [0,1] 坐标协议)via openprogram create_runtime。

发原图 + 直接问"输出归一化 [0,1] 点击坐标" → ×原图W,H → 判点∈GT框。归一化免疫
服务器端降采样(尺寸无关),四家 provider 一套协议。50 题固定集从 m3_zoom(harness
已跑)抽取,保证 M3 harness 同集可比;ids 存盘供其它 provider 复用。

用法: python probe_singleshot_baseline.py <provider> <model> <tag> [workers]
  例: ... minimax-cn-coding-plan MiniMax-M3 m3
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
M3_HARNESS = str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")

PROMPT = ("This is a GUI screenshot. Find the single UI element to click that fulfils the "
          "instruction, then give its center as NORMALIZED coordinates — fractions of the "
          "image size, top-left origin, each in [0,1].\n"
          "Instruction: {instr}\n"
          'Output ONLY JSON: {{"x": <float 0-1>, "y": <float 0-1>}}')


def load_m3_harness():
    m3 = {}
    for f in glob.glob(M3_HARNESS):
        if f.endswith(".errors.jsonl"):
            continue
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    return m3


def get_ids(m3):
    if IDS_FILE.exists():
        return json.load(open(IDS_FILE))
    ids = sorted(m3)
    step = max(1, len(ids) // 50)
    sel = ids[::step][:50]
    json.dump(sel, open(IDS_FILE, "w"))
    return sel


def parse_norm(txt):
    """返回 (nx,ny) ∈ [0,1] 或 None。兼容 [0,1]/[0,1000]/[0,100]。"""
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', txt, re.S)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
    else:
        nums = re.findall(r'-?\d+(?:\.\d+)?', txt)
        if len(nums) < 2:
            return None
        x, y = float(nums[0]), float(nums[1])
    if abs(x) <= 1.5 and abs(y) <= 1.5:
        return x, y
    if x <= 1000 and y <= 1000:
        return x / 1000.0, y / 1000.0
    return None


def main():
    from gui_harness.openprogram_compat import create_runtime
    provider, model, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 4

    m3 = load_m3_harness()
    ids = get_ids(m3)
    rt = create_runtime(provider=provider, model=model, max_retries=3)
    raw_log = []

    def work(sid):
        r = m3[sid]; gt = r["gt_bbox"]
        img = IMG_DIR / f"{sid}.png"
        base = {"sample_id": sid, "group": r.get("group"), "gt_bbox": gt,
                "harness_correct": r["correctness"] == "correct"}
        try:
            im = Image.open(img); W, H = im.size
            content = [{"type": "text", "text": PROMPT.format(instr=r["instruction"])},
                       {"type": "image", "path": str(img)}]
            resp = rt.exec(content=content, timeout_s=150) or ""
            raw_log.append(resp[:70].replace("\n", " "))
            pn = parse_norm(resp)
            if pn is None:
                base.update(single_pred=None, single_hit=False)
                return base
            px, py = pn[0] * W, pn[1] * H
            base.update(single_pred=[int(px), int(py)],
                        single_hit=bool(gt[0] <= px <= gt[2] and gt[1] <= py <= gt[3]))
            return base
        except Exception as e:
            base.update(error=f"{type(e).__name__}: {str(e)[:110]}")
            return base

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, s) for s in ids]
        for i, f in enumerate(as_completed(futs)):
            recs.append(f.result())
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(ids)} single={sum(x.get('single_hit', False) for x in recs)}", flush=True)

    with open(OUT / f"singleshot_{tag}.jsonl", "w", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")

    done = [x for x in recs if "single_hit" in x]
    errs = [x for x in recs if "error" in x]
    sh = sum(x["single_hit"] for x in done)
    hc = sum(x.get("harness_correct", False) for x in done)
    print(f"\n[{tag}] {provider}/{model}  同 {len(done)} 题(+{len(errs)}err)")
    print(f"   单发 baseline(归一化) {sh}/{len(done)} = {sh/max(1,len(done)):.0%}")
    print(f"   harness 同题          {hc}/{len(done)} = {hc/max(1,len(done)):.0%}")
    print("   前5条原始:", raw_log[:5])
    if errs:
        print("   err样例:", errs[0].get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
