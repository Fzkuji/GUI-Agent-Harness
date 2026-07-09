"""Per-model coordinate output formats for GUI grounding.

Different vision models are trained on different coordinate conventions, and
using the wrong one costs 20+ points of accuracy — this was discovered
empirically on ScreenSpot-Pro (see benchmarks/screenspot_pro/
COORDINATE_FORMAT_FINDINGS.md for the data). This module is the single
source of truth for that mapping: one prompt-instruction generator and one
parser per format, reused by every runner/probe instead of each one
re-implementing its own regex.

Confirmed via single-shot ablation (baseline50, ScreenSpot-Pro):
  gpt-5.5        -> "abs_pixel"     (62%; all normalized variants are worse)
  qwen3.7-plus   -> "point2d_1000"  (79%; matches Qwen's native point_2d/[0,1000] training)
  kimi-k2.6      -> "frac01"        (60%; kimi's outputs drift toward [0,1] even
                                     when told to use [0,1000] — that drift IS the signal)
"""
from __future__ import annotations

import re
from typing import Optional

FORMAT_IDS = ("abs_pixel", "frac01", "xy1000", "point2d_1000")

_INSTRUCTIONS = {
    "abs_pixel": (
        'The screenshot is {W}x{H} pixels. Output ONLY JSON {{"x": <int 0-{W}>, '
        '"y": <int 0-{H}>}} — the ABSOLUTE PIXEL center of the element to click.'
    ),
    "frac01": (
        'Output ONLY JSON {{"x": <float 0-1>, "y": <float 0-1>}} — the NORMALIZED '
        "center (fractions of image width/height, top-left origin)."
    ),
    "xy1000": (
        'Output ONLY JSON {{"x": <int 0-1000>, "y": <int 0-1000>}} — the click point '
        "normalized to [0,1000] (0=left/top edge, 1000=right/bottom edge)."
    ),
    "point2d_1000": (
        'Output ONLY JSON {{"point_2d": [x, y]}} where x and y are integers in '
        "[0, 1000] normalized to the image (0=left/top edge, 1000=right/bottom edge)."
    ),
}

_XY_RE = re.compile(r'"x"\s*:\s*(-?\d+(?:\.\d+)?).*?"y"\s*:\s*(-?\d+(?:\.\d+)?)', re.S)
_POINT2D_RE = re.compile(r'point_2d"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)')
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def prompt_suffix(fmt: str, img_w: int, img_h: int) -> str:
    """Coordinate-format instruction line to append to a grounding prompt."""
    if fmt not in _INSTRUCTIONS:
        raise ValueError(f"unknown coord format {fmt!r}; choices: {FORMAT_IDS}")
    return _INSTRUCTIONS[fmt].format(W=img_w, H=img_h)


def _extract_raw_xy(text: str, fmt: str) -> Optional[tuple[float, float]]:
    """Pull two numbers out of a (possibly malformed) model reply."""
    if fmt == "point2d_1000":
        m = _POINT2D_RE.search(text)
        if m:
            return float(m.group(1)), float(m.group(2))
    m = _XY_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    nums = _NUM_RE.findall(text)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None


def parse_point(text: str, fmt: str, img_w: int, img_h: int) -> Optional[tuple[float, float]]:
    """Parse a model reply into ORIGINAL-image pixel coordinates, or None.

    Models sometimes drift off the requested format (a Qwen-family model told
    to use pixels may slip into a [0,1] fraction; a model told to normalize
    may just emit raw pixels). The scale-detection heuristic below absorbs
    that drift instead of failing, EXCEPT for "abs_pixel": a real pixel
    coordinate on a wide screenshot can legitimately be under 1000 (e.g. x=519
    on a 3840-wide image), so abs_pixel only reinterprets an unambiguous
    fraction slip (both values <=1.5), never a <=1000 value.
    """
    raw = _extract_raw_xy(text, fmt)
    if raw is None:
        return None
    x, y = raw
    if fmt == "abs_pixel":
        if x <= 1.5 and y <= 1.5:
            return x * img_w, y * img_h
        return x, y
    # normalized-family formats (frac01 / xy1000 / point2d_1000)
    if x <= 1.5 and y <= 1.5:
        return x * img_w, y * img_h
    if x <= 1000 and y <= 1000:
        return x / 1000.0 * img_w, y / 1000.0 * img_h
    return x, y  # model ignored the format and gave raw pixels anyway
