#!/bin/bash
# GUI Agent Setup — run this on a new Mac to set up everything
# Usage: bash scripts/setup.sh
#
# Prerequisites:
#   - macOS with Apple Silicon (M1/M2/M3/M4)
#   - Homebrew installed
#   - Python 3.12+ (will install via brew if missing)
#   - cliclick (will install via brew if missing)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "🛠 GUI Agent Setup"
echo "  Skill dir: $SKILL_DIR"

# 1. Install system dependencies
echo ""
echo "=== 1. System dependencies ==="
if ! command -v cliclick &>/dev/null; then
    echo "  Installing cliclick..."
    brew install cliclick
else
    echo "  ✅ cliclick already installed"
fi

if ! command -v python3.12 &>/dev/null && ! python3 --version 2>&1 | grep -q "3.12"; then
    echo "  Installing Python 3.12..."
    brew install python@3.12
else
    echo "  ✅ Python 3.12+ available"
fi

# 2. Create Python venv
echo ""
echo "=== 2. Python virtual environment ==="
VENV_DIR="$HOME/gui-agent-env"
if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating venv at $VENV_DIR..."
    # Prefer python3.12, fallback to python3
    PYTHON=$(command -v python3.12 || command -v python3)
    $PYTHON -m venv "$VENV_DIR"
else
    echo "  ✅ venv already exists at $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# 3. Install Python packages
echo ""
echo "=== 3. Python packages ==="
pip install -q --upgrade pip
pip install -q torch torchvision torchaudio
pip install -q ultralytics opencv-python-headless numpy
pip install -q transformers accelerate huggingface-hub
pip install -q anthropic openai
echo "  ✅ Python packages installed"

# 4. Download GPA-GUI-Detector model
echo ""
echo "=== 4. GPA-GUI-Detector model ==="
MODEL_DIR="$HOME/GPA-GUI-Detector"
if [ ! -f "$MODEL_DIR/model.pt" ]; then
    echo "  Downloading GPA-GUI-Detector (40MB)..."
    python3 -c "
from huggingface_hub import hf_hub_download
import os
path = hf_hub_download('Salesforce/GPA-GUI-Detector', 'model.pt',
                        local_dir=os.path.expanduser('~/GPA-GUI-Detector'))
print(f'  ✅ Downloaded: {path}')
"
else
    echo "  ✅ Model already at $MODEL_DIR/model.pt"
fi

# 5. Create memory directory
echo ""
echo "=== 5. Memory directory ==="
mkdir -p "$SKILL_DIR/memory/apps"
echo "  ✅ Memory dir ready"

# 6. Verify everything works
echo ""
echo "=== 6. Verification ==="
python3 -c "
import torch
print(f'  PyTorch: {torch.__version__}, MPS: {torch.backends.mps.is_available()}')

from ultralytics import YOLO
import os
model = YOLO(os.path.expanduser('~/GPA-GUI-Detector/model.pt'))
print(f'  YOLO model loaded: {model.names}')

import cv2
print(f'  OpenCV: {cv2.__version__}')

print('  ✅ All good!')
"

echo ""
echo "=== Setup complete ==="
echo ""
echo "OpenClaw config — add to ~/.openclaw/openclaw.json:"
echo '  {'
echo '    "skills": { "entries": { "gui-agent": { "enabled": true } } },'
echo '    "tools": { "exec": { "timeoutSec": 60 } },'
echo '    "messages": { "queue": { "mode": "steer" } }'
echo '  }'
echo ""
echo "  timeoutSec: 60  — GUI operations take 15-30s, default timeout is too short"
echo "  queue.mode: steer — lets you interrupt/correct the agent mid-operation"
echo ""
echo "Usage:"
echo "  source ~/gui-actor-env/bin/activate"
echo "  cd $SKILL_DIR/scripts"
echo "  python3 app_memory.py learn --app WeChat    # Learn an app"
echo "  python3 app_memory.py detect --app WeChat   # Detect with memory"
echo "  python3 app_memory.py click --app WeChat --component search_bar_icon"
echo "  python3 ui_detector.py --app WeChat         # Raw detection"
echo ""
echo "Note: First run on any app will take longer (YOLO model warmup)."
echo "      Accessibility permissions may be needed — System Settings > Privacy > Accessibility"
