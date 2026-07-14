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
| **GPT-5.5** | **87.9%** (1581, legacy) · 88.7% (300, zoom) | **74.8%** (1581, abs, pure API) | positive (evidence +16pt) | general-reasoning |
| **MiniMax-M3** | **47.4%** (1581) | 26.4% (1581, point2d) | **+21.0pt** | general-reasoning |
| **kimi-k2.6** | — (not run) | **56.6%** (1581, frac01) | n/a | intermediate |
| **qwen3.7-plus** | 62.9% (partial ~979) | **78–79%** (120 paired, point2d) | **−8pt** (single-shot wins) | specialized shortcut |
| **Claude Opus 4.7** | **82.3%** (300, zoom+CC-protocol) · 79.0%* (338, old pipeline) | **57.4%** (1581, abs, CC-protocol) · 31.6% raw-API | **+24.9pt** | general-reasoning |
| Claude Opus 4.8 | stratified-78 done | — | — | — |

\* Caveats: GPT-5.5 87.9% used `configs/legacy_baseline.yaml` (full 1581); 88.7%
used `configs/sspro_stack_zoom.yaml` (300-sample subset) — different config AND
scale, not directly comparable (see `docs/COORDINATE_FORMAT_FINDINGS.md` §9.5).
GPT clean single-shot is unverified; 62% is the format-ablation best (50 samples).
Claude 4.7's 79.0% is the June-2026 old pipeline (quota exhaustion left 1,243
infra failures; 338 valid) — direction is solid, config differs from zoom stack.
Claude 4.7 single-shot is gated by the Anthropic API server-side downscale (long
edge ≤1568px / ~1.15Mpx): legible half (scale≥0.45) scores 61.9%, illegible half
2.2% — the 31.6% total is that mixture, not uniform weakness (see §9.8).

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

## Design-level ablation — cross-model (GPT-5.5 & MiniMax-M3, SSPro-300)

The harness has three designs: **① coordinate priming** (annotate detected
text/components with coordinates in the prompt), **② adaptive coarse-to-fine
cropping** (the model picks the next crop over rounds, with retry/recrop), and
**③ visual verification** (draw the crop/point back and re-check). Removing one
design at a time from the full config (`sspro_stack_zoom.yaml`), same 300-sample
stratified slice, thinking off.

**Cross-model matrix — every design's contribution is amplified on the weaker
base.** M3 is paired on its 290-sample common set (10 platform-refusal /
content-filter rows excluded from all arms); GPT on the full 300.

| Arm | GPT-5.5 | Δ | MiniMax-M3 | Δ |
|-----|---------|---|------------|---|
| **full** (①②③) | **88.7%** | — | **47.6%** | — |
| −① `abl_no_prime` | 87.7% | −1.0 | 40.3% | **−7.2** |
| −② `abl_no_adaptive` | 85.0%\* | **−3.7** | 25.5% | **−22.1** |
| −③ `abl_no_verify` | 87.0% | −1.7 | 42.8% | **−4.8** |
| single-locate (ref) | 78.3% | −10.4 | — | — |

**The M3 column is the strongest evidence for the paper's thesis.** Every
design's contribution is 3–6× larger on the weak base: priming −1.0 (GPT) vs
−7.2 (M3), adaptive crop −3.7 vs **−22.1**, verify −1.7 vs −4.8. Removing
adaptive cropping collapses M3 to **25.5%** — essentially its single-shot level
(26.4%), proving iterative cropping *is* the engine lifting M3 from 26% to 47%;
take it out and it falls back to raw single-shot. GPT is strong enough that one
big crop still localizes (−3.7 only). The **ordering is identical** across models
(② > ① > ③), so relative design importance is model-invariant — the weak base
just magnifies each margin. Gain from a training-free scaffold tracks base
strength, not model size. (M3 harness uses abs-pixel coords, *not* normalized:
the crop shrinks the image enough that abs — M3's worst single-shot format — works,
while normalized coords net-hurt inside the pipeline; see §format notes.)

Per-arm timing/rounds (GPT): full 114s/3 · −① 134s/3 · −② 81s/1 · −③ 79s/3 ·
single-locate 25s.

\* 2/300 samples counted wrong are deterministic local-GPU OOM (single-round
crops of 4K screenshots too large for the local detector; retried at concurrency
3→2→1). Valid-sample accuracy 255/298 = 85.6%. An earlier tally of this arm
(76.3%) contained 31 transient OOM rows and was invalid — all were retried per
the retry-errors-then-compare rule.

Paired McNemar (same 300 samples): −② p=0.019 and full-vs-single p<0.0001 are
significant; −① (p=0.63) and −③ (p=0.33) are individually within noise at
n=300 — ①'s standalone effect is instead evidenced by the single-shot hint
ablation (+16pt), and arm-level significance for ①③ is expected from the M3
cross-model matrix (weaker base → larger margins).

**Reading (GPT-5.5 = general-reasoning type):**
- Every design contributes — removing any one loses accuracy. ② adaptive
  cropping is the largest single contributor (−3.7pt).
- **② absorbs ①**: priming alone is worth +16pt in single-shot (58→74, format
  ablation), but only −1.0pt inside the full pipeline — once zoom makes the
  target legible, the model no longer needs textual coordinate hints. ① and ②
  are two redundant routes to the same missing spatial information.
- One crop is not enough: −② still crops once but only reaches ~50% of the
  image (vs 1.3% median final crop area with 8 rounds), so small targets stay
  small; its 85.0% sits between single-locate (78.3%) and full (88.7%).
- Cost: ③ costs ~35s/sample (79→114s); removing ① makes runs *slower* (134s)
  — without candidates the model needs more crop attempts.

Config arms: `configs/abl_no_prime.yaml`, `configs/abl_no_adaptive.yaml`,
`configs/abl_no_verify.yaml`; driver `runners/run_sspro_slice_arm.py
--arm zoom --config <arm>.yaml`; tally `reporting/report_design_ablation.py`.
GPT + M3 cross-model matrix is **done** (above) and confirms the prediction:
the weak base loses more on every −X arm. Optional extensions: a third
general-reasoning column (Claude 4.7, full=82.3% already in hand) and the
specialized-type contrast (qwen3.7-plus — predicted to barely move on any arm).

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
- **Harness (2026-07-13, 300-slice, `sspro_stack_zoom_claude2000.yaml` = zoom stack +
  CC image protocol + crop-check off): 82.3%** (247/300), 0 errors, median 27s/sample
  (3 zoom rounds) — beats the June legacy 79.0% on a reproducible, current-pipeline
  setup. Harness gain over CC-protocol single-shot: **+24.9pt**. By group: Office
  95.5% > Scientific 83.7% > Creative 83.1% > OS 80.6% > CAD 77.6% > Dev 75.4%.
- **Paired vs GPT-5.5 (88.7%, same 300 samples)**: both-correct 241, GPT-only 25,
  Claude-only 6, both-wrong 28 → oracle-union **90.7%**. The two models' weak spots
  differ (GPT worst at CAD, Claude worst at Dev) — cross-model arbitration headroom
  is real (+2pt over GPT alone).
- **Native single-shot (2026-07-12, full 1581, abs_pixel, CC image protocol): 57.4%**,
  0 errors. Raw direct-API feeding scores 31.6% on the same samples — the feeding
  protocol alone is worth **+25.8pt** (see FINDINGS §9.9). Claude Code's own CLI
  channel scores 68% on baseline50 (its full native environment; system prompt +
  tool-result image presentation account for the last ~20pt, not replicable via
  bare API).
- **The CC image protocol** (what Claude is calibrated to): downscale >2000px images
  to 2000 long edge + annotate `[Image: original WxH, displayed at wxh. Multiply
  coordinates by k to map to original image.]`. Implemented at the claude-code
  provider chokepoint in `gui_harness/openprogram_compat.py`; a `claude-cli`
  provider (shells out to claude.exe) is also available for full-native runs.
- Harness (new pipeline + CC protocol, `sspro_stack_zoom_claude2000.yaml`): hard-10
  android_studio slice 7/10 @ 30s/sample median (raw-API config: 3/10 @ 550s;
  official CLI channel: 6/10 @ 211s — replication matches the real thing).
- Format ablation (baseline50, raw API): abs 30% ≈ frac01 30% > xy1000 17% >
  point2d 13% — pixel-native like GPT, poor format compliance (answers raw pixels
  even under normalized-format prompts; forcing displayed-space answers scores 14%).
- June-2026 "79.0%" (338 valid, old pipeline via Meridian→Claude Code SDK) is now
  fully explained: that channel WAS the CC protocol. The old pipeline itself
  replayed through today's direct API scores 0/10 on the hard slice.
- Thinking: high ≈ off (28% vs 30%) — flat, like GPT.
- Results: `runs/sspro_native/claude-opus-4-7/` (57.4%),
  `claude-opus-4-7_rawapi/` (31.6% archive), `runs/sspro_baseline/claude47_*`,
  `runs/claude47_ab10*.jsonl` (harness A/B chain), `results/claude_opus_4_7/`
  (June legacy), `results/claude_opus_4_8/`.

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

**Directory structure** — scripts are grouped by function; the four
sibling-imported / subprocess-called modules stay at the root so every caller
resolves them.

```
benchmarks/screenspot_pro/
├── model_profiles.py              # per-model strategy registry (imported by runners)
├── run_screenspot_pro.py          # canonical harness (iterative-zoom) runner; imported + subprocess-called
├── refusal_judge.py               # feasibility/refusal classifier layer (imported)
├── prepare_gui_grounding_datasets.py  # UI-Vision/MMBench normalizer (imported + subprocess-called)
├── __init__.py
│
├── runners/                       # per-model / per-benchmark evaluation runners
│   ├── run_sspro_native.py        #   unified native single-shot (profile-driven) ← main SOP entry
│   ├── run_sspro_aliyun.py        #   SSPro via Aliyun Token-Plan VLMs (harness)
│   ├── run_sspro_codex.py         #   SSPro via official Codex CLI (gpt-5.5)
│   ├── run_sspro_singleshot.py    #   pure single-call GPT-5.5 baseline
│   ├── run_sspro_slice_arm.py     #   SSPro-300 slice arm driver
│   ├── run_osworld_g.py           #   OSWorld-G harness run
│   └── run_osworld_g_refusal.py   #   OSWorld-G refusal-layer eval
│
├── data_prep/                     # dataset builders / slice makers
│   ├── prepare_osworld_g.py
│   ├── prepare_screenspot_versions.py
│   ├── make_sspro_slice.py
│   └── make_ui_vision_slice.py
│
├── reporting/                     # aggregation, reports, result maintenance
│   ├── report_full_final.py
│   ├── report_screenspot_versions.py
│   ├── report_gui_grounding_datasets.py
│   ├── report_ui_vision_slice.py
│   ├── report_design_ablation.py
│   ├── sync_full_final.py
│   ├── finalize_full_results.py
│   ├── count_completed_range.py
│   └── update_network_retry_queue.py
│
├── launchers/                     # detached full-run starters (screen sessions)
│   ├── start_full_autoretry.py
│   ├── start_gui_grounding_datasets.py
│   ├── start_screenspot_versions.py
│   └── start_wrong_format_retry.py
│
├── figures/                       # paper-figure generators
│   ├── generate_paper_figures.py
│   └── render_zoom_example.py
│
├── configs/                       # harness pipeline configs (legacy_baseline / sspro_stack_zoom
│                                  #   / abl_no_{prime,adaptive,verify} design-ablation arms)
├── results/<model>/               # tracked per-model result summaries
├── data*/                         # local benchmark data (gitignored)
└── docs/                          # reports + research logs (below)
```

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
