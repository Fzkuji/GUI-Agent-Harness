#!/usr/bin/env python3
"""两臂分歧仲裁:single-shot(臂1)与 iterative_zoom(臂2)结果不一致时,
让裁决模型看双标记图选 A/B。

机制:
  - 两臂点距 <= AGREE_PX 视为一致,直接取臂2(zoom)的点,不花调用。
  - 一臂无点 → 取有点的那臂,不花调用。
  - 分歧 → 裁决调用:以两点外接框 + 上下文 pad 裁剪(小图放大),A/B 偏移
    标记(空心圈 + 字母在旁,避免遮挡目标),模型按指令选 A 或 B。
  - 输出 arbitrated.jsonl + 三方对比(arm1 / zoom / arbitrated)。

用法:
  python arbitrate_two_arms.py \
    --arm1-glob "runs/ui_vision_gpt_ss_element/*.jsonl" \
    --arm2-glob "runs/ui_vision_gpt_zoom/*.jsonl" \
    --out runs/ui_vision_arbitrated/arbitrated.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

DATA_DIR = HERE / "data_ui_vision"
AGREE_PX = 18      # 更小的一致阈值:15-40px 的"近距分歧"恰是可裁决的精度问题
PAD = 240
PAD_SPATIAL = 520  # 方位类指令需要看到参照锚点,用宽上下文
MIN_SIDE = 640  # upscale the judge crop so小目标看得清

_SPATIAL_WORDS = ("left of", "right of", "above", "below", "under", "nearest",
                  "next to", "beside", "between", "horizontally", "vertically")


def is_spatial(instruction: str) -> bool:
    low = instruction.lower()
    return any(w in low for w in _SPATIAL_WORDS)


def load_rows(pattern: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for p in glob.glob(pattern):
        if p.endswith("errors.jsonl"):
            continue
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            rows[r["sample_id"]] = r
    return rows


def image_path_for(sample_id: str, ann_cache: dict) -> Path | None:
    # sample_id: ui_vision_<split>_<idx>
    parts = sample_id.rsplit("_", 1)
    ann_name = parts[0] + ".json"  # ui_vision_basic.json
    idx = int(parts[1])
    if ann_name not in ann_cache:
        ann_path = DATA_DIR / "annotations" / ann_name
        ann_cache[ann_name] = json.loads(ann_path.read_text(encoding="utf-8"))
    sample = ann_cache[ann_name][idx]
    rel = sample.get("raw_image_path") or sample.get("img_filename")
    p = DATA_DIR / "raw_images" / rel
    return p if p.exists() else None


def point_inside(px, py, b) -> bool:
    return b[0] <= px <= b[2] and b[1] <= py <= b[3]


def dist(p, q) -> float:
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def draw_marker(d: ImageDraw.ImageDraw, x: float, y: float, label: str, color: str, scale: float):
    r = max(10, int(9 * scale))
    w = max(2, int(2 * scale))
    d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=w)
    # 字母放在圈外右上,避免遮挡圈内目标
    fs = max(14, int(13 * scale))
    d.text((x + r + 3, y - r - fs - 1), label, fill=color)


def judge_overview(img: Image.Image, pa, pb, out_path: Path,
                   cands: list[dict] | None = None) -> tuple[Path, float]:
    """全图概览(降采样 + A/B 标记 + 编号候选框)——给 C 选项提供全局视野。"""
    scale = 1.0
    long_side = max(img.width, img.height)
    if long_side > 1600:
        scale = 1600 / long_side
    ov = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS) if scale < 1 else img.copy()
    d = ImageDraw.Draw(ov)
    draw_marker(d, pa[0] * scale, pa[1] * scale, "A", "#ff2222", 1.0)
    draw_marker(d, pb[0] * scale, pb[1] * scale, "B", "#2255ff", 1.0)
    for c in (cands or []):
        b = c["box"]
        d.rectangle([b[0] * scale, b[1] * scale, b[2] * scale, b[3] * scale],
                    outline="#11aa33", width=2)
        d.text((b[0] * scale, max(0, b[1] * scale - 14)), c["id"], fill="#11aa33")
    ov.save(out_path)
    return out_path, scale


_DETECT_CACHE: dict[str, list[dict]] = {}


def relevant_candidates(img_path: str, instruction: str, pa, pb, k: int = 8) -> list[dict]:
    """检测 + 词面相关性排序的 top-k 候选(排除与 A/B 重叠的),供裁决者点名。"""
    from gui_harness.planning.component_memory import detect_components
    from gui_harness.planning import active_localization as active
    if img_path not in _DETECT_CACHE:
        det = detect_components(img_path)
        pool = active.build_candidates([], det["texts"], det["icons"])
        _DETECT_CACHE[img_path] = pool
    pool = _DETECT_CACHE[img_path]
    scored = []
    for c in pool:
        box = active._candidate_box(c)
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        # 已被 A/B 覆盖的不再标注
        if min(dist((cx, cy), pa), dist((cx, cy), pb)) <= 30:
            continue
        score = active._candidate_relevance(instruction, c)
        if score <= 0:
            continue
        scored.append((score, c, box))
    scored.sort(key=lambda t: -t[0])
    out = []
    for i, (score, c, box) in enumerate(scored[:k]):
        label = (c.get("label") or c.get("name") or "")[:40]
        out.append({"id": f"c{i+1}", "box": [int(v) for v in box], "label": label,
                    "center": [int((box[0]+box[2])/2), int((box[1]+box[3])/2)]})
    return out


def judge_crop(img: Image.Image, pa, pb, out_path: Path, pad: int = PAD) -> tuple[Path, float, list[int]]:
    x1 = max(0, int(min(pa[0], pb[0]) - pad))
    y1 = max(0, int(min(pa[1], pb[1]) - pad))
    x2 = min(img.width, int(max(pa[0], pb[0]) + pad))
    y2 = min(img.height, int(max(pa[1], pb[1]) + pad))
    crop = img.crop((x1, y1, x2, y2))
    scale = 1.0
    short = min(crop.width, crop.height)
    if short < MIN_SIDE:
        scale = MIN_SIDE / short
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(crop)
    draw_marker(d, (pa[0] - x1) * scale, (pa[1] - y1) * scale, "A", "#ff2222", scale)
    draw_marker(d, (pb[0] - x1) * scale, (pb[1] - y1) * scale, "B", "#2255ff", scale)
    crop.save(out_path)
    return out_path, scale, [x1, y1, x2, y2]


def _zoom_thumb(img: Image.Image, box: list[int], pad: int = 16,
                target_h: int = 150, max_src: int = 420) -> Image.Image:
    """候选框的放大缩略图(识别 20px 图标用)。过大的框截中心区。"""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    w, h = min(x2 - x1 + 2 * pad, max_src), min(y2 - y1 + 2 * pad, max_src)
    crop = img.crop((
        max(0, int(cx - w / 2)), max(0, int(cy - h / 2)),
        min(img.width, int(cx + w / 2)), min(img.height, int(cy + h / 2)),
    ))
    scale = target_h / max(1, crop.height)
    return crop.resize((max(1, int(crop.width * scale)), target_h), Image.LANCZOS)


def build_lineup(img: Image.Image, point: list[int], cands: list[dict],
                 out_path: Path) -> list[dict]:
    """验身阵容图:0=当前答案的放大图,1..K=备选候选的放大图,纵向拼接。
    返回阵容元数据(id -> center)。"""
    entries = [{"id": "0", "center": list(point),
                "box": [point[0] - 28, point[1] - 28, point[0] + 28, point[1] + 28],
                "label": "(current answer)"}]
    for c in cands[:5]:
        entries.append({"id": str(len(entries)), "center": c["center"],
                        "box": c["box"], "label": c["label"]})
    thumbs = []
    for e in entries:
        t = _zoom_thumb(img, e["box"])
        # 在当前答案缩略图上画点标记
        if e["id"] == "0":
            d = ImageDraw.Draw(t)
            d.ellipse([t.width / 2 - 7, t.height / 2 - 7, t.width / 2 + 7, t.height / 2 + 7],
                      outline="#ff9900", width=3)
        thumbs.append((e["id"], t))
    pad_y, label_h = 8, 18
    width = max(t.width for _, t in thumbs) + 90
    height = sum(t.height + label_h + pad_y for _, t in thumbs)
    sheet = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(sheet)
    y = 0
    for tid, t in thumbs:
        d.text((4, y + 2), f"[{tid}]", fill="#cc0000")
        sheet.paste(t, (60, y + label_h))
        y += t.height + label_h + pad_y
    sheet.save(out_path)
    return entries


def verify_final(runtime, img_p: str, instruction: str, point: list[int],
                 work: Path, sid: str) -> tuple[list[int], dict]:
    """对最终答案做放大验身;不确信则保持原答案。返回 (point, meta)。"""
    from gui_harness.utils import parse_json
    img = Image.open(img_p).convert("RGB")
    try:
        cands = relevant_candidates(img_p, instruction, point, point, k=5)
    except Exception:
        cands = []
    entries = build_lineup(img, point, cands, work / f"{sid}_lineup.png")
    lines = "\n".join(
        f"  [{e['id']}] {e['label'] or '(unlabeled icon)'}" for e in entries
    )
    prompt = f"""Target element: {instruction}

The attached sheet shows ZOOMED-IN views of UI elements from one screenshot:
  [0] is the currently chosen answer (orange dot marks the exact click point).
  [1]..[{len(entries)-1}] are alternative detected elements whose label relates
  to the target.
{lines}

Question: which numbered view shows EXACTLY the element the target names?
Keep [0] unless you can clearly see that [0] is a different element AND one of
the alternatives clearly IS the named element. Icons are now zoomed large
enough to read their glyphs — judge by visual identity, not position.

Reply with ONLY JSON: {{"choice": 0, "confidence": 0.0, "reasoning": "..."}}"""
    try:
        reply = runtime.exec(
            content=[{"type": "text", "text": prompt},
                     {"type": "image", "path": str(work / f"{sid}_lineup.png")}],
            timeout_s=120,
        )
        parsed = parse_json(reply)
        choice = int(parsed.get("choice", 0))
        conf = float(parsed.get("confidence", 0) or 0)
        meta = {"choice": choice, "confidence": conf,
                "reasoning": str(parsed.get("reasoning"))[:150],
                "n_alternatives": len(entries) - 1}
        # spatial 关系题禁止切换:阵容缩略图剥掉了空间上下文,凭关系推理换点
        # 在 70 行实测中 3 切全错(其中 1 刀砍掉好答案)。验身只用于语义认错。
        if 1 <= choice < len(entries) and conf >= 0.7 and not is_spatial(instruction):
            return list(entries[choice]["center"]), meta
        return point, meta
    except Exception as exc:
        return point, {"error": exc.__class__.__name__}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm1-glob", required=True)
    ap.add_argument("--arm2-glob", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--limit", type=int, default=0, help="仅处理前 N 个共同样本(0=全部)")
    ap.add_argument("--verify-final", action="store_true",
                    help="对每行最终答案做放大验身(zoomed lineup);确信时切换到正确候选")
    ap.add_argument("--shards", type=int, default=1, help="总分片数(并行跑)")
    ap.add_argument("--shard-index", type=int, default=0, help="本进程的分片号 0..shards-1")
    args = ap.parse_args()

    arm1 = load_rows(args.arm1_glob)
    arm2 = load_rows(args.arm2_glob)
    common = [k for k in arm2 if k in arm1]
    if args.limit:
        common = common[: args.limit]
    if args.shards > 1:
        common = [k for i, k in enumerate(sorted(common)) if i % args.shards == args.shard_index]
        print(f"shard {args.shard_index}/{args.shards}", flush=True)
    print(f"common rows: {len(common)}", flush=True)

    from gui_harness.openprogram_compat import create_runtime
    from gui_harness.utils import parse_json
    runtime = create_runtime(provider=args.provider, model=args.model)

    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent / "judge_crops"
    work.mkdir(exist_ok=True)

    done_ids = set()
    if out_path.exists():
        for line in open(out_path, encoding="utf-8"):
            try:
                done_ids.add(json.loads(line)["sample_id"])
            except Exception:
                pass

    ann_cache: dict = {}
    stats = {"agree": 0, "one_point": 0, "judged": 0, "judge_err": 0}
    f = open(out_path, "a", encoding="utf-8")
    for i, sid in enumerate(common):
        if sid in done_ids:
            continue
        r1, r2 = arm1[sid], arm2[sid]
        p1, p2 = r1.get("prediction_px"), r2.get("prediction_px")
        gt = r2["gt_bbox"]
        chosen, how, judge_meta = None, "", None
        if p1 and p2 and dist(p1, p2) <= AGREE_PX:
            chosen, how = p2, "agree_zoom"
            stats["agree"] += 1
        elif p1 and not p2:
            chosen, how = p1, "only_arm1"
            stats["one_point"] += 1
        elif p2 and not p1:
            chosen, how = p2, "only_arm2"
            stats["one_point"] += 1
        elif p1 and p2:
            img_p = image_path_for(sid, ann_cache)
            if img_p is None:
                chosen, how = p2, "no_image_fallback"
            else:
                img = Image.open(img_p).convert("RGB")
                instr = r2["instruction"]
                pad = PAD_SPATIAL if is_spatial(instr) else PAD
                crop_p, scale, box = judge_crop(img, p1, p2, work / f"{sid}.png", pad=pad)
                try:
                    cands = relevant_candidates(str(img_p), instr, p1, p2)
                except Exception:
                    cands = []
                ov_p, ov_scale = judge_overview(img, p1, p2, work / f"{sid}_ov.png", cands)
                name1 = str((r1.get("location") or {}).get("name") or "")[:80]
                name2 = str((r2.get("location") or {}).get("name") or "")[:80]
                cand_lines = "\n".join(
                    f"  {c['id']}: {c['label'] or '(unlabeled)'} at {c['center']}" for c in cands
                ) or "  (none)"
                prompt = f"""Target element (terse name, may be an icon/label/field): {instr}

Two candidate click points are proposed. They are marked with offset circles
on BOTH attached images:
  A (red)  — proposed by method 1, which described it as: {name1 or '(unnamed)'}
  B (blue) — proposed by method 2, which described it as: {name2 or '(unnamed)'}
Image 1 is a zoomed-in crop around the two points (use it to compare A vs B
precisely). Image 2 is the full screen (use it for context and spatial
relations). Image 2 additionally shows numbered GREEN boxes — other detected
elements whose text/label relates to the target:
{cand_lines}

Decide which marker is on the element the target names. Judge by what is
visibly under each marker, not by the descriptions. If the target describes a
spatial relation (left of / right of / nearest ...), first find the named
anchor element in image 2, then verify the relation. If both A and B look
plausible, choose the one more precisely centred on the named element itself
(its own icon/label extent, not an adjacent control).

If NEITHER A nor B is on the named element: check the green boxes — if one of
them IS the named element, answer with its id (e.g. "c3"). If the element is
visible somewhere else entirely, answer "C" with its pixel coordinates in
IMAGE 2.

Reply with ONLY JSON:
{{"choice": "A|B|c1..c8|C", "x": 0, "y": 0, "confidence": 0.0, "reasoning": "..."}}
(x/y are required only for choice C, in image-2 pixels.)"""
                try:
                    reply = runtime.exec(
                        content=[
                            {"type": "text", "text": prompt},
                            {"type": "image", "path": str(crop_p)},
                            {"type": "image", "path": str(ov_p)},
                        ],
                        timeout_s=120,
                    )
                    parsed = parse_json(reply)
                    pick_raw = str(parsed.get("choice", "")).strip()
                    pick = pick_raw.upper()
                    cand_map = {c["id"].upper(): c for c in cands}
                    if pick in cand_map:
                        chosen = list(cand_map[pick]["center"])
                    elif pick == "C":
                        try:
                            jx, jy = float(parsed.get("x", 0)), float(parsed.get("y", 0))
                            # image-2(全图概览)坐标 -> 原图坐标
                            cx = int(round(jx / ov_scale))
                            cy = int(round(jy / ov_scale))
                            if 0 < cx <= img.width and 0 < cy <= img.height and (jx, jy) != (0.0, 0.0):
                                chosen = [cx, cy]
                            else:
                                chosen, pick = p2, "B"
                        except (TypeError, ValueError):
                            chosen, pick = p2, "B"
                    else:
                        chosen = p1 if pick == "A" else p2
                    how = f"judge_{pick or 'B'}"
                    judge_meta = {"choice": pick, "confidence": parsed.get("confidence"),
                                  "reasoning": str(parsed.get("reasoning"))[:200], "crop_box": box}
                    stats["judged"] += 1
                except Exception as exc:
                    chosen, how = p2, f"judge_error_fallback({exc.__class__.__name__})"
                    stats["judge_err"] += 1
        else:
            chosen, how = None, "no_point_both"

        verify_meta = None
        if args.verify_final and chosen:
            img_pv = image_path_for(sid, ann_cache)
            if img_pv is not None:
                new_pt, verify_meta = verify_final(
                    runtime, str(img_pv), r2["instruction"], chosen, work, sid)
                if new_pt != chosen:
                    how += "+vswitch"
                    stats["vswitch"] = stats.get("vswitch", 0) + 1
                    chosen = new_pt
                stats["verified"] = stats.get("verified", 0) + 1

        correct = bool(chosen) and point_inside(chosen[0], chosen[1], gt)
        f.write(json.dumps({
            "sample_id": sid, "instruction": r2["instruction"], "gt_bbox": gt,
            "arm1_px": p1, "arm2_px": p2, "chosen_px": chosen, "how": how,
            "correctness": "correct" if correct else "wrong",
            "arm1_correct": r1.get("correctness") == "correct",
            "arm2_correct": r2.get("correctness") == "correct",
            "judge": judge_meta, "verify": verify_meta,
        }, ensure_ascii=False) + "\n")
        f.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(common)} {stats}", flush=True)
    f.close()

    # 总结
    rows = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    n = len(rows)
    arb = sum(r["correctness"] == "correct" for r in rows)
    a1 = sum(r["arm1_correct"] for r in rows)
    a2 = sum(r["arm2_correct"] for r in rows)
    uni = sum(r["arm1_correct"] or r["arm2_correct"] for r in rows)
    print(f"\nn={n}  arm1={a1/n:.1%}  arm2(zoom)={a2/n:.1%}  arbitrated={arb/n:.1%}  union-ceiling={uni/n:.1%}")
    print(f"stats: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
