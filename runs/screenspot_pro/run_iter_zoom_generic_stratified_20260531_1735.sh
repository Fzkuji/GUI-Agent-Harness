#!/usr/bin/env bash
set -euo pipefail

mode="${1:-pure}"
samples_per_annotation="${2:-3}"

cd "/Users/fzkuji/Documents/GUI Agent/GUI-Agent-Harness"
eval "$(/Users/fzkuji/miniforge3/bin/conda shell.bash hook)"
conda activate gui-agent

export GUI_HARNESS_SCREENSPOT_LOCATOR_MODE=iterative_zoom
export GUI_HARNESS_SCREENSPOT_ITERATIVE_ROUNDS=5
export GUI_HARNESS_SCREENSPOT_ITERATIVE_REVIEW_FINAL=1
export GUI_HARNESS_SCREENSPOT_ITERATIVE_VERIFY_FINAL=0
export GUI_HARNESS_SCREENSPOT_ITERATIVE_FALLBACK_TO_CROP=0

run_id="iter_zoom_generic_stratified_${mode}_k${samples_per_annotation}_20260531_1735"
out_dir="runs/screenspot_pro/${run_id}"
mkdir -p "$out_dir/work"
output="$out_dir/results.jsonl"
plan="$out_dir/plan.tsv"

python - "$samples_per_annotation" <<'PY' > "$plan"
import json
import sys
from pathlib import Path

k = max(1, int(sys.argv[1]))
ann_dir = Path("benchmarks/screenspot_pro/data/annotations")
for path in sorted(ann_dir.glob("*.json")):
    samples = json.loads(path.read_text())
    n = len(samples)
    if n <= 0:
        continue
    if k == 1:
        indexes = [0]
    else:
        indexes = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    print(f"{path.name}\t{','.join(str(i) for i in indexes)}\t{n}")
PY

while IFS=$'\t' read -r annotation indexes count; do
  echo "[stratified] annotation=$annotation count=$count indexes=$indexes" >&2
  args=(
    benchmarks/screenspot_pro/run_screenspot_pro.py
    --annotation "$annotation"
    --indexes "$indexes"
    --output "$output"
    --work-dir "$out_dir/work/${annotation%.json}"
    --runtime-retries 4
    --retry-provider-errors 2
    --sample-timeout-s 600
    --download-timeout-s 60
    --download-retries 5
    --skip-existing
  )
  if [[ "$mode" == "metadata" ]]; then
    args+=(--metadata-context)
  elif [[ "$mode" != "pure" ]]; then
    echo "unknown mode: $mode" >&2
    exit 2
  fi
  python "${args[@]}"
done < "$plan"

python - "$output" <<'PY'
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

path = Path(sys.argv[1])
rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
counts = Counter(row["correctness"] for row in rows)
by_group = defaultdict(Counter)
by_ann = defaultdict(Counter)
for row in rows:
    by_group[row.get("group") or "unknown"][row["correctness"]] += 1
    by_ann[row.get("annotation_file") or row.get("annotation") or "unknown"][row["correctness"]] += 1

def pack(counter):
    total = sum(counter.values())
    return {
        "count": total,
        "correct": counter["correct"],
        "wrong": counter["wrong"],
        "wrong_format": counter["wrong_format"],
        "accuracy": round(counter["correct"] / total, 4) if total else 0,
    }

summary = {
    "output": str(path),
    "overall": pack(counts),
    "unique_samples": len({row["sample_id"] for row in rows}),
    "by_group": {key: pack(value) for key, value in sorted(by_group.items())},
    "by_annotation": {key: pack(value) for key, value in sorted(by_ann.items())},
}
summary_path = path.with_suffix(".summary.json")
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
