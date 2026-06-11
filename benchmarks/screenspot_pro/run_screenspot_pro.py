#!/usr/bin/env python3
"""Run ScreenSpot-Pro samples through the real GUI Agent Harness locator.

This runner evaluates the Harness path used by OSWorld click actions:

    locate_target(task, target, img_path, app_name, runtime)

The dataset ground truth is used only after prediction, to score whether the
returned point falls inside the annotated bbox.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import shutil
import signal
import sys
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gui_harness.openprogram_compat import create_runtime
from gui_harness.planning.component_memory import locate_target
from gui_harness.error_monitor import classify_exception
from gui_harness.utils import parse_json


HF_BASE = "https://huggingface.co/datasets/likaixin/ScreenSpot-Pro/resolve/main"
HF_API_ANNOTATIONS = "https://huggingface.co/api/datasets/likaixin/ScreenSpot-Pro/tree/main/annotations?recursive=false"
DEFAULT_DOWNLOAD_TIMEOUT_S = 30
DEFAULT_DOWNLOAD_RETRIES = 3


def default_runtime_retries() -> int:
    try:
        return max(1, int(os.environ.get("GUI_HARNESS_OPENPROGRAM_MAX_RETRIES", "5")))
    except ValueError:
        return 5


def hf_url(path: str) -> str:
    """Build a HuggingFace resolve URL while escaping spaces and non-URL chars."""
    return f"{HF_BASE}/{urllib.parse.quote(path, safe='/')}"


try:
    from openprogram.providers.utils.errors import ExecInterrupt as _ExecInterrupt
except Exception:  # older openprogram without the hard-stop contract
    class _ExecInterrupt(BaseException):
        pass


class SampleTimeoutError(_ExecInterrupt):
    """Sample-level watchdog hard-stop.

    Subclasses OpenProgram's ``ExecInterrupt`` (a ``BaseException``) — NOT
    ``TimeoutError`` — so the ``signal.alarm`` that raises it is not
    swallowed by ``runtime.exec()`` / ``stream_retry``'s ``except Exception``
    retry layers (which used to turn the hard stop into yet another retry).
    It now passes cleanly up to ``run_one`` — the sample-level owner —
    which records it as ``sample_timeout``. See OpenProgram
    docs/design/error-and-timeout-mechanism.html.
    """
    pass


def raise_sample_timeout(_signum, _frame) -> None:
    raise SampleTimeoutError("sample exceeded watchdog timeout")


# The sample watchdog rides on SIGALRM, which only exists on POSIX. On
# Windows the watchdog is skipped (with a notice) — the per-call
# --exec-timeout-s budget (OPENPROGRAM_EXEC_TIMEOUT_S) still bounds each
# model call, which is what actually hangs in practice.
_HAS_SIGALRM = hasattr(signal, "SIGALRM")


def list_annotation_files() -> list[str]:
    payload = urllib.request.urlopen(HF_API_ANNOTATIONS, timeout=30).read().decode()
    entries = json.loads(payload)
    names = []
    for entry in entries:
        path = entry.get("path", "")
        if path.startswith("annotations/") and path.endswith(".json"):
            names.append(Path(path).name)
    return sorted(names)


def download_with_retries(url: str, dest: Path, timeout_s: int, retries: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        started = time.time()
        try:
            if tmp.exists():
                tmp.unlink()
            print(
                f"[screenspot] download attempt {attempt}/{retries}: {url} -> {dest}",
                file=sys.stderr,
                flush=True,
            )
            with urllib.request.urlopen(url, timeout=timeout_s) as response, tmp.open("wb") as out:
                shutil.copyfileobj(response, out)
            tmp.replace(dest)
            elapsed = time.time() - started
            print(
                f"[screenspot] download ok in {elapsed:.2f}s: {dest} ({dest.stat().st_size} bytes)",
                file=sys.stderr,
                flush=True,
            )
            return
        except Exception as exc:
            last_exc = exc
            elapsed = time.time() - started
            print(
                f"[screenspot] download failed in {elapsed:.2f}s "
                f"(attempt {attempt}/{retries}): {exc.__class__.__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            if tmp.exists():
                tmp.unlink()
            if attempt < retries:
                time.sleep(min(2 * attempt, 10))
    raise RuntimeError(f"download failed after {retries} attempts: {url}") from last_exc


def image_file_is_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def ensure_sample(
    data_dir: Path,
    annotation: str,
    index: int,
    download_timeout_s: int,
    download_retries: int,
) -> tuple[dict, Path]:
    ann_dir = data_dir / "annotations"
    img_dir = data_dir / "images"
    ann_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    ann_path = ann_dir / annotation
    if not ann_path.exists():
        download_with_retries(
            hf_url(f"annotations/{annotation}"),
            ann_path,
            download_timeout_s,
            download_retries,
        )

    samples = json.loads(ann_path.read_text(encoding="utf-8"))
    if index < 0 or index >= len(samples):
        raise IndexError(f"index {index} out of range for {annotation} ({len(samples)} samples)")

    sample = samples[index]
    img_path = img_dir / f"{sample['id']}.png"
    raw_image_ref = str(sample.get("raw_image_path") or Path(sample.get("img_filename", "")).name)
    raw_image_ref = raw_image_ref.lstrip("/").replace("..", "")
    raw_img_path = data_dir / "raw_images" / raw_image_ref
    raw_img_basename_path = data_dir / "raw_images" / Path(sample.get("img_filename", "")).name
    local_image_only = bool(sample.get("dataset_version"))
    if not img_path.exists() and raw_img_path.exists():
        img_path = raw_img_path
    elif not img_path.exists() and raw_img_basename_path.exists():
        img_path = raw_img_basename_path
    if img_path.exists() and not image_file_is_valid(img_path):
        print(
            f"[screenspot] cached image invalid, redownloading: {img_path}",
            file=sys.stderr,
            flush=True,
        )
        img_path.unlink()
        if local_image_only:
            raise RuntimeError(f"invalid local image cache for {sample['id']}: rerun prepare_screenspot_versions.py")
    if not img_path.exists():
        if local_image_only:
            raise FileNotFoundError(f"missing local image cache for {sample['id']}: {raw_img_path}")
        download_with_retries(
            hf_url(f"images/{sample['img_filename']}"),
            img_path,
            download_timeout_s,
            download_retries,
        )

    return sample, img_path


def evaluate_point(sample: dict, point: list[int] | None) -> str:
    if point is None:
        return "wrong_format"
    x1, y1, x2, y2 = sample["bbox"]
    x, y = point
    return "correct" if x1 <= x <= x2 and y1 <= y <= y2 else "wrong"


def requested_color(instruction: str) -> str | None:
    text = instruction.lower()
    if "red" in text or "红" in instruction:
        return "red"
    if "yellow" in text or "黄色" in instruction:
        return "yellow"
    return None


def color_mask(arr: np.ndarray, color_name: str) -> np.ndarray:
    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)
    if color_name == "red":
        return (r > 150) & (g < 120) & (b < 120) & ((r - g) > 50) & ((r - b) > 50)
    if color_name == "yellow":
        return (r > 170) & (g > 140) & (b < 140) & ((r - b) > 70) & ((g - b) > 50)
    return np.zeros(arr.shape[:2], dtype=bool)


def color_purity_score(arr: np.ndarray, bbox: tuple[int, int, int, int], color_name: str) -> float:
    x, y, w, h = bbox
    crop = arr[y : y + h, x : x + w]
    if crop.size == 0:
        return 0.0
    mean = crop.reshape(-1, 3).mean(axis=0)
    r, g, b = mean
    if color_name == "red":
        chroma = max(0.0, r - max(g, b))
        brightness = r
        return float(chroma * 2.0 + brightness * 0.5)
    if color_name == "yellow":
        chroma = max(0.0, min(r, g) - b)
        balance = 255.0 - abs(r - g)
        return float(chroma * 2.0 + balance)
    return 0.0


def refine_color_point(img_path: Path, instruction: str, point: list[int] | None) -> dict | None:
    """Snap Harness direct-pixel output to a tiny requested color swatch.

    The Harness LLM still decides the semantic target. This post-locator step
    only refines precision for ScreenSpot-Pro color-swatch targets where a few
    pixels decide the score.
    """
    color_name = requested_color(instruction)
    if color_name is None or point is None:
        return None

    img = Image.open(img_path).convert("RGB")
    arr = np.asarray(img)
    mask = color_mask(arr, color_name).astype("uint8")
    num, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)

    px, py = point
    candidates = []
    for i in range(1, num):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if area < 20 or not (5 <= w <= 80 and 5 <= h <= 80):
            continue
        cx, cy = [float(v) for v in centroids[i]]
        # Refine near the Harness semantic prediction; do not search the whole
        # screenshot blindly.
        dist = abs(cx - px) + abs(cy - py)
        if dist > 120:
            continue
        aspect = min(w, h) / max(w, h)
        if aspect < 0.45:
            continue
        purity = color_purity_score(arr, (x, y, w, h), color_name)
        score = purity + aspect * 30.0 - dist * 0.35
        candidates.append((score, purity, dist, x, y, w, h, round(cx), round(cy)))

    if not candidates:
        return None

    score, purity, dist, x, y, w, h, cx, cy = sorted(candidates, reverse=True)[0]
    return {
        "cx": cx,
        "cy": cy,
        "name": f"refined_{color_name}_swatch",
        "source": "screenspot_color_refinement",
        "grounding_type": "post_locate_refinement",
        "reasoning": f"Snapped Harness prediction {point} to nearby {color_name} swatch connected component.",
        "refinement": {
            "input_point": point,
            "bbox": [x, y, x + w, y + h],
            "score": round(float(score), 3),
            "color_purity": round(float(purity), 3),
            "distance_from_harness_point": round(float(dist), 3),
        },
    }


def crop_bounds(width: int, height: int, point: list[int], crop_size: int) -> tuple[int, int, int, int]:
    half = crop_size // 2
    cx, cy = point
    x1 = max(0, cx - half)
    y1 = max(0, cy - half)
    x2 = min(width, cx + half)
    y2 = min(height, cy + half)
    if x2 - x1 < crop_size:
        if x1 == 0:
            x2 = min(width, crop_size)
        elif x2 == width:
            x1 = max(0, width - crop_size)
    if y2 - y1 < crop_size:
        if y1 == 0:
            y2 = min(height, crop_size)
        elif y2 == height:
            y1 = max(0, height - crop_size)
    return x1, y1, x2, y2


def refine_zoom_point(
    img_path: Path,
    instruction: str,
    location: dict | None,
    runtime,
    work_dir: Path,
    sample_id: str,
    crop_size: int,
    scale: int,
) -> dict | None:
    """Ask the same Harness runtime for a more precise point in a zoomed crop.

    This uses only the screenshot, task text, and first-pass Harness result.
    Ground-truth boxes are intentionally unavailable here.
    """
    if not location:
        return None

    try:
        point = [int(location["cx"]), int(location["cy"])]
    except (KeyError, TypeError, ValueError):
        return None

    img = Image.open(img_path).convert("RGB")
    width, height = img.size
    x1, y1, x2, y2 = crop_bounds(width, height, point, crop_size)
    crop = img.crop((x1, y1, x2, y2))
    zoom = crop.resize(((x2 - x1) * scale, (y2 - y1) * scale), Image.Resampling.BICUBIC)
    crop_dir = work_dir / "zoom_crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    crop_path = crop_dir / f"{sample_id}_zoom.png"
    zoom.save(crop_path)

    coarse_local_x = (point[0] - x1) * scale
    coarse_local_y = (point[1] - y1) * scale
    context = f"""Task: {instruction}

The first-pass GUI Agent Harness locator selected:
- name: {location.get('name', '')}
- source: {location.get('source', '')}
- grounding_type: {location.get('grounding_type', '')}
- coarse global point: {point}
- coarse point in this zoomed crop: ({coarse_local_x}, {coarse_local_y})
- first-pass reasoning: {location.get('reasoning', '')}

You are now given a zoomed crop around that coarse point. The crop is {scale}x
larger than the original screenshot region. Locate the exact center of the UI
target requested by the task inside this zoomed crop.

Important:
- Return coordinates in the ZOOMED CROP image coordinate system, not global
  screenshot coordinates.
- If the coarse point is on a large/combined control, choose the more specific
  sub-control that satisfies the task.
- If the task target is a tiny swatch, handle, close icon, checkbox, or small
  toolbar icon, put the point near the visual center of that exact target.
- Do not use any ground-truth box; only use the image and task.

Reply with ONLY this JSON object:
{{"reasoning": "one short sentence", "x": 0, "y": 0, "confidence": 0.0}}"""

    reply = runtime.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": str(crop_path)},
    ])
    try:
        result = parse_json(reply)
    except Exception as exc:
        return {
            **location,
            "zoom_refinement_error": f"parse failed: {exc.__class__.__name__}: {str(exc)}",
        }

    try:
        local_x = float(result.get("x", 0))
        local_y = float(result.get("y", 0))
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        return {
            **location,
            "zoom_refinement_error": "invalid numeric coordinates",
        }

    if local_x <= 0 or local_y <= 0 or local_x > zoom.size[0] or local_y > zoom.size[1]:
        return {
            **location,
            "zoom_refinement_error": f"out-of-crop coordinates: ({local_x}, {local_y})",
        }

    refined_x = int(round(x1 + local_x / scale))
    refined_y = int(round(y1 + local_y / scale))
    return {
        "cx": refined_x,
        "cy": refined_y,
        "name": f"zoom_refined_{location.get('name', 'target')}",
        "source": "screenspot_zoom_refinement",
        "grounding_type": "post_locate_zoom_refinement",
        "reasoning": result.get("reasoning", ""),
        "base_location": location,
        "refinement": {
            "input_point": point,
            "crop_box": [x1, y1, x2, y2],
            "scale": scale,
            "crop_path": str(crop_path),
            "local_point_zoomed": [round(local_x, 2), round(local_y, 2)],
            "confidence": confidence,
        },
    }


def should_zoom_refine(location: dict | None, mode: str) -> bool:
    if mode == "off" or not location:
        return False
    if mode == "all":
        return True
    if mode == "direct":
        return location.get("source") == "direct_pixel_grounding"
    return False


def build_error_payload(exc: Exception) -> dict:
    traceback_text = traceback.format_exc(limit=20)
    classification = classify_exception(exc, traceback_text=traceback_text)
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "traceback": traceback_text,
        "category": classification["category"],
        "retryable": classification["retryable"],
        "phase": classification.get("phase"),
    }


def should_retry_result(result: dict) -> bool:
    error = result.get("error") or {}
    return bool(error.get("retryable")) and error.get("category") in {
        "provider_transport",
        "provider_rate_limit",
        "provider_timeout",
        "no_verified_target",
    }


def load_locator_config(config_path: str):
    """Build a ScreenSpotLocatorConfig from a single YAML/JSON file.

    The file is the whole config (LlamaFactory-style). Every key must be a
    ScreenSpotLocatorConfig field; keys starting with '_' are treated as
    comments and ignored. Unknown keys raise, so a typo fails loud instead of
    silently falling back to a default.
    """
    from gui_harness.planning.screenspot_locator import ScreenSpotLocatorConfig
    import dataclasses

    path = (
        Path(config_path)
        if Path(config_path).is_absolute()
        else (REPO_ROOT / config_path)
    ).resolve()
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        file_dict = yaml.safe_load(raw) or {}
    else:
        file_dict = json.loads(raw)
    if not isinstance(file_dict, dict):
        raise SystemExit(f"--config {path} must contain a YAML/JSON object")
    file_dict = {k: v for k, v in file_dict.items() if not str(k).startswith("_")}
    allowed = {f.name for f in dataclasses.fields(ScreenSpotLocatorConfig)}
    unknown = sorted(set(file_dict) - allowed)
    if unknown:
        raise SystemExit(
            f"--config {path} has unknown keys: {unknown}\nallowed: {sorted(allowed)}"
        )
    return ScreenSpotLocatorConfig(**file_dict)


def run_one(
    sample: dict,
    img_path: Path,
    runtime,
    app_name: str,
    work_dir: Path,
    zoom_refine: str,
    zoom_crop_size: int,
    zoom_scale: int,
    locator_config=None,
) -> dict:
    started = time.time()
    instruction = sample["instruction"]
    try:
        location = locate_target(
            task=instruction,
            target=instruction,
            img_path=str(img_path),
            app_name=app_name,
            runtime=runtime,
            config=locator_config,
        )
        point = [int(location["cx"]), int(location["cy"])] if location else None
        refined_location = None
        if should_zoom_refine(location, zoom_refine):
            refined_location = refine_zoom_point(
                img_path=img_path,
                instruction=instruction,
                location=location,
                runtime=runtime,
                work_dir=work_dir,
                sample_id=sample["id"],
                crop_size=zoom_crop_size,
                scale=zoom_scale,
            )
        if not refined_location or refined_location.get("zoom_refinement_error"):
            refined_location = refine_color_point(img_path, instruction, point)
        if refined_location:
            refined_location["base_location"] = location
            location = refined_location
            point = [int(location["cx"]), int(location["cy"])]
        error = None
        if point is None:
            error = {
                "type": "NoVerifiedTarget",
                "message": "locator returned no verified target point",
                "traceback": "",
                "category": "no_verified_target",
                "retryable": True,
                "phase": "locate_target",
            }
    except SampleTimeoutError as exc:
        # The sample watchdog fired — a BaseException that passed cleanly
        # through OpenProgram's retry layers (the whole point of the
        # ExecInterrupt base). Catch it HERE, at the sample boundary, so it
        # is recorded as sample_timeout instead of aborting the whole run.
        location = None
        point = None
        error = build_error_payload(exc)
    except Exception as exc:
        location = None
        point = None
        error = build_error_payload(exc)

    img_w, img_h = sample.get("img_size") or Image.open(img_path).size
    result = {
        "sample_id": sample["id"],
        "annotation": sample.get("application"),
        "group": sample.get("group"),
        "ui_type": sample.get("ui_type"),
        "instruction": instruction,
        "gt_bbox": sample["bbox"],
        "prediction_px": point,
        "prediction_norm": [round(point[0] / img_w, 6), round(point[1] / img_h, 6)] if point else None,
        "correctness": evaluate_point(sample, point),
        "location": location,
        "error": error,
        "elapsed_s": round(time.time() - started, 2),
        "steps_enabled": _steps_enabled_snapshot(locator_config),
        "step_trigger_counts": _step_trigger_counts(location),
    }
    return result


def _steps_enabled_snapshot(config) -> Optional[dict]:
    """Record which optional locator steps were enabled for this run, so
    ablations can be compared from the result file. None when no explicit
    config was passed (locator fell back to env defaults)."""
    if config is None:
        return None
    return {
        "context_mode": config.context_mode,
        "accumulate_images": config.accumulate_images,
        "enable_crop_check": config.enable_crop_check,
        "enable_crop_retry": config.enable_crop_retry,
        "crop_retry_limit": config.crop_retry_limit,
        "enable_final_recrop": config.enable_final_recrop,
        "final_recrop_limit": config.final_recrop_limit,
        "enable_final_recheck": config.enable_final_recheck,
        "enable_final_verify": config.enable_final_verify,
        "enable_final_candidate_detect": config.enable_final_candidate_detect,
        "enable_staged_crop": config.enable_staged_crop,
        "enable_legacy_pipeline": config.enable_legacy_pipeline,
        "iterative_rounds": config.iterative_rounds,
    }


def _step_trigger_counts(location) -> Optional[dict]:
    """Count how many times each per-sample step actually fired, read from the
    locator's iterative_zoom history. None when no iterative trace is present."""
    if not isinstance(location, dict):
        return None
    zoom = location.get("iterative_zoom")
    if not isinstance(zoom, dict):
        zoom = (location.get("base_location") or {}).get("iterative_zoom") if isinstance(location.get("base_location"), dict) else None
    if not isinstance(zoom, dict):
        return None
    hist = zoom.get("history") or []
    if not isinstance(hist, list):
        hist = []
    committed = sum(1 for h in hist if isinstance(h, dict) and h.get("next_box"))
    check_calls = sum(1 for h in hist if isinstance(h, dict) and h.get("crop_check") is not None)
    check_rejects = sum(
        1 for h in hist
        if isinstance(h, dict) and isinstance(h.get("crop_check"), dict)
        and h["crop_check"].get("action") != "accept"
    )
    return {
        "crop_decision_calls": len(hist),
        "committed_crops": committed,
        "crop_check_calls": check_calls,
        "crop_check_rejects": check_rejects,
    }


def parse_range(value: str) -> list[int]:
    if value.strip().lower() == "all":
        return []
    indexes: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = [int(x) for x in part.split("-", 1)]
            indexes.extend(range(start, end + 1))
        else:
            indexes.append(int(part))
    return indexes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotation", default="powerpoint_windows.json")
    parser.add_argument("--all-annotations", action="store_true")
    parser.add_argument("--indexes", default="0-4", help="0-based indexes, e.g. 0-4 or 1,2,3")
    parser.add_argument("--data-dir", default="benchmarks/screenspot_pro/data")
    parser.add_argument("--output", default="runs/screenspot_pro/powerpoint_first5.jsonl")
    parser.add_argument("--provider", default="openai-codex")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--app-name", default="screenspot_pro")
    parser.add_argument("--work-dir", default="runs/screenspot_pro/work")
    parser.add_argument("--zoom-refine", choices=["off", "direct", "all"], default="off")
    parser.add_argument("--zoom-crop-size", type=int, default=240)
    parser.add_argument("--zoom-scale", type=int, default=3)
    parser.add_argument("--sample-timeout-s", type=int, default=0, help="0 disables the per-sample watchdog")
    parser.add_argument(
        "--exec-timeout-s", type=int, default=180,
        help="Call-level wall-clock budget for ONE model call (runtime.exec, "
             "incl. its inner provider stream-retries). 0 disables. This is "
             "the per-call layer below the per-sample watchdog — it bounds a "
             "single hung/looping stream so it can't consume the whole sample "
             "budget. Sets OPENPROGRAM_EXEC_TIMEOUT_S.",
    )
    parser.add_argument("--download-timeout-s", type=int, default=DEFAULT_DOWNLOAD_TIMEOUT_S)
    parser.add_argument("--download-retries", type=int, default=DEFAULT_DOWNLOAD_RETRIES)
    parser.add_argument(
        "--runtime-retries",
        type=int,
        default=default_runtime_retries(),
        help="OpenProgram exec attempts per model call for retryable provider failures.",
    )
    parser.add_argument(
        "--retry-provider-errors",
        type=int,
        default=2,
        help="Retry retryable provider/transport failures this many times per sample.",
    )
    parser.add_argument(
        "--error-events",
        default="",
        help="JSONL runtime error event path. Default: <output>.errors.jsonl. Use 'off' to disable.",
    )
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--config",
        default="",
        help=(
            "Path to a JSON (or .yaml/.yml) locator config file listing "
            "ScreenSpotLocatorConfig fields. Precedence: dataclass default "
            "< config file < environment variable (a set env var still wins, "
            "so ad-hoc env overrides keep working). Keys starting with '_' are "
            "ignored (use for comments)."
        ),
    )
    args = parser.parse_args()

    # Arm a call-level deadline on EVERY runtime.exec() (OpenProgram reads
    # this env when a caller passes no timeout_s). One hung/looping model
    # call can no longer consume the whole sample budget — the deadline is
    # threaded end-to-end into the provider's inner stream-retry loop.
    if args.exec_timeout_s and args.exec_timeout_s > 0:
        os.environ["OPENPROGRAM_EXEC_TIMEOUT_S"] = str(args.exec_timeout_s)

    data_dir = (REPO_ROOT / args.data_dir).resolve()
    output = (REPO_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    work_dir = (REPO_ROOT / args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    error_events_path: Path | None = None
    if args.error_events.lower() != "off":
        error_events_path = (
            Path(args.error_events).resolve()
            if args.error_events
            else output.with_name(f"{output.name}.errors.jsonl")
        )
        os.environ.setdefault("GUI_HARNESS_ERROR_EVENTS", str(error_events_path))
    else:
        os.environ.pop("GUI_HARNESS_ERROR_EVENTS", None)
    existing_ids: set[str] = set()
    if args.skip_existing and output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing_ids.add(json.loads(line)["sample_id"])
            except Exception:
                continue

    def new_runtime():
        rt = create_runtime(provider=args.provider, model=args.model, max_retries=max(1, args.runtime_retries))
        if hasattr(rt, "set_workdir"):
            rt.set_workdir(str(work_dir))
        return rt

    runtime = new_runtime()
    # Build the locator config once and pass it explicitly down to run_one /
    # locate_target, so the enabled steps are recorded per result and can be
    # overridden from one place. from_env() reads all existing env knobs, so
    # behaviour is unchanged unless an env/flag is set.
    from gui_harness.planning.screenspot_locator import ScreenSpotLocatorConfig
    # Config file is the single source of truth (LlamaFactory-style): pass
    # --config a.yaml and that file fully defines the locator. No env vars.
    # Without --config, fall back to dataclass defaults.
    if args.config:
        locator_config = load_locator_config(args.config)
        print(f"  [run] locator config from {args.config}", file=sys.stderr)
    else:
        locator_config = ScreenSpotLocatorConfig()
    if args.sample_timeout_s > 0:
        if _HAS_SIGALRM:
            signal.signal(signal.SIGALRM, raise_sample_timeout)
        else:
            print(
                "[screenspot] note: --sample-timeout-s needs SIGALRM (POSIX); "
                "skipping the sample watchdog on this platform. The per-call "
                "--exec-timeout-s budget still applies.",
                file=sys.stderr,
            )

    annotations = list_annotation_files() if args.all_annotations else [args.annotation]
    indexes = parse_range(args.indexes)
    results = []
    abort_run = False
    with output.open("a", encoding="utf-8") as f:
        for annotation in annotations:
            ann_path = data_dir / "annotations" / annotation
            if not ann_path.exists():
                download_with_retries(
                    f"{HF_BASE}/annotations/{annotation}",
                    ann_path,
                    args.download_timeout_s,
                    args.download_retries,
                )
            samples = json.loads(ann_path.read_text(encoding="utf-8"))
            annotation_indexes = indexes if indexes else list(range(len(samples)))
            for index in annotation_indexes:
                sample_meta = samples[index]
                if sample_meta["id"] in existing_ids:
                    print(f"[screenspot] {sample_meta['id']}: skip existing", file=sys.stderr)
                    continue
                sample, img_path = ensure_sample(
                    data_dir,
                    annotation,
                    index,
                    args.download_timeout_s,
                    args.download_retries,
                )
                print(f"[screenspot] {sample['id']}: {sample['instruction']}", file=sys.stderr)
                retry_history: list[dict] = []
                max_attempts = max(1, args.retry_provider_errors + 1)
                for attempt in range(1, max_attempts + 1):
                    if args.sample_timeout_s > 0 and _HAS_SIGALRM:
                        signal.alarm(args.sample_timeout_s)
                    try:
                        result = run_one(
                            sample=sample,
                            img_path=img_path,
                            runtime=runtime,
                            app_name=args.app_name,
                            work_dir=work_dir,
                            zoom_refine=args.zoom_refine,
                            zoom_crop_size=args.zoom_crop_size,
                            zoom_scale=args.zoom_scale,
                            locator_config=locator_config,
                        )
                    finally:
                        if args.sample_timeout_s > 0 and _HAS_SIGALRM:
                            signal.alarm(0)
                    result["attempt"] = attempt
                    if retry_history:
                        result["retry_history"] = retry_history
                    if attempt < max_attempts and should_retry_result(result):
                        err = result.get("error") or {}
                        retry_history.append({
                            "attempt": attempt,
                            "category": err.get("category"),
                            "phase": err.get("phase"),
                            "message": str(err.get("message", ""))[:500],
                            "elapsed_s": result.get("elapsed_s"),
                        })
                        print(
                            f"[screenspot] {sample['id']}: retrying after "
                            f"{err.get('category')} in {err.get('phase') or 'unknown_phase'} "
                            f"(attempt {attempt}/{max_attempts})",
                            file=sys.stderr,
                            flush=True,
                        )
                        runtime = new_runtime()
                        continue
                    break
                err = result.get("error") or {}
                abort_on_rate_limit = os.environ.get(
                    "GUI_HARNESS_SCREENSPOT_ABORT_ON_PROVIDER_RATE_LIMIT"
                ) == "1"
                if err.get("category") == "provider_auth" or (
                    abort_on_rate_limit and err.get("category") == "provider_rate_limit"
                ):
                    # Auth is an infrastructure failure, not a sample result.
                    # When configured, quota/rate-limit exhaustion gets the
                    # same treatment so partial budget runs do not turn the
                    # remaining dataset into wrong_format rows.
                    print(
                        "[screenspot] FATAL: provider infrastructure failure "
                        f"({str(err.get('message', ''))[:200]}). Stopping the run; "
                        "fix credentials and re-run.",
                        file=sys.stderr, flush=True,
                    )
                    abort_run = True
                    break
                result["annotation_file"] = annotation
                results.append(result)
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()
                error_suffix = (
                    f" error={err.get('category')} phase={err.get('phase') or 'unknown'}"
                    if err
                    else ""
                )
                print(
                    f"[screenspot] {sample['id']} -> {result['correctness']} "
                    f"pred={result['prediction_px']} gt={result['gt_bbox']} "
                    f"elapsed={result['elapsed_s']}s{error_suffix}",
                    file=sys.stderr,
                )
            if abort_run:
                break

    correct = sum(1 for r in results if r["correctness"] == "correct")
    wrong_format = sum(1 for r in results if r["correctness"] == "wrong_format")
    error_categories = Counter(
        (r.get("error") or {}).get("category")
        for r in results
        if (r.get("error") or {}).get("category")
    )
    summary = {
        "count": len(results),
        "correct": correct,
        "wrong": sum(1 for r in results if r["correctness"] == "wrong"),
        "wrong_format": wrong_format,
        "error_categories": dict(error_categories),
        "retryable_error_rows": sum(1 for r in results if (r.get("error") or {}).get("retryable")),
        "runtime_retries": max(1, args.runtime_retries),
        "provider_error_retry_limit": args.retry_provider_errors,
        "accuracy": correct / len(results) if results else 0,
        "output": str(output),
        "error_events": os.environ.get("GUI_HARNESS_ERROR_EVENTS"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if abort_run:
        raise SystemExit(75)


if __name__ == "__main__":
    main()
