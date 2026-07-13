#!/bin/bash
#SBATCH --job-name=sspro_harness
#SBATCH --output=training/logs/sspro_harness_%j.out
#SBATCH --error=training/logs/sspro_harness_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --time=12:00:00
#SBATCH --gres=gpu:1

# FULL harness (commit gate + staged crops + live detector candidates,
# configs/sspro_stack_zoom.yaml) driving a LoRA-tuned checkpoint through the
# local-openai provider. This is the direct test of TRAINING_PLAN's thesis:
# "model trained to work inside the harness loop" + the real harness控制器.
#
# Two runtimes on one GPU: the LF env serves the model on PORT; the SYSTEM
# python3 (harness deps: torch/ultralytics/easyocr + openprogram stub) runs
# the benchmark. Submit from the REPO ROOT. Resumable (--skip-existing).
#
#   LORA_DIR=training/outputs/qwen3vl4b_zoom_v3full_lora \
#     sbatch training/jobs/eval_sspro_harness_lora.sbatch
#   NUM=12 OUT_SUBDIR=zoom_v3_smoke sbatch ...   # pilot-adapter smoke test

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
ENV_PREFIX="${ENV_PREFIX:-${TRAIN_DIR}/envs/llamafactory-qwen3vl}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models/Qwen3-VL-4B-Instruct}"
LORA_DIR="${LORA_DIR-${TRAIN_DIR}/outputs/qwen3vl4b_zoom_v3full_lora}"  # ""=base
SSPRO_DATA="${SSPRO_DATA:-${HOME}/data/ScreenSpot-Pro}"
NUM="${NUM:-300}"
CONCURRENCY="${CONCURRENCY:-3}"
CONFIG="${CONFIG:-sspro_stack_zoom.yaml}"
OUT_SUBDIR="${OUT_SUBDIR:-zoom_v3full}"
PORT="${PORT:-8000}"
MAX_PIXELS="${MAX_PIXELS:-2097152}"   # must match the checkpoint's training image_max_pixels

mkdir -p "${TRAIN_DIR}/logs"
echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
echo "lora=${LORA_DIR:-<base>} num=${NUM} config=${CONFIG} out=${OUT_SUBDIR}"
nvidia-smi --query-gpu=index,name,memory.used --format=csv,noheader

# run_screenspot_pro probes data_dir/raw_images/<img_filename>; reuse the
# local image store instead of re-downloading.
[ -e "${SSPRO_DATA}/raw_images" ] || ln -s images "${SSPRO_DATA}/raw_images"

# ── model server (LF env python; no conda activate needed) ──
if [ -n "${LORA_DIR}" ] && [ -d "${LORA_DIR}" ]; then
  "${ENV_PREFIX}/bin/python" "${TRAIN_DIR}/tools/serve_qwen_vl_lora_api.py" \
    --model "${MODEL_DIR}" --adapter "${LORA_DIR}" \
    --max-pixels "${MAX_PIXELS}" --port "${PORT}" &
else
  "${ENV_PREFIX}/bin/python" "${TRAIN_DIR}/tools/serve_qwen_vl_api.py" \
    --model "${MODEL_DIR}" --max-pixels "${MAX_PIXELS}" --port "${PORT}" &
fi
SERVER_PID=$!
trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT
for i in $(seq 1 120); do
  curl -sf "http://127.0.0.1:${PORT}/v1/models" > /dev/null 2>&1 && { echo "server up after ${i}0s"; break; }
  sleep 10
done

# ── manifest: same 300-row slice eval_zoom_traj scored ──
MANIFEST="${ROOT}/benchmarks/screenspot_pro/runs/sspro_slice/sspro${NUM}_seed20260711.json"
python3 "${TRAIN_DIR}/tools/make_sspro_manifest.py" --num "${NUM}" --out "${MANIFEST}" \
  --val-rows "${TRAIN_DIR}/data/sspro_val_rows.json" --annotations "${SSPRO_DATA}/annotations"

# ── full harness, local-openai provider (system python3) ──
export PYTHONPATH="${ROOT}:${TRAIN_DIR}/tools/openprogram_stub:${PYTHONPATH:-}"
export GUI_HARNESS_LOCAL_API_BASE="http://127.0.0.1:${PORT}/v1"
python3 "${ROOT}/benchmarks/screenspot_pro/runners/run_sspro_slice_arm.py" \
  --arm zoom --provider local-openai --model qwen3-vl-4b \
  --manifest "${MANIFEST}" --config "${CONFIG}" \
  --data-dir "${SSPRO_DATA}" --out-subdir "${OUT_SUBDIR}" \
  --concurrency "${CONCURRENCY}"

echo "finished_at=$(date -Is)"
