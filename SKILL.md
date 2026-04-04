---
name: gui-agent
description: "GUI automation via Agentic Programming. Give it a task, it handles the rest — screenshot, detect, act, verify, all automatic."
---

# GUI Agent

## Usage

Just describe what you want done:

```python
from gui_harness import execute_task
from gui_harness.runtime import GUIRuntime

runtime = GUIRuntime()  # auto-detects OpenClaw
result = execute_task("Open Firefox and go to google.com", runtime=runtime)
```

Or from OpenClaw, just call:

```bash
python3 {baseDir}/gui_harness/main.py "Open Firefox and go to google.com"
```

## What It Does

`execute_task()` runs an autonomous loop:

1. **OBSERVE** — screenshot + OCR + detection → understand current state
2. **PLAN** — LLM decides the next action based on the task and current state
3. **ACT** — execute the action (click, type, scroll, etc.)
4. **VERIFY** — screenshot again → check if action succeeded
5. **REPEAT** — until task is done or max steps reached

All sub-functions (`observe`, `act`, `verify`, `learn`, `navigate`) are called automatically. You don't need to call them manually.

## For VMs (OSWorld)

```python
from gui_harness.primitives.vm_adapter import patch_for_vm
patch_for_vm("http://VM_IP:5000")
# Then use execute_task() normally — it routes through the VM.
```

## First-Time Setup

```bash
cd {baseDir}
pip install -e .
python3 scripts/activate.py   # detect platform, install dependencies
```

## Core Rules

- **Coordinates from detection only** — OCR or GPA-GUI-Detector, never guessed
- **Look before you act** — every action justified by what was observed
- **Verify after every action** — screenshot to confirm it worked
