<div align="center">
  <img src="assets/banner.png" alt="GUIClaw" width="100%" />

  <h1>🦞 GUIClaw</h1>

  <p>
    <strong>See your screen. Learn every button. Click precisely.</strong>
    <br />
    Vision-based desktop automation skills built on <a href="https://github.com/openclaw/openclaw">OpenClaw</a>.
    <br />
    <em>Requires OpenClaw as the runtime — not a standalone API or library.</em>
  </p>

  <p>
    <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-blue?style=for-the-badge" /></a>
    <a href="#-quick-start"><img src="https://img.shields.io/badge/🦞_OpenClaw-red?style=for-the-badge" /></a>
    <a href="https://discord.gg/BQbUmVuD"><img src="https://img.shields.io/badge/Discord-7289da?style=for-the-badge&logo=discord&logoColor=white" /></a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Platform-macOS_Apple_Silicon-black?logo=apple" />
    <img src="https://img.shields.io/badge/Detection-GPA_GUI_Detector-green" />
    <img src="https://img.shields.io/badge/OCR-Apple_Vision-blue" />
    <img src="https://img.shields.io/badge/License-MIT-yellow" />
  </p>
</div>

---

<p align="center">
  <b>🇺🇸 English</b> ·
  <a href="docs/README_CN.md">🇨🇳 中文</a>
</p>

---

## 🔥 News

- **[03/22/2026]** 🏆 **OSWorld benchmark**: **24/24 Chrome tasks passed (100%)**, including external website tasks. [See results →](benchmarks/osworld/)
- **[03/22/2026]** v0.6.0 — **Vision vs Command boundary + unified action flow**: Clear definition of three visual methods (OCR/GPA-GUI-Detector/image tool) and when to use each; action and memory saving merged into one atomic operation (detect→match→execute→diff→save); browser per-website nested memory structure.
- **[03/21/2026]** v0.5.0 — **Cross-platform detection**: GPA-GUI-Detector works on any OS screenshot (Linux, Windows, mobile). First OSWorld evaluation on Ubuntu VM.
- **[03/19/2026]** v0.4.0 — **Workflow memory + async polling**: Saved workflows auto-matched by LLM intent; `wait_for` command (template-match polling, no blind clicks); mandatory timing & token delta reporting; multi-window fix (selects largest window).
- **[03/19/2026]** v0.3.0 — **Click-graph state architecture**: UI modeled as a graph of states; each click creates a new state entry; state identification via OCR text matching. Removed pages/regions/overlays complexity.
- **[03/17/2026]** v0.2.0 — Workflow-based revise, event-driven polling, mandatory operation protocol (observe→verify→act→confirm), per-app visual memory with auto-cleanup.
- **[03/16/2026]** v0.1.0 — GPA-GUI-Detector integration, Apple Vision OCR, template matching, browser automation, per-site memory.
- **[03/10/2026]** v0.0.1 — Initial release: WeChat/Discord/Telegram automation, app profiles, fuzzy app matching.

## 💬 What It Looks Like

> **You**: "Send a message to John in WeChat saying see you tomorrow"

```
OBSERVE  → Screenshot, identify current state
           ├── Current app: Finder (not WeChat)
           └── Action: need to switch to WeChat

STATE    → Check WeChat memory
           ├── Learned before? Yes (24 components)
           ├── OCR visible text: ["Chat", "Cowork", "Code", "Search", ...]
           ├── State identified: "initial" (89% match)
           └── Components for this state: 18 → use these for matching

NAVIGATE → Find contact "John"
           ├── Template match search_bar → found (conf=0.96) → click
           ├── Paste "John" into search field (clipboard → Cmd+V)
           ├── OCR search results → found → click
           └── New state: "click:John" (chat opened)

VERIFY   → Confirm correct chat opened
           ├── OCR chat header → "John" ✅
           └── Wrong contact? → ABORT

ACT      → Send message
           ├── Click input field (template match)
           ├── Paste "see you tomorrow" (clipboard → Cmd+V)
           └── Press Enter

CONFIRM  → Verify message sent
           ├── OCR chat area → "see you tomorrow" visible ✅
           └── Done
```

<details>
<summary>📖 More examples</summary>

### "Scan my Mac for malware"

```
OBSERVE  → Screenshot → CleanMyMac X not in foreground → activate
           ├── Get main window bounds (largest window, skip status bar panels)
           └── OCR window content → identify current state

STATE    → Check memory for CleanMyMac X
           ├── OCR visible text: ["Smart Scan", "Malware Removal", "Privacy", ...]
           ├── State identified: "initial" (92% match)
           └── Know which components to match: 21 components

NAVIGATE → Click "Malware Removal" in sidebar
           ├── Find element in window (exact match, filter by window bounds)
           ├── Click → new state: "click:Malware_Removal"
           └── OCR confirms new state (87% match)

ACT      → Click "Scan" button
           ├── Find "Scan" (exact match, bottom position — prevents matching "Deep Scan")
           └── Click → scan starts

POLL     → Wait for completion (event-driven, no fixed sleep)
           ├── Every 2s: screenshot → OCR check for "No threats"
           └── Target found → proceed immediately

CONFIRM  → "No threats found" ✅
```

### "Check if my GPU training is still running"

```
OBSERVE  → Screenshot → Chrome is open
           └── Identify target: JupyterLab tab

NAVIGATE → Find JupyterLab tab in browser
           ├── OCR tab bar or use bookmarks
           └── Click to switch

EXPLORE  → Multiple terminal tabs visible
           ├── Screenshot terminal area
           ├── LLM vision analysis → identify which tab has nvitop
           └── Click the correct tab

READ     → Screenshot terminal content
           ├── LLM reads GPU utilization table
           └── Report: "8 GPUs, 7 at 100% — experiment running" ✅
```

### "Kill GlobalProtect via Activity Monitor"

```
OBSERVE  → Screenshot current state
           └── Neither GlobalProtect nor Activity Monitor in foreground

ACT      → Launch both apps
           ├── open -a "GlobalProtect"
           └── open -a "Activity Monitor"

EXPLORE  → Screenshot Activity Monitor window
           ├── LLM vision → "Network tab active, search field empty at top-right"
           └── Decide: click search field first

ACT      → Search for process
           ├── Click search field (identified by explore)
           ├── Paste "GlobalProtect" (clipboard → Cmd+V, never cliclick type)
           └── Wait for filter results

VERIFY   → Process found in list → select it

ACT      → Kill process
           ├── Click stop button (X) in toolbar
           └── Confirmation dialog appears

VERIFY   → Click "Force Quit"

CONFIRM  → Screenshot → process list empty → terminated ✅
```

</details>

## ⚠️ Prerequisites

GUIClaw is an **OpenClaw skill** — it runs inside [OpenClaw](https://github.com/openclaw/openclaw) and uses OpenClaw's LLM orchestration to reason about UI actions. It is **not** a standalone API, CLI tool, or Python library. You need:

1. **[OpenClaw](https://github.com/openclaw/openclaw)** installed and running
2. **macOS with Apple Silicon** (for GPA-GUI-Detector and Apple Vision OCR)
3. **Accessibility permissions** granted to OpenClaw/Terminal

The LLM (Claude, GPT, etc.) is provided by your OpenClaw configuration — GUIClaw itself does not call any external APIs directly.

## 🚀 Quick Start

**1. Clone & install**
```bash
git clone https://github.com/Fzkuji/GUIClaw.git
cd GUIClaw
bash scripts/setup.sh
```

**2. Grant accessibility permissions**

System Settings → Privacy & Security → Accessibility → Add Terminal / OpenClaw

**3. Configure OpenClaw**

Add to `~/.openclaw/openclaw.json`:
```json
{
  "skills": { "entries": { "gui-agent": { "enabled": true } } },
  "tools": { "exec": { "timeoutSec": 60 } },
  "messages": { "queue": { "mode": "steer" } }
}
```

> ⚠️ **`timeoutSec: 60`** is important — GUIClaw operations (screenshot → detect → click → wait) often take 15-30s. The default timeout is too short and will kill commands mid-execution.

> 💡 **`queue.mode: "steer"`** is recommended — GUI operations take time, and steer mode lets you send corrections or new instructions that immediately interrupt the current action at the next tool-call boundary. Without it, your messages queue up and the agent won't see them until it finishes.

Then just chat with your OpenClaw agent — it reads `SKILL.md` and handles everything automatically.

## 🧠 How It Works

<p align="center">
  <img src="assets/pipeline.svg" alt="GUIClaw Pipeline" width="600" />
</p>

### Learn Once, Match Forever

**First time** — GPA-GUI-Detector detects everything (~4 seconds):
```
🔍 GPA-GUI-Detector: 43 icons    📝 OCR: 34 text elements    🔗 → 24 fixed UI components saved
```

**Every time after** — instant template match (~0.3 seconds):
```
✅ search_bar_icon (202,70) conf=1.0
✅ emoji_button (354,530) conf=1.0
✅ sidebar_contacts (85,214) conf=1.0
```

## 🔍 Detection Stack

| Detector | Speed | Finds | Why |
|----------|-------|-------|-----|
| **[GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector)** | 0.3s | Icons, buttons | Finds gray-on-gray icons others miss |
| **Apple Vision OCR** | 1.6s | Text (CN + EN) | Best Chinese OCR, pixel-accurate |
| **Template Match** | 0.3s | Known components | 100% accuracy after first learn |

## 📁 App Visual Memory

Each app gets its own visual memory with a **click-graph state model**.
Browsers are special — they host many websites, so each site gets its own **nested memory** with the same structure as any app.

```
memory/apps/
├── wechat/
│   ├── profile.json              # Components + click-graph states
│   ├── components/               # Cropped UI element images
│   │   ├── search_bar.png
│   │   ├── emoji_button.png
│   │   └── ...
│   ├── workflows/                # Saved task sequences
│   │   └── send_message.json
│   └── pages/
│       └── main_annotated.jpg
├── cleanmymac_x/
│   ├── profile.json
│   ├── components/
│   ├── workflows/
│   │   └── smart_scan_cleanup.json
│   └── pages/
├── claude/
│   ├── profile.json
│   ├── components/
│   ├── workflows/
│   │   └── check_usage.json
│   └── pages/
└── chromium/
    ├── profile.json              # Browser-level UI (toolbar, settings)
    ├── components/               # Browser UI element templates
    ├── pages/
    └── sites/                    # ⭐ Per-website memory (same structure as any app)
        ├── united.com/
        │   ├── profile.json      # Site UI: nav bar, forms, links
        │   ├── components/       # Cropped site-specific UI elements
        │   └── pages/            # Page screenshots
        ├── delta.com/
        │   ├── profile.json
        │   ├── components/
        │   └── pages/
        └── amazon.com/
            ├── profile.json
            ├── components/
            └── pages/
```

### Click Graph

The UI is modeled as a **graph of states**. Each state is defined by which components are visible on screen.

**profile.json structure:**
```json
{
  "app": "Claude",
  "window_size": [1512, 828],
  "components": {
    "Search": { "type": "icon", "rel_x": 115, "rel_y": 143, "icon_file": "components/Search.png", ... },
    "Settings": { ... }
  },
  "states": {
    "initial": {
      "visible": ["Chat_tab", "Cowork_tab", "Code_tab", "Search", "Ideas", ...],
      "description": "Main app view when first opened"
    },
    "click:Settings": {
      "trigger": "Settings",
      "trigger_pos": [63, 523],
      "visible": ["Chat_tab", "Account", "Billing", "Usage", "General", ...],
      "disappeared": ["Ideas", "Customize", ...],
      "description": "Settings page"
    },
    "click:Usage": {
      "trigger": "Usage",
      "visible": ["Chat_tab", "Account", "Billing", "Usage", "Developer", ...],
      "description": "Settings > Usage tab"
    }
  }
}
```

**How it works:**
1. **Initial state** = what's visible when the app first opens (captured during first `learn`)
2. **Click creates state** = every click that changes the screen creates a new `click:ComponentName` state
3. **State identification** = OCR screen → match visible text against each state's `visible` list → highest match ratio wins
4. **Components belong to states** = a component can appear in multiple states (e.g., `Chat_tab` is visible in `initial`, `click:Settings`, `click:Usage`)
5. **Matching is state-specific** = only match components that belong to the identified state

**Why this works:**
- No need to predefine "pages" or "regions" — states are discovered through interaction
- State identification is fast (OCR text matching, no vision model needed)
- Handles overlays, popups, nested navigation naturally
- Scales to complex apps with many UI states

## 🔄 Workflow Memory

Completed tasks are saved as reusable workflows. Next time a similar request comes in, the agent matches it semantically.

```
memory/apps/cleanmymac_x/workflows/smart_scan_cleanup.json
memory/apps/claude/workflows/check_usage.json
```

**How matching works:**
1. User says "帮我清理一下电脑" / "scan my Mac" / "run CleanMyMac"
2. Agent lists saved workflows for the target app
3. **LLM semantic matching** (not string matching) — the agent IS the LLM
4. Match found → load workflow steps, observe current state, resume from correct step
5. No match → operate normally, save new workflow after success

**Example workflow** (`smart_scan_cleanup.json`):
```json
{
  "steps": [
    {"action": "open", "target": "CleanMyMac X"},
    {"action": "observe", "note": "check current state"},
    {"action": "click", "target": "Scan"},
    {"action": "wait_for", "target": "Run", "timeout": 120},
    {"action": "click", "target": "Run"},
    {"action": "wait_for", "target": "Ignore", "timeout": 30},
    {"action": "click", "target": "Ignore", "condition": "only if quit dialog appeared"}
  ]
}
```

**`wait_for` — async UI polling:**
```bash
python3 agent.py wait_for --app "CleanMyMac X" --component Run
# ⏳ Waiting for 'Run' (timeout=120s, poll=10s)...
# ✅ Found 'Run' at (855,802) conf=0.98 after 45.2s (5 polls)
```
- Template match every 10s (~0.3s per check)
- On timeout → saves screenshot for inspection, **never blind-clicks**

## 🔴 Vision vs Command

GUIClaw uses visual detection for **decisions** and the most efficient method for **execution**:

| | Must be vision-based | May use keyboard/CLI |
|---|---|---|
| **What** | Determining state, locating elements, verifying results | Shortcuts (Ctrl+L), text input, system commands |
| **Why** | The agent must SEE what's on screen before acting | Execution can use the fastest available method |
| **Rule** | **Decision = Visual, Execution = Best Tool** | |

### Three Visual Methods

| Method | Returns | Use for |
|--------|---------|---------|
| **OCR** (`detect_text`) | Text + coordinates ✅ | Finding text labels, links, menu items |
| **GPA-GUI-Detector** (`detect_icons`) | Bounding boxes + coordinates ✅ (no labels) | Finding icons, buttons, non-text elements |
| **image tool** (LLM vision) | Semantic understanding ⛔ NO coordinates | Understanding the scene, deciding WHAT to click |

**Progressive workflow**: First visit → all three methods. Familiar pages → OCR + detector only (skip image tool, save tokens).

## ⚠️ Safety & Protocol

Every action follows a unified detect-match-execute-save protocol:

| Step | What | Why |
|------|------|-----|
| **DETECT** | Screenshot + OCR + GPA-GUI-Detector | Know what's on screen with coordinates |
| **MATCH** | Compare against saved memory components | Reuse learned elements (skip re-detection) |
| **DECIDE** | LLM picks target element | Visual understanding drives decisions |
| **EXECUTE** | Click detected coordinates / keyboard shortcut | Act using best tool |
| **DETECT AGAIN** | Screenshot + OCR + GPA-GUI-Detector after action | See what changed |
| **DIFF** | Compare before vs after (appeared/disappeared/persisted) | Understand state transition |
| **SAVE** | Update memory: components, labels, transitions, pages | Learn for future reuse |

**Safety rules enforced in code:**
- ✅ Verify chat recipient before sending messages (OCR header)
- ✅ Window-bounded operations (no clicking outside target app)
- ✅ Exact text matching (prevents "Scan" matching "Deep Scan")
- ✅ Largest-window detection (skips status bar panels for multi-window apps)
- ✅ No blind clicks after timeout — screenshot + inspect instead
- ✅ Mandatory timing & token delta reporting after every task

## 🗂️ Project Structure

```
GUIClaw/
├── SKILL.md                   # 🧠 Main skill — agent reads this first
│                              #    Defines: Vision vs Command boundary,
│                              #    three visual methods, execution flow
├── skills/                    # 📖 Sub-skills
│   ├── gui-observe/SKILL.md   #   👁️ Screenshot, OCR, identify state
│   ├── gui-learn/SKILL.md     #   🎓 Detect components, label, filter, save
│   ├── gui-act/SKILL.md       #   🖱️ Unified: detect→match→execute→diff→save
│   ├── gui-memory/SKILL.md    #   💾 Memory structure, browser sites/, cleanup
│   ├── gui-workflow/SKILL.md  #   🔄 State graph navigation, workflow replay
│   ├── gui-report/SKILL.md    #   📊 Task performance tracking
│   └── gui-setup/SKILL.md     #   ⚙️ First-time setup on a new machine
├── scripts/
│   ├── setup.sh               # 🔧 One-command setup
│   ├── agent.py               # 🎯 Unified entry point (all GUI ops go through here)
│   ├── ui_detector.py         # 🔍 Detection engine (GPA-GUI-Detector + OCR + Swift window info)
│   ├── app_memory.py          # 🧠 Visual memory (learn/detect/click/verify/learn_site)
│   ├── gui_agent.py           # 🖱️ Legacy task executor
│   └── template_match.py      # 🎯 Template matching utilities
├── memory/                    # 🔒 Visual memory (gitignored but ESSENTIAL)
│   ├── apps/<appname>/        #   Per-app: profile.json, components/, pages/
│   │   └── sites/<domain>/    #   Per-website memory (browsers only, same structure)
│   └── meta_workflows/        #   Cross-app orchestration
├── benchmarks/osworld/        # 📈 OSWorld benchmark results
├── assets/                    # 🎨 Architecture diagrams, banners
├── actions/_actions.yaml      # 📋 Atomic operation definitions
├── docs/
│   ├── core.md                # 📚 Lessons learned & hard-won rules
│   └── README_CN.md           # 🇨🇳 中文文档
├── LICENSE                    # 📄 MIT
└── requirements.txt
```

## 📦 Requirements

- **macOS** with Apple Silicon (M1/M2/M3/M4)
- **Accessibility permissions**: System Settings → Privacy → Accessibility
- Everything else installed by `bash scripts/setup.sh`

## 🤝 Ecosystem

| | |
|---|---|
| 🦞 **[OpenClaw](https://github.com/openclaw/openclaw)** | AI assistant framework — loads GUIClaw as a skill |
| 🔍 **[GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector)** | Salesforce/GPA-GUI-Detector — general-purpose UI element detection model |
| 💬 **[Discord Community](https://discord.gg/BQbUmVuD)** | Get help, share feedback |

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

## 📌 Citation

If you find GUIClaw useful in your research, please cite:

```bibtex
@misc{fu2026guiclaw,
  author       = {Fu, Zichuan},
  title        = {GUIClaw: Visual Memory-Driven GUI Automation for macOS},
  year         = {2026},
  publisher    = {GitHub},
  url          = {https://github.com/Fzkuji/GUIClaw},
}
```

---

## ⭐ Star History

<p align="center">
  <a href="https://star-history.com/#Fzkuji/GUIClaw&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Fzkuji/GUIClaw&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Fzkuji/GUIClaw&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Fzkuji/GUIClaw&type=Date" width="600" />
    </picture>
  </a>
</p>

<p align="center">
  <sub>Built with 🦞 by the GUIClaw team · Powered by <a href="https://github.com/openclaw/openclaw">OpenClaw</a></sub>
</p>
