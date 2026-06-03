# Benchmark Runs

Small run summaries live here so the repository records what was measured
without committing local datasets, screenshots, JSONL outputs, or work caches.

## Results By Model

### `openai-codex` / `gpt-5.5`

- ScreenSpot-Pro canonical final: 1390/1581, 87.92%
- ScreenSpot v2 full base run: 1219/1272, 95.83%
- ScreenSpot v2 final after workflow retry overlay: 1231/1272, 96.78%
- MMBench-GUI L2 paused partial: 1953/2109 completed rows, 92.60%

### `claude-code` / `claude-opus-4`

- ScreenSpot-Pro 78-sample comparison run: 62/78, 79.49%
- ScreenSpot-Pro full run: active, seeded from the same 78-sample run

### `claude-code` / `claude-opus-4-8`

- ScreenSpot-Pro 78-sample comparison run: 61/78, 78.21%

## ScreenSpot-Pro Full

- Model: `openai-codex` / `gpt-5.5`
- Canonical final run directory: `runs/screenspot_pro/iter_zoom_recrop_full_final_20260602`
- Final result: 1581/1581 completed, 1390 correct / 191 wrong / 0 wrong_format
- Accuracy: 87.92%
- Ignored infrastructure rows during merge: 81
- Reporter: `benchmarks/screenspot_pro/report_full_final.py`
- Merger: `benchmarks/screenspot_pro/sync_full_final.py`

## ScreenSpot v2

- Model: `openai-codex` / `gpt-5.5`
- Official manifests: desktop, mobile, and web. Standard reporting also splits
  each manifest by element type: text vs icon/widget.
- Base run directory: `runs/screenspot_pro/screenspot_v2_full_20260602_1157`
- Base result: 1272/1272 completed, 1219 correct / 39 wrong / 14 wrong_format
- Base accuracy: 95.83%
- Base split accuracy: desktop 313/334 (93.71%), mobile 485/501 (96.81%),
  web 421/437 (96.34%)
- Base platform/type accuracy:
  - desktop-icon 130/140 (92.86%)
  - desktop-text 183/194 (94.33%)
  - mobile-icon 200/211 (94.79%)
  - mobile-text 285/290 (98.28%)
  - web-icon 194/203 (95.57%)
  - web-text 227/234 (97.01%)
- Workflow retry directory: `runs/screenspot_pro/screenspot_v2_wf_retry_20260602_1931`
- Retry completed rows: 13/14, 12 correct / 1 wrong, with
  `screenspot_v2_mobile_0265` left pending and counted as wrong in the final
  merged summary
- Final merged result after retry overlay: 1231/1272 correct, 41 wrong
- Final merged accuracy: 96.78%
- Final split accuracy: desktop 325/334 (97.31%), mobile 485/501 (96.81%),
  web 421/437 (96.34%)
- Final platform/type accuracy:
  - desktop-icon 135/140 (96.43%)
  - desktop-text 190/194 (97.94%)
  - mobile-icon 200/211 (94.79%)
  - mobile-text 285/290 (98.28%)
  - web-icon 194/203 (95.57%)
  - web-text 227/234 (97.01%)
- Reporter: `benchmarks/screenspot_pro/report_screenspot_versions.py`

## Claude ScreenSpot-Pro 78-Sample Comparison

- Claude 4.7-labeled run: `runs/screenspot_pro/claude_opus47_stratified78_20260602_2145`
- Claude 4.8 run: `runs/screenspot_pro/claude_opus48_stratified78_20260603_0215`
- 4.7-labeled model: `claude-code` / `claude-opus-4`
- 4.8 model: `claude-code` / `claude-opus-4-8`
- 4.7-labeled result: 62/78, 79.49%
- 4.8 result: 61/78, 78.21%
- Per-sample matrix: 56 both correct, 11 both wrong, 5 improved on 4.8, 6 regressed on 4.8
- Caveat: the 4.7-labeled run used `--model claude-opus-4`; the 4.8 run used
  `--model claude-opus-4-8`.

## Active Claude Full ScreenSpot-Pro

- Run directory: `runs/screenspot_pro/claude_opus47_full_screenspot_pro_20260603_1300`
- Screen: `claude_opus47_full_screenspot_pro`
- Provider/model: `claude-code` / `claude-opus-4`
- Plan: full ScreenSpot-Pro, 1581 samples, 4 shards
- Seeded rows: 78 from `claude_opus47_stratified78_20260602_2145`

## MMBench-GUI L2 GPT-5.5 Pause Point

- Model: `openai-codex` / `gpt-5.5`
- Run directory: `runs/gui_grounding/gui_grounding_mmbench_gui_l2_full_20260602_2040`
- Stop marker: `STOPPED_20260603_1256.md`
- Status at stop: 2109/3594 completed, 1953 correct / 156 wrong / 0 wrong_format
- Accuracy on completed: 92.60%
- Remaining: 1485
- Split progress: Android 711/711, iOS 644/644, Linux 387/387, macOS 367/691,
  Web 0/618, Windows 0/543
- Resume with the same run directory and `--skip-existing`; do not start a new
  GPT run unless explicitly requested.
