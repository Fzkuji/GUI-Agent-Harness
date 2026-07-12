#!/usr/bin/env python3
"""SSPro 300 切片的臂驱动:--arm prefetch|single|zoom。

  prefetch:顺序确保切片所有标注+图片已下载(避免并发下载竞争)。
  single  :单次定位臂(生产 Phase-3 路径,--app-name sspro_single,control 惯例)。
  zoom    :迭代缩放臂(--app-name screenspot_pro --config sspro_stack_zoom.yaml)。

按 annotation 分组,ThreadPool 并发 3,逐文件批量 --indexes,--skip-existing 续跑。
输出 runs/sspro_stack/{arm}/<ann_stem>.jsonl。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
PY = sys.executable

DEFAULT_MANIFEST = HERE / "runs/sspro_slice/slice_manifest.json"
MANIFEST = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
OUT_BASE = REPO / "runs" / "sspro_stack"


def run_annotation(arm: str, ann: str, indexes: str,
                   provider: str, model: str, out_subdir: str,
                   config: str = "sspro_stack_zoom.yaml") -> tuple[str, int, int]:
    stem = ann[:-5]
    out = OUT_BASE / out_subdir / f"{stem}.jsonl"
    work = OUT_BASE / out_subdir / "work" / stem
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(HERE / "run_screenspot_pro.py"),
           "--annotation", ann, "--indexes", indexes,
           "--output", str(out), "--work-dir", str(work),
           "--provider", provider, "--model", model,
           "--runtime-retries", "4", "--retry-provider-errors", "2",
           "--exec-timeout-s", "300",
           "--download-timeout-s", "120", "--download-retries", "5",
           "--skip-existing"]
    if arm == "zoom":
        cfg_path = config if Path(config).is_absolute() else str(HERE / "configs" / config)
        cmd += ["--app-name", "screenspot_pro", "--config", cfg_path]
    else:
        cmd += ["--app-name", "sspro_single"]
    subprocess.run(cmd, cwd=REPO, text=True, encoding="utf-8", errors="replace",
                   capture_output=True)
    ok = n = 0
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            n += 1
            ok += r.get("correctness") == "correct"
    return (stem, ok, n)


def prefetch() -> int:
    sys.path.insert(0, str(HERE))
    from run_screenspot_pro import ensure_sample  # noqa: E402
    data_dir = HERE / "data"
    done = fail = 0
    for ann, idx in MANIFEST["samples"]:
        try:
            ensure_sample(data_dir, ann, idx, 120, 5)
            done += 1
        except Exception as exc:
            fail += 1
            print(f"  prefetch fail {ann}#{idx}: {exc.__class__.__name__}", flush=True)
        if (done + fail) % 25 == 0:
            print(f"  prefetch {done+fail}/{len(MANIFEST['samples'])}", flush=True)
    print(f"prefetch done={done} fail={fail}", flush=True)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["prefetch", "single", "zoom"], required=True)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--out-subdir", default="", help="输出子目录;默认=arm 名")
    ap.add_argument("--config", default="sspro_stack_zoom.yaml",
                    help="zoom 臂使用的 config(configs/ 下文件名或绝对路径)")
    ap.add_argument("--manifest", default="",
                    help="切片清单 json;默认 runs/sspro_slice/slice_manifest.json,"
                         "传其它文件可跑全量等任意样本集")
    args = ap.parse_args()

    global MANIFEST
    if args.manifest:
        mpath = Path(args.manifest)
        if not mpath.is_absolute():
            mpath = HERE / args.manifest
        MANIFEST = json.loads(mpath.read_text(encoding="utf-8"))

    if args.arm == "prefetch":
        return prefetch()

    # MiniMax 凭证:从 auth store 注入 env(子进程继承)
    if args.provider.startswith("minimax"):
        import os
        cred = Path.home() / ".openprogram" / "auth" / args.provider / "default.json"
        if cred.exists():
            d = json.loads(cred.read_text(encoding="utf-8"))
            os.environ.setdefault("MINIMAX_CN_API_KEY", d["credentials"][0]["payload"]["api_key"])

    out_subdir = args.out_subdir or args.arm
    groups = MANIFEST["index_args"]
    print(f"{args.arm} [{args.provider}/{args.model}] -> {out_subdir}: "
          f"{len(groups)} annotations, {MANIFEST['total']} samples, "
          f"concurrency={args.concurrency}", flush=True)
    tot_ok = tot_n = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(run_annotation, args.arm, ann, idxs,
                          args.provider, args.model, out_subdir, args.config)
                for ann, idxs in sorted(groups.items())]
        for fut in as_completed(futs):
            stem, ok, n = fut.result()
            tot_ok += ok
            tot_n += n
            print(f"  {stem}: {ok}/{n}  (total {tot_ok}/{tot_n})", flush=True)
    print(f"\n{args.arm} ARM DONE: {tot_ok}/{tot_n} = {tot_ok/max(1,tot_n):.1%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
