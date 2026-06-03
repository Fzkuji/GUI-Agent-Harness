#!/usr/bin/env python3
"""Prepare GUI grounding datasets for the ScreenSpot-Pro local runner.

This normalizes UI-Vision element grounding and MMBench-GUI L2 annotations into
the same local shape used by ``run_screenspot_pro.py``:

    data_<dataset>/annotations/*.json
    data_<dataset>/raw_images/<source-relative-path>.png

Images are downloaded or extracted only when ``--metadata-only`` is omitted.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile, is_zipfile

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROXY = "http://127.0.0.1:6152"

UI_VISION_REPO = "ServiceNow/ui-vision"
MMBENCH_REPO = "OpenGVLab/MMBench-GUI"

DATASETS: dict[str, dict[str, Any]] = {
    "ui_vision": {
        "repo": UI_VISION_REPO,
        "data_dir": Path("benchmarks/screenspot_pro/data_ui_vision"),
        "splits": (
            ("basic", "annotations/element_grounding/element_grounding_basic.json"),
            ("functional", "annotations/element_grounding/element_grounding_functional.json"),
            ("spatial", "annotations/element_grounding/element_grounding_spatial.json"),
        ),
    },
    "mmbench_gui_l2": {
        "repo": MMBENCH_REPO,
        "data_dir": Path("benchmarks/screenspot_pro/data_mmbench_gui_l2"),
        "manifest": "L2_annotations.json",
        "zip_path": "MMBench-GUI-OfflineImages.zip",
    },
}


def repo_url(repo: str, path: str) -> str:
    quoted = urllib.parse.quote(path, safe="/")
    return f"https://huggingface.co/datasets/{repo}/resolve/main/{quoted}"


def with_default_proxy(env: dict[str, str]) -> dict[str, str]:
    merged = dict(env)
    merged.setdefault("HTTPS_PROXY", DEFAULT_PROXY)
    merged.setdefault("HTTP_PROXY", DEFAULT_PROXY)
    merged.setdefault("https_proxy", merged["HTTPS_PROXY"])
    merged.setdefault("http_proxy", merged["HTTP_PROXY"])
    return merged


def curl_download(url: str, dest: Path, *, resume: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl",
        "-sS",
        "-L",
        "--fail",
        "--retry",
        "10",
        "--retry-all-errors",
        "--retry-connrefused",
        "--retry-delay",
        "3",
        "--connect-timeout",
        "30",
        "--output",
        str(dest),
    ]
    if resume:
        cmd.insert(1, "-C")
        cmd.insert(2, "-")
    cmd.append(url)
    print(f"[gui-grounding-prepare] download {url} -> {dest}", file=sys.stderr, flush=True)
    subprocess.run(cmd, cwd=REPO_ROOT, env=with_default_proxy(os.environ), check=True)


def load_or_download_json(repo: str, path: str, dest: Path) -> Any:
    for attempt in range(2):
        if not dest.exists() or dest.stat().st_size == 0:
            curl_download(repo_url(repo, path), dest)
        try:
            return json.loads(dest.read_text())
        except json.JSONDecodeError:
            if attempt == 0:
                dest.unlink(missing_ok=True)
                continue
            raise
    raise AssertionError("unreachable")


def rows_from_payload(payload: Any, *, source: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "annotations", "items", "examples"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
    raise ValueError(f"{source}: expected list-like JSON payload")


def image_file_is_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_bbox_xyxy(bbox: list[Any], image_size: list[Any]) -> list[int]:
    if len(bbox) != 4:
        raise ValueError(f"bbox must have 4 values, got {bbox!r}")
    width, height = [float(v) for v in image_size[:2]]
    x1, y1, x2, y2 = [float(v) for v in bbox]
    if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
        x1 *= width
        x2 *= width
        y1 *= height
        y2 *= height
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    x1 = clamp(x1, 0, width)
    x2 = clamp(x2, 0, width)
    y1 = clamp(y1, 0, height)
    y2 = clamp(y2, 0, height)
    return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


def safe_rel_path(value: str) -> str:
    rel = value.lstrip("/").replace("\\", "/")
    parts = [part for part in rel.split("/") if part and part not in (".", "..")]
    return "/".join(parts)


def download_ui_vision_image(image_path: str, raw_dir: Path) -> bool:
    dest = raw_dir / image_path
    if image_file_is_valid(dest):
        return False
    last_error = None
    for attempt in range(1, 4):
        try:
            curl_download(repo_url(UI_VISION_REPO, f"images/{image_path}"), dest)
            if image_file_is_valid(dest):
                return True
            raise OSError(f"downloaded UI-Vision image is invalid: {dest}")
        except (OSError, subprocess.CalledProcessError) as exc:
            last_error = exc
            dest.unlink(missing_ok=True)
            if attempt < 3:
                print(
                    f"[gui-grounding-prepare] retry ui_vision image {attempt}/3 {image_path}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
    if last_error is not None:
        raise last_error
    if not image_file_is_valid(dest):
        dest.unlink(missing_ok=True)
        raise OSError(f"downloaded UI-Vision image is invalid: {dest}")
    return False


def prepare_ui_vision(cfg: dict[str, Any], *, metadata_only: bool, image_workers: int) -> dict[str, Any]:
    data_dir = REPO_ROOT / cfg["data_dir"]
    ann_dir = data_dir / "annotations"
    meta_dir = data_dir / "metadata"
    raw_dir = data_dir / "raw_images"
    ann_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "dataset": "ui_vision",
        "source_repo": UI_VISION_REPO,
        "data_dir": str(data_dir.relative_to(REPO_ROOT)),
        "annotations": {},
        "samples": 0,
        "unique_images": 0,
        "images_downloaded": 0,
        "metadata_only": metadata_only,
    }
    unique_images: set[str] = set()

    for split, manifest_path in cfg["splits"]:
        local_manifest = meta_dir / Path(manifest_path).name
        rows = rows_from_payload(
            load_or_download_json(cfg["repo"], manifest_path, local_manifest),
            source=manifest_path,
        )
        samples: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            image_path = safe_rel_path(str(row.get("image_path") or ""))
            if not image_path:
                raise ValueError(f"ui_vision/{split}/{i}: missing image_path")
            image_size = row.get("image_size")
            if not image_size:
                raise ValueError(f"ui_vision/{split}/{i}: missing image_size")
            instruction = str(row.get("prompt_to_evaluate") or row.get("instruction") or "").strip()
            if not instruction:
                raise ValueError(f"ui_vision/{split}/{i}: missing prompt_to_evaluate")
            sample_id = f"ui_vision_{split}_{i:04d}"
            samples.append(
                {
                    "img_filename": Path(image_path).name,
                    "raw_image_path": image_path,
                    "bbox": normalize_bbox_xyxy(row["bbox"], image_size),
                    "img_size": [int(image_size[0]), int(image_size[1])],
                    "instruction": instruction,
                    "id": sample_id,
                    "application": row.get("platform") or "ui_vision",
                    "platform": row.get("platform") or "ui_vision",
                    "ui_type": row.get("element_type") or row.get("category"),
                    "group": "UI-Vision",
                    "split": split,
                    "data_source": "ui_vision",
                    "dataset_version": "ui_vision",
                    "source_repo": UI_VISION_REPO,
                    "source_image_path": image_path,
                    "category": row.get("category"),
                    "element_type": row.get("element_type"),
                }
            )
            unique_images.add(image_path)

        ann_path = ann_dir / f"ui_vision_{split}.json"
        ann_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
        summary["annotations"][ann_path.name] = len(samples)
        summary["samples"] += len(samples)

    if not metadata_only:
        missing_images = [image_path for image_path in sorted(unique_images) if not image_file_is_valid(raw_dir / image_path)]
        summary["images_cached"] = len(unique_images) - len(missing_images)
        workers = max(1, image_workers)
        if workers == 1:
            iterator = enumerate(missing_images, 1)
            for i, image_path in iterator:
                print(
                    f"[gui-grounding-prepare] ui_vision image {i}/{len(missing_images)} {image_path}",
                    file=sys.stderr,
                    flush=True,
                )
                if download_ui_vision_image(image_path, raw_dir):
                    summary["images_downloaded"] += 1
        else:
            print(
                f"[gui-grounding-prepare] ui_vision downloading {len(missing_images)} images with {workers} workers",
                file=sys.stderr,
                flush=True,
            )
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(download_ui_vision_image, image_path, raw_dir): image_path
                    for image_path in missing_images
                }
                for i, future in enumerate(as_completed(futures), 1):
                    image_path = futures[future]
                    if future.result():
                        summary["images_downloaded"] += 1
                    if i % 25 == 0 or i == len(futures):
                        print(
                            f"[gui-grounding-prepare] ui_vision images {i}/{len(futures)} done; latest={image_path}",
                            file=sys.stderr,
                            flush=True,
                        )

    summary["unique_images"] = len(unique_images)
    (data_dir / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def prepare_mmbench_gui_l2(cfg: dict[str, Any], *, metadata_only: bool) -> dict[str, Any]:
    data_dir = REPO_ROOT / cfg["data_dir"]
    ann_dir = data_dir / "annotations"
    meta_dir = data_dir / "metadata"
    raw_dir = data_dir / "raw_images"
    ann_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = cfg["manifest"]
    local_manifest = meta_dir / manifest_path
    rows = rows_from_payload(
        load_or_download_json(cfg["repo"], manifest_path, local_manifest),
        source=manifest_path,
    )

    by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unique_images: set[str] = set()
    type_counts: Counter[str] = Counter()
    grounding_counts: Counter[str] = Counter()

    for i, row in enumerate(rows):
        image_path = safe_rel_path(str(row.get("image_path") or ""))
        platform = safe_rel_path(str(row.get("platform") or "unknown"))
        if not image_path:
            raise ValueError(f"mmbench_gui_l2/{i}: missing image_path")
        image_size = row.get("image_size")
        if not image_size:
            raise ValueError(f"mmbench_gui_l2/{i}: missing image_size")
        instruction = str(row.get("instruction") or "").strip()
        if not instruction:
            raise ValueError(f"mmbench_gui_l2/{i}: missing instruction")
        raw_image_path = f"{platform}/{image_path}"
        row_index = row.get("index", i)
        sample_id = f"mmbench_gui_l2_{platform}_{int(row_index):04d}"
        sample = {
            "img_filename": Path(image_path).name,
            "raw_image_path": raw_image_path,
            "bbox": normalize_bbox_xyxy(row["bbox"], image_size),
            "img_size": [int(image_size[0]), int(image_size[1])],
            "instruction": instruction,
            "id": sample_id,
            "application": row.get("app_name") or platform,
            "platform": platform,
            "ui_type": row.get("data_type"),
            "group": "MMBench-GUI-L2",
            "split": platform,
            "data_source": "mmbench_gui_l2",
            "dataset_version": "mmbench_gui_l2",
            "source_repo": MMBENCH_REPO,
            "source_image_path": image_path,
            "source_index": row_index,
            "app_name": row.get("app_name"),
            "grounding_type": row.get("grounding_type"),
        }
        by_platform[platform].append(sample)
        unique_images.add(raw_image_path)
        if row.get("data_type"):
            type_counts[str(row["data_type"])] += 1
        if row.get("grounding_type"):
            grounding_counts[str(row["grounding_type"])] += 1

    annotations: dict[str, int] = {}
    for platform, samples in sorted(by_platform.items()):
        ann_path = ann_dir / f"mmbench_gui_l2_{platform}.json"
        ann_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
        annotations[ann_path.name] = len(samples)

    summary: dict[str, Any] = {
        "dataset": "mmbench_gui_l2",
        "source_repo": MMBENCH_REPO,
        "data_dir": str(data_dir.relative_to(REPO_ROOT)),
        "annotations": annotations,
        "samples": sum(annotations.values()),
        "unique_images": len(unique_images),
        "data_type_counts": dict(sorted(type_counts.items())),
        "grounding_type_counts": dict(sorted(grounding_counts.items())),
        "images_extracted": 0,
        "metadata_only": metadata_only,
    }

    if not metadata_only:
        summary["images_extracted"] = extract_mmbench_images(cfg, sorted(unique_images))

    (data_dir / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def valid_zip(path: Path) -> bool:
    try:
        return path.exists() and is_zipfile(path)
    except OSError:
        return False


def ensure_mmbench_zip(cfg: dict[str, Any]) -> Path:
    data_dir = REPO_ROOT / cfg["data_dir"]
    zip_path = data_dir / cfg["zip_path"]
    if valid_zip(zip_path):
        return zip_path
    if zip_path.exists():
        try:
            curl_download(repo_url(cfg["repo"], cfg["zip_path"]), zip_path, resume=True)
        except subprocess.CalledProcessError:
            zip_path.unlink(missing_ok=True)
            curl_download(repo_url(cfg["repo"], cfg["zip_path"]), zip_path)
    else:
        curl_download(repo_url(cfg["repo"], cfg["zip_path"]), zip_path)
    if not valid_zip(zip_path):
        zip_path.unlink(missing_ok=True)
        curl_download(repo_url(cfg["repo"], cfg["zip_path"]), zip_path)
    if not valid_zip(zip_path):
        raise BadZipFile(f"not a valid zip after download: {zip_path}")
    return zip_path


def extract_mmbench_images(cfg: dict[str, Any], needed: list[str]) -> int:
    data_dir = REPO_ROOT / cfg["data_dir"]
    raw_dir = data_dir / "raw_images"
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = ensure_mmbench_zip(cfg)
    extracted = 0

    with ZipFile(zip_path) as zf:
        by_ref: dict[str, str] = {}
        by_basename: dict[str, list[str]] = defaultdict(list)
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            norm = safe_rel_path(member)
            key = norm.removeprefix("offline_images/")
            by_ref[key] = member
            by_basename[Path(key).name].append(member)

        missing: list[str] = []
        for i, ref in enumerate(needed, 1):
            member = by_ref.get(ref)
            if member is None:
                basename_matches = by_basename.get(Path(ref).name, [])
                if len(basename_matches) == 1:
                    member = basename_matches[0]
            if member is None:
                missing.append(ref)
                continue
            dest = raw_dir / ref
            if image_file_is_valid(dest):
                continue
            print(
                f"[gui-grounding-prepare] mmbench extract {i}/{len(needed)} {ref}",
                file=sys.stderr,
                flush=True,
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(f".{dest.name}.tmp")
            with zf.open(member) as src, tmp.open("wb") as out:
                shutil.copyfileobj(src, out)
            tmp.replace(dest)
            extracted += 1
        if missing:
            raise FileNotFoundError(f"{len(missing)} MMBench images missing from zip; first: {missing[:5]}")
    return extracted


def parse_datasets(value: str) -> list[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names or names == ["all"]:
        names = list(DATASETS.keys())
    unknown = [name for name in names if name not in DATASETS]
    if unknown:
        raise ValueError(f"unknown dataset(s): {', '.join(unknown)}")
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", default="ui_vision,mmbench_gui_l2", help="Comma-separated dataset keys or all")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--image-workers", type=int, default=8, help="Parallel image downloads for UI-Vision")
    args = parser.parse_args()

    payload: dict[str, Any] = {"datasets": {}}
    for dataset in parse_datasets(args.datasets):
        cfg = DATASETS[dataset]
        if dataset == "ui_vision":
            summary = prepare_ui_vision(cfg, metadata_only=args.metadata_only, image_workers=args.image_workers)
        elif dataset == "mmbench_gui_l2":
            summary = prepare_mmbench_gui_l2(cfg, metadata_only=args.metadata_only)
        else:
            raise AssertionError(dataset)
        payload["datasets"][dataset] = summary
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
