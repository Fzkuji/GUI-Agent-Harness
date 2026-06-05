#!/usr/bin/env python3
"""探测 MiniMax-M3 能稳定并发几个：对每个并发级别同时发一批最小文本请求，
记成功数 / 失败数 / 延迟。失败率开始上升的并发级别就是上限。

每个请求都是独立 runtime（和实际跑法一致：每样本一个子进程/runtime）。
"""
from __future__ import annotations
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gui_harness.openprogram_compat import create_runtime  # noqa: E402

PROVIDER, MODEL = "minimax-cn-coding-plan", "MiniMax-M3"
LEVELS = [2, 4, 6, 8, 12]
PROMPT = [{"type": "text", "text": "Reply with exactly the two characters: ok"}]


def one_call(i: int) -> tuple:
    t0 = time.time()
    try:
        rt = create_runtime(provider=PROVIDER, model=MODEL, max_retries=1)
        reply = rt.exec(content=PROMPT)
        dt = time.time() - t0
        return (i, "ok", round(dt, 1), (reply or "")[:20].replace("\n", " "))
    except Exception as e:
        dt = time.time() - t0
        return (i, "ERR", round(dt, 1), f"{type(e).__name__}: {str(e)[:80]}")


def main() -> int:
    for n in LEVELS:
        print(f"\n=== 并发 {n} ===", flush=True)
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=n) as ex:
            futs = [ex.submit(one_call, i) for i in range(n)]
            res = [f.result() for f in as_completed(futs)]
        ok = sum(1 for r in res if r[1] == "ok")
        errs = [r for r in res if r[1] != "ok"]
        lat = sorted(r[2] for r in res)
        wall = time.time() - t0
        print(f"  成功 {ok}/{n}  墙钟 {wall:.1f}s  延迟 min/中/max={lat[0]}/{lat[len(lat)//2]}/{lat[-1]}s", flush=True)
        for r in errs[:5]:
            print(f"    ERR #{r[0]}: {r[3]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
