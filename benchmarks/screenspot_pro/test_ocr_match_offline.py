#!/usr/bin/env python3
"""离线测试:确定性 OCR 文本匹配在 UI-Vision 切片上的精度/覆盖率。

对切片每行:跑检测(GPU,无 LLM),用生产路径的 _deterministic_text_match
(component_memory Phase 1.5)对指令做字面匹配,与 gt_bbox 判分。

输出三类统计:
  - coverage:多少行能匹配到
  - precision:匹配到的行里多少命中 gt
  - rescue:在 zoom 臂答错的行里能救回多少 / 在答对的行里会破坏多少
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from gui_harness.planning.component_memory import detect_components, _deterministic_text_match  # noqa: E402


def in_box(px, py, b):
    return b[0] <= px <= b[2] and b[1] <= py <= b[3]


def main() -> int:
    zoom_rows = {}
    for p in glob.glob(str(REPO / "runs/ui_vision_gpt_zoom/*.jsonl")):
        if p.endswith("errors.jsonl"):
            continue
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            zoom_rows[r["sample_id"]] = r

    # sample_id -> image path
    ann_dir = HERE / "data_ui_vision" / "annotations"
    img_dir = HERE / "data_ui_vision" / "raw_images"
    id2img = {}
    for ann in ann_dir.glob("ui_vision_*.json"):
        for s in json.loads(ann.read_text(encoding="utf-8")):
            id2img[s["id"]] = img_dir / s.get("raw_image_path", s.get("img_filename", ""))

    cov = hit = 0
    rescue = brk = 0
    n = 0
    examples = []
    for sid, r in sorted(zoom_rows.items()):
        img_p = id2img.get(sid)
        if not img_p or not img_p.exists():
            continue
        n += 1
        det = detect_components(str(img_p))
        m = _deterministic_text_match(r["instruction"], det["texts"])
        if not m:
            continue
        cov += 1
        good = in_box(m["cx"], m["cy"], r["gt_bbox"])
        hit += good
        zoom_ok = r.get("correctness") == "correct"
        if good and not zoom_ok:
            rescue += 1
            examples.append(("RESCUE", sid, r["instruction"][:40]))
        elif not good and zoom_ok:
            brk += 1
            examples.append(("BREAK", sid, r["instruction"][:40]))
        if n % 50 == 0:
            print(f"  {n} rows... cov={cov} hit={hit} rescue={rescue} break={brk}", flush=True)

    print(f"\nrows={n}  coverage={cov} ({cov/max(1,n):.1%})  "
          f"precision={hit}/{cov} ({hit/max(1,cov):.1%})")
    print(f"vs zoom arm: rescues={rescue}  breaks={brk}  net={rescue-brk:+d}")
    for tag, sid, instr in examples[:20]:
        print(f"  {tag} {sid} {instr!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
