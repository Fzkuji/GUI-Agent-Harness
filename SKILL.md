---
name: gui-agent
description: "ALL interactions with ANY app — whether built-in (Finder, Safari, System Settings) or third-party (WeChat, Chrome, Slack) — MUST go through this skill. Clicking, typing, reading content, sending messages, navigating menus, filling forms: everything uses visual detection (screenshot → template match → click). This is the ONLY way to operate apps. Never bypass with CLI commands, AppleScript, or Accessibility APIs."
---

# GUI Agent Skill

## 🔴 VISION vs COMMAND — When to Use What (READ FIRST)

Every GUI task involves two kinds of operations. **Know the boundary.**

### MUST be vision-based (screenshot → detect → act)
- **Determining current state** — "What page am I on? What's visible?"
- **Locating click targets** — buttons, links, menu items, icons → coordinates MUST come from GPA-GUI-Detector / OCR / template matching
- **Verifying results** — "Did my action work? Did the page change?"
- **Handling unexpected UI** — popups, cookie banners, error pages, CAPTCHA
- **Reading content** — extracting text/data from the screen
- **Any spatial decision** — "where on screen is X?"

### MAY use keyboard shortcuts / CLI commands (non-visual)
- **Keyboard shortcuts** — Ctrl+L (address bar), Ctrl+T (new tab), Ctrl+W (close tab), Ctrl+C/V (copy/paste), Page Down (scroll), etc.
- **Text input** — typing URLs, search queries, form values (pyautogui.typewrite / hotkey)
- **System commands** — launching apps, setting resolution (xrandr), checking processes

### ⚠️ THE RULE: Decision = Visual, Execution = Best Tool
```
✅ CORRECT workflow:
   1. Screenshot → detect/OCR → understand current state (VISUAL)
   2. Decide what to do next based on what you SEE (VISUAL)
   3. Execute: click detected coordinates OR use keyboard shortcut (BEST TOOL)
   4. Screenshot → verify the result (VISUAL)

❌ WRONG workflows:
   - Skip observation, go straight to keyboard commands (no visual basis)
   - Know the answer beforehand, type it without looking (not agent behavior)
   - Use CLI to navigate instead of interacting with the UI
   - Chain multiple actions without visual verification between them
```

### Examples
```
✅ "I see Chrome is open on United Airlines homepage" → screenshot confirms this
   → "I see 'Travel info' in the nav bar at (661, 188) from OCR" → click (661, 188)
   → screenshot → "dropdown opened, I see 'Baggage' link at (650, 250)" → click

❌ "I know the URL is united.com/en/us/checked-bag-fee-calculator"
   → Ctrl+L → type URL → Enter → done
   (No visual observation drove the decision — this is command-line with extra steps)

✅ "I see I'm in Chrome" (visual) → Ctrl+L to focus address bar (shortcut is fine)
   → "I need to search for baggage calculator" → type search query (input is fine)
   → screenshot → verify results (visual)
   (Visual observation → shortcut for efficiency → visual verification)
```

**Bottom line: You must LOOK before you ACT. Every action must be justified by what you observed on screen. Shortcuts are tools for execution, not substitutes for observation.**

### 🔍 Three Visual Methods — When to Use Each

You have three ways to "see" the screen. They serve different purposes. **Do not mix up their roles.**

#### Method 1: OCR (`detect_text`)
- **What it does**: Uses Apple Vision framework to read all text on screen
- **Returns**: Each text element with: `label` (the text), `cx`/`cy` (center coordinates), `x`/`y`/`w`/`h` (bounding box)
- **Use when**: Finding a specific text label, link, menu item, button with text, or any UI element that has readable text
- **Strengths**: Precise text content + exact coordinates; most UI elements have text labels so this works for the majority of cases
- **Limitations**: Cannot detect non-text elements (icons without labels, graphical buttons, images)
- **✅ Provides click coordinates**: YES — use `cx`, `cy` from the result to click

#### Method 2: GPA-GUI-Detector (`detect_icons`)
- **What it does**: Runs a YOLO-based UI element detection model (Salesforce/GPA-GUI-Detector)
- **Returns**: Each detected UI component with: `cx`/`cy` (center coordinates), `x`/`y`/`w`/`h` (bounding box), `confidence` score. Label is always `null` (it detects position/shape only, not semantics)
- **Use when**: Finding buttons, icons, checkboxes, input fields, or other UI components that are identifiable by their shape/position rather than text
- **Strengths**: Finds all interactive elements regardless of whether they have text; good for icon-only buttons (hamburger menu, close button, three-dot menu, etc.)
- **Limitations**: No semantic labels — you get bounding boxes but don't know WHAT each box is. Must combine with OCR or image tool to identify which box is which
- **✅ Provides click coordinates**: YES — use `cx`, `cy` from the result to click

#### Method 3: image tool (LLM vision)
- **What it does**: Sends a screenshot to the LLM for visual understanding
- **Returns**: Natural language description of what's on screen — page layout, element meanings, spatial relationships, current state
- **Use when**: You need to UNDERSTAND the screen — "What page is this?", "What does this dialog mean?", "Which of the detected elements is the one I need?", "What should my next step be?"
- **Strengths**: Semantic understanding, can interpret complex layouts, read visual context that OCR/detector miss
- **Limitations**: ⛔ **NEVER provides reliable coordinates**. The LLM may describe positions ("top right corner", "third button") but these are ESTIMATES, not measured coordinates. NEVER use positions from image tool output for clicking.
- **⛔ Does NOT provide click coordinates**: NO — NEVER extract coordinates from image tool responses. ALWAYS go back to OCR/detector results for the actual click position.

#### Workflow: Unfamiliar → Familiar (progressive)

**Phase 1: First encounter / unfamiliar page (DEFAULT)**

Use all three methods together. This is the starting point for any new page or uncertain situation.

```
Step 1: Take screenshot
Step 2: Run OCR (detect_text) on the screenshot
        → get all text elements with their coordinates
        → read the output: you now know what text is on screen and where
Step 3: Send the screenshot to image tool
        → LLM sees the page visually
        → understand: what page is this? what's the layout? what elements matter?
        → ⛔ DO NOT use any coordinates from the image tool response
Step 4: Run GPA-GUI-Detector (detect_icons) on the screenshot
        → get all UI component bounding boxes with coordinates
Step 5: LLM decides what to click
        → combine: OCR text labels + visual understanding + detector positions
        → identify the target element
        → get its coordinates from OCR or detector results (NEVER from image tool)
        → execute the click at those coordinates
```

**Phase 2: Familiar page / repeated workflow (OPTIMIZATION)**

Once you've seen a page before and know what to expect, skip the image tool to save tokens.

```
Step 1: Take screenshot (but don't send to image tool)
Step 2: Run OCR + GPA-GUI-Detector on the screenshot
        → get text + coordinates as structured text data
Step 3: LLM reads the text output directly (no visual analysis needed)
        → identify the target element from text labels and positions
        → click using OCR/detector coordinates
```

**When to transition from Phase 1 to Phase 2:**
- You've successfully operated on this page/state before
- The OCR + detector text output gives you enough information to decide without seeing the screenshot
- You're confident about what elements to expect on this page

**When to fall back to Phase 1:**
- Something unexpected happened (wrong page, new popup, error)
- OCR + detector output doesn't make sense or seems incomplete
- You're unsure about the current state
- Whenever in doubt — Phase 1 is always safe

#### Summary of rules
- **OCR → coordinates ✅** — use for clicking text elements
- **GPA-GUI-Detector → coordinates ✅** — use for clicking non-text UI elements
- **image tool → understanding only ⛔ NO coordinates** — use for deciding WHAT to click, then get the WHERE from OCR/detector
- **Phase 1 is the safe default** — always start here, optimize to Phase 2 only when confident
- **Remote VMs (OSWorld)** — download screenshot to Mac, run OCR and/or detector locally, send coordinates back to VM. Same three methods, same rules, same phases.

---

You ARE the agent loop. Every GUI task follows this flow:

```
OBSERVE → ENSURE APP READY → ACT+SAVE (detect→match→save components→execute→diff→save transition) → REPORT
```

## Sub-Skills

Each step in the execution flow below has a corresponding sub-skill file. **When you reach that step, you MUST `read` the sub-skill file first.** This is not optional — the sub-skill contains the exact procedure and rules for that step.

| Step | Sub-Skill | Read when |
|------|-----------|-----------|
| **Observe** | `read {baseDir}/skills/gui-observe/SKILL.md` | MUST read before taking any screenshot or detecting state |
| **Learn** | `read {baseDir}/skills/gui-learn/SKILL.md` | MUST read before learning a new app or re-learning components |
| **Act + Memory** | `read {baseDir}/skills/gui-act/SKILL.md` | MUST read before any action. Includes detection, matching, execution, AND memory saving as one unified flow |
| **Memory (reference)** | `read {baseDir}/skills/gui-memory/SKILL.md` | Reference for memory structure (split storage: meta/components/states/transitions, forgetting, browser sites/) |
| **Workflow** | `read {baseDir}/skills/gui-workflow/SKILL.md` | MUST read before multi-step navigation or state graph operations |
| **Setup** | `read {baseDir}/skills/gui-setup/SKILL.md` | MUST read before first-time setup on a new machine |
| **Report** | `read {baseDir}/skills/gui-report/SKILL.md` | MUST read before tracking or reporting task performance |

## Core Commands

**exec timeout**: Always use `timeout=60` for GUI commands. Commands return immediately when done; the timeout only caps maximum wait.

```bash
source ~/gui-actor-env/bin/activate
cd ~/.openclaw/workspace/skills/gui-agent

# Observe
python3 scripts/agent.py learn --app AppName        # Detect + save components
python3 scripts/agent.py detect --app AppName        # Match known components
python3 scripts/agent.py list --app AppName          # List saved components

# Act
python3 scripts/agent.py click --app AppName --component ButtonName
python3 scripts/agent.py open --app AppName
python3 scripts/agent.py cleanup --app AppName

# State graph
python3 scripts/app_memory.py transitions --app AppName     # View state graph
python3 scripts/app_memory.py path --app AppName --component from_state --contact to_state  # Find route

# Messaging (prints guidance, agent executes step by step)
python3 scripts/agent.py send_message --app WeChat --contact "小明" --message "明天见"
```

## Execution Flow

### STEP 0: OBSERVE
→ **MUST `read {baseDir}/skills/gui-observe/SKILL.md` first**

Take screenshot. Run GPA-GUI-Detector + OCR to detect all UI elements. Use `image` tool only to **understand** the scene (not for coordinates).

### STEP 1: ENSURE APP READY
→ **MUST `read {baseDir}/skills/gui-learn/SKILL.md` first** (if learning needed)

If app not in memory → learn. If component not found → re-learn current state.

### STEP 2: ACT + SAVE (one unified step, per-click)
→ **MUST `read {baseDir}/skills/gui-act/SKILL.md` first**

gui-act defines the 7-sub-step flow for EACH click:

1. **DETECT** — screenshot → OCR + GPA-GUI-Detector
2. **MATCH** — compare against saved memory
3. **SAVE COMPONENTS** — new elements → `learn_from_screenshot()` (BEFORE clicking!)
4. **DECIDE & EXECUTE** — pick target → click at detected coordinates
5. **DETECT AGAIN** — screenshot after click (if needed to verify)
6. **DIFF** — compare before vs after
7. **SAVE TRANSITION** — `record_page_transition()` records state change

**Component saving happens BEFORE the click (step 3), not after.** This ensures memory is always populated even if the click fails.

Both save functions are automated — no manual cropping or JSON editing:
- `learn_from_screenshot(img_path, domain, app_name, page_name)` — auto-detects, crops, deduplicates, saves all components
- `record_page_transition(before_img, after_img, click_label, click_pos, domain)` — auto-diffs OCR, saves states + transition

For memory structure details (split storage format, forgetting mechanism, browser sites/): `read {baseDir}/skills/gui-memory/SKILL.md`

### STEP 3: REPORT

Report is mostly automatic (detect_all auto-starts tracker, functions auto-tick counters).
At the END of a GUI task, run this one command to generate and save the report:

```bash
source ~/gui-actor-env/bin/activate
python3 ~/.openclaw/workspace/skills/gui-agent/skills/gui-report/scripts/tracker.py report
```

This prints a one-line summary + saves full data to `logs/task_history.jsonl`.
If you forget, data is auto-saved next time tracker starts.

---

## ⛔ ABSOLUTE RULES (read every time, no exceptions)

**WHERE DO CLICK COORDINATES COME FROM?**

```
✅ ALLOWED coordinate sources:
   1. GPA-GUI-Detector (detect_icons) → bounding box center
   2. Apple Vision OCR (detect_text) → text bounding box center
   3. Template matching → saved component position

❌ FORBIDDEN:
   - LLM/vision model guessing coordinates ("it looks like it's around 500, 300")
   - Hardcoded pixel positions from memory or documentation
   - Coordinates from image tool analysis (image tool = understanding ONLY)
```

**Every click**: screenshot → run GPA-GUI-Detector and/or OCR → get coordinates from detection result → click that coordinate. No exceptions. If detection can't find the element, re-detect or re-learn — do NOT guess.

**This applies everywhere**: local Mac apps, remote VMs (OSWorld), any platform. For remote VMs: download screenshot to Mac → run detection locally → send click coordinates back to VM.

## Key Principles

1. **Vision-driven, no shortcuts** — screenshot → detect → match → click. Only allowed system calls: `activate` (bring to front), `screencapture`, `platform_input.py` (pynput click/type).
2. **Coordinates from detection only** — see ABSOLUTE RULES above. The `image` tool is for understanding ("what is this?", "which button should I click?"), NEVER for getting pixel coordinates.
3. **Not found = not on screen** — don't lower thresholds. Re-learn current state to discover what IS on screen.
4. **State graph drives navigation** — each click records a transition. Use `find_path()` to route between states.
5. **First time: screenshot + image. Repeat: detection only** — saves tokens on known workflows.
6. **Paste > Type** for CJK text
7. **Integer logical coordinates** — pynput uses screen logical pixels
8. **ALWAYS save to memory** — every GUI operation MUST save detection results, learned components, and state information to `memory/apps/<appname>/`. This is the core of the system. Even for one-off tasks or benchmarks (e.g., OSWorld), save what you learn about each app. Memory is local (gitignored) but essential — it's what makes GUIClaw learn and improve.

## Safety Rules

1. **Full-screen search + window validation** — match on full screen, reject matches outside target app's window bounds
2. **App switch detection** — `click_component` checks frontmost app after every click
3. **No wrong-app learning** — validate frontmost app before learn
4. **Reject tiny templates** — <30×30 pixels produce false matches
5. **Never send screenshots to chat** — internal detection only
6. **NEVER quit the communication app** — if a dialog asks to quit apps (like CleanMyMac's "Quit All"), NEVER quit Discord/Telegram/WhatsApp or whatever channel you're communicating through. Instead: click "Ignore" to skip. Quitting the comms app disconnects you from the user.
7. **Watch for new dialogs/windows** — clicking a button may spawn a new dialog or window. After clicking, check if a new window appeared and handle it before continuing.
8. **Every click uses `click_and_record` or `click_component`** — never raw `click_at()`. Every click must record a state transition.

## Input Methods (platform_input.py)

```python
from platform_input import click_at, paste_text, key_press, key_combo, screenshot, 
    activate_app, get_clipboard, set_clipboard, mouse_right_click
```

No cliclick. No osascript for input. pynput only.

## File Structure

```
gui-agent/
├── SKILL.md              # This file
├── skills/               # Sub-skills (read on demand)
├── scripts/
│   ├── agent.py          # CLI entry point
│   ├── app_memory.py     # Components, states, transitions, matching
│   ├── platform_input.py # Cross-platform input (pynput)
│   ├── ui_detector.py    # GPA-GUI-Detector + OCR detection
│   └── template_match.py # Legacy template matching
├── memory/               # Visual memory (gitignored but ESSENTIAL)
│   ├── apps/
│   │   ├── <appname>/
│   │   │   ├── meta.json          # Metadata (detect_count, forget_threshold)
│   │   │   ├── components.json    # Component registry + activity tracking
│   │   │   ├── states.json        # States defined by component sets
│   │   │   ├── transitions.json   # State transitions (dict, deduped)
│   │   │   ├── components/        # Cropped UI element templates
│   │   │   └── pages/             # Page screenshots
│   │   └── chromium/              # Browser example
│   │       ├── meta.json, components.json, states.json, transitions.json
│   │       ├── components/
│   │       ├── pages/
│   │       └── sites/             # ⭐ Each website = same 4-file structure
│   │           ├── united.com/
│   │           ├── delta.com/
│   │           └── ...
│   └── meta_workflows/
└── README.md
```
