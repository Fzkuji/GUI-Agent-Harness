#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

PYTHON_BIN=".venv/bin/python"
CONFIG="benchmarks/osworld/config/gimp_fixed.json"

export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/false
export SSH_ASKPASS=/bin/false
export SUDO_ASKPASS=/bin/false
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
export OSWORLD_BENCHMARK_FIXED=1

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing fixed Python interpreter: $PYTHON_BIN" >&2
  exit 2
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: benchmarks/osworld/run_gimp_fixed.sh <task_num> [extra run_osworld_task.py args]" >&2
  exit 2
fi

exec "$PYTHON_BIN" benchmarks/osworld/run_osworld_task.py "$1" --run-config "$CONFIG" "${@:2}"
