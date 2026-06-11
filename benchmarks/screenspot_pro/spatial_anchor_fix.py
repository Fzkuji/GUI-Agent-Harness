#!/usr/bin/env python3
"""spatial 锚点几何修正——离线评估器。

UI-Vision spatial 指令的形态:'What is the element that is immediately to the
right of the "xxx"' / 'nearest and located vertically above the "yyy"'。

机制(零 LLM 调用):
  1. 从指令解析方向 + 引号锚点名。
  2. OCR 在屏幕上找锚点文本(唯一、高分匹配才继续;模糊则跳过)。
  3. 校验当前答案是否满足"在锚点的该方向"——满足 → 不动(对的答案天然满足);
     明显违反 → 用"该方向上离锚点最近的检测元素中心"替换。
  4. 离线对 gt 判分,输出 rescue/break/keep 统计。

仅评估,不改结果文件;若净收益达标再并入 v5c。
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from gui_harness.planning.component_memory import detect_components  # noqa: E402
from gui_harness.planning import active_localization as active  # noqa: E402


def parse_relation(instr: str):
    """返回 (direction, anchor) 或 None。direction ∈ left/right/above/below。"""
    m = re.search(r'"([^"]{2,60})"', instr)
    if not m:
        return None
    anchor = m.group(1).strip()
    low = instr.lower()
    if "right of" in low:
        return "right", anchor
    if "left of" in low:
        return "left", anchor
    if "above" in low or "top of" in low:
        return "above", anchor
    if "below" in low or "under" in low or "beneath" in low:
        return "below", anchor
    return None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def find_anchor(texts: list[dict], anchor: str):
    """OCR 找锚点:归一化后包含匹配,得分=覆盖率;要求唯一最优。"""
    na = norm(anchor)
    if len(na) < 3:
        return None
    scored = []
    for t in texts:
        label = norm(t.get("label") or "")
        if not label:
            continue
        if na in label or label in na:
            cover = min(len(na), len(label)) / max(len(na), len(label))
            if cover >= 0.5:
                scored.append((cover, t))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    # 唯一性:次优分数明显低于最优才接受(防多处同名误锚)
    if len(scored) > 1 and scored[1][0] >= scored[0][0] * 0.95:
        return None
    return scored[0][1]


def box_of(c: dict) -> list[float]:
    b = active._candidate_box(c)
    return [float(v) for v in b]


def satisfies(pt, abox, direction, tol=14) -> bool:
    x, y = pt
    ax1, ay1, ax2, ay2 = abox
    if direction == "right":
        return x >= ax2 - tol and (ay1 - 60) <= y <= (ay2 + 60)
    if direction == "left":
        return x <= ax1 + tol and (ay1 - 60) <= y <= (ay2 + 60)
    if direction == "below":
        return y >= ay2 - tol and (ax1 - 80) <= x <= (ax2 + 80)
    if direction == "above":
        return y <= ay1 + tol and (ax1 - 80) <= x <= (ax2 + 80)
    return True


def pick_replacement(cands, abox, direction, anchor_label):
    """该方向上离锚点最近的元素(排除锚点自身)。"""
    ax1, ay1, ax2, ay2 = abox
    acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
    best = None
    for c in cands:
        b = box_of(c)
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if norm(c.get("label") or "") == norm(anchor_label or "") and c.get("label"):
            continue
        # 与锚点框重叠太多 = 锚点自己,跳过
        if abs(cx - acx) < 4 and abs(cy - acy) < 4:
            continue
        if not satisfies((cx, cy), abox, direction, tol=0):
            continue
        if direction in ("left", "right"):
            dist = abs(cx - acx) + 2.0 * abs(cy - acy)   # 同行优先
        else:
            dist = abs(cy - acy) + 2.0 * abs(cx - acx)   # 同列优先
        if best is None or dist < best[0]:
            best = (dist, cx, cy, c.get("label") or "")
    return best


def in_box(p, b):
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows-glob", default="runs/ui_vision_arbitrated/v5b_shard*.jsonl")
    args = ap.parse_args()

    rows = {}
    for p in glob.glob(str(REPO / args.rows_glob)):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            if r["sample_id"].split("_")[-2] == "spatial":
                rows[r["sample_id"]] = r

    ann_dir = HERE / "data_ui_vision" / "annotations"
    img_dir = HERE / "data_ui_vision" / "raw_images"
    id2img = {}
    for ann in ann_dir.glob("ui_vision_*.json"):
        for s in json.loads(ann.read_text(encoding="utf-8")):
            id2img[s["id"]] = img_dir / s.get("raw_image_path", s.get("img_filename", ""))

    stats = {"no_rel": 0, "no_anchor": 0, "keep_sat": 0, "replace": 0, "no_repl": 0}
    rescue = brk = 0
    events = []
    for i, (sid, r) in enumerate(sorted(rows.items())):
        rel = parse_relation(r["instruction"])
        if not rel:
            stats["no_rel"] += 1
            continue
        direction, anchor = rel
        img_p = id2img.get(sid)
        if not img_p or not img_p.exists():
            continue
        det = detect_components(str(img_p))
        a = find_anchor(det["texts"], anchor)
        if not a:
            stats["no_anchor"] += 1
            continue
        abox = box_of(a)
        cur = r.get("chosen_px")
        cur_ok = r["correctness"] == "correct"
        if cur and satisfies(cur, abox, direction):
            stats["keep_sat"] += 1
            continue
        cands = active.build_candidates([], det["texts"], det["icons"])
        repl = pick_replacement(cands, abox, direction, a.get("label"))
        if not repl:
            stats["no_repl"] += 1
            continue
        stats["replace"] += 1
        new_ok = in_box((repl[1], repl[2]), r["gt_bbox"])
        if new_ok and not cur_ok:
            rescue += 1
            events.append(("RESCUE", sid, r["instruction"][:45]))
        elif not new_ok and cur_ok:
            brk += 1
            events.append(("BREAK", sid, r["instruction"][:45]))
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(rows)} {stats} rescue={rescue} break={brk}", flush=True)

    print(f"\nspatial rows={len(rows)}  stats={stats}")
    print(f"rescues={rescue}  breaks={brk}  net={rescue-brk:+d}")
    for tag, sid, ins in events:
        print(f"  {tag} {sid} {ins!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
