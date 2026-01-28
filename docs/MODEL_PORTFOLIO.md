# Model Portfolio Overview (Zelda + Avatar)

Last updated: 2026-01-07
Scope: afs-scawful (research-only plugin). Summary of model families, training
tracks, and planned work based on repo notes.

Sources:
- `docs/STATUS.md`
- `docs/CURRENT_STATE.md`
- `docs/MODEL_NAMING.md`
- `docs/ZELDA_16B_TRAINING_PLAN.md`
- `docs/MODEL_STRATEGY.md`
- `docs/TRAINING_ROADMAP.md`
- `docs/advanced_training_plan.md`
- `/Users/scawful/src/docs/NAMING_CONVENTIONS.md`
- `/Users/scawful/src/training/scribe-corpus/docs/router.md`

## Zelda / ASM (Oracle series)

Naming and roles (from `docs/MODEL_NAMING.md`):
- Nayru: explanation, analysis, documentation
- Din: optimization, refactoring
- Farore: autocomplete, FIM
- Veran: large-context analysis
- Ralph: validation and error checking
- Linked Game: combined or ensemble workflows

Current named models (from `docs/STATUS.md`):
- nayru-7b-v1: Production
- farore-1.5b-v1: Testing (Windows)
- veran-14b-v1-lora: Available (needs 4-bit quantization)
- zelda-16b-v1: Benchmark (Vast) stopped

Additional names and roles:
- onox: aggressive optimization (from `docs/MODEL_NAMING.md`).
- twinrova: MoE ensemble (from `docs/MODEL_NAMING.md`).
- agahnim: patch merges, IPS/BPS workflows (`oracle-agahnim-patcher` in
  `/Users/scawful/src/docs/NAMING_CONVENTIONS.md`).
- majora: role defined in `docs/MODEL_NAMING.md` as Unknown / needs verification.
- other ideas in `docs/MODEL_NAMING.md`: maple (fast helper), impa (security
  review), zelda (scholarly analysis), essence (distilled/quantized models).

Planned large model (from `docs/ZELDA_16B_TRAINING_PLAN.md`):
- zelda-16b-v1 on DeepSeek-Coder-V2-Lite, dataset `zelda_16b_mix_v1`.

Evaluation focus (from `docs/STATUS.md`):
- Build ASAR-based eval framework for ASM validation.

## Avatar / Persona

Current tracks (from `docs/STATUS.md` and `docs/CURRENT_STATE.md`):
- scawful-echo: training on Vast; dataset refreshed and A/B queue staged on
  Windows (see `docs/CURRENT_STATE.md`).
- twitter-avatar-qwen25-3b: training on Windows GPU (Unknown / needs
  verification).
- twitter-avatar-qwen25-7b: training on Vast (Unknown / needs verification).
- muse-v2: training completed (Vast); local artifacts exist (see
  `docs/CURRENT_STATE.md`).

Local inference notes (from `docs/CURRENT_STATE.md`):
- Mac Ollama has `scawful-echo:latest` (Gemma2 9B + LoRA).
- Avatar MoE (local Ollama): `scawful-echo:latest`, `muse-v2:latest`,
  `scribe:v2`.

## Router / Utility

New run (router classifier, chat-format seed dataset):
- router-gemma2-2b-v1: queued on Windows GPU; dataset
  `~/src/training/datasets/router-2026-01-07` (see
  `~/src/training/scribe-corpus/docs/router.md`).

## Data and Inventory

- Local dataset inventory: `docs/TRAINING_DATA_INVENTORY.md` (source:
  `~/src/training/datasets`).
- Windows datasets are not validated here (see `docs/STATUS.md`).
- Avatar datasets are built under `~/src/training/scribe-corpus` (see
  `docs/CURRENT_STATE.md`).

## Local model targets (Mac eval)

From `docs/MODEL_STRATEGY.md`:
- Small models: Qwen2.5-1.5B-Instruct, Gemma 2 2B IT.
- Chat baselines: Qwen2.5-3B/7B-Instruct, Llama 3.1/3.2 8B Instruct
  (size dependent).

## Planned work (near-term)

From `docs/STATUS.md` and `docs/CURRENT_STATE.md`:
- Evaluate farore-1.5b-v1 autocomplete.
- Plan zelda-16b-v1 training (data + infra).
- Build ASAR eval framework.
- Train din-7b-v1 (optimization focus).
- Decide scawful-echo training location (Vast vs Windows GPU).
- Re-run scawful-echo micro overfit after dataset refresh.

From `docs/TRAINING_ROADMAP.md`:
- Training monitor schema validation and config docs.
- Generator QA summary + manifest output.
- Repeatable dataset build scripts and metrics export.
