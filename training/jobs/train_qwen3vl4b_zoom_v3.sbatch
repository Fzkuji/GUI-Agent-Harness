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
# Force absolute: the script cd's into LF_DIR before invoking llamafactory-cli,
# so a caller-supplied relative OUTPUT_DIR (e.g. OUTPUT_DIR=training/outputs/x)
# silently resolves under LF_DIR instead of ROOT, nesting output two levels
# deep (training/LLaMA-Factory/training/outputs/x) — bit us once already.
case "${OUTPUT_DIR}" in
  /*) ;;
  *) OUTPUT_DIR="${ROOT}/${OUTPUT_DIR}" ;;
esac
CAND_DIR="${CAND_DIR:-${TRAIN_DIR}/data/candidates_cache}"

N_GUIACT="${N_GUIACT:-8000}"
N_WAVEUI="${N_WAVEUI:-8000}"
N_UGROUND="${N_UGROUND:-4000}"
N_OSATLAS="${N_OSATLAS:-0}"   # OS-Atlas desktop_domain (linux+macos merged); 0=skip
EVIDENCE_FRAC="${EVIDENCE_FRAC:-0.5}"
FINAL_FRAC="${FINAL_FRAC:-0.5}"
RECROP_FRAC="${RECROP_FRAC:-0.25}"
DATASET_KEY="${DATASET_KEY:-zoom_sft_v3}"
EPOCHS="${EPOCHS:-1.0}"
MAX_STEPS="${MAX_STEPS:-0}"           # >0: stop at this step (staged training, checkpoint-and-gate)
RESUME_FROM="${RESUME_FROM:-}"        # checkpoint dir to resume from (staged continuation)
case "${RESUME_FROM}" in
  ""|/*) ;;
  *) RESUME_FROM="${ROOT}/${RESUME_FROM}" ;;
esac
ADAPTER_INIT="${ADAPTER_INIT:-}"      # existing LoRA adapter to initialize from (curriculum: new data, warm weights)
case "${ADAPTER_INIT}" in
  ""|/*) ;;
  *) ADAPTER_INIT="${ROOT}/${ADAPTER_INIT}" ;;
esac

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/outputs" "${TRAIN_DIR}/data"

echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
echo "rows: guiact=${N_GUIACT} waveui=${N_WAVEUI} uground=${N_UGROUND} evidence_frac=${EVIDENCE_FRAC}"
echo "final_frac=${FINAL_FRAC} recrop_frac=${RECROP_FRAC} dataset_key=${DATASET_KEY}"
nvidia-smi

for CONDA_SH in /opt/anaconda3/etc/profile.d/conda.sh \
                "${HOME}/miniconda/etc/profile.d/conda.sh" \
                "${HOME}/miniconda3/etc/profile.d/conda.sh"; do
  [ -f "${CONDA_SH}" ] && break
done
source "${CONDA_SH}"
conda activate "${ENV_PREFIX}"

if [ "${SKIP_PREP:-0}" = "1" ] && [ -s "${LF_DIR}/data/${DATASET_KEY}_train.json" ]; then
  echo "SKIP_PREP=1 — reusing existing ${DATASET_KEY} data."
else
  echo "Preparing v3 data (trajectories + real candidate evidence)..."
  SOURCES=()
  if [ -n "${CUSTOM_SOURCES:-}" ]; then
    # CUSTOM_SOURCES: space-separated name:json:imgdir:n specs — replaces the standard mix entirely
    for SPEC in ${CUSTOM_SOURCES}; do SOURCES+=(--source "${SPEC}"); done
  else
    SOURCES+=(--source "guiact:${GUIAIMA}/guiact_bbox.json:${GUIAIMA}/GUIAct/web_imgs:${N_GUIACT}")
    SOURCES+=(--source "waveui:${GUIAIMA}/wave_ui_bbox.json:${GUIAIMA}/Wave-UI/images_fixed:${N_WAVEUI}")
    SOURCES+=(--source "uground:${GUIAIMA}/uground_bbox_single_60k.json:${GUIAIMA}/Uground/images:${N_UGROUND}")
    if [ "${N_OSATLAS}" != "0" ]; then
      SOURCES+=(--source "osatlas:${GUIAIMA}/osatlas_desktop_bbox.json:${GUIAIMA}/OSAtlas-Desktop/all_images:${N_OSATLAS}")
    fi
  fi
  python "${TRAIN_DIR}/tools/prepare_zoom_sft_v2.py" \
    "${SOURCES[@]}" \
    --out-dir "${TRAIN_DIR}/data/${DATASET_KEY}" \
    --lf-data-dir "${LF_DIR}/data" \
    --dataset-key "${DATASET_KEY}" \
    --candidates-dir "${CAND_DIR}" \
    --evidence-frac "${EVIDENCE_FRAC}" \
    --final-frac "${FINAL_FRAC}" \
    --recrop-frac "${RECROP_FRAC}" \
    --workers 10
fi

echo "Starting LLaMA-Factory LoRA SFT (v3, dual-GPU DDP)..."
echo "max_steps=${MAX_STEPS} resume_from=${RESUME_FROM:-<fresh>}"
cd "${LF_DIR}"
EXTRA_ARGS=()
[ "${MAX_STEPS}" != "0" ] && EXTRA_ARGS+=("max_steps=${MAX_STEPS}")
[ -n "${RESUME_FROM}" ] && EXTRA_ARGS+=("resume_from_checkpoint=${RESUME_FROM}")
[ -n "${ADAPTER_INIT}" ] && EXTRA_ARGS+=("adapter_name_or_path=${ADAPTER_INIT}")
# cutoff_len 8192 (not the config's 4096): the evidence block adds up to
# ~1.5k tokens; at 4096 the trailing <image> token gets truncated away and
# transformers dies with "Image features and image tokens do not match".
FORCE_TORCHRUN=1 llamafactory-cli train "${CONFIG}" \
  model_name_or_path="${MODEL_DIR}" \
  dataset="${DATASET_KEY}" \
  dataset_dir="${LF_DIR}/data" \
  output_dir="${OUTPUT_DIR}" \
  num_train_epochs="${EPOCHS}" \
  gradient_accumulation_steps=4 \
  cutoff_len=8192 \
  "${EXTRA_ARGS[@]}"

echo "finished_at=$(date -Is)"
