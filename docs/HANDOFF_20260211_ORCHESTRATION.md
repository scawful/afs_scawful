# Handoff: Oracle Orchestration & Model Staging (2026-02-11)

## Executive Summary
Gemini's earlier orchestration work was mostly directionally correct, but runtime status and a few path claims were stale by the time of this review. The Windows Veran PEFT run completed, the eval task completed, and results were pulled locally for reproducible follow-up.

## Accuracy Review (Codex, validated on 2026-02-11)

### Verified Inputs
- `~/src/lab/afs/training_data/veran_v1_synthetic.jsonl` exists with **585** rows.
- `~/src/lab/afs/training_data/veran_v1_gold.jsonl` exists with **5** rows.
- `~/src/lab/afs/training_data/veran_v1_eval_quick_keywords.jsonl` exists with **12** rows.
- `~/src/lab/afs/training_data/veran_v1_eval_holdout.jsonl` exists with **34** rows.
- `~/src/lab/afs/knowledge/label_index.csv` has **1930** lines.
- `~/src/lab/scripts/agentic_preflight.sh` exists and points to `~/src/lab/afs-scawful/scripts/verify_rom.py`.
- `~/src/lab/scripts/sync_training_data.sh` exists and queues sync via `nerv-xfer`.

### Corrected / Clarified
- `AFS_Veran_v1_PEFT` and `AFS_Veran_v1_Eval` are **not currently running**.
  - As of 2026-02-11 review, both task states are `Ready`.
- Active Python process on `medical-mechanica` during review was only `pythonw.exe -m mm_daemon --background`.
- Paths in earlier notes mixed `~/src/lab/scripts/...` and `~/src/lab/afs-scawful/scripts/...`.
  - Canonical launchers used for this Veran run are in `~/src/lab/scripts/`.

## Windows Runtime State (medical-mechanica)

### Task Status Snapshot (2026-02-11)
- `AFS_Veran_v1_PEFT`: `Ready`
- `AFS_Veran_v1_Eval`: `Ready`

### PEFT Training Outcome
- Task action: `cmd /c D:\afs_training\scripts\run_veran_v1_peft.cmd`
- Base model: `Qwen/Qwen2.5-Coder-7B-Instruct`
- Dataset dir: `D:\models\datasets-models\veran_v1_peft_windows`
- Output checkpoint root: `D:\models\checkpoints\veran_v1_peft_20260210_224921`
- Final adapter path: `D:\models\checkpoints\veran_v1_peft_20260210_224921\lora_adapters`
- Log tail confirms completion with `train_runtime` stats and `Saving model...`.

### Eval Outcome
- Task action: `cmd /c D:/afs_training/scripts/run_veran_v1_eval.cmd`
- Outputs:
  - `D:\afs_training\evals\veran_v1\results_quick_20260210_230105.json`
  - `D:\afs_training\evals\veran_v1\results_holdout_20260210_230105.json`
- Quick summary:
  - `keyword_avg_recall`: **0.2708**
  - `keyword_full_match_rate`: **0.0**
- Holdout summary:
  - `reference_exact_match_rate`: **0.0588**
  - `reference_contains_rate`: **0.0588**
  - `reference_avg_token_f1`: **0.7790**

## Localized Artifacts (Pulled for Review)
- `docs/eval/veran_v1/results_quick_20260210_230105.json`
- `docs/eval/veran_v1/results_holdout_20260210_230105.json`
- `docs/eval/veran_v1/veran_v1_peft_20260210_224921.log`
- `docs/eval/veran_v1/veran_v1_eval_20260210_230105.log`

## Operational Scripts Added In This Continuation
- `scripts/launch_veran_eval_windows.sh`
  - Stages eval assets and launches Windows eval task from `afs-scawful` directly.
- `scripts/pull_veran_eval_results.sh`
  - Pulls latest quick/holdout JSON and latest eval log to local `docs/eval/veran_v1/`.

## EchoFlow Track (Training-First Support)
- Prior integration work remains valid:
  - strict JSON runtime setting and provider wiring
  - iOS + macOS build checks passed in prior pass
- Known current model baseline from prior run:
  - `gguf/afs/echo-qwen25-1p5b-v1-q8_0.gguf` on `echoflow_avatar_eval_v1.jsonl`: **7/15** (46.67%)
  - dominant failure mode: output-contract drift (length/format)
- New prep artifacts for next training cycle:
  - `docs/eval/echoflow_avatar_eval_v2.jsonl`
  - `scripts/eval_echoflow_avatar_remote.py`
  - `scripts/build_echo_repair_dataset.py`
  - `docs/ECHO_MODEL_TRAINING_LOOP_20260211.md`

## Updated Next Steps
1. Run `scripts/eval_echoflow_avatar_remote.py` on the next Echo candidate.
2. Build repair seed set with `scripts/build_echo_repair_dataset.py --eval-report ...`.
3. Merge repair samples into the chat-format corpus under `~/src/training/datasets/scribe-corpus/`.
4. Re-run eval gate and only promote defaults after pass-rate target is met.
5. If Windows host is unavailable, switch endpoint/workflow using `docs/VAST_SETUP.md`.
