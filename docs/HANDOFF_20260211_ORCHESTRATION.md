# Handoff: Oracle Orchestration & Model Staging (2026-02-11)

## Executive Summary
Veran v1 staging artifacts were mostly generated correctly, but several claims needed correction before execution on Windows. Sync is now complete to `medical-mechanica`, a Windows-compatible PEFT dataset was prepared, and a live training task is running.

## Accuracy Review (Codex, 2026-02-11)

### Verified
- `afs/training_data/veran_v1_synthetic.jsonl` exists with **585** rows.
- `afs/training_data/veran_v1_gold.jsonl` exists with **5** rows and contains the expected `maku_tree.asm` / `water_collision.asm` logic samples.
- `afs/knowledge/label_index.csv` has **1930** lines (header + 1929 labels), matching the stated label count.
- `scripts/agentic_preflight.sh` and `afs-scawful/scripts/verify_rom.py` exist and are wired together.
- `scripts/sync_training_data.sh` exists and sync queue entries were created for `medical-mechanica`.

### Corrected / Caveats
- `afs-scawful/config/veran-v1.yaml` was not directly runnable on Windows as synced:
  - It references local Mac paths (`afs/training_data/...`).
  - It assumes Axolotl, but **Axolotl is not installed** on `medical-mechanica`.
- The statement "optimized for RTX 5060 Ti (16GB) using 14B + r=128" is not aligned with local strategy notes (`docs/MODEL_STRATEGY.md` indicates 16GB is a better fit for 7B full-rank LoRA).
- "Full audit of `HappinessPondRupees` passed" was over-stated:
  - `scripts/run_agentic_eval.py` currently performs static patch-byte validation fallback if Mesen2 socket is unavailable.
  - no persisted artifact/report proving a full functional Mesen2 audit was found.
- NERV queue had duplicate dataset entries; all queued transfers were successfully drained.

## Actions Completed In This Continuation

1. Drained `nerv-xfer` queue and verified all Veran artifacts synced to `medical-mechanica`.
2. Built Windows PEFT training dataset:
   - Output dir: `afs/training_data/veran_v1_peft_windows`
   - Format: `instruction` / `input` / `output`
   - Composition: 585 synthetic + 5 gold oversampled 20x (=100) = **685 total**
   - Split: **651 train / 34 val**
3. Synced `veran_v1_peft_windows` dataset bundle to:
   - `D:\models\datasets-models\veran_v1_peft_windows`
4. Launched live Windows training via scheduled task:
   - Task: `AFS_Veran_v1_PEFT`
   - Command target: `D:\src\lab\afs-scawful\scripts\train_peft_v2.py`
   - Model: `Qwen/Qwen2.5-Coder-7B-Instruct`
   - Data dir: `D:\models\datasets-models\veran_v1_peft_windows`
   - Logs: `D:\afs_training\logs\veran_v1_peft_20260210_224921.log` and `.err.log`
   - Checkpoint out: `D:\models\checkpoints\veran_v1_peft_20260210_224921`

## Current Status
- `AFS_Veran_v1_PEFT` status: **Running**
- Active process observed: `python.exe` (training command line includes `train_peft_v2.py`)
- Log shows initialization reached:
  - `Initializing Training: Qwen/Qwen2.5-Coder-7B-Instruct (ChatML) | LR: 0.0001`

## Updated Next Steps
1. Monitor `AFS_Veran_v1_PEFT` until completion/failure.
2. If the Windows run stalls or errors out, pivot to `vast.ai` using existing Vast scripts (`docs/VAST_SETUP.md`).
3. After completion, evaluate and register the artifact in `config/chat_registry.toml`.
4. Keep Yaze sidebar work (`docs/YAZE_AI_INTEGRATION.md`) as a separate track from training ops.

## Eval Preparation (Added 2026-02-11)

- New eval script:
  - `afs-scawful/scripts/eval_veran_peft.py`
  - Runs adapter-based eval directly against `Qwen/Qwen2.5-Coder-7B-Instruct`
  - Supports `reference` and `keywords` cases, writes summary + per-case JSON report.
- New eval suites:
  - `afs/training_data/veran_v1_eval_quick_keywords.jsonl` (12 fast keyword checks)
  - `afs/training_data/veran_v1_eval_holdout.jsonl` (34 held-out reference cases)
- New launcher:
  - `scripts/launch_veran_eval_windows.sh`
  - Syncs eval assets to Windows and starts task `AFS_Veran_v1_Eval`.
  - Default behavior waits for `adapter_model.safetensors`, then runs quick + holdout suites.
- Current eval task status:
  - `AFS_Veran_v1_Eval`: **Running** (waiting for adapters)
  - Log: `D:\afs_training\logs\veran_v1_eval_20260210_230105.log`
  - Results (when done):
    - `D:\afs_training\evals\veran_v1\results_quick_20260210_230105.json`
    - `D:\afs_training\evals\veran_v1\results_holdout_20260210_230105.json`

## EchoFlow Continuation (Added 2026-02-11)

- Completed follow-on app integration work for EchoFlow personality/runtime:
  - Added strict JSON mode as a persisted intelligence setting and runtime sidebar toggle.
  - Wired provider-specific JSON request enforcement:
    - Gemini: `generationConfig.responseMimeType = application/json`
    - Ollama: `format = json`
    - LM Studio: `response_format = { type: json_object }`
  - Updated model defaults and runtime wiring paths used by iOS/macOS chat and capture flows.
- Validation:
  - iOS build: `xcodebuild -scheme EchoFlow -destination "platform=iOS Simulator,name=iPhone 17" build` ✅
  - macOS build: `xcodebuild -scheme EchoFlow_macOS CODE_SIGNING_ALLOWED=NO build` ✅
- Eval status for Echo avatar candidate on `medical-mechanica`:
  - `gguf/afs/echo-qwen25-1p5b-v1-q8_0.gguf` scored `7/15` (`46.67%`) on `echoflow_avatar_eval_v1.jsonl`.
  - Primary deficits are output-contract drift (length/format), not endpoint connectivity.
- Cleanup completed:
  - Removed temporary eval artifacts from `C:\Users\starw\AppData\Local\Temp\` on `medical-mechanica`.
  - Removed local temporary eval/build/search artifacts from `/tmp`.
