#!/usr/bin/env python3
"""Unified per-model native single-shot GUI grounding runner for ScreenSpot-Pro.

Consolidates what used to be one-off probe_*_format.py scripts into a single,
config-driven runner. Behavior for a given model comes ENTIRELY from its
ModelProfile (model_profiles.py) — coordinate format, OCR/icon-detector
hints, and (for Qwen-family models) the endpoint's high-resolution flag.
No per-model code branches here.

Only supports pipeline="native_single_shot" profiles. Models with
pipeline="harness" (currently gpt-5.5) should keep using
run_screenspot_pro.py / run_sspro_aliyun.py's full iterative-zoom pipeline.

Usage: python run_sspro_native.py <model> [--n N] [--workers W] [--shard S --shards T]
  model must have a ModelProfile in model_profiles.py.
Output schema matches run_sspro_aliyun.py's results.jsonl (drop-in compatible
with existing accuracy/analysis scripts):
  runs/sspro_native/<model>/results[_s{shard}].jsonl
"""
from __future__ import annotations

import argparse
import base64
import glob
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from PIL import Image

from gui_harness.planning import coord_formats
from model_profiles import get_profile

ANN_DIR = HERE / "data" / "annotations"
IMG_DIR = HERE / "data" / "images"
ALIYUN_BASE_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
ALIYUN_KEY_FILE = Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt"
MAX_IMG_BYTES = 9 * 1024 * 1024


def _img_data_url(path: Path) -> str:
    raw = path.read_bytes()
    mime = "image/png"
    if len(raw) > MAX_IMG_BYTES:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        raw = buf.getvalue()
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _make_aliyun_call(model: str, hires: bool):
    import httpx
    api_key = ALIYUN_KEY_FILE.read_text(encoding="utf-8").strip()
    client = httpx.Client(timeout=380)

    def call(prompt: str, img_path: Path) -> str:
        body = {
            "model": model,
            "stream": False,
            "enable_thinking": False,  # 2x2 消融(22题难样本): thinking关 平均48% > thinking开 30%
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _img_data_url(img_path)}},
            ]}],
        }
        if hires:
            body["vl_high_resolution_images"] = True
        r = client.post(f"{ALIYUN_BASE_URL}/chat/completions", json=body,
                        headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        return r.json()["choices"][0]["message"].get("content") or ""

    return call


ANTHROPIC_MAX_IMG_BYTES = 4_500_000  # API hard limit 5MB/image (HTTP 400 above it)


def _shrink_for_anthropic(img_path: Path) -> Path:
    """Re-encode >4.5MB PNGs to JPEG (same resolution) so Anthropic accepts them.
    3 baseline50 macos PNGs are 8.6-16MB and fail deterministically otherwise."""
    if img_path.stat().st_size <= ANTHROPIC_MAX_IMG_BYTES:
        return img_path
    cache = img_path.parent.parent / "images_jpeg_cache"
    cache.mkdir(exist_ok=True)
    out = cache / (img_path.stem + ".jpg")
    if not out.exists() or out.stat().st_size == 0:
        im = Image.open(img_path).convert("RGB")
        for quality in (92, 85, 75, 60):
            im.save(out, "JPEG", quality=quality)
            if out.stat().st_size <= ANTHROPIC_MAX_IMG_BYTES:
                break
    return out


def _make_openprogram_call(provider: str, model: str):
    from gui_harness.openprogram_compat import create_runtime
    rt = create_runtime(provider=provider, model=model, max_retries=3)

    def call(prompt: str, img_path: Path) -> str:
        if provider == "claude-code":
            img_path = _shrink_for_anthropic(img_path)
        content = [{"type": "text", "text": prompt}, {"type": "image", "path": str(img_path)}]
        return rt.exec(content=content, timeout_s=150) or ""

    return call


def _build_hint_block(img_path: Path, coord_format: str) -> str:
    """OCR/icon-detector candidates as plain-text grounding evidence.
    Universally positive across every model tested (GPT +16pt, Qwen +26pt),
    at zero extra API calls."""
    from gui_harness.planning.component_memory import detect_components
    from gui_harness.planning import active_localization

    det = detect_components(str(img_path))
    W, H = det["img_w"], det["img_h"]
    cands = active_localization.build_candidates([], det["texts"], det["icons"])
    lines = []
    for c in cands[:120]:
        x, y, w, h = c.get("x"), c.get("y"), c.get("w"), c.get("h")
        if None in (x, y, w, h):
            continue
        label = str(c.get("label") or c.get("text") or c.get("type") or "element")[:40]
        if coord_format == "abs_pixel":
            box = f"({int(x)},{int(y)},{int(x + w)},{int(y + h)})"
        else:
            box = (f"({int(x / W * 1000)},{int(y / H * 1000)},"
                   f"{int((x + w) / W * 1000)},{int((y + h) / H * 1000)})")
        lines.append(f'- "{label}" @ {box}')
    if not lines:
        return ""
    return ("\nDetected UI elements (OCR + icon detector) as grounding evidence — the "
            "target is usually one of these, but you may click elsewhere if none fits:\n"
            + "\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--n", type=int, default=0, help="0 = all samples")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    args = ap.parse_args()

    profile = get_profile(args.model)
    if profile.pipeline != "native_single_shot":
        raise SystemExit(
            f"{args.model} has pipeline={profile.pipeline!r}, not native_single_shot. "
            f"Use run_screenspot_pro.py / run_sspro_aliyun.py's harness pipeline instead."
        )

    call = (_make_aliyun_call(args.model, profile.hires) if profile.provider == "aliyun"
            else _make_openprogram_call(profile.provider, args.model))

    samples = []
    for af in sorted(ANN_DIR.glob("*.json")):
        samples += json.loads(af.read_text(encoding="utf-8"))
    samples.sort(key=lambda s: s["id"])
    if args.shards > 1:
        samples = [s for i, s in enumerate(samples) if i % args.shards == args.shard]
    if args.n > 0:
        samples = samples[: args.n]

    outdir = REPO / "runs" / "sspro_native" / args.model
    outdir.mkdir(parents=True, exist_ok=True)
    suffix = f"_s{args.shard}" if args.shards > 1 else ""
    out_path = outdir / f"results{suffix}.jsonl"
    done = set()
    if out_path.exists():
        for l in open(out_path, encoding="utf-8"):
            if l.strip():
                try:
                    done.add(json.loads(l)["sample_id"])
                except Exception:
                    pass
    todo = [s for s in samples if s["id"] not in done]
    print(f"[{args.model}] native_single_shot: {len(todo)} 待跑(已完成 {len(done)}, "
          f"format={profile.coord_format}, hires={profile.hires}, hints={profile.use_hints}, "
          f"confirmed={profile.confirmed})", flush=True)

    out_f = open(out_path, "a", encoding="utf-8")

    def work(s):
        img_path = IMG_DIR / f"{s['id']}.png"
        gt = s["bbox"]
        rec = {"sample_id": s["id"], "instruction": s["instruction"], "gt_bbox": gt,
               "group": s.get("group"), "ui_type": s.get("ui_type"), "model": args.model}
        t0 = time.time()
        try:
            im = Image.open(img_path)
            W, H = im.size
            hint = _build_hint_block(img_path, profile.coord_format) if profile.use_hints else ""
            prompt = (
                "This is a GUI screenshot. Find the single UI element to click for the "
                f"instruction, then give its click point.\nInstruction: {s['instruction']}\n"
                + hint + "\n" + coord_formats.prompt_suffix(profile.coord_format, W, H)
            )
            resp = call(prompt, img_path)
            pt = coord_formats.parse_point(resp, profile.coord_format, W, H)
            if pt is None:
                rec["prediction_px"] = None
                rec["correctness"] = "wrong"
            else:
                cx, cy = int(pt[0]), int(pt[1])
                rec["prediction_px"] = [cx, cy]
                rec["correctness"] = ("correct" if gt[0] <= cx <= gt[2] and gt[1] <= cy <= gt[3]
                                      else "wrong")
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("quota", "insufficient", "余额", "额度",
                                       "invalid api key", "invalid_api_key", "unauthorized")):
                raise
            rec["prediction_px"] = None
            rec["correctness"] = "wrong"
            rec["error"] = {"type": exc.__class__.__name__, "message": str(exc)[:200]}
        rec["elapsed_s"] = round(time.time() - t0, 1)
        return rec

    n_done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, s) for s in todo]
        for fut in as_completed(futs):
            rec = fut.result()
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            n_done += 1
            if n_done % 20 == 0:
                print(f"  {n_done}/{len(todo)}", flush=True)
    out_f.close()

    rows = {}
    for df in glob.glob(str(outdir / "results*.jsonl")):
        for l in open(df, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                rows[r["sample_id"]] = r
    ok = sum(r["correctness"] == "correct" for r in rows.values())
    print(f"\n[{args.model}] native_single_shot: {ok}/{len(rows)} = {ok/max(1,len(rows)):.1%}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
