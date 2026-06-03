# Benchmark Runs

Small run summaries live here so the repository records what was measured
without committing local datasets, screenshots, JSONL outputs, or work caches.

## ScreenSpot-Pro Full

- Canonical final run directory: `runs/screenspot_pro/iter_zoom_recrop_full_final_20260602`
- Final result: 1581/1581 completed, 1390 correct / 191 wrong / 0 wrong_format
- Accuracy: 87.92%
- Ignored infrastructure rows during merge: 81
- Reporter: `benchmarks/screenspot_pro/report_full_final.py`
- Merger: `benchmarks/screenspot_pro/sync_full_final.py`

## Claude ScreenSpot-Pro 78-Sample Comparison

- Claude 4.7-labeled run: `runs/screenspot_pro/claude_opus47_stratified78_20260602_2145`
- Claude 4.8 run: `runs/screenspot_pro/claude_opus48_stratified78_20260603_0215`
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

- Run directory: `runs/gui_grounding/gui_grounding_mmbench_gui_l2_full_20260602_2040`
- Stop marker: `STOPPED_20260603_1256.md`
- Status at stop: 2109/3594 completed, 1953 correct / 156 wrong / 0 wrong_format
- Accuracy on completed: 92.60%
- Remaining: 1485
- Split progress: Android 711/711, iOS 644/644, Linux 387/387, macOS 367/691,
  Web 0/618, Windows 0/543
- Resume with the same run directory and `--skip-existing`; do not start a new
  GPT run unless explicitly requested.

