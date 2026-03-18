---
name: gui-agent
description: "Control desktop GUI applications on macOS using visual detection, template matching, and cliclick. Use when asked to operate, click, type, or interact with any desktop application. NOT for web-only tasks (use browser tool) or simple file operations."
argument-hint: [app-name-and-task, e.g. "open WeChat and send message to 小明"]
allowed-tools: Read, Write, Edit, Bash(*), image, exec, process
---

# GUI Agent Skill

You ARE the agent loop: Observe → Decide → Act → Verify.

## Architecture Overview

```
User Intent ("click Connect button in GlobalProtect")
    │
    ▼
┌─────────────────────────────────────┐
│  1. LOCATE ELEMENT                  │
│     Try in order:                   │
│     ① Template Match (0.3s)         │  → known components from memory
│     ② OCR text search (1.6s)        │  → find by visible text
│     ③ YOLO detection (0.3s)         │  → icons, buttons, UI elements
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. MATCH (app_memory.py)           │
│     Template matching vs memory     │  → known components (0.3s, conf=1.0)
│     If matched → use stored coords  │
│     If unknown → LLM identifies     │  → save to memory for next time
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. ACT (gui_agent.py + cliclick)   │
│     Relative coords + window pos    │  → screen coordinates
│     Pre-action verify               │  → correct contact? correct field?
│     Execute click/type/key          │
│     Post-action verify (OCR)        │
└─────────────────────────────────────┘
```

## Detection Stack

| Detector | What it finds | Speed | Best for |
|----------|--------------|-------|----------|
| **GPA-GUI-Detector** | Icons, buttons, UI elements | 0.3s | WeChat icons, any app's buttons |
| **Apple Vision OCR** | Text (Chinese + English) | 1.6s | Chat content, labels, menus |
| **Template Match** | Previously seen components | 0.3s | Known UI elements (conf=1.0) |

### Core Principles

**1. UI Positions Are Stable**
If the user hasn't changed their setup, UI element positions don't change between sessions.
Template matching a learned icon gives the same result every time.
No need to re-detect or re-learn unless the app updates or window resizes.
Learn once → match forever → click instantly.

**2. Event-Driven, Not Sleep-Based**
NEVER use fixed sleep() to wait. Use short polling:
- Screenshot every 1-2 seconds
- Template match or OCR check for expected target
- Target appears → proceed immediately
- Timeout after 30 seconds max

**3. Template Match First, Always**
If an icon is in memory, use template match (0.3s).
Do NOT run YOLO or full OCR for known components.
Only fall back to detection for unknown/new elements.

**4. Window-Only Screenshots**
Always capture the target window only (screencapture -l <windowID>).
Never use fullscreen screenshots for detection — too slow, causes cross-app confusion.

### When to use what — Decision Tree

**ALWAYS try methods in this order:**

```
Step 1: Is the element in template memory?
  → app_memory.py find --app AppName --component name
  → If matched (conf > 0.8) → click it. Done.

Step 2: Run full detection (YOLO + OCR)
  → ui_detector.py --app AppName
  → GPA-GUI-Detector finds components/buttons
  → Apple Vision OCR finds text
  → Merge, save to memory for next time

Step 3: Last resort — screenshot + ask LLM
  → Take screenshot, send to vision model for analysis
  → Only if all above methods fail
```

### Detection Stack

GPA-GUI-Detector + Apple Vision OCR are used for all apps by default:
- **YOLO**: finds icons, buttons, and other visual UI elements
- **OCR**: finds text labels, menu items, chat content

## App Visual Memory

Each app gets a memory directory with learned components:

```
memory/apps/<appname>/
├── profile.json          # Component registry + page/region/overlay structure
├── summary.json         # App overview (workflows)
├── components/         # Cropped component images (PNG)
│   ├── Search.png
│   ├── Chat_tab.png
│   └── ...
├── pages/              # Per-page annotated screenshots
│   ├── main_annotated.jpg
│   └── settings_annotated.jpg
└── workflows/          # Saved workflow sequences
    └── <workflow_name>.json
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
        "sidebar": { "position": "left", "stable": true, "components": ["Search", "Ideas"] },
        "toolbar": { "position": "top", "stable": true, "components": ["Chat_tab"] },
        "content": { "position": "center", "stable": false, "components": [] }
      },
      "transitions": { "Cmd+,": { "to": "settings", "type": "page" } }
    },
    "settings": {
      "fingerprint": { "expect_text": ["General", "Account", "Usage"] },
      "regions": { ... },
      "transitions": { "Usage": { "to": "settings", "context": "usage" } }
    }
  },
  "overlays": {
    "account_menu": {
      "trigger": "profile_area",
      "parent_page": "main",
      "fingerprint": { "expect_text": ["Settings", "Log out"] },
      "components": ["Settings_link", "Log_out"],
      "dismiss": ["Esc", "click_outside"]
    }
  },
  "components": {
    "Search": { "type": "icon", "rel_x": 116, "rel_y": 144, "page": "main", "region": "sidebar", ... }
  }
}
```

### Key Concepts

| Concept | Description | Example |
|---------|------------|---------|
| **Page** | Full UI state, mutually exclusive | main, settings |
| **Region** | Area within a page | sidebar, toolbar, content |
| **Overlay** | Temporary popup over a page | account menu, context menu |
| **Fingerprint** | Text used to identify current page | ["General", "Account", "Usage"] → settings |
| **Transition** | What happens when component is clicked | click Usage → stays on settings page |

### Page-Aware Matching

When detecting/matching components:
1. OCR the screen → get visible text
2. Match fingerprints → identify current page
3. Only match components belonging to that page
4. Match rate is calculated per-page, not overall

### What Gets Saved

1. **components/** - Filtered YOLO-detected components (see filtering rules below)
2. **profile.json** - Component registry + page/region/overlay structure
3. **summary.json** - App overview with workflows

### Component Filtering Rules

Only save **stable UI elements** that will look the same next session:

**SAVE** (stable):
- Sidebar elements (left ~15% of window)
- Toolbar elements (top ~12% of window)
- Footer elements (bottom ~12% of window)
- Any element with OCR text label

**SKIP** (dynamic):
- Tiny elements (< 25×25 pixels)
- Content area icons without labels (e.g., folder icons in file list)
- Temporary content that changes every session

**Naming**:
- Has OCR label → use label as filename (`Search.png`, `AirDrop.png`)
- No label + stable region → `unlabeled_<region>.png`
- No label + content area → **SKIP** (don't save)

### Key Design Decisions

- **Relative coordinates**: All positions relative to window top-left, not screen
- **Window-based capture**: `screencapture -l <windowID>`, not fullscreen
- **Template matching first**: Check memory before running expensive detection
- **Learn once, match forever**: First detection saves templates; future ops use matching
- **Pre-action verification**: Always verify target before sending messages

### Memory Rules (MUST follow)

1. **Icon filename = content description**: `chat_button.png`, `search_bar.png`, NOT `icon_0_170_103.png`
   - If label is known (from OCR): use label as filename
   - If unknown: use `unlabeled_<region>_<x>_<y>.png` temporarily
   - After LLM identifies: `app_memory.py rename --old unlabeled_xxx --new actual_name`

2. **Dedup**: Never save duplicate icons. Before saving, compare against existing icons (similarity > 0.92 = duplicate). Keep ONE copy.

3. **Cleanup**: Run `app_memory.py cleanup --app AppName` to remove duplicates. Dynamic content (chat messages, timestamps, avatars in chat) should be periodically cleaned.

4. **Per-app, per-page**: Each app has its own memory directory. Different pages (main, chat, settings) get separate page layouts.

5. **Important vs unimportant**:
   - **Keep**: Fixed UI elements (buttons, icons, tabs, input fields, navigation)
   - **Clean**: Dynamic content (message text, timestamps, avatars in chat area, stickers)

### Learn Flow (MUST follow every time `learn` runs)

```
1. Capture window screenshot
2. Run GPA-GUI-Detector + Apple Vision OCR
3. For each detected element:
   a. Has OCR label? → use label as filename
   b. No label? → _find_nearest_text gives initial guess name
   c. Still no label? → "unlabeled_<region>_<x>_<y>"
   d. Check visual dedup (similarity > 0.92) → skip if duplicate
   e. Crop and save to components/
4. Agent MUST identify all components (including _find_nearest_text named ones):
   a. Use `image` tool to view each cropped component image
   b. Batch up to 20 images per `image` call
   c. For each image: read text, describe icon, determine actual name
   d. ⚠️ PRIVACY CHECK: if image contains personal info (username, email,
      avatar, account details, private data), DELETE it — do not keep as component
   e. Verify _find_nearest_text names are correct (they often mismatch in dense UIs)
   f. Rename: app_memory.py rename --old wrong_name --new actual_name
5. After ALL identification is complete and task is done:
   a. Run: agent.py cleanup --app AppName (removes remaining unlabeled)
   b. Remove dynamic content (timestamps, message previews, chat text)
   c. Keep ONLY fixed UI elements (buttons, icons, tabs, navigation, input fields)
6. Result: clean profile with ~20-30 named, fixed UI components per page
```

**Key rule**: `_find_nearest_text` is a HINT, not truth. Always verify by viewing the image.
**Privacy rule**: Components containing personal info (names, emails, avatars, account badges) must be deleted, not saved.

### What to KEEP vs REMOVE after learning

**The golden rule**: Only save things that will **look the same next time you open the app**. If it changes every session, don't save it.

**KEEP** (fixed UI elements — same every time):
- Sidebar navigation icons (chat, contacts, discover, favorites, etc.)
- Toolbar buttons (search, add, settings, share screen, etc.)
- Input area controls (emoji, file, voice, sticker buttons)
- Window controls (close, minimize, fullscreen)
- Tab/section headers
- Fixed logos and app icons

**REMOVE** (dynamic content — different every session):
- Chat message text and previews ("我好像到现在也就见到...")
- Timestamps (17:14, Yesterday, 03/10, etc.)
- User avatars in chat list (they move as chats reorder)
- Sticker/emoji content in messages
- Notification badges/counts
- Contact names in chat list (OCR detects them fresh each time)
- Web page content (articles, search results, feed items)
- Any text longer than ~15 chars in the main content area (likely content, not UI label)
- Profile pictures and photos in chat

**HOW TO JUDGE**: Ask yourself:
1. "Will this element be in the exact same place with the exact same appearance tomorrow?" → KEEP
2. "Is this a button/icon that I might need to click again?" → KEEP
3. "Is this just something someone typed/sent/posted?" → REMOVE
4. "Is this a webpage or feed item that will scroll away?" → REMOVE

### Post-Learn Checklist
After every `learn`, verify:
- [ ] No `unlabeled_` files remain (all identified or removed)
- [ ] No timestamps, message previews, or chat content saved
- [ ] Each icon filename describes what it IS, not where it IS
- [ ] No duplicate icons (run `cleanup` if needed)
- [ ] Profile has ~20-30 components per page (not 60+)

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

## How to Use (Unified Entry Point)

**All GUI operations go through `scripts/agent.py`:**

```bash
source ~/gui-agent-env/bin/activate

# Send a message
python3 scripts/agent.py send_message --app WeChat --contact "小明" --message "明天见"

# Click a component
python3 scripts/agent.py click --app WeChat --component search_bar_icon

# Read messages
python3 scripts/agent.py read_messages --app WeChat --contact "小明"

# Open an app
python3 scripts/agent.py open --app Discord

# Navigate browser
python3 scripts/agent.py navigate --url "https://example.com"

# Learn a new app (auto-runs if app not in memory)
python3 scripts/agent.py learn --app WeChat

# Detect + match known components
python3 scripts/agent.py detect --app WeChat

# List all known components
python3 scripts/agent.py list --app WeChat

# Screenshot + OCR
python3 scripts/agent.py read_screen --app WeChat
```

**agent.py automatically handles:**
- **New app** → `learn` → `plan` (detect components + analyze + create workflow)
- **App learned before** → `eval` (check if memory still matches)
  - Match rate ≥ 80% → use existing memory
  - Match rate < 80% → re-learn
- **Error during execution** → `plan` (re-learn + analyze + new plan)
- App name in Chinese? → resolves alias (微信→WeChat, 浏览器→Chrome)
- Activates the app window before operating
- Calls the right underlying script (app_memory / gui_agent / ui_detector)

### Eval Logic (Workflow-Based)

```
agent.py gets a task → ensure_app_ready(app, workflow, required_components)
  │
  ├── App never learned? → full learn
  │
  ├── App learned, but this workflow/page is NEW?
  │     → learn this specific page (e.g., 'malware_removal')
  │     → existing pages preserved, new page added
  │
  └── App learned, workflow known → template match:
        ├── Match ≥ 80% → memory good, proceed
        └── Match < 80% → incremental learn (update)
```

**Examples:**
- "Clean my Mac" → workflow='smart_scan' → page known → use memory
- "Scan for malware" → workflow='malware_removal' → NEW page → learn it
- "Send WeChat message" → workflow='send_message' → page known → use memory

### For OpenClaw agents

When you receive a GUI task, just call `agent.py` with the right action + params.
Don't call `app_memory.py` or `gui_agent.py` directly — `agent.py` handles the routing.

### Scene files (reference only)

`scenes/*.yaml` files describe operation flows for reference.
They are NOT executable scripts — the actual logic is in `agent.py` + `gui_agent.py`.

## ⚠️ CRITICAL SAFETY RULES (READ FIRST)

**These rules exist because of real bugs that caused messages sent to wrong people.**

1. **VERIFY BEFORE SENDING** — Before typing ANY message, OCR the chat header to confirm the correct contact/group name is displayed. If wrong → ABORT immediately, do NOT send.

2. **ALL OCR/clicks MUST be within target window bounds** — Get window bounds first, filter all OCR results by window region. NEVER click coordinates outside the target app's window. Without this, you WILL click on other apps visible behind.

3. **NEVER auto-learn from wrong-app context** — If a click landed outside the target app window, do NOT save that location as a template. Validate window bounds before auto_learn.

4. **Reject tiny templates** — Templates smaller than 30×30 pixels produce false matches everywhere. Never save them.

5. **Template match ≠ correct target** — A template matching "ContactName" text could be in a group chat name, a forwarded message, or another app. Always verify the CHAT HEADER after navigation, not just the sidebar click.

6. **LLM never provides coordinates** — The LLM (you) decides WHAT component to click by name. Coordinates ALWAYS come from detection tools (OCR, YOLO, template match). Never hardcode or estimate coordinates.

7. **NEVER send screenshots to the conversation** — Screenshot only for internal detection/verification. Never include them in replies to the user.

## Operation Protocol (MANDATORY for every action)

These are hard requirements. Not suggestions. Every step in order.

### TIMING & CONTEXT REPORTING (MANDATORY — NO EXCEPTIONS)

**Every GUI task MUST report timing and token cost at the end.**

This is enforced at two levels:

1. **Script level**: `agent.py` prints `⏱ Completed (X.Xs)` automatically after every command.

2. **Agent level**: For every GUI task (whether using agent.py or direct cliclick):

   **BEFORE starting**: call `session_status`, note the context size (e.g. `📚 Context: 85k/1.0m`)
   **AFTER completing**: call `session_status` again, compute the delta.

   Report format:
   ```
   ⏱ 45.2s | 📊 +10k tokens (85k→95k) | 🔧 3 screenshots, 2 clicks, 1 learn
   ```

   - **⏱ Total time**: wall clock from command received to report
   - **📊 Token delta**: context before → after, and the increment
   - **🔧 Actions taken**: number of screenshots, clicks, learns performed

**This applies even when you bypass agent.py and use cliclick directly.**
**No exceptions. No "I forgot". Write it every time.**

### STEP -1: INTENT MATCHING (before anything else)

When you receive a GUI task, BEFORE doing anything:

1. **Identify the target app** from the user's request
2. **List existing workflows**: `python3 agent.py workflows --app AppName`
3. **Match intent to workflow**: Does the user's request match any saved workflow?
   - User says "清理电脑" → matches `smart_scan_cleanup` workflow
   - User says "帮我扫一下垃圾" → also matches `smart_scan_cleanup`
   - User says "看看 Claude 用量" → matches `check_usage` workflow
   - **You are the LLM — use semantic understanding, not string matching**
4. **If matched**: Load the workflow, skip to STEP 0 with the workflow steps as your plan
5. **If no match**: Proceed normally (observe → plan → act), and **save the workflow after success**

### STEP 0: OBSERVE before anything

Before ANY task, FIRST observe the current state:
1. **Call `session_status`** — record context size for token delta reporting
2. Screenshot the screen
3. What app is in the foreground?
4. Is the target app visible? What page/state is it in?
5. Any popups, dialogs, overlays blocking?
6. ONLY after understanding current state, proceed

DO NOT skip this. DO NOT assume you know the state from last time.

### STEP: PRE-CLICK VERIFY (before every click)

Before clicking anything:
1. Is the element I want to click actually on screen RIGHT NOW?
2. Is it the CORRECT element (not something with a similar name in another window)?
3. Am I clicking inside the correct app window?
4. If ANY answer is NO: DO NOT CLICK. Re-observe first.

### STEP: PRE-SEND VERIFY (before sending messages)

Before sending any message:
1. OCR the chat header - is the correct contact/group open?
2. Is the message text in the input field?
3. If NO: ABORT. Do not send.

### STEP: POST-ACTION VERIFY (after every action)

After any click/type/send:
1. Screenshot again
2. Did the expected change happen?
3. Am I in the expected next state?
4. If NOT: something went wrong. Re-observe and decide.

### STEP: SAVE WORKFLOW (after successful task completion)

After completing a multi-step GUI task successfully:

1. **Check if a workflow already exists** for this task
2. **If not**: Save it with `save_workflow()` in agent.py:
   ```python
   save_workflow("CleanMyMac X", "smart_scan_cleanup", [
       {"action": "open", "target": "CleanMyMac X"},
       {"action": "click", "target": "Start_Over", "note": "only if on results page"},
       {"action": "click", "target": "Scan", "note": "bottom center button"},
       {"action": "wait_for", "target": "Run", "timeout": 120},
       {"action": "click", "target": "Run"},
       {"action": "wait_for", "target": "Ignore", "timeout": 30, "note": "quit apps dialog, may not appear"},
       {"action": "click", "target": "Ignore", "note": "skip quitting apps"},
   ], notes=["Ignore dialog appears if Chrome/Discord/Cursor/Claude running"])
   ```
3. **If exists**: Update it if you learned something new (e.g. new dialog appeared)
4. **Workflow names**: use snake_case, descriptive (e.g. `smart_scan_cleanup`, `check_usage`)
5. **Description**: one-line summary, **max 30 words** (e.g. "Scan and clean Mac junk files")

### Meta-Workflows (cross-app orchestration)

Meta-workflows are **pure orchestration** — they ONLY contain `call` steps referencing other workflows. No raw actions (`open`, `click`, `observe`) allowed in meta-workflows.

**Rules:**
1. Every step MUST be `{"action": "call", ...}` — no exceptions
2. Each `call` MUST specify all inputs the called workflow needs in `params`
3. If a workflow produces output needed by the next step, declare it in `output_as`

```python
save_meta_workflow("share_article_to_wechat", [
    {
        "action": "call",
        "app": "Chrome",
        "workflow": "copy_page_content",
        "params": {"url": "https://example.com/article"},
        "output_as": "$article"
    },
    {
        "action": "call",
        "app": "WeChat",
        "workflow": "send_message",
        "params": {"contact": "John", "content": "$article"}
    },
], description="Copy Chrome article and send via WeChat")
```

**Bad example (DO NOT do this):**
```python
# ❌ Raw actions in meta-workflow
[
    {"action": "open", "app": "Chrome"},          # WRONG: raw action
    {"action": "click", "app": "Chrome", ...},    # WRONG: raw action
    {"action": "call", "app": "WeChat", "workflow": "send_message"}  # missing params!
]
```

**Good example:**
```python
# ✅ Pure call + explicit params
[
    {"action": "call", "app": "Chrome", "workflow": "copy_page_content",
     "params": {"url": "..."}, "output_as": "$content"},
    {"action": "call", "app": "WeChat", "workflow": "send_message",
     "params": {"contact": "John", "content": "$content"}},
]
```

**Nesting**: meta-workflows can call other meta-workflows (max depth 5)

**When to create what**:
- Single task in one app → app workflow (`save_workflow`)
- Composing multiple workflows (same app or cross-app) → meta-workflow (`save_meta_workflow`)

**Listing**: `python3 agent.py all_workflows` — shows all app + meta workflows

### Running a known workflow

DO NOT blindly replay all steps from memory. INSTEAD:
1. Observe current state FIRST
2. Compare with workflow: WHERE in the workflow am I right now?
3. Skip steps already done (e.g., scan finished -> skip to Run)
4. Execute ONLY the next needed step
5. After each step: verify state changed, then next step
6. If state does not match any known step: STOP and trigger plan (learn + analyze)

### Waiting for async UI changes

When an action triggers a slow process (scan, download, loading):
1. **Use `wait_for`**: `python3 agent.py wait_for --app AppName --component ComponentName`
2. Template match polls every 10s (~0.3s per check), 120s timeout
3. On success: returns coordinates, proceed to click
4. On timeout: saves screenshot, **DO NOT blind-click** — inspect the screenshot and decide
5. **NEVER use `sleep(60)` + blind click** — always verify the target exists before clicking

### Explore (Manual Trigger)

**When to use:** When you want to analyze/familiarize with an app WITHOUT a specific goal.

**How:** User manually triggers `agent.py explore --app AppName`

**What it does:**
1. Screenshot the target window
2. Run YOLO + OCR detection
3. Save to memory for future reference
4. Agent analyzes the UI structure

**NOT for:** Workflow execution (use eval/plan for that)

## Auto-Learn Rule (MUST follow)

**Every time you interact with a GUI app or website, check memory FIRST:**
- App not in `memory/apps/<appname>/`? → Run `learn` automatically before operating
- Website not in `memory/apps/<browser>/sites/<domain>/`? → Run `learn_site` automatically
- New page/state in a known app? → Run `learn --page <pagename>` to add it
- After any screenshot/observation, if you see new unlabeled icons → identify them immediately

**Do NOT wait for the user to ask you to learn.** This is YOUR responsibility.

## Key Principles

1. **Memory first, detect second** — check template match before running YOLO+OCR
2. **Relative coordinates** — never hardcode screen positions; all coords relative to window top-left
3. **Verify before acting** — especially before sending messages (verify contact, verify input field)
4. **Template > OCR > YOLO > LLM** — use the cheapest method that works
5. **Paste > Type** for CJK text and special chars (set LANG=en_US.UTF-8)
6. **Learn incrementally** — save new components to memory after each interaction
7. **Window-based, not screen-based** — capture and operate within the target window only
8. **Integer coordinates only** — cliclick requires integers, always Math.round

## Operating System Rules (macOS)

### Coordinate System
- **Screen**: top-left origin (0,0), logical pixels (Retina physical ÷ 2)
- **Window**: relative to window's top-left corner
- **Retina**: screenshots are 2x physical pixels; divide by 2 for logical
- **cliclick**: uses screen logical pixels, integer only
- **Formula**: `screen_x = window_x + relative_x`, `screen_y = window_y + relative_y`

### Window Management
- Get window bounds: `osascript -e 'tell application "System Events" to tell process "AppName" to return {position, size} of window 1'`
- Get window ID: use Swift CGWindowListCopyWindowInfo (see ui_detector.py)
- Capture window: `screencapture -x -l <windowID> output.png`
- Activate app: `osascript -e 'tell application "AppName" to activate'`
- Resize: `tell process "AppName" to set size of window 1 to {900, 650}`

### Input Methods
- **Click**: `/opt/homebrew/bin/cliclick c:<x>,<y>` (logical screen coords, integers)
- **Type ASCII**: `cliclick t:"text"` (ASCII only, special chars may break)
- **Paste CJK/special**: `pbcopy` + `Cmd+V` (MUST set LANG=en_US.UTF-8)
- **Key press**: `cliclick kp:return` (valid keys: return, esc, tab, delete, space, arrow-*, f1-f16)
- **Shortcut**: `osascript -e 'tell app "System Events" to keystroke "v" using command down'`

### Window Utilities
- Get window bounds: `osascript -e 'tell application "System Events" to tell process "AppName" to return {position, size} of window 1'`
- Get window ID: use Swift CGWindowListCopyWindowInfo (see ui_detector.py)
- Capture window: `screencapture -x -l <windowID> output.png`
- Activate app: `osascript -e 'tell application "AppName" to activate'`
- Resize: `tell process "AppName" to set size of window 1 to {900, 650}`

### Input Methods

### Browser Automation

Browsers are a **two-layer** system:
1. **Browser chrome** (tabs, address bar, bookmarks) — fixed, learn once like any app
2. **Web page content** — different per site, need per-site memory

```
memory/apps/
├── google_chrome/
│   ├── profile.json          # Browser chrome UI (tabs, address bar, etc.)
│   ├── components/                # Browser UI icons
│   └── sites/                # Per-website memory
│       ├── 12306.cn/
│       │   ├── profile.json  # Site-specific UI elements
│       │   ├── components/        # Site buttons, nav items
│       │   └── pages/
│       │       ├── search.json     # Train search page layout
│       │       └── results.json    # Results page layout
│       ├── google.com/
│       └── ...
```

**Browser operation flow:**
```
1. Learn browser chrome once: app_memory.py learn --app "Google Chrome"
   → Saves: address bar, tab controls, bookmarks bar, etc.

2. Navigate to a website:
   a. Click address bar (template match: address_bar)
   b. Type URL or search term (paste)
   c. Press Enter

3. On a new website:
   a. Wait for page load (1-2s)
   b. Run detection (YOLO + OCR) on the page content area only
   c. Save site-specific UI elements to sites/<domain>/
   d. Dynamic content (search results, articles) = DON'T save
   e. Fixed UI (nav bar, search box, buttons, filters) = SAVE

4. Operate within website:
   a. Template match known site elements first
   b. If not found → OCR find text → click
   c. For form fields: click field → paste text → verify
```

**What to save per website:**
- Navigation bars, menus, headers (fixed across pages)
- Search boxes, filter buttons, sort controls
- Login/signup buttons, submit buttons
- Site logo, main action buttons

**What NOT to save per website:**
- Search results, article content, feed items
- Prices, availability (changes constantly)
- Ads, pop-ups, banners
- User-generated content

### Browser Input Quirks (MUST know)

- **Autocomplete fields** (like 12306 station selector): typing text alone is NOT enough. MUST click the dropdown suggestion item. The field only accepts values selected from the dropdown.
  - Flow: click input → type pinyin/text → wait for dropdown → click the correct suggestion
  - URL parameters may fill the text visually but don't trigger the selection event

- **Chinese input in browsers**: System IME interferes with website autocomplete.
  - Solution: switch to English input method first, type pinyin abbreviation (e.g., "bjn" for 北京南), let the WEBSITE's own autocomplete handle it (not system IME)
  - `cliclick t:bjn` with English input → website dropdown shows 北京南 → click it

- **Cmd+V paste in web forms**: May produce garbled text (encoding issues).
  - Safer: use `cliclick t:text` for ASCII/pinyin, let website autocomplete handle Chinese

- **Date pickers**: Usually need to click the calendar UI, not just type a date string. Some accept direct input, some don't.

## Complete Operation Flow

### Sending a Message (e.g., WeChat)

```
1. PREPARE
   a. Activate the app: osascript tell "WeChat" to activate
   b. Get window bounds: (win_x, win_y, win_w, win_h)
   c. ALL subsequent OCR/clicks MUST be within these bounds

2. NAVIGATE TO CONTACT
   a. Check if contact visible in sidebar (OCR within window bounds)
      - If found → click it
      - If not found → search:
        i.  Click search bar (template match or OCR within window)
        ii. Paste contact name (pbcopy + Cmd+V)
        iii. Wait 1s for results
        iv. OCR find contact in results (within window bounds) → click

3. ⚠️ VERIFY CONTACT (MANDATORY — DO NOT SKIP)
   a. OCR the chat HEADER area (top 120px of main content area)
   b. Confirm expected contact name appears in the header
   c. If WRONG contact or name NOT found:
      → LOG what chat IS open (for debugging)
      → ABORT immediately, do NOT type anything
      → Return error
   d. Only proceed to step 4 if verification PASSES

4. TYPE MESSAGE (only after step 3 passes)
   a. Click input field (template match or window_calc)
   b. Paste message (pbcopy + Cmd+V, NOT cliclick type)

5. SEND
   a. Press Enter (cliclick kp:return)

6. VERIFY SENT
   a. OCR the chat area
   b. Confirm first 10 chars of message visible
   c. If not found → report warning (may still have sent)
```

**WHY step 3 is critical**: Template matching "ContactName" could match:
- ✅ ContactName's private chat (correct)
- ❌ A group chat containing someone named ContactName
- ❌ A forwarded message mentioning ContactName
- ❌ Text in another app's window (if OCR wasn't bounded)

Only the chat HEADER reliably shows who you're actually chatting with.

### Learning a New App

```
1. Activate the app, ensure window is reasonably sized (≥800x600)
2. Run: python3 app_memory.py learn --app AppName
3. System automatically:
   a. Captures window screenshot
   b. Runs GPA-GUI-Detector (YOLO) → finds all components/buttons
   c. Runs Apple Vision OCR → finds all text
   d. Merges with IoU dedup
   e. Crops each element → saves to memory/apps/appname/components/
   f. Auto-cleans dynamic content (timestamps, message previews)
   g. Reports unlabeled icons
4. Agent identifies unlabeled icons (vision model looks at grid)
5. Rename: python3 app_memory.py rename --old unlabeled_xxx --new descriptive_name
6. Clean remaining dynamic content manually if needed
7. Final profile should have ~20-30 fixed UI components
```

### Clicking a Known Component

```
1. Capture window screenshot
2. Template match against saved icon (OpenCV matchTemplate, threshold=0.8)
3. If matched (conf > 0.8):
   a. Get relative coords from match
   b. Convert to screen coords: screen = window_pos + relative
   c. Verify: coords within window bounds? confidence > 0.7?
   d. Click: cliclick c:<screen_x>,<screen_y>
4. If not matched:
   a. Run full detection (YOLO + OCR)
   b. Ask LLM to identify target element
   c. Save new component to memory (auto-learn)
   d. Click the identified element
```

### Handling Unknown UI States

```
1. Take screenshot
2. Run detection (YOLO + OCR)
3. Compare against known page layout
4. If new elements found:
   a. Crop and save as unlabeled
   b. Use LLM to identify
   c. Update memory
5. If expected elements missing:
   a. Maybe different page/state
   b. Try learning as new page: learn --page settings
```

## Setup (New Machine)

Run the setup script on a fresh Mac:

```bash
# Clone the repo
git clone https://github.com/Fzkuji/gui-agent-skills.git
cd gui-agent-skills

# Run setup (installs everything)
bash scripts/setup.sh
```

This will:
1. Install `cliclick` and Python 3.12 via Homebrew
2. Create venv at `~/gui-agent-env/`
3. Install PyTorch, ultralytics, OpenCV, transformers
4. Download GPA-GUI-Detector model (40MB) to `~/GPA-GUI-Detector/`
5. Verify everything works

**After setup**, also grant **Accessibility permissions**:
System Settings → Privacy & Security → Accessibility → Add Terminal / OpenClaw

### First Use

```bash
source ~/gui-agent-env/bin/activate
cd scripts/

# Learn an app (captures window, detects all elements, saves to memory)
python3 app_memory.py learn --app WeChat

# After learning, identify unlabeled icons (agent does this automatically)
# Then operate:
python3 app_memory.py click --app WeChat --component search_bar_icon
python3 app_memory.py detect --app WeChat
```

## Scripts

| Script | Purpose |
|--------|---------|
| `setup.sh` | **Run first on new machine** — installs all dependencies |
| `ui_detector.py` | Unified detection engine (YOLO + OCR) |
| `app_memory.py` | Per-app visual memory (learn / detect / click / verify) |
| `gui_agent.py` | Legacy task executor (send_message, read_messages, etc.) |
| `template_match.py` | Low-level template matching utilities |
| `computer_use.py` | Claude Computer Use API (experimental) |

All scripts use venv: `source ~/gui-agent-env/bin/activate`

## Models & Dependencies

| Model | Size | Auto-installed by setup.sh | Purpose |
|-------|------|---------------------------|---------|
| **GPA-GUI-Detector** | 40MB | ✅ `~/GPA-GUI-Detector/model.pt` | UI element detection |

Optional (not auto-installed):
| **OmniParser V2** | 1.1GB | ❌ | Alt detection (weaker on desktop apps) |
| **GUI-Actor 2B** | 4.5GB | ❌ | End-to-end grounding (experimental) |

### Path Convention
- Venv: `~/gui-agent-env/` (created by setup.sh)
- Model: `~/GPA-GUI-Detector/model.pt` (downloaded by setup.sh)
- Memory: `<skill-dir>/memory/apps/<appname>/` (created on first learn)
- All paths use `os.path.expanduser("~")`, NOT hardcoded usernames

## File Structure

```
gui-agent/
├── SKILL.md              # This file
├── actions/              # Atomic operations
│   └── _actions.yaml
├── memory/               # All visual memory (gitignored)
│   └── apps/
│       └── <appname>/   # Per-app memory
│           ├── profile.json      # App config + metadata
│           ├── components/       # Learned UI components
│           └── workflows/        # Saved workflows
├── scripts/              # Core scripts
│   ├── ui_detector.py    # Detection engine (YOLO + OCR)
│   ├── app_memory.py     # Memory management
│   ├── gui_agent.py      # Task executor
│   └── agent.py          # Main agent (learn/plan/eval)
├── docs/
│   └── core.md           # Core principles
└── README.md
```

**Flow:**
- `learn`: Detect UI → save to `memory/apps/<app>/components/`
- `plan`: Analyze components → create workflow → save to `memory/apps/<app>/workflows/`
- `eval`: Check if memory is fresh enough
