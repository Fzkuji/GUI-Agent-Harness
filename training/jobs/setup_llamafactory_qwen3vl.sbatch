#!/bin/bash
#SBATCH --job-name=setup_lf_q3vl
#SBATCH --output=training/logs/setup_lf_q3vl_%j.out
#SBATCH --error=training/logs/setup_lf_q3vl_%j.err
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00

# One-time environment setup. Submit from the REPO ROOT:
#   mkdir -p training/logs
#   git clone https://github.com/hiyouga/LLaMA-Factory training/LLaMA-Factory
#   sbatch training/jobs/setup_llamafactory_qwen3vl.sbatch
#
# Machine-specific locations are env-overridable (MODEL_DIR, LF_DIR, ENV_PREFIX).

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
TRAIN_DIR="${ROOT}/training"
LF_DIR="${LF_DIR:-${TRAIN_DIR}/LLaMA-Factory}"
ENV_PREFIX="${ENV_PREFIX:-${TRAIN_DIR}/envs/llamafactory-qwen3vl}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models/Qwen3-VL-4B-Instruct}"

mkdir -p "${TRAIN_DIR}/logs" "${TRAIN_DIR}/envs"

echo "job_id=${SLURM_JOB_ID:-manual}"
echo "host=$(hostname)"
echo "started_at=$(date -Is)"
echo "lf_dir=${LF_DIR}"
echo "env_prefix=${ENV_PREFIX}"
echo "model_dir=${MODEL_DIR}"

if [ -f /opt/anaconda3/etc/profile.d/conda.sh ]; then
  source /opt/anaconda3/etc/profile.d/conda.sh
else
  echo "Cannot find /opt/anaconda3/etc/profile.d/conda.sh"
  exit 1
fi

if [ ! -d "${LF_DIR}/.git" ]; then
  echo "Cannot find LLaMA-Factory repo: ${LF_DIR}"
  exit 1
fi

if [ ! -d "${MODEL_DIR}" ]; then
  echo "Cannot find model dir: ${MODEL_DIR}"
  exit 1
fi

if [ ! -x "${ENV_PREFIX}/bin/python" ]; then
  conda create -y -p "${ENV_PREFIX}" python=3.11 pip
fi

conda activate "${ENV_PREFIX}"

python -m pip install --upgrade pip setuptools wheel

# Server A uses A100 with driver CUDA 12.5; use cu124 wheels rather than newer cu128 wheels.
python -m pip install \
  torch==2.6.0 \
  torchvision==0.21.0 \
  torchaudio==2.6.0 \
  --index-url https://download.pytorch.org/whl/cu124

cd "${LF_DIR}"
python -m pip install -e .
python -m pip check

MODEL_DIR="${MODEL_DIR}" python - <<'PY'
import importlib
import os
from pathlib import Path

packages = ["torch", "transformers", "datasets", "accelerate", "peft", "trl", "llamafactory"]
for name in packages:
    mod = importlib.import_module(name)
    print(f"{name} {getattr(mod, '__version__', 'unknown')}")

import torch
print(f"torch_cuda {torch.version.cuda}")
print(f"cuda_available {torch.cuda.is_available()}")
print(f"cuda_device_count {torch.cuda.device_count()}")

from transformers import AutoConfig, AutoProcessor

model_dir = Path(os.environ["MODEL_DIR"])
config = AutoConfig.from_pretrained(model_dir, trust_remote_code=True)
processor = AutoProcessor.from_pretrained(model_dir, trust_remote_code=True)
print(f"model_type {getattr(config, 'model_type', None)}")
print(f"architectures {getattr(config, 'architectures', None)}")
print(f"processor_class {processor.__class__.__name__}")

from llamafactory.data.template import TEMPLATES

print(f"has_qwen3_vl_template {'qwen3_vl' in TEMPLATES}")
print(f"has_qwen3_vl_nothink_template {'qwen3_vl_nothink' in TEMPLATES}")
PY

python -m pip freeze > "${TRAIN_DIR}/llamafactory-qwen3vl-freeze.txt"
echo "finished_at=$(date -Is)"
