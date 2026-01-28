# ASM Model Training Status (ALTTP / 65816)

Last updated: 2026-01-01 09:07 UTC
Status: ✅ TRAINING ACTIVE (Single Node)

## Active Training Runs

### 1. Cloud: Vultr A100 (20GB)
**Instance:** `107.191.41.64` (ewr)
**Resources:** NVIDIA A100 20GB (Slice), 6 vCPUs, 6GB RAM
**Current Job:** `Qwen/Qwen2.5-Coder-7B-Instruct`
*   **Status:** 🟢 Running (PID 3284)
*   **Config:** QLoRA 4-bit, Batch 1, GradAccum 8, LR 2e-4
*   **Log:** `/opt/training/training_7b_v3.log`
*   **Output:** `/opt/training/models/7b_asm_v3`
*   **Notes:** Restarted fresh (v3) after v2 checkpoint corruption. 14B model attempt failed (OOM on 20GB).

**Safety:** Auto-shutdown scheduled for 2026-01-01 16:15 UTC (~7h).

### 2. Local: Windows (RTX 5060 Ti)
**Host:** `medical-mechanica`
**Status:** 🛑 **STOPPED**
*   **Reason:** Performance insufficient for 1.5B training (thrashing). Abandoned.

## Dataset
**Source:** Consolidated ASM Dataset (`vultr_train_full.jsonl`)
**Count:** 28,707 records (Cleaned)
**Location:** `/opt/training/datasets/train.jsonl`

## Infrastructure Notes
*   **Vultr SSH:** `scripts/ssh_gpu.sh` (Password-auth wrapper)
*   **Deployment:** `lab/afs-scawful/infra/deploy.sh` (Updated with SSH/AT fixes)
*   **Scripts:** `lab/afs-scawful/scripts/train_peft_v2.py` (Universal trainer, supports `--model-name`)

## Next Actions
1.  Monitor Vultr logs: `./scripts/ssh_gpu.sh "tail -f /opt/training/training_7b_v3.log"`
2.  Wait for completion (~10 hours).
3.  Download model:
    `scp -r root@107.191.41.64:/opt/training/models/7b_asm_v3 ./models/`
