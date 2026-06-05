#!/usr/bin/env python3
"""为单变量参数扫描生成一个确定性分层样本清单：26 个 app 各取 3 个 index
（首、中、尾各一），共约 78 个样本，覆盖全部应用类型。

确定性（无随机）：index = round(k/3 * (n-1)) for k in 1..3，去重。
输出 sweep_samples.json：[["android_studio_macos.json", 0], ...]
"""
from __future__ import annotations
import json
import glob
import os

DATA = os.path.join(os.path.dirname(__file__), "data", "annotations")
OUT = os.path.join(os.path.dirname(__file__), "sweep_samples.json")
PER_APP = 3


def pick(n: int, k: int) -> list[int]:
    if n <= 0:
        return []
    if n <= k:
        return list(range(n))
    # 均匀取 k 个：首、中、尾附近
    idxs = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return idxs


def main() -> None:
    files = sorted(glob.glob(os.path.join(DATA, "*.json")))
    samples: list[list] = []
    for f in files:
        name = os.path.basename(f)
        try:
            n = len(json.load(open(f)))
        except Exception:
            continue
        for idx in pick(n, PER_APP):
            samples.append([name, idx])
    json.dump(samples, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"{len(samples)} samples across {len(files)} apps -> {OUT}")


if __name__ == "__main__":
    main()
