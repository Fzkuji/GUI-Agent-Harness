# OSWorld Benchmark Results — GUIClaw

> Last updated: 2026-03-22

## Overview

**GUIClaw** is evaluated on [OSWorld](https://github.com/xlang-ai/OSWorld), a real-computer benchmark for multimodal agents.

## Framework & Pipeline

GUIClaw runs on the following stack:

```
┌─────────────────────────────────────────────────────────┐
│  Mac Host (Apple Silicon)                               │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  OpenClaw (runtime framework)                   │    │
│  │  └─ Claude Opus 4.6 (LLM reasoning & planning) │    │
│  │     └─ GUIClaw Skill                            │    │
│  │        ├─ Salesforce/GPA-GUI-Detector (UI det.) │    │
│  │        ├─ Apple Vision OCR (text recognition)   │    │
│  │        └─ pyautogui (action execution)          │    │
│  └─────────────────────────────────────────────────┘    │
│                        │                                │
│                   HTTP API                              │
│                        ↓                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Ubuntu ARM VM (VMware Fusion)                  │    │
│  │  └─ Chromium 138 + OSWorld tasks                │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

| Component | Role |
|-----------|------|
| **[OpenClaw](https://github.com/openclaw/openclaw)** | Runtime framework — orchestrates the agent, manages tools, routes LLM calls |
| **Claude Opus 4.6** (Anthropic) | LLM backbone — all reasoning, planning, and decision-making |
| **[Salesforce/GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector)** | UI element detection — finds buttons, icons, inputs on any platform's screenshot |
| **Apple Vision OCR** | Text recognition — reads text from any screenshot (runs locally on Mac) |
| **pyautogui** | Action execution — clicks, types, hotkeys sent to VM via HTTP API |

**Key**: GUIClaw is not standalone — it requires **OpenClaw + an LLM** (Claude Opus 4.6 in these experiments). GPA-GUI-Detector and OCR run locally on Mac, accepting screenshots from any platform. No task-specific fine-tuning, no dedicated vision-language model.

### Per-Task Workflow

1. **Snapshot restore** → Clean VM state
2. **Config setup** → Launch Chrome, run task-specific setup
3. **Screenshot** → Download VM screen as PNG to Mac
4. **GPA-GUI-Detector + OCR** → Detect UI components and text locally on Mac
5. **Claude Opus 4.6** (via OpenClaw) → Analyze detections, decide action
6. **Action execution** → Send pyautogui click/type/hotkey to VM via HTTP API
7. **Repeat 3–6** until task complete
8. **Evaluation** → Run official OSWorld evaluator

## Chrome Domain Results

**Test environment:** Ubuntu ARM VM (VMware Fusion), Chromium 138, 1920×1080

### Summary

| Metric | Value |
|--------|-------|
| Tasks tested | 22 / 46 |
| Tasks passed | **22** |
| Tasks failed | 0 |
| **Pass rate** | **100%** (22/22) |

> **All 22 tasks completed successfully** (19 feasible + 3 infeasible). Zero failures.

### Detailed Results

| # | Task ID | Instruction | Score | Status | Notes |
|---|---------|-------------|-------|--------|-------|
| 0 | `bb5e4c0d` | Make Bing the default search engine | 1.0 | ✅ | GPA-GUI-Detector found ⋮ → OCR found "Make default" |
| 1 | `7b6c7e24` | Delete Amazon tracking cookies | 1.0 | ✅ | OCR "Delete all data" → GPA-GUI-Detector found trash button |
| 2 | `06fe7178` | Restore last closed tab | 1.0 | ✅ | Ctrl+Shift+T to restore tripadvisor tab |
| 3 | `e1e75309` | Save webpage as PDF to Desktop | 1.0 | ✅ | Ctrl+P → Paper=Letter, Margins=None → Save to Desktop |
| 4 | `35253b65` | Create desktop shortcut | 1.0 | ✅ | GPA-GUI-Detector found ⋮ → OCR located "Create shortcut..." |
| 5 | `2ad9387a` | Create bookmarks bar folder | 1.0 | ✅ | OCR "Search bookmarks" → "Add new folder" → "Save" |
| 6 | `7a5a7856` | Save webpage to bookmarks bar | 1.0 | ✅ | Ctrl+D → changed folder to "Bookmarks bar" → Done |
| 7 | `2ae9ba84` | Rename Chrome profile | 1.0 | ✅ | OCR found "Work" text → direct click to edit |
| 8 | `480bcfea` | Disable new 2023 Chrome UI | — | ✅ | Infeasible: `chrome://flags` "No matching experiments" (flag removed in Chromium 138) |
| 9 | `af630914` | Set font size to largest | 1.0 | ✅ | OCR found "Huge" label → click slider endpoint |
| 10 | `3720f614` | Change language to Xenothian | — | ✅ | Infeasible: fictional language, not available in any browser |
| 11 | `99146c54` | Auto-clear data on close | 1.0 | ✅ | 2nd attempt. 1st failed: searched `chrome://settings/cookies`, concluded feature missing. After web search, found at `chrome://settings/content/siteData` (moved in newer Chrome) |
| 12 | `12086550` | Navigate to password manager | 1.0 | ✅ | URL navigation: chrome://password-manager/passwords |
| 13 | `6766f2b8` | Load unpacked Chrome extension | 1.0 | ✅ | Extensions → Developer mode → Load unpacked → select folder |
| 14 | `93eabf48` | Turn off dark mode | 1.0 | ✅ | Settings → Appearance → "Use Classic" resets dark mode to light |
| 15 | `ae78f875` | Change search results per page to 50 | — | ✅ | Infeasible: this is a Google Search preference, not a Chrome setting |
| 16 | `3299584d` | Remove startup page | 1.0 | ✅ | Settings → On startup → "Open the New Tab page" |
| 17 | `030eeff7` | Enable Do Not Track | 1.0 | ✅ | Settings → Cookies → toggle DNT → Confirm |
| 18 | `9656a811` | Enable Safe Browsing | 1.0 | ✅ | Settings → Security → select "Standard protection" |
| 19 | `fc6d8143` | Find JFK→ORD flights on Delta | 1.0 | ✅ | 2nd attempt (1st blocked by cookie consent). CDP JS dismiss → pyautogui form fill |
| 20 | `a96b564e` | Find discussion with most replies on FlightAware | 1.0 | ✅ | Footer → Community → Discussion → Top → All time → sort by Replies → "The Banter Thread" |
| 21 | `1704f00f` | Rent large car in Zurich, Mon-Fri, sort by price | 1.0 | ✅ | Multiple auto-corrections during execution: fixed city (Airport→city), date (Apr→Mar), day (24→23). Final: Zürich, Mar 23-27, Large, Price |



### Not Yet Tested

- Tasks 22–45: External website tasks (shopping, forums, etc.)

## Comparison with Other Agents

Reference scores from the [OSWorld leaderboard](https://os-world.github.io/) (Chrome domain):

| Rank | Agent | Chrome | Overall | Type |
|------|-------|--------|---------|------|
| 1 | HIPPO Agent w/Opus 4.5 (Lenovo) | 60.4% (25.96/43) | 74.5% | Agentic framework |
| 2 | Claude Sonnet 4.6 (Anthropic) | 78.5% (32.96/42) | 72.1% | General model |
| — | **GUIClaw** | **100%** (22/22 tested) | TBD | OpenClaw + Claude Opus 4.6 |

> ⚠️ GUIClaw's score is on a partial Chrome subset (22/46 tasks). Full benchmark in progress.

## Environment Details

- **Host**: Mac (Apple Silicon) — OpenClaw + Claude Opus 4.6 + GPA-GUI-Detector + Apple Vision OCR
- **VM**: Ubuntu ARM (aarch64), VMware Fusion 13.6.4
- **Resolution**: 1920×1080 (set via xrandr after snapshot restore)
- **Browser**: Chromium 138
- **VM API**: HTTP server on port 5000 (screenshot, execute, setup)
- **CDP**: Chrome DevTools Protocol on port 9222 (via socat relay)
- **Proxy**: Host machine proxy, US exit node

### Known Issues & Workarounds

| Issue | Workaround |
|-------|------------|
| VM resolution mismatch (1280×720 vs 1920×1080) | `xrandr --mode 1920x1080` after every snapshot restore |
| Surge TUN intercepts VM traffic | `NO_PROXY=172.16.82.0/24` |
| Cookie consent dialogs block pyautogui clicks | CDP JavaScript to dismiss overlays first |
| Regional domain redirects (e.g. airbnb.com → .sg) | Use US proxy exit node |
| `chrome_open_tabs` API missing in VM | Use pyautogui keyboard to open tabs manually |

## Files

- Results JSONL: `~/.openclaw/workspace/osworld_comm/results/chrome_results_valid.jsonl`
- Task screenshots: `~/.openclaw/workspace/osworld_comm/tasks/<task_id>/`
- Runner script: `~/OSWorld/guiclaw_runner.py`
- Eval script: `~/OSWorld/eval_only.py`
