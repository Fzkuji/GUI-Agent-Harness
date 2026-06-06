<#
=============================================================================
 GUI-Agent-Harness - one-command installer (Windows / PowerShell)
-----------------------------------------------------------------------------
 Installs EVERYTHING the harness needs to run, beyond the Python package:
   1. PyTorch (CPU by default; -Cuda cuXXX for an NVIDIA build)
   2. The harness itself (editable) + deps (ultralytics, opencv, easyocr...)
   3. The OpenProgram host (if not already importable in the target env)
   4. The GPA-GUI-Detector YOLO weight  -> %USERPROFILE%\GPA-GUI-Detector\model.pt
   5. EasyOCR language models (en + ch_sim) - pre-warmed so first run is instant
   6. Windows needs no extra system tools (Win32 + PowerShell clipboard built-in)

 Re-runnable: every step is idempotent and skips work already done.
 This is the single source of truth for GUI-specific setup; the OpenProgram
 installer (..\..\..\..\..\scripts\install.ps1) calls it with -Gui.

 Usage:
   .\scripts\install.ps1                      # CPU torch, full GUI setup
   .\scripts\install.ps1 -Cuda cu121          # CUDA 12.1 torch wheel
   .\scripts\install.ps1 -Python C:\path\python.exe
   .\scripts\install.ps1 -NoWeights -NoOcr    # skip pieces
=============================================================================
#>
[CmdletBinding()]
param(
  [string]$Cuda = "cpu",
  [string]$Python = "",
  [switch]$NoWeights,
  [switch]$NoOcr,
  [switch]$NoHost
)
# NOTE: 'Continue', not 'Stop'. Under 'Stop', Windows PowerShell 5.1 turns a
# native exe's stderr line (e.g. pip's harmless "Scripts not on PATH" warning)
# into a terminating NativeCommandError. We gate on $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"

function Step($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m){ Write-Host "  ok $m" -ForegroundColor Green }
function Warn($m){ Write-Host "  !! $m" -ForegroundColor Yellow }
function Die($m){ Write-Host "ERROR $m" -ForegroundColor Red; exit 1 }

# ---- locate repo ------------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$HarnessRoot = (Resolve-Path "$ScriptDir\..").Path
# <host>\openprogram\functions\agentics\GUI-Agent-Harness -> host is 4 up
$HostRoot    = (Resolve-Path "$HarnessRoot\..\..\..\..").Path

# ---- resolve Python ---------------------------------------------------------
# Priority: -Python > active conda/venv > host .venv > create .venv at host root.
function Resolve-Python {
  if ($Python) { return $Python }
  if ($env:VIRTUAL_ENV -and (Test-Path "$env:VIRTUAL_ENV\Scripts\python.exe")) { return "$env:VIRTUAL_ENV\Scripts\python.exe" }
  if ($env:CONDA_PREFIX -and (Test-Path "$env:CONDA_PREFIX\python.exe"))        { return "$env:CONDA_PREFIX\python.exe" }
  if (Test-Path "$HostRoot\.venv\Scripts\python.exe")                          { return "$HostRoot\.venv\Scripts\python.exe" }
  $base = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $base) { $base = (Get-Command py -ErrorAction SilentlyContinue).Source }
  if (-not $base) { Die "no python found - install Python 3.11+ first (https://www.python.org/downloads/)" }
  Step "creating virtualenv at $HostRoot\.venv"
  & $base -m venv "$HostRoot\.venv"
  return "$HostRoot\.venv\Scripts\python.exe"
}
$PY = Resolve-Python
& $PY -c "import sys; assert sys.version_info[:2] >= (3,11), sys.version" 2>$null
if ($LASTEXITCODE -ne 0) { Die "Python 3.11+ required (got: $(& $PY --version 2>&1))" }
Ok "python: $(& $PY --version 2>&1)  [$PY]"
function Pip {
  & $PY -m pip @args 2>&1 | ForEach-Object { Write-Host $_ }
  if ($LASTEXITCODE -ne 0) { Die "pip $($args -join ' ') failed (exit $LASTEXITCODE)" }
}
& $PY -m pip install --quiet --upgrade pip *> $null

# ---- 1. PyTorch (variant-controlled) ----------------------------------------
function Install-Torch {
  & $PY -c "import torch" 2>$null
  if ($LASTEXITCODE -eq 0) { Ok "torch already installed: $(& $PY -c 'import torch;print(torch.__version__)')"; return }
  Step "installing PyTorch ($Cuda)"
  if ($Cuda -eq "cpu") { Pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu }
  else                 { Pip install torch torchvision --index-url "https://download.pytorch.org/whl/$Cuda" }
  Ok "torch: $(& $PY -c 'import torch;print(torch.__version__)')"
}

# ---- 2. OpenProgram host ----------------------------------------------------
function Ensure-Host {
  if ($NoHost) { return }
  & $PY -c "import openprogram" 2>$null
  if ($LASTEXITCODE -eq 0) { Ok "openprogram host present"; return }
  if ((Test-Path "$HostRoot\pyproject.toml") -and (Select-String -Path "$HostRoot\pyproject.toml" -Pattern 'name = "openprogram"' -Quiet)) {
    Step "installing OpenProgram host (editable) from $HostRoot"; Pip install -e "$HostRoot"
  } else { Step "installing OpenProgram host from PyPI"; Pip install openprogram }
  Ok "openprogram host installed"
}

# ---- 3. the harness ---------------------------------------------------------
function Install-Harness {
  Step "installing GUI-Agent-Harness (editable, with [ocr])"
  Pip install -e "${HarnessRoot}[ocr]"
  Ok "gui-agent-harness installed"
}

# ---- 4. GPA-GUI-Detector YOLO weight ----------------------------------------
function Install-Weights {
  if ($NoWeights) { Warn "skipping weight download (-NoWeights)"; return }
  $target = if ($env:GPA_MODEL_PATH) { $env:GPA_MODEL_PATH } else { "$env:USERPROFILE\GPA-GUI-Detector\model.pt" }
  if (Test-Path $target) { Ok "GPA weight present: $target"; return }
  $dir = Split-Path -Parent $target
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  # The download needs huggingface_hub (the `hf` CLI / hf_hub_download). Usually
  # transitive with the host, but ensure it for a clean/standalone harness
  # install. Best-effort - never abort the whole install.
  & $PY -c "import huggingface_hub" 2>$null
  if ($LASTEXITCODE -ne 0) { & $PY -m pip install --quiet huggingface_hub *> $null }
  Step "downloading GPA-GUI-Detector model.pt -> $dir"
  $hf = (Get-Command hf -ErrorAction SilentlyContinue)
  if (-not $hf) { $hf = (Get-Command huggingface-cli -ErrorAction SilentlyContinue) }
  try {
    if ($hf) {
      & $hf.Source download Salesforce/GPA-GUI-Detector model.pt --local-dir $dir
    } else {
      $env:GPA_DL_DIR = $dir
      & $PY -c "import os; from huggingface_hub import hf_hub_download; print(hf_hub_download('Salesforce/GPA-GUI-Detector','model.pt',local_dir=os.environ['GPA_DL_DIR']))"
    }
  } catch { Warn "weight download failed: $_" }
  if (Test-Path $target) { Ok "GPA weight ready: $target" }
  else { Warn "weight not at $target - download manually: hf download Salesforce/GPA-GUI-Detector model.pt --local-dir `"$dir`"" }
}

# ---- 5. EasyOCR models (pre-warm) -------------------------------------------
function Prewarm-Ocr {
  if ($NoOcr) { Warn "skipping OCR pre-warm (-NoOcr)"; return }
  Step "pre-warming EasyOCR models (en + ch_sim) - downloads ~300MB on first run"
  & $PY -c "import easyocr; easyocr.Reader(['en','ch_sim'], gpu=False, verbose=False); print('EasyOCR ready')"
  if ($LASTEXITCODE -ne 0) { Warn "EasyOCR pre-warm failed (it will download lazily on first OCR instead)" }
}

# ---- run --------------------------------------------------------------------
Step "GUI-Agent-Harness setup  (os=Windows, torch=$Cuda)"
Install-Torch
Ensure-Host
Install-Harness
Install-Weights
Prewarm-Ocr
Ok "Windows uses built-in Win32 + PowerShell clipboard - no extra system tools needed"
Write-Host "`nGUI-Agent-Harness ready.  Try:  gui-agent --work-dir C:\temp\gui --app firefox `"Open Firefox`"" -ForegroundColor Green
