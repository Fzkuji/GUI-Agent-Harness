---
name: gui-agent
description: "Control desktop GUI applications on macOS using visual detection, template matching, and cliclick. Use when asked to operate, click, type, or interact with any desktop application. NOT for web-only tasks (use browser tool) or simple file operations."
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
│     ③ YOLO detection (0.3s)         │  → icons in AX-poor apps only
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

### When to use what — Decision Tree

**ALWAYS try methods in this order (cheapest first):**

```
  → osascript: tell process "AppName" to get UI elements
  → If found (has name + position) → USE IT. Done.
    System Settings, GlobalProtect, most native apps

Step 2: Is the element in template memory?
  → app_memory.py find --app AppName --component name
  → If matched (conf > 0.8) → click it. Done.

Step 2: Can OCR find it by text?
  → ocr_find("button text") within window bounds
  → If found → click. Optionally auto-learn template.

Step 3: Run full detection (YOLO + OCR)
  → ui_detector.py --app AppName
  → GPA-GUI-Detector finds icons/buttons
  → Apple Vision OCR finds text
  → Merge, save to memory for next time

Step 4: Last resort — screenshot + ask LLM
  → Take screenshot, send to vision model for analysis
  → Only if all above methods fail
```

GlobalProtect VPN reconnect uses only AX + cliclick — no YOLO needed.


```bash
# List all UI elements of an app
osascript -l JavaScript -e '
  var se = Application("System Events");
  var p = se.processes["AppName"];
  var all = p.windows[0].entireContents();
  // Filter by role, title, position
'

# Click a named button

# Get element position
```

### When YOLO detection IS needed

Only use GPA-GUI-Detector for apps with **bad AX support**:
- **WeChat** (4 AX elements — only window buttons)
- **QQ**, other custom-rendered apps
- **Websites** inside browsers (browser chrome has AX, but page content doesn't)
- Any app where `entireContents()` returns < 10 elements

## App Visual Memory

Each app gets a memory directory with learned components:

```
memory/apps/
├── wechat/
│   ├── profile.json          # Component registry (coords, labels, types)
│   ├── icons/                # Cropped component images (PNG)
│   │   ├── Q_Search.png
│   │   ├── ContactName.png
│   │   ├── icon_11_173_225.png  (unlabeled → LLM identifies later)
│   │   └── ...
│   └── pages/
│       ├── main_annotated.jpg   # Annotated screenshot
│       └── main.json            # Page layout
├── discord/
│   └── ...
```

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
   b. No label? → name as "unlabeled_<region>_<x>_<y>"
   c. Check visual dedup (similarity > 0.92) → skip if duplicate
   d. Crop and save to icons/
4. After saving all elements:
   a. Use vision model (Claude/GPT-4o) to identify ALL unlabeled icons
   b. Rename identified icons: app_memory.py rename --old unlabeled_xxx --new actual_name
   c. Remove dynamic content (timestamps, message previews, chat text, stickers)
   d. Keep ONLY fixed UI elements (buttons, icons, tabs, navigation, input fields)
5. Result: clean profile with ~20-30 named, fixed UI components per page
```

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
| **Atomic Actions** | `actions/_actions.yaml` | click, type, paste, AX scan... |
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
- App not learned yet? → runs `learn` first
- App name in Chinese? → resolves alias (微信→WeChat, 浏览器→Chrome)
- Activates the app window before operating
- Calls the right underlying script (app_memory / gui_agent / ui_detector)

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
4. **AX > Template > OCR > YOLO** — use the cheapest method that works
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

### Accessibility (AX) API
- Some apps have full AX support: Discord (1913 elements), Chrome (1415), System Settings
- Some have zero: WeChat (4 elements), QQ, custom-rendered apps
- Dock and menubar ALWAYS have AX — use it for those
- AX gives: element name, position, size, role — most accurate source

### App-Specific Quirks
- **WeChat**: 4 AX elements only; left sidebar icons are gray-on-gray (YOLO needed); Cmd+F opens web search NOT contact search; input field placeholder invisible to OCR
- **Discord**: Full AX; Cmd+K for quick switcher; sidebar icons are round server avatars
- **Electron apps** (Discord, Cursor, Outlook): huge AX tree, may timeout on full scan; filter by region

### Browser Automation

Browsers are a **two-layer** system:
1. **Browser chrome** (tabs, address bar, bookmarks) — fixed, learn once like any app
2. **Web page content** — different per site, need per-site memory

```
memory/apps/
├── google_chrome/
│   ├── profile.json          # Browser chrome UI (tabs, address bar, etc.)
│   ├── icons/                # Browser UI icons
│   └── sites/                # Per-website memory
│       ├── 12306.cn/
│       │   ├── profile.json  # Site-specific UI elements
│       │   ├── icons/        # Site buttons, nav items
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
   b. Runs GPA-GUI-Detector (YOLO) → finds all icons/buttons
   c. Runs Apple Vision OCR → finds all text
   d. Merges with IoU dedup
   e. Crops each element → saves to memory/apps/appname/icons/
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
| `ui_detector.py` | Unified detection engine (YOLO + OCR + AX) |
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
├── scenes/               # Per-app operation workflows
│   ├── wechat/
│   ├── discord.yaml
│   └── ...
├── memory/               # Visual memory (gitignored)
│   └── apps/
│       ├── wechat/       # profile.json + icons/ + pages/
│       └── ...
├── scripts/              # Core scripts
│   ├── ui_detector.py    # Detection engine
│   ├── app_memory.py     # Memory management
│   ├── gui_agent.py      # Task executor
│   └── ...
├── apps/                 # App UI config (JSON)
├── docs/core.md          # Core principles
└── README.md
```
