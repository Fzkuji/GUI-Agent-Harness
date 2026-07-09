#!/usr/bin/env python3
"""ScreenSpot-Pro × 官方 Codex CLI(gpt-5.5)——纯净隔离 CODEX_HOME,不碰用户真实 ~/.codex。

两种模式(GUI_HARNESS_CODEX_MODE):
  ss    单发基线:reasoning=none,sandbox read-only,不用工具 → 原始模型一次性出坐标
  agent codex 框架:reasoning=high,sandbox workspace-write(每题独立 scratch,拷入图片)
        → 让 codex 用它自己的 agent 能力(可写 python 裁图/放大/迭代)后出坐标

判分:point-in-bbox(与 harness 一致)。分片:GUI_HARNESS_SSPRO_SHARDS/SHARD。skip-existing。
输出:runs/sspro_codex/{mode}/results[_s{shard}].jsonl
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
ANN_DIR = HERE / "data" / "annotations"
IMG_DIR = HERE / "data" / "images"
CODEX = r"C:\Users\fzkuj\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"
PRISTINE_AUTH = Path(r"C:\Users\fzkuj\.codex\auth.json")  # 真实登录凭证(只读拷贝)
SCHEMA = REPO / "runs/sspro_codex/schema.json"

# 最纯净:prompt = SSPro 原始指令,别的一律不给(不提尺寸/输出/工具/裁图)。
# 图经 -i 附上、agent 模式图还在可写工作区里(codex 若自发裁图放大自己够得到),
# 但我们零提示。输出靠 --output-schema 强制成 {x,y}。ss 与 agent 用完全相同的 prompt,
# 唯一区别是 reasoning effort(none vs high)与沙箱/工具 —— 只测脚手架差异。
_PROMPT_SS = "{instr}"
_PROMPT_AGENT = "{instr}"


def run_codex(mode: str, img: Path, w: int, h: int, instr: str, scratch: Path, home: Path = None) -> dict:
    # 每题一次性 CODEX_HOME:只放 auth,codex 无从加载/累积 memory/goals/skills → 零跨样本污染
    home = scratch / "codex_home"
    home.mkdir(parents=True, exist_ok=True)
    shutil.copy(PRISTINE_AUTH, home / "auth.json")
    env = dict(os.environ)
    env["CODEX_HOME"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    last = scratch / "last.json"
    # 注意:绝不用 --dangerously-bypass-approvals-and-sandbox。SSPro 指令是"click X"
    # 形式,全权模式下 codex 会真的去点用户鼠标(实测发生过)。codex exec 默认
    # approval=never,配 -s 沙箱即可:agent 限工作区、ss 只读,都碰不到真实系统。
    common = [CODEX, "exec", "--ignore-user-config", "-m", "gpt-5.5",
              "--skip-git-repo-check",
              "--ephemeral", "--output-schema", str(SCHEMA), "-o", str(last),
              "-i", str(img)]
    if mode == "ss":
        prompt = _PROMPT_SS.format(w=w, h=h, instr=instr)
        cmd = common + ["-c", "model_reasoning_effort=\"none\"", "-s", "read-only", prompt]
        cwd = str(scratch)
    else:  # agent
        shutil.copy(img, scratch / "shot.png")
        prompt = _PROMPT_AGENT.format(w=w, h=h, instr=instr)
        cmd = common + ["-c", "model_reasoning_effort=\"high\"", "-s", "workspace-write",
                        "-C", str(scratch), prompt]
        cwd = str(scratch)
    proc = subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=1200)
    if not last.exists():
        return {"error": f"no output (rc={proc.returncode}): {proc.stderr[-200:] or proc.stdout[-200:]}"}
    try:
        d = json.loads(last.read_text(encoding="utf-8"))
        return {"x": int(d["x"]), "y": int(d["y"])}
    except Exception as e:
        return {"error": f"parse: {e}; raw={last.read_text(encoding='utf-8')[:120]}"}


def main() -> int:
    # argv 优先(便于守护按命令行区分 mode/shard),回退到 env
    argv = sys.argv[1:]
    mode = (argv[0] if len(argv) >= 1 else os.environ.get("GUI_HARNESS_CODEX_MODE", "ss")).strip().lower()
    assert mode in {"ss", "agent"}, mode
    shard = int(argv[1]) if len(argv) >= 2 else int(os.environ.get("GUI_HARNESS_SSPRO_SHARD", "0") or "0")
    shards = int(argv[2]) if len(argv) >= 3 else int(os.environ.get("GUI_HARNESS_SSPRO_SHARDS", "1") or "1")
    sharded = shards > 1 and 0 <= shard < shards

    samples = []
    for af in sorted(ANN_DIR.glob("*.json")):
        samples += json.loads(af.read_text(encoding="utf-8"))
    samples.sort(key=lambda s: s["id"])

    outdir = REPO / "runs/sspro_codex" / mode
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / (f"results_s{shard}.jsonl" if sharded else "results.jsonl")
    scratch_root = REPO / "runs/sspro_codex" / mode / f"scratch_s{shard}"
    scratch_root.mkdir(parents=True, exist_ok=True)

    done = set()
    for df in glob.glob(str(outdir / "results*.jsonl")):
        for l in open(df, encoding="utf-8"):
            try:
                done.add(json.loads(l)["sample_id"])
            except Exception:
                pass

    todo = [s for i, s in enumerate(samples)
            if s["id"] not in done and (not sharded or i % shards == shard)]
    print(f"SSPro codex [{mode}]: {len(todo)} 待跑(总 {len(samples)},已完成 {len(done)}"
          f"{f', shard {shard}/{shards}' if sharded else ''})", flush=True)

    f = open(out, "a", encoding="utf-8")
    for i, s in enumerate(todo):
        img = IMG_DIR / f"{s['id']}.png"
        w, h = s["img_size"]
        gt = s["bbox"]
        scratch = scratch_root / s["id"]
        scratch.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        rec = {"sample_id": s["id"], "instruction": s["instruction"], "gt_bbox": gt,
               "group": s.get("group"), "ui_type": s.get("ui_type"), "mode": mode}
        try:
            if not img.exists():
                raise FileNotFoundError(s["img_filename"])
            r = run_codex(mode, img, w, h, s["instruction"], scratch)
            if "error" in r:
                rec["prediction_px"] = None
                rec["correctness"] = "wrong"
                rec["error"] = {"message": r["error"]}
            else:
                x, y = r["x"], r["y"]
                rec["prediction_px"] = [x, y]
                rec["correctness"] = "correct" if (gt[0] <= x <= gt[2] and gt[1] <= y <= gt[3]) else "wrong"
        except Exception as exc:
            rec["prediction_px"] = None
            rec["correctness"] = "wrong"
            rec["error"] = {"type": exc.__class__.__name__, "message": str(exc)[:200]}
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
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
    print(f"\nSSPro codex [{mode}]: {ok}/{len(rows)} = {ok/max(1,len(rows)):.1%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
