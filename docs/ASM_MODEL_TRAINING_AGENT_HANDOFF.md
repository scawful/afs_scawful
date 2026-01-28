# ASM Model Training - Autonomous Agent Handoff

Status doc: `/Users/scawful/src/docs/ASM_MODEL_TRAINING_STATUS.md`
Last handoff update: 2025-12-31 22:51

## Scope + Buckets
- Work lives in `lab/afs-scawful` + workspace docs (`/Users/scawful/src/docs`).
- Avoid employer/work code. Keep to hobby/lab sources.
- Exclude C++ `zelda3` sources:
  - `/Users/scawful/src/hobby/zelda3`
  - `/Users/scawful/src/hobby/yaze/src/zelda3`

## Constraints
- Do NOT use chain-of-thought traces; use concise rationales/checklists only.
- Do NOT use or access API keys directly. GPU deploy must be user-run unless key is already in env.
- Keep the status doc updated after each milestone.

## Active Training (Vultr)
- Instance: `107.191.41.64` (plan `vcg-a100-3c-30g-20vram`, 20GB VRAM)
- Log: `/opt/afs_training/logs/train_20260101_035059.log`
- PID: `4509`
- Venv: `/opt/afs_training/venv` (datasets/scripts under `/opt/afs_training`)
- Check: `tail -f /opt/afs_training/logs/train_20260101_035059.log` and `nvidia-smi`

## Current Artifacts (latest)
- Status: `/Users/scawful/src/docs/ASM_MODEL_TRAINING_STATUS.md`
- Datasets root: `/Users/scawful/src/training/datasets`
- Index: `/Users/scawful/src/training/index`
- Key scripts:
  - `/Users/scawful/src/lab/afs-scawful/scripts/generate_asm_comment_samples.py`
  - `/Users/scawful/src/lab/afs-scawful/scripts/generate_git_history_samples.py`
  - `/Users/scawful/src/lab/afs-scawful/scripts/generate_comment_to_code_dataset.py`
  - `/Users/scawful/src/lab/afs-scawful/scripts/validate_asm_dataset.py`
  - `/Users/scawful/src/lab/afs-scawful/scripts/dataset_qa_summary.py`
- ASAR validator requires:
  - `asar` on PATH
  - Dummy ROM: `~/.context/training/dummy.sfc`

## Immediate Next Actions
1. Build **doc-driven code-gen dataset** from doc sections:
   - Source: `/Users/scawful/src/training/datasets/asm_docs_sections_*.jsonl`
   - Convert to code-gen style (new script may be needed or reuse comment-to-code logic).
2. Run ASAR validation on code-output sets:
   - Start with a 1k sample; log pass rate.
3. Build a small eval harness:
   - Syntax: ASM validator
   - Semantics: ASAR pass + basic expectations
   - Optimization: simple cycle-count heuristics (optional)
4. If `VULTR_API_KEY` is set in env, deploy GPU:
   ```bash
   cd /Users/scawful/src/lab/afs-scawful/infra
   ./deploy.sh --hours 4
   ```
   `deploy.sh` auto-selects a valid GPU plan/region; optional overrides:
   ```bash
   export VULTR_GPU_PLAN=vcg-a100-1c-2g-4vram
   export VULTR_GPU_REGION=ewr
   ```
   Or:
   ```bash
   ./deploy.sh --hours 4 --plan vcg-a100-1c-2g-4vram --region ewr
   ```
   If missing, log blocker in status doc.

## Useful Commands
```bash
# Training status (Windows)
/Users/scawful/src/lab/afs-scawful/scripts/training_status.sh

# Refresh dataset registry
PYTHONPATH=/Users/scawful/src/lab/afs-scawful/src \
  python3 -m afs_scawful datasets index \
  --root /Users/scawful/src/training/datasets \
  --output /Users/scawful/src/training/index/dataset_registry.json

# QA summary for selected datasets
python3 /Users/scawful/src/lab/afs-scawful/scripts/dataset_qa_summary.py \
  --inputs <paths...> \
  --output /Users/scawful/src/training/index/dataset_qa_<timestamp>.md

# ASAR validation on a dataset
PYTHONPATH=/Users/scawful/src/lab/afs-scawful/src \
  python3 /Users/scawful/src/lab/afs-scawful/scripts/validate_asm_dataset.py \
  --input <dataset.jsonl> \
  --field output \
  --asar \
  --report /Users/scawful/src/training/index/asar_validation_<name>_<ts>.md \
  --passed /Users/scawful/src/training/datasets/<name>_asar_pass_<ts>.jsonl \
  --failed /Users/scawful/src/training/datasets/<name>_asar_fail_<ts>.jsonl
```

## Notes
- The comment-to-code dataset has a ~27% ASAR pass rate on a 1k sample.
- Continue pruning or improving prompt construction to raise pass rate before full-scale training.
- Always update `/Users/scawful/src/docs/ASM_MODEL_TRAINING_STATUS.md` with timestamps and new artifacts.
