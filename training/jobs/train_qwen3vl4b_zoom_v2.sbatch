#!/bin/bash
#SBATCH --job-name=q3vl4b_zoom_v2
#SBATCH --output=training/logs/q3vl4b_zoom_v2_%j.out
#SBATCH --error=training/logs/q3vl4b_zoom_v2_%j.err
#SBATCH --cpus-per-task=12
#SBATCH --mem=200G
#SBATCH --time=23:50:00
#SBATCH --gres=gpu:2

# v2 training: multi-source (GUIAct + Wave-UI + UGround), variable-depth
# trajectories, plausible recrop negatives, 2M-px round-0 inputs.
# Submit from the REPO ROOT (mkdir -p training/logs once).
# Dual-GPU DDP (cluster allows 2 cards/person; an empty machine assigns the
# NVLink pair 0+1): ~67k samples -> ~8h. grad accum halved to 4 so the
# effective batch stays 8, same as the v1 pilot.
# SKIP_PREP=1 reuses training/data/zoom_sft_v2 from a previous run.

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
LF_DIR="${LF_DIR:-${TRAIN_DIR}/LLaMA-Factory}"
ENV_PREFIX="${ENV_PREFIX:-${TRAIN_DIR}/envs/llamafactory-qwen3vl}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models/Qwen3-VL-4B-Instruct}"
GUIAIMA="${GUIAIMA:-${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data}"
CONFIG="${TRAIN_DIR}/configs/qwen3vl4b_zoom_v2_lora.yaml"
OUTPUT_DIR="${OUTPUT_DIR:-${TRAIN_DIR}/outputs/qwen3vl4b_zoom_v2_lora}"

# Per-source row budgets (env-overridable)
N_GUIACT="${N_GUIACT:-8000}"
N_WAVEUI="${N_WAVEUI:-8000}"
N_UGROUND="${N_UGROUND:-4000}"
EPOCHS="${EPOCHS:-1.0}"

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/outputs" "${TRAIN_DIR}/data"

echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
echo "rows: guiact=${N_GUIACT} waveui=${N_WAVEUI} uground=${N_UGROUND} epochs=${EPOCHS}"
nvidia-smi

for CONDA_SH in /opt/anaconda3/etc/profile.d/conda.sh \
                "${HOME}/miniconda/etc/profile.d/conda.sh" \
                "${HOME}/miniconda3/etc/profile.d/conda.sh"; do
  [ -f "${CONDA_SH}" ] && break
done
source "${CONDA_SH}"
conda activate "${ENV_PREFIX}"

if [ "${SKIP_PREP:-0}" = "1" ] && [ -s "${LF_DIR}/data/zoom_sft_v2_train.json" ]; then
  echo "SKIP_PREP=1 — reusing existing zoom_sft_v2 data."
else
  echo "Preparing v2 multi-source zoom SFT data..."
  python "${TRAIN_DIR}/tools/prepare_zoom_sft_v2.py" \
    --source "guiact:${GUIAIMA}/guiact_bbox.json:${GUIAIMA}/GUIAct/web_imgs:${N_GUIACT}" \
    --source "waveui:${GUIAIMA}/wave_ui_bbox.json:${GUIAIMA}/Wave-UI/images_fixed:${N_WAVEUI}" \
    --source "uground:${GUIAIMA}/uground_bbox_single_60k.json:${GUIAIMA}/Uground/images:${N_UGROUND}" \
    --out-dir "${TRAIN_DIR}/data/zoom_sft_v2" \
    --lf-data-dir "${LF_DIR}/data" \
    --dataset-key zoom_sft_v2 \
    --workers 10
fi

echo "Starting LLaMA-Factory LoRA SFT (v2, dual-GPU DDP)..."
cd "${LF_DIR}"
FORCE_TORCHRUN=1 llamafactory-cli train "${CONFIG}" \
  model_name_or_path="${MODEL_DIR}" \
  dataset_dir="${LF_DIR}/data" \
  output_dir="${OUTPUT_DIR}" \
  num_train_epochs="${EPOCHS}" \
  gradient_accumulation_steps=4

echo "finished_at=$(date -Is)"
