<div align="center">
  <img src="assets/banner.png" alt="GUI Agent Harness" width="100%" />

  <br />

  <p>
    <strong>Autonomous GUI agent — give it a task, it operates the desktop.</strong>
    <br />
    <sub>Visual memory &bull; One-shot UI learning &bull; Any LLM provider &bull; Local or VM</sub>
  </p>

  <p>
    <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-blue?style=for-the-badge" /></a>
    <a href="https://github.com/Fzkuji/OpenProgram"><img src="https://img.shields.io/badge/OpenProgram-green?style=for-the-badge" /></a>
    <a href="https://discord.gg/vfyqn5jWQy"><img src="https://img.shields.io/badge/Discord-7289da?style=for-the-badge&logo=discord&logoColor=white" /></a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Platform-macOS_%7C_Linux-black?logo=apple" />
    <img src="https://img.shields.io/badge/Provider-Claude_%7C_OpenClaw_%7C_OpenAI-orange" />
    <img src="https://img.shields.io/badge/Detection-GPA--GUI--Detector-green" />
    <img src="https://img.shields.io/badge/OCR-Apple_Vision_%7C_EasyOCR-blue" />
    <img src="https://img.shields.io/badge/License-MIT-yellow" />
    <img src="https://img.shields.io/badge/OSWorld_Multi--Apps-79.8%25_(72.6/91)-brightgreen" />
  </p>
</div>

---

<p align="center">
  <b>🇺🇸 English</b> ·
  <a href="docs/README_CN.md">🇨🇳 中文</a>
</p>

---

## News

- **[2026-04-14]** 🏆 **OSWorld Multi-Apps 79.8%** — 72.6/91 evaluated tasks. 4-phase step loop + CLI session persistence + PRESERVE FORMAT work habit. [Results →](benchmarks/osworld/multi_apps.md)
- **[2026-04-18]** 📦 **OpenProgram** — Agentic Programming graduated from concept to product: repo/package/CLI renamed to [OpenProgram](https://github.com/Fzkuji/OpenProgram). Agentic Programming remains the paradigm name; OpenProgram is the shippable framework. Harness imports migrated to `from openprogram import ...`.
- **[2026-04-07]** 🤖 **Agent-native architecture** — Rebuilt execution core on the [Agentic Programming](https://github.com/Fzkuji/OpenProgram) paradigm, unifying GUI perception and free-form agent actions under a single decision loop. Eliminates task-specific scripting.
- **[2026-03-30]** 📐 **ImageContext coordinate system** — Replaced dual-space model with `ImageContext` class; scale-independent cropping, fixes crop bugs on non-fullscreen images.
- **[2026-03-29]** 🎬 **v0.3 — Unified Actions & Cross-Platform GUI** — `gui_action.py` as single entry point. Platform backends auto-selected via `--remote`.
- **[2026-03-23]** 🏆 **OSWorld Chrome 93.5%** — One attempt (43/46), 97.8% two attempts (45/46). [Results →](benchmarks/osworld/)
- **[2026-03-23]** 🔄 **Memory overhaul** — Split storage, automatic component forgetting, state merging by Jaccard similarity.
- **[2026-03-10]** 🚀 **Initial release** — GPA-GUI-Detector + Apple Vision OCR + template matching + per-app visual memory.

## What is GUI Agent Harness?

A CLI tool that turns any LLM into a GUI automation agent. You give it a natural-language task, it operates the desktop autonomously — screenshots, clicks, types, verifies, and repeats until the task is done.

```bash
gui-agent --work-dir /private/tmp/gui-agent-desktop "Install the Orchis GNOME theme"
gui-agent --work-dir /private/tmp/gui-agent-vm --vm http://172.16.82.132:5000 "Open GitHub in Chrome and Python docs"
```

**Designed as an LLM tool.** The intended workflow is:
1. An LLM (Claude Code, OpenClaw, etc.) receives a GUI task from the user
2. The LLM's skill/prompt tells it to call `gui-agent` as a CLI tool
3. `gui-agent` handles all GUI perception and interaction internally
4. The LLM gets back a result summary

The LLM doesn't need to know how GUI automation works — it just calls the tool.

## Key Ideas

- **Visual memory** — UI components are detected once, labeled by a VLM, and stored as templates. On subsequent encounters, template matching replaces expensive re-detection (~5x faster, ~60x fewer tokens).
- **State transitions** — The UI is modeled as a graph of states (sets of visible components). Successful action sequences are recorded as transitions for future replay.
- **4-phase step loop** — Each step follows: Observe (screenshot + detect) → Verify (check previous action) → Plan (LLM decides next action) → Dispatch (execute). All phases are `@agentic_function` calls with structured feedback between steps.
- **Provider-agnostic** — Works with Claude Code CLI, OpenClaw, Anthropic API, or OpenAI API. Auto-detects the best available provider.

## OSWorld Results

**Multi-Apps domain: 79.8% (72.6/91 evaluated tasks)**

| Metric | Value |
|--------|-------|
| Total tasks | 101 |
| Evaluated | 91 |
| Blocked (no credentials) | 10 |
| Passed (score = 1.0) | 63 |
| Partial (0 < score < 1.0) | 11 |

Full results: [benchmarks/osworld/multi_apps.md](benchmarks/osworld/multi_apps.md)

## Quick Start

### Step 1: Install GUI Agent Harness

```bash
pip install git+https://github.com/Fzkuji/GUI-Agent-Harness.git
```

All dependencies are installed automatically, including a pinned legacy-compatible [OpenProgram](https://github.com/Fzkuji/OpenProgram) commit, ultralytics (GPA-GUI-Detector), OpenCV, Pillow, etc. The package does not track OpenProgram's latest `main` branch during install.

> **Local development**: if you want to use an existing old OpenProgram checkout, install it first (`pip install -e /path/to/OpenProgram`) and then run `pip install -e . --no-deps` inside this repo.

For development (editable install):

```bash
git clone https://github.com/Fzkuji/GUI-Agent-Harness.git
cd GUI-Agent-Harness
pip install -e .
```

> **Warning — editable installs bake in absolute paths.** `pip install -e` writes the current project path into a `.pth` file in `site-packages`. If you later rename any parent folder, every `import gui_harness` breaks with `ModuleNotFoundError` until you rerun `pip install -e .` from the new location. The same applies to `openprogram` and to symlinks under `OpenProgram/openprogram/programs/applications/` that point into this repo — recreate them on move.
>
> Canonical layout used by this repo's dev setup (as of 2026-04-19):
>
> ```
> ~/Documents/LLM Agent Harness/OpenProgram/              # pip install -e .  (install first)
> ~/Documents/GUI Agent/GUI-Agent-Harness/                # pip install -e .  (this repo)
> ~/Documents/Research-Agent-Harness/                     # pip install -e .
> ```
>
> Optional: if you want this repo to appear inside OpenProgram's application discovery, create a symlink manually. The CLI and benchmark runner do not require it:
>
> ```bash
> cd "$OPENPROGRAM_DIR/openprogram/programs/applications"
> rm -f GUI-Agent-Harness && ln -s "$HARNESS_DIR" GUI-Agent-Harness
> ```

### Step 2: Set up an LLM provider

GUI Agent Harness needs an LLM to make decisions. Install at least one provider:

**Option A: Claude Code CLI (recommended)**

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

Uses your Claude subscription — no per-token cost. The agent runs as `claude -p` under the hood.

**Option B: Anthropic API**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Pay-per-token. Set the key in your shell profile for persistence.

**Option C: OpenAI API**

```bash
export OPENAI_API_KEY=sk-...
```

The system auto-detects the best available provider. You can also force one with `--provider`.

### Step 3: Platform setup

**macOS:**
- Grant accessibility permissions: System Settings → Privacy & Security → Accessibility → add your Terminal app
- Apple Vision OCR works automatically (no extra install)

**Linux:**
- Install EasyOCR for text detection: `pip install easyocr`
- Or install with: `pip install "gui-agent-harness[ocr] @ git+https://github.com/Fzkuji/GUI-Agent-Harness.git"`

### Step 4: Run

```bash
# Local desktop
gui-agent --work-dir /private/tmp/gui-agent-firefox --app firefox "Open Firefox and go to google.com"

# Remote VM (e.g., OSWorld)
gui-agent --work-dir /private/tmp/gui-agent-vm --vm http://VM_IP:5000 "Install the Orchis GNOME theme"

# Specify provider and model
gui-agent --work-dir /private/tmp/gui-agent-wechat --provider claude-code --model opus --app wechat "Send hello in WeChat"
```

### Use as LLM skill

GUI Agent Harness is designed to be called by an LLM as a tool. After `pip install`, register the project as a skill so your LLM can discover and use it.

LLM skill systems typically scan a skills directory for subdirectories containing a `SKILL.md` file. To register GUI Agent Harness, copy or symlink the project into your LLM's skills directory:

```bash
# Example: copy into OpenClaw's skills directory
cp -r GUI-Agent-Harness ~/.openclaw/skills/gui-agent

# Or symlink (recommended — stays in sync with git)
ln -s /path/to/GUI-Agent-Harness ~/.openclaw/skills/gui-agent
```

**Claude Code** auto-discovers `SKILL.md` from the current working directory or configured skill paths:

```bash
# Option 1: work from the project directory (auto-discovered)
cd /path/to/GUI-Agent-Harness

# Option 2: add to Claude Code's skill search paths
claude config set skillPaths '["<path-to-GUI-Agent-Harness>"]'
```

Once registered, the LLM reads `SKILL.md` and knows when and how to call `gui-agent` — no further configuration needed.

## CLI Options

```
gui-agent [OPTIONS] TASK

Arguments:
  TASK                  Natural language task description

Options:
  --work-dir PATH       Required. Runtime working directory for file writes/commands
  --vm URL              Remote VM HTTP API (e.g., http://172.16.82.132:5000)
  --provider NAME       LLM provider: auto, claude-code, openclaw, anthropic, openai
  --model NAME          Override model name (e.g., opus, sonnet, gpt-4o)
  --max-steps N         Max actions before stopping (default: 15)
  --app NAME            App name for component memory (default: desktop)
  --no-general          Disable command-line fallback; use GUI actions only
```

Detailed Chinese usage notes, including local app, VM, OSWorld, and Python-call examples, are in [docs/USAGE_CN.md](docs/USAGE_CN.md).

## Architecture

```
gui-agent --work-dir /path/to/work-dir "task description"
    │
    ▼
gui_agent()                    ← @agentic_function, drives the loop
    │
    ├── for step in 1..max_steps:
    │       │
    │       ▼
    │   gui_step()             ← @agentic_function, orchestration
    │       │
    │       ├── 1. Observe     (Python) — screenshot + detect + match + state ID
    │       ├── 2. Verify      (LLM)   — check previous action's result
    │       ├── 3. Plan        (LLM)   — decide next action
    │       └── 4. Dispatch    (Python) — execute: click/type/scroll/general
    │       │
    │       ▼
    │   build_step_feedback()  ← structured result → next iteration
    │
    └── return result summary
```

**Observe** — Pure Python. Takes a screenshot, runs GPA-GUI-Detector + OCR, matches against stored component templates, identifies the current UI state.

**Verify** — LLM call. Examines the screenshot after the previous action. Reports whether the action succeeded. Does not decide task completion.

**Plan** — LLM call. Sees the screenshot, detected components, verification result, and known state transitions. Chooses one action (click, type, scroll, general, done).

**Dispatch** — Pure Python. Executes the planned action. For clicks, uses template matching to find precise coordinates. For `general`, delegates to the LLM with full tool access (Bash, file I/O, etc.).

## Visual Memory

When a UI element is first detected, it gets a **dual representation**: a cropped visual template (for fast matching) and a VLM-assigned label (for reasoning). Stored per-app, reused across all future sessions.

```
memory/
├── linux/                     # Platform-specific memory
│   └── apps/
│       ├── desktop/           # General desktop components
│       ├── chromium/          # Browser UI
│       │   └── sites/         # Per-website memory
│       ├── gimp/
│       └── libreoffice-calc/
│           ├── components.json    # Component registry
│           ├── states.json        # UI states (component sets)
│           ├── transitions.json   # State graph edges
│           └── components/        # Template images
```

**Activity-based forgetting** — Components track consecutive misses. After 15 misses, auto-removed. Keeps memory aligned with the app's current UI.

**State matching** — States are sets of visible components, matched by Jaccard similarity (>0.7 = same state, >0.85 = auto-merge).

## Detection Stack

| Detector | Speed | Finds |
|----------|-------|-------|
| [GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector) | ~0.3s | Icons, buttons, input fields |
| Apple Vision OCR / EasyOCR | ~1.6s | Text elements |
| Template Match | ~0.3s | Known components (after first detection) |

## Built on OpenProgram

GUI Agent Harness is built on [OpenProgram](https://github.com/Fzkuji/OpenProgram) — the reference implementation of the **Agentic Programming** paradigm, where ordinary Python functions call the LLM only when reasoning is needed. Each function (`verify_step`, `plan_next_action`, `general_action`) is an `@agentic_function` that calls the LLM exactly once and returns structured data.

```python
from openprogram import agentic_function

@agentic_function(render_range={"depth": 0, "siblings": 0})
def plan_next_action(task, img_path, ..., runtime=None) -> dict:
    """Decide the next action to take toward completing the task."""
    # The per-call instruction + screen data are built into `context`.
    reply = runtime.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])
    return parse_json(reply)
```

The per-call prompt lives in `runtime.exec(content=...)`; the docstring documents the function (and is rendered into context as description). The function signature defines the interface. The framework handles context management, history summarization, and provider abstraction.

> **Naming**: *Agentic Programming* is the paradigm — Python controls the flow, the `@agentic_function` decorator records each call as a node in a flat-DAG context, and the LLM only reasons when asked. *OpenProgram* is the product (the Python package that ships the runtime). The `@agentic_function` decorator keeps the paradigm name as a visible badge of lineage.

## LLM Provider Priority

| Priority | Provider | Cost | Notes |
|----------|----------|------|-------|
| 1 | OpenClaw | Subscription | Auto-detected if `openclaw` CLI exists |
| 2 | Claude Code CLI | Subscription | Auto-detected if `claude` CLI exists |
| 3 | Anthropic API | Per-token | Requires `ANTHROPIC_API_KEY` |
| 4 | OpenAI API | Per-token | Requires `OPENAI_API_KEY` |

Override with `--provider` and `--model` flags.

## Project Structure

```
GUI-Agent-Harness/
├── gui_harness/
│   ├── main.py                # CLI entry point + gui_agent loop
│   ├── openprogram_compat.py  # OpenProgram boundary — agentic_function + create_runtime
│   ├── tasks/
│   │   └── execute_task.py    # 4-phase step: observe → verify → plan → dispatch
│   ├── action/
│   │   ├── input.py           # Mouse/keyboard primitives
│   │   └── general_action.py  # Free-form LLM action with tool access
│   ├── perception/
│   │   └── screenshot.py      # Screenshot capture (local + VM)
│   ├── planning/
│   │   ├── component_memory.py  # Template matching + state management
│   │   └── learn.py           # First-time app component learning
│   ├── memory/                # Memory management utilities
│   └── adapters/
│       └── vm_adapter.py      # Redirect all I/O to remote VM
├── benchmarks/
│   └── osworld/               # OSWorld benchmark runner + results
├── memory/                    # Visual memory storage (per-platform, per-app)
├── SKILL.md                   # LLM skill definition for gui-agent
└── pyproject.toml
```

## Requirements

- **Python 3.12+**
- **macOS** (Apple Silicon recommended for Vision OCR) or **Linux**
- At least one LLM provider (Claude Code CLI, OpenClaw, or API key)
- For VM automation: OSWorld or compatible HTTP API

## License

MIT — see [LICENSE](LICENSE) for details.

## Citation

```bibtex
@misc{fu2026gui-agent-harness,
  author       = {Fu, Zichuan},
  title        = {GUI Agent Harness: Autonomous GUI Automation with Visual Memory},
  year         = {2026},
  publisher    = {GitHub},
  url          = {https://github.com/Fzkuji/GUI-Agent-Harness},
}
```

---

<p align="center">
  <sub>Built with <a href="https://github.com/Fzkuji/OpenProgram">OpenProgram</a> — the Agentic Programming paradigm, productized</sub>
</p>
