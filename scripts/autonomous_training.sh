#!/bin/bash
# Autonomous training pipeline - runs multiple model trainings
# Created for NYE 2024 autonomous run

set -e

LOG_DIR="$HOME/.context/logs"
mkdir -p "$LOG_DIR"
MAIN_LOG="$LOG_DIR/autonomous_training.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$MAIN_LOG"
}

HOST="${HOST:-medical-mechanica}"
TRAINING_DIR="D:\\afs_training"
MODELS_DIR="$HOME/Mounts/mm-d/afs_training/models"

# Models to train in order
MODELS=(
    "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    "Qwen/Qwen2.5-Coder-3B-Instruct"
)

wait_for_training() {
    log "Waiting for current training to complete..."
    while true; do
        # Check if training process is still running
        if ! ssh $HOST "tasklist | findstr python" 2>/dev/null | grep -q python; then
            log "Training process completed"
            break
        fi
        sleep 300  # Check every 5 minutes
    done
}

convert_to_gguf() {
    local model_dir="$1"
    log "Converting $model_dir to GGUF..."

    cd ~/src/lab/afs_scawful
    python scripts/convert_to_gguf.py "$model_dir" --quant Q4_K_M 2>&1 | tee -a "$MAIN_LOG"
}

evaluate_model() {
    local gguf_path="$1"
    log "Evaluating model: $gguf_path"

    # Quick smoke test
    if command -v ollama &> /dev/null; then
        # Create temp modelfile
        cat > /tmp/test_modelfile << EOF
FROM $gguf_path
PARAMETER temperature 0.7
SYSTEM "You are an expert in 65816 assembly."
EOF
        ollama create afs_test -f /tmp/test_modelfile 2>&1 | tee -a "$MAIN_LOG"

        # Test prompt
        log "Test prompt: Explain LDA \$0E20,X"
        ollama run afs_test "Explain: LDA \$0E20,X" 2>&1 | head -20 | tee -a "$MAIN_LOG"

        ollama rm afs_test 2>/dev/null || true
    else
        log "Ollama not available, skipping eval"
    fi
}

train_model() {
    local model_name="$1"
    local epochs="${2:-3}"

    log "Starting training: $model_name (epochs: $epochs)"

    # Update train script to use new model
    ssh $HOST "cd ${TRAINING_DIR} && python scripts\\train_peft.py --epochs $epochs --batch-size 4" 2>&1 | tee -a "$MAIN_LOG"

    log "Training completed for $model_name"
}

main() {
    log "========================================="
    log "AUTONOMOUS TRAINING PIPELINE STARTED"
    log "Happy New Year 2025!"
    log "========================================="

    # Step 1: Wait for current 1.5B training to complete
    log "Phase 1: Waiting for 1.5B training..."
    wait_for_training

    # Step 2: Find the latest model and convert
    log "Phase 2: Converting to GGUF..."
    LATEST_MODEL=$(ls -td "$MODELS_DIR"/afs_scawful_* 2>/dev/null | head -1)
    if [ -n "$LATEST_MODEL" ]; then
        convert_to_gguf "$LATEST_MODEL"

        # Find GGUF
        GGUF_PATH=$(ls "$LATEST_MODEL"/gguf/*.gguf 2>/dev/null | head -1)
        if [ -n "$GGUF_PATH" ]; then
            evaluate_model "$GGUF_PATH"
        fi
    fi

    # Step 3: Generate more training data
    log "Phase 3: Generating CoT examples..."
    cd ~/src/lab/afs_scawful
    python scripts/generate_cot_examples.py --count 500 --output ~/.context/training/datasets/cot_examples.jsonl 2>&1 | tee -a "$MAIN_LOG"

    log "========================================="
    log "AUTONOMOUS PIPELINE COMPLETE"
    log "========================================="
    log "Results:"
    log "  - Model: $LATEST_MODEL"
    log "  - GGUF: $GGUF_PATH"
    log "  - CoT examples: ~/.context/training/datasets/cot_examples.jsonl"
}

main "$@"
