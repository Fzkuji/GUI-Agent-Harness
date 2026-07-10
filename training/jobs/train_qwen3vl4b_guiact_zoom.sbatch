#!/bin/bash
#SBATCH --job-name=q3vl4b_zoom
#SBATCH --output=training/logs/q3vl4b_zoom_%j.out
#SBATCH --error=training/logs/q3vl4b_zoom_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=180G
#SBATCH --time=12:00:00
#SBATCH --gres=gpu:1

# Submit from the REPO ROOT (Slurm resolves the relative log paths above
# against the submission directory):
#   mkdir -p training/logs   # once
#   sbatch training/jobs/train_qwen3vl4b_guiact_zoom.sbatch
#
# Machine-specific locations are env-overridable, e.g.:
#   MODEL_DIR=/data/models/Qwen3-VL-4B-Instruct sbatch training/jobs/...

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
LF_DIR="${LF_DIR:-${TRAIN_DIR}/LLaMA-Factory}"
ENV_PREFIX="${ENV_PREFIX:-${TRAIN_DIR}/envs/llamafactory-qwen3vl}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models/Qwen3-VL-4B-Instruct}"
GUIAIMA="${GUIAIMA:-${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data}"
CONFIG="${TRAIN_DIR}/configs/qwen3vl4b_guiact_zoom_lora.yaml"
OUTPUT_DIR="${OUTPUT_DIR:-${TRAIN_DIR}/outputs/qwen3vl4b_guiact_zoom_lora}"

# Scale knobs. GUIAct has ~42.5k rows -> ~170k samples; a full 2-epoch run
# does NOT fit the cluster's 24h wall clock on one A100. Pilot small, then
# scale: NUM_ROWS=2000 (~8k samples, 2 epochs, a few hours) -> 10000 -> more.
NUM_ROWS="${NUM_ROWS:-2000}"     # 0 = all rows
EPOCHS="${EPOCHS:-2.0}"

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/outputs" "${TRAIN_DIR}/data"

echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
echo "root=${ROOT}"
echo "model_dir=${MODEL_DIR}"
echo "guiaima=${GUIAIMA}"
nvidia-smi

# Server A: /opt/anaconda3; Server B: preinstalled ~/miniconda (mandated).
for CONDA_SH in /opt/anaconda3/etc/profile.d/conda.sh \
                "${HOME}/miniconda/etc/profile.d/conda.sh" \
                "${HOME}/miniconda3/etc/profile.d/conda.sh"; do
  [ -f "${CONDA_SH}" ] && break
done
source "${CONDA_SH}"
conda activate "${ENV_PREFIX}"

echo "Preparing GUIAct full-trajectory zoom SFT data ([0,1000] normalized)..."
python "${TRAIN_DIR}/tools/prepare_guiact_zoom_sft.py" \
  --source-json "${GUIAIMA}/guiact_bbox.json" \
  --image-dir "${GUIAIMA}/GUIAct/web_imgs" \
  --out-dir "${TRAIN_DIR}/data/guiact_zoom_sft" \
  --lf-data-dir "${LF_DIR}/data" \
  --dataset-key guiact_zoom_sft \
  --num-samples "${NUM_ROWS}"

echo "Starting LLaMA-Factory LoRA SFT..."
cd "${LF_DIR}"
llamafactory-cli train "${CONFIG}" \
  model_name_or_path="${MODEL_DIR}" \
  dataset_dir="${LF_DIR}/data" \
  output_dir="${OUTPUT_DIR}" \
  num_train_epochs="${EPOCHS}"

echo "finished_at=$(date -Is)"
