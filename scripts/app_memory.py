#!/usr/bin/env python3
"""
App Visual Memory — per-app component memory with template matching.

Architecture:
- LEARN on app window crop (focused detection, less noise)
- MATCH on full screen (no coordinate conversion needed)
- Templates from window crops match full screen because both use
  the same screencapture pixel scaling (full screenshot + crop).

Each app gets:
- profile.json: window structure, known pages, component registry
- components/: cropped component images (named by content/function)
- pages/: page-specific layouts

Storage policy: only clean up temporary/dynamic content (timestamps,
chat messages, notification counts) to prevent storage bloat.
No privacy filtering — data stays local, never uploaded.

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

# Default forget threshold: a component must be missed this many consecutive
# times before being considered stale and eligible for removal.
DEFAULT_FORGET_THRESHOLD = 15

# ═══════════════════════════════════════════
# Split storage: meta / components / states / transitions
# ═══════════════════════════════════════════

def load_meta(app_dir):
    """Load meta.json from app/site directory. Returns dict with defaults."""
    meta_path = Path(app_dir) / "meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)
    return {
        "app": "",
        "domain": "",
        "detect_count": 0,
        "last_updated": None,
        "img_size": None,
        "forget_threshold": DEFAULT_FORGET_THRESHOLD,
    }


def save_meta(app_dir, meta):
    """Save meta.json to app/site directory."""
    meta_path = Path(app_dir) / "meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def load_components(app_dir):
    """Load components.json from app/site directory. Returns dict."""
    comp_path = Path(app_dir) / "components.json"
    if comp_path.exists():
        with open(comp_path) as f:
            return json.load(f)
    return {}


def save_components(app_dir, components):
    """Save components.json to app/site directory."""
    comp_path = Path(app_dir) / "components.json"
    with open(comp_path, "w") as f:
        json.dump(components, f, indent=2, ensure_ascii=False)


def load_states(app_dir):
    """Load states.json from app/site directory. Returns dict."""
    states_path = Path(app_dir) / "states.json"
    if states_path.exists():
        with open(states_path) as f:
            return json.load(f)
    return {}


def save_states(app_dir, states):
    """Save states.json to app/site directory."""
    states_path = Path(app_dir) / "states.json"
    with open(states_path, "w") as f:
        json.dump(states, f, indent=2, ensure_ascii=False)


def load_transitions(app_dir):
    """Load transitions.json from app/site directory. Returns dict (key=from|action|to)."""
    trans_path = Path(app_dir) / "transitions.json"
    if trans_path.exists():
        with open(trans_path) as f:
            return json.load(f)
    return {}


def save_transitions(app_dir, transitions):
    """Save transitions.json to app/site directory."""
    trans_path = Path(app_dir) / "transitions.json"
    with open(trans_path, "w") as f:
        json.dump(transitions, f, indent=2, ensure_ascii=False)


def migrate_profile_if_needed(app_dir):
    """Migrate old profile.json to split files (meta/components/states/transitions).

    - Detects old profile.json
    - Splits into 4 independent JSON files
    - Adds activity tracking fields to each component
    - Converts transitions list to dict (keyed by from|action|to)
    - Renames old file to profile.json.bak
    """
    app_dir = Path(app_dir)
    profile_path = app_dir / "profile.json"
    if not profile_path.exists():
        return  # Nothing to migrate

    # Don't re-migrate if new files already exist
    if (app_dir / "meta.json").exists():
        return

    with open(profile_path) as f:
        profile = json.load(f)

    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # --- meta.json ---
    meta = {
        "app": profile.get("app", ""),
        "domain": profile.get("domain", ""),
        "detect_count": 0,
        "last_updated": profile.get("last_updated", now),
        "img_size": profile.get("img_size") or profile.get("retina_img_size"),
        "forget_threshold": DEFAULT_FORGET_THRESHOLD,
    }
    # Carry over window_size if present
    if profile.get("window_size"):
        meta["window_size"] = profile["window_size"]
    if profile.get("url"):
        meta["url"] = profile["url"]
    if profile.get("pages"):
        meta["pages"] = profile["pages"]
    save_meta(app_dir, meta)

    # --- components.json (add activity fields) ---
    components = profile.get("components", {})
    for comp_name, comp_data in components.items():
        learned_at = comp_data.get("learned_at", now)
        comp_data.setdefault("last_seen", learned_at)
        comp_data.setdefault("seen_count", 1)
        comp_data.setdefault("consecutive_misses", 0)
    save_components(app_dir, components)

    # --- states.json ---
    states = profile.get("states", {})
    save_states(app_dir, states)

    # --- transitions.json (convert list → dict) ---
    old_transitions = profile.get("transitions", [])
    new_transitions = {}
    for t in old_transitions:
        from_s = t.get("from", "")
        action = f"click:{t.get('click', '')}" if t.get("click") else t.get("action", "")
        to_s = t.get("to", "")
        key = f"{from_s}|{action}|{to_s}"
        if key in new_transitions:
            new_transitions[key]["count"] = new_transitions[key].get("count", 1) + t.get("count", 1)
            new_transitions[key]["last_used"] = t.get("timestamp", now)
        else:
            new_transitions[key] = {
                "from_state": from_s,
                "action": action,
                "to_state": to_s,
                "count": t.get("count", 1),
                "last_used": t.get("timestamp", now),
                "success_rate": 1.0,
            }
            # Carry over extra fields
            if t.get("click_pos"):
                new_transitions[key]["click_pos"] = t["click_pos"]
    save_transitions(app_dir, new_transitions)

    # Rename old profile.json → profile.json.bak
    bak_path = app_dir / "profile.json.bak"
    profile_path.rename(bak_path)
    print(f"  📦 Migrated {profile_path} → split files (meta/components/states/transitions)")


# ═══════════════════════════════════════════
# Component activity tracking & forgetting (Phase 2)
# ═══════════════════════════════════════════

def update_component_activity(components, detected_names, now=None):
    """Update component activity based on detection results.

    For each component in the registry:
    - If detected this round: last_seen=now, seen_count+=1, consecutive_misses=0
    - If NOT detected: consecutive_misses+=1

    Args:
        components: dict of component_name -> component_data
        detected_names: set of component names detected in this round
        now: timestamp string (default: current time)

    Returns: updated components dict
    """
    if now is None:
        now = time.strftime("%Y-%m-%d %H:%M:%S")

    for comp_name, comp_data in components.items():
        if comp_name in detected_names:
            comp_data["last_seen"] = now
            comp_data["seen_count"] = comp_data.get("seen_count", 0) + 1
            comp_data["consecutive_misses"] = 0
        else:
            comp_data["consecutive_misses"] = comp_data.get("consecutive_misses", 0) + 1

    return components


def forget_stale_components(app_dir, components, meta, states, transitions):
    """Remove components that haven't been seen for too long.

    Only runs when detect_count > forget_threshold (avoids early false removals).

    For each stale component (consecutive_misses >= forget_threshold):
    - Delete its icon image file
    - Remove from states' defining_components
    - If a state's defining_components becomes empty → delete the state
    - If a transition references a deleted state → delete the transition

    Args:
        app_dir: Path to app/site directory
        components: components dict
        meta: meta dict
        states: states dict
        transitions: transitions dict (keyed by from|action|to)

    Returns: (components, states, transitions) — all updated
    """
    threshold = meta.get("forget_threshold", DEFAULT_FORGET_THRESHOLD)
    detect_count = meta.get("detect_count", 0)

    # Don't forget too early — need enough data first
    if detect_count <= threshold:
        return components, states, transitions

    app_dir = Path(app_dir)
    stale_names = set()

    for comp_name, comp_data in list(components.items()):
        if comp_data.get("consecutive_misses", 0) >= threshold:
            stale_names.add(comp_name)

    if not stale_names:
        return components, states, transitions

    # Remove stale components
    for comp_name in stale_names:
        comp_data = components.pop(comp_name, None)
        if comp_data:
            # Delete icon file
            icon_file = comp_data.get("icon_file", "")
            if icon_file:
                icon_path = app_dir / icon_file
                if icon_path.exists():
                    icon_path.unlink()

    # Clean up states
    deleted_states = set()
    for state_id, state_data in list(states.items()):
        defining = state_data.get("defining_components", [])
        if defining:
            cleaned = [c for c in defining if c not in stale_names]
            if not cleaned:
                deleted_states.add(state_id)
                del states[state_id]
            else:
                state_data["defining_components"] = cleaned

        # Also clean up "visible" lists if present
        visible = state_data.get("visible", [])
        if visible:
            state_data["visible"] = [v for v in visible if v not in stale_names]

    # Clean up transitions referencing deleted states
    for key in list(transitions.keys()):
        t = transitions[key]
        if t.get("from_state") in deleted_states or t.get("to_state") in deleted_states:
            del transitions[key]

    if stale_names:
        print(f"  🧹 Forgot {len(stale_names)} stale components: {', '.join(sorted(stale_names)[:5])}")
        if deleted_states:
            print(f"  🧹 Removed {len(deleted_states)} empty states")

    return components, states, transitions


# ═══════════════════════════════════════════
# State identification by components (Phase 3)
# ═══════════════════════════════════════════

def _jaccard(set_a, set_b):
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def identify_or_create_state(states, detected_components, components_data, description=None):
    """Match detected components against known states, or create a new one.

    1. Filter detected components to stable ones (seen_count >= 2).
    2. Compare stable_set against each state's defining_components via Jaccard.
    3. If best Jaccard > 0.7 → match that state, update visit_count & last_seen.
    4. Otherwise → create a new state with ID = s_ + 6-char hex hash.

    Args:
        states: states dict
        detected_components: set of component names detected this round
        components_data: full components dict (for checking seen_count)
        description: optional description for new states

    Returns: (state_id, updated_states_dict)
    """
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # Filter to stable components (seen at least twice)
    stable_set = set()
    for name in detected_components:
        comp = components_data.get(name, {})
        if comp.get("seen_count", 0) >= 2:
            stable_set.add(name)

    if not stable_set:
        # No stable components yet — skip state identification
        return None, states

    # Find best matching state
    best_state_id = None
    best_jaccard = 0.0

    for state_id, state_data in states.items():
        defining = set(state_data.get("defining_components", []))
        if not defining:
            continue
        j = _jaccard(stable_set, defining)
        if j > best_jaccard:
            best_jaccard = j
            best_state_id = state_id

    if best_jaccard > 0.7 and best_state_id:
        # Match — update existing state
        states[best_state_id]["last_seen"] = now
        states[best_state_id]["visit_count"] = states[best_state_id].get("visit_count", 0) + 1
        return best_state_id, states

    # No match — create new state
    import hashlib
    hash_input = "|".join(sorted(stable_set))
    state_hash = hashlib.md5(hash_input.encode()).hexdigest()[:6]
    new_id = f"s_{state_hash}"

    # Avoid collision
    while new_id in states:
        state_hash = hashlib.md5((hash_input + new_id).encode()).hexdigest()[:6]
        new_id = f"s_{state_hash}"

    states[new_id] = {
        "name": description or f"state_{state_hash}",
        "description": description,
        "defining_components": sorted(stable_set),
        "first_seen": now,
        "last_seen": now,
        "visit_count": 1,
    }

    return new_id, states


def identify_current_state(states, detected_components, components_data):
    """Identify which known state matches the detected components.

    Pure identification — does NOT create new states (unlike identify_or_create_state).
    Uses Jaccard similarity with defining_components.
    Filters to stable components (seen_count >= 2).

    Args:
        states: states dict from states.json
        detected_components: set of component names detected
        components_data: full components dict (for seen_count check)

    Returns:
        (state_id, jaccard_score) or (None, 0.0)
    """
    # Filter to stable components (seen at least twice)
    stable_set = set()
    for name in detected_components:
        comp = components_data.get(name, {})
        if comp.get("seen_count", 0) >= 2:
            stable_set.add(name)

    if not stable_set:
        return None, 0.0

    best_state_id = None
    best_jaccard = 0.0

    for state_id, state_data in states.items():
        defining = set(state_data.get("defining_components", []))
        if not defining:
            continue
        j = _jaccard(stable_set, defining)
        if j > best_jaccard:
            best_jaccard = j
            best_state_id = state_id

    if best_jaccard > 0.7 and best_state_id:
        return best_state_id, best_jaccard

    return None, 0.0


def quick_template_check(app_dir, component_names, img=None):
    """Only check if specified components are visible on screen.

    Faster than match_all_components — only matches the needed templates.

    Args:
        app_dir: Path to app/site directory
        component_names: list of component names to check
        img: pre-loaded screenshot (None = auto capture on Mac)

    Returns:
        (matched_names: set, total: int, ratio: float)
    """
    app_dir = Path(app_dir)
    components = load_components(app_dir)

    if not component_names:
        return set(), 0, 0.0

    # Auto-capture screenshot if not provided
    if img is None:
        import platform
        if platform.system() == "Darwin":
            screen_path = "/tmp/gui_agent_quick_check.png"
            subprocess.run(["screencapture", "-x", screen_path],
                           capture_output=True, timeout=5)
            img = cv2.imread(screen_path)
        if img is None:
            return set(), len(component_names), 0.0

    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    matched = set()

    for comp_name in component_names:
        comp_data = components.get(comp_name)
        if not comp_data or not comp_data.get("icon_file"):
            continue

        template_path = app_dir / comp_data["icon_file"]
        if not template_path.exists():
            continue

        template = cv2.imread(str(template_path))
        if template is None:
            continue

        gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        if (gray_tpl.shape[0] > gray_img.shape[0] or
                gray_tpl.shape[1] > gray_img.shape[1]):
            continue

        try:
            result = cv2.matchTemplate(gray_img, gray_tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= 0.8:
                matched.add(comp_name)
        except Exception:
            continue

    total = len(component_names)
    ratio = len(matched) / total if total > 0 else 0.0
    _tracker_auto_tick("workflow_level0")
    return matched, total, ratio


def load_workflows(app_dir):
    """Load workflows.json from app/site directory. Returns dict."""
    wf_path = Path(app_dir) / "workflows.json"
    if wf_path.exists():
        with open(wf_path) as f:
            return json.load(f)
    return {}


def save_workflows(app_dir, workflows):
    """Save workflows.json to app/site directory."""
    wf_path = Path(app_dir) / "workflows.json"
    with open(wf_path, "w") as f:
        json.dump(workflows, f, indent=2, ensure_ascii=False)


def merge_similar_states(states, transitions, threshold=0.85):
    """Merge states with highly similar defining_components.

    For each pair of states with Jaccard > threshold:
    - Keep the state with higher visit_count
    - Merge defining_components (union)
    - Update all transition references from merged state to kept state
    - Delete merged state

    Args:
        states: states dict
        transitions: transitions dict (keyed by from|action|to)
        threshold: Jaccard threshold for merging (default 0.85)

    Returns: (states, transitions)
    """
    merged_any = True
    while merged_any:
        merged_any = False
        state_ids = list(states.keys())
        for i in range(len(state_ids)):
            if state_ids[i] not in states:
                continue
            for j in range(i + 1, len(state_ids)):
                if state_ids[j] not in states:
                    continue
                s1 = states[state_ids[i]]
                s2 = states[state_ids[j]]
                set1 = set(s1.get("defining_components", []))
                set2 = set(s2.get("defining_components", []))
                if not set1 or not set2:
                    continue
                j_sim = _jaccard(set1, set2)
                if j_sim > threshold:
                    # Merge: keep higher visit_count
                    keep_id = state_ids[i] if s1.get("visit_count", 0) >= s2.get("visit_count", 0) else state_ids[j]
                    remove_id = state_ids[j] if keep_id == state_ids[i] else state_ids[i]
                    
                    # Merge defining_components (union)
                    states[keep_id]["defining_components"] = sorted(set1 | set2)
                    states[keep_id]["visit_count"] = (
                        states[keep_id].get("visit_count", 0) + states[remove_id].get("visit_count", 0)
                    )
                    
                    # Update transition references
                    new_transitions = {}
                    for key, t in transitions.items():
                        from_s = t["from_state"]
                        to_s = t["to_state"]
                        if from_s == remove_id:
                            from_s = keep_id
                        if to_s == remove_id:
                            to_s = keep_id
                        new_key = f"{from_s}|{t['action']}|{to_s}"
                        if new_key in new_transitions:
                            # Merge counts
                            new_transitions[new_key]["count"] += t.get("count", 1)
                            if t.get("last_used", "") > new_transitions[new_key].get("last_used", ""):
                                new_transitions[new_key]["last_used"] = t["last_used"]
                        else:
                            new_transitions[new_key] = {
                                "from_state": from_s,
                                "action": t["action"],
                                "to_state": to_s,
                                "count": t.get("count", 1),
                                "last_used": t.get("last_used"),
                                "success_rate": t.get("success_rate", 1.0),
                            }
                    transitions = new_transitions
                    
                    # Remove merged state
                    del states[remove_id]
                    merged_any = True
                    print(f"  🔗 Merged state '{remove_id}' into '{keep_id}' (Jaccard={j_sim:.2f})")
                    break  # restart inner loop
            if merged_any:
                break  # restart outer loop

    return states, transitions


# Tracker integration (auto-tick operations when tracker is active)
_TRACKER_STATE = SKILL_DIR / "skills" / "gui-report" / "scripts" / ".tracker_state.json"

def _tracker_auto_tick(counter, n=1):
    """Auto-tick tracker counter. Auto-starts tracker if not running."""
    try:
        tracker_scripts = str(SKILL_DIR / "skills" / "gui-report" / "scripts")
        if tracker_scripts not in sys.path:
            sys.path.insert(0, tracker_scripts)
        from tracker import tick_counter, STATE_FILE
        # Auto-start tracker if not running
        if not STATE_FILE.exists():
            _tracker_auto_start()
        tick_counter(counter, n)
    except Exception:
        pass  # Never fail — tracking is best-effort


def _tracker_auto_start():
    """Auto-start tracker on first detection call.

    Task name starts as 'auto', updated by learn_from_screenshot
    with app_name + domain on first call.
    """
    try:
        tracker_scripts = str(SKILL_DIR / "skills" / "gui-report" / "scripts")
        if tracker_scripts not in sys.path:
            sys.path.insert(0, tracker_scripts)
        from tracker import _read_tokens, STATE_FILE, COUNTERS
        import json as _json
        tokens = _read_tokens()
        state = {
            "task": "auto",
            "start_time": time.time(),
            "session_key": tokens["sessionKey"] if tokens else None,
            "tokens_start": tokens,
            "notes": [],
        }
        # Initialize all counters to 0
        for c in COUNTERS:
            state[c] = 0
        with open(STATE_FILE, "w") as f:
            _json.dump(state, f)
    except Exception:
        pass


def _tracker_update_task(name):
    """Update tracker task name. Called by learn_from_screenshot."""
    try:
        tracker_scripts = str(SKILL_DIR / "skills" / "gui-report" / "scripts")
        if tracker_scripts not in sys.path:
            sys.path.insert(0, tracker_scripts)
        from tracker import update_task_name
        update_task_name(name)
    except Exception:
        pass


def task_report(task_name=None):
    """Print final task report. Call once at end of task.
    
    Fully automatic — reads token usage from sessions.json,
    operation counts from auto-ticked tracker state.
    No LLM involvement needed.
    
    Args:
        task_name: Override the auto-generated task name
    """
    try:
        tracker_scripts = str(SKILL_DIR / "skills" / "gui-report" / "scripts")
        if tracker_scripts not in sys.path:
            sys.path.insert(0, tracker_scripts)
        from tracker import STATE_FILE, _read_tokens, _fmt, LOG_DIR, LOG_FILE, COUNTERS
        import json as _json

        if not STATE_FILE.exists():
            print("⚠ No task data to report.")
            return

        with open(STATE_FILE) as f:
            state = _json.load(f)

        if task_name:
            state["task"] = task_name

        elapsed = time.time() - state["start_time"]
        tokens_now = _read_tokens(state.get("session_key"))
        tokens_start = state.get("tokens_start", {})

        total_start = tokens_start.get("totalTokens", 0) if tokens_start else 0
        total_end = tokens_now.get("totalTokens", 0) if tokens_now else 0
        token_delta = total_end - total_start

        input_start = tokens_start.get("inputTokens", 0) if tokens_start else 0
        input_end = tokens_now.get("inputTokens", 0) if tokens_now else 0
        output_start = tokens_start.get("outputTokens", 0) if tokens_start else 0
        output_end = tokens_now.get("outputTokens", 0) if tokens_now else 0
        cache_start = tokens_start.get("cacheRead", 0) if tokens_start else 0
        cache_end = tokens_now.get("cacheRead", 0) if tokens_now else 0

        time_str = f"{elapsed:.1f}s" if elapsed < 60 else (f"{elapsed/60:.1f}min" if elapsed < 3600 else f"{elapsed/3600:.1f}h")

        ops = []
        for key in COUNTERS:
            v = state.get(key, 0)
            if v > 0:
                ops.append(f"{v}×{key}")

        print("=" * 60)
        print(f"📊 GUI Task Report: {state['task']}")
        print("=" * 60)
        print(f"⏱  Duration:    {time_str}")
        print(f"🪙 Tokens:      {_fmt(total_start)} → {_fmt(total_end)} (+{_fmt(token_delta)})")
        print(f"   Input:       +{_fmt(input_end - input_start)}")
        print(f"   Output:      +{_fmt(output_end - output_start)}")
        print(f"   Cache read:  +{_fmt(cache_end - cache_start)}")
        print(f"🔧 Operations:  {', '.join(ops) if ops else 'none'}")
        print("=" * 60)

        # Save to log
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "task": state["task"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": round(elapsed, 1),
            "tokens_start": total_start, "tokens_end": total_end,
            "tokens_delta": token_delta,
            "input_delta": input_end - input_start,
            "output_delta": output_end - output_start,
            "cache_read_delta": cache_end - cache_start,
            "operations": {k: state.get(k, 0) for k in COUNTERS},
        }
        with open(LOG_FILE, "a") as f:
            f.write(_json.dumps(log_entry) + "\n")

        STATE_FILE.unlink(missing_ok=True)
        return log_entry

    except Exception as e:
        print(f"⚠ Report failed: {e}")
        return None

def _tracker_tick(counter, n=1):
    """Increment a tracker counter if tracker is active. No-op otherwise."""
    try:
        if not _TRACKER_STATE.exists():
            return
        with open(_TRACKER_STATE) as f:
            state = json.load(f)
        state[counter] = state.get(counter, 0) + n
        with open(_TRACKER_STATE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass  # Never break main flow for tracking


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
    """Capture app window by cropping from full-screen screenshot.

    Used for LEARNING: crops the app window to focus detection on app UI only.
    Templates saved from this crop will be matched on FULL SCREEN later.
    This works because full-screen screenshot + crop gives identical pixel
    scaling to the full-screen screenshot used during matching.

    Returns: (img_path, win_x, win_y, win_w, win_h) in logical coords.
    """
    from platform_input import activate_app
    activate_app(app_name)

    bounds = get_window_bounds(app_name)
    if not bounds:
        return None, 0, 0, 0, 0

    win_x, win_y, win_w, win_h = bounds

    if out_path is None:
        out_path = f"/tmp/app_memory_{app_name.lower()}.png"

    # Always: full screenshot + crop (consistent pixel scaling)
    subprocess.run(["/usr/sbin/screencapture", "-x", "/tmp/_full.png"],
                   check=True, timeout=5)
    img = cv2.imread("/tmp/_full.png")
    # Convert click-space window bounds to detection-space for cropping
    from ui_detector import click_to_detect
    rx, ry = click_to_detect(win_x, win_y)
    rw, rh = click_to_detect(win_w, win_h)
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
    """Load app profile from split files (meta/components/states/transitions).

    Automatically migrates old profile.json if found.
    Returns a backwards-compatible dict with components, states, transitions.
    """
    app_dir = get_app_dir(app_name)

    # Auto-migrate old format
    migrate_profile_if_needed(app_dir)

    meta = load_meta(app_dir)
    components = load_components(app_dir)
    states = load_states(app_dir)
    transitions_dict = load_transitions(app_dir)

    # Build compatible dict
    profile = {
        "app": meta.get("app", app_name),
        "components": components,
        "states": states,
        "transitions": transitions_dict,  # Now a dict, not a list
        "last_updated": meta.get("last_updated"),
        "window_size": meta.get("window_size"),
    }
    # Carry over extra meta fields for backwards compat
    if meta.get("domain"):
        profile["domain"] = meta["domain"]
    if meta.get("img_size"):
        profile["img_size"] = meta["img_size"]
    if meta.get("retina_img_size"):
        profile["retina_img_size"] = meta["retina_img_size"]
    if meta.get("url"):
        profile["url"] = meta["url"]
    if meta.get("pages"):
        profile["pages"] = meta["pages"]

    return profile


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
    """Check if element overlaps with macOS traffic light buttons.
    
    Coordinates are in logical (pynput) space (from detect_all).
    """
    rel_x = el.get("cx", 0)
    rel_y = el.get("cy", 0)
    # Traffic lights are at top-left, roughly x < 70, y < 30
    return rel_x < 70 and rel_y < 30


def should_save_component(el, win_w, win_h):
    """Decide whether to save a detected component.

    Goal: prevent storage bloat by filtering out temporary/dynamic content.
    We keep all generic UI components (buttons, icons, tabs, nav).
    We skip things that change every session (timestamps, chat messages, etc.).

    Rules for what to save (stable UI):
    - Sidebar elements (left region)
    - Toolbar elements (top region)
    - Header/Footer elements
    - Elements with OCR text labels (UI labels)

    Rules for what to SKIP (temporary content that causes storage bloat):
    - Tiny elements (< 25x25 retina px)
    - macOS traffic light buttons (system-level, handled separately)

    Returns: (should_save, reason)
    """
    # Skip macOS traffic light buttons (close/minimize/fullscreen)
    if _is_traffic_light(el, win_w, win_h):
        return False, "traffic_light"

    # Skip tiny elements
    w, h = el.get("w", 0), el.get("h", 0)
    if w < 25 or h < 25:
        return False, "too_small"

    # Get position (already in logical pixels from detect_all)
    cx, cy = el.get("cx", 0), el.get("cy", 0)
    rel_x = cx
    rel_y = cy

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
        # Support both new format (defining_components) and old format (visible)
        state_visible = set(state_data.get("defining_components", []) or state_data.get("visible", []))
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
    """Save app profile to split files (meta/components/states/transitions).

    Accepts the same dict structure as before but writes to independent files.
    """
    app_dir = get_app_dir(app_name)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    profile["last_updated"] = now

    # --- meta.json ---
    meta = load_meta(app_dir)
    meta["app"] = profile.get("app", app_name)
    meta["last_updated"] = now
    if profile.get("domain"):
        meta["domain"] = profile["domain"]
    if profile.get("img_size"):
        meta["img_size"] = profile["img_size"]
    if profile.get("retina_img_size"):
        meta["retina_img_size"] = profile["retina_img_size"]
    if profile.get("window_size"):
        meta["window_size"] = profile["window_size"]
    if profile.get("url"):
        meta["url"] = profile["url"]
    if profile.get("pages"):
        meta["pages"] = profile["pages"]
    save_meta(app_dir, meta)

    # --- components.json ---
    save_components(app_dir, profile.get("components", {}))

    # --- states.json ---
    save_states(app_dir, profile.get("states", {}))

    # --- transitions.json ---
    save_transitions(app_dir, profile.get("transitions", {}))


def identify_state_by_components(app_name, visible_components):
    """Identify current state by matching visible component names against known states.
    
    Uses F1 score (harmonic mean of precision and recall) to avoid matching
    a small state that happens to be a subset of the current screen.
    
    - Precision: what % of state's components are visible (recall of state)
    - Recall: what % of visible components are in the state (precision of visible)
    - F1 balances both — prefers states that closely match current screen
    
    Args:
        app_name: App name
        visible_components: set of component names currently visible
        
    Returns:
        (state_name, f1_score) or (None, 0)
    """
    profile = load_profile(app_name)
    states = profile.get("states", {})
    
    if not states or not visible_components:
        return None, 0
    
    best_state = None
    best_f1 = 0.0
    
    for state_name, state_data in states.items():
        # Support both new format (defining_components) and old format (visible)
        state_visible = set(state_data.get("defining_components", []) or state_data.get("visible", []))
        if not state_visible:
            continue
        overlap = len(visible_components & state_visible)
        precision = overlap / len(state_visible)       # how much of state is visible
        recall = overlap / len(visible_components)      # how much of visible is in state
        if precision + recall == 0:
            continue
        f1 = 2 * precision * recall / (precision + recall)
        if f1 > best_f1:
            best_f1 = f1
            best_state = state_name
    
    return best_state, best_f1


# Pending transitions — not yet confirmed. Only committed after workflow success.
_pending_transitions = {}  # app_name -> [(from, click, to), ...]
_pending_states = {}       # app_name -> {state_name: state_data, ...}


def record_transition(app_name, from_state, click_component, to_state):
    """Record a PENDING state transition: from_state --click--> to_state.
    
    Transitions are NOT immediately saved to profile. They accumulate in
    _pending_transitions and are only committed when confirm_transitions()
    is called (after a workflow succeeds).
    
    This prevents trial-and-error clicks from polluting the state graph.
    """
    if app_name not in _pending_transitions:
        _pending_transitions[app_name] = []
    _pending_transitions[app_name].append((from_state, click_component, to_state))
    print(f"  📝 Pending transition: {from_state} --{click_component}--> {to_state}")


def confirm_transitions(app_name):
    """Commit all pending transitions to profile. Call after workflow succeeds.
    
    Transitions stored as dict with key = from_state|action|to_state.
    Returns: number of transitions committed.
    """
    pending = _pending_transitions.pop(app_name, [])
    pending_st = _pending_states.pop(app_name, {})
    
    if not pending and not pending_st:
        return 0
    
    profile = load_profile(app_name)
    if "transitions" not in profile or not isinstance(profile["transitions"], dict):
        profile["transitions"] = {}
    
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    committed = 0
    for from_s, click, to_s in pending:
        action = f"click:{click}"
        key = f"{from_s}|{action}|{to_s}"
        if key in profile["transitions"]:
            profile["transitions"][key]["count"] = profile["transitions"][key].get("count", 1) + 1
            profile["transitions"][key]["last_used"] = now
        else:
            profile["transitions"][key] = {
                "from_state": from_s,
                "action": action,
                "to_state": to_s,
                "count": 1,
                "last_used": now,
                "success_rate": 1.0,
            }
        committed += 1
    
    # Also commit pending states
    if "states" not in profile:
        profile["states"] = {}
    for state_name, state_data in pending_st.items():
        profile["states"][state_name] = state_data
    
    save_profile(app_name, profile)
    if committed:
        print(f"  ✅ Committed {committed} transitions + {len(pending_st)} states to {app_name}")
    return committed


def discard_transitions(app_name):
    """Discard all pending transitions (workflow failed/aborted)."""
    n = len(_pending_transitions.pop(app_name, []))
    _pending_states.pop(app_name, {})
    if n:
        print(f"  🗑️ Discarded {n} pending transitions for {app_name}")
    return n


def get_pending_transitions(app_name):
    """Get pending (uncommitted) transitions."""
    return _pending_transitions.get(app_name, [])


def find_path(app_name, from_state, to_state):
    """BFS to find shortest click path between two states.
    
    Transitions are now stored as a dict (key=from|action|to).
    Returns: list of (action, next_state) tuples, or None if no path.
    
    Example: find_path("WeChat", "contacts_page", "宋文涛_chat")
    → [("click:chat_tab", "chat_page"), ("click:宋文涛", "宋文涛_chat")]
    """
    profile = load_profile(app_name)
    transitions = profile.get("transitions", {})
    
    if not transitions:
        return None
    
    if from_state == to_state:
        return []
    
    # Build adjacency: state -> [(action, to_state), ...]
    graph = {}
    for t in transitions.values():
        src = t.get("from_state", "")
        action = t.get("action", "")
        dest = t.get("to_state", "")
        if src not in graph:
            graph[src] = []
        graph[src].append((action, dest))
    
    # BFS
    from collections import deque
    queue = deque([(from_state, [])])
    visited = {from_state}
    
    while queue:
        current, path = queue.popleft()
        for action, next_state in graph.get(current, []):
            if next_state == to_state:
                return path + [(action, next_state)]
            if next_state not in visited:
                visited.add(next_state)
                queue.append((next_state, path + [(action, next_state)]))
    
    return None  # No path found


def get_transitions(app_name):
    """Get all recorded transitions for an app.
    
    Returns: list of transition dicts (from transitions dict values).
    """
    profile = load_profile(app_name)
    transitions = profile.get("transitions", {})
    if isinstance(transitions, dict):
        return list(transitions.values())
    return transitions  # legacy list format


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

def match_component(app_name, component_name, img=None, threshold=0.8):
    """Match a saved component template against an image (or full screen).

    If img is None, takes a full screen screenshot automatically.
    Templates are learned from app window crops but matched on any image.
    Returns: (found, click_x, click_y, confidence) or (False, 0, 0, 0)
    Coordinates are in click space (OS logical pixels).
    """
    from ui_detector import detect_to_click
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

    # If no image provided, take a full screen screenshot
    if img is None:
        screen_path = "/tmp/gui_agent_fullscreen.png"
        subprocess.run(["screencapture", "-x", screen_path],
                       capture_output=True, timeout=5)
        img = cv2.imread(screen_path)
        if img is None:
            return False, 0, 0, 0

    # Convert both to grayscale
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    if (gray_tpl.shape[0] > gray_img.shape[0] or
        gray_tpl.shape[1] > gray_img.shape[1]):
        return False, 0, 0, 0

    result = cv2.matchTemplate(gray_img, gray_tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        # Template match returns detection-space pixel coords — convert to click space
        det_cx = max_loc[0] + template.shape[1] // 2
        det_cy = max_loc[1] + template.shape[0] // 2
        click_x, click_y = detect_to_click(det_cx, det_cy)
        return True, click_x, click_y, round(max_val, 4)

    return False, 0, 0, 0


def match_all_components(app_name, img=None, threshold=0.8):
    """Match all saved components against an image (or full screen).

    If img is None, takes a full screen screenshot automatically.
    Returns: list of (component_name, click_x, click_y, confidence)
    """
    # Take screenshot once, reuse for all components
    if img is None:
        screen_path = "/tmp/gui_agent_fullscreen.png"
        subprocess.run(["screencapture", "-x", screen_path],
                       capture_output=True, timeout=5)
        img = cv2.imread(screen_path)
        if img is None:
            return []

    profile = load_profile(app_name)
    matches = []

    for comp_name in profile["components"]:
        found, lx, ly, conf = match_component(app_name, comp_name, img, threshold)
        if found:
            matches.append((comp_name, lx, ly, conf))

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

    # 2. Detect (GPA required + OCR optional via detect_all)
    icon_elements, text_elements, all_elements, img_w, img_h = ui_detector.detect_all(img_path)

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
        # Note: detect_all now returns logical (pynput) coordinates
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
                rel_x = el["cx"]
                rel_y = el["cy"]
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
            if (abs(existing.get("rel_x", 0) - el["cx"]) < 15 and
                abs(existing.get("rel_y", 0) - el["cy"]) < 15):
                is_new = False
                comp_name = existing_name  # Keep existing name
                break

        # --- Crop icon from screenshot image ---
        # detect_all returns click-space coords; convert back to detection space for cropping
        from ui_detector import click_to_detect
        px_x, px_y = click_to_detect(el["x"], el["y"])
        px_w, px_h = click_to_detect(el["w"], el["h"])
        pad = 4
        y1 = max(0, px_y - pad)
        x1 = max(0, px_x - pad)
        y2 = min(img.shape[0], px_y + px_h + pad)
        x2 = min(img.shape[1], px_x + px_w + pad)
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

        # --- Save icon image (in screenshot pixel coords for the crop) ---
        icon_file = save_component_icon(
            app_name, comp_name, img,
            (px_x, px_y, px_w, px_h)
        )

        # Relative coordinates (already logical from detect_all)
        rel_x = el["cx"]
        rel_y = el["cy"]
        
        # Assign region
        region = assign_region(el, win_w, win_h)

        comp_data = {
            "type": el["type"],
            "source": el.get("source", "unknown"),
            "rel_x": rel_x,
            "rel_y": rel_y,
            "w": el["w"],
            "h": el["h"],
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
        print(f"STEP 1: View images with `image` tool (one at a time for accuracy):")
        print(f"  IMAGES: {json.dumps(unlabeled_paths)}")
        print(f"  NAMES:  {json.dumps(unlabeled_names)}")
        print(f"STEP 2: For each image, identify what it shows.")
        print(f"  - Read any text in the image")
        print(f"  - Describe the icon/element (e.g., 'search magnifier', 'settings gear')")
        print(f"  - Only label GENERIC UI components (buttons, icons, tabs, nav elements)")
        print(f"  - SKIP temporary content (chat messages, notifications, user-specific data)")
        print(f"STEP 3: Rename each generic component:")
        print(f"  python3 app_memory.py rename --app \"{app_name}\" --old <unlabeled_name> --new <actual_name>")
        print(f"  For temp/dynamic content, delete to prevent storage bloat:")
        print(f"  python3 app_memory.py delete --app \"{app_name}\" --component <name>")
        print(f"STEP 4: When task is fully complete, cleanup remaining:")
        print(f"  python3 agent.py cleanup --app \"{app_name}\"")
        print(f"{'='*60}")

    print(f"  📁 {app_dir}")
    _tracker_tick("learns")
    _tracker_tick("screenshots")  # capture_window takes a screenshot
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

    # Detect (GPA required + OCR optional via detect_all)
    icon_elements, text_elements, all_elements, img_w, img_h = ui_detector.detect_all(img_path)
    print(f"  🔍 Detected {len(all_elements)} elements ({len(icon_elements)} icons, {len(text_elements)} text)")

    # Save to site directory
    site_dir = get_site_dir(app_name, domain)

    # Auto-migrate old profile.json if present
    migrate_profile_if_needed(site_dir)

    meta = load_meta(site_dir)
    components = load_components(site_dir)

    meta["domain"] = domain
    meta["url"] = url
    meta["window_size"] = [win_w, win_h]
    img = cv2.imread(img_path)

    # Save elements (same logic as learn_app but to site dir)
    page_components = []
    new_count = 0
    dup_count = 0
    icons_dir = site_dir / "components"

    from ui_detector import click_to_detect

    for el in all_elements:
        if el.get("label"):
            comp_name = el["label"].replace(" ", "_").replace("/", "-")[:30]
        else:
            nearest_label = _find_nearest_text(el, text_elements)
            if nearest_label:
                comp_name = nearest_label.replace(" ", "_").replace("/", "-")[:30]
            else:
                rel_x = el["cx"]
                rel_y = el["cy"]
                comp_name = f"unlabeled_{rel_x}_{rel_y}"

        # Dedup by position (coords already click-space from detect_all)
        is_new = True
        for existing_name, existing in components.items():
            if (abs(existing.get("rel_x", 0) - el["cx"]) < 15 and
                abs(existing.get("rel_y", 0) - el["cy"]) < 15):
                is_new = False
                comp_name = existing_name
                break

        # Crop from screenshot image (convert click-space → detection space)
        px_x, px_y = click_to_detect(el["x"], el["y"])
        px_w, px_h = click_to_detect(el["w"], el["h"])
        pad = 4
        y1, x1 = max(0, px_y-pad), max(0, px_x-pad)
        y2 = min(img.shape[0], px_y+px_h+pad)
        x2 = min(img.shape[1], px_x+px_w+pad)
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

        rel_x = el["cx"]
        rel_y = el["cy"]
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        components[comp_name] = {
            "type": el["type"], "source": el.get("source", "unknown"),
            "rel_x": rel_x, "rel_y": rel_y,
            "w": el["w"], "h": el["h"],
            "icon_file": f"components/{safe_name}.png",
            "label": el.get("label"), "confidence": el.get("confidence", 0),
            "page": page_name, "learned_at": now,
            "last_seen": now, "seen_count": 1, "consecutive_misses": 0,
        }
        page_components.append(comp_name)
        if is_new:
            new_count += 1

    if "pages" not in meta:
        meta["pages"] = {}
    meta["pages"][page_name] = {
        "components": page_components,
        "learned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Save annotated image
    import ui_detector
    ui_detector.annotate_image(img_path, all_elements,
                                str(site_dir / f"pages/{page_name}_annotated.jpg"))

    meta["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_meta(site_dir, meta)
    save_components(site_dir, components)

    print(f"  💾 Saved {len(page_components)} components ({new_count} new, {dup_count} dups)")
    print(f"  📁 {site_dir}")
    return True


def learn_from_screenshot(img_path, domain=None, app_name="chromium", page_name=None, retina=False):
    """Learn UI components from any screenshot (local or remote VM).

    This is the platform-independent version of learn_site(). It takes a
    screenshot path as input and does NOT call any Mac-specific APIs
    (no screencapture, no osascript, no get_window_bounds).

    Args:
        img_path: Path to screenshot PNG (any source — local, VM, etc.)
        domain: Website domain (e.g. "united.com"). If None, saves to app-level memory.
        app_name: Browser/app name for memory directory (default "chromium")
        page_name: Page label (e.g. "homepage", "bags_overview"). Auto-generated if None.
        retina: If True, coordinates are halved for logical pixels (Mac Retina).
                If False (default), coordinates are used as-is (VMs, non-Retina).

    Returns: dict with saved component names and count
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    import ui_detector

    img = cv2.imread(img_path)
    if img is None:
        print(f"  ❌ Could not read image: {img_path}")
        return {"saved": 0, "components": []}

    img_h, img_w = img.shape[:2]
    # detect_all() handles all coordinate conversion internally (detection → click space).
    # Elements returned are already in click space. For cropping, use click_to_detect().
    # The `retina` parameter is DEPRECATED and ignored.
    from ui_detector import click_to_detect

    # Auto-generate page_name from domain + timestamp if not provided
    if not page_name:
        page_name = f"page_{time.strftime('%H%M%S')}"

    print(f"🧠 Learning from screenshot: {img_path}")
    print(f"  Size: {img_w}x{img_h}, domain: {domain}, page: {page_name}")

    # Detect (GPA required + OCR optional via detect_all)
    icon_elements, text_elements, all_elements, det_w, det_h = ui_detector.detect_all(img_path)
    _tracker_auto_tick("detector_calls")
    _tracker_auto_tick("ocr_calls")
    print(f"  🔍 Detected {len(all_elements)} elements ({len(icon_elements)} icons, {len(text_elements)} text)")

    _tracker_auto_tick("screenshots")
    _tracker_auto_tick("learns")

    # Auto-update tracker task name with app/domain info
    task_name = f"{app_name}"
    if domain:
        task_name += f"/{domain}"
    _tracker_update_task(task_name)

    # Get save directory
    if domain:
        save_dir = get_site_dir(app_name, domain)
    else:
        save_dir = get_app_dir(app_name)

    # Auto-migrate old format
    migrate_profile_if_needed(save_dir)

    # Load split files
    meta = load_meta(save_dir)
    components = load_components(save_dir)
    states = load_states(save_dir)
    transitions = load_transitions(save_dir)

    meta["app"] = app_name
    if domain:
        meta["domain"] = domain
    meta["img_size"] = [img_w, img_h]

    icons_dir = save_dir / "components"
    page_components = []
    new_count = 0
    dup_count = 0
    skip_count = 0
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    for el in all_elements:
        # Filter: skip tiny elements
        w, h = el.get("w", 0), el.get("h", 0)
        if w < 25 or h < 25:
            skip_count += 1
            continue

        # Smart naming: OCR text > nearest text > positional
        # el coords are already in click space (from detect_all)
        if el.get("label"):
            comp_name = el["label"].replace(" ", "_").replace("/", "-")[:30]
        else:
            nearest_label = _find_nearest_text(el, text_elements)
            if nearest_label:
                comp_name = nearest_label.replace(" ", "_").replace("/", "-")[:30]
            else:
                comp_name = f"unlabeled_{el['cx']}_{el['cy']}"

        # Dedup by position against existing components (click-space)
        is_new = True
        for existing_name, existing in components.items():
            if (abs(existing.get("rel_x", 0) - el["cx"]) < 15 and
                abs(existing.get("rel_y", 0) - el["cy"]) < 15):
                is_new = False
                comp_name = existing_name
                break

        # Crop from screenshot (convert click-space → detection-space for pixel access)
        det_x, det_y = click_to_detect(el["x"], el["y"])
        det_w, det_h = click_to_detect(w, h)
        pad = 4
        y1, x1 = max(0, det_y - pad), max(0, det_x - pad)
        y2 = min(img.shape[0], det_y + det_h + pad)
        x2 = min(img.shape[1], det_x + det_w + pad)
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        # Visual dedup
        is_dup, dup_name = is_duplicate_icon(crop, icons_dir, threshold=0.92)
        if is_dup and is_new:
            dup_count += 1
            continue

        # Save icon
        safe_name = comp_name.replace("/", "-").replace(" ", "_").replace(":", "")
        safe_name = safe_name.replace("\\", "-").replace("?", "").replace("*", "")[:50]
        icon_path = icons_dir / f"{safe_name}.png"
        cv2.imwrite(str(icon_path), crop)

        # Coordinates are already in click space from detect_all
        rel_x = el["cx"]
        rel_y = el["cy"]

        components[comp_name] = {
            "type": el["type"],
            "source": el.get("source", "detection"),
            "rel_x": rel_x, "rel_y": rel_y,
            "w": w, "h": h,
            "icon_file": f"components/{safe_name}.png",
            "label": el.get("label"),
            "confidence": el.get("confidence", 0),
            "page": page_name,
            "learned_at": now,
            "last_seen": now, "seen_count": 1, "consecutive_misses": 0,
        }
        page_components.append(comp_name)
        if is_new:
            new_count += 1

    # Save page screenshot
    pages_dir = save_dir / "pages"
    import shutil
    shutil.copy2(img_path, str(pages_dir / f"{page_name}.png"))

    # Save annotated image
    try:
        ui_detector.annotate_image(img_path, all_elements,
                                   str(pages_dir / f"{page_name}_annotated.jpg"))
    except Exception:
        pass

    # --- Phase 2: Component activity tracking + forgetting ---
    detected_names = set(page_components)
    components = update_component_activity(components, detected_names, now=now)
    meta["detect_count"] = meta.get("detect_count", 0) + 1
    components, states, transitions = forget_stale_components(
        save_dir, components, meta, states, transitions
    )

    # --- Phase 3: State identification + merging ---
    current_state_id, states = identify_or_create_state(
        states, detected_names, components, description=page_name
    )
    states, transitions = merge_similar_states(states, transitions)

    # Update meta
    if "pages" not in meta:
        meta["pages"] = {}
    meta["pages"][page_name] = {
        "components": page_components,
        "learned_at": now,
    }
    meta["last_updated"] = now

    # Save all split files
    save_meta(save_dir, meta)
    save_components(save_dir, components)
    save_states(save_dir, states)
    save_transitions(save_dir, transitions)

    print(f"  💾 Saved {len(page_components)} components ({new_count} new, {dup_count} dups, {skip_count} skipped)")
    if current_state_id:
        print(f"  📊 State: {current_state_id}")
    print(f"  📁 {save_dir}")
    return {"saved": len(page_components), "new": new_count, "components": page_components}


def record_page_transition(before_img_path, after_img_path, click_label, click_pos,
                           domain=None, app_name="chromium", retina=False):
    """Record a state transition from before/after screenshots.

    Platform-independent: no Mac APIs. Takes two screenshot paths,
    runs OCR on both, computes diff, saves to profile.

    Args:
        before_img_path: Screenshot before click
        after_img_path: Screenshot after click
        click_label: What was clicked (text label or component name)
        click_pos: (x, y) coordinates of the click
        domain: Website domain (for browser sites)
        app_name: App/browser name
        retina: Whether to halve coordinates

    Returns: dict with appeared/disappeared/transition info
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    import ui_detector

    # Detect both screenshots with GPA + OCR (always run both)
    before_texts = set()
    after_texts = set()
    before_icon_count = 0
    after_icon_count = 0

    try:
        before_icons, before_elems, before_merged, _, _ = ui_detector.detect_all(before_img_path)
        _tracker_auto_tick("detector_calls")
        _tracker_auto_tick("ocr_calls")
        before_texts = set(e.get("label", "").strip() for e in before_elems if e.get("label", "").strip())
        before_icon_count = len(before_icons)
    except Exception as ex:
        print(f"  ⚠️ Detection failed on before image: {ex}")

    try:
        after_icons, after_elems, after_merged, _, _ = ui_detector.detect_all(after_img_path)
        _tracker_auto_tick("detector_calls")
        _tracker_auto_tick("ocr_calls")
        after_texts = set(e.get("label", "").strip() for e in after_elems if e.get("label", "").strip())
        after_icon_count = len(after_icons)
    except Exception as ex:
        print(f"  ⚠️ Detection failed on after image: {ex}")

    _tracker_auto_tick("transitions")
    _tracker_auto_tick("clicks")

    # Text diff
    appeared = after_texts - before_texts
    disappeared = before_texts - after_texts
    persisted = before_texts & after_texts

    # Icon diff (count change as a signal)
    icon_delta = after_icon_count - before_icon_count

    if appeared:
        top = sorted(appeared)[:8]
        print(f"  ✅ Appeared: {', '.join(top)}")
    if disappeared:
        top = sorted(disappeared)[:8]
        print(f"  📤 Disappeared: {', '.join(top)}")
    print(f"  📊 Text: {len(persisted)} persisted, {len(appeared)} appeared, {len(disappeared)} disappeared")
    print(f"  📊 Icons: {before_icon_count} → {after_icon_count} (delta: {icon_delta:+d})")

    # Load split files
    if domain:
        save_dir = get_site_dir(app_name, domain)
    else:
        save_dir = get_app_dir(app_name)

    # Auto-migrate old format
    migrate_profile_if_needed(save_dir)

    meta = load_meta(save_dir)
    states = load_states(save_dir)
    transitions = load_transitions(save_dir)

    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # State names
    from_state = f"before_{click_label}"
    to_state = f"after_{click_label}"

    # Save states
    states[from_state] = {
        "visible_texts": sorted(list(before_texts))[:50],  # Cap to prevent bloat
    }
    states[to_state] = {
        "visible_texts": sorted(list(after_texts))[:50],
        "appeared": sorted(list(appeared))[:20],
        "disappeared": sorted(list(disappeared))[:20],
    }

    # Save transition (dict-based, deduped by key)
    action = f"click:{click_label}"
    key = f"{from_state}|{action}|{to_state}"
    if key in transitions:
        transitions[key]["count"] = transitions[key].get("count", 1) + 1
        transitions[key]["last_used"] = now
    else:
        transitions[key] = {
            "from_state": from_state,
            "action": action,
            "to_state": to_state,
            "count": 1,
            "last_used": now,
            "success_rate": 1.0,
            "click_pos": list(click_pos),
            "appeared_count": len(appeared),
            "disappeared_count": len(disappeared),
        }

    meta["last_updated"] = now
    save_meta(save_dir, meta)
    save_states(save_dir, states)
    save_transitions(save_dir, transitions)

    print(f"  🔄 Transition: {from_state} → [{click_label}] → {to_state}")
    return {
        "appeared": sorted(list(appeared)),
        "disappeared": sorted(list(disappeared)),
        "from": from_state,
        "to": to_state,
    }


def navigate_browser(app_name, url):
    """Navigate browser to a URL."""
    # Method 1: open command (works for any browser, most reliable)
    subprocess.run(["open", "-a", app_name, url], capture_output=True, timeout=10)
    time.sleep(3)  # Wait for page load
    return True


def auto_cleanup_dynamic(app_name):
    """Remove temporary/dynamic content after learning to prevent storage bloat.

    RULES:
    - Remove: timestamps, message previews, chat text, stickers, notification counts
      (these change every session and would accumulate endlessly)
    - Keep: all stable UI elements (buttons, icons, tabs, navigation, labels)
    - No privacy filtering — we don't upload, so no leak risk
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
    
    Learn uses app window crop, but matching is done on FULL SCREEN.
    No coordinate conversion needed — match returns screen logical coords directly.

    Returns: (known_matches, unknown_elements, img_path)
    """
    sys.path.insert(0, str(SCRIPT_DIR))

    # Capture window crop for GPA-GUI-Detector detection (new element discovery)
    img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
    if not img_path:
        return [], [], None

    # Detect all elements (GPA required + OCR optional via detect_all)
    import ui_detector
    icon_elements, text_elements, all_elements, _, _ = ui_detector.detect_all(img_path)
    visible_text = [t.get("label", "") for t in text_elements]
    
    # Identify current state using detected text
    current_state, match_ratio = identify_state(app_name, visible_text)
    if current_state:
        print(f"  📊 Identified state: '{current_state}' ({match_ratio:.0%} match)")
        state_components = get_state_components(app_name, current_state)
        print(f"  🎯 Matching {len(state_components)} state-specific components")
    else:
        print(f"  📊 Could not identify state, matching all components")
        profile = load_profile(app_name)
        state_components = list(profile.get("components", {}).keys())

    # Match on FULL SCREEN — take one screenshot and reuse
    screen_path = "/tmp/gui_agent_fullscreen.png"
    subprocess.run(["screencapture", "-x", screen_path],
                   capture_output=True, timeout=5)
    screen_img = cv2.imread(screen_path)

    known = []
    for comp_name in state_components:
        found, lx, ly, conf = match_component(app_name, comp_name, screen_img, threshold)
        if found:
            known.append((comp_name, lx, ly, conf))
    
    print(f"  🔗 Matched {len(known)} known components")
    for name, rx, ry, conf in known:
        print(f"    ✅ {name} ({rx},{ry}) conf={conf}")
    
    # Report match rate for this state
    if state_components:
        match_rate = len(known) / len(state_components)
        print(f"  📊 State match rate: {match_rate:.1%} ({len(known)}/{len(state_components)})")

    # Filter out known (matched) elements
    # Both all_elements (from detect_all) and known (from match_component)
    # are in click space — compare directly.
    unknown = []
    for el in all_elements:
        el_rx = el["cx"]
        el_ry = el["cy"]
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

def match_on_fullscreen(app_name, component_name, threshold=0.8, screen_img=None):
    """Match a component template on screen, scoped to the app's window area.

    Searches within the app's window bounds (+padding) to avoid false matches
    from other apps. Returns screen logical coords directly.
    
    Args:
        app_name: App name
        component_name: Component to find
        threshold: Minimum match confidence (default 0.8)
        screen_img: Pre-loaded full screen image (optional, avoids re-capture)
    
    Returns: (found, logical_x, logical_y, confidence)
    """
    profile = load_profile(app_name)
    comp = profile["components"].get(component_name)
    if not comp or not comp.get("icon_file"):
        return False, 0, 0, 0

    app_dir = get_app_dir(app_name)
    template_path = app_dir / comp["icon_file"]
    if not template_path.exists():
        return False, 0, 0, 0

    template = cv2.imread(str(template_path))
    if template is None:
        return False, 0, 0, 0

    # Take full screen screenshot (or reuse provided)
    if screen_img is None:
        screen_path = "/tmp/gui_agent_fullscreen.png"
        subprocess.run(["screencapture", "-x", screen_path], capture_output=True, timeout=5)
        screen_img = cv2.imread(screen_path)
    if screen_img is None:
        return False, 0, 0, 0

    # Full screen search + window bounds validation
    # Search on entire screen (no window position dependency for matching),
    # then verify the match is within the app's window (reject other apps).
    gray_screen = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    if (gray_tpl.shape[0] > gray_screen.shape[0] or
        gray_tpl.shape[1] > gray_screen.shape[1]):
        return False, 0, 0, 0

    result = cv2.matchTemplate(gray_screen, gray_tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < threshold:
        return False, 0, 0, 0

    # Detection-space pixel center → click-space coords
    from ui_detector import detect_to_click
    det_x = max_loc[0] + template.shape[1] // 2
    det_y = max_loc[1] + template.shape[0] // 2
    click_x, click_y = detect_to_click(det_x, det_y)

    # Validate: match must be within app's window (reject matches from other apps)
    bounds = get_window_bounds(app_name)
    if bounds:
        wx, wy, ww, wh = bounds
        margin = 30  # click-space pixels tolerance for shadows/titlebar
        if not (wx - margin <= click_x <= wx + ww + margin and
                wy - margin <= click_y <= wy + wh + margin):
            # Match is outside the app window — likely a false match from another app
            return False, 0, 0, 0

    return True, click_x, click_y, round(max_val, 4)


def _detect_visible_components(app_name, screen_img=None):
    """Quick scan: which saved components are currently visible on screen.
    
    Uses template matching only (fast, no image/LLM calls).
    Crops to window area for speed.
    
    Args:
        app_name: App name
        screen_img: Pre-loaded full screen image (optional, avoids re-capture)
    
    Returns: set of component names that matched on screen.
    """
    profile = load_profile(app_name)
    visible = set()
    
    import cv2
    if screen_img is None:
        import subprocess
        subprocess.run(["screencapture", "-x", "/tmp/_detect_vis.png"],
                       capture_output=True, timeout=5)
        screen_img = cv2.imread("/tmp/_detect_vis.png")
    
    if screen_img is None:
        return visible
    
    # Full screen search + window bounds validation (same as match_on_fullscreen)
    bounds = get_window_bounds(app_name)
    gray_screen = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
    
    app_dir = get_app_dir(app_name)
    for comp_name, comp_data in profile.get("components", {}).items():
        if not comp_data.get("icon_file"):
            continue
        tpl_path = app_dir / comp_data["icon_file"]
        if not tpl_path.exists():
            continue
        template = cv2.imread(str(tpl_path))
        if template is None:
            continue
        gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        if gray_tpl.shape[0] > gray_screen.shape[0] or gray_tpl.shape[1] > gray_screen.shape[1]:
            continue
        try:
            result = cv2.matchTemplate(gray_screen, gray_tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val < 0.8:
                continue
            # Validate match is within app window
            if bounds:
                wx, wy, ww, wh = bounds
                from ui_detector import detect_to_click as _d2c
                lx, ly = _d2c(max_loc[0] + template.shape[1] // 2,
                               max_loc[1] + template.shape[0] // 2)
                margin = 30
                if not (wx - margin <= lx <= wx + ww + margin and
                        wy - margin <= ly <= wy + wh + margin):
                    continue
            visible.add(comp_name)
        except Exception:
            continue
    
    return visible


def click_and_record(app_name, label, x, y):
    """Click at (x, y) and record state transition.
    
    Use this for ANY click — whether coordinates came from template matching,
    GPA-GUI-Detector detection, or OCR. Ensures every click builds the state graph.
    
    Uses both template matching (saved components) AND OCR text to detect
    state changes. This way it works even before the app has been learned.
    
    Args:
        app_name: App name
        label: What was clicked (component name, OCR text, etc.)
        x, y: Logical screen coordinates
    
    Returns: (success, message, after_visible_components)
    """
    from platform_input import click_at, verify_frontmost, activate_app as pi_activate
    import subprocess as _sp
    import cv2 as _cv2
    import ui_detector

    # Pre-click: lightweight — template match only (no OCR), ~2s
    _sp.run(["screencapture", "-x", "/tmp/_click_rec.png"],
            capture_output=True, timeout=5)
    _tracker_tick("screenshots")
    before_screen = _cv2.imread("/tmp/_click_rec.png")
    before_visible = _detect_visible_components(app_name, screen_img=before_screen)
    from_state, _ = identify_state_by_components(app_name, before_visible)

    # Click
    click_at(x, y)
    time.sleep(0.5)

    # Verify app
    is_correct, actual_app = verify_frontmost(app_name)
    if not is_correct:
        pi_activate(app_name)
        time.sleep(0.5)
        return False, f"App switched to '{actual_app}'", set()

    # Post-click: full detection — template match + OCR, ~3s
    time.sleep(0.3)
    _sp.run(["screencapture", "-x", "/tmp/_click_rec2.png"],
            capture_output=True, timeout=5)
    _tracker_tick("screenshots")
    after_screen = _cv2.imread("/tmp/_click_rec2.png")
    after_visible = _detect_visible_components(app_name, screen_img=after_screen)
    
    after_texts = set()
    after_icon_count = 0
    try:
        after_icons, after_text_elems, _, _, _ = ui_detector.detect_all("/tmp/_click_rec2.png")
        after_texts = set(e.get("label", "") for e in after_text_elems if e.get("label"))
        after_icon_count = len(after_icons)
    except Exception:
        pass
    
    after_all = after_visible | after_texts
    # For change detection, compare against template-only before set
    before_all = before_visible
    
    # Calculate changes (use combined sets)
    appeared = after_all - before_all
    disappeared = before_all - after_all

    if appeared:
        top = sorted(appeared)[:5]
        print(f"  ✅ Appeared: {', '.join(top)}")
    if disappeared:
        top = sorted(disappeared)[:5]
        print(f"  📤 Disappeared: {', '.join(top)}")
    
    changed = bool(appeared or disappeared)

    # Pending state + transition (NOT saved to profile yet — wait for confirm)
    to_state_name = f"click:{label}"
    state_data = {
        "visible": list(after_all),
        "trigger": label,
        "trigger_pos": [x, y],
        "disappeared": list(disappeared),
        "appeared": list(appeared),
    }
    if app_name not in _pending_states:
        _pending_states[app_name] = {}
    _pending_states[app_name][to_state_name] = state_data

    if from_state and changed and from_state != to_state_name:
        record_transition(app_name, from_state, label, to_state_name)
    elif not from_state and changed:
        from_state_name = "unknown_before"
        if app_name not in _pending_states:
            _pending_states[app_name] = {}
        _pending_states[app_name][from_state_name] = {"visible": list(before_all)}
        record_transition(app_name, from_state_name, label, to_state_name)

    print(f"  📊 State: {to_state_name} | {len(after_all)} items ({len(after_visible)} components + {len(after_texts)} texts)")

    # Auto-tick tracker (no-op if tracker not running)
    _tracker_tick("clicks")

    return True, f"Clicked '{label}' at ({x},{y})", after_visible


def drag_and_record(app_name, label, x1, y1, x2, y2, duration=0.5):
    """Drag from (x1,y1) to (x2,y2) and record state transition.
    
    Like click_and_record but for drag operations (area selection, 
    file drag-drop, slider adjustment, window resize, etc.).
    
    Args:
        app_name: App name
        label: Description of drag action  
        x1, y1: Start coordinates (logical)
        x2, y2: End coordinates (logical)
        duration: Drag duration in seconds
    
    Returns: (success, message, after_visible_components)
    """
    from platform_input import mouse_drag, verify_frontmost, activate_app as pi_activate
    import subprocess as _sp
    import cv2 as _cv2

    # Pre-drag: template match for state detection
    _sp.run(["screencapture", "-x", "/tmp/_drag_rec.png"],
            capture_output=True, timeout=5)
    _tracker_tick("screenshots")
    before_screen = _cv2.imread("/tmp/_drag_rec.png")
    before_visible = _detect_visible_components(app_name, screen_img=before_screen)
    from_state, _ = identify_state_by_components(app_name, before_visible)

    # Drag
    mouse_drag(x1, y1, x2, y2, duration=duration)
    time.sleep(0.5)

    # Verify app
    is_correct, actual_app = verify_frontmost(app_name)
    if not is_correct:
        pi_activate(app_name)
        time.sleep(0.5)
        return False, f"App switched to '{actual_app}'", set()

    # Post-drag: full detection
    time.sleep(0.3)
    _sp.run(["screencapture", "-x", "/tmp/_drag_rec2.png"],
            capture_output=True, timeout=5)
    _tracker_tick("screenshots")
    after_screen = _cv2.imread("/tmp/_drag_rec2.png")
    after_visible = _detect_visible_components(app_name, screen_img=after_screen)

    after_texts = set()
    after_icon_count = 0
    try:
        import ui_detector
        after_icons, after_text_elems, _, _, _ = ui_detector.detect_all("/tmp/_drag_rec2.png")
        after_texts = set(e.get("label", "") for e in after_text_elems if e.get("label"))
        after_icon_count = len(after_icons)
    except Exception:
        pass

    after_all = after_visible | after_texts
    before_all = before_visible

    appeared = after_all - before_all
    disappeared = before_all - after_all

    if appeared:
        print(f"  ✅ Appeared: {', '.join(sorted(appeared)[:5])}")
    if disappeared:
        print(f"  📤 Disappeared: {', '.join(sorted(disappeared)[:5])}")

    # Record state transition
    to_state_name = f"drag:{label}"
    state_data = {
        "visible": list(after_all),
        "trigger": label,
        "trigger_pos": [x1, y1, x2, y2],
        "type": "drag",
    }
    if app_name not in _pending_states:
        _pending_states[app_name] = {}
    _pending_states[app_name][to_state_name] = state_data

    if from_state:
        record_transition(app_name, from_state, label, to_state_name)

    print(f"  📊 Drag ({x1},{y1})→({x2},{y2}) | State: {to_state_name}")
    _tracker_tick("clicks")

    return True, f"Dragged '{label}' from ({x1},{y1}) to ({x2},{y2})", after_visible


def cell_select_by_ocr(app_name, cell_range, hints=None):
    """Select a cell range in a spreadsheet using OCR-based grid detection.
    
    Scans the screen for known data text, uses their positions to build a
    cell grid, then drags to select the target range.
    
    Args:
        app_name: Spreadsheet app name (e.g. 'Microsoft Excel')
        cell_range: Range like 'B2:D4' or single cell 'A1'
        hints: Optional dict of {text: (col, row)} for grid calibration.
               If None, auto-detects from common spreadsheet data.
    
    Returns: (success, message)
    """
    import re
    from platform_input import mouse_click, mouse_drag, activate_app as pi_activate, screenshot
    from spreadsheet_utils import _parse_cell_ref, _run_vision_ocr

    pi_activate(app_name)
    time.sleep(0.3)

    # Parse range
    if ':' in cell_range:
        start_ref, end_ref = cell_range.split(':')
    else:
        start_ref = cell_range
        end_ref = None

    start_col, start_row = _parse_cell_ref(start_ref)
    if end_ref:
        end_col, end_row = _parse_cell_ref(end_ref)
    else:
        end_col, end_row = start_col, start_row

    # Screenshot and OCR
    path = screenshot("/tmp/_cell_select.png")
    results = _run_vision_ocr(path)
    _tracker_tick("screenshots")

    # Build grid from OCR results
    # Use hints if provided, otherwise try to auto-detect
    col_xs = {}  # col_letter -> [center_x_logical]
    row_ys = {}  # row_num -> [center_y_logical]

    if hints:
        for text_pattern, (col, row) in hints.items():
            for text, x, y, w, h in results:
                if text.strip() == text_pattern:
                    cx = (x + w / 2) / 2  # Retina -> logical
                    cy = (y + h / 2) / 2
                    col_xs.setdefault(col, []).append(cx)
                    row_ys.setdefault(row, []).append(cy)
    
    # Also scan for row numbers in left margin (x < 80 retina, digits only)
    for text, x, y, w, h in results:
        clean = text.strip()
        if x < 80 and clean.isdigit() and 1 <= int(clean) <= 200:
            row_num = int(clean)
            cy = (y + h / 2) / 2
            row_ys.setdefault(row_num, []).append(cy)
    
    # Average positions
    col_pos = {k: sum(v)/len(v) for k, v in col_xs.items() if v}
    row_pos = {k: sum(v)/len(v) for k, v in row_ys.items() if v}

    # Extrapolate missing positions from known ones
    if len(col_pos) >= 2:
        sorted_cols = sorted(col_pos.items(), key=lambda c: c[1])
        # Estimate column width
        col_widths = []
        for i in range(1, len(sorted_cols)):
            c1_idx = ord(sorted_cols[i-1][0]) - ord('A')
            c2_idx = ord(sorted_cols[i][0]) - ord('A')
            if c2_idx > c1_idx:
                col_widths.append((sorted_cols[i][1] - sorted_cols[i-1][1]) / (c2_idx - c1_idx))
        if col_widths:
            avg_col_width = sum(col_widths) / len(col_widths)
            # Fill in missing columns
            ref_col, ref_x = sorted_cols[0]
            ref_idx = ord(ref_col) - ord('A')
            for col_letter in [start_col, end_col]:
                if col_letter not in col_pos:
                    target_idx = ord(col_letter) - ord('A')
                    col_pos[col_letter] = ref_x + (target_idx - ref_idx) * avg_col_width

    if len(row_pos) >= 2:
        sorted_rows = sorted(row_pos.items())
        row_heights = []
        for i in range(1, len(sorted_rows)):
            r1, y1 = sorted_rows[i-1]
            r2, y2 = sorted_rows[i]
            if r2 > r1:
                row_heights.append((y2 - y1) / (r2 - r1))
        if row_heights:
            avg_row_height = sum(row_heights) / len(row_heights)
            ref_row, ref_y = sorted_rows[0]
            for row_num in [start_row, end_row]:
                if row_num not in row_pos:
                    row_pos[row_num] = ref_y + (row_num - ref_row) * avg_row_height

    # Check we have all needed positions
    needed_cols = [start_col, end_col] if end_ref else [start_col]
    needed_rows = [start_row, end_row] if end_ref else [start_row]
    
    missing = []
    for c in needed_cols:
        if c not in col_pos:
            missing.append(f"column {c}")
    for r in needed_rows:
        if r not in row_pos:
            missing.append(f"row {r}")
    
    if missing:
        return False, f"Could not locate: {', '.join(missing)}. Provide --hints for calibration."

    if end_ref:
        # Drag select
        sx, sy = col_pos[start_col], row_pos[start_row]
        ex, ey = col_pos[end_col], row_pos[end_row]
        print(f"  📍 {start_ref} at ({sx:.0f}, {sy:.0f})")
        print(f"  📍 {end_ref} at ({ex:.0f}, {ey:.0f})")
        mouse_drag(sx, sy, ex, ey, duration=0.5)
        _tracker_tick("clicks")
        return True, f"Selected {cell_range} via drag ({sx:.0f},{sy:.0f})→({ex:.0f},{ey:.0f})"
    else:
        # Single cell click
        cx, cy = col_pos[start_col], row_pos[start_row]
        mouse_click(cx, cy)
        _tracker_tick("clicks")
        return True, f"Clicked cell {start_ref} at ({cx:.0f}, {cy:.0f})"


def click_component(app_name, component_name, verify=True):
    """Find a component by template match on FULL SCREEN and click it.

    Full protocol:
    1. Detect visible components (template match, no LLM)
    2. Check if expected post-click state exists (from previous clicks)
    3. Click
    4. Detect visible components again
    5. If expected state exists → verify by component matching (no screenshot needed)
       If no expected state → save new state for future verification
    6. Return result + visible components (agent decides next step)

    Returns: (success, message)
    """
    from platform_input import click_at, verify_frontmost, activate_app as pi_activate

    # 0. System component? Use fixed position relative to window
    if component_name.startswith("sys_") and component_name in MACOS_SYSTEM_COMPONENTS:
        img_path, win_x, win_y, win_w, win_h = capture_window(app_name)
        if not img_path:
            return False, f"Could not capture {app_name} window"
        sys_comp = MACOS_SYSTEM_COMPONENTS[component_name]
        screen_x = win_x + sys_comp["rel_x"]
        screen_y = win_y + sys_comp["rel_y"]
        print(f"  🎯 System component '{component_name}' → screen({screen_x},{screen_y})")
        click_at(screen_x, screen_y)
        return True, f"Clicked system component {component_name}"

    # 1. PRE-CLICK: one screenshot, reuse for everything
    import subprocess as _sp
    import cv2 as _cv2
    _sp.run(["screencapture", "-x", "/tmp/_click_screen.png"],
            capture_output=True, timeout=5)
    _tracker_tick("screenshots")
    before_screen = _cv2.imread("/tmp/_click_screen.png")
    before_visible = _detect_visible_components(app_name, screen_img=before_screen)

    # 2. Match target (using same screenshot, scoped to window)
    found, screen_x, screen_y, conf = match_on_fullscreen(
        app_name, component_name, screen_img=before_screen)

    if not found:
        return False, f"Component '{component_name}' not found (no template match on screen)"

    print(f"  🎯 Found '{component_name}' → screen({screen_x},{screen_y}) conf={conf}")

    # 3. Verify confidence
    if verify and conf < 0.8:
        return False, f"Low confidence ({conf}), not clicking"

    # 4. Check if we have an expected state for this click
    state_name = f"click:{component_name}"
    profile = load_profile(app_name)
    expected_state = profile.get("states", {}).get(state_name)

    # 5. Click
    click_at(screen_x, screen_y)
    time.sleep(0.5)

    # 6. Verify we're still in the right app
    is_correct, actual_app = verify_frontmost(app_name)
    if not is_correct:
        print(f"  ⚠️ APP SWITCHED! Expected '{app_name}', now in '{actual_app}'")
        pi_activate(app_name)
        time.sleep(0.5)
        return False, f"Click caused app switch to '{actual_app}', re-activated {app_name}"

    # 7. POST-CLICK: detect visible components again
    time.sleep(0.3)
    after_visible = _detect_visible_components(app_name)

    # Calculate what changed
    appeared = after_visible - before_visible
    disappeared = before_visible - after_visible

    if appeared:
        print(f"  ✅ New components appeared: {', '.join(sorted(appeared))}")
    if disappeared:
        print(f"  📤 Components disappeared: {', '.join(sorted(disappeared))}")
    if not appeared and not disappeared:
        print(f"  ⚠️ No component changes detected after click")

    # 8. State verification / learning / updating
    def _save_click_state():
        """Buffer state data as pending (not written to profile yet)."""
        state_data = {
            "visible": list(after_visible),
            "trigger": component_name,
            "trigger_pos": [screen_x, screen_y],
            "disappeared": list(disappeared),
            "appeared": list(appeared),
        }
        if app_name not in _pending_states:
            _pending_states[app_name] = {}
        _pending_states[app_name][state_name] = state_data

    if expected_state:
        # VERIFY: check expected components
        expected_appeared = set(expected_state.get("appeared", []))
        expected_visible = set(expected_state.get("visible", []))
        
        if expected_appeared:
            matched = expected_appeared & appeared
            match_ratio = len(matched) / len(expected_appeared) if expected_appeared else 0
        else:
            overlap = len(after_visible & expected_visible)
            match_ratio = overlap / len(expected_visible) if expected_visible else 0

        if match_ratio >= 0.5:
            print(f"  ✅ State verified ({match_ratio:.0%})")
        else:
            # Mismatch — update state with current data
            print(f"  ⚠️ State mismatch ({match_ratio:.0%}), updating state data...")
            _save_click_state()
            print(f"  🔄 State '{state_name}' updated with current components")
    else:
        # LEARN: new state
        _save_click_state()
        if appeared:
            print(f"  💾 Saved state '{state_name}': {len(appeared)} new components")
        else:
            print(f"  💾 Saved state '{state_name}'")

    # 9. Record state transition (from_state --click--> to_state)
    #    Use the state saved for this click as to_state (click:{component})
    #    The from_state is whatever best matches before_visible
    from_state, from_f1 = identify_state_by_components(app_name, before_visible)
    to_state_name = f"click:{component_name}"  # The state after clicking this component
    
    # Only record if we had a meaningful from_state and there was actual change
    if from_state and (appeared or disappeared) and from_state != to_state_name:
        record_transition(app_name, from_state, component_name, to_state_name)
        print(f"  🔗 Transition: {from_state} --{component_name}--> {to_state_name}")
    elif not from_state and (appeared or disappeared):
        # Unknown from_state — save current as "unknown" but still record
        print(f"  🔗 Transition: (unknown) --{component_name}--> {to_state_name}")

    # 10. Report current state for agent decision-making
    print(f"  📊 State: {to_state_name} | {len(after_visible)} components visible")
    if after_visible:
        summary = sorted(after_visible)[:15]
        if len(after_visible) > 15:
            print(f"  📋 Components: {', '.join(summary)} ... (+{len(after_visible)-15} more)")
        else:
            print(f"  📋 Components: {', '.join(summary)}")

    _tracker_tick("clicks")
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

    # Detect with GPA + OCR (always both)
    _, text_elements, merged, _, _ = ui_detector.detect_all(img_path)

    # Look for the expected contact name in the detected text
    for el in text_elements:
        if expected_contact.lower() in el.get("label", "").lower():
            return True, f"Verified: '{expected_contact}' found in UI"

    # Not found
    visible_texts = [el.get("label", "") for el in text_elements[:10]]
    return False, f"Contact '{expected_contact}' not found. Visible: {visible_texts[:5]}"


def verify_page_state(img_path, before_img_path=None, expected_texts=None, min_icon_change=0):
    """Verify the current page state after an action.

    Runs GPA (required) + OCR (optional) on the image to assess state.
    Designed to answer: "did my action have the expected effect?"

    Verification modes (combine as needed):
    1. DIFF MODE (before_img_path given): Compare before/after
       - Reports text appeared/disappeared
       - Reports icon count change (new UI elements appeared?)
       - Verdict: "changed" or "unchanged"
    2. EXPECT MODE (expected_texts given): Check specific content exists
       - Each expected text is checked via substring match in OCR results
       - Also checks if GPA detected reasonable number of UI elements
       - Verdict: "found" or "missing: [...]"
    3. BASELINE MODE (neither given): Just report what's detected
       - Returns raw detection counts for the LLM to interpret

    Args:
        img_path: Current screenshot to verify
        before_img_path: Previous screenshot for diff (optional)
        expected_texts: List of strings expected on the page (optional)
        min_icon_change: Minimum icon count change to consider "changed" (default 0)

    Returns: dict with:
        - verdict: "changed"|"unchanged"|"found"|"missing"|"detected"
        - icon_count: Number of GPA-detected UI elements
        - text_count: Number of OCR-detected text elements (0 if OCR unavailable)
        - texts: List of detected text labels (empty if no OCR)
        - details: Human-readable summary
        - diff: (only in DIFF mode) {text_appeared, text_disappeared, icon_delta}
        - missing: (only in EXPECT mode) List of expected texts not found
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    import ui_detector

    # Always run both detectors (OCR gracefully degrades)
    icons, texts, merged, img_w, img_h = ui_detector.detect_all(img_path)
    _tracker_auto_tick("detector_calls")
    _tracker_auto_tick("ocr_calls")

    text_labels = [e.get("label", "").strip() for e in texts if e.get("label", "").strip()]
    result = {
        "icon_count": len(icons),
        "text_count": len(texts),
        "merged_count": len(merged),
        "texts": text_labels,
    }

    # --- DIFF MODE ---
    if before_img_path:
        before_icons, before_texts, _, _, _ = ui_detector.detect_all(before_img_path)
        _tracker_auto_tick("detector_calls")
        _tracker_auto_tick("ocr_calls")

        before_text_set = set(e.get("label", "").strip() for e in before_texts if e.get("label", "").strip())
        after_text_set = set(text_labels)

        text_appeared = after_text_set - before_text_set
        text_disappeared = before_text_set - after_text_set
        icon_delta = len(icons) - len(before_icons)

        has_text_change = bool(text_appeared or text_disappeared)
        has_icon_change = abs(icon_delta) > min_icon_change

        result["diff"] = {
            "text_appeared": sorted(text_appeared)[:10],
            "text_disappeared": sorted(text_disappeared)[:10],
            "icon_delta": icon_delta,
        }

        if has_text_change or has_icon_change:
            result["verdict"] = "changed"
            parts = []
            if text_appeared:
                parts.append(f"+{len(text_appeared)} texts")
            if text_disappeared:
                parts.append(f"-{len(text_disappeared)} texts")
            if icon_delta != 0:
                parts.append(f"icons {icon_delta:+d}")
            result["details"] = f"Page changed: {', '.join(parts)}"
        else:
            result["verdict"] = "unchanged"
            result["details"] = f"No significant change detected (icons: {len(icons)}, texts: {len(texts)})"

        return result

    # --- EXPECT MODE ---
    if expected_texts:
        all_text_lower = " ".join(text_labels).lower()
        missing = []
        for expected in expected_texts:
            if expected.lower() not in all_text_lower:
                missing.append(expected)

        if missing:
            result["verdict"] = "missing"
            result["missing"] = missing
            result["details"] = f"Missing expected content: {missing}. Found {len(icons)} icons, {len(texts)} texts."
        else:
            result["verdict"] = "found"
            result["details"] = f"All expected content found. {len(icons)} icons, {len(texts)} texts."

        return result

    # --- BASELINE MODE ---
    result["verdict"] = "detected"
    result["details"] = f"Detected {len(icons)} icons, {len(texts)} texts, {len(merged)} total elements."
    return result


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

    p_trans = sub.add_parser("transitions", help="Show recorded state transitions")
    p_trans.add_argument("--app", required=True)

    p_path = sub.add_parser("path", help="Find click path between states")
    p_path.add_argument("--app", required=True)
    p_path.add_argument("--component", required=True, help="from_state")
    p_path.add_argument("--contact", required=True, help="to_state")

    p_click_record = sub.add_parser("click_at", help="Click at coordinates and record state transition")
    p_click_record.add_argument("--app", required=True)
    p_click_record.add_argument("--label", required=True, help="What was clicked (for state naming)")
    p_click_record.add_argument("--x", type=int, required=True)
    p_click_record.add_argument("--y", type=int, required=True)

    p_commit = sub.add_parser("commit", help="Commit pending transitions (after workflow success)")
    p_commit.add_argument("--app", required=True)

    p_discard = sub.add_parser("discard", help="Discard pending transitions (workflow failed)")
    p_discard.add_argument("--app", required=True)

    p_pending = sub.add_parser("pending", help="Show pending (uncommitted) transitions")
    p_pending.add_argument("--app", required=True)

    p_drag = sub.add_parser("drag", help="Drag from (x1,y1) to (x2,y2) and record state")
    p_drag.add_argument("--app", required=True)
    p_drag.add_argument("--label", required=True, help="Description of drag action")
    p_drag.add_argument("--x1", type=int, required=True)
    p_drag.add_argument("--y1", type=int, required=True)
    p_drag.add_argument("--x2", type=int, required=True)
    p_drag.add_argument("--y2", type=int, required=True)
    p_drag.add_argument("--duration", type=float, default=0.5)

    p_cell = sub.add_parser("cell_select", help="Select spreadsheet cell range via OCR-based grid detection")
    p_cell.add_argument("--app", required=True, help="Spreadsheet app name (e.g. 'Microsoft Excel')")
    p_cell.add_argument("--range", required=True, dest="cell_range", help="Cell range like 'B2:D4' or single cell 'A1'")
    p_cell.add_argument("--hints", nargs="*", default=[], help="Known text=col:row hints, e.g. 'Alice=A:2 Age=B:1'")

    args = parser.parse_args()

    if args.command == "learn":
        learn_app(args.app, args.page)

    elif args.command == "find":
        # Match on full screen — returns screen logical coords directly
        found, lx, ly, conf = match_component(args.app, args.component)
        if found:
            print(json.dumps({"found": True, "screen_x": lx, "screen_y": ly,
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

    elif args.command == "transitions":
        transitions = get_transitions(args.app)
        if not transitions:
            print("No transitions recorded yet.")
        else:
            print(f"State transitions for {args.app}:")
            for t in transitions:
                from_s = t.get("from_state", t.get("from", "?"))
                action = t.get("action", f"click:{t.get('click', '?')}")
                to_s = t.get("to_state", t.get("to", "?"))
                count = t.get("count", 1)
                print(f"  {from_s} --{action}--> {to_s} (×{count})")

    elif args.command == "path":
        from_s = getattr(args, 'from_state', None) or args.component  # reuse --component for from
        to_s = getattr(args, 'to_state', None) or args.contact  # reuse --contact for to
        path = find_path(args.app, from_s, to_s)
        if path is None:
            print(f"No path from '{from_s}' to '{to_s}'")
        elif not path:
            print(f"Already at '{to_s}'")
        else:
            print(f"Path from '{from_s}' to '{to_s}':")
            for action, next_state in path:
                print(f"  → {action} → {next_state}")


    elif args.command == "click_at":
        ok, msg, _ = click_and_record(args.app, args.label, args.x, args.y)
        print(f"{'✅' if ok else '❌'} {msg}")

    elif args.command == "drag":
        ok, msg, _ = drag_and_record(args.app, args.label,
                                      args.x1, args.y1, args.x2, args.y2,
                                      duration=args.duration)
        print(f"{'✅' if ok else '❌'} {msg}")

    elif args.command == "cell_select":
        # Parse hints: "Alice=A:2 Age=B:1" -> {"Alice": ("A", 2), "Age": ("B", 1)}
        hints = {}
        for h in args.hints:
            text, ref = h.split("=")
            col, row = ref.split(":")
            hints[text] = (col, int(row))
        ok, msg = cell_select_by_ocr(args.app, args.cell_range, hints=hints if hints else None)
        print(f"{'✅' if ok else '❌'} {msg}")

    elif args.command == "commit":
        n = confirm_transitions(args.app)
        print(f"Committed {n} transitions for {args.app}")

    elif args.command == "discard":
        n = discard_transitions(args.app)
        print(f"Discarded {n} pending transitions for {args.app}")

    elif args.command == "pending":
        pending = get_pending_transitions(args.app)
        if not pending:
            print("No pending transitions.")
        else:
            print(f"Pending transitions for {args.app}:")
            for f, c, t in pending:
                print(f"  {f} --{c}--> {t}")


if __name__ == "__main__":
    main()
