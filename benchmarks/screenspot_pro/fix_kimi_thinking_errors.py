#!/usr/bin/env python3
"""重跑 probe_kimi_thinking.py 里因基础设施问题(超时/413)出错的样本,替换掉错误条目,
拿到干净的、不受超时阈值污染的 thinking on/off 对比。
- 413(请求体过大):强制 JPEG 压缩,不管原图多大
- ReadTimeout:超时从 380s 提到 150s(合理上限,不无限等;仍失败的样本保留为 error,如实报告)
逐条落盘(每条重试立即写回文件),中途中断不丢已完成的部分。
"""
from __future__ import annotations
import base64, glob, io, json, sys, time
from pathlib import Path
from PIL import Image
import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
from gui_harness.planning import coord_formats as cf

IMG_DIR = HERE / "data" / "images"
OUT = REPO / "runs" / "sspro_baseline"
KEY = (Path.home() / ".openprogram/auth/aliyun-token-plan/key.txt").read_text(encoding="utf-8").strip()
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.6"
FMT = "frac01"
_client = httpx.Client(timeout=150)  # 380 -> 150,合理上限,不无限等


def data_url_force_jpeg(path):
    im = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    raw = buf.getvalue()
    print(f"  {path.name}: compressed to {len(raw)/1024/1024:.2f}MB (JPEG)", flush=True)
    return f"data:image/jpeg;base64,{base64.b64encode(raw).decode()}"


def ask(path, instr, thinking):
    prompt = ("This is a GUI screenshot. Find the single UI element to click for the "
              f"instruction, then give its click point.\nInstruction: {instr}\n"
              + cf.prompt_suffix(FMT, 0, 0))
    body = {"model": MODEL, "stream": False, "enable_thinking": thinking,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url_force_jpeg(path)}}]}]}
    r = _client.post(f"{BASE}/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {KEY}"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:140]}")
    return r.json()["choices"][0]["message"].get("content") or ""


def rewrite_file(path, rows):
    with open(path, "w", encoding="utf-8") as o:
        for rr in rows:
            o.write(json.dumps(rr, ensure_ascii=False) + "\n")
            o.flush()


def main():
    m3 = {}
    for p in glob.glob(str(REPO / "runs/sspro_stack/m3_zoom/*.jsonl")):
        if p.endswith(".errors.jsonl"):
            continue
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                m3[r["sample_id"]] = r

    for thinking, tag in [(True, "on"), (False, "off")]:
        path = OUT / f"kimi_thinking_{tag}.jsonl"
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        err_idx = [i for i, r in enumerate(rows) if "error" in r]
        print(f"[{tag}] {len(err_idx)} 个待重试", flush=True)

        for i in err_idx:
            sid = rows[i]["sample_id"]
            print(f"[{tag}] retrying {sid} (was: {rows[i]['error'][:60]})", flush=True)
            r = m3[sid]
            gt = r["gt_bbox"]
            try:
                im = Image.open(IMG_DIR / f"{sid}.png")
                W, H = im.size
                t0 = time.time()
                resp = ask(IMG_DIR / f"{sid}.png", r["instruction"], thinking)
                dt = time.time() - t0
                p = cf.parse_point(resp, FMT, W, H)
                hit = bool(p and gt[0] <= p[0] <= gt[2] and gt[1] <= p[1] <= gt[3])
                rows[i] = {"sample_id": sid, "hit": hit, "elapsed_s": round(dt, 1)}
                print(f"  -> recovered: hit={hit} elapsed={dt:.1f}s", flush=True)
            except Exception as e:
                print(f"  -> STILL FAILS: {type(e).__name__}: {str(e)[:100]}", flush=True)
                rows[i] = {"sample_id": sid, "error": f"{type(e).__name__}: {str(e)[:200]}"}
            rewrite_file(path, rows)  # 每条重试后立即落盘,不丢进度

        done = [x for x in rows if "hit" in x]
        err = [x for x in rows if "error" in x]
        ok = sum(x["hit"] for x in done)
        avg_t = sum(x["elapsed_s"] for x in done) / max(1, len(done))
        print(f"[kimi thinking={tag:3s}] FINAL: {ok}/{len(done)} = {ok/max(1,len(done)):.0%}  "
              f"avg={avg_t:.1f}s/call  (+{len(err)}err remaining)\n", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
