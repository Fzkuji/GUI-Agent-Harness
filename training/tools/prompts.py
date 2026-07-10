"""Training-time prompts for the GUI-Lens zoom SFT data.

The whole point of SFT is to internalise the *inference-time* behaviour, so the
training prompts must match the harness's iterative-zoom prompts exactly.
This module imports the rule blocks straight from
``gui_harness.planning.screenspot_locator`` when the repo (and its deps) are
importable, and falls back to verbatim embedded copies otherwise — e.g. on a
training box that only has this ``training/`` folder plus LLaMA-Factory.

Coordinate convention: everything is NORMALIZED [0,1000] integers relative to
the DISPLAYED image (Qwen3-VL's native grounding convention — worth ~+11pt on
single-shot vs pixel coords, plus ~+10pt from the point_2d wrapper; see the
comments above _NORM_COORD_CROP in screenspot_locator.py).
"""
from __future__ import annotations

# ── Try the harness first: byte-identical prompts, zero drift ──────────────
try:  # pragma: no cover - environment-dependent
    from gui_harness.planning.screenspot_locator import (  # type: ignore
        _CROP_DECISION_RULES as CROP_DECISION_RULES,
        _FINAL_CLICK_RULES as FINAL_CLICK_RULES,
        _NORM_COORD_CROP as NORM_COORD_CROP,
        _NORM_COORD_CLICK as NORM_COORD_CLICK,
    )
    PROMPT_SOURCE = "gui_harness"
except Exception:  # noqa: BLE001 - any import failure → embedded fallback
    PROMPT_SOURCE = "embedded"

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

    CROP_DECISION_RULES = (
        _CROP_DECISION_RULES_INTRO + "\n\n" + _CROP_DECISION_RULES_BODY
    )

    FINAL_CLICK_RULES = """Choose the exact center of the requested clickable target. Use the upscaled
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

    NORM_COORD_CROP = (
        "COORDINATE FORMAT OVERRIDE: express the bbox as NORMALIZED integers in [0,1000] "
        "relative to the DISPLAYED crop image — x1,y1,x2,y2 each an int in [0,1000] "
        "(0=left/top edge, 1000=right/bottom edge), NOT pixels. Example: [312, 420, 553, 604]."
    )
    NORM_COORD_CLICK = (
        "COORDINATE FORMAT OVERRIDE: give the click point as a \"point_2d\" array of two "
        "NORMALIZED integers in [0,1000] relative to the DISPLAYED crop image (0=left/top "
        "edge, 1000=right/bottom edge), NOT pixels. Add a \"point_2d\": [x, y] field to the "
        "JSON, e.g. \"point_2d\": [470, 630]."
    )


# ── Combined rule prefixes actually used in training samples ───────────────
# Mirrors screenspot_locator's cache layout with coords_normalized=True:
# rules block + "\n\n" + NORM override, followed by the dynamic context text.
CROP_RULES_NORM = CROP_DECISION_RULES + "\n\n" + NORM_COORD_CROP
CLICK_RULES_NORM = FINAL_CLICK_RULES + "\n\n" + NORM_COORD_CLICK

# JSON reminder tails (cache-layout `tail`, reasoning_first=False variant).
CROP_JSON_TAIL = (
    "Reply with ONLY JSON:\n"
    '{"action": "crop|final|recrop", "bbox": [x1, y1, x2, y2], '
    '"target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}'
)
CLICK_JSON_TAIL = (
    "Reply with ONLY JSON:\n"
    '{"action": "click|recrop", "candidate_id": "z0 or empty", "x": 0, "y": 0, '
    '"target_visible_element": "...", "confidence": 0.0, "reasoning": "..."}'
)

# Staged crop guidance (verbatim from _iterative_stage_guidance, staged mode).
STAGE_GUIDANCE = {
    0: (
        "Stage 1: screen/window selection. If the screenshot contains multiple "
        "apps, windows, panes, or documents, crop to the relevant app/window or "
        "broad screen region first. Do not jump directly to a tiny toolbar icon, "
        "button, or text label."
    ),
    1: (
        "Stage 2: region selection inside the chosen app/window. Crop to the "
        "relevant page, dialog, ribbon/toolbar, sidebar, canvas area, bottom "
        "panel, or functional section. Keep competing sections visible if the "
        "instruction is still ambiguous."
    ),
    2: (
        "Stage 3: control-group selection. Crop to the local group containing "
        "the target and nearby alternatives or labels needed to disambiguate it."
    ),
}


def stage_guidance(round_idx: int) -> str:
    return STAGE_GUIDANCE.get(
        round_idx,
        "Stage 4+: fine refinement. Crop closer only after the app/window, "
        "section, and local control group are already unambiguous.",
    )


def crop_dynamic_block(
    *,
    task: str,
    target: str,
    img_w: int,
    img_h: int,
    crop_box: list[int],
    display_scale: float,
    round_idx: int,
    total_rounds: int,
    stage_idx: int,
    history_lines: str = "(none)",
) -> str:
    """Per-round dynamic context, mirroring _iterative_zoom_locate's layout."""
    return f"""Task: {task}
Target: {target}
Original screenshot size: {img_w}x{img_h}
Current crop in original coordinates: {crop_box}
This displayed crop is scaled by {display_scale:.4f} from original pixels.
Round: {round_idx + 1}/{total_rounds}
Attempt: 1/4
Committed crop stage: {stage_idx + 1}
Staged crop guidance:
{stage_guidance(round_idx)}

Previous crop decisions:
{history_lines}

Rejected crop attempts from this same current crop:
(none)

Detected OCR/component candidates inside this crop, shown in displayed-crop
coordinates:
(none)

{CROP_JSON_TAIL}"""


def click_dynamic_block(
    *,
    task: str,
    target: str,
    img_w: int,
    img_h: int,
    crop_box: list[int],
    display_scale: float,
) -> str:
    """Final-click dynamic context (upscaled final crop)."""
    return f"""Task: {task}
Target: {target}
Original screenshot size: {img_w}x{img_h}
Final crop in original coordinates: {crop_box}
This displayed crop is scaled by {display_scale:.4f} from original pixels.

Detected OCR/component candidates inside this crop, shown in displayed-crop
coordinates:
(none)

{CLICK_JSON_TAIL}"""
