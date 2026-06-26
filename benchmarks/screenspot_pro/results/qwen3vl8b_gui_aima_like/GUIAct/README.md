# GUIAct Results

Dataset: GUIAct

Annotation file: `guiact_bbox.json`

Model: `Qwen/Qwen3-VL-8B-Instruct`

Pipeline: GUI Agent Harness iterative grounding.

## Current Result

| Completed | Correct | Wrong | Wrong format | Accuracy |
|---:|---:|---:|---:|---:|
| 500 | 341 | 140 | 19 | 68.2% |

The current run contains unique GUIAct sample ids only. The runner reads
`results.jsonl` before each batch and skips existing sample ids.

## Files

- `results.jsonl`: per-sample predictions and correctness labels.
- `errors.jsonl`: failed samples, if any.
- `full_summary.json`: aggregate statistics.
- `full_report.md`: short human-readable report.
