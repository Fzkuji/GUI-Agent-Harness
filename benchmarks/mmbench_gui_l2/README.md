# MMBench-GUI-L2 — GUI Element Grounding

Multi-platform GUI element grounding benchmark covering 6 platforms (Android/iOS/Linux/macOS/Web/Windows).

- Model: **GPT-5.5** (openai-codex)
- Samples: **3,594 / 3,594** (100%) ✅
- Pipeline: iterative_zoom (8 rounds), legacy (main_baseline.yaml)
- Accuracy: **91.52%** (3,271 correct / 303 wrong / 20 WF)

---

## Results

| Model | Progress | Correct | Wrong | WF | Accuracy | Status |
|-------|----------|---------|-------|-----|----------|--------|
| **GPT-5.5** | 3594/3594 | 3271 | 303 | 20 | **91.52%** | ✅ Done |

## By Difficulty

| Level | Samples | Correct | Accuracy |
|-------|---------|---------|----------|
| Basic | 1787 | 1691 | **94.89%** |
| Advanced | 1807 | 1580 | **88.17%** |
| **Total** | **3594** | **3271** | **91.52%** |

## By Platform

| Platform | Samples | Correct | Accuracy |
|----------|---------|---------|----------|
| Android | 711 | 682 | 95.9% |
| iOS | 644 | 612 | 95.0% |
| Web | 618 | 569 | 92.5% |
| macOS | 691 | 610 | 89.3% |
| Windows | 543 | 474 | 88.8% |
| Linux | 387 | 324 | 83.7% |
| **Total** | **3594** | **3271** | **91.52%** |

> All 20 WF are `NoVerifiedTarget` — genuine hard cases the model cannot locate even after iterative zoom with retries. Not network errors.

## Files
- `results/gpt_5_5/full_report.md` — summary report
- `results/gpt_5_5/full_summary.json` — aggregated stats by platform
- `results/gpt_5_5/results.jsonl` — 3,594 per-sample records

## Run Info
- Run directory: `runs/gui_grounding/gui_grounding_mmbench_gui_l2_full_20260602_2040/`
