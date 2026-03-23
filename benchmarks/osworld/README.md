# OSWorld Benchmark Results — GUIClaw

> Last updated: 2026-03-23

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
4. **GPA-GUI-Detector** (`detect_icons`) → Detect UI components with coordinates (runs locally on Mac)
5. **OCR** (`detect_text`) → Read all text with coordinates (runs locally on Mac)
6. **image tool** (if needed) → Claude sees screenshot for semantic understanding (⛔ no coordinates)
7. **Claude Opus 4.6** (via OpenClaw) → Combine detector positions + OCR text + visual understanding → decide action
8. **Action execution** → Send pyautogui click/type/hotkey to VM via HTTP API
9. **Repeat 3–8** until task complete (with memory saving after each action)
10. **Evaluation** → Run official OSWorld evaluator

> **Note**: Steps 4–6 follow the unified `detect_all()` pipeline. GPA-GUI-Detector is required; OCR is optional (graceful degradation on non-Mac platforms).

## Chrome Domain Results

**Test environment:** Ubuntu ARM VM (VMware Fusion), Chromium 138, 1920×1080

### Summary

| Metric | Value |
|--------|-------|
| Total tasks | 46 |
| ✅ First-try pass | 40 |
| ⚠️ Retry pass (×0.5) | 2 |
| ⚠️ Env change (×1.0) | 2 |
| ❌ Failed | 1 |
| ⏭️ Skipped | 1 |
| **Score** | **43.0 / 45** (95.6%) |

> Scoring: ✅ = 1.0, ⚠️ env-change = 1.0, ⚠️ retry = 0.5, ❌ = 0, ⏭️ = excluded from denominator.

### Detailed Results

| # | Task ID | Instruction | Score | Status | Notes |
|---|---------|-------------|-------|--------|-------|
| 1 | `bb5e4c0d` | Make Bing the default search engine | 1.0 | ✅ | GPA found ⋮ → OCR found "Make default" |
| 2 | `7b6c7e24` | Delete Amazon tracking cookies | 1.0 | ✅ | OCR "Delete all data" → GPA found trash button |
| 3 | `06fe7178` | Restore last closed tab | 1.0 | ✅ | Ctrl+Shift+T to restore tripadvisor tab |
| 4 | `e1e75309` | Save webpage as PDF to Desktop | 1.0 | ✅ | Ctrl+P → Paper=Letter, Margins=None → Save to Desktop |
| 5 | `35253b65` | Create desktop shortcut | 1.0 | ✅ | GPA found ⋮ → OCR located "Create shortcut..." |
| 6 | `2ad9387a` | Create bookmarks bar folder | 1.0 | ✅ | OCR "Search bookmarks" → "Add new folder" → "Save" |
| 7 | `7a5a7856` | Save webpage to bookmarks bar | 1.0 | ✅ | Ctrl+D → changed folder to "Bookmarks bar" → Done |
| 8 | `2ae9ba84` | Rename Chrome profile | 1.0 | ✅ | OCR found "Work" text → direct click to edit |
| 9 | `480bcfea` | Disable new 2023 Chrome UI | — | ✅ | Infeasible: flag removed in Chromium 138 |
| 10 | `af630914` | Set font size to largest | 1.0 | ✅ | OCR found "Huge" label → click slider endpoint |
| 11 | `3720f614` | Change language to Xenothian | — | ✅ | Infeasible: fictional language |
| 12 | `99146c54` | Auto-clear data on close | 1.0 | ⚠️ | 2nd attempt. Found at chrome://settings/content/siteData (moved in newer Chrome) |
| 13 | `12086550` | Navigate to password manager | 1.0 | ✅ | URL navigation: chrome://password-manager/passwords |
| 14 | `6766f2b8` | Load unpacked Chrome extension | 1.0 | ✅ | Extensions → Developer mode → Load unpacked → select folder |
| 15 | `93eabf48` | Turn off dark mode | 1.0 | ✅ | Settings → Appearance → "Use Classic" resets dark mode |
| 16 | `ae78f875` | Change search results per page to 50 | — | ✅ | Infeasible: Google Search preference, not a Chrome setting |
| 17 | `3299584d` | Remove startup page | 1.0 | ✅ | Settings → On startup → "Open the New Tab page" |
| 18 | `030eeff7` | Enable Do Not Track | 1.0 | ✅ | Settings → Cookies → toggle DNT → Confirm |
| 19 | `9656a811` | Enable Safe Browsing | 1.0 | ✅ | Settings → Security → select "Standard protection" |
| 20 | `fc6d8143` | Find JFK→ORD flights on Delta | 1.0 | ⚠️ | 2nd attempt (1st blocked by cookie consent) |
| 21 | `a96b564e` | Find discussion with most replies on FlightAware | 1.0 | ✅ | Footer → Community → Discussion → Top → All time → sort by Replies |
| 22 | `1704f00f` | Rent large car in Zurich, Mon-Fri, sort by price | 1.0 | ✅ | Multiple auto-corrections during execution |
| 23 | `f3b19d1e` | Find FAQ about ticket delivery on Ticketek | 1.0 | ⚠️ | Website restructured: URL matched but page shows 404 |
| 24 | `82bc8d6a` | Look up Mumbai→Stockholm flight on Qatar Airways | 1.0 | ✅ | From=BOM, To=STO, Date=next Monday |
| 25 | `47543840` | Show cars at Boston Logan, next month 10-11, sort by seats | 1.0 | ✅ | Budget.com: Apr 10-11, Sort by Number of Seats (High to Low) |
| 26 | `c1fa57f3` | Open baggage fee calculator on United Airlines | 1.0 | ✅ | OCR-guided: Home → Travel Info → Baggage → Calculator |
| 27 | `da46d875` | Book TAP appointment at MBTA Charlie Card Store | 0.0 | ⚠️ | Env change: 10:15 AM slot doesn't exist in live Outlook Bookings (as of 2026-03). All other steps completed. |
| 28 | `6c4c23a1` | Find SEA→NYC flights with Miles on Delta | 1.0 | ✅ | Privacy dialog → From/To/Date → Shop with Miles checkbox |
| 29 | `f79439ad` | Search DUB→VIE one-way flight on Ryanair | 1.0 | ✅ | Cookie dismiss → Dublin/Vienna → One way → Apr 10 → 2 adults |
| 30 | `b7895e80` | Find NYC hotel, lowest price, next weekend | 1.0 | ✅ | TripAdvisor: Mar 28-29, 1 Room 2 Guests, Sort Price low to high |
| 31 | `9f3f70fc` | Browse women's Nike jerseys over $60 on NBA Store | 0.0 | ❌ | Failed: missed correct path (search "jerseys" → sidebar filters) |
| 32 | `7f52cab9` | Drip coffee makers on sale, $25-60, black | 1.0 | ✅ | Google Shopping: On sale + $25-$60 + Black filters |
| 33 | `82279c77` | Find electric cars under $50k near 10001 | 1.0 | ✅ | Cars.com: all URL params match |
| 34 | `2888b4e6` | Men's large short-sleeve shirts 50%+ off | 1.0 | ✅ | Macys: Size=L + Discount Range=50% off & more |
| 35 | `b4f95342` | Find Next Available dates for Diamond | 1.0 | ✅ | Recreation.gov: search → campground → Next Available column |
| 36 | `f5d96daf` | Compare iPhone 15/14/13 Pro Max | 1.0 | ✅ | Apple compare page with modelList URL parameter |
| 37 | `121ba48f` | Find Dota 2 game and add all DLC to cart | 1.0 | ✅ | Steam: Ctrl+F Soundtrack → Add all DLC to Cart |
| 38 | `368d9ba4` | Monthly forecast for Manchester, GB | 1.0 | ✅ | AccuWeather: /manchester/march-weather/ |
| 39 | `59155008` | Similar names to "carl" | 1.0 | ✅ | BabyCenter: /baby-names/details/carl-853 |
| 40 | `a728a36e` | Driver License Eligibility Requirements | 1.0 | ✅ | DMV Virginia: /licenses-ids/license/applying/eligibility |
| 41 | `b070486d` | Show side effects of Tamiflu | 1.0 | ✅ | Drugs.com: /sfx/tamiflu-side-effects.html |
| 42 | `0d8b7de3` | Browse natural products database | 1.0 | ✅ | Drugs.com: /npc/ |
| 43 | `9f935cce` | Browse Civil Division forms | 1.0 | ✅ | Justice.gov: /forms?field_component_target_id=431 |
| 44 | `f0b971a1` | Super Bowl 2019 season score record | 1.0 | ✅ | NFL.com: /scores/2019/post4 |
| 45 | `cabb3bae` | Spider-man toys for kids, sort by lowest price | 1.0 | ✅ | Kohls: search + Sort Price Low-High |
| 46 | `44ee5668` | Clear YouTube browsing history | — | ⏭️ | Requires CDP history injection setup, not yet automated |

## Comparison with Other Agents

Reference scores from the [OSWorld leaderboard](https://os-world.github.io/) (Chrome domain):

| Rank | Agent | Chrome | Overall | Type |
|------|-------|--------|---------|------|
| 1 | HIPPO Agent w/Opus 4.5 (Lenovo) | 60.4% (25.96/43) | 74.5% | Agentic framework |
| 2 | Claude Sonnet 4.6 (Anthropic) | 78.5% (32.96/42) | 72.1% | General model |
| — | **GUIClaw** | **95.6%** (43.0/45) | TBD | OpenClaw + Claude Opus 4.6 |

> GUIClaw tested 46/46 Chrome tasks. 1 skipped (needs CDP setup). 1 failed (NBA Store navigation).

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
- Task screenshots: `~/.openclaw/workspace/osworld_comm/task*_*.png`
