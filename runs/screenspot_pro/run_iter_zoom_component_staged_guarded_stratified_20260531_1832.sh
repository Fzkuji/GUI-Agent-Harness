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
export GUI_HARNESS_SCREENSPOT_ITERATIVE_CROP_COMMIT_GATE=1
export GUI_HARNESS_SCREENSPOT_ITERATIVE_CROP_RETRIES=3
export GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGED_CROP=1
export GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGE1_MIN_AREA_PCT=20
export GUI_HARNESS_SCREENSPOT_ITERATIVE_STAGE2_MIN_AREA_PCT=8

run_id="iter_zoom_component_staged_guarded_stratified_${mode}_k${samples_per_annotation}_20260531_1832"
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
  echo "[component_staged_guarded] annotation=$annotation count=$count indexes=$indexes" >&2
  args=(
    benchmarks/screenspot_pro/run_screenspot_pro.py
    --annotation "$annotation"
    --indexes "$indexes"
    --output "$output"
    --work-dir "$out_dir/work/${annotation%.json}"
    --runtime-retries 4
    --retry-provider-errors 2
    --sample-timeout-s 900
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

python runs/screenspot_pro/report_iter_zoom_progress.py --run-dir "$out_dir" --max-visuals 50
