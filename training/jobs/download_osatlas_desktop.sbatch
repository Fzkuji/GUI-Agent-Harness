#!/bin/bash
#SBATCH --job-name=osatlas_dl
#SBATCH --output=training/logs/osatlas_dl_%j.out
#SBATCH --error=training/logs/osatlas_dl_%j.err
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00

# Download + extract + convert OS-Atlas desktop_domain (linux + macos) into
# the gui-aima bbox.json format prepare_zoom_sft_v2.py consumes. CPU-only,
# no GPU needed. Submit from the REPO ROOT.

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
GUIAIMA="${ROOT}/gui_aima_like_training_data/datasets/gui-aima-data/extracted/gui-aima-data"
OSA="${GUIAIMA}/OSAtlas-Desktop"
mkdir -p "${OSA}" "${ROOT}/training/logs"

echo "job_id=${SLURM_JOB_ID:-manual} started_at=$(date -Is)"

echo "=== downloading json annotations ==="
curl -sL --retry 5 --retry-delay 5 -o "${OSA}/linux_splited.json" \
  "https://huggingface.co/datasets/OS-Copilot/OS-Atlas-data/resolve/main/desktop_domain/linux_splited.json"
curl -sL --retry 5 --retry-delay 5 -o "${OSA}/macos_splited.json" \
  "https://huggingface.co/datasets/OS-Copilot/OS-Atlas-data/resolve/main/desktop_domain/macos_splited.json"

echo "=== downloading images (linux 3.1G, macos 5.5G) ==="
time curl -sL --retry 5 --retry-delay 5 -o "${OSA}/linux_images.zip" \
  "https://huggingface.co/datasets/OS-Copilot/OS-Atlas-data/resolve/main/desktop_domain/linux_images.zip"
time curl -sL --retry 5 --retry-delay 5 -o "${OSA}/macos_images.zip" \
  "https://huggingface.co/datasets/OS-Copilot/OS-Atlas-data/resolve/main/desktop_domain/macos_images.zip"

echo "=== extracting ==="
mkdir -p "${OSA}/linux_images" "${OSA}/macos_images"
unzip -q -o "${OSA}/linux_images.zip" -d "${OSA}/linux_images"
unzip -q -o "${OSA}/macos_images.zip" -d "${OSA}/macos_images"
echo "linux images: $(find "${OSA}/linux_images" -type f | wc -l)"
echo "macos images: $(find "${OSA}/macos_images" -type f | wc -l)"

echo "=== converting to gui-aima bbox.json ==="
python3 "${ROOT}/training/tools/convert_osatlas_desktop.py" \
  --sources "linux:${OSA}/linux_splited.json" "macos:${OSA}/macos_splited.json" \
  --out "${GUIAIMA}/osatlas_desktop_bbox.json"

rm -f "${OSA}/linux_images.zip" "${OSA}/macos_images.zip"
echo "finished_at=$(date -Is)"
