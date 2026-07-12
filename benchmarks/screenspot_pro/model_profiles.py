"""Per-model GUI-grounding strategy registry for ScreenSpot-Pro.

Each model gets a profile instead of one harness being assumed to fit every
model. Confirmed by data in docs/COORDINATE_FORMAT_FINDINGS.md:

  - coord_format : which gui_harness.planning.coord_formats id this model's
                   native grounding was trained on. Wrong format costs 20+ pts.
  - pipeline      : "native_single_shot" (one call, no YOLO/OCR, no iterative
                   crop — for models that are already strong groundors) or
                   "harness" (this repo's iterative-zoom crop-and-refine
                   pipeline — for models that are weak at raw grounding but
                   benefit from scaffolding).
  - confirmed     : True if BOTH coord_format and pipeline were validated by a
                   paired native-vs-harness comparison (not just format
                   ablation). False = pipeline is provisional; only the
                   format ablation has been run so far.
  - hires         : pass vl_high_resolution_images=True on the Aliyun
                   endpoint (Qwen-family only; small, roughly-noise-floor
                   effect, ~+6pt single-shot).
  - use_hints     : inject OCR/icon-detector candidates as plain text into the
                   single-shot prompt. Free (zero extra calls) but NOT
                   universally positive — it is model+format-specific. Helps
                   GPT on its winning format (abs_pixel, +16pt). HURTS qwen on
                   ITS winning format (point2d_1000: no-hint 77% > hint 60%,
                   paired 9 flipped-wrong vs 1 saved — a real reversal, not
                   noise). The earlier "+26pt for qwen" was measured on the
                   OLD suboptimal abs/frac01 formats, where a weak baseline
                   makes any crutch look useful. Always re-test use_hints
                   AFTER locking in the winning coord_format, never before.

Before adding a new model: run the two cheap probes that fill this table —
  1. single-shot format ablation (~50 samples x 3-4 formats, one call each)
  2. native single-shot vs harness, same samples, paired
  3. use_hints on/off, AT the winning coord_format from step 1 — do not reuse
     a hint-benefit number measured on a different format
Do not assume a new model fits an existing profile.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    provider: str          # "openai-codex" (openprogram runtime) | "aliyun" (direct httpx)
    coord_format: str       # gui_harness.planning.coord_formats.FORMAT_IDS member
    pipeline: str           # "native_single_shot" | "harness"
    confirmed: bool         # native-vs-harness paired comparison done?
    hires: bool = False
    use_hints: bool = True
    note: str = ""


MODEL_PROFILES: dict[str, ModelProfile] = {
    "gpt-5.5": ModelProfile(
        provider="openai-codex",
        coord_format="abs_pixel",
        pipeline="harness",
        confirmed=True,
        hires=False,
        use_hints=True,
        note=(
            "harness 88.7% (verified clean, 299/300 iterative_zoom_crop_refine, but only "
            "300/1581 samples — configs/sspro_stack_zoom.yaml has NEVER been run at full "
            "1581 scale for GPT). "
            "native single-shot 78.3% is UNVERIFIED — that file's grounding_type=direct_pixel "
            "traces to an old active_loop candidate-pool fallback branch, not a clean bare "
            "single call; the exact old code path no longer has a matching version. The "
            "88.7%-vs-harness-helps direction still stands (format ablation below, on a "
            "verified clean single call, independently shows hints +16pt for GPT — a "
            "harness benefit doesn't need the 78.3% number to be true). But the precise "
            "+10.4pt harness delta needs a clean single-shot rerun on the same 300 samples "
            "to confirm. Format ablation (baseline50, verified clean): abs 62% > "
            "xy1000/point2d 56% > frac01 50%. "
            "IMPORTANT SEPARATE CAVEAT (easy to re-confuse, see "
            "docs/COORDINATE_FORMAT_FINDINGS.md §9.5): the commonly-cited '87.9%' full-1581 GPT "
            "number used configs/legacy_baseline.yaml (an OLDER, weaker config — fill scaling, "
            "no candidate_sort, 8 rounds) — NOT sspro_stack_zoom.yaml (this profile's config, "
            "also what M3/qwen's full-1581 harness runs used). '87.9% (same config) / 88.7%' "
            "was cited together in early session summaries as if directly comparable — they "
            "are NOT: different config AND different sample count (1581 vs 300). No GPT number "
            "exists yet for 'current config, full 1581 scale'. candidate_sort=relevance (the "
            "sspro_stack_zoom.yaml improvement over legacy_baseline) is the harness's only "
            "confirmed stable positive knob, so the true full-scale number is likely >=87.9%, "
            "possibly close to 88.7%, but this is inference, not measured. "
            "3-PROBE DIAGNOSTIC (baseline50, probe_gpt_hints_reversal.py + probe_gpt_thinking.py): "
            "Probe C (hints at native abs_pixel vs foreign frac01) = +8pt BOTH conditions "
            "(66%->74% native, 50%->58% foreign) — identical magnitude, NO sign reversal. NOTE: "
            "the native no-hint baseline here (66%, probe_gpt_hints_reversal.py) differs from "
            "the original ablation's no-hint baseline (58%, probe_ablation_gpt.py, same nominal "
            "baseline50 set) — same call mechanism (create_runtime+openai-codex), likely GPT's "
            "own run-to-run stochasticity (4/50 samples) rather than a methodology bug; the "
            "'with hint' endpoint (74%) matches exactly across both runs. Effect estimate is "
            "therefore +8 to +16pt depending on which no-hint run you anchor to — direction "
            "(positive, no reversal) is what matters for the diagnostic and is robust either way. Same "
            "clean 'general-reasoning' signature as M3. Probe A (thinking) now testable — earlier "
            "'reasoning_effort not passable via Runtime.exec()' conclusion was WRONG, corrected "
            "2026-07: the real knob is the Runtime instance attribute `rt.thinking_level` (set "
            "AFTER create_runtime(), BEFORE calling .exec() — NOT a constructor/exec kwarg, which "
            "is why searching for a kwarg found nothing). Values: off/minimal/low/medium/high/"
            "xhigh. run_sspro_native.py's _make_openprogram_call does not set this (stays at "
            "Runtime's default 'off'). See probe_gpt_thinking.py for the working pattern. "
            "RESULT (baseline50, abs_pixel): thinking=off 60% (30/50, 24.4s/call) vs "
            "thinking=high 62% (31/50, 45.4s/call) = +2pt, essentially flat/noise-level, "
            "~1.9x slower for no real gain. NOT negative like qwen's -19pt — doesn't show the "
            "specialized-head degradation signature. FINAL 3-PROBE VERDICT for GPT-5.5: "
            "A~flat(+2pt), B+8pt, C+8pt-no-reversal — clean general-reasoning profile, same "
            "shape as M3. All 4 models now have complete 3-probe data."
        ),
    ),
    "qwen3.7-plus": ModelProfile(
        provider="aliyun",
        coord_format="point2d_1000",
        pipeline="native_single_shot",
        confirmed=True,
        hires=True,
        use_hints=False,
        # thinking: 2x2(hints x thinking, 22 个难样本子集)显示 thinking=False 独立正向且和
        # hints 效应正交——无提示条件下 thinking关64% > thinking开45%;有提示条件下 thinking关
        # 32% > thinking开14%。两个变量互不解释对方,各自都成立。run_sspro_native.py 的
        # _make_aliyun_call 已固定 enable_thinking=False。呼应 Qwen 官方 79.0 就是 thinking-off
        # 测出来的。
        note=(
            "native 78% >> harness(abs pixel, iterative zoom) 70% on 120 paired samples, "
            "at 1/20th the call count. Format ablation: point2d_1000 79% > xy1000 69% > "
            "frac01 58% > abs 16%. Reproduces Qwen's self-reported 79.0. "
            "IMPORTANT: use_hints was re-tested AT this winning format (point2d_1000+hires, "
            "same 48 samples) and REVERSES — no-hint 77% > hint 60% (paired: 9 flipped "
            "wrong-by-hint vs 1 saved-by-hint, not noise). The earlier '+26/+6 hint benefit' "
            "was measured on the OLD suboptimal abs/frac01 formats — a weak baseline makes any "
            "crutch look useful; qwen's real native format doesn't need one, and the imperfect "
            "OCR/YOLO candidate list actively distracts a strong native grounder. use_hints is "
            "NOT a universal free win — it is model+format-specific and must be re-checked "
            "whenever the winning coord_format changes. FOLLOW-UP: tried fixing hint QUALITY "
            "(production candidate_sort='relevance' + top-12 instead of raw unsorted top-120) "
            "to see if the harness's real candidate-ranking logic (not a sloppy dump) could "
            "flip this — it narrowed the gap (60%->65%) but did NOT reverse it (still 77% "
            "no-hint > 65% relevance-hint, paired 7-flipped-wrong vs 1-saved). Conclusion: this "
            "is not a hint-quality artifact — qwen's native point2d_1000 grounding is simply "
            "more reliable than any external candidate evidence we've tried. See "
            "probe_qwen_hints_relevance.py."
        ),
    ),
    "kimi-k2.6": ModelProfile(
        provider="aliyun",
        coord_format="frac01",
        pipeline="native_single_shot",
        confirmed=False,  # format ablation done; native-vs-harness NOT yet run
        hires=False,
        use_hints=False,  # UNVERIFIED for kimi — conservative default, see note
        note=(
            "Format ablation only (48 samples): frac01 60% > xy1000 44% > point2d_1000 36% "
            "> abs 19%. Outputs frequently drift toward [0,1] fractions even when the prompt "
            "asks for [0,1000] integers or point_2d — that drift is itself the evidence for "
            "frac01 being kimi's native convention. pipeline=native_single_shot is PROVISIONAL "
            "(matches the qwen pattern) — no paired native-vs-harness run yet; kimi's own "
            "harness run was stopped early for resource reasons, not enough overlap with the "
            "baseline50 set for a clean comparison. use_hints=False is a CONSERVATIVE DEFAULT, "
            "not a measured result — all 4 kimi format-ablation conditions were run with no "
            "hints, so there is zero data on kimi's hint response. Given qwen's hint effect "
            "reversed once measured at its true winning format (see qwen3.7-plus note), do not "
            "assume hints help kimi either — test on/off at frac01 before flipping this. "
            "thinking: tested on/off (baseline50, frac01). REFINED after fixing 2 infra bugs "
            "(413 body-too-large from a compression-threshold miss, unrelated to thinking, now "
            "fixed for both conditions) and retrying the 6 remaining ReadTimeouts at a shorter "
            "150s cutoff (still ALL genuinely fail to complete, not a fluke): thinking=on 66% "
            "among completed calls (29/44) but 12% total-failure rate (6/50 never return an "
            "answer even at 150s); thinking=off 58% (29/50) with 0% failures. Accuracy-among-"
            "completed actually FAVORS thinking=on (+8pt) — opposite sign from qwen's clear "
            "-19pt degradation — but the 12% hard-failure rate exactly cancels this out under "
            "'unanswered counts as wrong' scoring (both land at 58%), and it's still ~11x "
            "slower (68.1s vs 6.2s/call). Net: thinking=off remains the right production choice "
            "(reliability + speed), but the underlying signal is 'tries to reason and sometimes "
            "succeeds better, at a real reliability cost' — NOT qwen's 'reasoning actively hurts "
            "a calibrated shortcut' signature. This nudges kimi's Probe-A classification from "
            "'flat/neutral' to 'mildly positive-but-unreliable', consistent with its overall "
            "'mixed/intermediate' 3-probe verdict rather than a clean specialized-head case. "
            "See fix_kimi_thinking_errors.py for the reliability investigation. "
            "run_sspro_native.py's shared "
            "_make_aliyun_call already hardcodes enable_thinking=False for all aliyun models, "
            "so kimi inherits this correctly with no code change needed. "
            "FULL-SCALE (2026-07, 1581/1581, frac01+no-hints+thinking=off): 56.6% (895 hits, "
            "38 errors) — matches the baseline50 probe (56%) closely, confirms this config is "
            "the real 'model-best-adapted single-shot' number for kimi, not just a small-sample "
            "estimate. pipeline vs harness still not paired-tested (see confirmed=False above). "
            "3-PROBE DIAGNOSTIC (specialized-head vs general-reasoning classification, see "
            "docs/COORDINATE_FORMAT_FINDINGS.md §5.6): Probe B (hints at native frac01, baseline50) "
            "= -23pt (60%->38%), MORE negative than qwen's -17pt — strong specialized-head "
            "signature. Probe C (same hints test at foreign/worst format abs_pixel) = only "
            "+3pt (21%->23%), essentially noise — does NOT show qwen's dramatic sign-reversal "
            "(-17 -> +26). Probe A (thinking on/off) was TIED (54% both ways), not clearly "
            "negative like qwen. CONCLUSION: kimi is a PARTIAL match — decisive on probe B, "
            "ambiguous on A and C — suggests a middle ground between qwen's clean specialized-"
            "head case and a general-reasoning model, not a clean binary classification. "
            "Probes: probe_kimi_hints_reversal.py."
        ),
    ),
    "MiniMax-M3": ModelProfile(
        provider="minimax-cn-coding-plan",
        coord_format="point2d_1000",
        pipeline="native_single_shot",
        confirmed=False,  # format ablation done (below); native-vs-harness paired run pending
        hires=False,
        use_hints=False,
        note=(
            "STANDARD baseline (abs_pixel), used deliberately as the 'no model-specific tuning' "
            "reference point for the cross-model matrix — coord_format here is NOT yet M3's "
            "confirmed winning format, do not treat as optimized. MiniMax Token Plan quota was "
            "exhausted earlier this session, confirmed restored 2026-07. Full 1581-sample "
            "harness run exists (47.4%, m3_zoom/, verified clean in the §9 audit). "
            "PRELIMINARY 1-sample spot-check (2026-07, NOT a real ablation, just a smoke-test "
            "red flag): abs_pixel raw reply '{\"x\":536,\"y\":701}' on a 3840x2160 image with "
            "GT center ~(1943,1602) — off by 1400+px, clearly wrong scale. Same single sample "
            "with frac01/xy1000/point2d_1000 all landed near the true target (xy1000 closest, "
            "x off by only 27px) — strongly suggests M3, like qwen, is NOT trained on raw full-"
            "resolution absolute pixels and needs a normalized convention. THIS IS NOT YET A "
            "REAL FINDING (n=1) — a proper 50-sample 4-format ablation (same SOP as gpt/qwen/"
            "kimi) is required before updating coord_format/confirmed here. Standard abs_pixel "
            "is still being run at full 1581 scale anyway (as the deliberate 'unoptimized' "
            "reference point), even though we expect it to score low — don't skip a planned "
            "measurement just because the outcome is predictable, that's exactly the mistake "
            "this whole investigation started by catching (see qwen §1). "
            "FULL-SCALE RESULT (2026-07, 1581/1581, abs_pixel+no-hints): 0.7% (11 hits, 43 "
            "errors) — confirms the n=1 spot-check red flag was real, not noise; abs_pixel is "
            "essentially non-functional for M3 (near-zero, not just 'suboptimal'). "
            "FORMAT ABLATION (2026-07, baseline50, no-hints, via probe_m3_format.py, same "
            "Runtime.exec()/openprogram-runtime call path as the full run): abs_pixel 0% << "
            "frac01 22% < xy1000 24% < point2d_1000 27% (best). Same ranking shape as qwen "
            "(point2d_1000 wins) but a much lower ceiling (27% vs qwen's 79%) — M3's raw "
            "grounding is intrinsically weaker than qwen's even in its best format, this isn't "
            "just a format-mismatch story like qwen's was. coord_format updated to "
            "point2d_1000 above. NEXT STEP: full-1581 run at point2d_1000 (the real "
            "'model-best-adapted single-shot' number), then pair vs the existing 47.4% harness "
            "run to decide if M3 needs scaffolding (unlike qwen, plausible given the low "
            "single-shot ceiling — harness may well beat native here, opposite of qwen's case). "
            "FULL-SCALE RESULT (2026-07, 1581/1581, point2d_1000+no-hints): 26.1% (412 hits, "
            "43 errors) — matches the 27% baseline50 ablation closely. vs harness 47.4%: "
            "harness wins by +21pt, OPPOSITE of qwen (where native beat harness by +8pt). "
            "CONCLUSION: M3 is a model that NEEDS scaffolding — unlike qwen's clean 'specialized "
            "head, skip the harness' case, M3's raw single-shot grounding is weak enough that "
            "iterative-zoom scaffolding still adds real value. Native-vs-harness comparison "
            "here is on the same benchmark but not sample-paired (both are full-1581 runs, "
            "different configs/eras) — good enough for the direction, a proper paired subset "
            "check would tighten the exact delta. "
            "3-PROBE DIAGNOSTIC (baseline50, probe_m3_hints_reversal.py): Probe B (hints at "
            "native point2d_1000) = +10pt (24%->35%). Probe C (same hints test at foreign/worst "
            "abs_pixel) = +20pt (0%->20%). BOTH POSITIVE, NO SIGN REVERSAL — the opposite "
            "signature from qwen's specialized-head case (qwen: -17pt native -> +26pt foreign, "
            "a reversal). M3 accepts evidence productively regardless of format — this is the "
            "clean 'general-reasoning' signature, matching its low single-shot ceiling (27%) "
            "and its strong dependence on harness scaffolding (47.4% vs 26%). Probe A untestable "
            "(no thinking toggle exposed via Runtime.exec/minimax-cn-coding-plan). CONCLUSION: "
            "M3 is a general-reasoning-type model — our scaffolding method has real room to "
            "improve it, unlike qwen where the method correctly has nothing to add."
        ),
    ),
    "claude-opus-4-7": ModelProfile(
        provider="claude-code",
        coord_format="abs_pixel",
        pipeline="native_single_shot",
        confirmed=False,  # format ablation done (below); native-vs-harness paired run pending
        hires=False,
        use_hints=False,
        note=(
            "FORMAT ABLATION (2026-07, baseline50, no-hints, probe_claude_format.py, "
            "Runtime.exec via claude-code provider = Claude Code subscription OAuth, thinking "
            "default off): abs_pixel 30% ~ frac01 30% > xy1000 17% > point2d_1000 13%. "
            "Claude is PIXEL-NATIVE like GPT but with POOR format compliance: under "
            "point2d_1000/xy1000 it frequently answers the SAME raw pixel coords as under "
            "abs_pixel (e.g. [1304,1017] verbatim in both conditions) — normalized formats' "
            "low scores are non-compliance, not worse grounding. "
            "RESCALE HYPOTHESIS REFUTED (probe_claude_rescale.py, 47 scored): guessed Claude "
            "answers in the Anthropic-API-downscaled image space (long edge 1568px / ~1.15Mpx "
            "cap) — scoring predictions as downscaled-space coords gives 0/47 vs 34% as "
            "original-space coords. Claude correctly compensates the server-side downscale and "
            "answers in the prompt-declared original pixel space. "
            "THE REAL BOTTLENECK IS RESOLUTION, split is dramatic: images with mild API "
            "downscale (scale>=0.45, ~2.5K) 14/21=67% vs heavy downscale (scale<0.45, 4K/"
            "ultrawide) 2/26=8%. Single-shot ~30% is 'physically cannot see', not weak "
            "reasoning — on legible images Claude approaches GPT's level. This predicts the "
            "LARGEST harness gain of any model (June-2026 old-pipeline iterative harness: "
            "79.0% on 338 valid / 79.5% stratified-78 ≈ +45-50pt over single-shot; zoom crops "
            "stay under the API downscale threshold so the model sees native resolution). "
            "INFRA: Anthropic hard-rejects images >5MB (HTTP 400) — 3 baseline50 PNGs "
            "(8.6-16MB macos screenshots) fail deterministically; run_sspro_native.py's "
            "claude-code path re-encodes >4.5MB PNGs to JPEG before sending. "
            "FULL-SCALE RESULT v1 (raw direct API, 2026-07-12, 1581/1581): 31.6% — "
            "SUPERSEDED, archived at runs/sspro_native/claude-opus-4-7_rawapi/. That number "
            "was a CHANNEL ARTIFACT: raw base64-to-API feeding lets the server silently "
            "downscale 4K to ~1568 while the prompt declares original dims. "
            "FULL-SCALE RESULT v2 (CC image protocol, 2026-07-12, 1581/1581, 0 errors): "
            "**57.4%** (907 hits). The feeding protocol alone is worth +25.8pt; the old "
            "blind bucket (scale<0.45, 804 samples) went 2.2% -> 47.5%, OS 0.5% -> 50.0%; "
            "CAD lowest at 32.6%. THE PROTOCOL (mapped from Claude Code's Read tool, see "
            "FINDINGS §9.9): downscale >2000px long edge to 2000 + annotate '[Image: "
            "original WxH, displayed at wxh. Multiply coordinates by k to map to original "
            "image.]' — implemented in gui_harness/openprogram_compat.py (claude-code "
            "provider chokepoint) and in the locator's _display_scale_line + "
            "_normalize_bbox_to_display (Claude answers original-space coords on downscaled "
            "displays; forcing displayed-space answers scores 14%). Claude Code's own CLI "
            "channel scores 68% on baseline50 (system prompt + tool-result presentation add "
            "~20pt a bare API call can't replicate; provider 'claude-cli' shells out to "
            "claude.exe when full-native is needed). HARNESS: new pipeline + CC protocol "
            "(sspro_stack_zoom_claude2000.yaml: max_side 2000 + min_scale 0.3 — beware "
            "iterative_min_scale:1.0 silently vetoes max_side shrink — + crop_check off, "
            "quote \"off\" in YAML!) scores 7/10 on the hard android_studio slice @30s/"
            "sample vs 3/10 @550s raw and 6/10 @211s via the official CLI channel — "
            "replication matches the real thing at 7x speed. June-2026 79.0% fully "
            "explained: Meridian->Claude Code SDK channel WAS the CC protocol."
        ),
    ),
}


def get_profile(model: str) -> ModelProfile:
    try:
        return MODEL_PROFILES[model]
    except KeyError as exc:
        raise KeyError(
            f"No ModelProfile for {model!r}. Run the format-ablation + "
            f"native-vs-harness probes before adding one — do not guess."
        ) from exc
