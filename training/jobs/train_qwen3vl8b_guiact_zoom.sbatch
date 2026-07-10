#!/bin/bash
#SBATCH --job-name=q3vl8b_zoom
#SBATCH --output=/home/zichuanfu2/GUI-Attention-Harness/training/logs/q3vl8b_zoom_%j.out
#SBATCH --error=/home/zichuanfu2/GUI-Attention-Harness/training/logs/q3vl8b_zoom_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=180G
#SBATCH --time=12:00:00
#SBATCH --gres=gpu:1

set -euo pipefail

# ── Edit these two if the repo/data live elsewhere ─────────────────────────
ROOT=/home/zichuanfu2/GUI-Attention-Harness
GUIAIMA=${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data
# ───────────────────────────────────────────────────────────────────────────

TRAIN_DIR="${ROOT}/training"
LF_DIR="${TRAIN_DIR}/LLaMA-Factory"
ENV_PREFIX="${TRAIN_DIR}/envs/llamafactory-qwen3vl"
CONFIG="${TRAIN_DIR}/configs/qwen3vl8b_guiact_zoom_lora.yaml"
PREP="${TRAIN_DIR}/tools/prepare_guiact_zoom_sft.py"

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/outputs" "${TRAIN_DIR}/data"

echo "job_id=${SLURM_JOB_ID:-manual}"
echo "host=$(hostname)"
echo "started_at=$(date -Is)"
nvidia-smi

if [ -f /opt/anaconda3/etc/profile.d/conda.sh ]; then
  source /opt/anaconda3/etc/profile.d/conda.sh
else
  echo "Cannot find /opt/anaconda3/etc/profile.d/conda.sh"
  exit 1
fi
conda activate "${ENV_PREFIX}"

echo "Preparing GUIAct full-trajectory zoom SFT data ([0,1000] normalized)..."
python "${PREP}" \
  --source-json "${GUIAIMA}/guiact_bbox.json" \
  --image-dir "${GUIAIMA}/GUIAct/web_imgs" \
  --out-dir "${TRAIN_DIR}/data/guiact_zoom_sft" \
  --lf-data-dir "${LF_DIR}/data" \
  --dataset-key guiact_zoom_sft

echo "Starting LLaMA-Factory LoRA SFT..."
cd "${LF_DIR}"
llamafactory-cli train "${CONFIG}"

echo "finished_at=$(date -Is)"
