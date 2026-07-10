# Training — distilling GUI-Lens into model weights

Goal: SFT a Qwen3-VL so the iterative-zoom behaviour (crop → crop → final →
click) lives **in the weights**, with no detector / OCR / candidate evidence at
inference. The harness's role shifts from inference-time scaffold to
**training-data format designer**: trajectories are synthesized directly from
GUIAct ground-truth boxes — no teacher LLM runs, no manual clicking.

## Why the previous attempt (first_crop_1k) underperformed

Three fixes, in order of suspected impact:

1. **Coordinate convention.** The old data supervised *displayed-crop pixel*
   bboxes. Qwen3-VL's native grounding convention is **normalized [0,1000]**
   integers (Qwen2.5-VL was pixel-based; Qwen3-VL switched back). Training
   against the model's own convention instead of fighting it is worth double-
   digit points on single-shot (see `_NORM_COORD_*` notes in
   `gui_harness/planning/screenspot_locator.py`). Everything here is [0,1000]
   of the displayed image — which is also crop-invariant, so the same
   convention works at every zoom level.
2. **Only round-1 was taught.** No stage-2 crop, no `final` decision, no click
   point, no `recrop` recovery — the model never saw the rest of the loop.
   The new data covers the full trajectory (5 record types).
3. **`image_max_pixels: 262144`** downscaled full screenshots to ~512px before
   the ViT — small targets became sub-patch. Now 1048576.

## Layout

```
training/
├── configs/qwen3vl8b_guiact_zoom_lora.yaml   # LLaMA-Factory LoRA SFT config
├── jobs/
│   ├── setup_llamafactory_qwen3vl.sbatch     # one-time env setup (unchanged)
│   ├── train_qwen3vl8b_guiact_zoom.sbatch    # prepare data + train
│   └── eval_qwen3vl8b_guiact_zoom.sbatch     # serve + pure-model zoom eval
├── tools/
│   ├── prompts.py                    # training prompts ≡ harness inference prompts
│   ├── prepare_guiact_zoom_sft.py    # GT box → full zoom trajectory (the core)
│   ├── eval_zoom_traj.py             # model-only zoom loop eval (no harness)
│   ├── serve_qwen_vl_api.py          # OpenAI-compatible local server (base)
│   └── serve_qwen_vl_lora_api.py     # same, with a LoRA adapter
├── data/       (generated, gitignored)
├── outputs/    (checkpoints + eval results, gitignored)
├── envs/       (conda envs, gitignored)
└── LLaMA-Factory/  (cloned framework, gitignored)
```

`prompts.py` imports the rule blocks from `gui_harness` when importable (byte-
identical to inference) and falls back to embedded verbatim copies otherwise —
`dataset_summary.json` records which source was used (`prompt_source`).

## Data design (prepare_guiact_zoom_sft.py)

Per GUIAct row (image + instruction + GT box), synthesized with a seeded RNG:

| record_type | input image | supervised answer |
|---|---|---|
| `crop_r0` | full screenshot | `{"action":"crop","bbox":<stage-1 region>}` |
| `crop_r1` | rendered stage-1 crop | `{"action":"crop","bbox":<stage-2 group>}` |
| `crop_final` (~50%) | rendered stage-2 crop | `{"action":"final","bbox":<tight target>}` |
| `click` | upscaled stage-2 crop | `{"action":"click",...,"point_2d":[x,y]}` |
| `recrop_neg` (~15%) | decoy crop w/o target | `{"action":"recrop",...}` |

Key properties:
- **Jittered geometry** — crop size/aspect/placement randomized so the target
  is *not* always centered (otherwise "answer = crop center" is learnable).
- **Single-turn per round** — matches the harness (`context_mode: single`).
- **Stage areas** follow the harness's staged-crop policy (stage 1 ≈ 18–35% of
  the screen, stage 2 ≈ 22–45% of stage 1).
- Held-out `val_rows.json` (default 2%) is written for eval; never trained on.

## Workflow (cluster)

```bash
# 0. once: env
sbatch jobs/setup_llamafactory_qwen3vl.sbatch

# 1. prepare data + LoRA SFT (prepare runs inside the job)
sbatch jobs/train_qwen3vl8b_guiact_zoom.sbatch

# 2. eval — pure-model zoom loop on held-out rows
sbatch jobs/eval_qwen3vl8b_guiact_zoom.sbatch                      # LoRA, zoom
EVAL_MODE=single sbatch jobs/eval_qwen3vl8b_guiact_zoom.sbatch     # LoRA, single-shot
LORA_DIR="" sbatch jobs/eval_qwen3vl8b_guiact_zoom.sbatch          # base, zoom
LORA_DIR="" EVAL_MODE=single sbatch jobs/eval_qwen3vl8b_guiact_zoom.sbatch
```

## The comparison that matters

| config | what it shows |
|---|---|
| base, single-shot | floor |
| base + GUI-Lens harness (existing `benchmarks/guiact` runs) | training-free scaffold lift |
| **SFT, pure-model zoom loop** | did the scaffold distill into weights? |
| SFT, single-shot | how much survives without even the loop |

Success bar: SFT pure-model zoom ≥ base+harness (68.2% for Qwen3-VL-8B on the
existing GUIAct-500). Everything above the base single-shot floor is distilled
scaffold; anything ≥ the harness row means the method no longer needs its
inference-time prompts. Next steps beyond SFT (candidate-evidence mixing,
agentic RL, the three-way ablation) are in
`../benchmarks/screenspot_pro/docs/TRAINING_PLAN.md`.
