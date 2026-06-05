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
    <img src="https://img.shields.io/badge/Platform-macOS_%7C_Windows_%7C_Linux-black?logo=apple" />
    <img src="https://img.shields.io/badge/Provider-OpenAI_%7C_Anthropic_%7C_MiniMax-orange" />
    <img src="https://img.shields.io/badge/Detection-GPA--GUI--Detector-green" />
    <img src="https://img.shields.io/badge/OCR-Apple_Vision_%7C_EasyOCR-blue" />
    <img src="https://img.shields.io/badge/License-MIT-yellow" />
    <img src="https://img.shields.io/badge/MMBench--GUI--L2-91.52%25-brightgreen" />
  </p>
</div>

---

<p align="center">
  <b>🇺🇸 English</b> ·
  <a href="docs/README_CN.md">🇨🇳 中文</a>
</p>

---

## News

- **[2026-06-05]** 🏆 **MMBench-GUI-L2 91.52%** — GPT-5.5, 3,594 samples. [Results →](benchmarks/mmbench_gui_l2/)
- **[2026-06-05]** 🏆 **ScreenSpot Pro 87.9%** — GPT-5.5, 1,581 samples across 23 apps. [Results →](benchmarks/screenspot_pro/results/gpt_5_5/)
- **[2026-06-02]** 🏆 **ScreenSpot v2 96.78%** — GPT-5.5, 1,272 samples. [Results →](benchmarks/screenspot_v2/)
- **[2026-04-18]** 📦 **OpenProgram** — Renamed from Agentic Programming. [GitHub](https://github.com/Fzkuji/OpenProgram)
- **[2026-04-14]** 🏆 **OSWorld Multi-Apps 79.8%** — 72.6/91 evaluated. [Results →](benchmarks/osworld/multi_apps.md)
- **[2026-04-07]** 🤖 **Agent-native architecture** — Unified GUI perception + agent actions under single decision loop.
- **[2026-03-30]** 📐 **ImageContext** — Scale-independent coordinate system, fixes crop bugs.
- **[2026-03-29]** 🎬 **v0.3 — Unified Actions** — `gui_action.py` single entry point, auto platform detection.
- **[2026-03-23]** 🏆 **OSWorld Chrome 93.5%** — 43/46 one attempt, 45/46 two attempts. [Results →](benchmarks/osworld/)
- **[2026-03-10]** 🚀 **Initial release** — GPA-GUI-Detector + Apple Vision OCR + template matching.

## What is GUI Agent Harness?

A CLI tool that turns any LLM into a GUI automation agent. Give it a natural-language task, it operates the desktop autonomously — screenshots, clicks, types, verifies, and repeats until the task is done.

```bash
gui-agent --work-dir /private/tmp/gui-agent-desktop "Install the Orchis GNOME theme"
gui-agent --work-dir /private/tmp/gui-agent-vm --vm http://172.16.82.132:5000 "Open GitHub in Chrome and Python docs"
```

Built on [OpenProgram](https://github.com/Fzkuji/OpenProgram) — the runtime handles provider abstraction, context management, and structured LLM calls. The harness adds GUI perception (YOLO detection, OCR, template matching) and action execution (mouse, keyboard, clipboard).

## Grounding Pipeline: Iterative Zoom

At the core of the harness is a dedicated GUI element grounding pipeline. Given a screenshot and a natural-language description of a target element, it outputs precise click coordinates through progressive refinement.

```
Screenshot + Target description
         │
         ▼
  Phase 1: Detection          GPA-GUI-Detector (YOLO) + OCR → all visible UI elements
         │
         ▼
  Phase 2: Candidate Match    Template-match against stored visual memory
         │
         ▼
  Phase 3: LLM Grounding      VLM sees full screen + component list → identifies target region
         │
         ▼
  Phase 4: Iterative Zoom     Crop → upscale → re-ground → verify, repeat up to 8 rounds
         │
         ▼
     Precise (x, y)
```

**Key design decisions:**

- **Multi-source perception** — YOLO detection + OCR + visual memory templates provide rich spatial context to the VLM, so it reasons over labeled components rather than raw pixels alone.
- **Progressive refinement** — Instead of one-shot coordinate prediction, the pipeline iteratively crops and zooms into candidate regions. Each round gives the VLM a higher-resolution view of a smaller area.
- **Verifier gate** — After each zoom level, a separate verification step checks whether the predicted point actually lands on the target. False predictions are rejected before they become wrong clicks.
- **Cacheable prompt layout** — Fixed rules are hoisted into a cacheable prefix; only the task, component list, and image change per call. This maximizes prompt cache hit rate across the 8-round pipeline.
- **Configurable scale strategy** — `preserve` mode keeps large images at native resolution (no information loss from downscaling small targets); `fill` mode matches legacy behavior for controlled comparisons.

### Benchmark Results

| Benchmark | Samples | Accuracy | Paper Best | Delta |
|-----------|---------|----------|------------|-------|
| MMBench-GUI-L2 (full) | 3,594 | **91.52%** | 74.25% (UI-TARS-72B-DPO) | **+17.3** |
| MMBench-GUI-L2 (basic) | 1,787 | **94.89%** | — | — |
| MMBench-GUI-L2 (advanced) | 1,807 | **88.17%** | — | — |
| ScreenSpot Pro (full) | 1,581 | **87.9%** | — | — |
| ScreenSpot v2 | 1,272 | **96.78%** | — | — |

Full per-platform breakdown: [benchmarks/mmbench_gui_l2/](benchmarks/mmbench_gui_l2/) | [benchmarks/screenspot_pro/](benchmarks/screenspot_pro/)

## Agent Loop: Observe → Verify → Plan → Dispatch

For full task automation (beyond grounding), the harness runs a 4-phase loop:

- **Observe** (Python) — Screenshot + YOLO detection + OCR + template match. Identifies visible UI state.
- **Verify** (LLM) — Checks whether the previous action succeeded.
- **Plan** (LLM) — Sees the screenshot, detected components, and verification result. Chooses one action.
- **Dispatch** (Python) — Executes the action. For clicks, delegates to the iterative zoom grounding pipeline.

All phases are `@agentic_function` calls with structured feedback between steps.

## Visual Memory

UI components are detected once, labeled by a VLM, and stored as templates. On subsequent encounters, template matching replaces expensive re-detection (~5x faster, ~60x fewer tokens). States are modeled as sets of visible components, matched by Jaccard similarity. Components auto-forget after 15 consecutive misses.

## OSWorld Results

**Multi-Apps: 79.8% (72.6/91) | Chrome: 93.5% (43/46)**

| Domain | Tasks | Passed | Accuracy |
|--------|-------|--------|----------|
| Chrome | 46 | 43 | 93.5% |
| Multi-Apps | 91 | 63 | 79.8% |

[Full OSWorld results →](benchmarks/osworld/)

## Quick Start

### 1. Install

```bash
pip install openprogram
openprogram programs install gui
```

Installs [OpenProgram](https://github.com/Fzkuji/OpenProgram) (the host runtime), clones this harness, and installs all deps (ultralytics, OpenCV, Pillow, pynput).

<details>
<summary>Manual / dev install</summary>

```bash
AGENTICS=$(python -c "import openprogram,os;print(os.path.join(os.path.dirname(openprogram.__file__),'functions','agentics'))")
git clone https://github.com/Fzkuji/GUI-Agent-Harness "$AGENTICS/GUI-Agent-Harness"
pip install "$AGENTICS/GUI-Agent-Harness"
```
</details>

### 2. Provider

```bash
openprogram providers login openai-codex    # ChatGPT subscription (recommended)
# or set an API key:
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
```

Auto-detects available providers. Override with `--provider` and `--model`.

### 3. Platform

- **macOS**: grant Accessibility permission to Terminal
- **Linux**: `pip install easyocr` + `apt install wmctrl xdotool`
- **Windows**: `pip install easyocr` (Win32 API built-in, HiDPI auto-detected)

### 4. Run

```bash
gui-agent --work-dir /tmp/gui-agent-firefox --app firefox "Open Firefox, go to google.com"
gui-agent --work-dir /tmp/gui-agent-vm --vm http://VM_IP:5000 "Install the Orchis GNOME theme"
```

## Project Structure

```
GUI-Agent-Harness/
├── gui_harness/
│   ├── main.py                   # CLI entry + agent loop
│   ├── openprogram_compat.py     # OpenProgram boundary
│   ├── action/input.py           # Mouse, keyboard, clipboard
│   ├── perception/               # Screenshot, YOLO detection, OCR
│   ├── planning/
│   │   ├── component_memory.py   # Visual memory + template matching
│   │   └── screenspot_locator.py # Iterative zoom grounding pipeline
│   └── adapters/vm_adapter.py    # Remote VM I/O
├── benchmarks/
│   ├── screenspot_pro/           # ScreenSpot Pro (1,581 samples, 87.9%)
│   ├── screenspot_v2/            # ScreenSpot v2 (1,272 samples, 95.83%)
│   ├── mmbench_gui_l2/           # MMBench-GUI-L2 (3,594 samples, 91.52%)
│   └── osworld/                  # OSWorld
├── memory/                       # Per-app visual templates
├── SKILL.md                      # LLM skill definition
└── pyproject.toml
```

## License

MIT — see [LICENSE](LICENSE).

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
  <sub>Built with <a href="https://github.com/Fzkuji/OpenProgram">OpenProgram</a></sub>
</p>
