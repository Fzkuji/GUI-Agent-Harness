# ScreenSpot-Pro Benchmark Utilities

This directory contains local runners and reporting helpers for GUI grounding
benchmarks that share the `run_screenspot_pro.py` evaluator.

## Tracked Code

- `run_screenspot_pro.py` runs one or more ScreenSpot-style annotation files.
- `sync_full_final.py` merges a full ScreenSpot-Pro run, recovery runs, and
  autoretry runs into one canonical result directory.
- `report_full_final.py` prints a compact ScreenSpot-Pro final/progress report.
- `start_full_autoretry.py` starts a detached retry pass for pending
  ScreenSpot-Pro samples.
- `prepare_screenspot_versions.py`, `start_screenspot_versions.py`, and
  `report_screenspot_versions.py` normalize, run, and report ScreenSpot v1/v2.
- `prepare_gui_grounding_datasets.py`, `start_gui_grounding_datasets.py`, and
  `report_gui_grounding_datasets.py` normalize, run, and report UI-Vision and
  MMBench-GUI L2.

## Local Data

The following are intentionally ignored by git:

- `benchmarks/screenspot_pro/data*/`
- `runs/`
- JSONL outputs and error-event files

Use `GUI_HARNESS_PYTHON=/path/to/python` when a detached starter should use a
specific virtual environment. Otherwise the current Python interpreter is used.

## Resume Notes

All detached starters use shard JSONL outputs and `--skip-existing`, so a run can
be resumed from the same run directory without duplicating completed sample IDs.

