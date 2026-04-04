# Agentic Programming Integration

> `gui_harness/` — GUI automation powered by [Agentic Programming](https://github.com/Fzkuji/Agentic-Programming)

## Architecture

```
┌─────────────────────────────────────────────────┐
│  OpenClaw Agent (the LLM — Claude/GPT/etc.)     │
│  ┌───────────────────────────────────────────┐   │
│  │ OpenClaw session accumulates context      │   │
│  │ Agent decides what to do next             │   │
│  │ Agent calls gui_harness functions         │   │
│  └──────────┬────────────────────────────────┘   │
│             │ calls                               │
│  ┌──────────▼────────────────────────────────┐   │
│  │ gui_harness/functions/                    │   │
│  │  @agentic_function(summarize={d:0, s:0})  │   │
│  │  observe() → screenshot + OCR + LLM       │   │
│  │  act()     → find target + click          │   │
│  │  verify()  → check result                 │   │
│  │  learn()   → label UI components          │   │
│  │  navigate()→ BFS state graph (compress)   │   │
│  └──────────┬────────────────────────────────┘   │
│             │ calls                               │
│  ┌──────────▼────────────────────────────────┐   │
│  │ gui_harness/primitives/                   │   │
│  │  screenshot.take()                        │   │
│  │  ocr.detect_text()                        │   │
│  │  detector.detect_all()                    │   │
│  │  input.mouse_click() / paste_text()       │   │
│  │  template_match.find_template()           │   │
│  │  (pure Python, no LLM, no decorator)      │   │
│  └───────────────────────────────────────────┘   │
│             │ calls                               │
│  ┌──────────▼────────────────────────────────┐   │
│  │ scripts/                                  │   │
│  │  platform_input.py (pynput/cliclick)      │   │
│  │  ui_detector.py (GPA + Apple Vision OCR)  │   │
│  │  template_match.py                        │   │
│  │  app_memory.py (state graph + components) │   │
│  └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## Context Management: Two Modes

Agentic Programming supports two context modes via `@agentic_function(summarize=...)`:

### Session Mode (OpenClaw) — Default

```python
@agentic_function(summarize={"depth": 0, "siblings": 0})
def observe(task, runtime=None):
    """Only sends this call's data. OpenClaw accumulates context."""
    return runtime.exec(content=[...])
```

- **`summarize={"depth": 0, "siblings": 0}`** — skip Context tree injection
- OpenClaw agent IS the runtime; it sees all prior calls in its session
- Each function only sends its own screenshot + OCR data
- No redundant context duplication

### API Mode (Standalone) — For non-OpenClaw use

```python
@agentic_function  # summarize=None (default) → full context injection
def observe(task, runtime=None):
    """Injects full Context tree into every LLM call."""
    return runtime.exec(content=[...])
```

- **`summarize=None`** (default) — auto-inject ancestor + sibling summaries
- Needed when calling stateless APIs directly (no session memory)
- Each LLM call receives the full execution history

**Current gui_harness uses Session Mode** because it's designed for OpenClaw.

## Runtime: GUIRuntime

`GUIRuntime` routes LLM calls through OpenClaw gateway (`/v1/chat/completions`):

```python
from gui_harness.runtime import GUIRuntime

runtime = GUIRuntime(
    gateway_url="http://localhost:18789",  # OpenClaw gateway
    model="anthropic/claude-sonnet-4-6",   # any model OpenClaw supports
)
```

- Uses OpenClaw's auth (no separate API keys needed)
- Supports all models configured in OpenClaw (Claude, GPT, Gemini, etc.)
- Image content blocks are base64-encoded automatically

## Functions

| Function | Decorator | Calls LLM? | Description |
|----------|-----------|------------|-------------|
| `observe()` | `@agentic_function(summarize={d:0,s:0})` | Yes | Screenshot + OCR + detection + LLM analysis |
| `act()` | `@agentic_function(summarize={d:0,s:0})` | Yes | Find target + execute click/type |
| `verify()` | `@agentic_function(summarize={d:0,s:0})` | Yes | Check if action succeeded |
| `learn()` | `@agentic_function(summarize={d:0,s:0})` | Yes | Label UI components |
| `navigate()` | `@agentic_function(compress=True)` | No* | BFS state graph navigation |
| `remember()` | `@agentic_function` | No | Manage visual memory |
| `send_message()` | `@agentic_function(compress=True)` | No* | High-level: observe → navigate → type → verify |
| `read_messages()` | `@agentic_function(compress=True)` | No* | High-level: navigate → observe |

\* These functions call other `@agentic_function`s internally, which may call LLM.

`compress=True` means callers see only the final result — internal sub-steps are hidden from `summarize()`.

## VM Support

For remote VMs (e.g., OSWorld Ubuntu), use `vm_adapter.py`:

```python
from gui_harness.primitives.vm_adapter import patch_for_vm
patch_for_vm("http://172.16.105.128:5000")

# Now all primitives route through the VM HTTP API:
# screenshot → GET /screenshot
# mouse/keyboard → POST /execute (pyautogui)
# OCR/detection → still runs locally on downloaded screenshots
```

## File Structure

```
gui_harness/
├── __init__.py              # from gui_harness import observe, act, ...
├── runtime.py               # GUIRuntime → OpenClaw gateway
├── functions/
│   ├── observe.py           # @agentic_function — screenshot + OCR + LLM
│   ├── act.py               # @agentic_function — find + execute
│   ├── verify.py            # @agentic_function — verify result
│   ├── learn.py             # @agentic_function — learn UI
│   ├── navigate.py          # @agentic_function(compress) — state graph
│   └── remember.py          # @agentic_function — memory ops
├── tasks/
│   ├── send_message.py      # @agentic_function(compress)
│   └── read_messages.py     # @agentic_function(compress)
├── primitives/
│   ├── screenshot.py        # → scripts/platform_input
│   ├── ocr.py               # → scripts/ui_detector
│   ├── detector.py          # → scripts/ui_detector
│   ├── input.py             # → scripts/platform_input
│   ├── template_match.py    # → scripts/template_match
│   └── vm_adapter.py        # VM monkey-patch
agentic/                     # Bundled Agentic Programming library
```
