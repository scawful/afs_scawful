# CLAUDE.md — afs-scawful

Agent instructions for working on this project.

## What This Is

Personal AFS extension: skills, context, model registries, and domain-specific workflows. Includes multi-core personality framework (glados, claudia, oracle, scawfulbot).

## Persona Source-of-Truth

- Claudia: `~/src/folio/context/personal/identity.md` and `~/src/folio/context/hivemind/*` are canonical for voice/identity. Read before any change that affects Claudia voice or eval.
- Scawfulbot: `~/src/folio/` writing is the upstream training corpus. Don't infer voice from output samples — read folio.
- Glados, Oracle: source-of-truth lives in this repo's eval cases and core files.

## Scawfulbot Consolidation

`cores/training/scawfulbot_unified/` contains **symlinks** to the canonical scawfulbot repo at `~/src/lab/scawfulbot/`. Do not edit training scripts or data pipeline files here — edit them in scawfulbot/ and the symlinks will pick up changes.

**Symlinked (edit in scawfulbot/):**
- `build.py`, `build_balanced.py`, `build_gemma4_dataset.py`, `build_preference_data.py`
- `train_unsloth.py`, `train_unsloth_dpo.py`, `train_mlx.py`
- `cloud_setup.sh`, `convert_to_gguf.sh`
- `repair/` (entire directory)

**Symlinked eval (edit in scawfulbot/):**
- `cores/eval/scawfulbot_signals.py` → `scawfulbot/eval/personality_signals.py`
- `cores/eval/scawfulbot_eval_cases.jsonl` → `scawfulbot/eval/eval_cases.jsonl`

**Local to this repo (edit here):**
- `cores/eval/personality_eval.py` — multi-core eval harness
- `cores/eval/claudia_eval_cases.jsonl`, `glados_eval_cases.jsonl`
- Training data outputs (`train.jsonl`, `valid.jsonl`, bundles)
- Launch scripts (`launch_vast_*.sh`, `download_model.sh`)
- `src/afs_scawful/feedback.py`, `chat_harness.py`, `gateway_server.py`

## Feedback Pipeline

Chat feedback flows: `chat_harness /good /bad` → `feedback.py` → `~/src/folio/logs/chat-feedback/` → `build_preference_data.py` (in scawfulbot/) → training data.

## Key Constraints

- Follow local `AGENTS.md` first.
- Don't commit large JSONL data files or model weights.
- Prefer editing existing files over creating new ones.
