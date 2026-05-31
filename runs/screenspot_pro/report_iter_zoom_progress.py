#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def planned_count(plan_path: Path) -> int:
    if not plan_path.exists():
        return 0
    total = 0
    for line in plan_path.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1]:
            total += len([x for x in parts[1].split(",") if x])
    return total


def pack(counter: Counter) -> dict:
    total = sum(counter.values())
    return {
        "count": total,
        "correct": counter["correct"],
        "wrong": counter["wrong"],
        "wrong_format": counter["wrong_format"],
        "accuracy": round(counter["correct"] / total, 4) if total else 0.0,
    }


def active_from_log(log_path: Path) -> str | None:
    if not log_path.exists():
        return None
    lines = log_path.read_text(errors="ignore").splitlines()
    starts = [line for line in lines if line.startswith("[screenspot] ") and ": " in line and " -> " not in line]
    if not starts:
        return None
    return starts[-1].replace("[screenspot] ", "", 1)


def draw_marker(draw: ImageDraw.ImageDraw, x: float, y: float, color: str, scale: float) -> None:
    r = max(8, int(12 * scale))
    w = max(3, int(4 * scale))
    draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=w)
    draw.line((x - r * 1.5, y, x + r * 1.5, y), fill=color, width=w)
    draw.line((x, y - r * 1.5, x, y + r * 1.5), fill=color, width=w)


def scaled_box(box: list[int], scale: float) -> list[int]:
    return [round(v * scale) for v in box]


def contains_point(box: list[int] | None, x: float, y: float) -> bool:
    return bool(box) and len(box) == 4 and box[0] <= x <= box[2] and box[1] <= y <= box[3]


def crop_loss_round(row: dict) -> str | None:
    gt = row.get("gt_bbox") or []
    if len(gt) != 4:
        return None
    gx = (gt[0] + gt[2]) / 2.0
    gy = (gt[1] + gt[3]) / 2.0
    zoom = (row.get("location") or {}).get("iterative_zoom") or {}
    for item in zoom.get("history") or []:
        next_box = item.get("next_box")
        if next_box and not contains_point(next_box, gx, gy):
            return f"round_{item.get('round')}_next_box"
    final_box = zoom.get("final_crop_box")
    if final_box and not contains_point(final_box, gx, gy):
        return "final_crop"
    return None


def crop_trace_boxes(row: dict) -> list[tuple[str, list[int]]]:
    zoom = (row.get("location") or {}).get("iterative_zoom") or {}
    boxes: list[tuple[str, list[int]]] = []
    for item in zoom.get("history") or []:
        next_box = item.get("next_box")
        if next_box and len(next_box) == 4:
            boxes.append((f"r{item.get('round')}", next_box))
    final_box = zoom.get("final_crop_box")
    if final_box and len(final_box) == 4:
        boxes.append(("final", final_box))
    return boxes


def make_visualization(row: dict, images_dir: Path, out_dir: Path, max_side: int = 1800) -> str | None:
    sample_id = row.get("sample_id")
    if not sample_id:
        return None
    img_path = images_dir / f"{sample_id}.png"
    if not img_path.exists():
        return None
    img = Image.open(img_path).convert("RGB")
    orig_w, orig_h = img.size
    scale = min(1.0, max_side / max(orig_w, orig_h))
    if scale < 1.0:
        img = img.resize((round(orig_w * scale), round(orig_h * scale)), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img)
    line_w = max(3, int(5 * scale))
    colors = ["#ffcc00", "#00b7ff", "#bf5af2", "#ff9f0a", "#64d2ff", "#ffd60a"]

    for idx, (label, box) in enumerate(crop_trace_boxes(row)):
        sbox = scaled_box(box, scale)
        color = colors[idx % len(colors)]
        draw.rectangle(sbox, outline=color, width=max(2, int(3 * scale)))
        draw.text((sbox[0] + 4, max(0, sbox[1] + 4)), label, fill=color)

    gt = row.get("gt_bbox") or []
    if len(gt) == 4:
        box = scaled_box(gt, scale)
        draw.rectangle(box, outline="#00d26a", width=line_w)
        draw.text((box[0], max(0, box[1] - 22)), "GT", fill="#00d26a")

    pred = row.get("prediction_px")
    if pred and len(pred) == 2:
        px, py = pred[0] * scale, pred[1] * scale
        draw_marker(draw, px, py, "#ff3b30", scale)
        draw.text((px + 12, max(0, py - 22)), "PRED", fill="#ff3b30")

    title = (
        f"{sample_id} | {row.get('correctness')} | "
        f"lost={crop_loss_round(row) or 'no'} | {row.get('instruction', '')[:120]}"
    )
    pad = 10
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    bbox = draw.textbbox((pad, pad), title, font=font)
    title_h = bbox[3] - bbox[1] + pad * 2
    title_y1 = max(0, img.height - title_h)
    title_w = min(img.width, bbox[2] + pad * 2)
    draw.rectangle((0, title_y1, title_w, img.height), fill=(0, 0, 0))
    draw.text((pad, title_y1 + pad), title, fill=(255, 255, 255), font=font)

    if not crop_trace_boxes(row):
        note = "no crop history available"
        note_bbox = draw.textbbox((pad, pad), note, font=font)
        draw.rectangle((0, 0, note_bbox[2] + pad * 2, note_bbox[3] + pad * 2), fill=(0, 0, 0))
        draw.text((pad, pad), note, fill="#ffd60a", font=font)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sample_id}_{row.get('correctness')}.png"
    img.save(out_path)
    return str(out_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--data-dir", default="benchmarks/screenspot_pro/data")
    parser.add_argument("--max-visuals", type=int, default=12)
    parser.add_argument("--new-only", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    rows = load_rows(run_dir / "results.jsonl")
    planned = planned_count(run_dir / "plan.tsv")
    counts = Counter(row.get("correctness") for row in rows)
    by_group: dict[str, Counter] = defaultdict(Counter)
    by_annotation: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_group[row.get("group") or "unknown"][row.get("correctness")] += 1
        by_annotation[row.get("annotation_file") or row.get("annotation") or "unknown"][row.get("correctness")] += 1

    state_path = run_dir / "progress_report_state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except json.JSONDecodeError:
            state = {}
    seen = set(state.get("visualized_wrong_sample_ids", []))

    wrong_rows = [row for row in rows if row.get("correctness") != "correct"]
    rows_to_visualize = [row for row in wrong_rows if (not args.new_only or row.get("sample_id") not in seen)]
    rows_to_visualize = rows_to_visualize[: max(0, args.max_visuals)]

    images_dir = Path(args.data_dir) / "images"
    vis_dir = run_dir / "wrong_visualizations"
    visualizations = []
    for row in rows_to_visualize:
        path = make_visualization(row, images_dir, vis_dir)
        if path:
            visualizations.append({
                "sample_id": row.get("sample_id"),
                "correctness": row.get("correctness"),
                "instruction": row.get("instruction"),
                "prediction_px": row.get("prediction_px"),
                "gt_bbox": row.get("gt_bbox"),
                "path": path,
            })
            seen.add(row.get("sample_id"))

    state["visualized_wrong_sample_ids"] = sorted(x for x in seen if x)
    state["last_completed"] = len(rows)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    summary = {
        "planned": planned,
        "completed": len(rows),
        "unique_samples": len({row.get("sample_id") for row in rows}),
        "overall": pack(counts),
        "last_completed": (
            {
                "sample_id": rows[-1].get("sample_id"),
                "correctness": rows[-1].get("correctness"),
                "annotation_file": rows[-1].get("annotation_file"),
                "prediction_px": rows[-1].get("prediction_px"),
                "gt_bbox": rows[-1].get("gt_bbox"),
            }
            if rows
            else None
        ),
        "active": active_from_log(run_dir.with_suffix(".log")),
        "wrong_cases": [
            {
                "sample_id": row.get("sample_id"),
                "correctness": row.get("correctness"),
                "annotation_file": row.get("annotation_file"),
                "group": row.get("group"),
                "instruction": row.get("instruction"),
                "prediction_px": row.get("prediction_px"),
                "gt_bbox": row.get("gt_bbox"),
                "crop_lost_gt_at": crop_loss_round(row),
            }
            for row in wrong_rows
        ],
        "new_visualizations": visualizations,
        "by_group": {key: pack(value) for key, value in sorted(by_group.items())},
        "by_annotation": {key: pack(value) for key, value in sorted(by_annotation.items())},
    }
    (run_dir / "progress_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
