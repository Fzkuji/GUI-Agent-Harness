#!/usr/bin/env python3
"""
UI Element Detector — unified detection using:
1. Salesforce/GPA-GUI-Detector — icons, buttons, UI elements
2. Apple Vision OCR — text elements
3. Accessibility API — Dock, menubar, status bar

Usage:
    python ui_detector.py                    # detect current front window
    python ui_detector.py --app WeChat       # detect specific app window
    python ui_detector.py --fullscreen       # detect full screen
    python ui_detector.py --save             # save annotated image + elements JSON
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
GPA_MODEL = os.path.expanduser("~/GPA-GUI-Detector/model.pt")
SCREEN_W = 1512
SCREEN_H = 982

# ═══════════════════════════════════════════
# Coordinate system — dual-space + mapping
# ═══════════════════════════════════════════
# Two coordinate spaces:
#   - Detection space (screencapture pixels): GPA, OCR, template match, cv2 crop
#   - Click space (OS logical pixels): pynput click_at, pyautogui, osascript bounds
#
# detect_all() is the single exit point — it returns click-space coords.
# Functions that crop/annotate images must convert back with click_to_detect().
#
# Scale is computed dynamically each time detect_all runs (not hardcoded).

_screen_info = {
    "detect_w": None, "detect_h": None,  # screenshot pixel dimensions
    "click_w": None, "click_h": None,    # OS logical dimensions
    "scale_x": 1.0, "scale_y": 1.0,     # detect / click
}


def refresh_screen_info(img_w=None, img_h=None):
    """Update screen info. Called by detect_all() each time.

    img_w/img_h: current screenshot pixel dimensions (from detect_icons).
    Click-space dimensions are obtained from the OS:
      - Mac: NSScreen.main.frame.width/height (logical)
      - Linux: xdpyinfo dimensions
      - Fallback: assume 1:1 (scale = 1.0)
    """
    global _screen_info
    import platform as _plat

    if img_w and img_h:
        _screen_info["detect_w"] = img_w
        _screen_info["detect_h"] = img_h

    click_w, click_h = img_w, img_h  # fallback 1:1

    if _plat.system() == "Darwin":
        try:
            r = subprocess.run(
                ["swift", "-e",
                 'import AppKit; let s=NSScreen.main!; '
                 'print("\\(Int(s.frame.width)) \\(Int(s.frame.height))")'],
                capture_output=True, text=True, timeout=10
            )
            parts = r.stdout.strip().split()
            if len(parts) == 2:
                click_w, click_h = int(parts[0]), int(parts[1])
        except Exception:
            pass  # keep fallback
    elif _plat.system() == "Linux":
        try:
            r = subprocess.run(["xdpyinfo"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n'):
                if 'dimensions:' in line:
                    dims = line.split(':')[1].strip().split()[0]
                    click_w, click_h = map(int, dims.split('x'))
                    break
        except Exception:
            pass  # keep fallback

    _screen_info["click_w"] = click_w
    _screen_info["click_h"] = click_h

    if img_w and click_w and click_w > 0:
        _screen_info["scale_x"] = img_w / click_w
    else:
        _screen_info["scale_x"] = 1.0

    if img_h and click_h and click_h > 0:
        _screen_info["scale_y"] = img_h / click_h
    else:
        _screen_info["scale_y"] = 1.0


def detect_to_click(x, y):
    """Detection-space coordinates → click-space coordinates."""
    return int(x / _screen_info["scale_x"]), int(y / _screen_info["scale_y"])


def click_to_detect(x, y):
    """Click-space coordinates → detection-space coordinates (for image cropping)."""
    return int(x * _screen_info["scale_x"]), int(y * _screen_info["scale_y"])


def get_screen_info():
    """Return a copy of the current screen info dict."""
    return dict(_screen_info)


# Legacy alias — DEPRECATED. Use detect_to_click / click_to_detect instead.
def get_backing_scale():
    """DEPRECATED: use detect_to_click() / click_to_detect() instead.

    Returns the scale factor (detection / click). Kept for backwards compat.
    """
    if _screen_info["scale_x"] != 1.0:
        return _screen_info["scale_x"]
    # If refresh_screen_info hasn't been called yet, probe the OS once.
    import platform as _plat
    if _plat.system() == "Darwin":
        try:
            r = subprocess.run(
                ["swift", "-e", 'import AppKit; print(NSScreen.main!.backingScaleFactor)'],
                capture_output=True, text=True, timeout=10
            )
            return float(r.stdout.strip())
        except Exception:
            return 2.0
    return 1.0


# ═══════════════════════════════════════════
# Screenshot utilities
# ═══════════════════════════════════════════

def get_front_app():
    """Get frontmost app name."""
    r = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to return name of first process whose frontmost is true'],
        capture_output=True, text=True, timeout=5
    )
    return r.stdout.strip()


def get_window_info(app_name=None):
    """Get window ID, position, size using CGWindowList."""
    swift_code = '''
import CoreGraphics
let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
if let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] {
    for w in windowList {
        let name = w["kCGWindowOwnerName"] as? String ?? ""
        let layer = w["kCGWindowLayer"] as? Int ?? -1
        let bounds = w["kCGWindowBounds"] as? [String: Any] ?? [:]
        let wid = w["kCGWindowNumber"] as? Int ?? 0
        let bw = bounds["Width"] as? Int ?? 0
        let bh = bounds["Height"] as? Int ?? 0
        let bx = bounds["X"] as? Int ?? 0
        let by = bounds["Y"] as? Int ?? 0
        if layer == 0 && bw > 100 && bh > 100 {
            print("\\(name)|\\(wid)|\\(bx)|\\(by)|\\(bw)|\\(bh)")
        }
    }
}
'''
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False) as f:
        f.write(swift_code)
        swift_file = f.name
    r = subprocess.run(["swift", swift_file], capture_output=True, text=True)
    os.unlink(swift_file)

    windows = []
    for line in r.stdout.strip().split("\n"):
        if "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) == 6:
            windows.append({
                "app": parts[0], "id": int(parts[1]),
                "x": int(parts[2]), "y": int(parts[3]),
                "w": int(parts[4]), "h": int(parts[5])
            })

    if app_name:
        # Find all windows for this app, return the largest one
        app_windows = [w for w in windows if w["app"].lower() == app_name.lower()]
        if app_windows:
            return max(app_windows, key=lambda w: w["w"] * w["h"])
    return windows[0] if windows else None


def take_window_screenshot(window_id, out_path="/tmp/ui_detect_window.png"):
    """Capture a specific window by ID."""
    subprocess.run(["/usr/sbin/screencapture", "-x", "-l", str(window_id), out_path],
                   check=True, timeout=5)
    return out_path


def take_fullscreen(out_path="/tmp/ui_detect_full.png"):
    """Capture full screen."""
    subprocess.run(["/usr/sbin/screencapture", "-x", out_path], check=True, timeout=5)
    return out_path


# ═══════════════════════════════════════════
# Salesforce/GPA-GUI-Detector
# ═══════════════════════════════════════════

_gpa_model = None

def load_gpa_detector():
    global _gpa_model
    if _gpa_model is None:
        from ultralytics import YOLO
        _gpa_model = YOLO(GPA_MODEL)
    return _gpa_model


def detect_icons(img_path, conf=0.1, iou=0.3):
    """Detect UI elements using Salesforce/GPA-GUI-Detector."""
    model = load_gpa_detector()
    results = model.predict(img_path, conf=conf, iou=iou, verbose=False)
    r = results[0]

    # Get image dimensions for coordinate conversion
    img_h, img_w = r.orig_shape

    elements = []
    for box in r.boxes:
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        confidence = float(box.conf[0])
        elements.append({
            "type": "icon",
            "source": "gpa_detector",
            "x": x1, "y": y1,
            "w": x2 - x1, "h": y2 - y1,
            "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
            "confidence": round(confidence, 3),
            "label": None,  # To be filled by LLM or template match
        })

    return elements, img_w, img_h


# ═══════════════════════════════════════════
# Apple Vision OCR
# ═══════════════════════════════════════════

def detect_text(img_path, return_logical=False):
    """Detect text using Apple Vision framework.

    Returns coordinates in screenshot pixel space (same as GPA detect_icons).
    Coordinate conversion to logical (pynput) space happens in detect_all().

    Args:
        img_path: path to screenshot image
        return_logical: DEPRECATED. Kept for backwards compatibility.
                       Previously auto-converted retina coords to logical coords.
                       Now defaults to False — callers should use detect_all() instead.
    """
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

        # Auto-detect scale: if image is retina, coords need to be divided
        scale = 1
        if return_logical and raw:
            try:
                import cv2
                img = cv2.imread(img_path)
                if img is not None:
                    pixel_w = img.shape[1]
                    # Screen logical width (most common macOS resolutions)
                    # If pixel width > 2000, it's likely retina
                    if pixel_w > 2000:
                        scale = 2  # Retina 2x
                        # Try to get exact logical width
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


# ═══════════════════════════════════════════
# Accessibility API
# ═══════════════════════════════════════════

def detect_ax_dock():
    """Get Dock items via AX API."""
    r = subprocess.run(['osascript', '-l', 'JavaScript', '-e', '''
var se = Application("System Events");
var list1 = se.processes["Dock"].uiElements[0];
var items = list1.uiElements();
var r = [];
for (var i = 0; i < items.length; i++) {
    try {
        var n = items[i].title() || items[i].name() || "?";
        var p = items[i].position();
        var s = items[i].size();
        r.push(JSON.stringify({name: n, x: Math.round(p[0]), y: Math.round(p[1]),
               w: Math.round(s[0]), h: Math.round(s[1])}));
    } catch(e) {}
}
"[" + r.join(",") + "]";
'''], capture_output=True, text=True, timeout=5)

    elements = []
    try:
        items = json.loads(r.stdout.strip())
        for item in items:
            elements.append({
                "type": "dock_icon",
                "source": "ax_api",
                "x": item["x"], "y": item["y"],
                "w": item["w"], "h": item["h"],
                "cx": item["x"] + item["w"] // 2,
                "cy": item["y"] + item["h"] // 2,
                "confidence": 1.0,
                "label": item["name"],
            })
    except:
        pass
    return elements


def detect_ax_menubar():
    """Get menu bar items via AX API."""
    r = subprocess.run(['osascript', '-l', 'JavaScript', '-e', '''
var se = Application("System Events");
var front = se.processes.whose({frontmost: true})[0];
var bar = front.menuBars[0];
var items = bar.menuBarItems();
var r = [];
for (var i = 0; i < items.length; i++) {
    try {
        var n = items[i].title() || items[i].name() || "?";
        var p = items[i].position();
        var s = items[i].size();
        r.push(JSON.stringify({name: n, x: Math.round(p[0]), y: Math.round(p[1]),
               w: Math.round(s[0]), h: Math.round(s[1])}));
    } catch(e) {}
}
"[" + r.join(",") + "]";
'''], capture_output=True, text=True, timeout=5)

    elements = []
    try:
        items = json.loads(r.stdout.strip())
        for item in items:
            elements.append({
                "type": "menu_item",
                "source": "ax_api",
                "x": item["x"], "y": item["y"],
                "w": item["w"], "h": item["h"],
                "cx": item["x"] + item["w"] // 2,
                "cy": item["y"] + item["h"] // 2,
                "confidence": 1.0,
                "label": item["name"],
            })
    except:
        pass
    return elements


# ═══════════════════════════════════════════
# Merge & Dedup
# ═══════════════════════════════════════════

def compute_iou(a, b):
    """Compute IoU between two boxes {x, y, w, h}."""
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0


def detect_all(img_path, conf=0.1, iou=0.3):
    """Unified detection on an image file: GPA (required) + OCR (optional).

    Platform-independent: works on any screenshot (local, remote VM, downloaded).
    GPA-GUI-Detector is the required baseline — always runs.
    OCR is optional enhancement — gracefully degrades if unavailable.

    Returns: (icons, texts, merged, img_w, img_h)
        - icons: GPA-GUI-Detector results (always populated)
        - texts: OCR results (empty list if OCR unavailable)
        - merged: deduplicated combination of both
        - img_w, img_h: image dimensions
    """
    # GPA-GUI-Detector: REQUIRED — if this fails, we have nothing
    icons, img_w, img_h = detect_icons(img_path, conf=conf, iou=iou)  # screenshot pixels

    # OCR: OPTIONAL — graceful degradation if unavailable
    texts = []
    try:
        texts = detect_text(img_path, return_logical=False)  # screenshot pixels
    except Exception as ex:
        # OCR may not be available on non-Mac platforms — that's OK
        pass

    merged = merge_elements(icons, texts)  # detection space

    # ── Unified coordinate conversion: detection space → click space ──
    # merged contains all elements (icons/texts are views into merged objects),
    # so converting merged converts them all exactly once.
    refresh_screen_info(img_w, img_h)
    info = get_screen_info()
    if info["scale_x"] != 1.0 or info["scale_y"] != 1.0:
        coord_keys = ("cx", "cy", "x", "y", "w", "h")
        converted = set()
        for el in merged:
            eid = id(el)
            if eid in converted:
                continue
            converted.add(eid)
            for k in coord_keys:
                if k in el:
                    el[k] = int(el[k] / info["scale_x"])  # scale_x ≈ scale_y typically

    # Auto-tick tracker (best-effort, never fail)
    try:
        import sys as _sys
        _report_dir = str(Path(__file__).parent.parent / "skills" / "gui-report" / "scripts")
        if _report_dir not in _sys.path:
            _sys.path.insert(0, _report_dir)
        from tracker import tick_counter, STATE_FILE, LAST_REPORT_FILE
        if not STATE_FILE.exists():
            # Show last report summary if available
            if LAST_REPORT_FILE.exists():
                try:
                    print(LAST_REPORT_FILE.read_text().strip())
                    LAST_REPORT_FILE.unlink()
                except Exception:
                    pass
            from tracker import start as _start
            class _Args:
                task = "auto"
                session = None
            _start(_Args())
        tick_counter("detector_calls")
        if texts:
            tick_counter("ocr_calls")
    except Exception:
        pass

    return icons, texts, merged, img_w, img_h


def merge_elements(icon_elements, text_elements, ax_elements=None, iou_threshold=0.3):
    """Merge elements from different sources, dedup by IoU.

    Priority: AX (has name) > text (has label) > icon (no label).
    When IoU > threshold, keep the one with a label; if icon overlaps text,
    assign the text label to the icon.
    """
    all_elements = []

    # Start with AX elements (highest priority, always have labels)
    if ax_elements:
        all_elements.extend(ax_elements)

    # Add text elements, skip if overlaps with existing
    for txt in text_elements:
        overlap = False
        for existing in all_elements:
            if compute_iou(txt, existing) > iou_threshold:
                overlap = True
                break
        if not overlap:
            all_elements.append(txt)

    # Add icon elements, merge labels from overlapping text
    for icon in icon_elements:
        overlap_idx = -1
        best_iou = 0
        for i, existing in enumerate(all_elements):
            iou = compute_iou(icon, existing)
            if iou > best_iou:
                best_iou = iou
                if iou > iou_threshold:
                    overlap_idx = i

        if overlap_idx >= 0:
            # Icon overlaps with existing element
            existing = all_elements[overlap_idx]
            if existing.get("label") and not icon.get("label"):
                # Assign text/AX label to icon, keep icon's better bbox
                icon["label"] = existing["label"]
                icon["label_source"] = existing["source"]
            # Keep whichever has higher confidence or a label
            if icon.get("label") and not existing.get("label"):
                all_elements[overlap_idx] = icon
            # If both have labels, keep existing (AX/text priority)
        else:
            all_elements.append(icon)

    # Sort by position (top-to-bottom, left-to-right)
    all_elements.sort(key=lambda e: (e["y"], e["x"]))

    # Assign sequential IDs
    for i, el in enumerate(all_elements):
        el["id"] = i

    return all_elements


# ═══════════════════════════════════════════
# Annotation
# ═══════════════════════════════════════════

def annotate_image(img_path, elements, out_path=None, retina_scale=2):
    """Draw bounding boxes and labels on image.

    Elements may be in click-space coordinates if they came from detect_all().
    The function auto-scales them back to detection space for drawing using
    click_to_detect(). The retina_scale parameter is DEPRECATED.
    """
    import cv2

    img = cv2.imread(img_path)
    if img is None:
        return None

    # Auto-detect if coordinates need scaling up for annotation.
    # If elements are in click-space (from detect_all), scale them up.
    # Heuristic: if image width > 1.5x the max element x+w, coords are click-space.
    info = get_screen_info()
    needs_upscale = False
    if info["scale_x"] != 1.0 and elements:
        max_right = max((el.get("x", 0) + el.get("w", 0)) for el in elements) if elements else 0
        if max_right > 0 and img.shape[1] / max_right > 1.5:
            needs_upscale = True

    colors = {
        "icon": (0, 255, 0),       # green
        "text": (0, 255, 255),      # yellow
        "dock_icon": (255, 200, 0), # cyan
        "menu_item": (255, 165, 0), # orange
    }

    for el in elements:
        if needs_upscale:
            x = int(el["x"] * info["scale_x"])
            y = int(el["y"] * info["scale_y"])
            w = int(el["w"] * info["scale_x"])
            h = int(el["h"] * info["scale_y"])
        else:
            x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        color = colors.get(el["type"], (255, 255, 255))
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)

        # Label
        label = f"{el.get('id', '')}"
        if el.get("label"):
            label += f":{el['label'][:15]}"
        cv2.putText(img, label, (x, max(y - 3, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

    if out_path is None:
        out_path = img_path.replace(".png", "_annotated.jpg")
    cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return out_path


# ═══════════════════════════════════════════
# Main detection pipeline
# ═══════════════════════════════════════════

def detect_all_mac(app_name=None, fullscreen=False, include_ax=False,
                   gpa_conf=0.1, gpa_iou=0.3, merge_iou=0.3):
    """Run full detection pipeline on Mac (screenshot + detect).

    Mac-specific: uses screencapture, osascript, AX API.
    For platform-independent detection on an existing image, use detect_all().

    Returns: (elements, img_path, annotated_path)
    """
    t0 = time.time()

    # 1. Screenshot
    if fullscreen:
        img_path = take_fullscreen()
        print(f"  📸 Full screen screenshot")
    else:
        if app_name:
            subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'],
                           capture_output=True, timeout=5)
            time.sleep(0.5)
        win = get_window_info(app_name or get_front_app())
        if win:
            img_path = take_window_screenshot(win["id"])
            print(f"  📸 Window: {win['app']} ({win['w']}x{win['h']})")
        else:
            img_path = take_fullscreen()
            print(f"  📸 Fallback to fullscreen")

    # 2. GPA-GUI-Detector
    t1 = time.time()
    icon_elements, img_w, img_h = detect_icons(img_path, conf=gpa_conf, iou=gpa_iou)
    print(f"  🔍 GPA-GUI-Detector: {len(icon_elements)} icons ({time.time()-t1:.1f}s)")

    # 3. Apple Vision OCR
    t2 = time.time()
    text_elements = detect_text(img_path)
    print(f"  📝 OCR: {len(text_elements)} text elements ({time.time()-t2:.1f}s)")

    # 4. AX API (optional)
    ax_elements = []
    if include_ax and fullscreen:
        t3 = time.time()
        ax_elements.extend(detect_ax_dock())
        ax_elements.extend(detect_ax_menubar())
        print(f"  ♿ AX: {len(ax_elements)} elements ({time.time()-t3:.1f}s)")

    # 5. Merge & dedup (still in screenshot pixels)
    all_elements = merge_elements(icon_elements, text_elements, ax_elements,
                                   iou_threshold=merge_iou)
    print(f"  🔗 Merged: {len(all_elements)} total ({time.time()-t0:.1f}s)")

    # 6. Annotate (must use detection-space coords — annotation draws on raw image)
    annotated_path = annotate_image(img_path, all_elements)

    # 7. Convert all coordinates to click space
    refresh_screen_info(img_w, img_h)
    info = get_screen_info()
    if info["scale_x"] != 1.0 or info["scale_y"] != 1.0:
        coord_keys = ("cx", "cy", "x", "y", "w", "h")
        for el in all_elements:
            for k in coord_keys:
                if k in el:
                    el[k] = int(el[k] / info["scale_x"])

    return all_elements, img_path, annotated_path


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="UI Element Detector")
    parser.add_argument("--app", help="App name to detect")
    parser.add_argument("--fullscreen", action="store_true", help="Full screen detection")
    parser.add_argument("--save", action="store_true", help="Save results to file")
    parser.add_argument("--conf", type=float, default=0.1, help="GPA-GUI-Detector confidence threshold")
    parser.add_argument("--iou", type=float, default=0.3, help="GPA-GUI-Detector NMS IoU threshold")
    parser.add_argument("--merge-iou", type=float, default=0.3, help="Merge IoU threshold")
    parser.add_argument("--no-ax", action="store_true", help="Skip AX API")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    elements, img_path, annotated_path = detect_all_mac(
        app_name=args.app,
        fullscreen=args.fullscreen,
        include_ax=not args.no_ax,
        gpa_conf=args.conf,
        gpa_iou=args.iou,
        merge_iou=args.merge_iou,
    )

    if args.json:
        print(json.dumps(elements, ensure_ascii=False, indent=2))
    else:
        # Summary
        by_type = {}
        for el in elements:
            t = el["type"]
            by_type[t] = by_type.get(t, 0) + 1
        print(f"\n  Summary: {dict(by_type)}")

        labeled = sum(1 for el in elements if el.get("label"))
        print(f"  Labeled: {labeled}/{len(elements)}")

        if annotated_path:
            print(f"  Annotated: {annotated_path}")

    if args.save:
        # Save to per-app pages directory instead of global detected/
        app_slug = args.app.lower().replace(" ", "_") if args.app else "unknown"
        out_dir = SKILL_DIR / "memory" / "apps" / app_slug / "pages"
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "elements.json", "w") as f:
            json.dump(elements, f, ensure_ascii=False, indent=2)
        if annotated_path:
            import shutil
            shutil.copy(annotated_path, out_dir / "annotated.jpg")
        print(f"  Saved to {out_dir}")


if __name__ == "__main__":
    main()
