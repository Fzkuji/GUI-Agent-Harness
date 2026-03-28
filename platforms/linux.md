# Linux Platform Guide

## Screenshot
```bash
# scrot (lightweight)
scrot /path/to/output.png

# gnome-screenshot
gnome-screenshot -f /path/to/output.png

# ImageMagick import
import -window root /path/to/output.png

# PyAutoGUI (Python)
import pyautogui
pyautogui.screenshot("/path/to/output.png")
```

## Input

### xdotool (recommended for X11)
```bash
# Type text (supports special characters, spaces, etc.)
xdotool type --delay 20 "Hello World"

# Type with clearmodifiers (release held keys first)
xdotool type --clearmodifiers "text with spaces"

# Key press
xdotool key Return
xdotool key ctrl+s
xdotool key ctrl+shift+t

# Mouse click
xdotool mousemove 500 300 click 1    # left click at (500, 300)
xdotool mousemove 500 300 click 3    # right click
```

### pyautogui (Python, cross-platform)
```python
import pyautogui

# Click
pyautogui.click(x, y)

# Type (ASCII only — no /, :, @, etc. on some layouts)
pyautogui.typewrite("hello", interval=0.02)

# Key press
pyautogui.press("enter")
pyautogui.press("tab")

# Key combination
pyautogui.hotkey("ctrl", "s")
pyautogui.hotkey("ctrl", "shift", "t")

# ⚠️ typewrite limitations:
# - Only ASCII characters
# - Cannot type: / : @ # $ etc. on non-US layouts
# - For these, use xdotool type or clipboard paste
```

## Clipboard
```bash
# Copy text to clipboard (X11)
echo -n "text" | xclip -selection clipboard

# Paste from clipboard
xclip -selection clipboard -o

# Alternative: xsel
echo -n "text" | xsel --clipboard --input
xsel --clipboard --output
```

**⚠️ Warning:** `xclip` sets the X11 clipboard, but Ctrl+V in some apps (especially LibreOffice) may not read it correctly. Prefer `xdotool type` for direct text input.

## Window Management (wmctrl)
```bash
# List windows
wmctrl -l

# Activate window by title
wmctrl -a "window title"

# Close window by title
wmctrl -c "window title"

# List with PIDs
wmctrl -lp
```

## OCR
Download screenshot to a Mac/host with Apple Vision, or use:
```python
# pytesseract (needs tesseract installed)
import pytesseract
from PIL import Image
text = pytesseract.image_to_string(Image.open("screenshot.png"))

# Or use the gui-agent detect_text on the host machine
# (download screenshot first, run OCR locally)
```

## Keyboard Shortcuts
| Action | Shortcut |
|--------|----------|
| Save | Ctrl+S |
| Copy | Ctrl+C |
| Paste | Ctrl+V |
| Close window/tab | Ctrl+W |
| Quit app | Ctrl+Q |
| Undo | Ctrl+Z |
| Select all | Ctrl+A |
| New tab | Ctrl+T |
| Address bar | Ctrl+L |
| Terminal | Ctrl+Alt+T |

## Common Tools
| Tool | Package | Install |
|------|---------|---------|
| xdotool | xdotool | `sudo apt install xdotool` |
| xclip | xclip | `sudo apt install xclip` |
| wmctrl | wmctrl | `sudo apt install wmctrl` |
| scrot | scrot | `sudo apt install scrot` |
| tesseract | tesseract-ocr | `sudo apt install tesseract-ocr` |

## LibreOffice-Specific Notes
- **Number display:** Large numbers may show as `3E+07` in narrow columns — this is a **display issue only**, data is intact. Widen the column to verify. Do NOT prefix with apostrophe unless the evaluator explicitly expects text type — apostrophe changes the data type from number to string, which may cause comparison failures.
- **Save dialog:** After Ctrl+S on xlsx, press Enter to confirm "Keep Current Format"
- **Name Box:** Click the cell reference box (top-left) → type cell reference (e.g., "A2") → Enter to navigate
- **Close file without quitting:** Ctrl+W (not Ctrl+Q which quits LO entirely)

## Notes
- X11 is required for xdotool and xclip (Wayland needs different tools)
- `DISPLAY` environment variable must be set (usually `:0` or `:1`)
- For remote VMs: execute commands via SSH or HTTP API, run OCR on host
- pyautogui requires a running X server (`DISPLAY` must be set)
