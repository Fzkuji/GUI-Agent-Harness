---
name: gui-agent
description: "Visually operate any application on macOS — native apps, browsers, or anything with a GUI window. Open apps, click buttons, type text, send messages, fill forms, navigate menus, all driven by visual UI detection. Use when the task requires interacting with what's on screen."
---

# GUI Agent Skill

You ARE the agent loop. Every GUI task follows this flow, in order:

```
INTENT MATCH → OBSERVE → ENSURE APP READY → ACT → VERIFY → SAVE WORKFLOW → REPORT
```

## agent.py — Unified Entry Point

**All GUI operations go through `scripts/agent.py`.** Do not call `app_memory.py` or `gui_agent.py` directly.

```bash
source ~/gui-agent-env/bin/activate

# Core operations
python3 scripts/agent.py open --app AppName              # Open/activate app
python3 scripts/agent.py learn --app AppName             # Learn new app (YOLO + OCR → save components)
python3 scripts/agent.py detect --app AppName            # Detect + match known components
python3 scripts/agent.py click --app AppName --component ButtonName  # Click known component
python3 scripts/agent.py list --app AppName              # List all known components
python3 scripts/agent.py read_screen --app AppName       # Screenshot + OCR
python3 scripts/agent.py wait_for --app AppName --component X        # Poll until component appears
python3 scripts/agent.py cleanup --app AppName           # Remove duplicates + unlabeled

# Messaging
python3 scripts/agent.py send_message --app WeChat --contact "小明" --message "明天见"
python3 scripts/agent.py read_messages --app WeChat --contact "小明"

# Browser
python3 scripts/agent.py navigate --url "https://example.com"

# Workflows
python3 scripts/agent.py workflows --app AppName         # List saved workflows for app
python3 scripts/agent.py all_workflows                   # List all workflows (app + meta)
```

**agent.py automatically handles:**
- New app → `learn` → `plan` (detect + analyze + create workflow)
- Known app → `eval` (template match check; ≥80% → proceed, <80% → re-learn)
- Error → `plan` (re-learn + analyze + new plan)
- Chinese aliases: 微信→WeChat, 浏览器→Chrome
- Window activation before operating

---

## Execution Flow

### STEP -1: INTENT MATCHING

When you receive a GUI task, BEFORE doing anything:

1. **Identify the target app** from the user's request
2. **List existing workflows**: `python3 agent.py workflows --app AppName`
3. **Match intent to workflow** — use semantic understanding, not string matching:
   - "清理电脑" → `smart_scan_cleanup`
   - "帮我扫一下垃圾" → also `smart_scan_cleanup`
   - "看看 Claude 用量" → `check_usage`
4. **If matched**: Load workflow, skip to STEP 0 with steps as plan
5. **If no match**: Proceed normally, save workflow after success

### STEP 0: OBSERVE

Before ANY task, FIRST observe the current state:

1. **Call `session_status`** — record context size for token delta reporting later
2. Screenshot the screen
3. What app is in the foreground? Is the target app visible?
4. What page/state is the app in?
5. Any popups, dialogs, overlays blocking?

Do not skip this. Do not assume you know the state from last time. The screen may have changed since your last interaction — always look before you act.

### STEP 1: ENSURE APP READY

Every time you interact with a GUI app, check memory FIRST:

```
agent.py gets a task → ensure_app_ready(app, workflow, required_components)
  │
  ├── App never learned?
  │     → Full learn (YOLO + OCR → save ~20-30 components)
  │
  ├── App learned, but this workflow/page is NEW?
  │     → Learn this specific page (e.g., 'malware_removal')
  │     → Existing pages preserved, new page added
  │
  └── App learned, workflow known → template match:
        ├── Match ≥ 80% → memory good, proceed
        └── Match < 80% → incremental learn (update changed components)
```

This is YOUR responsibility. Do not wait for the user to ask you to learn. If `memory/apps/<appname>/` doesn't exist, run `learn` before operating.

For browsers: also check `memory/apps/<browser>/sites/<domain>/`. New website → `learn_site`.

### STEP 2: LEARN (when needed)

Learning detects and saves all UI components for future template matching:

```
1. Activate the app, ensure window is reasonably sized (≥800x600)
2. Run: python3 agent.py learn --app AppName
3. System automatically:
   a. Captures window screenshot (screencapture -l <windowID>)
   b. Runs GPA-GUI-Detector (YOLO) → icons, buttons, UI elements
   c. Runs Apple Vision OCR → text labels, menus
   d. Merges results with IoU dedup
   e. Crops each element → saves to memory/apps/<appname>/components/
   f. Reports unlabeled icons
4. Agent identifies all components:
   a. Use `image` tool to view each cropped image (batch up to 20)
   b. For each: read text, describe icon, determine actual name
   c. ⚠️ PRIVACY CHECK: personal info (username, email, avatar) → DELETE
   d. Verify _find_nearest_text names (often wrong in dense UIs)
   e. Rename: app_memory.py rename --old X --new Y
5. After identification + task complete:
   a. Run: agent.py cleanup --app AppName
   b. Remove dynamic content (timestamps, message previews)
   c. Keep ONLY fixed UI elements
6. Result: ~20-30 named, fixed UI components per page
```

`_find_nearest_text` is a hint, not truth — always verify by viewing the cropped image.

#### Component Filtering

Only save **stable UI elements** that look the same next session:

**SAVE** (stable):
- Sidebar elements (left ~15% of window)
- Toolbar elements (top ~12% of window)
- Footer elements (bottom ~12% of window)
- Any element with OCR text label

**SKIP** (dynamic):
- Tiny elements (< 25×25 pixels)
- Content area icons without labels
- Temporary content that changes every session

**Naming convention**:
- Has OCR label → label as filename (`Search.png`, `Settings.png`)
- No label + stable region → `unlabeled_<region>_<x>_<y>.png`
- No label + content area → **SKIP** (don't save)

#### What to KEEP vs REMOVE

The golden rule: **only save things that look the same next time you open the app.**

**KEEP** (fixed UI — same every time):
- Sidebar navigation icons (chat, contacts, discover, favorites)
- Toolbar buttons (search, add, settings, share screen)
- Input area controls (emoji, file, voice, sticker buttons)
- Window controls (close, minimize, fullscreen)
- Tab/section headers, fixed logos

**REMOVE** (dynamic — different every session):
- Chat message text and previews
- Timestamps (17:14, Yesterday, 03/10)
- User avatars in chat list (they move as chats reorder)
- Sticker/emoji content in messages
- Notification badges/counts
- Contact names in chat list (OCR detects them fresh each time)
- Web page content (articles, search results, feed items)
- Text >15 chars in content area (likely content, not UI)
- Profile pictures and photos

**Quick test**: "Will this element be in the exact same place with the exact same appearance tomorrow?" → KEEP. Otherwise → REMOVE.

#### Memory Rules

1. **Filename = content**: `chat_button.png`, NOT `icon_0_170_103.png`
2. **Dedup**: similarity > 0.92 = duplicate → keep ONE copy
3. **Cleanup**: `agent.py cleanup --app AppName` removes duplicates + unlabeled
4. **Per-app, per-page**: each app has its own memory directory
5. **Privacy**: components with personal info → delete, never save

#### Post-Learn Checklist

- [ ] No `unlabeled_` files remain
- [ ] No timestamps, message previews, or chat content saved
- [ ] Each filename describes what the component IS, not where it IS
- [ ] No duplicate icons
- [ ] ~20-30 components per page (not 60+)

### STEP 3: ACT

Now execute the actual task. Detection priority: **Template Match (0.3s) → OCR (1.6s) → YOLO (0.3s) → LLM (last resort)**. Always use the cheapest method that works.

#### Pre-Click Verify (before every click)

1. Is the element actually on screen RIGHT NOW?
2. Is it the CORRECT element (not something with a similar name in another window)?
3. Am I clicking inside the correct app window bounds?
4. If ANY answer is NO → re-observe first. Do not click.

#### Clicking a Known Component

```
1. Capture window screenshot
2. Template match against saved icon (matchTemplate, threshold=0.8)
3. If matched (conf > 0.8):
   a. Get relative coords from match
   b. Convert to screen coords: screen = window_pos + relative
   c. Verify: coords within window bounds?
   d. Click: cliclick c:<screen_x>,<screen_y>
4. If not matched:
   a. Run full detection (YOLO + OCR)
   b. LLM identifies target element
   c. Save new component to memory (auto-learn)
   d. Click the identified element
```

#### Pre-Send Verify (before sending messages)

This exists because of a real bug that sent messages to the wrong person.

1. OCR the chat HEADER area (top 120px of main content) — is the correct contact open?
2. Is the message text in the input field?
3. If either is NO → ABORT. Do not send.

Why: template matching "ContactName" could match a group chat, forwarded message, or another app's window. Only the chat header reliably shows who you're actually talking to.

#### Sending a Message (e.g., WeChat)

```
1. PREPARE
   a. Activate app, get window bounds
   b. ALL subsequent OCR/clicks MUST be within these bounds

2. NAVIGATE TO CONTACT
   a. Contact visible in sidebar? → click it
   b. Not visible → search:
      click search bar → paste name → wait 1s → click result

3. ⚠️ VERIFY CONTACT (mandatory)
   a. OCR the chat HEADER — confirm correct name
   b. Wrong contact? → ABORT, do NOT type anything

4. TYPE MESSAGE (only after verify passes)
   a. Click input field
   b. Paste message (pbcopy + Cmd+V, NOT cliclick type for CJK)

5. SEND: cliclick kp:return

6. VERIFY SENT: OCR chat area, confirm first 10 chars visible
```

#### Waiting for Async UI Changes

When an action triggers a slow process (scan, download, loading):

1. Use `wait_for`: `python3 agent.py wait_for --app AppName --component ComponentName`
2. Template match polls every 10s (~0.3s/check), 120s timeout
3. On success → returns coordinates, proceed
4. On timeout → saves screenshot. **Do NOT blind-click** — inspect and decide
5. Never use `sleep(60)` + blind click — always verify target exists first

### STEP 4: POST-ACTION VERIFY

After any click/type/send:
1. Screenshot again
2. Did the expected change happen?
3. Am I in the expected next state?
4. If NOT → re-observe and decide

### STEP 5: SAVE WORKFLOW

After completing a multi-step task successfully:

1. Check if a workflow already exists for this task
2. If not → save it:
   ```python
   save_workflow("CleanMyMac X", "smart_scan_cleanup", [
       {"action": "open", "target": "CleanMyMac X"},
       {"action": "click", "target": "Start_Over", "note": "only if on results page"},
       {"action": "click", "target": "Scan", "note": "bottom center button"},
       {"action": "wait_for", "target": "Run", "timeout": 120},
       {"action": "click", "target": "Run"},
       {"action": "wait_for", "target": "Ignore", "timeout": 30, "note": "quit apps dialog"},
       {"action": "click", "target": "Ignore", "note": "skip quitting apps"},
   ], notes=["Ignore dialog appears if Chrome/Discord running"])
   ```
3. If exists → update if you learned something new
4. Names: snake_case, descriptive (`smart_scan_cleanup`, `check_usage`)
5. Description: one-line, **max 30 words**

#### Running a Known Workflow

Do NOT blindly replay all steps. Instead:
1. Observe current state FIRST
2. Where in the workflow am I now?
3. Skip steps already done (e.g., scan finished → skip to Run)
4. Execute ONLY the next needed step
5. After each step: verify state changed
6. State doesn't match any step → STOP, trigger plan (learn + analyze)

#### Meta-Workflows (Cross-App Orchestration)

Meta-workflows are **pure orchestration** — ONLY `call` steps referencing other workflows. No raw actions allowed.

Rules:
1. Every step = `{"action": "call", ...}` — no exceptions
2. Each call specifies all params the called workflow needs
3. Use `output_as` for inter-step data passing

```python
save_meta_workflow("share_article_to_wechat", [
    {"action": "call", "app": "Chrome", "workflow": "copy_page_content",
     "params": {"url": "..."}, "output_as": "$article"},
    {"action": "call", "app": "WeChat", "workflow": "send_message",
     "params": {"contact": "John", "content": "$article"}},
], description="Copy Chrome article and send via WeChat")
```

- Max nesting depth: 5
- Single app task → `save_workflow`; cross-app composition → `save_meta_workflow`
- Listing: `python3 agent.py all_workflows`

### STEP 6: REPORT

**Every GUI task ends with a report. No exceptions.**

`agent.py` prints `⏱ Completed (X.Xs)` automatically. You also report:

```
⏱ 45.2s | 📊 +10k tokens (85k→95k) | 🔧 3 screenshots, 2 clicks, 1 learn
```

How: compare `session_status` from STEP 0 (before) vs now (after).

---

## Safety Rules

These exist because of real bugs. Each rule has a reason.

1. **Verify before sending** — A template match for "ContactName" once matched a group chat instead of the private chat. Always OCR the chat header.

2. **Stay within window bounds** — Without filtering OCR by window region, clicks landed on apps behind the target window. Get bounds first, filter everything.

3. **No wrong-app learning** — A click outside the target window was once saved as a template. Validate bounds before auto_learn.

4. **Reject tiny templates** — Templates <30×30 pixels produce false matches everywhere.

5. **LLM never provides coordinates** — You decide WHAT to click by name. Detection tools provide WHERE (coordinates). Never hardcode or estimate pixel positions.

6. **Never send screenshots to conversation** — Screenshots are for internal detection only.

---

## Key Principles

1. **Memory first, detect second** — template match before YOLO+OCR
2. **Template > OCR > YOLO > LLM** — cheapest method first
3. **Relative coordinates** — all positions relative to window top-left, never hardcode screen positions
4. **Window-based, not screen-based** — capture and operate within target window only (`screencapture -l <windowID>`)
5. **Paste > Type** for CJK text and special chars (`LANG=en_US.UTF-8 pbcopy` + Cmd+V)
6. **Learn incrementally** — save new components to memory after each interaction
7. **Integer coordinates only** — cliclick requires integers
8. **Learn once, match forever** — UI positions are stable; no need to re-detect unless app updates

---

## macOS Reference

### Coordinate System

- **Screen**: top-left origin (0,0), logical pixels (Retina physical ÷ 2)
- **Window**: relative to window's top-left corner
- **Retina**: screenshots are 2x physical pixels; divide by 2 for logical coordinates
- **cliclick**: uses screen logical pixels, integer only
- **Formula**: `screen_x = window_x + relative_x`, `screen_y = window_y + relative_y`

### Window Management

```bash
# Get window bounds (position + size)
osascript -e 'tell application "System Events" to tell process "AppName" to return {position, size} of window 1'

# Get window ID for screencapture (uses Swift CGWindowListCopyWindowInfo — see ui_detector.py)

# Capture specific window only
screencapture -x -l <windowID> output.png

# Activate app
osascript -e 'tell application "AppName" to activate'

# Resize window
osascript -e 'tell application "System Events" to tell process "AppName" to set size of window 1 to {900, 650}'
```

### Input Methods

```bash
# Click (logical screen coords, integers)
/opt/homebrew/bin/cliclick c:<x>,<y>

# Type ASCII only
cliclick t:"text"

# Paste CJK/special chars
LANG=en_US.UTF-8 pbcopy <<< "中文"
osascript -e 'tell app "System Events" to keystroke "v" using command down'

# Key press (return, esc, tab, delete, space, arrow-*, f1-f16)
cliclick kp:return

# Keyboard shortcut
osascript -e 'tell app "System Events" to keystroke "v" using command down'
```

### Browser Automation

Browsers are a **two-layer** system — same app, different content per site:

1. **Browser chrome** (tabs, address bar, bookmarks) — fixed, learn once like any app
2. **Web page content** — different per site, need per-site memory

```
memory/apps/google_chrome/
├── profile.json          # Browser chrome UI
├── components/           # Browser UI icons
└── sites/                # Per-website memory
    ├── 12306.cn/
    │   ├── profile.json  # Site-specific elements
    │   ├── components/   # Site buttons, nav
    │   └── pages/
    └── google.com/
```

**Operation flow:**
1. Learn browser chrome once → saves address bar, tab controls, etc.
2. Navigate: click address bar → paste URL → Enter
3. New website: wait for load → detect page content area → save fixed site UI (nav, search, buttons)
4. Operate: template match site elements → OCR text → click

**Save**: navigation bars, menus, search boxes, filter/sort controls, login buttons, logos.
**Don't save**: search results, article content, prices, ads, user-generated content.

#### Browser Input Quirks

- **Autocomplete fields** (e.g., 12306 station selector): typing alone is NOT enough — must click the dropdown suggestion
- **Chinese input**: System IME interferes with website autocomplete. Switch to English input, type pinyin, let website autocomplete handle it
- **Cmd+V in web forms**: May garble text. Use `cliclick t:text` for ASCII/pinyin
- **Date pickers**: Usually need to click calendar UI, not type a date string

---

## Memory System

### Directory Structure

```
memory/apps/<appname>/
├── profile.json        # Component registry + page/region/overlay structure
├── summary.json        # App overview
├── components/         # Cropped component images (PNG)
├── pages/              # Annotated screenshots
└── workflows/          # Saved workflow sequences

memory/meta_workflows/  # Cross-app orchestration
```

### Profile Structure (profile.json)

```json
{
  "app": "AppName",
  "window_size": [w, h],
  "pages": {
    "main": {
      "fingerprint": { "expect_text": ["Chat", "Cowork", "Code"] },
      "regions": {
        "sidebar": { "position": "left", "stable": true, "components": ["Search"] },
        "toolbar": { "position": "top", "stable": true, "components": ["Chat_tab"] },
        "content": { "position": "center", "stable": false, "components": [] }
      },
      "transitions": { "Cmd+,": { "to": "settings", "type": "page" } }
    }
  },
  "overlays": {
    "account_menu": {
      "trigger": "profile_area",
      "parent_page": "main",
      "fingerprint": { "expect_text": ["Settings", "Log out"] },
      "components": ["Settings_link"],
      "dismiss": ["Esc", "click_outside"]
    }
  },
  "components": {
    "Search": { "type": "icon", "rel_x": 116, "rel_y": 144, "page": "main", "region": "sidebar" }
  }
}
```

### Key Concepts

| Concept | Description | Example |
|---------|------------|---------|
| **Page** | Full UI state, mutually exclusive | main, settings |
| **Region** | Area within a page | sidebar, toolbar, content |
| **Overlay** | Temporary popup over a page | account menu, context menu |
| **Fingerprint** | Text to identify current page | ["General", "Account"] → settings |
| **Transition** | What happens on click | click Usage → stays on settings |

### Page-Aware Matching

1. OCR the screen → get visible text
2. Match fingerprints → identify current page
3. Only match components belonging to that page
4. Match rate is calculated per-page, not overall

### Handling Unknown UI States

```
1. Take screenshot
2. Run detection (YOLO + OCR)
3. Compare against known page layout
4. New elements found → crop, save, identify, update memory
5. Expected elements missing → maybe different page → learn --page <name>
```

---

## Detection Stack

| Detector | Finds | Speed | Best for |
|----------|-------|-------|----------|
| **GPA-GUI-Detector (YOLO)** | Icons, buttons, UI elements | 0.3s | Any app's buttons/controls |
| **Apple Vision OCR** | Text (Chinese + English) | 1.6s | Labels, menus, content |
| **Template Match** | Previously seen components | 0.3s | Known elements (conf ≈ 1.0) |

---

## Explore (Manual Trigger)

When you want to analyze an app WITHOUT a specific goal:
- User triggers: `agent.py explore --app AppName`
- Screenshots, runs YOLO + OCR, saves to memory
- NOT for workflow execution (use eval/plan)

---

## Scene Index

| Scene | Location | Goal |
|-------|----------|------|
| **Atomic Actions** | `actions/_actions.yaml` | click, type, paste, detect... |
| **WeChat** | `scenes/wechat/` | Send/read messages, scroll history |
| **Discord** | `scenes/discord.yaml` | Send/read messages |
| **Telegram** | `scenes/telegram.yaml` | Send/read messages |
| **1Password** | `scenes/1password.yaml` | Retrieve credentials |
| **VPN Reconnect** | `scenes/vpn-reconnect.yaml` | Reconnect GlobalProtect VPN |
| **App Exploration** | `scenes/app-explore.yaml` | Map an unfamiliar app's UI |

Scene files are reference only — not executable scripts.

---

## Setup (New Machine)

```bash
git clone https://github.com/Fzkuji/GUIClaw.git
cd GUIClaw
bash scripts/setup.sh
```

Installs: cliclick, Python 3.12, PyTorch, ultralytics, OpenCV, GPA-GUI-Detector (40MB to `~/GPA-GUI-Detector/`)

Grant **Accessibility permissions**: System Settings → Privacy & Security → Accessibility → Add Terminal / OpenClaw

### Scripts

| Script | Purpose |
|--------|---------|
| `agent.py` | **Unified entry point** — all GUI ops go through here |
| `ui_detector.py` | Detection engine (YOLO + OCR + Swift window info) |
| `app_memory.py` | Per-app visual memory (learn/detect/click/verify) |
| `gui_agent.py` | Legacy task executor (send_message, read_messages) |
| `template_match.py` | Template matching utilities |
| `setup.sh` | First-run setup — installs all dependencies |

All scripts use venv: `source ~/gui-agent-env/bin/activate`

### Models

| Model | Size | Auto-installed | Purpose |
|-------|------|----------------|---------|
| **GPA-GUI-Detector** | 40MB | ✅ `~/GPA-GUI-Detector/model.pt` | UI element detection |
| OmniParser V2 | 1.1GB | ❌ | Alt detection (weaker on desktop) |
| GUI-Actor 2B | 4.5GB | ❌ | End-to-end grounding (experimental) |

### Path Conventions

- Venv: `~/gui-agent-env/`
- Model: `~/GPA-GUI-Detector/model.pt`
- Memory: `<skill-dir>/memory/apps/<appname>/`
- All paths use `os.path.expanduser("~")`, NOT hardcoded usernames

### File Structure

```
gui-agent/
├── SKILL.md              # This file
├── actions/              # Atomic operations
│   └── _actions.yaml
├── memory/               # All visual memory (gitignored)
│   ├── apps/<appname>/   # Per-app memory
│   │   ├── profile.json, components/, workflows/
│   └── meta_workflows/   # Cross-app orchestration
├── scripts/              # Core scripts
│   ├── agent.py, ui_detector.py, app_memory.py, gui_agent.py, template_match.py
├── docs/
└── README.md
```
