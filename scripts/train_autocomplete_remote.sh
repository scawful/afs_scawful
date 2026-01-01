#!/bin/bash
# Remote training trigger for Windows RTX 5060 Ti (autocomplete/LSP)
set -e

HOST="${HOST:-medical-mechanica}"
TRAINING_DIR="D:\\afs_training"
MOUNT_DIR="$HOME/Mounts/mm-d/afs_training"
LOG_FILE="/tmp/afs_autocomplete.log"

MODEL_NAME="Qwen/Qwen2.5-Coder-0.5B"
EPOCHS=1
BATCH_SIZE=4
GRAD_ACCUM=4
MAX_LENGTH=1024
MODE="auto"
TRAIN_FILE=""
VAL_FILE=""
OUTPUT=""
LOG_NAME="training_autocomplete.log"
WATCH=false
DETACH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --epochs)
            EPOCHS="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --grad-accum)
            GRAD_ACCUM="$2"
            shift 2
            ;;
        --max-length)
            MAX_LENGTH="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --train-file)
            TRAIN_FILE="$2"
            shift 2
            ;;
        --val-file)
            VAL_FILE="$2"
            shift 2
            ;;
        --log-file)
            LOG_NAME="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        --watch)
            WATCH=true
            shift
            ;;
        --detach)
            DETACH=true
            shift
            ;;
        --status)
            echo "Checking training status..."
            ssh $HOST "type ${TRAINING_DIR}\\logs\\training.log 2>nul || echo No active training"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--model-name NAME] [--epochs N] [--host HOST] [--batch-size N] [--grad-accum N] \\"
            echo "          [--max-length N] [--mode prefix|fim|auto] [--train-file PATH] [--val-file PATH] \\"
            echo "          [--log-file NAME|PATH] [--output PATH] [--watch] [--detach] [--status]"
            exit 1
            ;;
    esac
done

if [[ -z "$TRAIN_FILE" ]]; then
    TRAIN_FILE="${TRAINING_DIR}\\datasets\\train.jsonl"
fi

if [[ -z "$VAL_FILE" ]]; then
    VAL_FILE="${TRAINING_DIR}\\datasets\\val.jsonl"
fi

REMOTE_CMD="python ${TRAINING_DIR}\\scripts\\train_autocomplete.py"
REMOTE_CMD+=" --model-name \"$MODEL_NAME\""
REMOTE_CMD+=" --epochs $EPOCHS"
REMOTE_CMD+=" --batch-size $BATCH_SIZE"
REMOTE_CMD+=" --gradient-accumulation-steps $GRAD_ACCUM"
REMOTE_CMD+=" --max-length $MAX_LENGTH"
REMOTE_CMD+=" --mode $MODE"
REMOTE_CMD+=" --train-file \"$TRAIN_FILE\""
REMOTE_CMD+=" --val-file \"$VAL_FILE\""

REMOTE_LOG="${TRAINING_DIR}\\logs\\${LOG_NAME}"
if [[ "$LOG_NAME" == *:\\* || "$LOG_NAME" == *\\* ]]; then
    REMOTE_LOG="$LOG_NAME"
fi

if [[ -n "$OUTPUT" ]]; then
    REMOTE_CMD+=" --output \"$OUTPUT\""
fi

if $DETACH; then
    RUN_SCRIPT_LOCAL="${MOUNT_DIR}/scripts/run_autocomplete.cmd"
    RUN_SCRIPT_WIN="${TRAINING_DIR}\\scripts\\run_autocomplete.cmd"
    TASK_NAME="AFS_Autocomplete_Train"
    if [[ -d "$MOUNT_DIR/scripts" ]]; then
        {
            printf '@echo off\r\n'
            printf 'python %s\\scripts\\train_autocomplete.py --model-name %s --epochs %s --batch-size %s --gradient-accumulation-steps %s --max-length %s --mode %s --train-file %s --val-file %s' \
                "${TRAINING_DIR}" "${MODEL_NAME}" "${EPOCHS}" "${BATCH_SIZE}" "${GRAD_ACCUM}" "${MAX_LENGTH}" "${MODE}" "${TRAIN_FILE}" "${VAL_FILE}"
            if [[ -n "$OUTPUT" ]]; then
                printf ' --output %s' "${OUTPUT}"
            fi
            printf ' > %s 2>&1\r\n' "${REMOTE_LOG}"
        } > "$RUN_SCRIPT_LOCAL"
    else
        echo "Windows mount not found at $MOUNT_DIR; writing run script over SSH."
        CMD_CONTENT=$(
            printf '@echo off\r\n'
            printf 'python %s\\scripts\\train_autocomplete.py --model-name %s --epochs %s --batch-size %s --gradient-accumulation-steps %s --max-length %s --mode %s --train-file %s --val-file %s' \
                "${TRAINING_DIR}" "${MODEL_NAME}" "${EPOCHS}" "${BATCH_SIZE}" "${GRAD_ACCUM}" "${MAX_LENGTH}" "${MODE}" "${TRAIN_FILE}" "${VAL_FILE}"
            if [[ -n "$OUTPUT" ]]; then
                printf ' --output %s' "${OUTPUT}"
            fi
            printf ' > %s 2>&1\r\n' "${REMOTE_LOG}"
        )
        CMD_B64=$(printf '%s' "$CMD_CONTENT" | base64 | tr -d '\n')
        ssh "$HOST" "powershell -NoProfile -Command \"[IO.File]::WriteAllText('${RUN_SCRIPT_WIN}', [Text.Encoding]::ASCII.GetString([Convert]::FromBase64String('${CMD_B64}')))\""
    fi

    echo "Launching detached training on Windows..."
    ssh "$HOST" "schtasks /create /tn ${TASK_NAME} /tr \"cmd /c ${RUN_SCRIPT_WIN}\" /sc once /st 00:00 /sd 01/01/2026 /f"
    ssh "$HOST" "schtasks /run /tn ${TASK_NAME}"
    echo "Detached. Remote log: ${REMOTE_LOG}"
    echo "Task name: ${TASK_NAME} (delete with: schtasks /delete /tn ${TASK_NAME} /f)"
    exit 0
fi

echo "========================================="
echo "AFS Remote Autocomplete Training"
echo "Model: $MODEL_NAME"
echo "Epochs: $EPOCHS, Batch size: $BATCH_SIZE"
echo "Max length: $MAX_LENGTH, Mode: $MODE"
echo "========================================="

echo "Checking GPU..."
ssh $HOST "python -c \"import torch; assert torch.cuda.is_available(), 'No CUDA'; print('GPU:', torch.cuda.get_device_name(0))\""

echo ""
echo "Starting training..."
ssh $HOST "$REMOTE_CMD" 2>&1 | tee "$LOG_FILE" &
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
fi
