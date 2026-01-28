# Zelda 16B Training Plan (DeepSeek-Coder-V2-Lite)

Status: Draft (research-only)
Last updated: 2026-01-02

## Scope

- Train `zelda-16b-v1` for 65816 ASM + Oracle-of-Secrets workflows.
- Use existing AFS Scawful generators/validators and local dataset inventory.

## Target Model

- **Name:** `zelda-16b-v1`
- **Base:** DeepSeek-Coder-V2-Lite (16B MoE, 128K context per `docs/MODEL_NAMING.md`)
- **Base model ID (suggested):** `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`
- **Alternative base:** `deepseek-ai/DeepSeek-Coder-V2-Lite-Base` (if we want to keep instruction tuning separate).
- **Source:** Hugging Face API lookup on 2026-01-02 (model IDs exist; license in model card).

Unknown / needs verification:
- Chat template for DeepSeek-Coder-V2-Lite (script currently uses Qwen ChatML).

## Data Sources (local inventory)

Reference: `docs/TRAINING_DATA_INVENTORY.md` (source: `~/src/training/datasets`).

Core candidates:
- `vultr_train_full.jsonl` (28,707) — main ASM training set.
- `vultr_gold_full.jsonl` (11,044) — higher quality gold set.
- `oos_enriched_v1_normalized_notodo.jsonl` (19,303) — Oracle-of-Secrets enriched.
- `asm_gold_asar_pass_20260102.jsonl` (3,894) — ASAR-validated gold.
- `nerv_watcher_v1.jsonl` (211) — error/validation reasoning.
- `expert_router_v1.jsonl` (53) — routing (optional).

Windows-only datasets (not validated here):
- `D:\afs_training\datasets\lsp_fim_train.jsonl`
- `D:\afs_training\datasets\lsp_train.jsonl`

## Proposed Mix (Draft)

Phase 0 (smoke test):
- Use `asm_gold_asar_pass_20260102.jsonl` or `vultr_gold_full.jsonl` to validate memory.
- Goal: confirm training loop stability + checkpointing.

Phase 1 (quality-first):
- Merge `vultr_gold_full.jsonl` + `oos_enriched_v1_normalized_notodo.jsonl`.
- Optional: add `nerv_watcher_v1.jsonl` for review/error detection.

Phase 2 (full scale):
- Add `vultr_train_full.jsonl` to broaden coverage.
- Keep a small gold subset for eval/early stopping.

Locked mix (zelda_16b_mix_v1):
- Dataset bundle: `/Users/scawful/src/training/datasets/zelda_16b_mix_v1/`
- Train: 61,948 samples; Eval: 1,264 samples (2% per dataset, seed=42).
- Ratios (by source): vultr_train_full 45.41%, oos_enriched 30.54%, vultr_gold 17.47%, asm_gold_asar 6.16%, nerv 0.33%, router 0.08%.
- `train.jsonl` + `eval.jsonl` are shuffled; `val.jsonl` mirrors eval.

Unknown / needs verification:
- Whether to adjust mix ratios beyond v1.
- Whether to include tool-routing samples beyond v1.

## QA + Validation

Before training:
- Run QA summary: `python scripts/dataset_qa_summary.py --inputs <datasets...>`
- Ensure dataset registry is updated: `python -m afs_scawful datasets index`

After training:
- Use the eval pipeline: `python -m afs_scawful eval batch --prompts <prompts.jsonl>`
- Prefer ASAR v2 validation (default in eval pipeline).

## Infrastructure Options

Vultr (development):
- Use plan catalog in `infra/VULTR_GPU_PLANS.md`.
- Likely candidates: A100 80GB plan (`vcg-a100-12c-120g-80vram`) or larger.

Vast (marketplace):
- Use `docs/VAST_SETUP.md` + `infra/vast/vast_deploy.sh`.
- Filter by `gpu_name=A100` and `gpu_ram>=80` for 80GB offers.
- Pricing and availability: Unknown / needs verification (offer-based).

GCP (production-scale):
- Use `infra/gcp/GCP_SETUP.md`.
- Region and GPU availability: Unknown / needs verification.
- If H100 is required, check `gcloud compute accelerator-types list` by region.

Note:
- A100 80GB plan may not be available in the current Vultr regions (no regions listed in the API). Needs verification via `vultr regions` or console.
- Deployment attempt (2026-01-02) returned: "plan is not available in the selected region".

## Training Run Outline (QLoRA)

1. Update training scripts to accept 16B:
   - `infra/scripts/manage_training.sh` now supports `16b` and `--model-name` overrides.

2. Prepare dataset directory on the training node:
   - `/opt/training/datasets/<dataset>.jsonl`

3. Launch training:
   - `train_peft.py --model-name <deepseek-id> --data-dir /opt/training/datasets`
   - Output dir: `/opt/training/models/zelda-16b-v1_<timestamp>`

4. Checkpoint/export:
   - Confirm interval settings and exports to `halext-nj`.

## Artifacts + Naming

- LoRA outputs: `models/zelda-16b-v1_<timestamp>/lora_adapters`
- Merged model: optional (size depends on base).
- GGUF: optional for local inference; likely large.

## Open Questions

- DeepSeek-Coder-V2-Lite license details + chat template specifics.
- GPU memory needs for QLoRA + target context length.
- Dataset mixing ratios.
- Training schedule (epochs, batch size, grad accumulation).
- Whether to run training on Vultr A100 80GB or GCP H100.

## Higher-Parameter Candidates (80GB QLoRA)

Found via Hugging Face API search on 2026-01-02:
- `Qwen/Qwen2.5-Coder-32B-Instruct`
- `codellama/CodeLlama-34b-Instruct-hf`

Notes:
- Fit in 80GB depends on QLoRA settings and sequence length; needs verification.
