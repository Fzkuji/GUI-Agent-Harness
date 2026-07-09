#!/usr/bin/env python3
"""ScreenSpot-Pro × 阿里云 Token Plan 视觉模型 × 本 harness(迭代缩放,sspro_stack_zoom.yaml)。

用法: python run_sspro_aliyun.py <model> [shard] [shards]
  model 例: qwen3.7-plus / kimi-k2.7-code
key: ~/.openprogram/auth/aliyun-token-plan/key.txt(仓库外,不进 git)
端点: OpenAI 兼容 /chat/completions;image 块转 base64 data URL(>9MB 转 JPEG 防 413)。
输出: runs/sspro_aliyun/<model>/results[_s{shard}].jsonl;skip-existing 续跑。
"""
from __future__ import annotations

import base64
import glob
import io
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

ANN_DIR = HERE / "data" / "annotations"
IMG_DIR = HERE / "data" / "images"
BASE_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
KEY_FILE = Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt"
MAX_IMG_BYTES = 9 * 1024 * 1024   # 端点常见 10MB 限;超限降为 JPEG


def _img_data_url(path: str) -> str:
    raw = Path(path).read_bytes()
    mime = "image/png"
    if len(raw) > MAX_IMG_BYTES:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        raw = buf.getvalue()
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def make_call(api_key: str):
    import httpx
    # kimi/qwen 推理型视觉模型单次可超 4 分钟;380s 由 httpx 兜底成"瞬时错"重试,
    # runtime 死线在 runner 里放宽到 1200s,避免被判 permanent 炸死进程。
    client = httpx.Client(timeout=380)

    def call(content, model, response_format=None):
        parts = []
        for b in content:
            if b.get("type") == "text":
                parts.append({"type": "text", "text": b["text"]})
            elif b.get("type") == "image":
                parts.append({"type": "image_url",
                              "image_url": {"url": _img_data_url(b["path"])}})
        body = {"model": model, "messages": [{"role": "user", "content": parts}],
                "stream": False}
        r = client.post(f"{BASE_URL}/chat/completions", json=body,
                        headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        msg = r.json()["choices"][0]["message"]
        return msg.get("content") or ""

    return call


def main() -> int:
    from openprogram.agentic_programming.runtime import Runtime
    from gui_harness.planning.component_memory import detect_components
    from gui_harness.planning import active_localization, screenspot_locator
    from run_screenspot_pro import load_locator_config

    argv = sys.argv[1:]
    assert argv, "用法: run_sspro_aliyun.py <model> [shard] [shards]"
    model = argv[0]
    shard = int(argv[1]) if len(argv) >= 2 else 0
    shards = int(argv[2]) if len(argv) >= 3 else 1
    sharded = shards > 1

    api_key = KEY_FILE.read_text(encoding="utf-8").strip()
    rt = Runtime(call=make_call(api_key), model=model, max_retries=4)

    samples = []
    for af in sorted(ANN_DIR.glob("*.json")):
        samples += json.loads(af.read_text(encoding="utf-8"))
    samples.sort(key=lambda s: s["id"])

    outdir = REPO / "runs/sspro_aliyun" / model
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / (f"results_s{shard}.jsonl" if sharded else "results.jsonl")
    work = outdir / f"work_s{shard}"
    work.mkdir(parents=True, exist_ok=True)

    done = set()
    for df in glob.glob(str(outdir / "results*.jsonl")):
        for l in open(df, encoding="utf-8"):
            try:
                done.add(json.loads(l)["sample_id"])
            except Exception:
                pass

    import dataclasses
    cfg = load_locator_config(str(HERE / "configs" / "sspro_stack_zoom.yaml"))
    # 慢推理模型:runtime 死线放宽(httpx 380s 先到,超时按瞬时错重试而非 permanent)
    cfg = dataclasses.replace(cfg, runtime_timeout_s=1200)
    todo = [s for i, s in enumerate(samples)
            if s["id"] not in done and (not sharded or i % shards == shard)]
    print(f"SSPro aliyun [{model}]: {len(todo)} 待跑(总 {len(samples)},已完成 {len(done)}"
          f"{f', shard {shard}/{shards}' if sharded else ''})", flush=True)

    f = open(out, "a", encoding="utf-8")
    for i, s in enumerate(todo):
        img = IMG_DIR / f"{s['id']}.png"
        gt = s["bbox"]
        t0 = time.time()
        rec = {"sample_id": s["id"], "instruction": s["instruction"], "gt_bbox": gt,
               "group": s.get("group"), "ui_type": s.get("ui_type"), "model": model}
        try:
            if not img.exists():
                raise FileNotFoundError(f"{s['id']}.png")
            det = detect_components(str(img))
            cands = active_localization.build_candidates([], det["texts"], det["icons"])
            located = screenspot_locator.screenspot_locate(
                task=s["instruction"], target=s["instruction"], img_path=str(img),
                img_w=det["img_w"], img_h=det["img_h"], candidates=cands, runtime=rt,
                work_dir=str(work), config=cfg)
            if located:
                cx, cy = int(located["cx"]), int(located["cy"])
                rec["prediction_px"] = [cx, cy]
                rec["correctness"] = "correct" if (gt[0] <= cx <= gt[2] and gt[1] <= cy <= gt[3]) else "wrong"
                rec["location"] = {k: located.get(k) for k in ("name", "grounding_type")}
            else:
                rec["prediction_px"] = None
                rec["correctness"] = "wrong"
        except Exception as exc:
            # 只有额度/认证类才致命(停下来交给守护/cron 处置);超时、审查、瞬时
            # 网络错都记 error 行继续跑,不让单题炸死整个 runner。
            msg = str(exc).lower()
            if any(k in msg for k in ("quota", "insufficient", "余额", "额度",
                                       "invalid api key", "invalid_api_key", "unauthorized")):
                raise
            rec["prediction_px"] = None
            rec["correctness"] = "wrong"
            rec["error"] = {"type": exc.__class__.__name__, "message": str(exc)[:200]}
        rec["elapsed_s"] = round(time.time() - t0, 1)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(todo)}", flush=True)
    f.close()

    rows = {}
    for df in glob.glob(str(outdir / "results*.jsonl")):
        for l in open(df, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); rows[r["sample_id"]] = r
    ok = sum(r["correctness"] == "correct" for r in rows.values())
    print(f"\nSSPro [{model}]: {ok}/{len(rows)} = {ok/max(1,len(rows)):.1%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
