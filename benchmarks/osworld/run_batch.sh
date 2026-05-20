#!/bin/bash
# Run OSWorld tasks sequentially
# Usage: bash run_batch.sh [start] [end] [domain]

START=${1:-1}
END=${2:-10}
DOMAIN=${3:-multi_apps}
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
RUN_CONFIG="${OSWORLD_RUN_CONFIG:-}"
MAX_STEPS="${MAX_STEPS:-15}"
LOG_DIR="/tmp/osworld_batch_${DOMAIN}"

export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/false
export SSH_ASKPASS=/bin/false
export SUDO_ASKPASS=/bin/false
export OSWORLD_BENCHMARK_FIXED=1

mkdir -p "$LOG_DIR"

echo "=== Running ${DOMAIN} tasks $START to $END ==="
echo "Logs: $LOG_DIR/"
echo ""

for i in $(seq $START $END); do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Starting Task $i at $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    CMD=("$PYTHON_BIN" benchmarks/osworld/run_osworld_task.py "$i" --domain "$DOMAIN" --max-steps "$MAX_STEPS")
    if [ -n "$RUN_CONFIG" ]; then
        CMD+=("--run-config" "$RUN_CONFIG")
    fi
    "${CMD[@]}" > "$LOG_DIR/task${i}.log" 2>&1

    # Extract score from log
    SCORE=$(grep -o 'Score: [0-9.]*' "$LOG_DIR/task${i}.log" | tail -1 | awk '{print $2}')
    STEPS=$(grep -o 'Steps: [0-9]*' "$LOG_DIR/task${i}.log" | tail -1 | awk '{print $2}')
    TIME=$(grep -o 'Total: [0-9.]*s' "$LOG_DIR/task${i}.log" | tail -1)

    if [ -z "$SCORE" ]; then
        echo "Task $i: ERROR (no score found)"
    else
        echo "Task $i: Score=$SCORE Steps=$STEPS $TIME"
    fi
    echo ""
done

echo "=== Batch complete ==="
echo ""
echo "Summary:"
for i in $(seq $START $END); do
    SCORE=$(grep -o 'Score: [0-9.]*' "$LOG_DIR/task${i}.log" | tail -1 | awk '{print $2}')
    if [ -z "$SCORE" ]; then
        echo "  Task $i: ERROR"
    elif [ "$SCORE" = "1.000" ]; then
        echo "  Task $i: ✅ $SCORE"
    elif [ "$SCORE" = "0.000" ]; then
        echo "  Task $i: ❌ $SCORE"
    else
        echo "  Task $i: ⚠️  $SCORE"
    fi
done
