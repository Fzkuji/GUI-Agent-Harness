#!/usr/bin/env python3
"""验证 coords_normalized 开关对 qwen 完整 harness 的效果(同样本 on vs off)。

在 baseline50 的前 N 题上跑完整迭代缩放 harness,coords_normalized 由参数切换。
两次跑(on/off)用不同 work_dir/输出文件,可作为两个进程并行。
用法: python probe_harness_norm.py <on|off> [N] [workers]
"""
from __future__ import annotations
import dataclasses, glob, json, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
KEY_FILE = Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt"
MODEL = "qwen3.7-plus"


def main():
    from run_sspro_aliyun import make_call
    from openprogram.agentic_programming.runtime import Runtime
    from gui_harness.planning.component_memory import detect_components
    from gui_harness.planning import active_localization, screenspot_locator
    from run_screenspot_pro import load_locator_config

    mode = sys.argv[1]  # on|off
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    normalized = mode == "on"

    m3 = {}
    for f in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if f.endswith(".errors.jsonl"):
            continue
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); m3[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))[:N]

    api_key = KEY_FILE.read_text(encoding="utf-8").strip()
    rt = Runtime(call=make_call(api_key), model=MODEL, max_retries=4)
    cfg = load_locator_config(str(HERE / "configs" / "sspro_stack_zoom.yaml"))
    cfg = dataclasses.replace(cfg, runtime_timeout_s=1200, coords_normalized=normalized)

    work = OUT / f"harness_norm_work_{mode}"; work.mkdir(parents=True, exist_ok=True)
    out = OUT / f"harness_norm_{mode}.jsonl"
    done = set()
    if out.exists():
        for l in open(out, encoding="utf-8"):
            if l.strip():
                done.add(json.loads(l)["sample_id"])
    f = open(out, "a", encoding="utf-8")
    print(f"[{mode}] coords_normalized={normalized}  {len(ids)} 题(已完成{len(done)})", flush=True)
    for i, sid in enumerate(ids):
        if sid in done:
            continue
        r = m3[sid]; gt = r["gt_bbox"]; img = IMG_DIR / f"{sid}.png"
        rec = {"sample_id": sid, "group": r.get("group"), "gt_bbox": gt,
               "harness_correct_m3": r["correctness"] == "correct"}
        t0 = time.time()
        try:
            det = detect_components(str(img))
            cands = active_localization.build_candidates([], det["texts"], det["icons"])
            loc = screenspot_locator.screenspot_locate(
                task=r["instruction"], target=r["instruction"], img_path=str(img),
                img_w=det["img_w"], img_h=det["img_h"], candidates=cands, runtime=rt,
                work_dir=str(work), config=cfg)
            if loc:
                cx, cy = int(loc["cx"]), int(loc["cy"])
                rec["pred"] = [cx, cy]
                rec["hit"] = bool(gt[0] <= cx <= gt[2] and gt[1] <= cy <= gt[3])
            else:
                rec["pred"] = None; rec["hit"] = False
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("quota", "insufficient", "余额", "额度", "unauthorized")):
                raise
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"; rec["hit"] = False
        rec["elapsed_s"] = round(time.time() - t0, 1)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
        nh = sum(1 for _ in [1])  # placeholder
        print(f"  [{mode}] {i+1}/{len(ids)} {sid[:20]} hit={rec.get('hit')} {rec['elapsed_s']}s", flush=True)
    f.close()

    rows = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
    ok = sum(x.get("hit") for x in rows)
    print(f"\n[{mode}] harness coords_normalized={normalized}: {ok}/{len(rows)} = {ok/max(1,len(rows)):.0%}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
