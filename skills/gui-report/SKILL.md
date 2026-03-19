---
name: gui-report
description: "Track and report GUI agent task performance — duration, token usage, operation counts. Call at START and END of every gui-agent workflow. Also view historical task data."
---

# GUI Task Report

Track every GUI task: time, tokens, and operations.

## When to Use

- **BEFORE** any gui-agent task: call `start`
- **DURING** the task: call `tick` after each screenshot/click/learn/detect/image call
- **AFTER** the task completes: call `report` with final token counts
- **On demand**: call `history` to review past tasks

## Commands

```bash
TRACKER="python3 ~/.openclaw/workspace/skills/gui-agent/skills/gui-report/scripts/tracker.py"

# 1. Start tracking (get context size from session_status, e.g. "Context: 94k" → 94000)
$TRACKER start --task "CleanMyMac cleanup" --context 94000

# 2. During task — increment counters as you go
$TRACKER tick screenshots
$TRACKER tick clicks
$TRACKER tick learns
$TRACKER tick image_calls
$TRACKER tick clicks -n 3    # batch increment

# 3. Optional notes
$TRACKER note "Clicked Ignore on quit dialog"

# 4. Final report (get context size again from session_status)
$TRACKER report --context 100000

# 5. View history
$TRACKER history
```

## Context Baseline

Get context size from `session_status` tool (the `Context: XXk/1.0m` line):
- **Before task**: record context size → `tracker start --context XXX`
- **After task**: record again → `tracker report --context XXX`
- Tracker computes the delta = how much context this task consumed

## Output Example

```
============================================================
📊 GUI Task Report: CleanMyMac cleanup
============================================================
⏱  Duration:    4.4min
📦 Context:     94.0k → 100.0k (+6.0k)
🔧 Operations:  3×screenshots, 5×clicks, 3×image_calls
============================================================
```

## Integration with gui-agent

In SKILL.md STEP 6 (Report):
1. `session_status` at task start → `tracker.py start`
2. `tick` inline with each operation
3. `session_status` at task end → `tracker.py report`

## Log Storage

`skills/gui-report/logs/task_history.jsonl` — one JSON per line.
`history` command shows formatted summary.
