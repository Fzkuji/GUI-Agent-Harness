#!/bin/bash
# Run OSWorld tasks 41-51 sequentially with Opus model
# Usage: bash run_batch.sh [start] [end]

START=${1:-41}
END=${2:-51}
VM="172.16.82.132"
MAX_STEPS=15
LOG_DIR="/tmp/osworld_batch"

mkdir -p "$LOG_DIR"

echo "=== Running tasks $START to $END ==="
echo "Logs: $LOG_DIR/"
echo ""

for i in $(seq $START $END); do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Starting Task $i at $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    python3 benchmarks/osworld/run_osworld_task.py "$i" --vm "$VM" --max-steps "$MAX_STEPS" \
        > "$LOG_DIR/task${i}.log" 2>&1
    
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
