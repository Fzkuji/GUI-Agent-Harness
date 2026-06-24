# Qwen2.5-VL-3B GUI-AIMA-Like Data Runs

This directory stores GUI Agent Harness results using
`Qwen/Qwen2.5-VL-3B-Instruct` on GUI-AIMA-style public grounding datasets.

Each dataset has its own subfolder so results from GUIAct, AndroidControl,
Wave-UI, UGround, and GTA1 do not get mixed.

## Dataset Summary

| Folder | Dataset | Annotation file | Status | Completed | Correct | Wrong | Wrong format | Accuracy |
|---|---|---|---|---:|---:|---:|---:|---:|
| `GUIAct/` | GUIAct | `guiact_bbox.json` | completed to 1450 samples | 1450 | 691 | 439 | 320 | 47.7% |
| `AndroidControl/` | AndroidControl | `androidcontrol_bbox.json` | not run yet | 0 | 0 | 0 | 0 | N/A |
| `Wave-UI/` | Wave-UI | `wave_ui_bbox.json` | not run yet | 0 | 0 | 0 | 0 | N/A |
| `UGround/` | UGround single-round | `uground_bbox_single_60k.json` | not run yet | 0 | 0 | 0 | 0 | N/A |
| `GTA1/` | GTA1 no-web | `gta_data_wo_web_output_60k.json` | not run yet | 0 | 0 | 0 | 0 | N/A |

## Per-Dataset Files

Each dataset folder should use the same file names:

- `results.jsonl`: one JSON object per evaluated sample.
- `errors.jsonl`: failed samples, if any.
- `full_summary.json`: aggregate counts and accuracy.
- `full_report.md`: human-readable report.
- `README.md`: dataset-specific note.

Large intermediate crops, screenshots, and per-step traces should remain under:

`/home/zichuanfu2/GUI-Attention-Harness/runs/qwen25vl3b_gui_aima_like/work/`
