#!/usr/bin/env python3
"""把 ServiceNow/ui-vision 的 element grounding 标注归一化成 ScreenSpot-Pro runner
能读的格式（annotation JSON 每应用一个 + 本地图）。

源（benchmarks/ui_vision_raw/）：
  annotations/element_grounding/element_grounding_{basic,functional,spatial}.json
  images/element_grounding/<hash>.png
源单条：image_path / image_size / prompt_to_evaluate / bbox / platform / category / element_type

目标（benchmarks/ui_vision/data/）：
  annotations/<subset>_<platform>.json   每条含 ScreenSpot-Pro 字段
  raw_images/<hash>.png                   图片（多指令共用，按 hash 去重）
  字段 dataset_version="ui_vision" -> runner 只用本地图、不联网下载。

跑法： python benchmarks/ui_vision/prepare_ui_vision.py
"""
from __future__ import annotations
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "ui_vision_raw"
SRC_ANN = RAW / "annotations" / "element_grounding"
SRC_IMG = RAW / "images" / "element_grounding"
OUT = HERE / "data"
OUT_ANN = OUT / "annotations"
OUT_IMG = OUT / "raw_images"
SUBSETS = ["basic", "functional", "spatial"]


def safe(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_").lower()


def main() -> None:
    OUT_ANN.mkdir(parents=True, exist_ok=True)
    OUT_IMG.mkdir(parents=True, exist_ok=True)

    copied: set[str] = set()
    written = 0
    for subset in SUBSETS:
        src = SRC_ANN / f"element_grounding_{subset}.json"
        rows = json.load(open(src))
        # 按 platform 分组
        by_plat: dict[str, list] = defaultdict(list)
        for r in rows:
            by_plat[r["platform"]].append(r)

        for plat, items in by_plat.items():
            plat_safe = safe(plat)
            ann_name = f"{subset}_{plat_safe}"
            out_samples = []
            for idx, r in enumerate(items):
                img_hash = Path(r["image_path"]).name  # <hash>.png
                # 复制图片（去重）
                if img_hash not in copied:
                    src_img = SRC_IMG / img_hash
                    if src_img.exists():
                        shutil.copy2(src_img, OUT_IMG / img_hash)
                        copied.add(img_hash)
                sample = {
                    "id": f"{ann_name}_{idx}",
                    "img_filename": img_hash,
                    "raw_image_path": img_hash,
                    "bbox": [round(float(v), 2) for v in r["bbox"]],
                    "instruction": r["prompt_to_evaluate"],
                    "instruction_cn": "",
                    "application": plat_safe,
                    "platform": "ui_vision",
                    "img_size": r["image_size"],
                    "ui_type": r.get("element_type", ""),
                    "group": subset,
                    "category": r.get("category", ""),
                    "dataset_version": "ui_vision",
                }
                out_samples.append(sample)
            (OUT_ANN / f"{ann_name}.json").write_text(
                json.dumps(out_samples, ensure_ascii=False, indent=2))
            written += len(out_samples)

    n_ann = len(list(OUT_ANN.glob("*.json")))
    print(f"写出 {written} 条样本, {n_ann} 个 annotation 文件, {len(copied)} 张图 -> {OUT}")


if __name__ == "__main__":
    main()
