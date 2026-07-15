#!/bin/bash
#SBATCH --job-name=grpo_click
#SBATCH --output=training/logs/grpo_click_%j.out
#SBATCH --error=training/logs/grpo_click_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=100G
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00

# GRPO click-only RL (see training/tools/train_grpo_click.py). Uses the
# GRPO-dedicated env (trl 1.8.0, cloned from llamafactory-qwen3vl so SFT's
# pinned trl<=0.24.0 stays untouched). Submit from the REPO ROOT.

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
ENV_PREFIX="${ENV_PREFIX:-${TRAIN_DIR}/envs/grpo-qwen3vl}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models/Qwen3-VL-4B-Instruct}"
DATA="${DATA:-${TRAIN_DIR}/data/grpo_click_v1.json}"
OUTPUT_DIR="${OUTPUT_DIR:-${TRAIN_DIR}/outputs/grpo_click_v1}"
case "${OUTPUT_DIR}" in /*) ;; *) OUTPUT_DIR="${ROOT}/${OUTPUT_DIR}" ;; esac

MAX_STEPS="${MAX_STEPS:-500}"
NUM_GENERATIONS="${NUM_GENERATIONS:-4}"
PER_DEVICE_BATCH="${PER_DEVICE_BATCH:-4}"
GRAD_ACCUM="${GRAD_ACCUM:-2}"
LR="${LR:-1e-6}"
BETA="${BETA:-0.02}"

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/outputs"
echo "job_id=${SLURM_JOB_ID:-manual} started_at=$(date -Is)"
echo "max_steps=${MAX_STEPS} num_generations=${NUM_GENERATIONS} per_device_batch=${PER_DEVICE_BATCH} lr=${LR} beta=${BETA}"
nvidia-smi --query-gpu=index,name,memory.used --format=csv,noheader

for CONDA_SH in /opt/anaconda3/etc/profile.d/conda.sh \
                "${HOME}/miniconda/etc/profile.d/conda.sh" \
                "${HOME}/miniconda3/etc/profile.d/conda.sh"; do
  [ -f "${CONDA_SH}" ] && break
done
source "${CONDA_SH}"
conda activate "${ENV_PREFIX}"

cd "${ROOT}"
python3 "${TRAIN_DIR}/tools/train_grpo_click.py" \
  --data "${DATA}" \
  --model "${MODEL_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --max-steps "${MAX_STEPS}" \
  --num-generations "${NUM_GENERATIONS}" \
  --per-device-batch "${PER_DEVICE_BATCH}" \
  --grad-accum "${GRAD_ACCUM}" \
  --lr "${LR}" \
  --beta "${BETA}"

echo "finished_at=$(date -Is)"
