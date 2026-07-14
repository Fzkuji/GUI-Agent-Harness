#!/usr/bin/env python3
"""Convert OS-Atlas desktop_domain *_splited.json into the gui-aima bbox.json
format our pipeline already consumes (guiact_bbox.json / wave_ui_bbox.json).

OS-Atlas format (grouped by image):
  [{"img_filename": "...", "elements": [{"instruction": "...",
    "bbox": [x1,y1,x2,y2] in [0,1], "data_type": "..."}, ...]}, ...]

gui-aima format (flat, one row per instruction):
  [{"image": "...", "conversations": [
    {"from": "human", "value": "<image> INSTRUCTION"},
    {"from": "gpt", "value": "pyautogui.click(x=CX, y=CY)",
     "recipient": "os", "end_turn": true, "bbox_gt": [x1,y1,x2,y2]}]}, ...]

Drops degenerate boxes (zero area) and instructions that are empty/whitespace.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def convert(src: Path, platform: str) -> list[dict]:
    data = json.loads(src.read_text(encoding="utf-8"))
    out = []
    for row in data:
        img = row.get("img_filename")
        if not img:
            continue
        # Skip pre-cropped quadrant images (e.g. "..._sub0.png", quarter-size
        # of the real screenshot): our zoom trajectory synthesis assumes every
        # source image IS the full round-0 screen, so mixing in already-cropped
        # sub-images teaches an inconsistent "what does round 0 look like"
        # signal — confirmed root cause of a checkpoint-1500 regression
        # (60-63% -> ~53% on SSPro300).
        if "_sub" in Path(img).stem:
            continue
        for el in row.get("elements", []):
            instr = (el.get("instruction") or "").strip()
            bbox = el.get("bbox")
            if not instr or not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = bbox
            if x2 <= x1 or y2 <= y1:
                continue
            x1, x2 = max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))
            y1, y2 = max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            out.append({
                "image": img,
                "platform": platform,
                "conversations": [
                    {"from": "human", "value": f"<image> {instr}"},
                    {"from": "gpt", "value": f"pyautogui.click(x={cx:.4f}, y={cy:.4f})",
                     "recipient": "os", "end_turn": True,
                     "bbox_gt": [round(x1, 6), round(y1, 6), round(x2, 6), round(y2, 6)]},
                ],
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", required=True,
                    help="platform:path/to/*_splited.json pairs, e.g. linux:desktop_domain/linux_splited.json macos:desktop_domain/macos_splited.json")
    ap.add_argument("--out", required=True, help="output merged bbox.json")
    args = ap.parse_args()

    merged: list[dict] = []
    for spec in args.sources:
        platform, path = spec.split(":", 1)
        rows = convert(Path(path), platform)
        print(f"[{platform}] {len(rows)} instruction rows from {path}")
        merged.extend(rows)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(merged)} total rows -> {out_path}")


if __name__ == "__main__":
    main()
