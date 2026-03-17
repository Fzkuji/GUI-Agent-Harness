<div align="center">
  <img src="assets/banner.png" alt="GUI Agent Skills" width="100%" />

  

  <p>
    <strong>Vision-based desktop automation skills for LLM agents on macOS.</strong>
    <br />
    See, learn, and control any desktop application autonomously.
  </p>

  <p>
    <img src="https://img.shields.io/badge/Platform-macOS_Apple_Silicon-black?logo=apple" />
    <img src="https://img.shields.io/badge/Skill_for-OpenClaw-red" />
    <img src="https://img.shields.io/badge/License-MIT-yellow" />
  </p>
</div>

## What Is This?

GUI-Agent-Skills is an **agent skill** — a set of instructions and tools that teach AI assistants how to control your desktop. Instead of writing automation scripts, your AI:

1. **Sees** your screen (YOLO icon detection + Apple Vision OCR)
2. **Learns** every button, icon, and UI element (saves them to memory)
3. **Remembers** what it learned (template matching, 100% accuracy, 0.3s)
4. **Acts** precisely (click, type, paste, verify)

## 🚀 Install as OpenClaw Skill

```bash
# Clone into your OpenClaw skills directory
cd ~/.openclaw/workspace/skills
git clone https://github.com/Fzkuji/GUI-Agent-Skills.git gui-agent

# Run setup (installs cliclick, Python env, detection model)
bash gui-agent/scripts/setup.sh
```

Then add to your OpenClaw config (`~/.openclaw/openclaw.json`):
```json
{
  "skills": {
    "load": {
      "extraDirs": ["~/.openclaw/workspace/skills"]
    },
    "entries": {
      "gui-agent": { "enabled": true }
    }
  }
}
```

**That's it.** Your OpenClaw agent will now read `SKILL.md` automatically when you ask it to operate any desktop app.



## 💬 Try It

Once installed, just talk to your AI naturally:

> **You**: "帮我在微信里给小明发消息，就说明天见"
>
> **AI**: "✅ 已发送给小明：明天见"

> **You**: "帮我看看周五北京到济南的高铁票"
>
> **AI**: "G29 18:00→19:31 ¥211 / G31 18:04→19:36 ¥211 — 推荐这两趟，最快1.5小时"

> **You**: "Check if my training experiment is still running"
>
> **AI**: "All GPUs at 92% utilization — experiment is still running."

> **You**: "Open Discord settings"
>
> **AI**: "✅ Opened Discord settings."

## 🧠 How It Works

```
User: "Send a message to John"
            │
            ▼
    ┌───────────────┐
    │   SKILL.md    │ Agent reads rules
    └───────┬───────┘
            ▼
    ┌───────────────┐     ┌───────────────────────┐
    │ App in memory?├──No─▶  ui_detector.py       │
    └───┬───────────┘     │  ├ GPA-GUI-Detector   │
        │ Yes             │  ├ Apple Vision OCR    │
        ▼                 │  └ Accessibility API   │
    ┌────────────┐        └───────────┬───────────┘
    │ Template   │                    │
    │ Match 0.3s │          Save to memory
    └─────┬──────┘                    │
          └──────────┬────────────────┘
                     ▼
            ┌────────────────┐
            │ Verify target  │ OCR chat header
            └───────┬────────┘
                    ▼
            ┌────────────────┐
            │ Act: click/type│ cliclick + paste
            └───────┬────────┘
                    ▼
            ┌────────────────┐
            │ Verify result  │ Confirm sent
            └────────────────┘
```

### Learn Once, Match Forever

**First interaction** — AI detects everything (~4 seconds):
```
🔍 YOLO: 43 icons    📝 OCR: 34 text elements    🔗 Merged → 24 fixed UI components
```

**Every interaction after** — instant recognition (~0.3 seconds):
```
✅ sidebar_contacts (85,214) conf=1.0
✅ emoji_button (354,530) conf=1.0
✅ search_bar_icon (202,70) conf=1.0
```

### Detection Stack

| Detector | Speed | What it finds | Why it matters |
|----------|-------|---------------|----------------|
| **[GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector)** | 0.3s | Icons, buttons | Finds gray-on-gray icons others miss |
| **Apple Vision OCR** | 1.6s | Text (CN + EN) | Best Chinese OCR available |
| **Accessibility API** | 0.1s | Dock, menus | Perfect accuracy, zero cost |
| **Template Match** | 0.3s | Anything seen before | 100% accuracy after first learn |

### App Visual Memory

Each app gets its own memory directory:
```
memory/apps/
├── wechat/
│   ├── profile.json              # Named components with coordinates
│   ├── icons/
│   │   ├── sidebar_contacts.png
│   │   ├── emoji_button.png
│   │   └── search_bar_icon.png
│   └── pages/
│       └── main_annotated.jpg
├── google_chrome/
│   ├── icons/
│   └── sites/                    # Per-website memory
│       ├── 12306_cn/
│       └── github_com/
```

## ⚠️ Safety

Real bugs taught us these rules (they're enforced in code):

- **Always verify chat recipient** before sending messages (OCR the header)
- **Window-bounded operations** — never click outside target app window
- **No tiny templates** — templates < 30×30 pixels produce false matches
- **Auto-learn validation** — only save from correct app context

## 🗂️ Project Structure

```
GUI-Agent-Skills/
├── SKILL.md              # 📖 Agent reads this first (complete instruction manual)
├── scripts/
│   ├── setup.sh          # One-command setup
│   ├── ui_detector.py    # Detection engine (YOLO + OCR + AX)
│   ├── app_memory.py     # Visual memory (learn/detect/click/verify)
│   ├── gui_agent.py      # Task executor (send_message, etc.)
│   └── template_match.py # Template matching utilities
├── memory/               # Per-app visual memory (gitignored, machine-specific)
├── actions/              # Atomic operations catalog
├── scenes/               # Per-app operation workflows (YAML)
├── apps/                 # App UI configs (JSON)
├── docs/core.md          # Hard-won lessons & principles
└── requirements.txt
```

### The `SKILL.md` Contract

`SKILL.md` is the **single source of truth** for any AI agent using GUI-Agent-Skills. It contains:
- Complete architecture and detection flow
- Safety rules (critical, read-first section)
- Step-by-step operation flows (sending messages, learning apps, clicking)
- macOS coordinate system, input methods, AX API coverage
- App-specific quirks and lessons learned

Any OpenClaw agent, Claude Code instance, or LLM that reads `SKILL.md` can fully operate the system.

## 📦 Requirements

- **macOS** with Apple Silicon (M1/M2/M3/M4)
- **Accessibility permissions**: System Settings → Privacy → Accessibility
- Everything else installed by `setup.sh`:
  - Python 3.12, cliclick, PyTorch, ultralytics
  - GPA-GUI-Detector model (40MB)

## 🤝 Ecosystem

| Tool | Role |
|------|------|
| [OpenClaw](https://github.com/openclaw/openclaw) | AI assistant framework — loads GUI-Agent-Skills as a skill |
| [GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector) | Salesforce's YOLO model for UI element detection |

## 📄 License

MIT
