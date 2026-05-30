#!/usr/bin/env python3
"""
gui_harness.perception.ocr — Apple Vision OCR and EasyOCR fallback.

Moved from scripts/ui_detector.py (OCR-related functions).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


# ═══════════════════════════════════════════
# OCR — Apple Vision (macOS) or EasyOCR (cross-platform fallback)
# ═══════════════════════════════════════════

def detect_text(img_path: str, return_logical: bool = False) -> list:
    """Detect text using Apple Vision (macOS) or EasyOCR (Linux/fallback).

    Returns coordinates in screenshot pixel space (same as GPA detect_icons).
    Coordinate conversion to logical (pynput) space happens in detect_all().

    Platform selection:
    - macOS with Swift available → Apple Vision (fastest, best quality)
    - Linux or macOS without Swift → EasyOCR (requires: pip install easyocr)
    - Neither available → returns empty list

    Args:
        img_path: path to screenshot image
        return_logical: DEPRECATED. Kept for backwards compatibility.
                       Previously auto-converted retina coords to logical coords.
                       Now defaults to False — callers should use detect_all() instead.
    """
    import platform
    if platform.system() == "Darwin":
        return _detect_text_apple_vision(img_path, return_logical)
    else:
        return _detect_text_easyocr(img_path)


# ── EasyOCR fallback (Linux / cross-platform) ──

_easyocr_reader = None


def _detect_text_easyocr(img_path: str) -> list:
    """Detect text using EasyOCR. Works on any platform with PyTorch.

    Requires: pip install easyocr
    First call downloads language models (~100MB for en, ~200MB for ch_sim).
    """
    global _easyocr_reader
    try:
        import easyocr
    except ImportError:
        print("⚠️ EasyOCR not installed. Run: pip install easyocr")
        return []

    if _easyocr_reader is None:
        # Auto-detect GPU: a hardcoded gpu=True crashes / warns on CPU-only
        # machines (e.g. most Windows boxes without CUDA).
        gpu = False
        try:
            import torch
            gpu = bool(torch.cuda.is_available())
        except Exception:
            gpu = False
        _easyocr_reader = easyocr.Reader(['en', 'ch_sim'], gpu=gpu, verbose=False)

    # ultralytics monkeypatches cv2.imread (for Unicode-path support), and its
    # patched IMREAD_GRAYSCALE returns (H, W, 1) instead of (H, W). easyocr's
    # internal grayscale load then crashes in get_image_list ("too many values
    # to unpack") once YOLO has run in the same process. Hand easyocr a
    # guaranteed-2D grayscale ndarray so it never takes that broken path.
    import cv2
    bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
    if bgr is None:
        print(f"⚠️ EasyOCR: could not read image {img_path}")
        return []
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if gray.ndim == 3:  # defensive: collapse any stray channel dim
        gray = gray[:, :, 0]
    results = _easyocr_reader.readtext(gray)
    elements = []
    for bbox, text, conf in results:
        x1 = int(min(p[0] for p in bbox))
        y1 = int(min(p[1] for p in bbox))
        x2 = int(max(p[0] for p in bbox))
        y2 = int(max(p[1] for p in bbox))
        w = x2 - x1
        h = y2 - y1
        elements.append({
            "type": "text",
            "source": "easyocr",
            "x": x1, "y": y1, "w": w, "h": h,
            "cx": x1 + w // 2, "cy": y1 + h // 2,
            "confidence": round(float(conf), 3),
            "label": text,
        })
    return elements


# ── Apple Vision OCR (macOS native) ──

def _detect_text_apple_vision(img_path: str, return_logical: bool = False) -> list:
    """Detect text using Apple Vision framework (macOS only)."""
    swift_code = r'''
import Vision
import AppKit
import Foundation

guard let image = NSImage(contentsOfFile: CommandLine.arguments[1]) else {
    print("[]"); exit(0)
}
guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("[]"); exit(0)
}

let w = Double(cgImage.width)
let h = Double(cgImage.height)
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en"]
request.usesLanguageCorrection = true

try handler.perform([request])
var results: [[String: Any]] = []
for obs in (request.results ?? []) {
    guard let top = obs.topCandidates(1).first else { continue }
    let box = obs.boundingBox
    let x = Int(box.origin.x * w)
    let y = Int((1.0 - box.origin.y - box.height) * h)
    let bw = Int(box.width * w)
    let bh = Int(box.height * h)
    results.append([
        "text": top.string,
        "x": x, "y": y, "w": bw, "h": bh,
        "cx": x + bw/2, "cy": y + bh/2,
        "conf": top.confidence
    ])
}
let data = try JSONSerialization.data(withJSONObject: results)
print(String(data: data, encoding: .utf8)!)
'''
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False) as f:
        f.write(swift_code)
        swift_file = f.name

    r = subprocess.run(
        ["swift", swift_file, img_path],
        capture_output=True, text=True,
        env={**os.environ, "LANG": "en_US.UTF-8"}
    )
    os.unlink(swift_file)

    elements = []
    try:
        raw = json.loads(r.stdout.strip())

        scale = 1
        if return_logical and raw:
            try:
                import cv2
                img = cv2.imread(img_path)
                if img is not None:
                    pixel_w = img.shape[1]
                    if pixel_w > 2000:
                        scale = 2
                        try:
                            sr = subprocess.run(["osascript", "-e",
                                'tell application "Finder" to get bounds of window of desktop'],
                                capture_output=True, text=True, timeout=3)
                            if sr.stdout.strip():
                                logical_w = int(sr.stdout.strip().split(", ")[2])
                                scale = round(pixel_w / logical_w)
                        except:
                            pass
            except:
                pass

        for item in raw:
            elements.append({
                "type": "text",
                "source": "vision_ocr",
                "x": item["x"] // scale, "y": item["y"] // scale,
                "w": item["w"] // scale, "h": item["h"] // scale,
                "cx": item["cx"] // scale, "cy": item["cy"] // scale,
                "confidence": round(item.get("conf", 0), 3),
                "label": item["text"],
            })
    except:
        pass

    return elements
