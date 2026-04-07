---
name: gui-agent
description: "GUI automation via visual perception. Screenshot → detect → click → verify. Use when asked to operate a desktop app, interact with a VM, or complete an OSWorld benchmark task."
---

# GUI Agent

Autonomous GUI task execution. Give it a natural language task, it handles the rest.

## Usage

```bash
cd ~/Documents/GUI\ Agent\ Skills/GUI-Agent-Harness
source .venv/bin/activate
python3 gui_harness/main.py "Open Firefox and go to google.com"
```

For remote VMs (OSWorld):

```bash
python3 gui_harness/main.py --vm http://VM_IP:5000 "Add a lecture to the timetable"
```

Options:

```
--vm URL          Remote VM HTTP API (e.g., http://172.16.82.132:5000)
--max-steps N     Max actions before stopping (default: 15)
--provider NAME   Force LLM provider: openclaw, claude-code, anthropic, openai
--model NAME      Override model name
```

## What It Does

`execute_task()` runs an autonomous loop:

1. **OBSERVE** — screenshot + OCR + GPA-GUI-Detector → understand current state
2. **PLAN** — LLM decides the next action based on task and current state
3. **ACT** — execute the action (click, type, scroll, etc.)
4. **VERIFY** — screenshot again → check if action succeeded
5. **REPEAT** — until task is done or max steps reached

All sub-functions (observe, act, verify, learn, memory) are called automatically.

## First-Time Setup

```bash
cd ~/Documents/GUI\ Agent\ Skills/GUI-Agent-Harness
git submodule update --init --recursive
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./libs/agentic-programming
pip install -e .
pip install ultralytics requests
python3 -m gui_harness.platform.activate
```
