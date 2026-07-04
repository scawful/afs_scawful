# Oracle Status Snapshot

Last updated: 2026-04-19T22:15:00Z
Status: qwen3-oracle-14b-v1-r3 active on fresh 4090 retry; oracle-coder v2 recovered but not promoted; qwen35 14B path downgraded to stale prep

This note captures the current Oracle training wave, the public catalog
direction, and the next promotion steps.

## Platform Policy

- `medical-mechanica` WSL2 + RTX `5090` is now the primary local mixed-use host
  for Oracle-family and scawfulbot work
- local-first applies to `oracle-fast`, `oracle-coder`, specialist `9B`, evals,
  merges, quant/export, and many `14B` runs
- Vast is the fallback when the shared desktop is busy, unstable, or cannot
  spare the GPU

## Public Catalog Contract

- `oracle-fast`: first public `8-9B` shared Oracle model
- `oracle`: planned `14B` default public Oracle model
- `oracle-pro`: reserved `27B` premium model only if it earns the cost/latency jump
- `plan` / `act` are no longer intended public model names; they are effort presets or compatibility aliases
- `switchhook-*` and `oracle-tools` remain compatibility aliases only

## Current Shared-Model Status

- current shared proving-ground artifact: `qwen3-oracle-8b-v1`
- current corrective config: `qwen3-oracle-8b-v1-corrective2`
- corrected floor result is still the completed `qwen3-oracle-8b-v1-corrective2` run on the recovered `35084371` box
- recovery notes:
  - the merged base upload completed on the recovery box and the side files synced successfully
  - the first relaunch attempt exposed a `pyarrow.lib.ArrowInvalid` dataset-schema failure on heterogeneous `messages`
  - `z3_training/data.py` was patched to tokenize records before building the HF dataset, which avoids Arrow schema inference on raw mixed-format messages
  - after the data-loader patch, `qwen3-oracle-8b-v1-corrective2` successfully started training on the recovered box
- 14B follow-up is now active on the Qwen3 mainline:
  - dataset builder: `training/scripts/build_qwen3_oracle_14b_dataset.py`
  - upgraded shared foundation: `training/datasets/qwen3_oracle_rebase_v2`
  - live dataset: `training/datasets/qwen3_oracle_14b_v1`
  - current built counts: train `21,258` (`19,358` rebase + `1,900` corrective), val `5,497`, test `6,842`
  - train duplicate note: `1,772` intentional duplicate rows preserving corrective weighting (`19,486` unique train messages)
  - launch config: `training/configs/zelda/qwen3_oracle_14b.toml`
  - run brief: `training/runs/qwen3_oracle_14b_v1/README.md`
  - first attempt failed at step `1` with CUDA OOM on the original `4096` / `r=32` profile
  - retry-2 was blocked by the unrecoverable stopped host that held the seed adapter
  - current live retry is `qwen3-oracle-14b-v1-r3` on fresh Vast instance `35257256`
  - current stable profile runs at `2816` / `r=16` / `alpha=32` with `adamw_torch`
  - latest verified trainer state in this note: healthy past `checkpoint-100` and still actively training
- Qwen3.5 shared-backbone pivot prep is also ready as an A/B challenger:
  - dataset builder: `training/scripts/build_qwen35_oracle_9b_dataset.py`
  - prepared dataset: `training/datasets/qwen35_oracle_9b_v1`
  - current built counts: train `21,258` (`19,358` rebase + `1,900` corrective), val `5,497`, test `6,842`
  - train duplicate note: `1,772` intentional duplicate rows preserving corrective weighting (`19,486` unique train messages)
  - launch config: `training/configs/zelda/qwen35_oracle_9b.toml`
  - run brief: `training/runs/qwen35_oracle_9b_v1/README.md`
  - fairness rule: keep `qwen35_specialist_failure_repairs_20260413.jsonl` out of the first pilot launch
  - current corrective target remains `training/datasets/qwen35_oracle_fast_v2/`
  - the separate `qwen35_oracle_14b_v1` scaffold should now be treated as stale prep because `Qwen/Qwen3.5-14B` is not a public model id
- internal coding worker track remains active:
  - completed baseline: `qwen25-oracle-coder-7b-v1`
  - completed corrective rerun: `qwen25-oracle-coder-7b-v2`
  - `v2` was recovered with `scripts/finalize_peft_run.py` after a post-checkpoint closeout fault
  - held-out outcome is mixed, so the line is not yet promoted
  - next prepared corrective: `qwen25-oracle-coder-7b-v3`
- rollout status:
  - do not promote `qwen3-oracle-8b-v1` to public aliases yet
  - use the live `qwen3-oracle-14b-v1` probe plus the eventual `qwen35-oracle-fast-v2` corrective to decide whether `oracle-fast` stays on the Qwen3 floor or pivots back toward Qwen3.5

## Active Runs

### `veran-9b`

- training completed on `2026-04-18`
- final step: `2988 / 2988`
- role in the wave: finished teacher candidate; post-run teacher-gate decision still pending

### `qwen3-oracle-8b-v1-corrective2`

- Vast instance: `35084371`
- host: `ssh1.vast.ai:14370`
- state at last watcher check: training complete
- latest verified progress: `120 / 120` (`100.0%`)
- completion line: `2026-04-17 01:22:16,841 - INFO - Training complete.`
- eval suite recorded:
  - Track C: overall `0.64`, tool format `0.885` (`19/20`), thinking `0.06` (`0/10`), domain `0.84` (`8/10`), chain `0.41` (`0/5`)
  - shared core acceptance: overall `0.00`, thinking `0.00` (`0/4`)
  - boundary matrix report captured at `training/evals/runs/qwen3_oracle_corrective2_boundary_matrix_20260417_015652.json`
- interpretation:
  - corrective SFT preserved strong tool formatting but still did not solve the shared thinking surface
  - this result justifies the prepared Qwen3.5 backbone challenge instead of blindly scaling the Qwen3 model first

### `qwen35-oracle-9b-v1`

- Vast instance: `35084371` (reused corrective box)
- host: `ssh1.vast.ai:14370`
- state: finished
- current evidence:
  - local launch log: `training/logs/vast/qwen35_oracle_9b_launch.log`
  - first launch failed because `launch_zelda_vast.sh` uploaded the dataset to `/workspace/training/data/` while the config expected `/workspace/training/data/qwen35_oracle_9b_v1/`
  - second launch exposed CUDA OOM at the original `4096` / `r=32` profile
  - launch script is patched to upload datasets to the config-declared remote data dir
  - pilot config is reduced to the proven 9B fit profile (`2048` / `r=16`)
  - final eval result is decisively bad on tool activation and thinking
- next action: keep `qwen35-oracle-fast-v2` as the only active Qwen3.5 corrective path instead of trying to scale that backbone directly

### `qwen25-oracle-coder-7b-v2`

- state: completed via recovered closeout
- current interpretation:
  - the corrective rerun reached the end of its scheduled steps
  - `final/` and `train_end` were reconstructed from `checkpoint-66`
  - held-out evals improved in places, but not enough to promote the coder line

## Finished This Wave

### Specialist runs

| Model | Status | Notes |
|-------|--------|-------|
| `majora-9b` | finished + exported | promising architecture/xref teacher, not a shared-core model |
| `farore-9b` | finished + downloaded/exported | strong narrow debug/tool-chain teacher |
| `din-9b` | finished + exited | optimization + hook-contract teacher |
| `hylia-9b` | finished + downloaded/exported | archive / sunset candidate |
| `nayru-9b` | finished per logs + backup complete | strongest explanation/trace teacher; Vast still shows a lingering running instance |

### Teacher ranking for the next shared corrective pass

1. `nayru`
2. `farore`
3. `din`
4. `majora`
5. `hylia` excluded

## Planned Next Steps

1. keep monitoring the live `qwen3-oracle-14b-v1-r3` run until it either finishes cleanly or exposes a new failure mode
2. run the prepared `qwen25-oracle-coder-7b-v3` corrective on the local-first WSL + `5090` path
3. decide whether `oracle-fast` stays on the Qwen3 floor or needs the separate `qwen35-oracle-fast-v2` corrective to stay viable
4. treat `qwen35_oracle_14b_v1` as stale prep unless a real public `Qwen3.5-14B` base appears
5. run the narrow DPO follow-up using `qwen3_oracle_dpo1_v1` after corrective SFT produces a merged artifact
6. make the post-wave decision on which specialists stay as internal overrides or teacher-only models now that `veran` is done

## Verifiability Rule

- do not scale the shared Oracle dataset just because a newer backbone feels smarter
- scale only after a held-out failure family is measurable and repeatable on the current eval surfaces
- current policy note: `training/docs/ORACLE_VERIFIABILITY_AND_DATA_SCALING_20260417.md`
- current backbone A/B rubric: `docs/eval/ORACLE_BACKBONE_AB_RUBRIC_V1_20260417.md`

## Internal Model Catalog Snapshot

### Public models

| Public name | Target size | Current state | Purpose |
|-------------|-------------|---------------|---------|
| `oracle-fast` | `8-9B` | active default | pinned small Oracle contract; local-first on `medical-mechanica` WSL2 + `5090` |
| `oracle` | `14B` | active 14B probe | current live mainline run is `qwen3-oracle-14b-v1-r3`; long-term policy is local-first with Vast fallback |
| `oracle-pro` | `27B` | reserved | premium model only if the quality jump is real |

### Internal specialist bench

| Model | Best surface | Current use |
|-------|--------------|-------------|
| `nayru` | explanation / trace | top teacher for shared corrective repair |
| `farore` | OOS debug / tool chains | narrow teacher for debug sequencing |
| `din` | optimization / hook contracts | narrow teacher for low-level patch safety |
| `majora` | architecture / xref | narrow teacher for subsystem maps and cross-reference work |
| `veran` | deep analysis / long-context shared work | finished; final bench decision pending |
| `hylia` | history / rationale | archive candidate unless a uniquely winning history surface emerges |

## Related Docs

- `docs/ORACLE_CATALOG_CONSOLIDATION_PLAN_20260415.md`
- `docs/ORACLE_TEACHER_DISTILLATION_PLAN_20260416.md`
- `docs/eval/ORACLE_EVAL_MATRIX_V1_20260415.md`
- `docs/eval/ORACLE_BACKBONE_AB_RUBRIC_V1_20260417.md`
- `training/docs/ORACLE_VERIFIABILITY_AND_DATA_SCALING_20260417.md`
- `training/docs/ORACLE_SHARED_BACKBONE_AB_20260417.md`
- `training/logs/vast/qwen3_corrective2_completion_watch.log`
- `training/logs/vast/qwen35_oracle_9b_launch.log`
