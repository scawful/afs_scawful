# Oracle Teacher Distillation Plan

Last updated: 2026-04-16
Status: active design + seed implementation

## Goal

Use the strongest internal specialist traits as narrow teachers for the shared Oracle models.

The teacher policy is:

- distill by routed surface, not by prestige
- distill by disagreement, not by volume
- keep each teacher narrow and evidence-backed
- do not transfer a specialist's failed shared-core behavior into `oracle` or `oracle-fast`

## Teacher map

### `farore`

- role: OOS debug specialist
- teach into:
  - `farore_domain_distill`
  - `farore_tool_choice_distill`
  - `farore_chain_distill`
  - `farore_disagreement_distill`
- good for:
  - crash triage
  - breakpoint ordering
  - room/state/diagnostics sequencing
- avoid distilling:
  - shared-core `<think>` style

### `nayru`

- role: explanation and trace teacher
- teach into:
  - `nayru_explain_distill`
  - `nayru_trace_distill`
- good for:
  - patient explanations
  - vanilla-aware trace work
  - teaching-oriented tool-backed answers

### `din`

- role: optimization and hook-contract teacher
- teach into:
  - `din_opt_distill`
  - `din_hook_contract_distill`
- good for:
  - cycle-aware optimization
  - width/register contract safety
  - low-level patch hygiene

### `majora`

- role: architecture and xref teacher
- teach into:
  - `majora_architecture_distill`
  - `majora_xref_distill`
- good for:
  - subsystem maps
  - caller relationships
  - vanilla vs hacked separation

### `hylia`

- role: history / rationale / vanilla-context specialist
- current status: archive / sunset candidate
- specialist eval read:
  - specialist acceptance `0.767`
  - core thinking `0.000`
- good for:
  - narrow history/rationale prompts
  - explicit lore or original-behavior context
- current decision:
  - do **not** build a full disagreement/distill model
  - do **not** keep `hylia` as an active long-term teacher model unless a later eval pass shows a clearly bounded historical surface it uniquely wins
  - treat it as an archive/sunset candidate after preserving evals and any tiny grounded historical slice worth keeping
  - if revived later, prefer a very small docs-grounded pack instead of a broad teacher profile or a routed model

### `oracle-main`

- role: broad shared-model teacher
- good for:
  - mixed Oracle behavior after the artifact is healthy enough
  - shared style and tool discipline

## Ensemble policy

### `oracle`

- primary teachers:
  - `oracle-main`
  - `nayru`
  - `din`
  - `farore`
  - `majora` (only on architecture/xref surfaces)

### `oracle-fast`

- primary teachers:
  - `farore`
  - `nayru`
  - `din`
  - selected `oracle-main` repairs
  - optional later `majora` xref deltas

## Grounding policy

Each teacher pack should prefer, in order:

1. tool-grounded traces from real teacher profile data
2. docs-grounded exemplars built from authoritative Oracle notes
3. disagreement-mined teacher-over-student cases

Avoid free-form synthetic answers without tool traces or grounded doc context.

## Current implemented seed packs

- `farore_distill_20260416.jsonl`
- `farore_disagreement_distill_20260416.jsonl`
- `nayru_distill_20260416.jsonl`
- `din_distill_20260416.jsonl`
- `majora_distill_20260416.jsonl`

## Disagreement-mining status

- completed eval packs:
  - `farore_disagreement_eval_v1.jsonl`
  - `nayru_disagreement_eval_v1.jsonl`
  - `din_disagreement_eval_v1.jsonl`
  - `majora_disagreement_eval_v1.jsonl`
- completed disagreement distill outputs:
  - `farore_disagreement_distill_20260416.jsonl`
  - `nayru_disagreement_distill_20260416.jsonl`
  - `din_disagreement_distill_20260416.jsonl`
  - `majora_disagreement_distill_20260416.jsonl`

Observed value so far:

- `nayru` produced the strongest shared-teacher signal
- `farore` remains the best narrow teacher for debug/tool-chain continuation
- `din` adds targeted optimization + hook-contract repair
- `majora` adds architecture/xref repair without justifying a shared-core model

## Current next step

Use the completed disagreement packs in the active shared corrective wave:

- finish the recovery upload on `qwen3-oracle-8b-v1-corrective3`
- launch `qwen3-oracle-8b-v1-corrective2`
- evaluate the corrected shared `8B` model against the Oracle boundary/effort matrix
- run the narrow DPO follow-up only after the corrective SFT model produces a stable merged artifact

## Current weighted corrective recommendation

The next shared Qwen corrective run should use a weighted blend rather than a flat union.

Recommended training mix now implemented in `qwen3_oracle_corrective2_v1`:

- `trackc_train` × `8`
- `nayru_disagreement` × `4`
- `farore_disagreement` × `3`
- `din_disagreement` × `2`
- `majora_disagreement` × `2`
- grounded seed exemplars × `3`

Current ranking for the next shared corrective run:

1. `nayru`
2. `farore`
3. `din`
4. `majora`
5. `hylia` (excluded; archive candidate)

Rationale:

- `nayru` is the strongest teacher for explanation/trace tool omission
- `farore` is the strongest teacher for OOS debug chain completion
- `din` adds optimization and hook-contract repair
- `majora` adds architecture/xref chain repair without dominating the mix
- the original Track C repair pack remains the broad shared anchor
- `hylia` is currently excluded because its specialist score is only moderate and its core thinking score is still zero

## Narrow DPO follow-up

The Zelda shared model should use DPO only on narrow disagreement surfaces, not the whole corpus.

Current scaffolding added:

- pair builder:
  - `/Users/scawful/src/training/scripts/build_qwen3_oracle_dpo1_pairs.py`
- training entrypoint:
  - `/Users/scawful/src/training/scripts/train_zelda_dpo.py`
- training modules:
  - `/Users/scawful/src/training/z3_training/dpo_config.py`
  - `/Users/scawful/src/training/z3_training/dpo_data.py`
  - `/Users/scawful/src/training/z3_training/dpo_train.py`
- config:
  - `/Users/scawful/src/training/configs/zelda/qwen3_oracle_8b_corrective_dpo1.toml`

Current DPO1 pair dataset:

- `/Users/scawful/src/training/datasets/qwen3_oracle_dpo1_v1`
- weights:
  - `nayru` × `4`
  - `farore` × `3`
  - `din` × `2`
  - `majora` × `2`
- split sizes:
  - train `318`
  - val `15`
  - test `15`

Intended use:

- run DPO only after the corrective SFT model has produced a stable merged artifact
- use DPO to steer:
  - chain continuation
  - tool-vs-prose preference
  - narrow specialist-domain behavior
- do not use DPO as a replacement for the broad SFT + grounded repair corpus

## PPO stance

Current Oracle plan: no PPO.

Reasoning:

- the current failure surfaces are narrow behavioral preferences, not broad reward-model problems
- specialist disagreement data already gives us strong pairwise signals for DPO
- PPO would add much more infrastructure and instability than we currently need for the Zelda models

So the current intended stack is:

1. broad SFT + grounded repair packs
2. narrow specialist distillation
3. narrow DPO on disagreement surfaces
4. no PPO unless the DPO-corrected model still fails in a way that clearly needs online reward optimization

Minimum-data gating for this stack is now captured in the shared policy doc in
`z3cli` (`docs/ZELDA_RLHF_THRESHOLD_POLICY.md`); apply the
pilot gate before each training wave and keep production promotion to the stricter
threshold set.
