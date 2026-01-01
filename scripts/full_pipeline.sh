#!/bin/bash
# Full autonomous training, testing, and iteration pipeline
# Handles: training completion → conversion → testing → fixes → retraining if needed

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$HOME/.context/logs"
mkdir -p "$LOG_DIR"

MAIN_LOG="$LOG_DIR/full_pipeline_$(date +%Y%m%d_%H%M%S).log"
HOST="${HOST:-medical-mechanica}"
WIN_TRAINING_DIR="D:\\afs_training"
MAC_TRAINING_DIR="$HOME/Mounts/mm-d/afs_training"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$MAIN_LOG"
}

error() {
    log "ERROR: $1"
    exit 1
}

# Check if training is still running
is_training_running() {
    ssh $HOST "tasklist 2>nul | findstr python" 2>/dev/null | grep -q python
    return $?
}

# Wait for training to complete
wait_for_training() {
    log "Waiting for training to complete..."
    local count=0
    while is_training_running; do
        count=$((count + 1))
        if [ $((count % 12)) -eq 0 ]; then  # Log every hour
            log "Still training... (${count}x5min = $((count * 5)) min elapsed)"
        fi
        sleep 300
    done
    log "Training completed!"
}

# Find latest model directory
find_latest_model() {
    ls -td "$MAC_TRAINING_DIR"/models/afs_scawful_* 2>/dev/null | head -1
}

# Convert model to GGUF
convert_to_gguf() {
    local model_dir="$1"
    log "Converting to GGUF: $model_dir"

    cd "$PROJECT_DIR"

    # Check if merged_model exists
    if [ ! -d "$model_dir/merged_model" ]; then
        error "merged_model directory not found in $model_dir"
    fi

    # Install llama-cpp-python if needed
    pip3 show llama-cpp-python >/dev/null 2>&1 || pip3 install llama-cpp-python

    # Convert
    python3 scripts/convert_to_gguf.py "$model_dir" --quant Q4_K_M 2>&1 | tee -a "$MAIN_LOG"

    # Return GGUF path
    echo "$model_dir/gguf/"*.gguf | head -1
}

# Run comprehensive tests
run_tests() {
    local gguf_path="$1"
    log "Running comprehensive tests on: $gguf_path"

    local results_file="$LOG_DIR/test_results_$(date +%Y%m%d_%H%M%S).json"

    # Create Ollama model for testing
    log "Creating Ollama model for testing..."
    cat > /tmp/afs_test_modelfile << EOF
FROM $gguf_path
PARAMETER temperature 0.7
PARAMETER top_p 0.9
SYSTEM "You are an expert in 65816 assembly language and A Link to the Past ROM hacking."
EOF

    ollama create afs_test -f /tmp/afs_test_modelfile 2>&1 | tee -a "$MAIN_LOG"

    # Test 1: Basic ASM understanding
    log "Test 1: ASM Understanding"
    local test1=$(ollama run afs_test "Explain what LDA \$0E20,X does in 65816 assembly" 2>&1)
    echo "$test1" | tee -a "$MAIN_LOG"

    local test1_pass=0
    if echo "$test1" | grep -qiE "load|accumulator|address|index"; then
        test1_pass=1
        log "Test 1: PASS"
    else
        log "Test 1: FAIL - Missing key concepts"
    fi

    # Test 2: Code generation
    log "Test 2: Code Generation"
    local test2=$(ollama run afs_test "Write a 65816 routine that adds 10 to the value at address \$0100" 2>&1)
    echo "$test2" | tee -a "$MAIN_LOG"

    local test2_pass=0
    if echo "$test2" | grep -qiE "LDA|ADC|STA|CLC"; then
        test2_pass=1
        log "Test 2: PASS"
    else
        log "Test 2: FAIL - Missing assembly instructions"
    fi

    # Test 3: ALTTP knowledge
    log "Test 3: ALTTP Knowledge"
    local test3=$(ollama run afs_test "What is stored at WRAM address \$0E20 in A Link to the Past?" 2>&1)
    echo "$test3" | tee -a "$MAIN_LOG"

    local test3_pass=0
    if echo "$test3" | grep -qiE "sprite|enemy|hp|health|damage"; then
        test3_pass=1
        log "Test 3: PASS"
    else
        log "Test 3: FAIL - Missing ALTTP knowledge"
    fi

    # Test 4: Tool calling format
    log "Test 4: Tool Calling"
    local test4=$(ollama run afs_test "Using yaze tools, read 16 bytes from ROM address 0x008000" 2>&1)
    echo "$test4" | tee -a "$MAIN_LOG"

    local test4_pass=0
    if echo "$test4" | grep -qiE "read|rom|8000|bytes"; then
        test4_pass=1
        log "Test 4: PASS"
    else
        log "Test 4: FAIL - Missing tool calling concepts"
    fi

    # Test 5: Optimization
    log "Test 5: Optimization"
    local test5=$(ollama run afs_test "Optimize this 65816 code: LDA #\$00 / STA \$00 / LDA #\$00 / STA \$01" 2>&1)
    echo "$test5" | tee -a "$MAIN_LOG"

    local test5_pass=0
    if echo "$test5" | grep -qiE "STZ|optimize|cycle|redundant"; then
        test5_pass=1
        log "Test 5: PASS"
    else
        log "Test 5: FAIL - Missing optimization insight"
    fi

    # Calculate score
    local total_pass=$((test1_pass + test2_pass + test3_pass + test4_pass + test5_pass))
    local score=$((total_pass * 20))

    log "========================================="
    log "TEST RESULTS: $total_pass/5 passed ($score%)"
    log "========================================="

    # Cleanup
    ollama rm afs_test 2>/dev/null || true

    # Save results
    cat > "$results_file" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "model": "$gguf_path",
    "tests": {
        "asm_understanding": $test1_pass,
        "code_generation": $test2_pass,
        "alttp_knowledge": $test3_pass,
        "tool_calling": $test4_pass,
        "optimization": $test5_pass
    },
    "total_passed": $total_pass,
    "score_percent": $score
}
EOF

    log "Results saved to: $results_file"

    # Return pass/fail threshold (60% = 3/5 tests)
    [ $total_pass -ge 3 ]
}

# Trigger cloud training if local model quality is poor
trigger_cloud_training() {
    log "Triggering Vultr cloud GPU training..."

    cd "$PROJECT_DIR/infra"

    if [ -z "$VULTR_API_KEY" ]; then
        log "VULTR_API_KEY not set, checking secrets file..."
        if [ -f "$HOME/.secrets" ]; then
            source "$HOME/.secrets"
        fi
    fi

    if [ -z "$VULTR_API_KEY" ]; then
        error "VULTR_API_KEY not available. Set it or add to ~/.secrets"
    fi

    ./deploy.sh --hours 3 2>&1 | tee -a "$MAIN_LOG"
}

# Main pipeline
main() {
    log "========================================="
    log "FULL TRAINING PIPELINE STARTED"
    log "========================================="

    # Step 1: Wait for current training
    if is_training_running; then
        wait_for_training
    else
        log "No active training detected"
    fi

    # Step 2: Find latest model
    local model_dir=$(find_latest_model)
    if [ -z "$model_dir" ]; then
        error "No trained model found"
    fi
    log "Found model: $model_dir"

    # Step 3: Convert to GGUF
    local gguf_path=$(convert_to_gguf "$model_dir")
    if [ -z "$gguf_path" ] || [ ! -f "$gguf_path" ]; then
        error "GGUF conversion failed"
    fi
    log "GGUF created: $gguf_path"

    # Step 4: Run tests
    if run_tests "$gguf_path"; then
        log "========================================="
        log "MODEL PASSED QUALITY CHECKS!"
        log "========================================="
        log "Model ready for deployment: $gguf_path"

        # Optional: Start 3B training
        log "Starting 3B model training..."
        ssh $HOST "python ${WIN_TRAINING_DIR}\\scripts\\train_3b.py --epochs 3" 2>&1 | tee -a "$MAIN_LOG" &

    else
        log "========================================="
        log "MODEL FAILED QUALITY CHECKS"
        log "========================================="
        log "Consider:"
        log "  1. Adding more training data"
        log "  2. Training for more epochs"
        log "  3. Using larger base model (3B/7B)"

        # Could trigger cloud training here if needed
        # trigger_cloud_training
    fi

    log "Pipeline complete. Log: $MAIN_LOG"
}

# Run if executed directly
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
