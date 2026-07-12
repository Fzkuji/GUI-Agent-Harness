#!/usr/bin/env python3
"""Claude 通道对照探针 v2:baseline50+abs_pixel 单发,走 claude.exe -p(Claude Code CLI)。

即 6 月 Meridian→Claude Code SDK 通道的忠实等价物:模型通过 Read 工具读图,
走 Claude Code 自己的图片预处理,而不是我们把原图 base64 直塞 API。
对照组:直连 API 同条件 30%。冒烟单题:直连偏 870px,本通道偏 85px。
用法: python probe_claude_cli.py [workers] [model]
输出: runs/sspro_baseline/claude47_cli.jsonl
"""
from __future__ import annotations
import json, subprocess, sys, glob, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from PIL import Image
from gui_harness.planning import coord_formats as cf

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
IDS_FILE = OUT / "baseline50_ids.json"
CLAUDE = (r"C:\Users\fzkuj\AppData\Roaming\npm\node_modules\@rynfar\meridian"
          r"\node_modules\@anthropic-ai\claude-code\bin\claude.exe")


def ask(model: str, prompt: str) -> str:
    p = subprocess.run(
        [CLAUDE, "-p", prompt, "--model", model, "--allowedTools", "Read"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=420, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        raise RuntimeError(f"claude rc={p.returncode}: {(p.stderr or '')[:120]}")
    return (p.stdout or "").strip()


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    model = sys.argv[2] if len(sys.argv) > 2 else "claude-opus-4-7"
    meta = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                meta[r["sample_id"]] = r
    ids = json.load(open(IDS_FILE))
    out_path = OUT / "claude47_cli.jsonl"
    done = set()
    if out_path.exists():
        for l in open(out_path, encoding="utf-8"):
            if l.strip():
                rr = json.loads(l)
                if "hit" in rr:
                    done.add(rr["sample_id"])
    todo = [s for s in ids if s not in done]

    def work(sid):
        r = meta[sid]
        gt = r["gt_bbox"]
        try:
            img = IMG_DIR / f"{sid}.png"
            W, H = Image.open(img).size
            prompt = (f"Read the image file at {img} (a {W}x{H} GUI screenshot). "
                      "Find the single UI element to click for this instruction: "
                      f"{r['instruction']}\n"
                      + cf.prompt_suffix("abs_pixel", W, H))
            t0 = time.time()
            resp = ask(model, prompt)
            p = cf.parse_point(resp, "abs_pixel", W, H)
            rec = {"sample_id": sid, "elapsed_s": round(time.time() - t0, 1)}
            if not p:
                rec.update(hit=False, raw=resp[:150])
            else:
                rec.update(pred=[p[0], p[1]],
                           hit=bool(gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3]))
            return rec
        except Exception as e:
            return {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:120]}"}

    recs = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, s) for s in todo]):
            recs.append(f.result())
            if len(recs) % 10 == 0:
                print(f"  progress {len(recs)}/{len(todo)}", flush=True)
    with open(out_path, "a", encoding="utf-8") as o:
        for rr in recs:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
    all_recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    done_r = [x for x in all_recs if "hit" in x]
    ok = sum(x["hit"] for x in done_r)
    print("[claude CLI-channel abs] %d/%d = %.0f%% (err=%d)  [对照 直连: 30%%]"
          % (ok, len(done_r), 100 * ok / max(1, len(done_r)),
             len(all_recs) - len(done_r)), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
