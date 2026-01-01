#!/bin/bash
# Quick training status check

LOG="/tmp/afs_training.log"
WINDOWS_LOG="D:\\afs_training\\logs\\training.log"
HOST="${HOST:-medical-mechanica}"

echo "=== AFS Training Status ==="
echo ""

# Check local log first
if [ -f "$LOG" ]; then
    PROGRESS=$(tail -20 "$LOG" | grep -oE "[0-9]+%" | tail -1)
    LOSS=$(tail -100 "$LOG" | grep "'loss'" | tail -1 | grep -oE "loss': [0-9.]+" | cut -d' ' -f2)
    EPOCH=$(tail -100 "$LOG" | grep "'epoch'" | tail -1 | grep -oE "epoch': [0-9.]+" | cut -d' ' -f2)

    echo "Progress: ${PROGRESS:-Unknown}"
    echo "Loss:     ${LOSS:-N/A}"
    echo "Epoch:    ${EPOCH:-N/A}"
    echo ""
    echo "Last lines:"
    tail -3 "$LOG" | grep -E "%|loss"
else
    # Try Windows directly
    echo "Checking Windows training..."
    ssh "$HOST" "type ${WINDOWS_LOG} 2>nul | find /v \"\" /c" 2>/dev/null || echo "No active training found"
fi
