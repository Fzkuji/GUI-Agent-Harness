# GPT-5.5 — UI-Vision Full Results

Model: GPT-5.5 (openai-codex)
Samples: 5479/5479 ✅
Pipeline: single-shot Phase-3 (`find_target_in_known`). CORRECTION: this header
previously claimed "iterative_zoom 8 rounds", but the per-row data contradicts
it — all 5479 rows carry `listed_entry`/`direct_pixel` grounding types and
component-memory phase timings, with zero iterative-zoom traces. The app_name
routing gate into the locator never fired in this run.

## Final
| Correct | Wrong | WF | Accuracy |
|---------|-------|----|----------|
| 3761 | 1718 | 0 | **68.64%** |

## By Split
| Split | Samples | Correct | Wrong | Accuracy |
|-------|---------|---------|-------|----------|
| ui_vision_basic | 1772 | 1295 | 477 | 73.1% |
| ui_vision_functional | 1772 | 1188 | 584 | 67.0% |
| ui_vision_spatial | 1935 | 1278 | 657 | 66.0% |
