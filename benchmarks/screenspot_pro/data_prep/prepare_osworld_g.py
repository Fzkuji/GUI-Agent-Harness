#!/usr/bin/env python3
"""准备 OSWorld-G(564 样本 grounding benchmark)给本地 runner。

数据源:GitHub xlang-ai/OSWorld-G
  - 标注: benchmark/OSWorld-G.json(原始指令)
  - 图片: benchmark/images/<image_path>
转换:box_coordinates [x,y,w,h] -> gt bbox [x1,y1,x2,y2];写成 runner 的 annotation 格式
       (与 ui_vision 同结构:img_filename/raw_image_path/bbox/img_size/instruction/id/...)
输出:
  data_osworld_g/annotations/osworld_g.json
  data_osworld_g/raw_images/<image_path>
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data_osworld_g"
ANN_DIR = DATA / "annotations"
IMG_DIR = DATA / "raw_images"
RAW_GH = "https://raw.githubusercontent.com/xlang-ai/OSWorld-G/main"
JSON_URL = f"{RAW_GH}/benchmark/OSWorld-G.json"
IMG_BASE = f"{RAW_GH}/benchmark/images"
PROXY = "http://127.0.0.1:7890"   # FlClash;直连 GitHub 不稳时走它


def curl(url, dest, tries=4):
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(tries):
        proxy = [] if attempt == 0 else ["--proxy", PROXY]
        r = subprocess.run(["curl", "-sSL", "--max-time", "60", *proxy, "-o", str(dest), url],
                           capture_output=True, text=True)
        if dest.exists() and dest.stat().st_size > 0:
            return True
    return False


def img_ok(p: Path) -> bool:
    if not p.exists() or p.stat().st_size == 0:
        return False
    try:
        from PIL import Image
        with Image.open(p) as im:
            im.verify()
        return True
    except Exception:
        return False


def main() -> int:
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    raw_json = DATA / "OSWorld-G.json"
    if not raw_json.exists():
        assert curl(JSON_URL, raw_json), "下载标注失败"
    rows = json.loads(raw_json.read_text(encoding="utf-8"))
    print(f"OSWorld-G: {len(rows)} 条标注", flush=True)

    samples = []
    for i, r in enumerate(rows):
        bt = r.get("box_type")
        bc = r["box_coordinates"]
        polygon = None
        if bt == "bbox":
            x, y, w, h = bc
            gt = [int(round(x)), int(round(y)), int(round(x + w)), int(round(y + h))]
        elif bt == "polygon":
            xs = [bc[j] for j in range(0, len(bc), 2)]
            ys = [bc[j] for j in range(1, len(bc), 2)]
            gt = [int(round(min(xs))), int(round(min(ys))),
                  int(round(max(xs))), int(round(max(ys)))]
            polygon = [[bc[j], bc[j + 1]] for j in range(0, len(bc) - 1, 2)]
        else:  # refusal:任务不可完成,正确答案=拒绝;无有效目标框 → 任何点击都错
            gt = [-1, -1, -1, -1]
        iw, ih = r["image_size"]
        samples.append({
            "img_filename": r["image_path"],
            "raw_image_path": r["image_path"],
            "bbox": gt,
            "img_size": [int(iw), int(ih)],
            "instruction": r["instruction"],
            "id": f"osworld_g_{i:04d}",
            "application": "osworld_g",
            "platform": "osworld_g",
            "ui_type": (r.get("GUI_types") or [None])[0],
            "group": "OSWorld-G",
            "split": "osworld_g",
            "data_source": "osworld_g",
            "dataset_version": "osworld_g",
            "source_image_path": r["image_path"],
            "gui_types": r.get("GUI_types"),
            "osworld_box_type": bt,
            "osworld_polygon": polygon,
            "orig_id": r["id"],
        })
    (ANN_DIR / "osworld_g.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    print(f"标注写入 {ANN_DIR/'osworld_g.json'}", flush=True)

    # 下载图片(去重,多线程)
    imgs = sorted({r["image_path"] for r in rows})
    missing = [im for im in imgs if not img_ok(IMG_DIR / im)]
    print(f"图片 {len(imgs)} 张,需下载 {len(missing)}", flush=True)
    done = fail = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(curl, f"{IMG_BASE}/{im}", IMG_DIR / im): im for im in missing}
        for fut in as_completed(futs):
            im = futs[fut]
            if fut.result() and img_ok(IMG_DIR / im):
                done += 1
            else:
                fail += 1
            if (done + fail) % 50 == 0:
                print(f"  下载 {done+fail}/{len(missing)} (失败 {fail})", flush=True)
    print(f"完成:成功 {done},失败 {fail}", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
