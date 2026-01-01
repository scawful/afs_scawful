#!/bin/bash
# Remote training trigger for Windows RTX 5060 Ti
# Usage: ./train_remote.sh [--epochs N] [--watch]
set -e

HOST="${HOST:-medical-mechanica}"
TRAINING_DIR="D:\\afs_training"
LOG_FILE="/tmp/afs_training.log"

EPOCHS=3
BATCH_SIZE=4
WATCH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --epochs)
            EPOCHS="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --watch)
            WATCH=true
            shift
            ;;
        --status)
            echo "Checking training status..."
            ssh $HOST "type ${TRAINING_DIR}\\logs\\training.log 2>nul || echo No active training"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--epochs N] [--batch-size N] [--watch] [--status]"
            exit 1
            ;;
    esac
done

echo "========================================="
echo "AFS Remote Training (Windows RTX 5060 Ti)"
echo "Epochs: $EPOCHS, Batch size: $BATCH_SIZE"
echo "========================================="

# Check GPU is accessible
echo "Checking GPU..."
ssh $HOST "python -c \"import torch; assert torch.cuda.is_available(), 'No CUDA'; print('GPU:', torch.cuda.get_device_name(0))\""

# Start training
echo ""
echo "Starting training..."
ssh $HOST "python ${TRAINING_DIR}\\scripts\\train_peft.py --epochs $EPOCHS --batch-size $BATCH_SIZE" 2>&1 | tee "$LOG_FILE" &
TRAIN_PID=$!

if $WATCH; then
    echo "Watching training progress (Ctrl+C to detach)..."
    wait $TRAIN_PID
else
    echo ""
    echo "Training started in background (PID: $TRAIN_PID)"
    echo "Log: $LOG_FILE"
    echo ""
    echo "To watch: tail -f $LOG_FILE"
    echo "To check: $0 --status"
fi
