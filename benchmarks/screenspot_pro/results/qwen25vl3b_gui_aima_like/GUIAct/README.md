# GUIAct Results

Dataset: GUIAct

Annotation file: `guiact_bbox.json`

Model: `Qwen/Qwen2.5-VL-3B-Instruct`

Pipeline: GUI Agent Harness iterative grounding.

## Current Result

| Completed | Correct | Wrong | Wrong format | Accuracy |
|---:|---:|---:|---:|---:|
| 1000 | 474 | 305 | 221 | 47.4% |

The current run covers `GUIAct_000000` through `GUIAct_000999` without duplicate
sample ids.

## Files

- `results.jsonl`: per-sample predictions and correctness labels.
- `errors.jsonl`: failed samples, if any.
- `full_summary.json`: aggregate statistics.
- `full_report.md`: short human-readable report.
