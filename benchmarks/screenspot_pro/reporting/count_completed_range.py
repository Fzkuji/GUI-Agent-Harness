#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def parse_range(text: str) -> list[int]:
    indexes: list[int] = []
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = [int(x) for x in part.split('-', 1)]
            indexes.extend(range(start, end + 1))
        else:
            indexes.append(int(part))
    return indexes


def main() -> None:
    output = Path(sys.argv[1])
    args = sys.argv[2:]
    if len(args) % 2:
        raise SystemExit('usage: count_completed_range.py OUTPUT ANNOTATION RANGE [ANNOTATION RANGE ...]')

    target_ids: set[str] = set()
    for annotation, range_text in zip(args[0::2], args[1::2]):
        ann_path = Path('benchmarks/screenspot_pro/data/annotations') / annotation
        samples = json.loads(ann_path.read_text())
        for i in parse_range(range_text):
            target_ids.add(samples[i]['id'])
    completed: set[str] = set()
    if output.exists():
        for line in output.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            sample_id = row.get('sample_id')
            if sample_id in target_ids:
                completed.add(sample_id)
    print(len(completed))


if __name__ == '__main__':
    main()
