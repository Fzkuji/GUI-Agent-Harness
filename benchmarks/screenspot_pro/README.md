# ScreenSpot-Pro Benchmark

ScreenSpot-Pro is a GUI element grounding benchmark covering 1,581 professional
software samples across 5 subsets and 23 applications. Scoring: predicted point
must fall inside the ground-truth box (no IoU).

Two evaluation pipelines are compared throughout:
- **Harness** — this repo's iterative-zoom crop-and-refine pipeline (multi-call).
- **Native single-shot** — one API call, each model in *its own* trained
  coordinate format (no zoom, no OCR/detector hints).

---

## Results Summary

| Model | Harness (iterative-zoom) | Native single-shot | Δ (harness − single) | Grounding type |
|-------|--------------------------|--------------------|----------------------|----------------|
| **GPT-5.5** | **87.9%** (1581, legacy) · 88.7% (300, zoom) | ~62%* (fmt ablation, abs, 50) | positive (evidence +16pt) | general-reasoning |
| **MiniMax-M3** | **47.4%** (1581) | 26.1% (1581, point2d) | **+21.3pt** | general-reasoning |
| **kimi-k2.6** | — (not run) | **56.6%** (1581, frac01) | n/a | intermediate |
| **qwen3.7-plus** | 62.9% (partial ~979) | **78–79%** (120 paired, point2d) | **−8pt** (single-shot wins) | specialized shortcut |
| Claude Opus 4.7 | 79.0%* (338, quota-limited) | — | — | — |
| Claude Opus 4.8 | stratified-78 done | — | — | — |

\* Caveats: GPT-5.5 87.9% used `configs/legacy_baseline.yaml` (full 1581); 88.7%
used `configs/sspro_stack_zoom.yaml` (300-sample subset) — different config AND
scale, not directly comparable (see `docs/COORDINATE_FORMAT_FINDINGS.md` §9.5).
GPT clean single-shot is unverified; 62% is the format-ablation best (50 samples).
Claude 4.7 full run hit quota exhaustion (1,243 infra failures, not model errors).

---

## Key finding: grounding comes in two kinds

Not every model benefits from the harness — and it is **structural, not noise**.
A cheap 3-probe diagnostic (single call each) separates two capability types:

- **General-reasoning grounding** — the model reasons about the screen; supplying
  spatial evidence + iterative refinement *amplifies* it. Our method helps a lot.
- **Specialized fine-tuned grounding** — the model was SFT'd into a coordinate
  regression head locked to one output format; already near its trained ceiling,
  does not benefit from evidence/refinement, can even be **hurt** by them.

| Model | A · reasoning | B · evidence | C · sign-consistency | Format-robustness (std) | Verdict |
|-------|---------------|--------------|----------------------|-------------------------|---------|
| GPT-5.5 | +2pt | +8pt | +8pt (no reversal) | **4.2pt** (best) | general-reasoning |
| MiniMax-M3 | (no toggle) | +10pt | +20pt (no reversal) | 10.7pt | general-reasoning |
| kimi-k2.6 | +8pt* | −23pt | +3pt (≈noise) | 14.8pt | intermediate |
| qwen3.7-plus | −19pt | −17pt | **+26pt (reversal)** | **24.0pt** (worst) | specialized shortcut |

**Takeaway:** the gain from a training-free harness is *not* a function of model
size — it is a function of whether the model's grounding is reasoning-based or
already-specialized. Full analysis: `docs/GROUNDING_CAPABILITY_REPORT.html`
(clean report) and `docs/COORDINATE_FORMAT_FINDINGS.md` (research log).

---

## Per-model results

Each model has a *native* coordinate format; feeding the wrong format costs
20–60 pts. See `model_profiles.py` for the machine-readable registry.

### GPT-5.5  ·  native format: absolute pixels
- Harness 87.9% (full 1581, legacy) / 88.7% (300, current zoom config).
- Format ablation (baseline50): abs 62% > xy1000/point2d 56% > frac01 50%.
- Evidence hints +16pt (58%→74%); 3-probe all positive, no reversal → general-reasoning.
- Results: `results/gpt_5_5/`, `results/easy100/gpt-5_5/`.

### MiniMax-M3  ·  native format: point_2d + [0,1000]
- Harness **47.4%** (full 1581) vs native single-shot **26.1%** (full 1581) →
  **harness +21.3pt**, the clearest demonstration our method adds real value.
- Format ablation: point2d 27% > xy1000 24% > frac01 22% > abs 0%.
- 3-probe evidence/robustness both positive → general-reasoning.
- Results: `results/minimax_m3/` (harness), `runs/sspro_native/MiniMax-M3/` (single-shot).

### kimi-k2.6  ·  native format: {x,y} + [0,1] fractions
- Native single-shot **56.6%** (full 1581, frac01). Harness not paired-tested.
- Format ablation: frac01 60% > xy1000 44% > point2d 36% > abs 19%.
- Evidence −23pt (native), thinking ≈flat but 12% timeouts → intermediate case.
- Results: `runs/sspro_native/kimi-k2.6/`.

### qwen3.7-plus  ·  native format: point_2d + [0,1000] (+hires)
- Native single-shot **78–79%** (reproduces vendor 79.0) *beats* harness 62.9% by
  ~+8pt on 120 paired samples — a specialized grounder the harness cannot lift.
- Format ablation: point2d 79% > xy1000 69% > frac01 58% > abs 16%.
- Evidence/thinking both negative, format-shift reverses evidence sign → specialized.
- Results: `runs/sspro_native/qwen3.7-plus/`, `runs/sspro_aliyun/qwen3.7-plus/` (harness).

### Claude Opus 4.7 / 4.8
- 4.7 full run 79.0%* (338/1581, quota-limited, 1,243 WF); stratified-78 79.5%.
- 4.8 stratified-78 done.
- Results: `results/claude_opus_4_7/`, `results/claude_opus_4_8/`.

---

## GPT-5.5 by subset (harness, full 1581)

| Subset | Samples | Correct | Accuracy |
|--------|---------|---------|----------|
| Office | 230 | 221 | 96.1% |
| Development | 289 | 259 | 89.6% |
| Operating Systems | 196 | 177 | 90.3% |
| CAD | 306 | 259 | 84.6% |
| Creative | 306 | 259 | 84.6% |
| Scientific | 254 | 215 | 84.6% |
| **Total** | **1581** | **1390** | **87.9%** |

### GPT-5.5 top/bottom apps

| App | Subset | Samples | Accuracy |
|-----|--------|---------|----------|
| EViews | Scientific | 50 | 98.0% |
| Word | Office | 84 | 97.6% |
| VMware | Development | 41 | 97.6% |
| Excel | Office | 64 | 96.9% |
| macOS | OS | 65 | 95.4% |
| ... | ... | ... | ... |
| Origin | Scientific | 62 | 58.1% |
| AutoCAD | CAD | 34 | 70.6% |
| FL Studio | Creative | 57 | 75.4% |
| Quartus | CAD | 45 | 75.6% |

---

## Method & code

**Per-model SOP** (see `model_profiles.py` header for the full protocol):
1. Format ablation (~50 samples × 4 formats, single call each).
2. Native single-shot vs harness, paired.
3. `use_hints` on/off at the winning format.
4. 3-probe diagnostic to classify the model.

**Directory layout** (scripts grouped by function; core modules kept at root
because they are imported/subprocess-called by the others)
- root: `model_profiles.py`, `run_screenspot_pro.py`, `refusal_judge.py`,
  `prepare_gui_grounding_datasets.py` — shared modules.
- `runners/` — per-model / per-benchmark runners (`run_sspro_native.py`,
  `run_sspro_aliyun.py`, `run_sspro_codex.py`, `run_sspro_singleshot.py`,
  `run_sspro_slice_arm.py`, `run_osworld_g.py`, `run_osworld_g_refusal.py`).
- `data_prep/` — dataset builders (`prepare_*`, `make_*_slice`).
- `reporting/` — aggregation & reports (`report_*`, `sync_full_final`,
  `finalize_full_results`, `count_completed_range`, `update_network_retry_queue`).
- `launchers/` — detached full-run starters (`start_*`).
- `figures/` — paper-figure generators.
- `configs/` — harness pipeline configs (`legacy_baseline.yaml`, `sspro_stack_zoom.yaml`).
- `docs/` — reports and research logs (below).

**Per-model SOP entry points**: `model_profiles.py` (registry) +
`runners/run_sspro_native.py` (native single-shot) + `run_screenspot_pro.py`
(harness) + `gui_harness/planning/coord_formats.py` (format source of truth).
The one-off `probe_*.py` diagnostics behind the findings live in git history
(see `docs/COORDINATE_FORMAT_FINDINGS.md` §10).

**Docs** (in `docs/`)
- `GROUNDING_CAPABILITY_REPORT.html` — clean results report (two capability types).
- `COORDINATE_FORMAT_FINDINGS.md` / `.html` — full research log + data audit.
- `TRAINING_PLAN.md` — local Qwen3-VL SFT + agentic-RL plan.
- `BEST_CONFIG.md`, `UI_VISION_OPTIMIZATION_LOG.md` — config/experiment logs.

**Result directories** (`results/` tracked; `runs/` local, gitignored)
- `results/<model>/` — tracked summaries (gpt_5_5, claude_opus_4_7/4_8, minimax_m3).
- `runs/sspro_native/<model>/` — this-session single-shot per-sample records.
- `runs/sspro_aliyun/<model>/`, `runs/sspro_stack/` — harness per-sample records.
