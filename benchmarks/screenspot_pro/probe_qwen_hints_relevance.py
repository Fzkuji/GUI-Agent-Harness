#!/usr/bin/env python3
"""证明"候选证据"这个方法本身有没有用——不是弃用,是换成生产级的相关性排序+精简候选。

之前 probe_qwen_hints_on_best.py 测的是原始堆砌(120条,检测器原序,无排序无去重),
结果 -17pt。但 GPT 用同样粗糙的堆砌反而 +16——说明不是"候选没用",是"这版候选提示太糙"。
harness 生产代码本来就有 candidate_sort="relevance"(_candidate_relevance 按指令关键词/OCR
类型打分)+ 去重 + 限量,这次单发探针一直没用上。这里补上,测 relevance-sorted top-K。
用法: python probe_qwen_hints_relevance.py [workers] [topk]
"""
from __future__ import annotations
import json, sys, glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from PIL import Image

from gui_harness.planning import coord_formats as cf
from gui_harness.planning.component_memory import detect_components
from gui_harness.planning import active_localization
from run_sspro_native import _make_aliyun_call, IMG_DIR

OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
MODEL = "qwen3.7-plus"
FMT = "point2d_1000"


def build_relevance_hint(img_path: Path, instruction: str, topk: int) -> str:
    det = detect_components(str(img_path))
    W, H = det["img_w"], det["img_h"]
    cands = active_localization.build_candidates([], det["texts"], det["icons"])
    # 生产级排序:_candidate_relevance(按指令关键词/OCR匹配打分) + confidence 兜底
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
    return ("\nMost relevant detected UI elements (OCR + icon detector, ranked by match to the "
            "instruction) — the target is usually one of these, but you may click elsewhere if "
            "none fits:\n" + "\n".join(lines))


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    topk = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    call = _make_aliyun_call(MODEL, hires=True)

    def work(sid):
        r = m3[sid]; gt = r["gt_bbox"]
        img_path = IMG_DIR / f"{sid}.png"
        rec = {"sample_id": sid}
        try:
            im = Image.open(img_path); W, H = im.size
            hint = build_relevance_hint(img_path, r["instruction"], topk)
            prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
                      f"instruction, then give its click point.\nInstruction: {r['instruction']}\n"
                      + hint + "\n" + cf.prompt_suffix(FMT, W, H))
            resp = call(prompt, img_path)
            p = cf.parse_point(resp, FMT, W, H)
            if p is None:
                rec["prediction_px"] = None; rec["hit"] = False
            else:
                cx, cy = int(p[0]), int(p[1])
                rec["prediction_px"] = [cx, cy]
                rec["hit"] = bool(gt[0] <= cx <= gt[2] and gt[1] <= cy <= gt[3])
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        return rec

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in ids]):
            recs.append(f.result())
    with open(OUT / f"qwen_hints_relevance_top{topk}.jsonl", "w", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    done = [x for x in recs if "hit" in x]
    ok = sum(x["hit"] for x in done)
    print(f"[relevance top{topk}] point2d_1000+hires: {ok}/{len(done)} = {ok/max(1,len(done)):.0%} "
          f"(+{len(recs)-len(done)}err)", flush=True)
    print("对照: 无提示77% / 原始堆砌120条60%")


if __name__ == "__main__":
    raise SystemExit(main())
