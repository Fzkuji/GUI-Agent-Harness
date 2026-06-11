#!/usr/bin/env python3
"""
GUI Template Matching - Learn once, match forever.

Usage:
  # Save a template (crop from current screen)
  python template_match.py save --app WeChat --name search_bar --region 100,200,300,250
  
  # Save with click offset (where to click within the template)
  python template_match.py save --app WeChat --name search_bar --region 100,200,300,250 --click 150,225
  
  # Find a template on current screen
  python template_match.py find --app WeChat --name search_bar
  
  # Find and click
  python template_match.py click --app WeChat --name search_bar
  
  # List all saved templates
  python template_match.py list [--app WeChat]
  
  # Auto-learn: screenshot + vision model identified coords, save as template
  python template_match.py learn --app WeChat --name search_bar --center 485,244 --size 200,40

Output (find/click):
  JSON with matched position: {"found": true, "x": 485, "y": 244, "confidence": 0.95}
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# Template storage directory
# gui_harness/perception/ → gui_harness/ → project_root/templates
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"
SCREENSHOT_PATH = "/tmp/gui_template_screen.png"


def get_screen_resolution():
    """Get logical screen resolution."""
    result = subprocess.run(
        ["system_profiler", "SPDisplaysDataType"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if "Resolution" in line:
            # e.g., "Resolution: 3024 x 1964 Retina"
            parts = line.split()
            idx = parts.index("x")
            phys_w, phys_h = int(parts[idx - 1]), int(parts[idx + 1])
            is_retina = "Retina" in line
            if is_retina:
                return phys_w // 2, phys_h // 2
            return phys_w, phys_h
    return 1512, 982  # default MacBook Pro


def take_screenshot(path=SCREENSHOT_PATH):
    """Take a screenshot and return the image."""
    subprocess.run(["/usr/sbin/screencapture", "-x", path], check=True)
    img = cv2.imread(path)
    return img


def get_index_path(app_name):
    """Get the index.json path for an app."""
    app_dir = TEMPLATE_DIR / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "index.json"


def load_index(app_name):
    """Load the template index for an app."""
    path = get_index_path(app_name)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_index(app_name, index):
    """Save the template index for an app."""
    path = get_index_path(app_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def cmd_save(args):
    """Save a template by cropping from current screen."""
    img = take_screenshot()
    
    # Parse region: x,y,w,h (in logical pixels, but screenshot is retina)
    x, y, w, h = map(int, args.region.split(","))
    
    # Retina: multiply by 2 for actual pixel coords in screenshot
    scale = img.shape[1] / get_screen_resolution()[0]
    sx, sy, sw, sh = int(x * scale), int(y * scale), int(w * scale), int(h * scale)
    
    template = img[sy:sy+sh, sx:sx+sw]
    
    # Save template image
    app_dir = TEMPLATE_DIR / args.app
    app_dir.mkdir(parents=True, exist_ok=True)
    template_path = app_dir / f"{args.name}.png"
    cv2.imwrite(str(template_path), template)
    
    # Determine click offset (center of template by default)
    if args.click:
        click_x, click_y = map(int, args.click.split(","))
        click_offset = [click_x - x, click_y - y]
    else:
        click_offset = [w // 2, h // 2]
    
    # Update index
    index = load_index(args.app)
    index[args.name] = {
        "template": f"{args.name}.png",
        "click_offset": click_offset,
        "original_region": [x, y, w, h],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_matched": None,
        "match_count": 0,
        "threshold": args.threshold
    }
    save_index(args.app, index)
    
    print(json.dumps({
        "saved": True,
        "app": args.app,
        "name": args.name,
        "path": str(template_path),
        "region": [x, y, w, h],
        "click_offset": click_offset
    }))


def detect_element_bounds(screenshot, cx, cy, fallback_size=(160, 80), 
                           ocr_box=None):
    """Detect UI element boundaries around a click point.
    
    Strategy (ordered):
    1. If ocr_box provided → use it directly (most reliable)
    2. Color flood fill — find connected region of similar color
    3. Edge detection → find contours
    4. Fallback → fixed size
    
    Args:
        screenshot: Full retina screenshot (numpy array)
        cx, cy: Click point in RETINA pixel coordinates
        fallback_size: (w, h) in retina pixels if detection fails
        ocr_box: Optional (x, y, w, h) in retina pixels from OCR
        
    Returns:
        (x, y, w, h) in retina pixel coordinates, detection method string
    """
    img_h, img_w = screenshot.shape[:2]
    
    # Strategy 1: OCR bounding box (if available)
    if ocr_box:
        bx, by, bw, bh = ocr_box
        # Add padding
        pad = 12
        bx = max(0, bx - pad)
        by = max(0, by - pad)
        bw = min(bw + 2 * pad, img_w - bx)
        bh = min(bh + 2 * pad, img_h - by)
        return (bx, by, bw, bh), "ocr_box"
    
    # Crop a large area around the point
    crop_half = 200
    crop_x1 = max(0, cx - crop_half)
    crop_y1 = max(0, cy - crop_half)
    crop_x2 = min(img_w, cx + crop_half)
    crop_y2 = min(img_h, cy + crop_half)
    
    crop = screenshot[crop_y1:crop_y2, crop_x1:crop_x2]
    if crop.size == 0:
        fw, fh = fallback_size
        return (cx - fw // 2, cy - fh // 2, fw, fh), "fallback"
    
    rel_cx = cx - crop_x1
    rel_cy = cy - crop_y1
    
    # Strategy 2: Color-based region growing
    # Sample the color at click point, find connected area of similar color
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    center_color = hsv[rel_cy, rel_cx]
    
    # Create mask of pixels similar to the center color
    tolerance = np.array([15, 40, 40])  # H, S, V tolerance
    lower = np.clip(center_color.astype(int) - tolerance, 0, 255).astype(np.uint8)
    upper = np.clip(center_color.astype(int) + tolerance, 0, 255).astype(np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    
    # Flood fill from center
    flood_mask = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), np.uint8)
    cv2.floodFill(mask, flood_mask, (rel_cx, rel_cy), 255)
    
    # Find bounding rect of the filled region
    filled_points = np.where(mask == 255)
    if len(filled_points[0]) > 50:  # need enough pixels
        y_min, y_max = filled_points[0].min(), filled_points[0].max()
        x_min, x_max = filled_points[1].min(), filled_points[1].max()
        rw, rh = x_max - x_min, y_max - y_min
        
        # Reasonable size check (retina pixels)
        if 30 <= rw <= 600 and 20 <= rh <= 300:
            aspect = rw / rh
            if 0.3 <= aspect <= 10:
                pad = 8
                bx = max(0, crop_x1 + x_min - pad)
                by = max(0, crop_y1 + y_min - pad)
                bw = min(rw + 2 * pad, img_w - bx)
                bh = min(rh + 2 * pad, img_h - by)
                return (bx, by, bw, bh), "color_flood"
    
    # Strategy 3: Edge detection (contours)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    best_rect = None
    best_area = float('inf')
    
    for blur_k in [3, 5]:
        for thresh_lo, thresh_hi in [(30, 100), (50, 150), (80, 200)]:
            blurred = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
            edges = cv2.Canny(blurred, thresh_lo, thresh_hi)
            kernel = np.ones((3, 3), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=1)
            
            contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                
                if not (x <= rel_cx <= x + w and y <= rel_cy <= y + h):
                    continue
                if w < 30 or h < 20 or w > 500 or h > 250:
                    continue
                aspect = w / h
                if aspect < 0.25 or aspect > 8:
                    continue
                if area < best_area:
                    best_area = area
                    best_rect = (crop_x1 + x, crop_y1 + y, w, h)
    
    if best_rect:
        pad = 8
        bx, by, bw, bh = best_rect
        bx = max(0, bx - pad)
        by = max(0, by - pad)
        bw = min(bw + 2 * pad, img_w - bx)
        bh = min(bh + 2 * pad, img_h - by)
        return (bx, by, bw, bh), "edge"
    
    # Strategy 4: Fallback
    fw, fh = fallback_size
    fx = max(0, cx - fw // 2)
    fy = max(0, cy - fh // 2)
    return (fx, fy, fw, fh), "fallback"


def auto_learn_element(app_name, element_name, click_x, click_y, 
                        screenshot=None, source_info=None, threshold=0.85):
    """Auto-learn a UI element after a successful click.
    
    Takes a screenshot, detects element bounds around the click point,
    crops and saves as a template.
    
    Args:
        app_name: App name (e.g., "WeChat")
        element_name: Element identifier (e.g., "search_bar", "send_button")  
        click_x, click_y: Click position in LOGICAL pixels
        screenshot: Optional pre-taken screenshot (retina)
        source_info: Optional dict with context (e.g., {"from": "ocr", "text": "搜索"})
        threshold: Match threshold (default 0.85)
    
    Returns:
        dict with save result
    """
    if screenshot is None:
        screenshot = take_screenshot()
    
    screen_w = get_screen_resolution()[0]
    scale = screenshot.shape[1] / screen_w
    
    # Convert logical → retina
    retina_cx = int(click_x * scale)
    retina_cy = int(click_y * scale)
    
    # Detect element bounds
    (rx, ry, rw, rh), detection_method = detect_element_bounds(screenshot, retina_cx, retina_cy)
    
    # Crop the template
    template = screenshot[ry:ry+rh, rx:rx+rw]
    if template.size == 0:
        return {"saved": False, "error": "Empty template region"}
    
    # Save template image
    app_dir = TEMPLATE_DIR / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    template_path = app_dir / f"{element_name}.png"
    cv2.imwrite(str(template_path), template)
    
    # Click offset: where in the template to click (logical pixels, relative to template top-left)
    logical_rx = int(rx / scale)
    logical_ry = int(ry / scale)
    click_offset = [click_x - logical_rx, click_y - logical_ry]
    logical_w = int(rw / scale)
    logical_h = int(rh / scale)
    
    # Update index
    index = load_index(app_name)
    existing = index.get(element_name, {})
    index[element_name] = {
        "template": f"{element_name}.png",
        "click_offset": click_offset,
        "size": [logical_w, logical_h],
        "original_region": [logical_rx, logical_ry, logical_w, logical_h],
        "created": existing.get("created", time.strftime("%Y-%m-%d %H:%M:%S")),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_matched": existing.get("last_matched"),
        "match_count": existing.get("match_count", 0),
        "threshold": threshold,
        "source": source_info or {},
        "detection": detection_method
    }
    save_index(app_name, index)
    
    return {
        "saved": True,
        "app": app_name,
        "name": element_name,
        "region": [logical_rx, logical_ry, logical_w, logical_h],
        "click_offset": click_offset,
        "detection": detection_method,
        "path": str(template_path)
    }


def cmd_learn(args):
    """Auto-learn: given a center point and size, crop and save template."""
    img = take_screenshot()
    
    cx, cy = map(int, args.center.split(","))
    
    if args.auto:
        # Use edge detection to find element bounds
        result = auto_learn_element(args.app, args.name, cx, cy, screenshot=img,
                                     threshold=args.threshold)
        print(json.dumps(result))
        return
    
    tw, th = map(int, args.size.split(","))
    
    # Region in logical pixels
    x = cx - tw // 2
    y = cy - th // 2
    
    # Retina scaling
    scale = img.shape[1] / get_screen_resolution()[0]
    sx, sy, sw, sh = int(x * scale), int(y * scale), int(tw * scale), int(th * scale)
    
    # Clamp to image bounds
    sx = max(0, sx)
    sy = max(0, sy)
    sw = min(sw, img.shape[1] - sx)
    sh = min(sh, img.shape[0] - sy)
    
    template = img[sy:sy+sh, sx:sx+sw]
    
    if template.size == 0:
        print(json.dumps({"saved": False, "error": "Empty template region"}))
        return
    
    # Save
    app_dir = TEMPLATE_DIR / args.app
    app_dir.mkdir(parents=True, exist_ok=True)
    template_path = app_dir / f"{args.name}.png"
    cv2.imwrite(str(template_path), template)
    
    # Click offset is center
    click_offset = [tw // 2, th // 2]
    
    index = load_index(args.app)
    index[args.name] = {
        "template": f"{args.name}.png",
        "click_offset": click_offset,
        "original_region": [x, y, tw, th],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_matched": None,
        "match_count": 0,
        "threshold": args.threshold
    }
    save_index(args.app, index)
    
    print(json.dumps({
        "saved": True,
        "app": args.app,
        "name": args.name,
        "center": [cx, cy],
        "size": [tw, th],
        "click_offset": click_offset
    }))


def find_template(app_name, element_name, screenshot=None, multi_scale=True):
    """Find a template on screen. Returns (x, y, confidence) or None."""
    index = load_index(app_name)
    if element_name not in index:
        return None
    
    entry = index[element_name]
    template_path = TEMPLATE_DIR / app_name / entry["template"]
    
    if not template_path.exists():
        return None
    
    template = cv2.imread(str(template_path))
    if screenshot is None:
        screenshot = take_screenshot()
    
    threshold = entry.get("threshold", 0.85)
    click_offset = entry.get("click_offset", [0, 0])
    screen_w = get_screen_resolution()[0]
    scale = screenshot.shape[1] / screen_w
    
    best_val = 0
    best_loc = None
    best_scale_factor = 1.0
    
    # Multi-scale matching for robustness
    # Only use multi-scale for larger templates; small ones get false positives
    scales = [1.0]
    if multi_scale:
        tmpl_min_dim = min(template.shape[0], template.shape[1])
        if tmpl_min_dim > 80:  # Only multi-scale for templates > 80px (retina)
            scales = [0.9, 0.95, 1.0, 1.05, 1.1]
        # Always try exact match first (scale=1.0 is already in list)
    
    gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
    gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    
    for s in scales:
        if s != 1.0:
            new_w = int(gray_template.shape[1] * s)
            new_h = int(gray_template.shape[0] * s)
            if new_w < 10 or new_h < 10:
                continue
            scaled_template = cv2.resize(gray_template, (new_w, new_h))
        else:
            scaled_template = gray_template
        
        if (scaled_template.shape[0] > gray_screen.shape[0] or
            scaled_template.shape[1] > gray_screen.shape[1]):
            continue
        
        result = cv2.matchTemplate(gray_screen, scaled_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_scale_factor = s
    
    if best_val < threshold:
        return None
    
    # Click position: template top-left (in retina pixels) + click_offset (in logical) * scale
    # Then convert everything back to logical
    logical_x = int(best_loc[0] / scale) + click_offset[0]
    logical_y = int(best_loc[1] / scale) + click_offset[1]
    
    # Update stats
    index[element_name]["last_matched"] = time.strftime("%Y-%m-%d %H:%M:%S")
    index[element_name]["match_count"] = index[element_name].get("match_count", 0) + 1
    save_index(app_name, index)
    
    return {
        "found": True,
        "x": logical_x,
        "y": logical_y,
        "confidence": round(best_val, 4),
        "scale": round(best_scale_factor, 2)
    }


def cmd_find(args):
    """Find a template on current screen."""
    result = find_template(args.app, args.name)
    if result:
        print(json.dumps(result))
    else:
        print(json.dumps({"found": False, "app": args.app, "name": args.name}))


def cmd_click(args):
    """Find and click a template."""
    result = find_template(args.app, args.name)
    if not result:
        print(json.dumps({"clicked": False, "found": False, "app": args.app, "name": args.name}))
        return
    
    x, y = result["x"], result["y"]
    subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
    
    print(json.dumps({
        "clicked": True,
        "x": x,
        "y": y,
        "confidence": result["confidence"]
    }))


def cmd_list(args):
    """List all saved templates."""
    if args.app:
        apps = [args.app]
    else:
        if not TEMPLATE_DIR.exists():
            print(json.dumps({"templates": {}}))
            return
        apps = [d.name for d in TEMPLATE_DIR.iterdir() if d.is_dir()]
    
    templates = {}
    for app in apps:
        index = load_index(app)
        if index:
            templates[app] = index
    
    print(json.dumps({"templates": templates}, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="GUI Template Matching")
    sub = parser.add_subparsers(dest="command", required=True)
    
    # save
    p_save = sub.add_parser("save", help="Save template from screen region")
    p_save.add_argument("--app", required=True, help="App name")
    p_save.add_argument("--name", required=True, help="Element name")
    p_save.add_argument("--region", required=True, help="x,y,w,h in logical pixels")
    p_save.add_argument("--click", help="Click position x,y in logical pixels (default: center)")
    p_save.add_argument("--threshold", type=float, default=0.85, help="Match threshold")
    
    # learn
    p_learn = sub.add_parser("learn", help="Auto-learn from center point")
    p_learn.add_argument("--app", required=True, help="App name")
    p_learn.add_argument("--name", required=True, help="Element name")
    p_learn.add_argument("--center", required=True, help="Center x,y in logical pixels")
    p_learn.add_argument("--size", default="80,40", help="Template w,h (default: 80,40)")
    p_learn.add_argument("--auto", action="store_true", help="Auto-detect element bounds via edge detection")
    p_learn.add_argument("--threshold", type=float, default=0.85, help="Match threshold")
    
    # auto_learn (shorthand for learn --auto)
    p_auto = sub.add_parser("auto_learn", help="Auto-detect and save element at click point")
    p_auto.add_argument("--app", required=True, help="App name")
    p_auto.add_argument("--name", required=True, help="Element name")
    p_auto.add_argument("--click", required=True, help="Click position x,y in logical pixels")
    p_auto.add_argument("--source", default="", help="Source info (e.g., 'ocr:搜索')")
    p_auto.add_argument("--threshold", type=float, default=0.85, help="Match threshold")
    
    # find
    p_find = sub.add_parser("find", help="Find template on screen")
    p_find.add_argument("--app", required=True, help="App name")
    p_find.add_argument("--name", required=True, help="Element name")
    
    # click
    p_click = sub.add_parser("click", help="Find and click template")
    p_click.add_argument("--app", required=True, help="App name")
    p_click.add_argument("--name", required=True, help="Element name")
    
    # list
    p_list = sub.add_parser("list", help="List saved templates")
    p_list.add_argument("--app", help="Filter by app")
    
    args = parser.parse_args()
    
    if args.command == "save":
        cmd_save(args)
    elif args.command == "learn":
        cmd_learn(args)
    elif args.command == "auto_learn":
        cx, cy = map(int, args.click.split(","))
        source = {}
        if args.source:
            parts = args.source.split(":", 1)
            source = {"method": parts[0], "text": parts[1] if len(parts) > 1 else ""}
        result = auto_learn_element(args.app, args.name, cx, cy,
                                     source_info=source, threshold=args.threshold)
        print(json.dumps(result, indent=2))
    elif args.command == "find":
        cmd_find(args)
    elif args.command == "click":
        cmd_click(args)
    elif args.command == "list":
        cmd_list(args)


if __name__ == "__main__":
    main()
