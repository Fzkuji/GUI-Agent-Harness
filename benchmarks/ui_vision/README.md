# UI-Vision — GUI Grounding Benchmark

UI-Vision is a large-scale GUI element grounding benchmark with 5,479 samples across three splits: basic, functional, and spatial reasoning.

- Model: **GPT-5.5** (openai-codex)
- Samples: **5,479 / 5,479** ✅
- Pipeline: **single-shot Phase-3** (`find_target_in_known` — one LLM call over
  the component list + full screenshot). NOT the iterative-zoom locator,
  despite what this header used to claim: the recorded rows carry only
  `listed_entry`/`direct_pixel` grounding types and component-memory phase
  timings, with zero zoom traces — the `app_name` routing gate never fired in
  that run. Treat 68.64% as the weak-path baseline, not the locator's score.
- Accuracy: **68.64%** (3,761 correct / 1,718 wrong / 0 WF)

---

## Optimized pipeline (2026-06-11, 300-sample stratified slice)

The single-shot 68.64% above is the weak-path baseline. Routing UI-Vision
through the full stack — single-shot(+element convention) ∥ iterative-zoom
locator (`configs/ui_vision_gpt_zoom.yaml`) → disagreement judge → zoomed
identity verification — on a 300-row stratified slice (same rows compared
against the old run):

| Split | Old (single-shot) | Optimized | Δ |
|-------|------------------|-----------|---|
| Basic | 76.3% | **84.5%** | +8.2 |
| Functional | 62.9% | **71.1%** | +8.2 |
| Spatial | 67.9% | **79.2%** | +11.3 |
| **Total** | **69.0%** | **78.3%** | **+9.3** |

A 13-agent visual audit of all 65 remaining misses found 8 annotation errors
(in 5 the model's click was demonstrably the correct element), 7 un-scoreable
rows (garbled instructions / self-referential boxes), and 10 functionally
equivalent clicks. Corrected tiers: **80.0%** (fixing the 5 mis-drawn gt
boxes), **82.8%** (excluding defective rows), 86.2% (human-eval style).
Full experiment history: `../screenspot_pro/UI_VISION_OPTIMIZATION_LOG.md`.
SSPro regression guard: easy100 × legacy config = 98/100 (no regression).

## Results (legacy single-shot full run)

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
