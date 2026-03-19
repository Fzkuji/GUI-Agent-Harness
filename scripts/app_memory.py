#!/usr/bin/env python3
"""
App Visual Memory — per-app component memory with template matching.

Each app gets:
- profile.json: window structure, known pages, component registry
- components/: cropped component images (named by content/function)
- pages/: page-specific layouts with relative coordinates

All coordinates are RELATIVE to the window top-left corner.

Usage:
    # Learn: detect + save all components for an app
    python app_memory.py learn --app WeChat

    # Find: match a known component on current screen
    python app_memory.py find --app WeChat --component search_bar

    # List: show all known components for an app
    python app_memory.py list --app WeChat

    # Detect: run detection and match against memory
    python app_memory.py detect --app WeChat
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

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
MEMORY_DIR = SKILL_DIR / "memory" / "apps"


# ═══════════════════════════════════════════
# Window utilities (relative coordinates)
# ═══════════════════════════════════════════

def get_window_bounds(app_name):
    """Get window position and size. Returns (x, y, w, h) or None.
    
    Selects the largest window if the app has multiple windows.
    """
    try:
        r = subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to tell process "{app_name}"\n'
             f'  set best to missing value\n'
             f'  set bestArea to 0\n'
             f'  repeat with w in every window\n'
             f'    set {{ww, wh}} to size of w\n'
             f'    if ww * wh > bestArea then\n'
             f'      set bestArea to ww * wh\n'
             f'      set best to w\n'
             f'    end if\n'
             f'  end repeat\n'
             f'  if best is not missing value then\n'
             f'    set {{wx, wy}} to position of best\n'
             f'    set {{ww, wh}} to size of best\n'
             f'    return {{wx, wy, ww, wh}}\n'
             f'  end if\n'
             f'end tell'],
            capture_output=True, text=True, timeout=5
        )
        nums = [int(n.strip()) for n in r.stdout.split(",") if n.strip()]
        if len(nums) == 4:
            return tuple(nums)  # (x, y, w, h)
    except:
        pass
    return None


def capture_window(app_name, out_path=None):
    """Capture a specific app window, return (img_path, win_x, win_y, win_w, win_h)."""
    # Activate app
    # Use set frontmost (works for all apps including CleanMyMac)
    subprocess.run(["osascript", "-e",
        f'tell application "System Events" to set frontmost of process "{app_name}" to true'],
        capture_output=True, timeout=5)
    time.sleep(0.3)

    bounds = get_window_bounds(app_name)
    if not bounds:
        return None, 0, 0, 0, 0

    win_x, win_y, win_w, win_h = bounds

    if out_path is None:
        out_path = f"/tmp/app_memory_{app_name.lower()}.png"

    # Try window-specific capture via CGWindowList
    import ui_detector
    win_info = ui_detector.get_window_info(app_name)
    if win_info:
        ui_detector.take_window_screenshot(win_info["id"], out_path)
    else:
        # Fallback: full screenshot + crop
        subprocess.run(["/usr/sbin/screencapture", "-x", "/tmp/_full.png"],
                       check=True, timeout=5)
        img = cv2.imread("/tmp/_full.png")
        # Retina: multiply by 2
        rx, ry, rw, rh = win_x * 2, win_y * 2, win_w * 2, win_h * 2
        crop = img[ry:ry+rh, rx:rx+rw]
        cv2.imwrite(out_path, crop)

    return out_path, win_x, win_y, win_w, win_h


# ═══════════════════════════════════════════
# Memory management
# ═══════════════════════════════════════════

def get_app_dir(app_name):
    """Get/create memory directory for an app."""
    app_dir = MEMORY_DIR / app_name.lower().replace(" ", "_")
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "components").mkdir(exist_ok=True)
    (app_dir / "pages").mkdir(exist_ok=True)
    return app_dir


def get_site_dir(app_name, domain):
    """Get/create memory directory for a website within a browser app."""
    app_dir = get_app_dir(app_name)
    # Sanitize domain: "kyfw.12306.cn" → "12306_cn"
    safe_domain = domain.replace(".", "_").replace(":", "").replace("/", "")[:50]
    site_dir = app_dir / "sites" / safe_domain
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "components").mkdir(exist_ok=True)
    (site_dir / "pages").mkdir(exist_ok=True)
    return site_dir


def get_current_url(app_name="Google Chrome"):
    """Get the current URL from the browser address bar."""
    try:
        r = subprocess.run(
            ["osascript", "-e", f'tell application "{app_name}" to return URL of active tab of front window'],
            capture_output=True, text=True, timeout=15
        )
        return r.stdout.strip()
    except:
        return ""


def get_domain_from_url(url):
    """Extract domain from URL. 'https://kyfw.12306.cn/otn/leftTicket/init' → 'kyfw.12306.cn'"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0]
    except:
        return ""


def load_profile(app_name):
    """Load app profile (component registry + click graph states)."""
    app_dir = get_app_dir(app_name)
    profile_path = app_dir / "profile.json"
    if profile_path.exists():
        with open(profile_path) as f:
            return json.load(f)
    return {
        "app": app_name,
        "components": {},  # name -> {type, rel_x, rel_y, icon_file, label, ...}
        "states": {},      # state_name -> {visible: [...], trigger, trigger_pos, disappeared, description}
        "last_updated": None,
        "window_size": None,
    }


def _find_nearest_text(icon_el, text_elements, max_dist=60):
    """Find the nearest text element to an icon, to use as its name.

    CONSERVATIVE: only matches text that overlaps or nearly overlaps the icon
    (within max_dist retina pixels). This avoids false matches in dense UIs.

    For icons without a nearby match, they stay unlabeled and the agent
    identifies them later by viewing the cropped images.

    All coordinates are in retina pixels (2x logical).

    Returns the text label string, or None.
    """
    icon_cx = icon_el["cx"]
    icon_cy = icon_el["cy"]
    icon_w = icon_el.get("w", 0)
    icon_h = icon_el.get("h", 0)

    best = None
    best_dist = max_dist

    for t in text_elements:
        label = t.get("label", "")
        if not label or len(label) < 2:
            continue
        # Skip long text (likely content, not a UI label)
        if len(label) > 15:
            continue

        t_cx = t["cx"]
        t_cy = t["cy"]

        # Only match if text significantly overlaps with the icon region
        # (same bounding box or very close)
        dy = abs(t_cy - icon_cy)
        dx = abs(t_cx - icon_cx)
        dist = (dx ** 2 + dy ** 2) ** 0.5

        if dist < best_dist:
            best_dist = dist
            best = label

    return best


def assign_region(el, win_w, win_h):
    """Stub — always returns 'default'. 
    
    State identification is done via click-graph matching, not preset regions.
    """
    return "default"


# macOS traffic light buttons — fixed positions relative to window top-left
# These are system-level and identical across all apps
MACOS_SYSTEM_COMPONENTS = {
    "sys_close":    {"rel_x": 14, "rel_y": 14, "w": 12, "h": 12, "type": "system", "desc": "Close (red)"},
    "sys_minimize": {"rel_x": 34, "rel_y": 14, "w": 12, "h": 12, "type": "system", "desc": "Minimize (yellow)"},
    "sys_fullscreen":{"rel_x": 54, "rel_y": 14, "w": 12, "h": 12, "type": "system", "desc": "Fullscreen (green)"},
}


def _is_traffic_light(el, win_w, win_h):
    """Check if element overlaps with macOS traffic light buttons."""
    rel_x = el.get("cx", 0) // 2
    rel_y = el.get("cy", 0) // 2
    # Traffic lights are at top-left, roughly x < 70, y < 30
    return rel_x < 70 and rel_y < 30


def should_save_component(el, win_w, win_h):
    """Decide whether to save a detected component.

    Rules for what to save (stable UI):
    - Sidebar elements (left region)
    - Toolbar elements (top region)
    - Header/Footer elements
    - Elements with OCR text labels

    Rules for what to SKIP (dynamic content):
    - Content area folder/file icons (they change every session)
    - Tiny icons (< 30x30)
    - Elements in the main content area without labels

    Returns: (should_save, reason)
    """
    # Skip macOS traffic light buttons (close/minimize/fullscreen)
    if _is_traffic_light(el, win_w, win_h):
        return False, "traffic_light"

    # Skip tiny elements
    w, h = el.get("w", 0), el.get("h", 0)
    if w < 25 or h < 25:
        return False, "too_small"

    # Get position
    cx, cy = el.get("cx", 0), el.get("cy", 0)
    rel_x = cx // 2  # Convert to logical pixels
    rel_y = cy // 2

    # Define regions (relative to window size)
    is_sidebar = rel_x < win_w * 0.15  # Left 15%
    is_toolbar = rel_y < win_h * 0.12   # Top 12%
    is_footer = rel_y > win_h * 0.88     # Bottom 12%
    is_content_area = not (is_sidebar or is_toolbar or is_footer)

    # Has OCR label → likely stable UI element
    has_label = el.get("label") and len(el.get("label", "").strip()) > 0

    # If has label and in stable region → save
    if has_label and (is_sidebar or is_toolbar or is_footer):
        return True, "labeled_stable_region"

    # If in sidebar or toolbar → likely stable UI
    if is_sidebar or is_toolbar:
        return True, "stable_region"

    # If has label → might be useful, save it
    if has_label:
        return True, "has_label"

    # Content area without label → likely dynamic content (folder icons, etc.)
    if is_content_area and not has_label:
        return False, "dynamic_content_area"

    # Default: save it
    return True, "default"


def identify_state(app_name, visible_text):
    """Identify current state by matching visible text against known states.
    
    Each state is defined by which components are visible on screen.
    The state with the highest match ratio is the current state.
    
    Args:
        app_name: App name
        visible_text: List of visible text strings from OCR
        
    Returns:
        (state_name, match_ratio) or (None, 0)
    """
    profile = load_profile(app_name)
    states = profile.get("states", {})
    
    if not states:
        return None, 0
    
    # Convert visible_text to set for fast matching
    visible_set = set(t.strip() for t in visible_text if t and t.strip())
    
    best_state = None
    best_ratio = 0.0
    
    for state_name, state_data in states.items():
        state_visible = set(state_data.get("visible", []))
        if not state_visible:
            continue
        
        # Count overlap
        overlap = len(visible_set & state_visible)
        ratio = overlap / len(state_visible)
        
        if ratio > best_ratio:
            best_ratio = ratio
            best_state = state_name
    
    return best_state, best_ratio


def get_state_components(app_name, state_name):
    """Get component names that are visible in a given state.
    
    Args:
        app_name: App name
        state_name: State name
        
    Returns:
        list of component names (from state's "visible" list)
    """
    profile = load_profile(app_name)
    states = profile.get("states", {})
    
    if state_name not in states:
        return []
    
    return states[state_name].get("visible", [])


def save_state(app_name, state_name, visible_texts, trigger=None, trigger_pos=None, disappeared=None, description=None):
    """Save a state to the profile.
    
    Args:
        app_name: App name
        state_name: State name (e.g., "initial", "click:Settings")
        visible_texts: List of component names/text visible in this state
        trigger: Component name that triggered this state (for click:X states)
        trigger_pos: [x, y] position where trigger was clicked
        disappeared: List of component names that disappeared when entering this state
        description: Optional human-readable description
    """
    profile = load_profile(app_name)
    
    if "states" not in profile:
        profile["states"] = {}
    
    state_data = {
        "visible": visible_texts,
    }
    
    if trigger:
        state_data["trigger"] = trigger
    if trigger_pos:
        state_data["trigger_pos"] = trigger_pos
    if disappeared:
        state_data["disappeared"] = disappeared
    if description:
        state_data["description"] = description
    
    profile["states"][state_name] = state_data
    save_profile(app_name, profile)


def save_profile(app_name, profile):
    """Save app profile."""
    app_dir = get_app_dir(app_name)
    profile["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(app_dir / "profile.json", "w") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def save_component_icon(app_name, component_name, img, bbox, retina_scale=2):
    """Crop and save a component's icon image.

    RULES:
    - Filename MUST describe the content (not coordinates)
    - If label exists: use label as filename
    - If no label: use "unlabeled_<position>" temporarily
    - After LLM identifies: rename to actual content description

    bbox: (x, y, w, h) in the window screenshot's pixel coordinates.
    """
    app_dir = get_app_dir(app_name)
    x, y, w, h = bbox

    # Add padding
    pad = 4
    y1 = max(0, y - pad)
    x1 = max(0, x - pad)
    y2 = min(img.shape[0], y + h + pad)
    x2 = min(img.shape[1], x + w + pad)

    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    # Sanitize filename — name should describe content
    safe_name = component_name.replace("/", "-").replace(" ", "_").replace(":", "")
    safe_name = safe_name.replace("\\", "-").replace("?", "").replace("*", "")[:50]
    icon_path = app_dir / "components" / f"{safe_name}.png"
    cv2.imwrite(str(icon_path), crop)
    return str(icon_path.relative_to(app_dir))


def is_duplicate_icon(new_crop, existing_icons_dir, threshold=0.9):
    """Check if a cropped icon is a duplicate of any existing saved icon.

    Returns: (is_dup, matching_name) or (False, None)
    """
    if new_crop is None or new_crop.size == 0:
        return False, None

    gray_new = cv2.cvtColor(new_crop, cv2.COLOR_BGR2GRAY)

    for icon_file in existing_icons_dir.glob("*.png"):
        existing = cv2.imread(str(icon_file))
        if existing is None:
            continue

        gray_exist = cv2.cvtColor(existing, cv2.COLOR_BGR2GRAY)

        # Resize to same size for comparison
        h1, w1 = gray_new.shape
        h2, w2 = gray_exist.shape

        # Skip if size difference > 2x
        if max(h1, h2) > 2 * min(h1, h2) or max(w1, w2) > 2 * min(w1, w2):
            continue

        # Resize smaller to match larger
        target_h = min(h1, h2)
        target_w = min(w1, w2)
        if target_h < 5 or target_w < 5:
            continue

        r1 = cv2.resize(gray_new, (target_w, target_h))
        r2 = cv2.resize(gray_exist, (target_w, target_h))

        result = cv2.matchTemplate(r1, r2, cv2.TM_CCOEFF_NORMED)
        similarity = result[0][0]

        if similarity > threshold:
            return True, icon_file.stem

    return False, None


# ═══════════════════════════════════════════
# Template matching
# ═══════════════════════════════════════════

def match_component(app_name, component_name, window_img, threshold=0.8):
    """Match a saved component template against current window.

    Returns: (found, rel_x, rel_y, confidence) or (False, 0, 0, 0)
    Coordinates are relative to window, in logical pixels.
    """
    app_dir = get_app_dir(app_name)
    profile = load_profile(app_name)

    comp = profile["components"].get(component_name)
    if not comp or not comp.get("icon_file"):
        return False, 0, 0, 0

    template_path = app_dir / comp["icon_file"]
    if not template_path.exists():
        return False, 0, 0, 0

    template = cv2.imread(str(template_path))
    if template is None:
        return False, 0, 0, 0

    # Convert both to grayscale
    gray_img = cv2.cvtColor(window_img, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    if (gray_tpl.shape[0] > gray_img.shape[0] or
        gray_tpl.shape[1] > gray_img.shape[1]):
        return False, 0, 0, 0

    result = cv2.matchTemplate(gray_img, gray_tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        # Convert to logical pixels (÷2 for retina)
        rel_x = max_loc[0] // 2 + template.shape[1] // 4
        rel_y = max_loc[1] // 2 + template.shape[0] // 4
        return True, rel_x, rel_y, round(max_val, 4)

    return False, 0, 0, 0


def match_all_components(app_name, window_img, threshold=0.8):
    """Match all saved components against current window.

    Returns: list of (component_name, rel_x, rel_y, confidence)
    """
    profile = load_profile(app_name)
    matches = []

    for comp_name in profile["components"]:
        found, rx, ry, conf = match_component(app_name, comp_name, window_img, threshold)
        if found:
            matches.append((comp_name, rx, ry, conf))

    return matches


# ═══════════════════════════════════════════
# Learn: detect + save all components
# ═══════════════════════════════════════════

def learn_app(app_name, page_name=None):
    """Detect all UI elements and save to memory.

    Flow:
    1. Capture window screenshot
    2. Run GPA-GUI-Detector + OCR
    3. Crop each element
    4. Save to profile with relative coordinates
    5. Save "initial" state with all visible OCR texts
    
    Note: page_name parameter is kept for compatibility but ignored.
          State identification happens through the click graph.
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    import ui_detector

    print(f"🧠 Learning {app_name}...")

    # 1. Capture
    img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
    if not img_path:
        print(f"  ❌ Could not capture {app_name} window")
        return False

    print(f"  📸 Window at ({win_x},{win_y}) {win_w}x{win_h}")

    # 2. Detect
    icon_elements, img_w, img_h = ui_detector.detect_icons(img_path, conf=0.1, iou=0.3)
    text_elements = ui_detector.detect_text(img_path)
    all_elements = ui_detector.merge_elements(icon_elements, text_elements, iou_threshold=0.3)

    print(f"  🔍 Detected {len(all_elements)} elements ({len(icon_elements)} icons, {len(text_elements)} text)")

    # 3. Load existing profile
    profile = load_profile(app_name)
    profile["window_size"] = [win_w, win_h]
    profile["retina_img_size"] = [img_w, img_h]

    # Inject macOS system components (traffic light buttons)
    for sys_name, sys_data in MACOS_SYSTEM_COMPONENTS.items():
        if sys_name not in profile["components"]:
            profile["components"][sys_name] = {
                "type": sys_data["type"],
                "source": "system",
                "rel_x": sys_data["rel_x"],
                "rel_y": sys_data["rel_y"],
                "w": sys_data["w"],
                "h": sys_data["h"],
                "label": sys_data["desc"],
                "confidence": 1.0,
                "page": "all",
            }

    # 4. Read image for cropping
    img = cv2.imread(img_path)

    # 5. Save each element (with filtering + dedup + smart naming)
    learned_components = []
    visible_texts = []  # For initial state
    new_count = 0
    dup_count = 0
    skip_count = 0
    skip_reasons = {}
    icons_dir = get_app_dir(app_name) / "components"

    for el in all_elements:
        # --- FILTER: Decide whether to save this component ---
        should_save, reason = should_save_component(el, win_w, win_h)
        if not should_save:
            skip_count += 1
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        # --- Smart naming ---
        # Rule: filename = content description, NOT coordinates
        if el.get("label"):
            # Has text label → use it
            comp_name = el["label"].replace(" ", "_").replace("/", "-")[:30]
        else:
            # No label → find nearest text element to use as name
            nearest_label = _find_nearest_text(el, text_elements)
            if nearest_label:
                comp_name = nearest_label.replace(" ", "_").replace("/", "-")[:30]
            else:
                # Last resort: use "unlabeled_<region>_<position>"
                rel_x = el["cx"] // 2
                rel_y = el["cy"] // 2
                if rel_x < 60:
                    region = "leftbar"
                elif rel_y < 50:
                    region = "toolbar"
                elif rel_y > 550:
                    region = "bottom"
                else:
                    region = "main"
                comp_name = f"unlabeled_{region}_{rel_x}_{rel_y}"

        # --- Check if already known (by similar position) ---
        is_new = True
        for existing_name, existing in profile["components"].items():
            if (abs(existing.get("rel_x", 0) - el["cx"] // 2) < 15 and
                abs(existing.get("rel_y", 0) - el["cy"] // 2) < 15):
                is_new = False
                comp_name = existing_name  # Keep existing name
                break

        # --- Crop icon ---
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        pad = 4
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(img.shape[0], y + h + pad)
        x2 = min(img.shape[1], x + w + pad)
        crop = img[y1:y2, x1:x2]

        if crop.size == 0:
            continue

        # --- Dedup: skip if visually identical icon already saved ---
        is_dup, dup_name = is_duplicate_icon(crop, icons_dir, threshold=0.92)
        if is_dup and is_new:
            dup_count += 1
            # Don't save duplicate, but record it points to existing
            el["duplicate_of"] = dup_name
            continue

        # --- Save icon image ---
        icon_file = save_component_icon(
            app_name, comp_name, img,
            (el["x"], el["y"], el["w"], el["h"])
        )

        # Relative coordinates (logical pixels, relative to window top-left)
        rel_x = el["cx"] // 2  # retina → logical
        rel_y = el["cy"] // 2
        
        # Assign region
        region = assign_region(el, win_w, win_h)

        comp_data = {
            "type": el["type"],
            "source": el.get("source", "unknown"),
            "rel_x": rel_x,
            "rel_y": rel_y,
            "w": el["w"] // 2,
            "h": el["h"] // 2,
            "icon_file": icon_file,
            "label": el.get("label"),
            "confidence": el.get("confidence", 0),
            "region": region,
            "learned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        profile["components"][comp_name] = comp_data
        learned_components.append(comp_name)
        
        # Track visible text for initial state
        if el.get("label"):
            visible_texts.append(el.get("label"))

        if is_new:
            new_count += 1

    # 6. Save profile first (so save_state can load it with components)
    profile["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_profile(app_name, profile)
    
    # 7. Save "initial" state with ALL visible text (not just saved components)
    all_visible = [t.get("label", "") for t in text_elements if t.get("label")]
    if "initial" not in profile.get("states", {}):
        save_state(
            app_name, 
            "initial", 
            all_visible,
            description="Main app view when first opened"
        )
        print(f"  📊 Created 'initial' state with {len(all_visible)} visible texts")
    else:
        save_state(app_name, "initial", all_visible, description="Main app view when first opened")
        print(f"  📊 Updated 'initial' state with {len(all_visible)} visible texts")
    
    # 8. Reload profile (save_state updated it)
    profile = load_profile(app_name)

    # 8. Save annotated image
    app_dir = get_app_dir(app_name)
    annotated = ui_detector.annotate_image(img_path, all_elements,
                                            str(app_dir / "pages/annotated.jpg"))

    # 9. Save profile
    save_profile(app_name, profile)

    print(f"  💾 Saved {len(learned_components)} components ({new_count} new, {dup_count} dups, {skip_count} skipped)")
    if skip_reasons:
        print(f"     Skip reasons: {skip_reasons}")

    # 10. Auto-cleanup: remove dynamic content
    #    (timestamps, message previews, chat text, stickers)
    cleanup_count = auto_cleanup_dynamic(app_name)
    if cleanup_count > 0:
        print(f"  🧹 Auto-cleaned {cleanup_count} dynamic elements")

    # 11. Report unlabeled icons for agent identification
    profile = load_profile(app_name)  # reload after cleanup
    unlabeled = [name for name, comp in profile["components"].items()
                 if name.startswith("unlabeled_")]
    if unlabeled:
        # Collect image paths
        unlabeled_paths = []
        unlabeled_names = []
        for name in sorted(unlabeled):
            comp = profile["components"][name]
            icon_path = app_dir / comp.get("icon_file", f"components/{name}.png")
            if icon_path.exists():
                unlabeled_paths.append(str(icon_path))
                unlabeled_names.append(name)

        # Output structured prompt for agent
        print(f"\n{'='*60}")
        print(f"⚠ ACTION REQUIRED: {len(unlabeled)} unlabeled components")
        print(f"{'='*60}")
        print(f"STEP 1: View images with `image` tool (max 20 per call):")
        print(f"  IMAGES: {json.dumps(unlabeled_paths)}")
        print(f"  NAMES:  {json.dumps(unlabeled_names)}")
        print(f"STEP 2: For each image, identify what it shows.")
        print(f"  - Read any text in the image")
        print(f"  - Describe the icon/element")
        print(f"  - ⚠ PRIVACY: If it contains personal info (username, email,")
        print(f"    avatar, account details), DELETE it instead of renaming")
        print(f"STEP 3: Rename each component:")
        print(f"  python3 app_memory.py rename --app \"{app_name}\" --old <unlabeled_name> --new <actual_name>")
        print(f"  Or DELETE private ones:")
        print(f"  python3 app_memory.py delete --app \"{app_name}\" --component <name>")
        print(f"STEP 4: When task is fully complete, cleanup remaining:")
        print(f"  python3 agent.py cleanup --app \"{app_name}\"")
        print(f"{'='*60}")

    print(f"  📁 {app_dir}")
    return True


def learn_site(app_name="Google Chrome", page_name="main"):
    """Learn UI elements of the current website in a browser.

    Similar to learn_app but saves to sites/<domain>/ subdirectory.
    Only saves fixed site UI (nav, search, buttons), not content.
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    import ui_detector

    url = get_current_url(app_name)
    domain = get_domain_from_url(url)
    if not domain:
        print(f"  ❌ Could not get current URL from {app_name}")
        return False

    print(f"🌐 Learning site: {domain} (page: {page_name})")
    print(f"  URL: {url}")

    # Capture
    img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
    if not img_path:
        return False

    # Detect
    icon_elements, img_w, img_h = ui_detector.detect_icons(img_path, conf=0.1, iou=0.3)
    text_elements = ui_detector.detect_text(img_path)
    all_elements = ui_detector.merge_elements(icon_elements, text_elements, iou_threshold=0.3)
    print(f"  🔍 Detected {len(all_elements)} elements")

    # Save to site directory
    site_dir = get_site_dir(app_name, domain)
    profile_path = site_dir / "profile.json"
    if profile_path.exists():
        with open(profile_path) as f:
            profile = json.load(f)
    else:
        profile = {"domain": domain, "url": url, "components": {},
                    "pages": {}, "last_updated": None}

    profile["window_size"] = [win_w, win_h]
    img = cv2.imread(img_path)

    # Save elements (same logic as learn_app but to site dir)
    page_components = []
    new_count = 0
    dup_count = 0
    icons_dir = site_dir / "components"

    for el in all_elements:
        if el.get("label"):
            comp_name = el["label"].replace(" ", "_").replace("/", "-")[:30]
        else:
            nearest_label = _find_nearest_text(el, text_elements)
            if nearest_label:
                comp_name = nearest_label.replace(" ", "_").replace("/", "-")[:30]
            else:
                rel_x = el["cx"] // 2
                rel_y = el["cy"] // 2
                comp_name = f"unlabeled_{rel_x}_{rel_y}"

        # Dedup by position
        is_new = True
        for existing_name, existing in profile["components"].items():
            if (abs(existing.get("rel_x", 0) - el["cx"] // 2) < 15 and
                abs(existing.get("rel_y", 0) - el["cy"] // 2) < 15):
                is_new = False
                comp_name = existing_name
                break

        # Crop
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        pad = 4
        y1, x1 = max(0, y-pad), max(0, x-pad)
        y2 = min(img.shape[0], y+h+pad)
        x2 = min(img.shape[1], x+w+pad)
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        # Dedup visual
        is_dup, dup_name = is_duplicate_icon(crop, icons_dir, threshold=0.92)
        if is_dup and is_new:
            dup_count += 1
            continue

        # Save icon
        safe_name = comp_name.replace("/", "-").replace(" ", "_").replace(":", "")[:50]
        icon_path = icons_dir / f"{safe_name}.png"
        cv2.imwrite(str(icon_path), crop)

        rel_x = el["cx"] // 2
        rel_y = el["cy"] // 2

        profile["components"][comp_name] = {
            "type": el["type"], "source": el.get("source", "unknown"),
            "rel_x": rel_x, "rel_y": rel_y,
            "w": el["w"] // 2, "h": el["h"] // 2,
            "icon_file": f"components/{safe_name}.png",
            "label": el.get("label"), "confidence": el.get("confidence", 0),
            "page": page_name, "learned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        page_components.append(comp_name)
        if is_new:
            new_count += 1

    profile["pages"][page_name] = {
        "components": page_components,
        "learned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Save annotated image
    import ui_detector
    ui_detector.annotate_image(img_path, all_elements,
                                str(site_dir / f"pages/{page_name}_annotated.jpg"))

    profile["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    print(f"  💾 Saved {len(page_components)} components ({new_count} new, {dup_count} dups)")
    print(f"  📁 {site_dir}")
    return True


def navigate_browser(app_name, url):
    """Navigate browser to a URL."""
    # Method 1: open command (works for any browser, most reliable)
    subprocess.run(["open", "-a", app_name, url], capture_output=True, timeout=10)
    time.sleep(3)  # Wait for page load
    return True


def auto_cleanup_dynamic(app_name):
    """Remove dynamic content (timestamps, message previews, etc.) after learning.

    RULES (from SKILL.md):
    - Remove: timestamps, message previews, chat text, stickers, notification counts
    - Keep: fixed UI elements (buttons, icons, tabs, navigation)
    """
    profile = load_profile(app_name)
    app_dir = get_app_dir(app_name)
    to_remove = []

    import re

    for name, comp in profile["components"].items():
        label = comp.get("label", "")
        comp_type = comp.get("type", "")
        rel_x = comp.get("rel_x", 0)
        rel_y = comp.get("rel_y", 0)

        is_dynamic = False

        # === TEXT ELEMENTS ===
        if comp_type == "text" and label:
            # Timestamps: HH:MM, dates, Yesterday/Today
            if re.match(r'^\d{1,2}[:/]\d{2}$', label):  # 17:14, 03/10
                is_dynamic = True
            if re.match(r'^\d{2}-\d{2}$', label):  # 03-10
                is_dynamic = True
            if any(x in label for x in ['Yesterday', 'Today', 'Saturday',
                                          'Sunday', 'Monday', 'Tuesday',
                                          'Wednesday', 'Thursday', 'Friday']):
                is_dynamic = True

            # Message previews and chat content
            if any(x in label for x in ['［', '...', '⋯', '•', '[Sticker]',
                                          '[Photo]', '[File]', '[Link]',
                                          '[Voice]', '[Video]', '：']):
                is_dynamic = True

            # Long text in content area = chat messages, NOT UI labels
            # UI labels are short (Search, File, Edit, etc.)
            if len(label) > 15 and rel_x > 100 and rel_y > 80:
                is_dynamic = True

            # Pure numbers (notification counts, message counts)
            if re.match(r'^\d+$', label):
                is_dynamic = True

            # Contact names in chat list area (x=150-400, repeating pattern)
            # These are OCR'd fresh each time, not template-matched
            if 100 < rel_x < 400 and rel_y > 80:
                # In the chat list area — only keep if it looks like a UI label
                # UI labels: "Search", "Q Search", "Hide stickied chats"
                # NOT UI: "ContactA", "GroupChat", "FamilyChat"
                known_ui_labels = {'Search', 'Q Search', 'Hide stickied chats',
                                    'Favorites', 'Contacts', 'Discover'}
                if label not in known_ui_labels and len(label) > 3:
                    is_dynamic = True

        # === ICON ELEMENTS in content area ===
        # Icons in the main chat/content area are likely avatars, stickers, photos
        if comp_type == "icon" and name.startswith("unlabeled_"):
            # Content area icons (not toolbar, not sidebar) are usually avatars
            if rel_x > 100 and rel_y > 80 and rel_y < 550:
                # Check size: avatars are typically 30-50px, UI icons are 15-25px
                w = comp.get("w", 0)
                h = comp.get("h", 0)
                if w > 30 and h > 30:  # likely avatar, not UI icon
                    is_dynamic = True

        if is_dynamic:
            to_remove.append(name)

    # Remove
    for name in to_remove:
        comp = profile["components"].pop(name, None)
        if comp:
            icon_path = app_dir / comp.get("icon_file", "")
            if icon_path.exists():
                icon_path.unlink()

    if to_remove:
        save_profile(app_name, profile)

    return len(to_remove)


# ═══════════════════════════════════════════
# Detect: run detection with memory matching
# ═══════════════════════════════════════════

def detect_with_memory(app_name, threshold=0.8):
    """Detect elements, match against memory, report new/known.
    
    State-aware version: identifies current state and only matches state-specific components.

    Returns: (known_matches, unknown_elements, img_path)
    """
    sys.path.insert(0, str(SCRIPT_DIR))

    img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
    if not img_path:
        return [], [], None

    img = cv2.imread(img_path)
    
    # Get visible text for state identification
    import ui_detector
    text_elements = ui_detector.detect_text(img_path)
    visible_text = [t.get("label", "") for t in text_elements]
    
    # Identify current state
    current_state, match_ratio = identify_state(app_name, visible_text)
    if current_state:
        print(f"  📊 Identified state: '{current_state}' ({match_ratio:.0%} match)")
        # Get components for this state only
        state_components = get_state_components(app_name, current_state)
        print(f"  🎯 Matching {len(state_components)} state-specific components")
    else:
        print(f"  📊 Could not identify state, matching all components")
        profile = load_profile(app_name)
        state_components = list(profile.get("components", {}).keys())

    # Match only relevant components
    known = []
    for comp_name in state_components:
        found, rx, ry, conf = match_component(app_name, comp_name, img, threshold)
        if found:
            known.append((comp_name, rx, ry, conf))
    
    print(f"  🔗 Matched {len(known)} known components")
    for name, rx, ry, conf in known:
        print(f"    ✅ {name} ({rx},{ry}) conf={conf}")
    
    # Report match rate for this state
    if state_components:
        match_rate = len(known) / len(state_components)
        print(f"  📊 State match rate: {match_rate:.1%} ({len(known)}/{len(state_components)})")

    # Detect new elements
    icon_elements, _, _ = ui_detector.detect_icons(img_path, conf=0.1, iou=0.3)
    all_elements = ui_detector.merge_elements(icon_elements, text_elements)

    # Filter out known (matched) elements
    unknown = []
    for el in all_elements:
        el_rx = el["cx"] // 2
        el_ry = el["cy"] // 2
        is_known = False
        for name, rx, ry, conf in known:
            if abs(el_rx - rx) < 20 and abs(el_ry - ry) < 20:
                is_known = True
                el["matched_name"] = name
                break
        if not is_known:
            unknown.append(el)

    print(f"  ❓ {len(unknown)} unknown elements")

    return known, unknown, img_path


# ═══════════════════════════════════════════
# Click: find component and click it
# ═══════════════════════════════════════════

def click_component(app_name, component_name, verify=True):
    """Find a component by template match and click it.

    Uses relative coordinates + window position = absolute screen coordinates.
    Optionally verifies the target before clicking.

    Returns: (success, message)
    """
    # 0. System component? Use fixed position, no template match needed
    if component_name.startswith("sys_") and component_name in MACOS_SYSTEM_COMPONENTS:
        img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
        if not img_path:
            return False, f"Could not capture {app_name} window"
        sys_comp = MACOS_SYSTEM_COMPONENTS[component_name]
        screen_x = win_x + sys_comp["rel_x"]
        screen_y = win_y + sys_comp["rel_y"]
        print(f"  🎯 System component '{component_name}' → screen({screen_x},{screen_y})")
        subprocess.run(["/opt/homebrew/bin/cliclick", f"c:{screen_x},{screen_y}"],
                       capture_output=True, timeout=5)
        return True, f"Clicked system component {component_name}"

    # 1. Capture window
    img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
    if not img_path:
        return False, f"Could not capture {app_name} window"

    img = cv2.imread(img_path)

    # 2. Template match
    found, rel_x, rel_y, conf = match_component(app_name, component_name, img)

    if not found:
        return False, f"Component '{component_name}' not found (no template match)"

    # 3. Convert to screen coordinates
    screen_x = win_x + rel_x
    screen_y = win_y + rel_y

    print(f"  🎯 Found '{component_name}' at rel({rel_x},{rel_y}) → screen({screen_x},{screen_y}) conf={conf}")

    # 4. Verify (optional): check that the click target is reasonable
    if verify:
        # Check within window bounds
        if not (0 <= rel_x <= win_w and 0 <= rel_y <= win_h):
            return False, f"Component position ({rel_x},{rel_y}) outside window bounds ({win_w}x{win_h})"

        # Check confidence
        if conf < 0.7:
            return False, f"Low confidence ({conf}), not clicking"

    # 5. Click
    subprocess.run(["/opt/homebrew/bin/cliclick", f"c:{screen_x},{screen_y}"], check=True)
    return True, f"Clicked '{component_name}' at ({screen_x},{screen_y}) conf={conf}"


# ═══════════════════════════════════════════
# Verify: pre-action safety checks
# ═══════════════════════════════════════════

def verify_before_send(app_name, expected_contact, message):
    """Verify correct contact is open before sending a message.

    Returns: (safe_to_send, reason)
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    import ui_detector

    img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
    if not img_path:
        return False, "Could not capture window"

    # OCR the header area to find contact name
    text_elements = ui_detector.detect_text(img_path)

    # Look for the expected contact name in the detected text
    for el in text_elements:
        if expected_contact.lower() in el.get("label", "").lower():
            return True, f"Verified: '{expected_contact}' found in UI"

    # Not found
    visible_texts = [el.get("label", "") for el in text_elements[:10]]
    return False, f"Contact '{expected_contact}' not found. Visible: {visible_texts[:5]}"


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="App Visual Memory")
    sub = parser.add_subparsers(dest="command", required=True)

    # learn
    p_learn = sub.add_parser("learn", help="Learn all components of an app")
    p_learn.add_argument("--app", required=True)
    p_learn.add_argument("--page", default="main")

    # find
    p_find = sub.add_parser("find", help="Find a component by template match")
    p_find.add_argument("--app", required=True)
    p_find.add_argument("--component", required=True)

    # click
    p_click = sub.add_parser("click", help="Find and click a component")
    p_click.add_argument("--app", required=True)
    p_click.add_argument("--component", required=True)
    p_click.add_argument("--no-verify", action="store_true")

    # detect
    p_detect = sub.add_parser("detect", help="Detect with memory matching")
    p_detect.add_argument("--app", required=True)

    # list
    p_list = sub.add_parser("list", help="List known components")
    p_list.add_argument("--app", required=True)

    # rename
    p_rename = sub.add_parser("rename", help="Rename a component (after LLM identifies it)")
    p_rename.add_argument("--app", required=True)
    p_rename.add_argument("--old", required=True, help="Current component name")
    p_rename.add_argument("--new", required=True, help="New descriptive name")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a component (e.g. privacy-sensitive)")
    p_delete.add_argument("--app", required=True)
    p_delete.add_argument("--component", required=True, help="Component name to delete")

    # cleanup
    p_cleanup = sub.add_parser("cleanup", help="Remove duplicate and unimportant components")
    p_cleanup.add_argument("--app", required=True)
    p_cleanup.add_argument("--threshold", type=float, default=0.92, help="Similarity threshold for dedup")

    # learn_site
    p_site = sub.add_parser("learn_site", help="Learn current website in browser")
    p_site.add_argument("--app", default="Google Chrome")
    p_site.add_argument("--page", default="main")

    # navigate
    p_nav = sub.add_parser("navigate", help="Navigate browser to URL")
    p_nav.add_argument("--app", default="Google Chrome")
    p_nav.add_argument("--url", required=True)

    # verify
    p_verify = sub.add_parser("verify", help="Verify contact before sending")
    p_verify.add_argument("--app", required=True)
    p_verify.add_argument("--contact", required=True)

    args = parser.parse_args()

    if args.command == "learn":
        learn_app(args.app, args.page)

    elif args.command == "find":
        img_path, wx, wy, ww, wh = capture_window(args.app)
        if img_path:
            img = cv2.imread(img_path)
            found, rx, ry, conf = match_component(args.app, args.component, img)
            if found:
                print(json.dumps({"found": True, "rel_x": rx, "rel_y": ry,
                                  "screen_x": wx + rx, "screen_y": wy + ry,
                                  "confidence": conf}))
            else:
                print(json.dumps({"found": False, "component": args.component}))

    elif args.command == "click":
        ok, msg = click_component(args.app, args.component, verify=not args.no_verify)
        print(f"{'✅' if ok else '❌'} {msg}")

    elif args.command == "detect":
        known, unknown, img_path = detect_with_memory(args.app)
        print(f"\nKnown: {len(known)}, Unknown: {len(unknown)}")

    elif args.command == "list":
        profile = load_profile(args.app)
        comps = profile["components"]
        print(f"App: {args.app} ({len(comps)} components)")
        for name, data in sorted(comps.items(), key=lambda x: (x[1].get("rel_y", 0), x[1].get("rel_x", 0))):
            label = data.get("label", "")
            pos = f"({data.get('rel_x', '?')},{data.get('rel_y', '?')})"
            print(f"  {name:30s} {pos:12s} {data['type']:8s} {label}")

    elif args.command == "rename":
        profile = load_profile(args.app)
        if args.old not in profile["components"]:
            print(f"❌ Component '{args.old}' not found")
        else:
            comp = profile["components"].pop(args.old)
            app_dir = get_app_dir(args.app)

            # Rename icon file
            old_icon = app_dir / comp["icon_file"]
            safe_new = args.new.replace("/", "-").replace(" ", "_").replace(":", "")[:50]
            new_icon = app_dir / "components" / f"{safe_new}.png"
            if old_icon.exists():
                old_icon.rename(new_icon)
                comp["icon_file"] = f"components/{safe_new}.png"

            comp["label"] = args.new
            profile["components"][safe_new] = comp

            # Update state references
            for state_data in profile.get("states", {}).values():
                for key in ["visible", "disappeared"]:
                    if args.old in state_data.get(key, []):
                        lst = state_data[key]
                        lst[lst.index(args.old)] = safe_new

            save_profile(args.app, profile)
            print(f"✅ Renamed '{args.old}' → '{safe_new}'")

    elif args.command == "delete":
        profile = load_profile(args.app)
        comp_name = args.component
        if comp_name not in profile["components"]:
            print(f"❌ Component '{comp_name}' not found")
        else:
            comp = profile["components"].pop(comp_name)
            app_dir = get_app_dir(args.app)
            # Delete icon file
            icon_path = app_dir / comp.get("icon_file", f"components/{comp_name}.png")
            if icon_path.exists():
                icon_path.unlink()
            # Remove from state references
            for state_data in profile.get("states", {}).values():
                for key in ["visible", "disappeared"]:
                    if comp_name in state_data.get(key, []):
                        state_data[key].remove(comp_name)
            save_profile(args.app, profile)
            print(f"🗑 Deleted '{comp_name}'")

    elif args.command == "cleanup":
        profile = load_profile(args.app)
        app_dir = get_app_dir(args.app)
        icons_dir = app_dir / "components"

        # Find duplicates
        items = list(profile["components"].items())
        to_remove = set()
        for i in range(len(items)):
            if items[i][0] in to_remove:
                continue
            path_i = app_dir / items[i][1].get("icon_file", "")
            if not path_i.exists():
                continue
            img_i = cv2.imread(str(path_i))
            if img_i is None:
                continue
            for j in range(i + 1, len(items)):
                if items[j][0] in to_remove:
                    continue
                path_j = app_dir / items[j][1].get("icon_file", "")
                if not path_j.exists():
                    continue
                img_j = cv2.imread(str(path_j))
                if img_j is None:
                    continue
                is_dup, _ = is_duplicate_icon(img_i, Path("/dev/null"))  # skip
                # Direct comparison
                h1, w1 = img_i.shape[:2]
                h2, w2 = img_j.shape[:2]
                if abs(h1 - h2) < 5 and abs(w1 - w2) < 5:
                    target_h, target_w = min(h1, h2), min(w1, w2)
                    if target_h >= 5 and target_w >= 5:
                        r1 = cv2.resize(cv2.cvtColor(img_i, cv2.COLOR_BGR2GRAY), (target_w, target_h))
                        r2 = cv2.resize(cv2.cvtColor(img_j, cv2.COLOR_BGR2GRAY), (target_w, target_h))
                        sim = cv2.matchTemplate(r1, r2, cv2.TM_CCOEFF_NORMED)[0][0]
                        if sim > args.threshold:
                            # Keep the one with a label
                            if items[j][1].get("label") and not items[i][1].get("label"):
                                to_remove.add(items[i][0])
                            else:
                                to_remove.add(items[j][0])

        # Remove duplicates
        for name in to_remove:
            comp = profile["components"].pop(name, None)
            if comp:
                icon_path = app_dir / comp.get("icon_file", "")
                if icon_path.exists():
                    icon_path.unlink()
            print(f"  🗑 Removed duplicate: {name}")

        save_profile(args.app, profile)
        print(f"✅ Cleaned {len(to_remove)} duplicates, {len(profile['components'])} remaining")

    elif args.command == "learn_site":
        learn_site(args.app, args.page)

    elif args.command == "navigate":
        navigate_browser(args.app, args.url)
        print(f"✅ Navigated to {args.url}")

    elif args.command == "verify":
        ok, reason = verify_before_send(args.app, args.contact, "")
        print(f"{'✅' if ok else '❌'} {reason}")


if __name__ == "__main__":
    main()
