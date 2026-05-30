#!/usr/bin/env python3
"""
gui_harness.perception.screenshot — screenshot capture utilities.

Provides: screenshot, screenshot_region, capture_window
Moved from scripts/platform_input.py (screenshot-related functions).
"""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
import time

SYSTEM = platform.system()


def _shot_path(name: str = "gui_agent_screen.png") -> str:
    """Cross-platform scratch path for a screenshot (platform temp dir)."""
    return os.path.join(tempfile.gettempdir(), name)


def screenshot(path: str | None = None) -> str:
    """Take a full-screen screenshot and return the path. Cross-platform.

    - macOS: ``screencapture`` (fast, native, captures the main display).
    - Windows / Linux: Pillow ``ImageGrab`` (Pillow is a declared dep; on
      Windows it is fully native, on Linux it uses the X11 grabber).
    - Linux fallback: ``scrot`` / ``gnome-screenshot`` / ImageMagick
      ``import`` if Pillow's grabber is unavailable (e.g. Wayland).

    Coordinate note: macOS Retina screenshots are 2x logical points; on
    Windows/Linux the captured image is in physical pixels (== logical
    unless the desktop is HiDPI-scaled). Callers mapping click coords to
    screenshot pixels should account for the per-platform scale factor.
    """
    path = path or _shot_path()
    if SYSTEM == "Darwin":
        subprocess.run(["/usr/sbin/screencapture", "-x", path],
                       capture_output=True, timeout=5)
        return path

    # Windows + Linux: Pillow ImageGrab (no extra dependency).
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(path)
        if os.path.exists(path):
            return path
    except Exception:
        if SYSTEM != "Linux":
            raise  # Windows has no further fallback

    # Linux fallback when ImageGrab is unavailable (Wayland / headless X).
    if SYSTEM == "Linux":
        for cmd in (["scrot", "-o", path],
                    ["gnome-screenshot", "-f", path],
                    ["import", "-window", "root", path]):
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=10)
                if r.returncode == 0 and os.path.exists(path):
                    return path
            except FileNotFoundError:
                continue
        raise RuntimeError(
            "No screenshot backend on Linux: install Pillow with X11 support "
            "or one of scrot / gnome-screenshot / imagemagick (import).")
    return path


def capture_window(app_name: str, out_path: str = None):
    """Capture a screenshot of the app's window.

    Returns: (image_path, x, y, w, h) or None on failure.
    """
    out_path = out_path or _shot_path(
        f"gui_agent_{app_name.lower().replace(' ', '_')}.png")

    if SYSTEM == "Darwin":
        from gui_harness.perception.detector import (
            get_window_info, take_window_screenshot)

        info = get_window_info(app_name)
        if not info:
            return None
        take_window_screenshot(info["id"], out_path)
        return out_path, info["x"], info["y"], info["w"], info["h"]

    # Windows / Linux: resolve window bounds, grab full screen, crop.
    from gui_harness.action.window import get_window_bounds
    bounds = get_window_bounds(app_name)
    if not bounds:
        return None
    x, y, w, h = bounds
    full = screenshot(_shot_path("_capwin_full.png"))
    try:
        from PIL import Image
        Image.open(full).crop((x, y, x + w, y + h)).save(out_path)
        return out_path, x, y, w, h
    except Exception:
        return None


def screenshot_region(out_path, method="auto", x1=None, y1=None, x2=None, y2=None,
                      anchor_start=None, anchor_end=None, padding=10,
                      bg_color=None, content_threshold=245):
    """Take a screenshot of a specific region.

    Two strategies (per GUI Agent Skills design):

    Strategy 1 — Anchor-based (when text/components can define boundaries):
    - "anchors": Use OCR text as reference points to define crop boundaries.
                 anchor_start/anchor_end are text strings to search for.
                 Crops from above anchor_start to below anchor_end.
    - "crop": Explicit logical coordinates (x1,y1,x2,y2).
    - "drag": Cmd+Shift+4 interactive drag.

    Strategy 2 — Feature-based (when no anchors, detect content boundaries):
    - "auto_crop": Detect largest uniform region (white/colored) via connected
                   components. Works for slides, documents, dialogs.
    - "edge_detect": Use edge detection to find content boundaries.
                     Works for images, mixed-content areas.

    "auto" mode: tries anchors if provided, falls back to auto_crop.

    Args:
        out_path: Output image path
        method: "auto", "anchors", "crop", "drag", "auto_crop", "edge_detect"
        x1,y1,x2,y2: Logical screen coordinates (for "crop" and "drag")
        anchor_start: Text string marking top/left of region (for "anchors")
        anchor_end: Text string marking bottom/right of region (for "anchors")
        padding: Pixels of padding around anchors (logical coords, default 10)
        bg_color: Background color tuple (R,G,B) for auto_crop. None = auto-detect.
        content_threshold: Brightness threshold for white region detection (default 245)

    Returns: path to saved image, or None on failure.
    """
    from gui_harness.action.input import mouse_drag, key_combo

    # Auto mode: use anchors if provided, otherwise auto_crop
    if method == "auto":
        if anchor_start or anchor_end:
            method = "anchors"
        else:
            method = "auto_crop"

    if method == "drag":
        key_combo("command", "shift", "4")
        time.sleep(1)
        mouse_drag(x1, y1, x2, y2, duration=0.8)
        time.sleep(1.5)
        import glob
        files = sorted(glob.glob(os.path.expanduser("~/Desktop/Screenshot*.png")),
                       key=os.path.getmtime, reverse=True)
        if files:
            import shutil
            shutil.move(files[0], out_path)
            return out_path
        return None

    elif method == "crop":
        full = screenshot(_shot_path("_region_full.png"))
        from PIL import Image
        img = Image.open(full)
        # Logical → Retina (2x)
        crop = img.crop((x1 * 2, y1 * 2, x2 * 2, y2 * 2))
        crop.save(out_path)
        return out_path

    elif method == "anchors":
        return _screenshot_by_anchors(out_path, anchor_start, anchor_end, padding)

    elif method == "auto_crop":
        return _screenshot_auto_crop(out_path, content_threshold)

    elif method == "edge_detect":
        return _screenshot_edge_detect(out_path)

    else:
        raise ValueError(f"Unknown method: {method}")


def _screenshot_by_anchors(out_path, anchor_start, anchor_end, padding=10):
    """Strategy 1: OCR-based anchor positioning."""
    full = screenshot(_shot_path("_anchor_full.png"))
    from PIL import Image
    img = Image.open(full)

    # Run OCR
    try:
        from gui_harness.memory.spreadsheet import _run_vision_ocr
        ocr_results = _run_vision_ocr(full)
    except ImportError:
        print("OCR not available")
        return None

    if not ocr_results:
        print("OCR returned no results")
        return None

    # Find anchor positions (Retina coordinates from OCR)
    start_pos = None
    end_pos = None

    for text, x, y, w, h in ocr_results:
        clean = text.strip()
        if anchor_start and anchor_start.lower() in clean.lower():
            if start_pos is None or y < start_pos[1]:
                start_pos = (x, y, w, h)
        if anchor_end and anchor_end.lower() in clean.lower():
            if end_pos is None or (y + h) > (end_pos[1] + end_pos[3]):
                end_pos = (x, y, w, h)

    if not start_pos and not end_pos:
        print(f"Could not find anchors: start='{anchor_start}', end='{anchor_end}'")
        return None

    # Calculate crop bounds (Retina coordinates)
    pad = padding * 2

    if start_pos and end_pos:
        crop_x1 = min(start_pos[0], end_pos[0]) - pad
        crop_y1 = start_pos[1] - pad
        crop_x2 = max(start_pos[0] + start_pos[2], end_pos[0] + end_pos[2]) + pad
        crop_y2 = end_pos[1] + end_pos[3] + pad
    elif start_pos:
        crop_x1 = start_pos[0] - pad
        crop_y1 = start_pos[1] - pad
        crop_x2 = img.width
        crop_y2 = min(start_pos[1] + 800, img.height)
    elif end_pos:
        crop_x1 = 0
        crop_y1 = max(0, end_pos[1] - 800)
        crop_x2 = end_pos[0] + end_pos[2] + pad
        crop_y2 = end_pos[1] + end_pos[3] + pad

    # Clamp to image bounds
    crop_x1 = max(0, int(crop_x1))
    crop_y1 = max(0, int(crop_y1))
    crop_x2 = min(img.width, int(crop_x2))
    crop_y2 = min(img.height, int(crop_y2))

    crop = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
    crop.save(out_path)
    print(f"Anchored crop: ({crop_x1 // 2},{crop_y1 // 2})->({crop_x2 // 2},{crop_y2 // 2}) logical")
    return out_path


def _screenshot_auto_crop(out_path, content_threshold=245):
    """Strategy 2a: Connected components white/content region detection."""
    full = screenshot(_shot_path("_auto_full.png"))
    from PIL import Image
    import numpy as np
    import cv2

    img = Image.open(full)
    arr = np.array(img)[:, :, :3]
    gray_img = np.mean(arr, axis=2)

    binary = (gray_img > content_threshold).astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)

    max_area = 0
    best = None
    for i in range(1, num_labels):
        area = stats[i, 4]
        w, h = stats[i, 2], stats[i, 3]
        if area > max_area and w > 200 and h > 200:
            max_area = area
            best = (stats[i, 0], stats[i, 1], stats[i, 2], stats[i, 3])

    if best:
        x, y, w, h = best
        margin = 3
        crop = img.crop((x + margin, y + margin, x + w - margin, y + h - margin))
        crop.save(out_path)
        return out_path

    return None


def _screenshot_edge_detect(out_path):
    """Strategy 2b: Edge-based content boundary detection."""
    full = screenshot(_shot_path("_edge_full.png"))
    from PIL import Image
    import numpy as np
    import cv2

    img = Image.open(full)
    arr = np.array(img)[:, :, :3]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    edges = cv2.Canny(gray, 50, 150)
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=3)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    best_rect = None
    best_area = 0
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area > best_area and w > 200 and h > 200:
            best_area = area
            best_rect = (x, y, w, h)

    if best_rect:
        x, y, w, h = best_rect
        margin = 5
        crop = img.crop((x + margin, y + margin, x + w - margin, y + h - margin))
        crop.save(out_path)
        return out_path

    return None


# Legacy alias for backward compat
take = screenshot
take_window = capture_window
