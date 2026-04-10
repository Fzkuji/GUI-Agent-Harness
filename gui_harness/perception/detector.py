#!/usr/bin/env python3
"""
gui_harness.perception.detector — GPA-GUI-Detector (YOLO), window info, merge/dedup.

Moved from scripts/ui_detector.py (detection + merge + coordinate utilities).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

GPA_MODEL = os.path.expanduser("~/GPA-GUI-Detector/model.pt")
SCREEN_W = 1512   # Default click-space dimensions (Mac logical)
SCREEN_H = 982    # Default click-space dimensions (Mac logical)


# ═══════════════════════════════════════════
# Coordinate system — ImageContext
# ═══════════════════════════════════════════

class ImageContext:
    """Maps between image pixel coordinates and screen click coordinates.

    pixel_scale: ratio of image pixels to click-space units.
        - Mac Retina screencapture: 2.0 (backingScaleFactor)
        - Mac non-Retina / VM / remote: 1.0
    origin_x, origin_y: image top-left in screen click-space.
        - Fullscreen: (0, 0)
        - Window crop: (window_x, window_y) in click-space
    """

    def __init__(self, pixel_scale=1.0, origin_x=0, origin_y=0):
        self.pixel_scale = pixel_scale
        self.origin_x = origin_x
        self.origin_y = origin_y

    def image_to_click(self, ix, iy):
        """Image pixel coords → screen click coords."""
        return (
            int(ix / self.pixel_scale) + self.origin_x,
            int(iy / self.pixel_scale) + self.origin_y,
        )

    def click_to_image(self, cx, cy):
        """Screen click coords → image pixel coords (for cropping)."""
        return (
            int((cx - self.origin_x) * self.pixel_scale),
            int((cy - self.origin_y) * self.pixel_scale),
        )

    def image_size_to_click(self, pw, ph):
        """Image pixel dimensions → click-space dimensions."""
        return int(pw / self.pixel_scale), int(ph / self.pixel_scale)

    def click_size_to_image(self, cw, ch):
        """Click-space dimensions → image pixel dimensions."""
        return int(cw * self.pixel_scale), int(ch * self.pixel_scale)

    @classmethod
    def mac_fullscreen(cls):
        """Mac full-screen screenshot (screencapture without -l)."""
        return cls(pixel_scale=_get_backing_scale_factor(), origin_x=0, origin_y=0)

    @classmethod
    def mac_window(cls, win_x=0, win_y=0):
        """Mac window screenshot. win_x/win_y = window position in click-space."""
        return cls(pixel_scale=_get_backing_scale_factor(),
                   origin_x=win_x, origin_y=win_y)

    @classmethod
    def remote(cls):
        """Remote VM or downloaded image. 1:1, no offset."""
        return cls(pixel_scale=1.0, origin_x=0, origin_y=0)

    def __repr__(self):
        return (f"ImageContext(pixel_scale={self.pixel_scale}, "
                f"origin=({self.origin_x}, {self.origin_y}))")


def _get_backing_scale_factor():
    """Get Mac display backing scale factor (2.0 for Retina, 1.0 otherwise)."""
    import platform as _plat
    if _plat.system() != "Darwin":
        return 1.0
    try:
        r = subprocess.run(
            ["swift", "-e", 'import AppKit; print(NSScreen.main!.backingScaleFactor)'],
            capture_output=True, text=True, timeout=10
        )
        return float(r.stdout.strip())
    except Exception:
        return 2.0


# ── Legacy compat shims ── (DEPRECATED, kept for backwards compat)

_screen_info = {
    "detect_w": None, "detect_h": None,
    "click_w": None, "click_h": None,
    "scale_x": 1.0, "scale_y": 1.0,
}


def refresh_screen_info(img_w=None, img_h=None):
    """DEPRECATED — legacy compat. Sets scale from backingScaleFactor."""
    global _screen_info
    scale = _get_backing_scale_factor()
    _screen_info["detect_w"] = img_w
    _screen_info["detect_h"] = img_h
    _screen_info["click_w"] = int(img_w / scale) if img_w else None
    _screen_info["click_h"] = int(img_h / scale) if img_h else None
    _screen_info["scale_x"] = scale
    _screen_info["scale_y"] = scale


def detect_to_click(x, y):
    """DEPRECATED — use ImageContext.image_to_click()."""
    s = _screen_info["scale_x"] if _screen_info["scale_x"] != 1.0 else _get_backing_scale_factor()
    return int(x / s), int(y / s)


def click_to_detect(x, y):
    """DEPRECATED — use ImageContext.click_to_image()."""
    s = _screen_info["scale_x"] if _screen_info["scale_x"] != 1.0 else _get_backing_scale_factor()
    return int(x * s), int(y * s)


def get_screen_info():
    """DEPRECATED — Return a copy of the current screen info dict."""
    return dict(_screen_info)


def get_backing_scale():
    """DEPRECATED: use detect_to_click() / click_to_detect() instead."""
    if _screen_info["scale_x"] != 1.0:
        return _screen_info["scale_x"]
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
# Window info / screenshot utilities
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


def detect_icons(img_path: str, conf: float = 0.1, iou: float = 0.3):
    """Detect UI elements using Salesforce/GPA-GUI-Detector."""
    model = load_gpa_detector()
    results = model.predict(img_path, conf=conf, iou=iou, verbose=False)
    r = results[0]

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
            "label": None,
        })

    img_h, img_w = r.orig_shape
    return elements, img_w, img_h


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


def detect_all(img_path: str, conf: float = 0.1, iou: float = 0.3):
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
    from gui_harness.perception.ocr import detect_text

    # GPA-GUI-Detector: REQUIRED
    icons, img_w, img_h = detect_icons(img_path, conf=conf, iou=iou)

    # OCR: OPTIONAL
    texts = []
    try:
        texts = detect_text(img_path, return_logical=False)
    except Exception:
        pass

    merged = merge_elements(icons, texts)

    return icons, texts, merged, img_w, img_h


def merge_elements(icon_elements, text_elements, ax_elements=None, iou_threshold=0.3):
    """Merge elements from different sources, dedup by IoU.

    Priority: AX (has name) > text (has label) > icon (no label).
    """
    all_elements = []

    if ax_elements:
        all_elements.extend(ax_elements)

    for txt in text_elements:
        overlap = False
        for existing in all_elements:
            if compute_iou(txt, existing) > iou_threshold:
                overlap = True
                break
        if not overlap:
            all_elements.append(txt)

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
            existing = all_elements[overlap_idx]
            if existing.get("label") and not icon.get("label"):
                icon["label"] = existing["label"]
                icon["label_source"] = existing["source"]
            if icon.get("label") and not existing.get("label"):
                all_elements[overlap_idx] = icon
        else:
            all_elements.append(icon)

    all_elements.sort(key=lambda e: (e["y"], e["x"]))

    for i, el in enumerate(all_elements):
        el["id"] = i

    return all_elements


# ═══════════════════════════════════════════
# Annotation
# ═══════════════════════════════════════════

def annotate_image(img_path, elements, out_path=None, retina_scale=2):
    """Draw bounding boxes and labels on image."""
    import cv2

    img = cv2.imread(img_path)
    if img is None:
        return None

    colors = {
        "icon": (0, 255, 0),
        "text": (0, 255, 255),
        "dock_icon": (255, 200, 0),
        "menu_item": (255, 165, 0),
    }

    for el in elements:
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        color = colors.get(el["type"], (255, 255, 255))
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        label = f"{el.get('id', '')}"
        if el.get("label"):
            label += f":{el['label'][:15]}"
        cv2.putText(img, label, (x, max(y - 3, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

    if out_path is None:
        out_path = img_path.replace(".png", "_annotated.jpg")
    cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return out_path


def annotate_numbered(img_path, icons, out_path=None):
    """Draw numbered bounding boxes on screenshot for batch LLM labeling.

    Each icon gets a colored box and a number label [0], [1], [2], etc.
    Returns path to annotated image.
    """
    import cv2

    img = cv2.imread(img_path)
    if img is None:
        return None

    color = (0, 200, 255)  # orange-yellow for visibility

    for i, icon in enumerate(icons):
        x, y, w, h = icon["x"], icon["y"], icon["w"], icon["h"]
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        # Number label with background for readability
        label = f"[{i}]"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        lx, ly = x, max(y - 4, th + 4)
        cv2.rectangle(img, (lx, ly - th - 4), (lx + tw + 4, ly + 2), (0, 0, 0), -1)
        cv2.putText(img, label, (lx + 2, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    if out_path is None:
        out_path = img_path.replace(".png", "_numbered.jpg")
    cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return out_path


# ═══════════════════════════════════════════
# Mac-specific full pipeline
# ═══════════════════════════════════════════

def detect_all_mac(app_name=None, fullscreen=False, include_ax=False,
                   gpa_conf=0.1, gpa_iou=0.3, merge_iou=0.3):
    """Run full detection pipeline on Mac (screenshot + detect).

    Mac-specific: uses screencapture, osascript, AX API.
    For platform-independent detection on an existing image, use detect_all().

    Returns: (elements, img_path, annotated_path)
    """
    from gui_harness.perception.ocr import detect_text

    t0 = time.time()

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

    t1 = time.time()
    icon_elements, img_w, img_h = detect_icons(img_path, conf=gpa_conf, iou=gpa_iou)
    print(f"  🔍 GPA-GUI-Detector: {len(icon_elements)} icons ({time.time() - t1:.1f}s)")

    t2 = time.time()
    text_elements = detect_text(img_path)
    print(f"  📝 OCR: {len(text_elements)} text elements ({time.time() - t2:.1f}s)")

    ax_elements = []
    if include_ax and fullscreen:
        t3 = time.time()
        ax_elements.extend(detect_ax_dock())
        ax_elements.extend(detect_ax_menubar())
        print(f"  ♿ AX: {len(ax_elements)} elements ({time.time() - t3:.1f}s)")

    all_elements = merge_elements(icon_elements, text_elements, ax_elements,
                                  iou_threshold=merge_iou)
    print(f"  🔗 Merged: {len(all_elements)} total ({time.time() - t0:.1f}s)")

    annotated_path = annotate_image(img_path, all_elements)

    # Convert all coordinates to click space
    scale = _get_backing_scale_factor()
    if scale != 1.0:
        coord_keys = ("cx", "cy", "x", "y", "w", "h")
        for el in all_elements:
            for k in coord_keys:
                if k in el:
                    el[k] = int(el[k] / scale)

    return all_elements, img_path, annotated_path
