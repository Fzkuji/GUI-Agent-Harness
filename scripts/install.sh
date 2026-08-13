#!/usr/bin/env bash
# =============================================================================
# GUI-Agent-Harness — one-command installer (macOS / Linux)
# -----------------------------------------------------------------------------
# Installs EVERYTHING the harness needs to run, beyond the Python package:
#   1. PyTorch — AUTO-DETECTS an NVIDIA GPU (nvidia-smi) and installs the matching
#      CUDA build; falls back to CPU when there's no GPU. Override: --cpu / --cuda cuXXX.
#   2. The harness itself (editable) + its deps (ultralytics, opencv, easyocr…)
#   3. The OpenProgram host (if not already importable in the target env)
#   4. The GPA-GUI-Detector YOLO weight  -> ~/GPA-GUI-Detector/model.pt
#   5. EasyOCR language models (en + ch_sim) — pre-warmed so first run is instant
#   6. Platform system tools (Linux: xclip + window tools; macOS: Xcode CLT)
#
# Re-runnable: every step is idempotent and skips work already done.
# This script is the single source of truth for the GUI-specific setup; the
# OpenProgram installer (../../../../../scripts/install.sh) runs this by default.
#
# Usage:
#   ./scripts/install.sh                # auto GPU/CPU torch, full GUI setup
#   ./scripts/install.sh --cpu          # force the CPU torch build
#   ./scripts/install.sh --cuda cu124   # force a specific CUDA tag (cu121/cu124/…)
#   ./scripts/install.sh --python /path/to/python   # target a specific interp
#   ./scripts/install.sh --no-weights --no-ocr --no-system   # skip pieces
# =============================================================================
set -euo pipefail

# ---- pretty output ----------------------------------------------------------
c_blue='\033[1;34m'; c_green='\033[1;32m'; c_yellow='\033[1;33m'; c_red='\033[1;31m'; c_reset='\033[0m'
step() { printf "${c_blue}==>${c_reset} %s\n" "$*"; }
ok()   { printf "${c_green}  ok${c_reset} %s\n" "$*"; }
warn() { printf "${c_yellow}  !!${c_reset} %s\n" "$*" >&2; }
die()  { printf "${c_red}ERROR${c_reset} %s\n" "$*" >&2; exit 1; }

# ---- locate repo ------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# <host>/openprogram/programs/applications/gui_harness  -> host is 4 up
HOST_ROOT="$(cd "$HARNESS_ROOT/../../../.." && pwd)"

# ---- args -------------------------------------------------------------------
TORCH_VARIANT="auto"         # auto (detect NVIDIA GPU) | cpu | cuXXX (force, e.g. cu124)
PYTHON_BIN=""
DO_WEIGHTS=1; DO_OCR=1; DO_SYSTEM=1; ENSURE_HOST=1
while [ $# -gt 0 ]; do
  case "$1" in
    --cuda) TORCH_VARIANT="${2:?--cuda needs your CUDA tag, e.g. cu121 or cu124}"; shift 2 ;;
    --cpu) TORCH_VARIANT="cpu"; shift ;;
    --python) PYTHON_BIN="${2:?--python needs a path}"; shift 2 ;;
    --no-weights) DO_WEIGHTS=0; shift ;;
    --no-ocr) DO_OCR=0; shift ;;
    --no-system) DO_SYSTEM=0; shift ;;
    --no-host) ENSURE_HOST=0; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

OS="$(uname -s)"   # Darwin | Linux

# ---- resolve Python ---------------------------------------------------------
# Priority: --python > active venv/conda > repo .venv > create .venv at host root.
resolve_python() {
  if [ -n "$PYTHON_BIN" ]; then echo "$PYTHON_BIN"; return; fi
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then echo "$VIRTUAL_ENV/bin/python"; return; fi
  if [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then echo "$CONDA_PREFIX/bin/python"; return; fi
  if [ -x "$HOST_ROOT/.venv/bin/python" ]; then echo "$HOST_ROOT/.venv/bin/python"; return; fi
  local base; base="$(command -v python3 || command -v python || true)"
  [ -n "$base" ] || die "no python3 found — install Python 3.11+ first"
  step "creating virtualenv at $HOST_ROOT/.venv"
  "$base" -m venv "$HOST_ROOT/.venv"
  echo "$HOST_ROOT/.venv/bin/python"
}
PY="$(resolve_python)"
"$PY" -c 'import sys; assert sys.version_info[:2] >= (3,11), sys.version' \
  || die "Python 3.11+ required (got: $("$PY" --version 2>&1))"
ok "python: $("$PY" --version 2>&1)  [$PY]"
PIP() { "$PY" -m pip "$@"; }
PIP install --quiet --upgrade pip >/dev/null 2>&1 || true

# ---- 1. PyTorch (variant-controlled, BEFORE ultralytics pulls a default) ----

# Echo a CUDA wheel tag for this machine, or "" for CPU. Honors an NVIDIA GPU
# (nvidia-smi present) and the driver's max CUDA version, choosing the newest
# torch CUDA tag that the driver supports AND that actually publishes wheels.
detect_cuda_tag() {
  command -v nvidia-smi >/dev/null 2>&1 || { echo ""; return; }   # no NVIDIA GPU -> CPU
  local drv num=999999 entry tag ver
  drv="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -1)"
  [ -n "$drv" ] && num=$(echo "$drv" | awk -F. '{printf "%d%02d",$1,$2}')   # 13.1 -> 1301
  for entry in cu130:1300 cu129:1209 cu128:1208 cu126:1206 cu124:1204 cu121:1201 cu118:1108; do
    tag="${entry%%:*}"; ver="${entry##*:}"
    [ "$ver" -le "$num" ] || continue                              # tag's CUDA must be <= driver
    if "$PY" -m pip install "torch==99" --index-url "https://download.pytorch.org/whl/$tag" --no-deps --dry-run 2>&1 | grep -q "from versions:"; then
      echo "$tag"; return                                          # first tag that has wheels
    fi
  done
  echo ""   # GPU present but no usable tag -> CPU fallback
}

install_torch() {
  if "$PY" -c 'import torch' >/dev/null 2>&1; then
    local cur cuda_ok
    cur="$("$PY" -c 'import torch;print(torch.__version__)' 2>/dev/null)"
    cuda_ok="$("$PY" -c 'import torch;print(torch.cuda.is_available())' 2>/dev/null)"
    ok "torch already installed: $cur (CUDA available: $cuda_ok)"
    if [ "$cuda_ok" != "True" ] && command -v nvidia-smi >/dev/null 2>&1; then
      warn "NVIDIA GPU present but torch is CPU-only — to switch: pip uninstall -y torch torchvision, then rerun"
    fi
    return
  fi
  if [ "$OS" = "Darwin" ]; then
    step "installing PyTorch (macOS universal CPU/MPS wheel)"
    PIP install torch torchvision
    ok "torch: $("$PY" -c 'import torch;print(torch.__version__)')"
    return
  fi
  local idx
  case "$TORCH_VARIANT" in
    cpu)  idx="https://download.pytorch.org/whl/cpu"; step "installing PyTorch (CPU)" ;;
    auto) local tag; tag="$(detect_cuda_tag)"
          if [ -n "$tag" ]; then idx="https://download.pytorch.org/whl/$tag"; step "NVIDIA GPU detected → installing CUDA PyTorch ($tag)"
          else idx="https://download.pytorch.org/whl/cpu"; step "no NVIDIA GPU → installing CPU PyTorch"; fi ;;
    *)    idx="https://download.pytorch.org/whl/$TORCH_VARIANT"; step "installing PyTorch ($TORCH_VARIANT)" ;;
  esac
  PIP install torch torchvision --index-url "$idx"
  ok "torch: $("$PY" -c 'import torch;print(torch.__version__)')  (CUDA available: $("$PY" -c 'import torch;print(torch.cuda.is_available())' 2>/dev/null))"
}

# ---- 2. OpenProgram host (so the harness can run) ---------------------------
ensure_host() {
  [ "$ENSURE_HOST" = "1" ] || return 0
  if "$PY" -c 'import openprogram' >/dev/null 2>&1; then
    ok "openprogram host present"
    return
  fi
  if [ -f "$HOST_ROOT/pyproject.toml" ] && grep -q 'name = "openprogram"' "$HOST_ROOT/pyproject.toml"; then
    step "installing OpenProgram host (editable) from $HOST_ROOT"
    PIP install -e "$HOST_ROOT"
  else
    step "installing OpenProgram host from PyPI"
    PIP install openprogram
  fi
  ok "openprogram host installed"
}

# ---- 3. the harness ---------------------------------------------------------
install_harness() {
  step "installing GUI-Agent-Harness (editable, with [ocr])"
  PIP install -e "$HARNESS_ROOT[ocr]"
  ok "gui-agent-harness installed"
}

# ---- 4. GPA-GUI-Detector YOLO weight ----------------------------------------
install_weights() {
  [ "$DO_WEIGHTS" = "1" ] || { warn "skipping weight download (--no-weights)"; return 0; }
  local target="${GPA_MODEL_PATH:-$HOME/GPA-GUI-Detector/model.pt}"
  if [ -f "$target" ]; then ok "GPA weight present: $target"; return 0; fi
  local dir; dir="$(dirname "$target")"; mkdir -p "$dir"
  # The download needs huggingface_hub (the `hf` CLI / hf_hub_download). It
  # usually arrives transitively with the host, but ensure it for a clean /
  # standalone harness install. Best-effort — never abort the whole install.
  "$PY" -c "import huggingface_hub" >/dev/null 2>&1 || PIP install --quiet huggingface_hub || warn "could not install huggingface_hub"
  step "downloading GPA-GUI-Detector model.pt -> $dir"
  if command -v hf >/dev/null 2>&1; then
    hf download Salesforce/GPA-GUI-Detector model.pt --local-dir "$dir" || warn "hf download failed"
  elif command -v huggingface-cli >/dev/null 2>&1; then
    huggingface-cli download Salesforce/GPA-GUI-Detector model.pt --local-dir "$dir" || warn "huggingface-cli download failed"
  else
    "$PY" - "$dir" <<'PYEOF' || warn "python hf_hub_download failed"
import sys, shutil, os
from huggingface_hub import hf_hub_download
d = sys.argv[1]
p = hf_hub_download("Salesforce/GPA-GUI-Detector", "model.pt", local_dir=d)
print("downloaded:", p)
PYEOF
  fi
  if [ -f "$target" ]; then ok "GPA weight ready: $target"
  else warn "weight not found at $target — download manually: hf download Salesforce/GPA-GUI-Detector model.pt --local-dir $dir"; fi
}

# ---- 5. EasyOCR models (pre-warm) -------------------------------------------
prewarm_ocr() {
  [ "$DO_OCR" = "1" ] || { warn "skipping OCR pre-warm (--no-ocr)"; return 0; }
  step "pre-warming EasyOCR models (en + ch_sim) — downloads ~300MB on first run"
  "$PY" -c "import easyocr; easyocr.Reader(['en','ch_sim'], gpu=False, verbose=False); print('EasyOCR ready')" \
    || warn "EasyOCR pre-warm failed (it will download lazily on first OCR instead)"
}

# ---- 6. platform system tools -----------------------------------------------
install_system_tools() {
  [ "$DO_SYSTEM" = "1" ] || { warn "skipping system tools (--no-system)"; return 0; }
  if [ "$OS" = "Linux" ]; then
    step "installing Linux system tools (xclip required; wmctrl/xdotool/scrot optional)"
    local pkgs="xclip wmctrl xdotool scrot"
    if command -v apt-get >/dev/null 2>&1; then sudo_run apt-get update -qq && sudo_run apt-get install -y $pkgs
    elif command -v dnf >/dev/null 2>&1; then sudo_run dnf install -y $pkgs
    elif command -v pacman >/dev/null 2>&1; then sudo_run pacman -S --noconfirm $pkgs
    else warn "unknown package manager — install manually: $pkgs"; fi
  elif [ "$OS" = "Darwin" ]; then
    # macOS uses Apple Vision OCR (needs Swift from Xcode CLT). EasyOCR is the
    # cross-platform fallback and is already installed, so this is best-effort.
    if xcode-select -p >/dev/null 2>&1; then ok "Xcode command-line tools present"
    else step "requesting Xcode command-line tools (Swift, for Apple Vision OCR)"; xcode-select --install 2>/dev/null || warn "run 'xcode-select --install' manually if Apple Vision OCR is wanted"; fi
    warn "macOS: grant Terminal 'Screen Recording' + 'Accessibility' in System Settings > Privacy for screenshots/clicks"
  fi
}
sudo_run() { if [ "$(id -u)" = "0" ]; then "$@"; elif command -v sudo >/dev/null 2>&1; then sudo "$@"; else warn "no sudo — run as root: $*"; return 1; fi; }

# ---- run --------------------------------------------------------------------
step "GUI-Agent-Harness setup  (os=$OS, torch=$TORCH_VARIANT)"
install_torch
ensure_host
install_harness
install_weights
prewarm_ocr
install_system_tools
printf "\n${c_green}GUI-Agent-Harness ready.${c_reset}  Try:  gui-agent --work-dir /tmp/gui --app firefox \"Open Firefox\"\n"
