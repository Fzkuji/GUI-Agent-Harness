#!/bin/bash
#SBATCH --job-name=precompute_cands
#SBATCH --output=training/logs/precompute_cands_%j.out
#SBATCH --error=training/logs/precompute_cands_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=100G
#SBATCH --time=16:00:00
#SBATCH --gres=gpu:1

# One-time: run the harness's detector+OCR (GPA-YOLO + EasyOCR, conf=0.12)
# over the v3 training images and cache build_candidates() output.
# Uses the SYSTEM python3 (~/.local has torch/ultralytics/easyocr — the env
# the harness benchmark runs used), NOT the LLaMA-Factory env.
# Submit from the REPO ROOT. Resumable: re-submitting skips cached images.

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
GUIAIMA="${GUIAIMA:-${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data}"
N_GUIACT="${N_GUIACT:-8000}"
N_WAVEUI="${N_WAVEUI:-8000}"
N_UGROUND="${N_UGROUND:-4000}"
N_OSATLAS="${N_OSATLAS:-0}"   # OS-Atlas desktop_domain (linux+macos merged); 0=skip

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/data/candidates_cache"

echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
nvidia-smi --query-gpu=index,name,memory.used --format=csv,noheader

cd "${ROOT}"
EXTRA_SOURCES=()
if [ "${N_OSATLAS}" != "0" ]; then
  EXTRA_SOURCES+=(--source "osatlas:${GUIAIMA}/osatlas_desktop_bbox.json:${GUIAIMA}/OSAtlas-Desktop/all_images:${N_OSATLAS}")
fi
python3 "${TRAIN_DIR}/tools/precompute_candidates.py" \
  --source "guiact:${GUIAIMA}/guiact_bbox.json:${GUIAIMA}/GUIAct/web_imgs:${N_GUIACT}" \
  --source "waveui:${GUIAIMA}/wave_ui_bbox.json:${GUIAIMA}/Wave-UI/images_fixed:${N_WAVEUI}" \
  --source "uground:${GUIAIMA}/uground_bbox_single_60k.json:${GUIAIMA}/Uground/images:${N_UGROUND}" \
  "${EXTRA_SOURCES[@]}" \
  --out-dir "${TRAIN_DIR}/data/candidates_cache"

echo "finished_at=$(date -Is)"
