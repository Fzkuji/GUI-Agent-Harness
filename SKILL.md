---
name: gui-agent
description: "GUI automation via Agentic Programming. Give it a task, it handles the rest — screenshot, detect, act, verify, all automatic."
---

# GUI Agent

## Usage

```python
from gui_harness.tasks.execute_task import execute_task
from gui_harness.runtime import GUIRuntime

runtime = GUIRuntime()
result = execute_task("Open Firefox and go to google.com", runtime=runtime)
```

```bash
python3 {baseDir}/gui_harness/main.py "Open Firefox and go to google.com"
python3 {baseDir}/gui_harness/main.py --vm http://VM_IP:5000 "Click the OK button"
```

## Setup

```bash
cd {baseDir}
git submodule update --init --recursive
pip install -e ./libs/agentic-programming
pip install -e .
```
