#!/bin/bash
#SBATCH --job-name=q3vl4b_zoom_eval
#SBATCH --output=training/logs/q3vl4b_zoom_eval_%j.out
#SBATCH --error=training/logs/q3vl4b_zoom_eval_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --time=08:00:00
#SBATCH --gres=gpu:1

# Submit from the REPO ROOT (mkdir -p training/logs once, see train job).
# Variants:
#   sbatch training/jobs/eval_qwen3vl4b_guiact_zoom.sbatch                 # LoRA, zoom loop
#   EVAL_MODE=single sbatch training/jobs/eval_qwen3vl4b_guiact_zoom.sbatch
#   LORA_DIR="" sbatch training/jobs/eval_qwen3vl4b_guiact_zoom.sbatch     # base model
#   LORA_DIR="" EVAL_MODE=single sbatch training/jobs/eval_qwen3vl4b_guiact_zoom.sbatch

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
ENV_PREFIX="${ENV_PREFIX:-${TRAIN_DIR}/envs/llamafactory-qwen3vl}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models/Qwen3-VL-4B-Instruct}"
GUIAIMA="${GUIAIMA:-${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data}"
LORA_DIR="${LORA_DIR-${TRAIN_DIR}/outputs/qwen3vl4b_guiact_zoom_lora}"  # set LORA_DIR="" for base
EVAL_MODE="${EVAL_MODE:-zoom}"   # zoom | single
EVAL_NUM="${EVAL_NUM:-0}"        # 0 = all val rows
PORT="${PORT:-8000}"
# Dataset knobs — default GUIAct val; for ScreenSpot-Pro pass e.g.:
#   VAL_ROWS=training/data/sspro_val_rows.json \
#   IMAGE_DIR=$HOME/data/ScreenSpot-Pro/images \
#   EVAL_TAG=sspro sbatch training/jobs/eval_qwen3vl4b_guiact_zoom.sbatch
VAL_ROWS="${VAL_ROWS:-${TRAIN_DIR}/data/guiact_zoom_sft/val_rows.json}"
IMAGE_DIR="${IMAGE_DIR:-${GUIAIMA}/GUIAct/web_imgs}"
EVAL_TAG="${EVAL_TAG:-guiact}"
MAX_PIXELS="${MAX_PIXELS:-1048576}"   # must match the checkpoint's training image_max_pixels (v2: 2097152)

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/outputs"

echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
echo "root=${ROOT} lora_dir=${LORA_DIR:-<base>} mode=${EVAL_MODE}"
nvidia-smi

# Server A: /opt/anaconda3; Server B: preinstalled ~/miniconda (mandated).
for CONDA_SH in /opt/anaconda3/etc/profile.d/conda.sh \
                "${HOME}/miniconda/etc/profile.d/conda.sh" \
                "${HOME}/miniconda3/etc/profile.d/conda.sh"; do
  [ -f "${CONDA_SH}" ] && break
done
source "${CONDA_SH}"
conda activate "${ENV_PREFIX}"

# Start the OpenAI-compatible server (LoRA variant if LORA_DIR set).
# --max-pixels matches the checkpoint's training image_max_pixels so the
# model sees the same resolution distribution it was tuned on.
if [ -n "${LORA_DIR}" ] && [ -d "${LORA_DIR}" ]; then
  python "${TRAIN_DIR}/tools/serve_qwen_vl_lora_api.py" \
    --model "${MODEL_DIR}" --adapter "${LORA_DIR}" \
    --max-pixels "${MAX_PIXELS}" --port "${PORT}" &
else
  python "${TRAIN_DIR}/tools/serve_qwen_vl_api.py" \
    --model "${MODEL_DIR}" \
    --max-pixels "${MAX_PIXELS}" --port "${PORT}" &
fi
SERVER_PID=$!
trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT

# Wait for the server to come up.
for i in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${PORT}/v1/models" > /dev/null 2>&1; then
    echo "server up after ${i}0s"; break
  fi
  sleep 10
done

python "${TRAIN_DIR}/tools/eval_zoom_traj.py" \
  --api-base "http://127.0.0.1:${PORT}/v1" \
  --model qwen3-vl-4b \
  --val-rows "${VAL_ROWS}" \
  --image-dir "${IMAGE_DIR}" \
  --mode "${EVAL_MODE}" \
  --num "${EVAL_NUM}" \
  --out "${TRAIN_DIR}/outputs/eval_${EVAL_TAG}_${EVAL_MODE}_${SLURM_JOB_ID:-manual}.jsonl"

echo "finished_at=$(date -Is)"
