---
name: gui-setup
description: "First-time setup for GUI Agency Pack — install dependencies for local (Mac/Linux) and remote (VM) operation."
---

# Setup — New Machine

## Quick Start

```bash
git clone https://github.com/Fzkuji/GUI-Agent-Skills.git
cd GUI-Agent-Skills
bash scripts/setup.sh
```

## Dependencies by Platform

### macOS (local operation)

```bash
# Python venv
python3 -m venv ~/gui-agent-env
source ~/gui-agent-env/bin/activate

# Core dependencies
pip install pynput opencv-python pillow requests

# GPA-GUI-Detector (UI element detection, ~40MB)
pip install torch ultralytics
git clone https://huggingface.co/Salesforce/GPA-GUI-Detector ~/GPA-GUI-Detector

# Accessibility permissions required:
# System Settings → Privacy & Security → Accessibility → Add Terminal / OpenClaw
```

### Linux (local operation)

```bash
# System tools
sudo apt install xdotool wmctrl xclip scrot

# Python venv
python3 -m venv ~/gui-agent-env
source ~/gui-agent-env/bin/activate

# Core dependencies
pip install pyautogui opencv-python pillow requests
```

## OpenClaw Configuration

Add to `~/.openclaw/openclaw.json`:

```json
{
  "tools": {
    "exec": {
      "timeoutSec": 300
    }
  },
  "messages": {
    "queue": {
      "mode": "interrupt"
    }
  },
  "skills": {
    "entries": {
      "gui-agent": {
        "enabled": true
      }
    }
  }
}
```

- **`timeoutSec: 300`**: GUI operations (screenshot → detect → click → verify) can take time
- **`queue.mode: "interrupt"`**: lets you abort long-running GUI operations

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/activate.py` | Detect local platform, print environment info |
| `scripts/gui_action.py` | **Unified GUI action interface** — all operations go through here |
| `scripts/ui_detector.py` | OCR + YOLO UI element detection |
| `scripts/app_memory.py` | Per-app visual memory (learn/detect components) |

### gui_action.py Usage

```bash
source ~/gui-agent-env/bin/activate
cd path/to/GUI-Agent-Skills

# Local operations (default)
python3 scripts/gui_action.py click 500 300
python3 scripts/gui_action.py type "hello"
python3 scripts/gui_action.py screenshot /tmp/s.png

# Remote VM operations
python3 scripts/gui_action.py click 500 300 --remote http://VM_IP:5000
python3 scripts/gui_action.py type "hello" --remote http://VM_IP:5000
```

## Models

| Model | Size | Purpose |
|-------|------|---------|
| **GPA-GUI-Detector** | 40MB | UI element detection (YOLO-based) |

Location: `~/GPA-GUI-Detector/model.pt`

## Path Conventions

- Venv: `~/gui-agent-env/`
- Model: `~/GPA-GUI-Detector/model.pt`
- Memory: `<skill-dir>/memory/apps/<appname>/`
- Actions: `<skill-dir>/actions/`
- Backends: `<skill-dir>/scripts/backends/`
