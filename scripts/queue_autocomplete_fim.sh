#!/bin/bash
# Queue a FIM run once the prefix training completes.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${LOG:-$HOME/Mounts/mm-d/afs_training/logs/training_autocomplete.log}"
HOST="${HOST:-medical-mechanica}"
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-Coder-1.5B}"
TRAIN_FILE="${TRAIN_FILE:-D:\\afs_training\\datasets\\lsp_fim_train.jsonl}"
VAL_FILE="${VAL_FILE:-D:\\afs_training\\datasets\\lsp_fim_val.jsonl}"
LOG_FILE="${LOG_FILE:-training_fim_autocomplete.log}"

while true; do
  if [[ -f "$LOG" ]] && rg -q "Mode: prefix" "$LOG" && rg -q "TRAINING COMPLETE" "$LOG"; then
    break
  fi
  sleep 60
done

"$SCRIPT_DIR/train_autocomplete_remote.sh" \
  --model-name "$MODEL_NAME" \
  --epochs 1 \
  --host "$HOST" \
  --batch-size 4 \
  --grad-accum 4 \
  --max-length 1024 \
  --mode fim \
  --train-file "$TRAIN_FILE" \
  --val-file "$VAL_FILE" \
  --log-file "$LOG_FILE" \
  --detach

echo "$(date) queued fim" >> "$HOME/Mounts/mm-d/afs_training/logs/queue_autocomplete.log"
