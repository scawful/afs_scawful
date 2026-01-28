# ASM Model Training Run: 2025-12-31 / 2026-01-01

## Executive Summary
We are conducting a multi-model training experiment to fine-tune Qwen 2.5 Coder on 65816 Assembly (SNES).
The goal is to compare the performance of 1.5B, 7B, and 14B parameter models on the specific task of generating ASM code from comments.

## Architecture
**Base Models:**
*   `Qwen/Qwen2.5-Coder-1.5B-Instruct` (Fast, baseline)
*   `Qwen/Qwen2.5-Coder-7B-Instruct` (Reasoning-heavy, standard)
*   `Qwen/Qwen2.5-Coder-14B-Instruct` (Large, experimental for 20GB VRAM)

**Method:**
*   **PEFT / QLoRA:** 4-bit quantization (NF4), bfloat16 compute.
*   **Target Modules:** All linear layers (`q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`).
*   **Rank (r):** 16
*   **Alpha:** 32

## Deployment Details

### 1. Cloud Infrastructure (Vultr)
*   **Instance Type:** `vcg-a100-1c-6g-4vram` (NVIDIA A100 20GB slice)
*   **Cost:** ~$1.29/hr
*   **Setup:**
    *   OS: Ubuntu 24.04 LTS
    *   Env: Python 3.12 venv (`/opt/training/venv`)
    *   Libs: PyTorch 2.5, Transformers 4.37+, PEFT, BitsAndBytes
*   **Access:**
    *   IP: `107.191.41.64`
    *   User: `root`
    *   Tool: `./scripts/ssh_gpu.sh`

### 2. Windows Infrastructure
*   **Host:** `medical-mechanica`
*   **GPU:** RTX 5060 Ti (16GB)
*   **Role:** Dedicated 1.5B model trainer.

## Automation & Scripts

### `train_peft_v2.py`
The unified training script located in `lab/afs-scawful/scripts/`.
*   **Features:**
    *   Supports `--model-name` argument.
    *   Uses **ChatML** template (`<|im_start|>system...`) instead of Alpaca.
    *   Optimized defaults (LR 3e-4, BF16).
    *   Argument parsing for `data-dir` and `output`.

### `queue_14b.sh` (Vultr)
A simple bash loop running on the cloud instance to serialize jobs.
```bash
#!/bin/bash
TARGET_PID=85779 # 7B Model PID
while kill -0 "$TARGET_PID" 2>/dev/null; do sleep 60; done
# ... Launch 14B training ...
```

## Logs & Monitoring

**Vultr (7B & 14B):**
```bash
# Check 7B progress
./scripts/ssh_gpu.sh "tail -f /opt/training/training_7b.log"

# Check Queue Status
./scripts/ssh_gpu.sh "ps aux | grep queue"

# Check GPU Usage
./scripts/ssh_gpu.sh "nvidia-smi"
```

**Windows (1.5B):**
```bash
ssh medical-mechanica "type D:\\afs_training\\logs\\training_v2.log"
# If empty, check Task Manager for python.exe
```

## Recovery / Retrieval
When training completes (or before 16:15 UTC shutdown):
1.  **Stop Queue:** `kill <queue_pid>` on Vultr.
2.  **Download Adapters:**
    ```bash
    scp -r root@107.191.41.64:/opt/training/models/7b_asm_v1 ./models/
    ```
3.  **Merge:**
    The script auto-saves `lora_adapters` and `merged_model`. Download `merged_model` for immediate use with Ollama/Llama.cpp.

```
