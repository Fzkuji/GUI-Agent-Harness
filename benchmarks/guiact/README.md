# GUIAct Benchmark

GUIAct is a large-scale GUI grounding dataset used here to evaluate **GUI-Lens**
(training-free, model-agnostic iterative-zoom harness) across open-weight VLMs.
Scoring: predicted point must fall inside the ground-truth box (no IoU).

All models below run the **same harness**, swapping only the frozen VLM backbone
— no fine-tuning. This is the paper's main "GUI-Lens across VLMs" result.

## Results Summary (harness, GUIAct)

| Model | Samples | Correct | Wrong | Wrong-format | Accuracy |
|-------|--------:|--------:|------:|-------------:|---------:|
| Qwen2.5-VL-3B | 2184 | 1024 | 679 | 481 | 46.9% |
| Qwen2.5-VL-7B | 500 | 294 | 134 | 72 | 58.8% |
| Qwen3-VL-4B | 500 | 340 | 141 | 19 | **68.0%** |
| Qwen3-VL-8B | 500 | 341 | 140 | 19 | **68.2%** |

Note: sample counts differ (3B ran to 2184, others to 500) — re-run 3B to 500 for
a matched comparison. Wrong-format rate drops sharply from Qwen2.5 → Qwen3 (72/481
→ 19), i.e. newer VLMs emit valid coordinates far more reliably.

**Takeaway:** training-free GUI-Lens lifts open VLMs to be competitive with trained
baselines; a stronger VLM helps, but size alone is not proportional (Qwen3-VL-4B ≈
Qwen3-VL-8B). Whether the harness helps a given VLM tracks its grounding *type*
(reasoning-based vs. already-specialized), not its size — see the 3-probe
diagnostic in `../screenspot_pro/docs/GROUNDING_CAPABILITY_REPORT.html`.

## Layout

```
guiact/results/<model>/
  results.jsonl      # per-sample records
  errors.jsonl       # failed samples
  full_summary.json  # aggregate counts
  full_report.md     # human-readable report
  README.md          # dataset-specific note
```

Other public grounding datasets (AndroidControl, Wave-UI, UGround, GTA1) were
scaffolded but not yet run; when run, each gets its own `benchmarks/<dataset>/`.
Harness code lives in `../screenspot_pro/` (shared runner `run_screenspot_pro.py`,
model registry `model_profiles.py`).
