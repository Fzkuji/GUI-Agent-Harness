#!/bin/bash
#SBATCH --job-name=q3vl4b_zoom_v3
#SBATCH --output=training/logs/q3vl4b_zoom_v3_%j.out
#SBATCH --error=training/logs/q3vl4b_zoom_v3_%j.err
#SBATCH --cpus-per-task=12
#SBATCH --mem=200G
#SBATCH --time=23:50:00
#SBATCH --gres=gpu:2

# v3: same trajectories as v2 PLUS real detector/OCR candidate evidence in
# ~50% of rows (TRAINING_PLAN stage-1 design) — trains the model to work
# INSIDE the harness loop. Requires precompute_candidates.sbatch output.
# Submit from the REPO ROOT. Dual-GPU DDP, effective batch 8.

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
LF_DIR="${LF_DIR:-${TRAIN_DIR}/LLaMA-Factory}"
ENV_PREFIX="${ENV_PREFIX:-${TRAIN_DIR}/envs/llamafactory-qwen3vl}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models/Qwen3-VL-4B-Instruct}"
GUIAIMA="${GUIAIMA:-${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data}"
CONFIG="${TRAIN_DIR}/configs/qwen3vl4b_zoom_v2_lora.yaml"   # same hparams; dataset overridden below
OUTPUT_DIR="${OUTPUT_DIR:-${TRAIN_DIR}/outputs/qwen3vl4b_zoom_v3_lora}"
CAND_DIR="${CAND_DIR:-${TRAIN_DIR}/data/candidates_cache}"

N_GUIACT="${N_GUIACT:-8000}"
N_WAVEUI="${N_WAVEUI:-8000}"
N_UGROUND="${N_UGROUND:-4000}"
EVIDENCE_FRAC="${EVIDENCE_FRAC:-0.5}"
EPOCHS="${EPOCHS:-1.0}"

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/outputs" "${TRAIN_DIR}/data"

echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
echo "rows: guiact=${N_GUIACT} waveui=${N_WAVEUI} uground=${N_UGROUND} evidence_frac=${EVIDENCE_FRAC}"
nvidia-smi

for CONDA_SH in /opt/anaconda3/etc/profile.d/conda.sh \
                "${HOME}/miniconda/etc/profile.d/conda.sh" \
                "${HOME}/miniconda3/etc/profile.d/conda.sh"; do
  [ -f "${CONDA_SH}" ] && break
done
source "${CONDA_SH}"
conda activate "${ENV_PREFIX}"

if [ "${SKIP_PREP:-0}" = "1" ] && [ -s "${LF_DIR}/data/zoom_sft_v3_train.json" ]; then
  echo "SKIP_PREP=1 — reusing existing zoom_sft_v3 data."
else
  echo "Preparing v3 data (trajectories + real candidate evidence)..."
  python "${TRAIN_DIR}/tools/prepare_zoom_sft_v2.py" \
    --source "guiact:${GUIAIMA}/guiact_bbox.json:${GUIAIMA}/GUIAct/web_imgs:${N_GUIACT}" \
    --source "waveui:${GUIAIMA}/wave_ui_bbox.json:${GUIAIMA}/Wave-UI/images_fixed:${N_WAVEUI}" \
    --source "uground:${GUIAIMA}/uground_bbox_single_60k.json:${GUIAIMA}/Uground/images:${N_UGROUND}" \
    --out-dir "${TRAIN_DIR}/data/zoom_sft_v3" \
    --lf-data-dir "${LF_DIR}/data" \
    --dataset-key zoom_sft_v3 \
    --candidates-dir "${CAND_DIR}" \
    --evidence-frac "${EVIDENCE_FRAC}" \
    --workers 10
fi

echo "Starting LLaMA-Factory LoRA SFT (v3, dual-GPU DDP)..."
cd "${LF_DIR}"
FORCE_TORCHRUN=1 llamafactory-cli train "${CONFIG}" \
  model_name_or_path="${MODEL_DIR}" \
  dataset=zoom_sft_v3 \
  dataset_dir="${LF_DIR}/data" \
  output_dir="${OUTPUT_DIR}" \
  num_train_epochs="${EPOCHS}" \
  gradient_accumulation_steps=4

echo "finished_at=$(date -Is)"
