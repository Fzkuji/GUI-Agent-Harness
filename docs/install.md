# Installing the GUI agent

The GUI agent is an **OpenProgram program** — it runs *inside* an OpenProgram
host, not on its own. So the order is always:

1. **Install OpenProgram** (the host). See
   [OpenProgram/docs/install.md](../../../../../docs/install.md).
2. **Install this harness into it.** It lands in
   `openprogram/functions/agentics/GUI-Agent-Harness/` and is **auto-registered**
   — `gui_agent` then shows up in the web UI and function list automatically.

The fastest route does both at once from the OpenProgram checkout:
```bash
./scripts/install.sh --gui          # macOS/Linux   (-Cuda/-cuda cu121 for NVIDIA)
.\scripts\install.ps1 -Gui          # Windows
```

The rest of this page is for installing/repairing **just the GUI agent** on a
host you already have.

---

## One command (GUI agent only)

From the harness directory (`…/functions/agentics/GUI-Agent-Harness`):

**macOS / Linux**
```bash
./scripts/install.sh                 # CPU PyTorch (default)
./scripts/install.sh --cuda cu121    # NVIDIA CUDA 12.1
```

**Windows (PowerShell)**
```powershell
.\scripts\install.ps1                 # CPU PyTorch (default)
.\scripts\install.ps1 -Cuda cu121     # NVIDIA CUDA 12.1
```

Then run a task — `gui_agent` is also live in the web UI after a worker restart:
```bash
gui-agent --work-dir /tmp/gui-firefox --app firefox "Open Firefox, go to google.com"
```

Idempotent and re-runnable. It targets the active `venv`/conda env (or
`--python <path>`), and installs the OpenProgram host too if it isn't importable.

> **Why a script and not just `pip`?** `pip install` of this harness pulls the
> Python deps, but the agent also needs a YOLO detector weight and OCR models
> that pip can't fetch. The script is the complete, authoritative install.

---

## What it installs

| Step | Action | Notes |
|------|--------|-------|
| 1 | **PyTorch** (+ torchvision) | CPU wheel by default; `--cuda cuXXX` for NVIDIA. Installed first so ultralytics doesn't pull a mismatched default. |
| 2 | **OpenProgram host** | Only if not importable (editable from the repo, else PyPI). Skip with `--no-host` / `-NoHost`. |
| 3 | **The harness** (editable, in-tree) | `pip install -e .[ocr]` → ultralytics, opencv, numpy, Pillow, pynput, easyocr. In-tree under `functions/agentics/` ⇒ **auto-registers** `gui_agent`. |
| 4 | **GPA YOLO weight** | `Salesforce/GPA-GUI-Detector/model.pt` → `~/GPA-GUI-Detector/model.pt` (~40 MB). Skipped if present. Override path with `GPA_MODEL_PATH`. |
| 5 | **EasyOCR models** | Pre-warms `en` + `ch_sim` into `~/.EasyOCR/model` (~300 MB). |
| 6 | **Platform tools** | Linux: `xclip` (+ wmctrl/xdotool/scrot). macOS: Xcode CLT for Apple Vision OCR (best-effort; EasyOCR fallback). Windows: none. |

### Flags

| Goal | POSIX | Windows |
|------|-------|---------|
| CUDA torch | `--cuda cu121` | `-Cuda cu121` |
| Specific interpreter | `--python /path/python` | `-Python C:\path\python.exe` |
| Skip weight download | `--no-weights` | `-NoWeights` |
| Skip OCR pre-warm | `--no-ocr` | `-NoOcr` |
| Skip installing the host | `--no-host` | `-NoHost` |
| Skip Linux system tools | `--no-system` | *(n/a)* |

---

## Platform notes

**Windows** — fully self-contained: screenshots, clicks, and clipboard use the
built-in Win32 API + PowerShell, so no extra system packages. CPU PyTorch is the
default. HiDPI auto-detected; opt out with `OPENPROGRAM_GUI_NO_DPI_AWARE=1`.

**Linux** — needs `xclip` for the clipboard (installed via `apt`/`dnf`/`pacman`).
`wmctrl`/`xdotool` (windows) and `scrot`/`gnome-screenshot`/`imagemagick`
(screenshot fallbacks) are best-effort. OCR uses EasyOCR.

**macOS** — uses native Apple Vision OCR (needs the Swift compiler from
`xcode-select --install`; the installer requests it best-effort, with EasyOCR as
a working fallback). Grant Terminal **Screen Recording** + **Accessibility** in
System Settings → Privacy & Security so the agent can capture and control.

---

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `GPA_MODEL_PATH` | Path to the YOLO weight | `~/GPA-GUI-Detector/model.pt` |
| `OPENPROGRAM_GUI_NO_DPI_AWARE` | Disable Windows per-monitor DPI awareness | unset |

---

## Remote VM mode (optional)

`gui-agent --vm http://VM_IP:5000 "…"` drives a remote desktop. The VM needs a
small HTTP server exposing `POST /execute` and `GET /screenshot` (e.g. an OSWorld
env). See [VM_SETUP.md](VM_SETUP.md).

---

## Troubleshooting

- **`gui_agent` not in the web UI** — restart the worker / Refresh the Functions
  page. Confirm registration from the host: `openprogram programs available`.
- **`GPA-GUI-Detector model not found`** — fetch the weight:
  `hf download Salesforce/GPA-GUI-Detector model.pt --local-dir ~/GPA-GUI-Detector`.
- **First OCR hangs for a minute** — EasyOCR is downloading; pre-warming (default)
  avoids this.
- **NVIDIA GPU unused** — you installed the CPU torch build; re-run with `--cuda cu121`.
- **`gui-agent: command not found`** — activate the env the harness was installed into.
