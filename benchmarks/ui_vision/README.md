# UI-Vision — GUI Grounding Benchmark

UI-Vision is a large-scale GUI element grounding benchmark with 5,479 samples across three splits: basic, functional, and spatial reasoning.

- Model: **GPT-5.5** (openai-codex)
- Samples: **5,479 / 5,479** ✅
- Pipeline: iterative_zoom (8 rounds), legacy (main_baseline.yaml)
- Accuracy: **68.64%** (3,761 correct / 1,718 wrong / 0 WF)

---

## Results

| Model | Progress | Correct | Wrong | WF | Accuracy | Status |
|-------|----------|---------|-------|-----|----------|--------|
| **GPT-5.5** | 5479/5479 | 3761 | 1718 | 0 | **68.64%** | ✅ Done |

## By Split

| Split | Samples | Correct | Accuracy |
|-------|---------|---------|----------|
| Basic | 1772 | 1295 | **73.1%** |
| Functional | 1772 | 1188 | **67.0%** |
| Spatial | 1935 | 1278 | **66.0%** |
| **Total** | **5479** | **3761** | **68.64%** |

> Spatial reasoning questions are significantly harder: the model must identify "the button to the right of X" or "the element above Y" — requiring spatial relationship understanding beyond simple element recognition.

## Files
- `../screenspot_pro/results/ui_vision_gpt_5_5/full_report.md` — summary report
- `../screenspot_pro/results/ui_vision_gpt_5_5/full_summary.json` — aggregated stats by split
- `../screenspot_pro/results/ui_vision_gpt_5_5/results.jsonl` — 5,479 per-sample records
