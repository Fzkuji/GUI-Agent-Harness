# Benchmarks Overview — GUI Agent Harness

| Benchmark | Status | Best Model | Best Acc | Samples |
|-----------|--------|------------|----------|---------|
| [ScreenSpot Pro](screenspot_pro/) | ✅ Done | GPT-5.5 | **87.9%** | 1581/1581 |
| [ScreenSpot v2](screenspot_v2/) | ✅ Done | GPT-5.5 | **96.78%** | 1272/1272 |
| [ScreenSpot v1](screenspot_v1/) | ❌ Not run | — | — | 0/~1272 |
| [MMBench-GUI-L2](mmbench_gui_l2/) | ✅ Done | GPT-5.5 | **91.52%** | 3594/3594 |
| [OSWorld](osworld/) | Partial | Claude 4.6 | 93.5% (Chrome) | 172+/369 |

## Directory Structure
```
benchmarks/
  screenspot_pro/       # Professional software grounding (1581 samples)
    results/
      claude_opus_4_7/  # Claude Opus 4.7 results
      claude_opus_4_8/  # Claude Opus 4.8 results
      gpt_5_5/          # GPT-5.5 full results
    configs/
      main_baseline.yaml    # Legacy pipeline config
      known_good.yaml       # New pipeline config
    README.md
  screenspot_v2/
    results/gpt_5_5/
    README.md
  screenspot_v1/
    README.md
  mmbench_gui_l2/
    results/gpt_5_5/
    README.md
  osworld/
    docs/                # Task documentation
    scripts/             # Python/Shell scripts
    config/              # Task configs
    results/             # Model results
    README.md
  README.md (this file)
```

## Raw Data
All raw JSONL results, error logs, and run scripts live under `runs/`:
- `runs/screenspot_pro/` — ScreenSpot series runs
- `runs/gui_grounding/` — MMBench-GUI-L2 and other grounding runs
