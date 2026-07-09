#!/usr/bin/env python3
"""从 full1581 分层抽 300 样本做 SSPro 切片(按 annotation 文件分层,固定种子)。

输出 runs/sspro_slice/slice_manifest.json:
  {"samples": [[ann, idx], ...], "index_args": {ann: "i1,i2,..."}}
旧全量逐行结果(results/gpt_5_5/results.jsonl, legacy_baseline 87.9%)可按
sample_id 同行对比。
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SEED = 42
TARGET = 300

samples = json.loads((HERE / "full1581_samples.json").read_text(encoding="utf-8"))
by_ann: dict[str, list[int]] = defaultdict(list)
for ann, idx in samples:
    by_ann[ann].append(idx)

rng = random.Random(SEED)
total = len(samples)
picked: list[tuple[str, int]] = []
# 按各 annotation 占比分配名额(至少 1),再随机抽样
quota = {ann: max(1, round(len(idxs) / total * TARGET)) for ann, idxs in by_ann.items()}
# 调整到正好 TARGET
diff = TARGET - sum(quota.values())
anns_sorted = sorted(by_ann, key=lambda a: -len(by_ann[a]))
i = 0
while diff != 0:
    a = anns_sorted[i % len(anns_sorted)]
    if diff > 0 and quota[a] < len(by_ann[a]):
        quota[a] += 1
        diff -= 1
    elif diff < 0 and quota[a] > 1:
        quota[a] -= 1
        diff += 1
    i += 1

for ann, idxs in sorted(by_ann.items()):
    take = rng.sample(idxs, min(quota[ann], len(idxs)))
    picked.extend((ann, i) for i in sorted(take))

out_dir = HERE / "runs" / "sspro_slice"
out_dir.mkdir(parents=True, exist_ok=True)
manifest = {
    "seed": SEED,
    "total": len(picked),
    "samples": picked,
    "index_args": {
        ann: ",".join(str(i) for a2, i in picked if a2 == ann)
        for ann in sorted({a for a, _ in picked})
    },
}
(out_dir / "slice_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"picked {len(picked)} samples across {len(manifest['index_args'])} annotations")
