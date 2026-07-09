#!/usr/bin/env python3
"""Prepare ScreenSpot v1/v2 data for the local ScreenSpot-Pro runner.

The Pro runner expects local annotation JSON files and images keyed by sample
id. This script normalizes public ScreenSpot v1/v2 metadata into that shape
while keeping raw images under ``raw_images`` to avoid duplicating screenshots
that have multiple instructions.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile, is_zipfile

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROXY = "http://127.0.0.1:6152"

DATASETS: dict[str, dict[str, Any]] = {
    "v1": {
        "repo": "KevinQHLin/ScreenSpot",
        "data_dir": Path("benchmarks/screenspot_pro/data_screenspot_v1"),
        "image_prefix": "images",
        "manifests": (
            ("desktop", "metadata/screenspot_desktop.json"),
            ("mobile", "metadata/screenspot_mobile.json"),
            ("web", "metadata/screenspot_web.json"),
        ),
    },
    "v2": {
        "repo": "OS-Copilot/ScreenSpot-v2",
        "data_dir": Path("benchmarks/screenspot_pro/data_screenspot_v2"),
        "zip_path": "screenspotv2_image.zip",
        "manifests": (
            ("desktop", "screenspot_desktop_v2.json"),
            ("mobile", "screenspot_mobile_v2.json"),
            ("web", "screenspot_web_v2.json"),
        ),
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
        "-L",
        "--fail",
        "--retry",
        "10",
        "--retry-delay",
        "3",
        "--connect-timeout",
        "30",
        "--output",
        str(dest),
    ]
    if resume:
        cmd[1:1] = ["-C", "-"]
    cmd.append(url)
    print(f"[screenspot-prepare] download {url} -> {dest}", file=sys.stderr, flush=True)
    subprocess.run(cmd, cwd=REPO_ROOT, env=with_default_proxy(os.environ), check=True)


def load_or_download_json(repo: str, path: str, dest: Path) -> Any:
    if not dest.exists():
        curl_download(repo_url(repo, path), dest)
    return json.loads(dest.read_text())


def image_file_is_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def xywh_to_xyxy(bbox: list[Any]) -> list[int]:
    x, y, w, h = [float(v) for v in bbox]
    return [
        int(round(x)),
        int(round(y)),
        int(round(x + w)),
        int(round(y + h)),
    ]


def normalize_manifest(dataset: str, split: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        img_filename = row.get("img_filename") or row.get("img_url") or row.get("file_name")
        if not img_filename:
            raise ValueError(f"{dataset}/{split}/{i}: missing image filename")
        instruction = row.get("instruction") or row.get("task")
        if not instruction:
            raise ValueError(f"{dataset}/{split}/{i}: missing instruction")
        sample_id = f"screenspot_{dataset}_{split}_{i:04d}"
        samples.append({
            "img_filename": Path(str(img_filename)).name,
            "bbox": xywh_to_xyxy(row["bbox"]),
            "instruction": instruction,
            "id": sample_id,
            "application": row.get("data_source") or split,
            "platform": row.get("data_source") or split,
            "ui_type": row.get("data_type"),
            "group": split.capitalize(),
            "split": split,
            "data_source": row.get("data_source"),
            "dataset_version": dataset,
        })
    return samples


def prepare_annotations(dataset: str, cfg: dict[str, Any]) -> dict[str, Any]:
    data_dir = REPO_ROOT / cfg["data_dir"]
    ann_dir = data_dir / "annotations"
    meta_dir = data_dir / "metadata"
    ann_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "dataset": dataset,
        "data_dir": str(data_dir.relative_to(REPO_ROOT)),
        "annotations": {},
        "samples": 0,
        "unique_images": 0,
    }
    unique_images: set[str] = set()
    for split, manifest_path in cfg["manifests"]:
        local_manifest = meta_dir / Path(manifest_path).name
        rows = load_or_download_json(cfg["repo"], manifest_path, local_manifest)
        if not isinstance(rows, list):
            raise ValueError(f"{manifest_path}: expected list, got {type(rows).__name__}")
        samples = normalize_manifest(dataset, split, rows)
        ann_path = ann_dir / f"screenspot_{dataset}_{split}.json"
        ann_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
        unique_images.update(sample["img_filename"] for sample in samples)
        summary["annotations"][ann_path.name] = len(samples)
        summary["samples"] += len(samples)
    summary["unique_images"] = len(unique_images)
    (data_dir / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def all_needed_images(data_dir: Path) -> set[str]:
    needed: set[str] = set()
    for ann_path in sorted((data_dir / "annotations").glob("*.json")):
        for sample in json.loads(ann_path.read_text()):
            needed.add(sample["img_filename"])
    return needed


def download_v1_images(cfg: dict[str, Any]) -> int:
    data_dir = REPO_ROOT / cfg["data_dir"]
    raw_dir = data_dir / "raw_images"
    raw_dir.mkdir(parents=True, exist_ok=True)
    needed = all_needed_images(data_dir)
    downloaded = 0
    for i, filename in enumerate(sorted(needed), 1):
        dest = raw_dir / filename
        if image_file_is_valid(dest):
            continue
        print(f"[screenspot-prepare] v1 image {i}/{len(needed)} {filename}", file=sys.stderr, flush=True)
        curl_download(repo_url(cfg["repo"], f"{cfg['image_prefix']}/{filename}"), dest)
        downloaded += 1
    return downloaded


def valid_zip(path: Path) -> bool:
    try:
        return path.exists() and is_zipfile(path)
    except OSError:
        return False


def ensure_v2_zip(cfg: dict[str, Any]) -> Path:
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


def extract_v2_images(cfg: dict[str, Any]) -> int:
    data_dir = REPO_ROOT / cfg["data_dir"]
    raw_dir = data_dir / "raw_images"
    raw_dir.mkdir(parents=True, exist_ok=True)
    needed = all_needed_images(data_dir)
    zip_path = ensure_v2_zip(cfg)
    extracted = 0
    with ZipFile(zip_path) as zf:
        by_name = {Path(name).name: name for name in zf.namelist() if not name.endswith("/")}
        missing = sorted(filename for filename in needed if filename not in by_name)
        if missing:
            raise FileNotFoundError(f"{len(missing)} needed v2 images missing from zip; first: {missing[:5]}")
        for i, filename in enumerate(sorted(needed), 1):
            dest = raw_dir / filename
            if image_file_is_valid(dest):
                continue
            print(f"[screenspot-prepare] v2 extract {i}/{len(needed)} {filename}", file=sys.stderr, flush=True)
            tmp = dest.with_name(f".{dest.name}.tmp")
            with zf.open(by_name[filename]) as src, tmp.open("wb") as out:
                shutil.copyfileobj(src, out)
            tmp.replace(dest)
            extracted += 1
    return extracted


def parse_datasets(value: str) -> list[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names or names == ["all"]:
        names = ["v1", "v2"]
    unknown = [name for name in names if name not in DATASETS]
    if unknown:
        raise ValueError(f"unknown dataset(s): {', '.join(unknown)}")
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", default="v1,v2", help="Comma-separated: v1,v2 or all")
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()

    payload: dict[str, Any] = {"datasets": {}}
    for dataset in parse_datasets(args.datasets):
        cfg = DATASETS[dataset]
        summary = prepare_annotations(dataset, cfg)
        if not args.metadata_only:
            if dataset == "v1":
                summary["images_downloaded"] = download_v1_images(cfg)
            elif dataset == "v2":
                summary["images_extracted"] = extract_v2_images(cfg)
        payload["datasets"][dataset] = summary
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
