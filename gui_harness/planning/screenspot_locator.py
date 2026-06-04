"""ScreenSpot-Pro locator.

ScreenSpot-Pro is a static screenshot benchmark, not a live application. It
does not benefit from app memory, workflow learning, or unknown-component
labeling. Keep its control flow explicit behind one entry point:

1. optional iterative zoom / recrop locator
2. crop-first locator with optional candidate and active fallbacks
3. return None if no verified target is found

Environment variables in this module are tuning knobs for benchmark ablations.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from gui_harness.error_monitor import reraise_if_fatal
from gui_harness.planning import active_localization as active
from gui_harness.utils import parse_json


# ═══════════════════════════════════════════════════════════════════════════
# Static instruction prefixes (prompt-cache stable prefixes)
#
# Each LLM call in this module repeats a large block of fixed rules / policy /
# JSON-format text that is byte-identical across every call, round, and sample.
# These blocks are pulled out as module-level constants and sent as the FIRST
# content block of each request, marked with cache_control, so the provider
# caches them once and serves later calls from cache_read. The per-call dynamic
# text (task, crop box, round, history, candidates) follows as a second block,
# and the image last. Reordering rules-before-dynamic is intentional: the cache
# prefix must be stable, and general constraints read fine before the task.
# ═══════════════════════════════════════════════════════════════════════════

# ``{"type": "ephemeral"}`` marks an explicit prompt-cache breakpoint. The
# patched OpenProgram Anthropic provider passes this through and skips its own
# default last-block breakpoint when a caller marks one (see
# providers/anthropic/anthropic.py). OpenAI-style providers ignore the marker
# and cache stable prefixes automatically — either way, putting the fixed text
# first is what lets the cache hit.
_CACHE_BREAKPOINT = {"type": "ephemeral"}


def _cacheable_prefix_block(text: str) -> dict:
    """Build a leading text block marked as a prompt-cache breakpoint."""
    return {"type": "text", "text": text, "cache_control": _CACHE_BREAKPOINT}


_CROP_DECISION_RULES_INTRO = """Your job in this stage is NOT to click. Choose the next smaller crop that still
contains the requested clickable target and enough surrounding context to keep
orientation. The intended behavior is iterative zoom-in: shrink the search
area substantially each round, then a later stage will click on an upscaled
final crop."""

_CROP_DECISION_RULES_BODY = """Rules:
- Return bbox coordinates in the DISPLAYED CROP image coordinate system.
- Use the OCR/component candidate list as explicit grounding evidence. Candidate
  labels, centers, and boxes should guide which window/section/control group to
  keep. If a target-related candidate is present, the next crop should include
  it or include the larger unresolved region containing it.
- When multiple candidate clusters could satisfy the instruction, crop to a
  region that preserves the competing clusters until later rounds or the commit
  gate can disambiguate them.
- ScreenSpot-Pro labels the clickable UI control, not an abstract concept or a
  decorative label. Keep the region around the control that would actually be
  clicked to complete the instruction.
- If the instruction names an application/window, ignore matching desktop
  icons, other windows, document content, or web pages outside that app unless
  the instruction explicitly points there.
- For modify/change/adjust instructions, prefer the editable control itself
  (slider track/thumb, text input, dropdown item, checkbox, swatch) over the
  nearby label or category icon.
- For turn on/off/open/close instructions, prefer the direct toggle, close X,
  or command item for the named target. If several plausible controls exist,
  keep enough surrounding context to compare them instead of cropping to the
  first large related widget.
- For toolbar/menu commands with many similar icons, keep the whole local
  toolbar/menu group until the requested icon or row is unambiguous.
- If the target names a file, tab, embedded panel, or nested window, preserve
  enough surrounding controls to decide which layer the instruction refers to.
- Do not crop to passive status text such as "On", "Enabled", a title-bar
  status, or a menu label for on/off tasks. The next crop must contain a
  clickable toggle/button/switch.
- Maintain target identity across rounds. If an earlier round identified a
  concrete actionable control, the next crop should stay on that same control,
  not jump to a different plausible control with a similar label. Only switch
  targets if the earlier identification is clearly inconsistent with the
  instruction and screenshot.
- Prefer one high-recall crop over many tiny guesses. Do not crop so tightly
  that the target loses its label, icon context, or neighboring disambiguators.
- This crop is pending until a separate commit gate accepts it. If there is
  any unresolved ambiguity, return a larger, more conservative crop.
- Follow the staged crop guidance. The first committed crop must be a real
  crop from the full image, but it should be a window/region crop, not an
  immediate final-control crop.
- If the target is already clear enough and further cropping would risk cutting
  off context, use action="final".
- If the target is not visible in this crop, use action="recrop" to back out
  to a wider crop and try again. Do not give up; ScreenSpot-Pro targets are
  assumed to exist somewhere in the original screenshot.
- Do not return a final click point in this stage.

Reply with ONLY JSON:
{"action": "crop|final|recrop", "bbox": [x1, y1, x2, y2], "target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}"""

# Full rules block (intro + body) for the cache-prefix layout. Byte-identical to
# the legacy inline text; legacy reuses INTRO and BODY separately so the
# candidate list can sit between them exactly as origin/main did.
_CROP_DECISION_RULES = _CROP_DECISION_RULES_INTRO + "\n\n" + _CROP_DECISION_RULES_BODY


_COMMIT_GATE_RULES_BODY = """Accept the proposed crop only if all of these are true:
- The requested clickable target is still inside the magenta rectangle.
- The component/OCR evidence inside the magenta rectangle is consistent with
  the requested target, or the rectangle is a broad staged region that contains
  the target's unresolved candidate cluster.
- The component/OCR evidence outside the rectangle does not include another
  plausible target candidate that should remain visible at this stage.
- The crop keeps enough nearby label/icon/window context to identify the same
  target in the next round.
- The crop has not discarded another plausible target for the same instruction
  that is still unresolved.
- The proposal is not just a visually similar control in a different panel,
  window, toolbar, or application context.
- The proposal follows the staged crop guidance for this round; early rounds
  should select broad screen/window or app-section regions rather than jumping
  straight to a tiny final control.

Reject when uncertain. A rejected crop will be retried from the current wider
crop rather than clicked."""

_COMMIT_GATE_JSON = """Reply with ONLY JSON:
{"action": "accept|reject", "target_inside": true, "context_sufficient": true, "discarded_plausible_targets": false, "confidence": 0.0, "reasoning": "..."}"""

# Cache-prefix layout uses the full rules block (body + JSON). Byte-identical to
# the legacy text; legacy keeps the JSON after the proposal-rationale fields,
# exactly where origin/main put it.
_COMMIT_GATE_RULES = _COMMIT_GATE_RULES_BODY + "\n\n" + _COMMIT_GATE_JSON


_FINAL_CLICK_RULES = """Choose the exact center of the requested clickable target. Use the upscaled
image for precision. Candidate boxes are hints only: if a candidate covers a
combined toolbar group, a label next to an icon, or the wrong sub-control,
return explicit x/y for the true target instead of using candidate_id.

Click policy:
- Click the actionable control, not just the label, icon category, or visual
  explanation of the setting.
- For sliders, click the slider track/thumb/value area associated with the
  requested setting, not the setting's label/icon above it.
- For adjacent status counters or toolbar clusters, do not click the center of
  the whole cluster unless the instruction clearly asks for the whole cluster;
  choose the specific counter/icon/menu item named by the instruction.
- For close-file/tab instructions, click the small close affordance on the tab
  or named file, not the file icon/content or a different window.
- Do not click passive status text like "On" or "Enabled" for turn on/off
  tasks. Choose the actual toggle/button/switch.
- If two controls both seem plausible, prefer the one in the active/current
  task panel or named application context.
- If this crop does not contain a trustworthy clickable target, return
  action="recrop" so the caller can retry from a wider crop. Do not invent a
  coordinate in an unrelated region.

Reply with ONLY JSON:
{"action": "click|recrop", "candidate_id": "z0 or empty", "x": 0, "y": 0, "target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}"""


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes"}


def _env_choice(name: str, default: str, choices: set[str]) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.lower().strip()
    return value if value in choices else default


def _runtime_exec(runtime, config: "ScreenSpotLocatorConfig", **kwargs):
    timeout_s = config.runtime_timeout_s
    if timeout_s > 0:
        kwargs.setdefault("timeout_s", timeout_s)
    return runtime.exec(**kwargs)


@dataclass(frozen=True)
class ScreenSpotLocatorConfig:
    locator_mode: str = "crop_first"
    region_limit: int = 4
    active_rounds: int = 2
    active_top_k: int = 80
    snap_px: int = 80
    require_direct_snap: bool = True
    candidate_first: bool = False
    active_fallback: bool = True
    crop_verify_mode: str = "strict"
    crop_verify_fallback_after: int = 0
    pre_click_verify_fallback_after: int = 0
    direct_crop_width: int = 360
    direct_crop_height: int = 240
    refine_crop_width: int = 360
    refine_crop_height: int = 260
    iterative_rounds: int = 5
    iterative_max_side: int = 0          # 0 = no shrink cap (large crops keep full resolution)
    iterative_max_scale: int = 5
    iterative_min_short_side: int = 512
    iterative_min_scale: float = 1.0     # scale floor; 1.0 = never shrink, 0.1 = allow shrink
    iterative_final_max_side: int = 0    # 0 = no shrink cap
    iterative_final_max_scale: int = 8
    iterative_final_min_short_side: int = 640
    iterative_final_min_scale: float = 1.0
    iterative_scale_mode: str = "preserve"  # "preserve"=only enlarge small crops; "fill"=blow up to max_side (origin/main); "target_pixels"=scale each crop to ~a fixed pixel count
    iterative_target_pixels: int = 0        # scale_mode=target_pixels: target pixel count for per-round crops (0=off). e.g. 1500000 ~= 1.5MP
    iterative_final_target_pixels: int = 0  # same for the final-click crop (can be larger for precision)
    iterative_prompt_layout: str = "cache"  # "cache"=rules hoisted to a cacheable prefix; "legacy"=rules inline after dynamic fields, byte-matching origin/main
    reasoning_first: bool = False           # crop-decision JSON: put reasoning+target BEFORE the bbox so the model localizes/justifies in text first, then emits coordinates (only affects cache layout)
    candidate_limit: int = 60               # max OCR/detector candidates shown per crop-decision prompt
    candidate_sort: str = "none"            # "none"=detector order; "relevance"=rank by match to target then confidence; "confidence"
    candidate_dedup_iou: float = 0.0        # >0 drops candidates overlapping a kept one above this IoU (removes OCR-vs-button / near-dup boxes); 0=off
    iterative_max_area_pct: int = 0      # 0 = no per-round area cap (model decides zoom amount)
    iterative_padding_pct: int = 8
    iterative_min_width: int = 240
    iterative_min_height: int = 80
    iterative_final_candidates: int = 80
    enable_final_candidate_detect: bool = True
    enable_final_verify: bool = False
    enable_final_recheck: bool = False
    enable_legacy_pipeline: bool = False
    enable_crop_check: bool = True
    crop_check_mode: str = "every"        # "every"=check each round; "last_only"=only the final round; "off"=never (same as enable_crop_check False)
    crop_check_reject_mode: str = "widen" # on reject: "widen"=back out to a wider box; "restart_full"=reset to the full image and re-crop from scratch
    enable_crop_retry: bool = True
    crop_retry_limit: int = 3
    enable_final_recrop: bool = True
    final_recrop_limit: int = 0
    enable_staged_crop: bool = True
    iterative_stage1_min_area_pct: int = 20
    iterative_stage2_min_area_pct: int = 8
    context_mode: str = "single"
    accumulate_images: bool = False
    runtime_timeout_s: int = 180

    @classmethod
    def from_env(cls) -> "ScreenSpotLocatorConfig":
        return cls(
            locator_mode=_env_choice(
                "GUI_HARNESS_SCREENSPOT_LOCATOR_MODE",
                "crop_first",
                {"crop_first", "iterative_zoom"},
            ),
            region_limit=_env_int("GUI_HARNESS_SCREENSPOT_REGION_LIMIT", 4),
            active_rounds=_env_int("GUI_HARNESS_SCREENSPOT_ACTIVE_ROUNDS", 2),
            active_top_k=_env_int("GUI_HARNESS_SCREENSPOT_ACTIVE_TOPK", 80),
            snap_px=_env_int("GUI_HARNESS_SCREENSPOT_SNAP_PX", 80),
            require_direct_snap=_env_bool("GUI_HARNESS_SCREENSPOT_REQUIRE_DIRECT_SNAP", True),
            candidate_first=_env_bool("GUI_HARNESS_SCREENSPOT_CANDIDATE_FIRST", False),
            active_fallback=_env_bool("GUI_HARNESS_SCREENSPOT_ACTIVE_FALLBACK", True),
            crop_verify_mode=_env_choice(
                "GUI_HARNESS_SCREENSPOT_CROP_VERIFY_MODE",
                "strict",
                {"strict", "soft", "off"},
            ),
            crop_verify_fallback_after=_env_int("GUI_HARNESS_SCREENSPOT_CROP_VERIFY_FALLBACK_AFTER", 0, minimum=0),
            pre_click_verify_fallback_after=_env_int(
                "GUI_HARNESS_SCREENSPOT_PRE_CLICK_VERIFY_FALLBACK_AFTER",
                0,
                minimum=0,
            ),
            direct_crop_width=_env_int("GUI_HARNESS_SCREENSPOT_DIRECT_CROP_W", 360),
            direct_crop_height=_env_int("GUI_HARNESS_SCREENSPOT_DIRECT_CROP_H", 240),
            refine_crop_width=_env_int("GUI_HARNESS_SCREENSPOT_REFINE_CROP_W", 360),
            refine_crop_height=_env_int("GUI_HARNESS_SCREENSPOT_REFINE_CROP_H", 260),
            iterative_rounds=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_ROUNDS", 5),
            iterative_max_side=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_MAX_SIDE", 0, minimum=0),
            iterative_max_scale=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_MAX_SCALE", 5),
            iterative_min_short_side=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_MIN_SHORT_SIDE", 512),
            iterative_min_scale=_env_float("GUI_HARNESS_SCREENSPOT_ITERATIVE_MIN_SCALE", 1.0),
            iterative_final_max_side=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_MAX_SIDE", 0, minimum=0),
            iterative_final_max_scale=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_MAX_SCALE", 8),
            iterative_final_min_short_side=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_MIN_SHORT_SIDE", 640),
            iterative_final_min_scale=_env_float("GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_MIN_SCALE", 1.0),
            iterative_scale_mode=_env_choice(
                "GUI_HARNESS_SCREENSPOT_ITERATIVE_SCALE_MODE",
                "preserve",
                {"preserve", "fill", "target_pixels"},
            ),
            iterative_target_pixels=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_TARGET_PIXELS", 0, minimum=0),
            iterative_final_target_pixels=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_TARGET_PIXELS", 0, minimum=0),
            iterative_prompt_layout=_env_choice(
                "GUI_HARNESS_SCREENSPOT_ITERATIVE_PROMPT_LAYOUT",
                "cache",
                {"cache", "legacy"},
            ),
            reasoning_first=_env_bool("GUI_HARNESS_SCREENSPOT_REASONING_FIRST", False),
            candidate_limit=_env_int("GUI_HARNESS_SCREENSPOT_CANDIDATE_LIMIT", 60),
            candidate_sort=_env_choice(
                "GUI_HARNESS_SCREENSPOT_CANDIDATE_SORT",
                "none",
                {"none", "relevance", "confidence"},
            ),
            candidate_dedup_iou=_env_float("GUI_HARNESS_SCREENSPOT_CANDIDATE_DEDUP_IOU", 0.0),
            iterative_max_area_pct=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_MAX_AREA_PCT", 0, minimum=0),
            iterative_padding_pct=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_PADDING_PCT", 8, minimum=0),
            iterative_min_width=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_MIN_W", 240),
            iterative_min_height=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_MIN_H", 80),
            iterative_final_candidates=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_FINAL_CANDIDATES", 80),
            enable_final_candidate_detect=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_FINAL_CANDIDATE_DETECT", True),
            enable_final_verify=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_FINAL_VERIFY", False),
            enable_final_recheck=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_FINAL_RECHECK", False),
            enable_legacy_pipeline=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_LEGACY_PIPELINE", False),
            enable_crop_check=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_CROP_CHECK", True),
            crop_check_mode=_env_choice(
                "GUI_HARNESS_SCREENSPOT_CROP_CHECK_MODE",
                "every",
                {"every", "last_only", "off"},
            ),
            crop_check_reject_mode=_env_choice(
                "GUI_HARNESS_SCREENSPOT_CROP_CHECK_REJECT_MODE",
                "widen",
                {"widen", "restart_full"},
            ),
            enable_crop_retry=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_CROP_RETRY", True),
            crop_retry_limit=_env_int("GUI_HARNESS_SCREENSPOT_CROP_RETRY_LIMIT", 3, minimum=0),
            enable_final_recrop=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_FINAL_RECROP", True),
            final_recrop_limit=_env_int("GUI_HARNESS_SCREENSPOT_FINAL_RECROP_LIMIT", 0, minimum=0),
            enable_staged_crop=_env_bool("GUI_HARNESS_SCREENSPOT_ENABLE_STAGED_CROP", True),
            iterative_stage1_min_area_pct=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGE1_MIN_AREA_PCT", 20),
            iterative_stage2_min_area_pct=_env_int("GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGE2_MIN_AREA_PCT", 8),
            context_mode=_env_choice(
                "GUI_HARNESS_SCREENSPOT_CONTEXT_MODE",
                "single",
                {"single", "accumulate"},
            ),
            accumulate_images=_env_bool("GUI_HARNESS_SCREENSPOT_ACCUMULATE_IMAGES", False),
            runtime_timeout_s=_env_int("GUI_HARNESS_SCREENSPOT_RUNTIME_TIMEOUT_S", 180, minimum=0),
        )


def screenspot_locate(
    task: str,
    target: str,
    img_path: str,
    img_w: int,
    img_h: int,
    candidates: list[dict],
    runtime,
    work_dir: Optional[str] = None,
    config: Optional[ScreenSpotLocatorConfig] = None,
) -> Optional[dict]:
    """Locate one ScreenSpot-Pro click target using a fixed benchmark flow."""
    if runtime is None:
        return None

    config = config or ScreenSpotLocatorConfig.from_env()
    out_dir = work_dir or os.environ.get("GUI_HARNESS_ACTIVE_LOC_DIR") or tempfile.gettempdir()
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    if config.locator_mode == "iterative_zoom":
        located = _iterative_zoom_locate(task, target, img_path, img_w, img_h, runtime, out_dir, config, candidates)
        if located:
            return located
        if not config.enable_legacy_pipeline:
            return None

    located = _verified_crop_refine(task, target, img_path, img_w, img_h, runtime, out_dir, config, candidates)
    if located:
        return located

    if config.candidate_first:
        located = _candidate_first_select(task, target, img_path, candidates, runtime, out_dir, config)
        if located:
            return located

    if not config.active_fallback:
        return None

    return _active_controller_fallback(
        task=task,
        target=target,
        img_path=img_path,
        img_w=img_w,
        img_h=img_h,
        candidates=candidates,
        runtime=runtime,
        out_dir=out_dir,
        config=config,
    )


def _iterative_zoom_locate(
    task: str,
    target: str,
    img_path: str,
    img_w: int,
    img_h: int,
    runtime,
    out_dir: str,
    config: ScreenSpotLocatorConfig,
    candidates: list[dict],
) -> Optional[dict]:
    if runtime is None:
        return None

    current_box = [0, 0, img_w, img_h]
    history: list[dict] = []
    stop_refining = False
    # Accumulated prior-turn blocks for context_mode == "accumulate". Each
    # accepted crop turn appends its sent user blocks + the model reply, so the
    # next round's prompt = rules prefix + thread_blocks + new turn. Stays empty
    # (and unused) in single mode, keeping that path byte-identical.
    thread_blocks: list[dict] = []
    for round_idx in range(config.iterative_rounds):
        rejected_attempts: list[dict] = []
        max_attempts = 1 + (config.crop_retry_limit if config.enable_crop_retry else 0)
        for attempt_idx in range(max_attempts):
            stage_idx = _iterative_committed_crop_count(history)
            crop_path, crop_box, display_scale = _render_iterative_crop(
                img_path,
                current_box,
                out_dir,
                f"iter_round{round_idx + 1}_attempt{attempt_idx + 1}",
                max_side=config.iterative_max_side,
                max_scale=config.iterative_max_scale,
                min_short_side=config.iterative_min_short_side,
                min_scale=config.iterative_min_scale,
                scale_mode=config.iterative_scale_mode,
                target_pixels=config.iterative_target_pixels,
            )
            candidate_lines, _round_candidates = _iterative_candidate_lines(
                candidates,
                crop_box,
                display_scale,
                limit=config.candidate_limit,
                target=target,
                sort_mode=config.candidate_sort,
                dedup_iou=config.candidate_dedup_iou,
            )
            dynamic_head = f"""Task: {task}
Target: {target}
Original screenshot size: {img_w}x{img_h}
Current crop in original coordinates: {crop_box}
This displayed crop is scaled by {display_scale:.4f} from original pixels.
Round: {round_idx + 1}/{config.iterative_rounds}
Attempt: {attempt_idx + 1}/{max_attempts}
Committed crop stage: {stage_idx + 1}
Staged crop guidance:
{_iterative_stage_guidance(stage_idx, config)}

Previous crop decisions:
{_format_iterative_history(history)}

Rejected crop attempts from this same current crop:
{_format_crop_rejections(rejected_attempts)}"""
            candidates_block = f"""Detected OCR/component candidates inside this crop, shown in displayed-crop
coordinates:
{candidate_lines or "(none)"}"""
            if config.iterative_prompt_layout == "legacy":
                # Byte-for-byte origin/main: framing prose -> candidates -> Rules
                # -> JSON, all in one text block, no cache prefix, no accumulation.
                context = (
                    dynamic_head + "\n\n" + _CROP_DECISION_RULES_INTRO + "\n\n"
                    + candidates_block + "\n\n" + _CROP_DECISION_RULES_BODY
                )
                content = [
                    {"type": "text", "text": context},
                    {"type": "image", "path": crop_path},
                ]
            else:
                # cache layout: fixed rules hoisted to a cacheable prefix block;
                # dynamic text (with a short JSON reminder at the tail) + image follow.
                if config.reasoning_first:
                    # Reasoning-first: the model must localize + justify in text
                    # BEFORE committing coordinates (reasoning/target precede bbox).
                    tail = (
                        "Think first, then act. In 'reasoning': state where in the "
                        "current crop the target is and which region you will keep "
                        "vs crop away. Then set the bbox to that region.\n"
                        "Reply with ONLY JSON:\n"
                        + '{"reasoning": "...", "target_visible_element": "...", '
                        + '"action": "crop|final|recrop", "bbox": [x1, y1, x2, y2], '
                        + '"confidence": 0.0}'
                    )
                else:
                    tail = (
                        "Reply with ONLY JSON:\n"
                        + '{"action": "crop|final|recrop", "bbox": [x1, y1, x2, y2], '
                        + '"target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}'
                    )
                context = dynamic_head + "\n\n" + candidates_block + "\n\n" + tail
                content = [
                    _cacheable_prefix_block(_CROP_DECISION_RULES),
                    *thread_blocks,
                    {"type": "text", "text": context},
                    {"type": "image", "path": crop_path},
                ]
            try:
                reply = _runtime_exec(runtime, config, content=content)
                parsed = parse_json(reply)
            except Exception as exc:
                reraise_if_fatal(exc)
                print(
                    f"  [screenspot_zoom] round {round_idx + 1} attempt {attempt_idx + 1} "
                    f"failed: {exc.__class__.__name__}: {exc}",
                    file=__import__("sys").stderr,
                )
                rejected_attempts.append({
                    "action": "exception",
                    "reason": f"{exc.__class__.__name__}: {exc}",
                })
                continue

            action = str(parsed.get("action", "")).lower().strip()
            entry = {
                "round": round_idx + 1,
                "attempt": attempt_idx + 1,
                "action": action,
                "crop_path": crop_path,
                "crop_box": crop_box,
                "display_scale": display_scale,
                "target_visible_element": parsed.get("target_visible_element", ""),
                "confidence": float(parsed.get("confidence", 0) or 0),
                "reasoning": parsed.get("reasoning", ""),
            }
            if action in {"recrop", "restart", "widen", "fail"}:
                fallback_box = _iterative_restart_box(current_box, history, img_w, img_h)
                entry["fallback_box"] = fallback_box
                rejected_attempts.append({
                    "action": action,
                    "bbox": parsed.get("bbox"),
                    "reasoning": parsed.get("reasoning", ""),
                    "fallback_box": fallback_box,
                })
                history.append(entry)
                current_box = fallback_box
                if attempt_idx + 1 < max_attempts:
                    continue
                break
            if action == "final":
                if config.enable_crop_check and not any(item.get("next_box") for item in history):
                    rejected_attempts.append({
                        "action": action,
                        "bbox": parsed.get("bbox"),
                        "reasoning": "final requested before any committed crop",
                    })
                    if attempt_idx + 1 < max_attempts:
                        continue
                    history.append(entry)
                    stop_refining = True
                    break
                history.append(entry)
                stop_refining = True
                break
            if action != "crop":
                fallback_box = _iterative_restart_box(current_box, history, img_w, img_h)
                entry["fallback_box"] = fallback_box
                rejected_attempts.append({
                    "action": action,
                    "bbox": parsed.get("bbox"),
                    "reasoning": "invalid crop action",
                    "fallback_box": fallback_box,
                })
                if attempt_idx + 1 < max_attempts:
                    continue
                history.append(entry)
                current_box = fallback_box
                break

            next_box = _iterative_next_box(
                parsed.get("bbox"),
                crop_box,
                display_scale,
                img_w,
                img_h,
                config,
                stage_idx,
            )
            if not next_box:
                entry["rejected_next_box"] = parsed.get("bbox")
                rejected_attempts.append({
                    "action": action,
                    "bbox": parsed.get("bbox"),
                    "reasoning": "bbox failed geometric checks",
                })
                if attempt_idx + 1 < max_attempts:
                    continue
                history.append(entry)
                current_box = _iterative_restart_box(current_box, history, img_w, img_h)
                break

            gate = None
            # When this crop's check runs depends on crop_check_mode:
            #   "every"     — check every round (default)
            #   "last_only" — only on the final round (round_idx == rounds-1)
            #   "off"       — never
            # enable_crop_check=False also disables it entirely (back-compat).
            _mode = config.crop_check_mode
            _is_last_round = round_idx == config.iterative_rounds - 1
            _check_now = (
                config.enable_crop_check
                and _mode != "off"
                and (_mode != "last_only" or _is_last_round)
            )
            if _check_now:
                gate = _run_crop_check(
                    task,
                    target,
                    img_w,
                    img_h,
                    runtime,
                    crop_path,
                    crop_box,
                    display_scale,
                    parsed.get("bbox"),
                    next_box,
                    parsed,
                    out_dir,
                    round_idx,
                    attempt_idx,
                    config,
                    candidates,
                    stage_idx=stage_idx,
                )
                entry["crop_check"] = gate
                if not gate or gate.get("action") != "accept":
                    rejected_attempts.append({
                        "action": "crop_check_reject",
                        "bbox": parsed.get("bbox"),
                        "reasoning": (gate or {}).get("reasoning", "crop check rejected crop"),
                    })
                    if attempt_idx + 1 < max_attempts:
                        continue
                    history.append(entry)
                    # On reject after retries: widen back, or restart from the
                    # full image (re-crop from scratch) per crop_check_reject_mode.
                    if config.crop_check_reject_mode == "restart_full":
                        current_box = [0, 0, img_w, img_h]
                    else:
                        current_box = _iterative_restart_box(current_box, history, img_w, img_h)
                    break

            old_area = _box_area(crop_box)
            new_area = _box_area(next_box)
            entry["next_box"] = next_box
            entry["area_fraction"] = round(new_area / old_area, 4) if old_area else 1.0
            history.append(entry)
            if config.context_mode == "accumulate":
                # Carry this accepted turn forward so next round's prompt grows a
                # byte-stable prefix. Only accepted crops join the thread (gate
                # rejections / recrops stay out, keeping the chain clean).
                thread_blocks.append({"type": "text", "text": context})
                if config.accumulate_images:
                    thread_blocks.append({"type": "image", "path": crop_path})
                thread_blocks.append({
                    "type": "text",
                    "text": f"[assistant round {round_idx + 1} decision]\n{reply}",
                })
            print(
                f"  [screenspot_zoom] round {round_idx + 1} attempt {attempt_idx + 1}: "
                f"{crop_box} -> {next_box} area={entry['area_fraction']}",
                file=__import__("sys").stderr,
            )
            current_box = next_box
            if (
                current_box[2] - current_box[0] <= config.iterative_min_width
                or current_box[3] - current_box[1] <= config.iterative_min_height
            ):
                stop_refining = True
            break

        if stop_refining:
            break

    final_boxes = _iterative_final_box_candidates(current_box, history, img_w, img_h)
    if not config.enable_final_recrop:
        final_boxes = final_boxes[:1]
    elif config.final_recrop_limit > 0:
        final_boxes = final_boxes[:config.final_recrop_limit]
    for final_attempt_idx, final_box in enumerate(final_boxes):
        located = _iterative_zoom_final_click(
            task,
            target,
            img_path,
            final_box,
            img_w,
            img_h,
            runtime,
            out_dir,
            config,
            candidates,
            history,
            final_attempt_idx=final_attempt_idx + 1,
            final_attempts=len(final_boxes),
        )
        if located:
            if final_attempt_idx:
                located.setdefault("iterative_zoom", {})["final_recrop_attempt"] = final_attempt_idx + 1
                located["iterative_zoom"]["final_recrop_source_box"] = final_box
            return located
    return None


def _box_area(box: list[int]) -> int:
    return max(0, int(box[2]) - int(box[0])) * max(0, int(box[3]) - int(box[1]))


def _iterative_stage_guidance(round_idx: int, config: ScreenSpotLocatorConfig) -> str:
    if not config.enable_staged_crop:
        return "Use a conservative crop that preserves the requested target and context."
    if round_idx == 0:
        return (
            "Stage 1: screen/window selection. If the screenshot contains multiple "
            "apps, windows, panes, or documents, crop to the relevant app/window or "
            "broad screen region first. Do not jump directly to a tiny toolbar icon, "
            "button, or text label."
        )
    if round_idx == 1:
        return (
            "Stage 2: region selection inside the chosen app/window. Crop to the "
            "relevant page, dialog, ribbon/toolbar, sidebar, canvas area, bottom "
            "panel, or functional section. Keep competing sections visible if the "
            "instruction is still ambiguous."
        )
    if round_idx == 2:
        return (
            "Stage 3: control-group selection. Crop to the local group containing "
            "the target and nearby alternatives or labels needed to disambiguate it."
        )
    return (
        "Stage 4+: fine refinement. Crop closer only after the app/window, section, "
        "and local control group are already unambiguous."
    )


def _stage_min_area_pct(round_idx: int, config: ScreenSpotLocatorConfig) -> int:
    if not config.enable_staged_crop:
        return 0
    if round_idx == 0:
        return max(0, config.iterative_stage1_min_area_pct)
    if round_idx == 1:
        return max(0, config.iterative_stage2_min_area_pct)
    return 0


def _iterative_committed_crop_count(history: list[dict]) -> int:
    return sum(1 for item in history if item.get("next_box"))


def _iterative_restart_box(current_box: list[int], history: list[dict], img_w: int, img_h: int) -> list[int]:
    current_area = _box_area(current_box)
    for item in reversed(history):
        candidate = item.get("crop_box")
        if (
            isinstance(candidate, list)
            and len(candidate) == 4
            and _box_area(candidate) > current_area
        ):
            return active._clamp_box(candidate, img_w, img_h)
    return [0, 0, img_w, img_h]


def _iterative_final_box_candidates(
    current_box: list[int],
    history: list[dict],
    img_w: int,
    img_h: int,
) -> list[list[int]]:
    boxes: list[list[int]] = []
    seen: set[tuple[int, int, int, int]] = set()

    def add(box) -> None:
        if not isinstance(box, list) or len(box) != 4:
            return
        try:
            clamped = active._clamp_box([int(v) for v in box], img_w, img_h)
        except (TypeError, ValueError):
            return
        if clamped[2] <= clamped[0] or clamped[3] <= clamped[1]:
            return
        key = tuple(clamped)
        if key in seen:
            return
        seen.add(key)
        boxes.append(clamped)

    add(current_box)
    for item in reversed(history):
        add(item.get("crop_box"))
        add(item.get("fallback_box"))
    add([0, 0, img_w, img_h])
    return boxes


def _expand_box_to_min_area(box: list[int], parent_box: list[int], min_area: float) -> list[int]:
    if min_area <= 0 or _box_area(box) >= min_area:
        return box
    px1, py1, px2, py2 = parent_box
    parent_w = max(1, px2 - px1)
    parent_h = max(1, py2 - py1)
    width = max(1, box[2] - box[0])
    height = max(1, box[3] - box[1])
    factor = (min_area / max(1, width * height)) ** 0.5
    new_w = min(parent_w, max(width, int(round(width * factor))))
    new_h = min(parent_h, max(height, int(round(height * factor))))
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    x1 = int(round(cx - new_w / 2.0))
    y1 = int(round(cy - new_h / 2.0))
    x1 = max(px1, min(x1, px2 - new_w))
    y1 = max(py1, min(y1, py2 - new_h))
    return [x1, y1, x1 + new_w, y1 + new_h]


def _text_has_any(text: str, words: tuple[str, ...]) -> bool:
    lower = (text or "").lower()
    return any(word in lower for word in words)


def _is_adjustment_like_request(task: str, target: str) -> bool:
    return _text_has_any(
        f"{task}\n{target}",
        (
            "adjust",
            "change",
            "modify",
            "set ",
            "increase",
            "decrease",
            "raise",
            "lower",
            "make ",
            "select",
            "choose",
            "pick",
        ),
    )


def _mentions_direct_control(text: str) -> bool:
    return _text_has_any(
        text,
        (
            "slider",
            "track",
            "thumb",
            "handle",
            "knob",
            "input",
            "textbox",
            "text box",
            "field",
            "dropdown",
            "drop-down",
            "combo",
            "checkbox",
            "check box",
            "radio",
            "switch",
            "toggle",
            "button",
            "swatch",
            "color square",
            "color chip",
            "palette",
            "value area",
            "control",
        ),
    )


def _mentions_passive_marker(text: str) -> bool:
    return _text_has_any(
        text,
        (
            "label",
            "icon",
            "category",
            "heading",
            "header",
            "title",
            "status",
            "caption",
            "legend",
            "preview",
            "thumbnail",
        ),
    )


def _review_replacement_breaks_control_type(task: str, target: str, proposed: dict, reviewed: dict) -> bool:
    if not _is_adjustment_like_request(task, target):
        return False
    proposed_text = f"{proposed.get('target_visible_element', '')}\n{proposed.get('reasoning', '')}"
    reviewed_text = f"{reviewed.get('target_visible_element', '')}\n{reviewed.get('reasoning', '')}"
    if not _mentions_direct_control(proposed_text):
        return False
    if _mentions_direct_control(reviewed_text):
        return False
    return _mentions_passive_marker(reviewed_text)


def _render_iterative_crop(
    img_path: str,
    box: list[int],
    out_dir: str,
    name: str,
    max_side: int,
    max_scale: int,
    min_short_side: int = 0,
    min_scale: float = 1.0,
    scale_mode: str = "preserve",
    target_pixels: int = 0,
) -> tuple[str, list[int], float]:
    """Render a crop at a chosen display scale.

    scale_mode picks the policy:
      "preserve" (default): start at 1.0 (original resolution); only up-scale a
        small crop (min_short_side raises it, max_scale caps); large crops keep
        full resolution unless max_side shrinks them. The "only enlarge small
        crops, leave big ones alone" policy.
      "fill": reproduce origin/main — start at scale_cap = min(max_scale,
        max_side/longest_side), so every sub-max_side crop is blown UP to fill
        max_side on the long side (or the max_scale cap); large crops shrink to
        max_side. Use this to match the legacy baseline.

    Knobs:
      min_short_side : up-scale a small crop until its short side reaches this (0=off).
      max_scale      : cap on the up-scale factor (0 = unlimited).
      max_side       : longest displayed side cap (shrinks big crops; 0 = no cap).
      min_scale      : hard floor on scale (1.0 = never shrink; 0.1 = allow shrink).
    """
    img = Image.open(img_path).convert("RGB")
    img_w, img_h = img.size
    x1, y1, x2, y2 = active._clamp_box(box, img_w, img_h)
    crop = img.crop((x1, y1, x2, y2))
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    floor = float(min_scale) if min_scale and min_scale > 0 else 0.1
    if scale_mode == "target_pixels" and target_pixels > 0:
        # Adaptive: scale every crop so its pixel count (~ file size) lands near
        # target_pixels. Small crops get enlarged a lot, crops already at/over the
        # target are left alone (never shrink). scale = sqrt(target / crop_area),
        # clamped to [1.0, max_scale]. This keeps the image fed to the model a
        # roughly constant size regardless of crop area, and bounds the long side
        # automatically (so it never blows past the provider's image-size limit).
        crop_area = float(width * height)
        scale = (float(target_pixels) / crop_area) ** 0.5 if crop_area > 0 else 1.0
        if max_scale > 0:
            scale = min(scale, float(max_scale))
        scale = max(1.0, scale)
    elif scale_mode == "fill":
        # origin/main policy: blow every crop up to fill max_side (long side).
        cap = float(max_scale) if max_scale > 0 else float("inf")
        if max_side > 0:
            cap = min(cap, float(max_side) / max(width, height))
        scale = cap if cap != float("inf") else 1.0
        if min_short_side > 0:
            scale = min(cap, max(scale, float(min_short_side) / min(width, height)))
        scale = max(floor, scale)
    else:
        # "preserve": start at original size; only enlarge small crops.
        scale = 1.0
        if min_short_side > 0:
            target = float(min_short_side) / min(width, height)
            if target > scale:
                scale = target
        if max_scale > 0:
            scale = min(scale, float(max_scale))
        if max_side > 0:
            scale = min(scale, float(max_side) / max(width, height))
        scale = max(floor, scale)
    display_w = max(1, int(round(width * scale)))
    display_h = max(1, int(round(height * scale)))
    if display_w != width or display_h != height:
        crop = crop.resize((display_w, display_h), Image.Resampling.LANCZOS)
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)[:60]
    out = Path(out_dir) / f"screenspot_iterative_{os.getpid()}_{safe_name}.png"
    crop.save(out)
    return str(out), [x1, y1, x2, y2], scale


def _iterative_candidate_lines(
    candidates: list[dict],
    crop_box: list[int],
    display_scale: float,
    limit: int,
    target: str = "",
    sort_mode: str = "none",
    dedup_iou: float = 0.0,
) -> tuple[str, list[dict]]:
    """Build the candidate evidence block.

    sort_mode  : "none" (detector order, legacy) | "relevance" (rank by match to
                 target, then confidence) | "confidence". Applied BEFORE the
                 limit truncation so the most useful candidates survive.
    dedup_iou  : >0 drops a candidate that overlaps an already-kept one above this
                 IoU (removes OCR-word-vs-button and near-duplicate boxes). 0=off.
    Ids (z0, z1, ...) are assigned AFTER sort+dedup so they match the shown order.
    """
    x1, y1, x2, y2 = crop_box
    pool: list[dict] = []
    for cand in candidates:
        cbox = active._candidate_box(cand)
        ccx = int(cand.get("cx", (cbox[0] + cbox[2]) / 2) or 0)
        ccy = int(cand.get("cy", (cbox[1] + cbox[3]) / 2) or 0)
        if active._iou(cbox, crop_box) <= 0 and not (x1 <= ccx <= x2 and y1 <= ccy <= y2):
            continue
        pool.append(dict(cand))
    # Sort before truncating so the cap keeps the most useful candidates.
    if sort_mode == "relevance" and target:
        pool.sort(key=lambda c: (active._candidate_relevance(target, c),
                                 float(c.get("confidence", 0) or 0)), reverse=True)
    elif sort_mode == "confidence":
        pool.sort(key=lambda c: float(c.get("confidence", 0) or 0), reverse=True)
    # Greedy IoU dedup (keep higher-ranked, drop overlaps).
    if dedup_iou and dedup_iou > 0:
        kept: list[dict] = []
        for cand in pool:
            cb = active._candidate_box(cand)
            if any(active._iou(cb, active._candidate_box(k)) >= dedup_iou for k in kept):
                continue
            kept.append(cand)
        pool = kept
    scoped: list[dict] = []
    for cand in pool[:limit]:
        cand["id"] = f"z{len(scoped)}"
        scoped.append(cand)
    lines = []
    for cand in scoped:
        cbox = active._candidate_box(cand)
        ccx = int(cand.get("cx", (cbox[0] + cbox[2]) / 2) or 0)
        ccy = int(cand.get("cy", (cbox[1] + cbox[3]) / 2) or 0)
        local_box = [
            int(round((cbox[0] - x1) * display_scale)),
            int(round((cbox[1] - y1) * display_scale)),
            int(round((cbox[2] - x1) * display_scale)),
            int(round((cbox[3] - y1) * display_scale)),
        ]
        local_center = [
            int(round((ccx - x1) * display_scale)),
            int(round((ccy - y1) * display_scale)),
        ]
        label = cand.get("label") or cand.get("name") or "(unlabeled)"
        lines.append(
            f"{cand['id']}: {label} source={cand.get('source')} type={cand.get('type')} "
            f"display_bbox={local_box} display_center={local_center} "
            f"original_center=({ccx},{ccy})"
        )
    return "\n".join(lines), scoped


def _iterative_candidate_partition_lines(
    candidates: list[dict],
    current_box: list[int],
    proposed_box: list[int],
    display_scale: float,
    limit: int = 80,
) -> tuple[str, str]:
    x1, y1, x2, y2 = current_box
    inside: list[str] = []
    outside: list[str] = []
    for cand in candidates:
        cbox = active._candidate_box(cand)
        ccx = int(cand.get("cx", (cbox[0] + cbox[2]) / 2) or 0)
        ccy = int(cand.get("cy", (cbox[1] + cbox[3]) / 2) or 0)
        if active._iou(cbox, current_box) <= 0 and not (x1 <= ccx <= x2 and y1 <= ccy <= y2):
            continue
        in_proposed = active._iou(cbox, proposed_box) > 0 or (
            proposed_box[0] <= ccx <= proposed_box[2] and proposed_box[1] <= ccy <= proposed_box[3]
        )
        local_box = [
            int(round((cbox[0] - x1) * display_scale)),
            int(round((cbox[1] - y1) * display_scale)),
            int(round((cbox[2] - x1) * display_scale)),
            int(round((cbox[3] - y1) * display_scale)),
        ]
        local_center = [
            int(round((ccx - x1) * display_scale)),
            int(round((ccy - y1) * display_scale)),
        ]
        label = cand.get("label") or cand.get("name") or "(unlabeled)"
        line = (
            f"{label} source={cand.get('source')} type={cand.get('type')} "
            f"display_bbox={local_box} display_center={local_center} "
            f"original_center=({ccx},{ccy})"
        )
        if in_proposed:
            inside.append(line)
        else:
            outside.append(line)
    return "\n".join(inside[:limit]), "\n".join(outside[:limit])


def _format_crop_rejections(rejections: list[dict]) -> str:
    if not rejections:
        return "(none)"
    lines = []
    for idx, item in enumerate(rejections[-6:], start=1):
        lines.append(
            f"attempt {idx}: action={item.get('action')} bbox={item.get('bbox')} "
            f"reason={item.get('reasoning') or item.get('reason')}"
        )
    return "\n".join(lines)


def _render_crop_commit_overlay(
    crop_path: str,
    display_bbox,
    out_dir: str,
    name: str,
) -> Optional[str]:
    if not isinstance(display_bbox, list) or len(display_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in display_bbox]
    except (TypeError, ValueError):
        return None
    img = Image.open(crop_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width = max(4, round(max(img.size) / 300))
    draw.rectangle([x1, y1, x2, y2], outline="#ff00ff", width=width)
    draw.text((max(0, x1 + 6), max(0, y1 + 6)), "proposed crop", fill="#ff00ff")
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)[:60]
    out = Path(out_dir) / f"screenspot_iterative_{os.getpid()}_{safe_name}_commit.png"
    img.save(out)
    return str(out)


def _run_crop_check(
    task: str,
    target: str,
    img_w: int,
    img_h: int,
    runtime,
    crop_path: str,
    crop_box: list[int],
    display_scale: float,
    display_bbox,
    next_box: list[int],
    proposal: dict,
    out_dir: str,
    round_idx: int,
    attempt_idx: int,
    config: ScreenSpotLocatorConfig,
    candidates: list[dict],
    stage_idx: Optional[int] = None,
) -> Optional[dict]:
    overlay_path = _render_crop_commit_overlay(
        crop_path,
        display_bbox,
        out_dir,
        f"iter_round{round_idx + 1}_attempt{attempt_idx + 1}",
    )
    if not overlay_path:
        return {"action": "reject", "confidence": 0.0, "reasoning": "could not render proposed crop overlay"}
    inside_candidates, outside_candidates = _iterative_candidate_partition_lines(
        candidates,
        crop_box,
        next_box,
        display_scale,
        limit=60,
    )

    guidance_idx = round_idx if stage_idx is None else stage_idx
    gate_head = f"""Task: {task}
Target: {target}
Original screenshot size: {img_w}x{img_h}
Current crop in original coordinates: {crop_box}
Current crop display scale: {display_scale:.4f}
Proposed next crop in displayed-crop coordinates: {display_bbox}
Proposed next crop in original coordinates: {next_box}
Round: {round_idx + 1}
Attempt: {attempt_idx + 1}
Committed crop stage: {guidance_idx + 1}
Staged crop guidance:
{_iterative_stage_guidance(guidance_idx, config)}

The attached image is the current crop with a magenta rectangle showing the
proposed next crop. This is a commit gate. Do not click.

OCR/component candidates INSIDE the proposed magenta crop:
{inside_candidates or "(none)"}

OCR/component candidates still visible in the current crop but OUTSIDE the
proposed magenta crop:
{outside_candidates or "(none)"}"""
    rationale = f"""Proposal rationale:
target_visible_element={proposal.get('target_visible_element', '')}
reasoning={proposal.get('reasoning', '')}
confidence={proposal.get('confidence', '')}"""
    if config.iterative_prompt_layout == "legacy":
        # origin/main order: dynamic+framing+candidates -> accept rules ->
        # rationale -> JSON, one text block, no cache prefix.
        context = (
            gate_head + "\n\n" + _COMMIT_GATE_RULES_BODY + "\n\n"
            + rationale + "\n\n" + _COMMIT_GATE_JSON
        )
        gate_content = [
            {"type": "text", "text": context},
            {"type": "image", "path": overlay_path},
        ]
    else:
        context = gate_head + "\n\n" + rationale + "\n\n" + _COMMIT_GATE_JSON
        gate_content = [
            _cacheable_prefix_block(_COMMIT_GATE_RULES),
            {"type": "text", "text": context},
            {"type": "image", "path": overlay_path},
        ]
    try:
        parsed = parse_json(_runtime_exec(runtime, config, content=gate_content))
    except Exception as exc:
        reraise_if_fatal(exc)
        return {
            "action": "reject",
            "confidence": 0.0,
            "reasoning": f"crop check failed: {exc.__class__.__name__}: {exc}",
            "overlay_path": overlay_path,
        }
    action = str(parsed.get("action", "")).lower().strip()
    confidence = float(parsed.get("confidence", 0) or 0)
    target_inside = bool(parsed.get("target_inside"))
    context_sufficient = bool(parsed.get("context_sufficient"))
    discarded = bool(parsed.get("discarded_plausible_targets"))
    if action != "accept" or not target_inside or not context_sufficient or discarded:
        action = "reject"
    result = {
        "action": action,
        "target_inside": target_inside,
        "context_sufficient": context_sufficient,
        "discarded_plausible_targets": discarded,
        "confidence": confidence,
        "reasoning": parsed.get("reasoning", ""),
        "overlay_path": overlay_path,
    }
    return result


def _iterative_next_box(
    display_bbox,
    current_box: list[int],
    display_scale: float,
    img_w: int,
    img_h: int,
    config: ScreenSpotLocatorConfig,
    round_idx: int = 0,
) -> Optional[list[int]]:
    if not isinstance(display_bbox, list) or len(display_bbox) != 4:
        return None
    try:
        dx1, dy1, dx2, dy2 = [float(v) for v in display_bbox]
    except (TypeError, ValueError):
        return None
    if dx2 <= dx1 or dy2 <= dy1:
        return None
    x1, y1, x2, y2 = current_box
    next_box = [
        int(round(x1 + dx1 / display_scale)),
        int(round(y1 + dy1 / display_scale)),
        int(round(x1 + dx2 / display_scale)),
        int(round(y1 + dy2 / display_scale)),
    ]
    width = max(1, next_box[2] - next_box[0])
    height = max(1, next_box[3] - next_box[1])
    pad_x = int(round(width * config.iterative_padding_pct / 100.0))
    pad_y = int(round(height * config.iterative_padding_pct / 100.0))
    next_box = active._clamp_box(
        [next_box[0] - pad_x, next_box[1] - pad_y, next_box[2] + pad_x, next_box[3] + pad_y],
        img_w,
        img_h,
    )
    min_w = max(1, int(config.iterative_min_width or 1))
    min_h = max(1, int(config.iterative_min_height or 1))
    if next_box[2] - next_box[0] < min_w:
        cx = (next_box[0] + next_box[2]) // 2
        next_box[0] = cx - min_w // 2
        next_box[2] = next_box[0] + min_w
    if next_box[3] - next_box[1] < min_h:
        cy = (next_box[1] + next_box[3]) // 2
        next_box[1] = cy - min_h // 2
        next_box[3] = next_box[1] + min_h
    next_box = active._clamp_box(next_box, img_w, img_h)
    min_area_pct = _stage_min_area_pct(round_idx, config)
    if min_area_pct > 0:
        min_area = _box_area(current_box) * (min_area_pct / 100.0)
        next_box = _expand_box_to_min_area(next_box, current_box, min_area)
        next_box = active._clamp_box(next_box, img_w, img_h)
    if next_box[2] <= next_box[0] or next_box[3] <= next_box[1]:
        return None
    if _box_area(next_box) >= _box_area(current_box):
        return None
    # No upper cap on how much the model may shrink per round: it decides the
    # zoom amount. (iterative_max_area_pct=0 disables the cap; >0 re-enables it.)
    if config.iterative_max_area_pct > 0:
        max_area = _box_area(current_box) * (config.iterative_max_area_pct / 100.0)
        if _box_area(next_box) > max_area:
            return None
    return next_box


def _iterative_zoom_final_click(
    task: str,
    target: str,
    img_path: str,
    crop_box: list[int],
    img_w: int,
    img_h: int,
    runtime,
    out_dir: str,
    config: ScreenSpotLocatorConfig,
    candidates: list[dict],
    history: list[dict],
    final_attempt_idx: int = 1,
    final_attempts: int = 1,
) -> Optional[dict]:
    crop_path, crop_box, display_scale = _render_iterative_crop(
        img_path,
        crop_box,
        out_dir,
        f"iter_final_attempt{final_attempt_idx}",
        max_side=config.iterative_final_max_side,
        max_scale=config.iterative_final_max_scale,
        min_short_side=config.iterative_final_min_short_side,
        min_scale=config.iterative_final_min_scale,
        scale_mode=config.iterative_scale_mode,
        target_pixels=config.iterative_final_target_pixels,
    )
    final_candidates = list(candidates)
    if config.enable_final_candidate_detect:
        final_candidates.extend(
            active._detect_region_candidates(img_path, {"name": "iter_final", "bbox": crop_box}, out_dir)
        )
    candidate_lines, scoped_candidates = _iterative_candidate_lines(
        final_candidates,
        crop_box,
        display_scale,
        limit=config.iterative_final_candidates,
    )
    final_head = f"""Task: {task}
Target: {target}
Original screenshot size: {img_w}x{img_h}
Final crop in original coordinates: {crop_box}
This final crop is upscaled by {display_scale:.4f}. Return coordinates in the
DISPLAYED FINAL CROP image coordinate system.
Final click attempt: {final_attempt_idx}/{final_attempts}

Crop history:
{_format_iterative_history(history)}

Detected OCR/component candidates in this final crop:
{candidate_lines or "(none)"}"""
    if config.iterative_prompt_layout == "legacy":
        # origin/main: dynamic+history+candidates -> click-policy rules+JSON,
        # one text block, no cache prefix.
        context = final_head + "\n\n" + _FINAL_CLICK_RULES
        final_content = [
            {"type": "text", "text": context},
            {"type": "image", "path": crop_path},
        ]
    else:
        context = (
            final_head + "\n\n"
            + "Reply with ONLY JSON:\n"
            + '{"action": "click|recrop", "candidate_id": "z0 or empty", "x": 0, "y": 0, '
            + '"target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}'
        )
        final_content = [
            _cacheable_prefix_block(_FINAL_CLICK_RULES),
            {"type": "text", "text": context},
            {"type": "image", "path": crop_path},
        ]
    try:
        reply = _runtime_exec(runtime, config, content=final_content)
        parsed = parse_json(reply)
    except Exception as exc:
        reraise_if_fatal(exc)
        print(
            f"  [screenspot_zoom] final click failed: {exc.__class__.__name__}: {exc}",
            file=__import__("sys").stderr,
        )
        return None
    action = str(parsed.get("action", "")).lower().strip()
    if action in {"recrop", "restart", "widen", "fail"}:
        print(
            f"  [screenspot_zoom] final click requested recrop "
            f"attempt={final_attempt_idx}/{final_attempts} crop={crop_box}",
            file=__import__("sys").stderr,
        )
        return None
    if action != "click":
        return None

    x1, y1, x2, y2 = crop_box
    selected_candidate = None
    selected_id = str(parsed.get("candidate_id") or "").strip()
    if selected_id:
        selected_candidate = active._candidate_by_id(scoped_candidates, selected_id)

    cx = cy = None
    local_x = local_y = None
    try:
        local_x = float(parsed.get("x", 0))
        local_y = float(parsed.get("y", 0))
    except (TypeError, ValueError):
        local_x = local_y = None
    if (
        local_x is not None
        and local_y is not None
        and local_x > 0
        and local_y > 0
        and local_x <= (x2 - x1) * display_scale
        and local_y <= (y2 - y1) * display_scale
    ):
        cx = int(round(x1 + local_x / display_scale))
        cy = int(round(y1 + local_y / display_scale))
    elif selected_candidate:
        selected_box = active._candidate_box(selected_candidate)
        cx = int(round((selected_box[0] + selected_box[2]) / 2))
        cy = int(round((selected_box[1] + selected_box[3]) / 2))
        local_x = (cx - x1) * display_scale
        local_y = (cy - y1) * display_scale
    if cx is None or cy is None or cx <= 0 or cy <= 0 or cx > img_w or cy > img_h:
        return None

    review = None
    if config.enable_final_recheck:
        reviewed = _iterative_zoom_review_click(
            task,
            target,
            img_w,
            img_h,
            runtime,
            config,
            history,
            {
                "source": "final",
                "crop_path": crop_path,
                "crop_box": crop_box,
                "display_scale": display_scale,
            },
            {
                "cx": cx,
                "cy": cy,
                "local_x": local_x,
                "local_y": local_y,
                "target_visible_element": parsed.get("target_visible_element", ""),
                "reasoning": parsed.get("reasoning", ""),
            },
        )
        if reviewed and reviewed.get("action") == "replace":
            cx = int(reviewed["cx"])
            cy = int(reviewed["cy"])
            local_x = float(reviewed.get("local_x", local_x or 0))
            local_y = float(reviewed.get("local_y", local_y or 0))
            parsed["target_visible_element"] = reviewed.get("target_visible_element") or parsed.get("target_visible_element", "")
            parsed["reasoning"] = reviewed.get("reasoning") or parsed.get("reasoning", "")
            parsed["confidence"] = reviewed.get("confidence", parsed.get("confidence", 0))
            review = reviewed
        elif reviewed:
            review = reviewed

    result = {
        "id": "iterative_zoom",
        "label": parsed.get("target_visible_element", "iterative_zoom"),
        "name": parsed.get("target_visible_element", "iterative_zoom"),
        "source": "screenspot_iterative_zoom",
        "grounding_type": "iterative_zoom_crop_refine",
        "cx": cx,
        "cy": cy,
        "x": cx - 24,
        "y": cy - 24,
        "w": 48,
        "h": 48,
        "confidence": float(parsed.get("confidence", 0) or 0),
        "reasoning": parsed.get("reasoning", ""),
        "iterative_zoom": {
            "rounds": len(history),
            "history": history,
            "final_crop_path": crop_path,
            "final_crop_box": crop_box,
            "final_display_scale": display_scale,
            "local_point_scaled": [round(float(local_x), 2), round(float(local_y), 2)],
            "candidate_count": len(scoped_candidates),
            "selected_candidate_id": selected_id if selected_candidate else "",
            "selected_candidate": selected_candidate,
            "review": review,
        },
    }
    if config.enable_final_verify:
        verifier = active.verify_candidate(task, target, img_path, result, runtime, out_dir=out_dir)
        result["pre_click_verifier"] = verifier
    print(
        f"  [screenspot_zoom] final click ({cx},{cy}) crop={crop_box} scale={display_scale:.2f}",
        file=__import__("sys").stderr,
    )
    return result


def _iterative_zoom_review_click(
    task: str,
    target: str,
    img_w: int,
    img_h: int,
    runtime,
    config: ScreenSpotLocatorConfig,
    history: list[dict],
    final_entry: dict,
    proposed: dict,
) -> Optional[dict]:
    """Review a final click against recent wider crops and optionally replace it."""
    review_crops: list[dict] = [dict(final_entry, source="r0", description="final upscaled crop")]
    seen = {tuple(final_entry.get("crop_box", []))}
    for item in reversed(history):
        crop_path = item.get("crop_path")
        crop_box = item.get("crop_box")
        display_scale = item.get("display_scale")
        if not crop_path or not crop_box or not display_scale:
            continue
        key = tuple(crop_box)
        if key in seen:
            continue
        seen.add(key)
        review_crops.append({
            "source": f"r{len(review_crops)}",
            "description": f"wider crop from round {item.get('round')}",
            "crop_path": crop_path,
            "crop_box": crop_box,
            "display_scale": display_scale,
            "visible": item.get("target_visible_element", ""),
        })
        if len(review_crops) >= 4:
            break

    crop_lines = []
    for item in review_crops:
        box = item["crop_box"]
        scale = float(item["display_scale"])
        crop_lines.append(
            f"{item['source']}: {item['description']} original_box={box} "
            f"display_scale={scale:.4f} visible={item.get('visible', '')}"
        )
    context = f"""Task: {task}
Target: {target}
Original screenshot size: {img_w}x{img_h}

This is a review gate after an iterative zoom click. The first image is the
final crop used for the proposed click. Later images are wider earlier crops.

Proposed click:
- original=({proposed.get('cx')}, {proposed.get('cy')})
- final_crop_local=({proposed.get('local_x')}, {proposed.get('local_y')})
- chosen_element={proposed.get('target_visible_element', '')}
- reasoning={proposed.get('reasoning', '')}

Attached crop sources:
{chr(10).join(crop_lines)}

Review policy:
- Keep the proposed click only if it is the actual clickable ScreenSpot target.
- Replace it if a wider crop reveals a better actionable control for the same
  instruction that the zoom path cropped away.
- For turn on/off tasks, never replace with passive status text. Keep or choose
  an actual toggle/button/switch.
- Treat earlier crop decisions as an anchor. If the final click switched away
  from an earlier concrete actionable control, replace only when the wider crop
  clearly shows the earlier control better satisfies the instruction.
- For modify/change/adjust/set requests, preserve the direct editable control
  type. If the proposed click is on the relevant slider track/thumb, input,
  dropdown, checkbox, toggle, or color swatch, keep it. Do not replace an
  actionable control with the nearby label, category icon, header, preview, or
  explanatory text for that same setting.

If replacing, return x/y in the DISPLAYED CROP coordinates of the chosen source
(r0, r1, r2, ...). Reply with ONLY JSON:
{{"action": "keep|replace|fail", "source": "r0", "x": 0, "y": 0, "target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}}"""
    content = [{"type": "text", "text": context}]
    for item in review_crops:
        content.append({"type": "image", "path": item["crop_path"]})
    try:
        parsed = parse_json(_runtime_exec(runtime, config, content=content))
    except Exception as exc:
        reraise_if_fatal(exc)
        print(
            f"  [screenspot_zoom] review failed: {exc.__class__.__name__}: {exc}",
            file=__import__("sys").stderr,
        )
        return None

    action = str(parsed.get("action", "")).lower().strip()
    result = {
        "action": action or "keep",
        "source": str(parsed.get("source") or ""),
        "target_visible_element": parsed.get("target_visible_element", ""),
        "confidence": float(parsed.get("confidence", 0) or 0),
        "reasoning": parsed.get("reasoning", ""),
    }
    if action != "replace":
        return result
    if _review_replacement_breaks_control_type(task, target, proposed, result):
        result["action"] = "keep"
        result["reasoning"] = (
            "review replacement rejected because it would replace a direct "
            "editable control with a passive label/icon marker"
        )
        return result

    source = result["source"]
    source_crop = next((item for item in review_crops if item["source"] == source), None)
    if not source_crop:
        result["action"] = "keep"
        result["reasoning"] = f"review replacement source not found: {source}"
        return result
    try:
        local_x = float(parsed.get("x", 0))
        local_y = float(parsed.get("y", 0))
    except (TypeError, ValueError):
        result["action"] = "keep"
        result["reasoning"] = "review replacement had invalid coordinates"
        return result
    x1, y1, x2, y2 = source_crop["crop_box"]
    scale = float(source_crop["display_scale"])
    if local_x <= 0 or local_y <= 0 or local_x > (x2 - x1) * scale or local_y > (y2 - y1) * scale:
        result["action"] = "keep"
        result["reasoning"] = "review replacement outside selected crop"
        return result
    cx = int(round(x1 + local_x / scale))
    cy = int(round(y1 + local_y / scale))
    if cx <= 0 or cy <= 0 or cx > img_w or cy > img_h:
        result["action"] = "keep"
        result["reasoning"] = "review replacement outside original image"
        return result
    result.update({
        "cx": cx,
        "cy": cy,
        "local_x": local_x,
        "local_y": local_y,
        "source_crop_box": source_crop["crop_box"],
        "source_display_scale": scale,
    })
    print(
        f"  [screenspot_zoom] review replaced click with ({cx},{cy}) from {source}",
        file=__import__("sys").stderr,
    )
    return result


def _format_iterative_history(history: list[dict]) -> str:
    lines = []
    for item in history[-8:]:
        line = (
            f"round {item.get('round')}: action={item.get('action')} "
            f"crop={item.get('crop_box')} next={item.get('next_box')} "
            f"area_fraction={item.get('area_fraction')} "
            f"visible={item.get('target_visible_element')}"
        )
        lines.append(line)
    return "\n".join(lines) or "(none)"


def _candidate_first_select(
    task: str,
    target: str,
    img_path: str,
    candidates: list[dict],
    runtime,
    out_dir: str,
    config: ScreenSpotLocatorConfig,
) -> Optional[dict]:
    """Prefer bounded OCR/component candidates before free-form localization."""
    pool = list(candidates)
    attempts = min(3, max(1, config.active_rounds + 1))
    for attempt in range(attempts):
        selected = active.rerank_candidates(task, target, img_path, pool, runtime)
        if not selected:
            return None
        selected["source"] = "screenspot_candidate_first"
        selected["grounding_type"] = "candidate_first_rerank"
        verifier = active.verify_candidate(task, target, img_path, selected, runtime, out_dir=out_dir)
        selected["pre_click_verifier"] = verifier
        verdict = str(verifier.get("is_target", "")).lower()
        print(
            f"  [screenspot_locate] candidate-first attempt {attempt + 1}: "
            f"{selected.get('name')} at ({selected.get('cx')},{selected.get('cy')}) "
            f"verdict={verdict} clicked={verifier.get('clicked_visible_element', '')!r} "
            f"target={verifier.get('target_visible_element', '')!r} "
            f"evidence={verifier.get('evidence', '')!r}",
            file=__import__("sys").stderr,
        )
        if verdict == "yes" and verifier.get("suggestion") != "zoom":
            return selected
        active._remove_rejected_candidate(pool, selected)
    return None


def _verified_crop_refine(
    task: str,
    target: str,
    img_path: str,
    img_w: int,
    img_h: int,
    runtime,
    out_dir: str,
    config: ScreenSpotLocatorConfig,
    candidates: list[dict],
) -> Optional[dict]:
    regions = active.propose_regions(
        task,
        target,
        img_path,
        img_w,
        img_h,
        runtime,
        max_regions=config.region_limit,
        candidates=candidates,
    )
    rejected_regions: list[tuple[dict, dict]] = []
    rejected_clicks: list[tuple[dict, dict, str]] = []
    for region in regions:
        verifier = active.verify_region_crop(task, target, img_path, region, runtime, out_dir)
        verdict = str(verifier.get("contains_target", "")).lower()
        print(
            f"  [screenspot_locate] region {region.get('name')} {region.get('bbox')} "
            f"verdict={verdict} target={verifier.get('target_visible_element', '')!r} "
            f"evidence={verifier.get('evidence', '')!r}",
            file=__import__("sys").stderr,
        )
        if not _crop_verifier_allows_refine(verifier, config):
            rejected_regions.append((region, verifier))
            continue

        selected = _refine_and_verify_region(
            task,
            target,
            img_path,
            region,
            verifier,
            runtime,
            out_dir,
            candidates,
        )
        if selected and _pre_click_verifier_allows_click(selected.get("pre_click_verifier", {})):
            return selected
        if selected:
            rejected_clicks.append((selected, selected.get("pre_click_verifier", {}), "strict_crop_gate"))

    relaxed = _try_relaxed_crop_regions(
        task,
        target,
        img_path,
        runtime,
        out_dir,
        config,
        candidates,
        rejected_regions,
        rejected_clicks,
    )
    if relaxed:
        return relaxed

    return _relaxed_pre_click_fallback(rejected_clicks, config)


def _refine_and_verify_region(
    task: str,
    target: str,
    img_path: str,
    region: dict,
    crop_verifier: dict,
    runtime,
    out_dir: str,
    candidates: list[dict],
) -> Optional[dict]:
    selected = active.refine_click_in_region(task, target, img_path, region, runtime, out_dir, candidates=candidates)
    if not selected:
        return None
    selected["crop_region_verifier"] = crop_verifier

    final_verifier = active.verify_candidate(task, target, img_path, selected, runtime, out_dir=out_dir)
    selected["pre_click_verifier"] = final_verifier
    final_verdict = str(final_verifier.get("is_target", "")).lower()
    print(
        f"  [screenspot_locate] refined click ({selected.get('cx')},{selected.get('cy')}) "
        f"verdict={final_verdict} evidence={final_verifier.get('evidence', '')!r}",
        file=__import__("sys").stderr,
    )
    return selected


def _try_relaxed_crop_regions(
    task: str,
    target: str,
    img_path: str,
    runtime,
    out_dir: str,
    config: ScreenSpotLocatorConfig,
    candidates: list[dict],
    rejected_regions: list[tuple[dict, dict]],
    rejected_clicks: list[tuple[dict, dict, str]],
) -> Optional[dict]:
    fallback_after = config.crop_verify_fallback_after
    if fallback_after <= 0 or len(rejected_regions) < fallback_after:
        return None

    for attempt, (region, verifier) in enumerate(rejected_regions, start=1):
        print(
            f"  [screenspot_locate] relaxing crop verifier after {len(rejected_regions)} "
            f"rejected regions; refining rejected region {attempt}: {region.get('name')}",
            file=__import__("sys").stderr,
        )
        selected = _refine_and_verify_region(
            task,
            target,
            img_path,
            region,
            verifier,
            runtime,
            out_dir,
            candidates,
        )
        if not selected:
            continue
        selected["crop_region_verifier_relaxed"] = {
            "reason": "regular crop verifier rejected enough regions; refined this crop as a fallback",
            "rejected_region_count": len(rejected_regions),
            "fallback_after": fallback_after,
        }
        verifier = selected.get("pre_click_verifier", {})
        if _pre_click_verifier_allows_click(verifier):
            return selected
        rejected_clicks.append((selected, verifier, "relaxed_crop_gate"))

    return None


def _crop_verifier_allows_refine(verifier: dict, config: ScreenSpotLocatorConfig) -> bool:
    verdict = str(verifier.get("contains_target", "")).lower()
    suggestion = str(verifier.get("suggestion", "")).lower()
    if config.crop_verify_mode == "off":
        return True
    if config.crop_verify_mode == "soft":
        return not (verdict == "no" and suggestion == "try_next")
    return verdict == "yes" and suggestion != "try_next"


def _pre_click_verifier_allows_click(verifier: dict) -> bool:
    verdict = str(verifier.get("is_target", "")).lower()
    suggestion = str(verifier.get("suggestion", "")).lower()
    return verdict == "yes" and suggestion != "zoom"


def _relaxed_pre_click_fallback(
    rejected_clicks: list[tuple[dict, dict, str]],
    config: ScreenSpotLocatorConfig,
) -> Optional[dict]:
    fallback_after = config.pre_click_verify_fallback_after
    if fallback_after <= 0 or len(rejected_clicks) < fallback_after:
        return None

    eligible_clicks = [
        item for item in rejected_clicks
        if _pre_click_relaxation_allows_candidate(item[0], item[1])
    ]
    if not eligible_clicks:
        return None

    def score(item: tuple[dict, dict, str]) -> tuple[float, float]:
        selected, verifier, source = item
        verdict = str(verifier.get("is_target", "")).lower()
        suggestion = str(verifier.get("suggestion", "")).lower()
        if suggestion == "zoom":
            return (-100.0, 0.0)
        verdict_score = {"yes": 4.0, "uncertain": 2.0, "no": 0.0}.get(verdict, 1.0)
        source_score = 1.0 if source == "relaxed_crop_gate" else 0.0
        confidence = float(selected.get("active_confidence", selected.get("confidence", 0.0)) or 0.0)
        return (verdict_score + source_score, confidence)

    selected, verifier, source = max(eligible_clicks, key=score)
    if score((selected, verifier, source))[0] < -50.0:
        return None
    selected["pre_click_verifier_relaxed"] = {
        "reason": "pre-click verifier rejected enough refined candidates; returning best non-zoom candidate",
        "rejected_click_count": len(rejected_clicks),
        "fallback_after": fallback_after,
        "selected_from": source,
    }
    selected["active_verifier_relaxed"] = True
    print(
        f"  [screenspot_locate] relaxing pre-click verifier after {len(rejected_clicks)} "
        f"rejected clicks; returning {selected.get('name')} at "
        f"({selected.get('cx')},{selected.get('cy')})",
        file=__import__("sys").stderr,
    )
    return selected


def _pre_click_relaxation_allows_candidate(selected: dict, verifier: dict) -> bool:
    suggestion = str(verifier.get("suggestion", "")).lower()
    if suggestion == "zoom":
        return False

    verdict = str(verifier.get("is_target", "")).lower()
    if verdict == "uncertain":
        return True

    crop_verifier = selected.get("crop_region_verifier") or {}
    crop_verdict = str(crop_verifier.get("contains_target", "")).lower()
    crop_suggestion = str(crop_verifier.get("suggestion", "")).lower()
    crop_saw_target = crop_verdict in {"yes", "uncertain"} and crop_suggestion != "try_next"

    # A hard pre-click "no" is only relaxable when the crop-level evidence said
    # this region contains the target. If both gates say no, keep the WF.
    return verdict == "no" and crop_saw_target


def _active_controller_fallback(
    task: str,
    target: str,
    img_path: str,
    img_w: int,
    img_h: int,
    candidates: list[dict],
    runtime,
    out_dir: str,
    config: ScreenSpotLocatorConfig,
) -> Optional[dict]:
    pool = list(candidates)
    crop_paths: list[tuple[str, str]] = []
    rejected: list[str] = []

    for round_idx in range(config.active_rounds):
        has_crop_context = bool(crop_paths)
        context = f"""Task: {task}
Target: {target}
Screenshot size: {img_w}x{img_h}
Round: {round_idx + 1}/{config.active_rounds}

You are localizing one click target in a static screenshot. Use the full image,
OCR text boxes, detected component boxes, and any crop images from previous
rounds. Decide ONE action:
- click: choose a final click point or candidate_id when the target is visible.
  Prefer candidate_id whenever a candidate box matches. The click must be at
  the center of the target component/text box, not near an edge or merely close
  to the label.
- crop: request up to 3 regions to inspect more closely if the target is not
  clear enough in the full screenshot/candidates.
- fail: if there is not enough evidence.

Be conservative: if the proposed click might be a different UI element, choose
crop or fail instead of click.

Recent rejected candidates:
{chr(10).join(rejected[-4:]) or "(none)"}

Candidate UI elements:
{active._candidate_lines(pool, config.active_top_k)}

Reply with ONLY JSON:
{{
  "action": "click|crop|fail",
  "candidate_id": "c0 or empty",
  "x": 0,
  "y": 0,
  "regions": [
    {{"name": "short_name", "bbox": [x1, y1, x2, y2], "reasoning": "..."}}
  ],
  "confidence": 0.0,
  "reasoning": "..."
}}"""
        content = [{"type": "text", "text": context}, {"type": "image", "path": img_path}]
        for name, path in crop_paths[-3:]:
            content.append({"type": "text", "text": f"Crop image: {name}"})
            content.append({"type": "image", "path": path})

        reply = _runtime_exec(runtime, config, content=content)
        try:
            decision = parse_json(reply)
        except Exception:
            rejected.append(f"round {round_idx + 1}: unparseable controller reply")
            continue

        action = str(decision.get("action", "")).lower().strip()
        if action == "click":
            selected = _selection_from_click_decision(decision, pool, img_w, img_h, has_crop_context, config)
            if selected is None:
                rejected.append(f"round {round_idx + 1}: invalid click decision")
                continue
            if selected.get("direct_unsnapped") and config.require_direct_snap and not has_crop_context:
                _add_direct_click_crop(img_path, selected, pool, crop_paths, out_dir, img_w, img_h, round_idx, config)
                rejected.append(
                    f"round {round_idx + 1}: rejected unsnapped direct pixel at "
                    f"({selected.get('cx')},{selected.get('cy')}); request crop or candidate_id"
                )
                continue

            selected["reasoning"] = decision.get("reasoning", "")
            verifier = active.verify_candidate(task, target, img_path, selected, runtime, out_dir=out_dir)
            selected["pre_click_verifier"] = verifier
            verdict = str(verifier.get("is_target", "")).lower()
            if verdict == "yes" and verifier.get("suggestion") != "zoom":
                if selected.get("direct_unsnapped"):
                    refined = _refine_direct_on_crop(task, target, img_path, selected, runtime, out_dir, img_w, img_h, config)
                    if refined:
                        refined_verifier = active.verify_candidate(task, target, img_path, refined, runtime, out_dir=out_dir)
                        refined["pre_click_verifier"] = refined_verifier
                        refined_verdict = str(refined_verifier.get("is_target", "")).lower()
                        if refined_verdict == "yes" and refined_verifier.get("suggestion") != "zoom":
                            return refined
                        print(
                            f"  [screenspot_locate] refined direct rejected at "
                            f"({refined.get('cx')},{refined.get('cy')}): "
                            f"verdict={refined_verdict} suggestion={refined_verifier.get('suggestion')} "
                            f"evidence={refined_verifier.get('evidence', '')!r}",
                            file=__import__("sys").stderr,
                        )
                return selected

            print(
                f"  [screenspot_locate] verifier rejected {selected.get('name')} "
                f"at ({selected.get('cx')},{selected.get('cy')}): "
                f"verdict={verdict} suggestion={verifier.get('suggestion')} "
                f"clicked={verifier.get('clicked_visible_element', '')!r} "
                f"target={verifier.get('target_visible_element', '')!r} "
                f"evidence={verifier.get('evidence', '')!r}",
                file=__import__("sys").stderr,
            )
            if verdict == "no":
                active._remove_rejected_candidate(pool, selected)
            rejected.append(
                f"round {round_idx + 1}: rejected {selected.get('name')} at "
                f"({selected.get('cx')},{selected.get('cy')}): {verifier.get('evidence', '')}"
            )
            continue

        if action == "crop":
            _append_requested_crops(decision, img_path, img_w, img_h, pool, crop_paths, out_dir, round_idx)
            continue

        rejected.append(f"round {round_idx + 1}: controller failed or declined: {decision.get('reasoning', '')}")

    return None


def _selection_from_click_decision(
    decision: dict,
    pool: list[dict],
    img_w: int,
    img_h: int,
    has_crop_context: bool,
    config: ScreenSpotLocatorConfig,
) -> Optional[dict]:
    selected = None
    candidate_id = str(decision.get("candidate_id", "")).strip()
    if candidate_id:
        selected = active._candidate_by_id(pool, candidate_id)
    if selected:
        selected = active._centered_location(selected)
        selected.update({
            "name": selected.get("label") or selected.get("id") or "active_loop_candidate",
            "source": "screenspot_active_loop",
            "grounding_type": "active_loop_candidate",
            "active_confidence": float(decision.get("confidence", 0) or 0),
        })
        return selected

    try:
        cx = int(round(float(decision.get("x", 0))))
        cy = int(round(float(decision.get("y", 0))))
    except (TypeError, ValueError):
        return None
    if cx <= 0 or cy <= 0 or cx > img_w or cy > img_h:
        return None

    direct = {
        "id": "direct",
        "label": "direct_pixel",
        "name": "direct_pixel",
        "source": "screenspot_active_loop",
        "grounding_type": "active_loop_direct_pixel",
        "cx": cx,
        "cy": cy,
        "x": cx - 24,
        "y": cy - 24,
        "w": 48,
        "h": 48,
        "confidence": decision.get("confidence", 0.0),
    }
    return _snap_direct_click_to_candidate(direct, pool, config)


def _snap_direct_click_to_candidate(selected: dict, candidates: list[dict], config: ScreenSpotLocatorConfig) -> dict:
    cx = int(selected.get("cx", 0) or 0)
    cy = int(selected.get("cy", 0) or 0)
    best: Optional[tuple[float, dict]] = None
    for cand in candidates:
        box = active._candidate_box(cand)
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        ccx = int(round((box[0] + box[2]) / 2))
        ccy = int(round((box[1] + box[3]) / 2))
        inside = box[0] <= cx <= box[2] and box[1] <= cy <= box[3]
        dist2 = float((ccx - cx) ** 2 + (ccy - cy) ** 2)
        if not inside and dist2 > config.snap_px ** 2:
            continue
        label = (cand.get("label") or cand.get("name") or "").strip()
        source = str(cand.get("source") or cand.get("type") or "")
        source_bonus = -10000.0 if source in {"ocr", "text"} or label else 0.0
        inside_bonus = -20000.0 if inside else 0.0
        score = dist2 + source_bonus + inside_bonus
        if best is None or score < best[0]:
            best = (score, cand)
    if best is None:
        result = dict(selected)
        result["direct_unsnapped"] = True
        result["snap_reason"] = "no nearby detected OCR/component candidate for direct click"
        return result

    snapped = active._centered_location(best[1])
    snapped.update({
        "id": snapped.get("id") or "direct_snapped",
        "name": snapped.get("label") or snapped.get("name") or "direct_snapped",
        "source": "screenspot_active_loop",
        "grounding_type": "active_loop_direct_snapped_to_candidate",
        "active_confidence": selected.get("confidence", selected.get("active_confidence", 0.0)),
        "original_direct_click": [cx, cy],
        "snap_reason": "direct click snapped to nearest detected component center before verification",
    })
    return snapped


def _append_requested_crops(
    decision: dict,
    img_path: str,
    img_w: int,
    img_h: int,
    pool: list[dict],
    crop_paths: list[tuple[str, str]],
    out_dir: str,
    round_idx: int,
) -> None:
    regions = []
    for item in decision.get("regions", [])[:3]:
        bbox = item.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            regions.append({
                "name": item.get("name", f"round_{round_idx + 1}_region"),
                "bbox": active._clamp_box(bbox, img_w, img_h),
                "reasoning": item.get("reasoning", ""),
            })
    for region in regions:
        x1, y1, x2, y2 = region["bbox"]
        if x2 <= x1 or y2 <= y1:
            continue
        img = Image.open(img_path).convert("RGB")
        crop = img.crop((x1, y1, x2, y2))
        safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(region["name"]))[:60]
        crop_path = Path(out_dir) / f"screenspot_round{round_idx + 1}_{safe_name}.png"
        crop.save(crop_path)
        crop_paths.append((f"{region['name']} bbox={region['bbox']}", str(crop_path)))
        for cand in active._detect_region_candidates(img_path, region, out_dir):
            cand["id"] = f"c{len(pool)}"
            pool.append(cand)


def _add_direct_click_crop(
    img_path: str,
    selected: dict,
    pool: list[dict],
    crop_paths: list[tuple[str, str]],
    out_dir: str,
    img_w: int,
    img_h: int,
    round_idx: int,
    config: ScreenSpotLocatorConfig,
) -> None:
    cx = int(selected.get("cx", 0) or 0)
    cy = int(selected.get("cy", 0) or 0)
    half_w = config.direct_crop_width // 2
    half_h = config.direct_crop_height // 2
    bbox = active._clamp_box([cx - half_w, cy - half_h, cx + half_w, cy + half_h], img_w, img_h)
    region = {
        "name": f"rejected_direct_round{round_idx + 1}",
        "bbox": bbox,
        "reasoning": "inspection crop around rejected direct pixel",
    }
    x1, y1, x2, y2 = bbox
    img = Image.open(img_path).convert("RGB")
    crop = img.crop((x1, y1, x2, y2))
    crop_path = Path(out_dir) / f"screenspot_round{round_idx + 1}_rejected_direct.png"
    crop.save(crop_path)
    crop_paths.append((f"{region['name']} bbox={bbox}", str(crop_path)))
    for cand in active._detect_region_candidates(img_path, region, out_dir):
        cand["id"] = f"c{len(pool)}"
        pool.append(cand)


def _refine_direct_on_crop(
    task: str,
    target: str,
    img_path: str,
    selected: dict,
    runtime,
    out_dir: str,
    img_w: int,
    img_h: int,
    config: ScreenSpotLocatorConfig,
) -> Optional[dict]:
    cx = int(selected.get("cx", 0) or 0)
    cy = int(selected.get("cy", 0) or 0)
    half_w = config.refine_crop_width // 2
    half_h = config.refine_crop_height // 2
    x1, y1, x2, y2 = active._clamp_box([cx - half_w, cy - half_h, cx + half_w, cy + half_h], img_w, img_h)
    img = Image.open(img_path).convert("RGB")
    crop = img.crop((x1, y1, x2, y2))
    crop_path = Path(out_dir) / f"screenspot_refine_{os.getpid()}_{abs(hash((img_path, cx, cy)))}.png"
    crop.save(crop_path)
    context = f"""Task: {task}
Target: {target}
Original screenshot crop origin: ({x1}, {y1})
Initial proposed global click: ({cx}, {cy})

You are given a local crop around the proposed click. Choose the exact center
of the requested clickable target in ORIGINAL GLOBAL screenshot coordinates.
If the initial point is slightly above/below/left/right of the real target,
correct it. For split controls, choose the specific sub-control requested by
the target, not the neighboring label/status/toggle area.

Reply with ONLY JSON:
{{"x": 0, "y": 0, "target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}}"""
    try:
        reply = _runtime_exec(runtime, config, content=[
            {"type": "text", "text": context},
            {"type": "image", "path": str(crop_path)},
        ])
        parsed = parse_json(reply)
        rx = int(round(float(parsed.get("x", 0))))
        ry = int(round(float(parsed.get("y", 0))))
        confidence = float(parsed.get("confidence", 0) or 0)
    except Exception as exc:
        reraise_if_fatal(exc)
        return None
    if rx <= 0 or ry <= 0 or rx > img_w or ry > img_h:
        return None
    if abs(rx - cx) > half_w or abs(ry - cy) > half_h:
        return None
    refined = dict(selected)
    refined.update({
        "cx": rx,
        "cy": ry,
        "x": rx - 24,
        "y": ry - 24,
        "w": 48,
        "h": 48,
        "name": selected.get("name", "direct_pixel") + "_refined",
        "grounding_type": "active_loop_direct_crop_refined",
        "direct_refinement": {
            "input_point": [cx, cy],
            "crop_path": str(crop_path),
            "crop_box": [x1, y1, x2, y2],
            "target_visible_element": parsed.get("target_visible_element", ""),
            "confidence": confidence,
            "reasoning": parsed.get("reasoning", ""),
        },
    })
    return refined
