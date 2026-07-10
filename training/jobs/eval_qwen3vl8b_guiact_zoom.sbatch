#!/bin/bash
#SBATCH --job-name=q3vl8b_zoom_eval
#SBATCH --output=/home/zichuanfu2/GUI-Attention-Harness/training/logs/q3vl8b_zoom_eval_%j.out
#SBATCH --error=/home/zichuanfu2/GUI-Attention-Harness/training/logs/q3vl8b_zoom_eval_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --time=08:00:00
#SBATCH --gres=gpu:1

set -euo pipefail

# ── Edit these if the repo/data live elsewhere ─────────────────────────────
ROOT=/home/zichuanfu2/GUI-Attention-Harness
GUIAIMA=${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data
MODEL_DIR=/home/zichuanfu2/models/Qwen3-VL-8B-Instruct
LORA_DIR=${ROOT}/training/outputs/qwen3vl8b_guiact_zoom_lora   # empty ("") = eval base model
EVAL_MODE=${EVAL_MODE:-zoom}     # zoom | single
EVAL_NUM=${EVAL_NUM:-0}          # 0 = all val rows
# ───────────────────────────────────────────────────────────────────────────

TRAIN_DIR="${ROOT}/training"
ENV_PREFIX="${TRAIN_DIR}/envs/llamafactory-qwen3vl"
PORT=8000

echo "job_id=${SLURM_JOB_ID:-manual} host=$(hostname) started_at=$(date -Is)"
nvidia-smi

source /opt/anaconda3/etc/profile.d/conda.sh
conda activate "${ENV_PREFIX}"

# Start the OpenAI-compatible server (LoRA variant if LORA_DIR set).
if [ -n "${LORA_DIR}" ] && [ -d "${LORA_DIR}" ]; then
  python "${TRAIN_DIR}/tools/serve_qwen_vl_lora_api.py" \
    --model "${MODEL_DIR}" --lora "${LORA_DIR}" --port "${PORT}" &
else
  python "${TRAIN_DIR}/tools/serve_qwen_vl_api.py" \
    --model "${MODEL_DIR}" --port "${PORT}" &
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
  --model qwen3-vl-8b \
  --val-rows "${TRAIN_DIR}/data/guiact_zoom_sft/val_rows.json" \
  --image-dir "${GUIAIMA}/GUIAct/web_imgs" \
  --mode "${EVAL_MODE}" \
  --num "${EVAL_NUM}" \
  --out "${TRAIN_DIR}/outputs/eval_${EVAL_MODE}_${SLURM_JOB_ID:-manual}.jsonl"

echo "finished_at=$(date -Is)"
