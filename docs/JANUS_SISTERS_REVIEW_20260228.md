# Janus Sisters Plan Review (2026-02-28)

## Scope Reviewed
- `/Users/scawful/src/docs/HALEXT_PRIME_SPEC.md`
- `/Users/scawful/src/training/scripts/janus_bifurcate.py`
- `/Users/scawful/src/training/scripts/mlx_train_janus.sh`
- `/Users/scawful/src/training/datasets/janus_bifurcated/{jana_modern.jsonl,janice_retro.jsonl}`

## Current State
- Spec exists and role split is clear: **Jana (modern execution)** vs **Janice (retro architecture)**.
- Bifurcated datasets already exist:
  - `jana_modern.jsonl`: 14,796 rows (~370 MB)
  - `janice_retro.jsonl`: 15,914 rows (~149 MB)
- `mlx_train_janus.sh` now includes strict shell flags, preflight checks, and a valid multiline `python3 -m mlx_lm.lora` invocation.
- Primary blocker is now role-gate quality controls and deployment benchmarking, not basic script executability.

## Findings (Severity-Ordered)

### 1. High: Dataset split heuristic can still over-index on weak path signals
`janus_bifurcate.py` now uses weighted keyword + path + extension signals, but path/extension cues can still dominate and leak overlap between personas.

Impact:
- Jana and Janice learn overlapping style/content distributions.
- Harder to maintain strong routing boundaries and specialization.

### 2. High: No default eval gate wired into Janus training flow
Spec defines persona roles but there is no explicit eval pack that checks:
- Jana speed/conciseness and modern toolchain competence.
- Janice depth on ASM/hardware/historical architecture.
- Cross-role contamination thresholds.

Impact:
- Promotion decisions are subjective; regressions are easy to miss.

### 3. Medium: Adapter switching architecture is defined but not benchmarked
Spec calls for hot-swappable MLX adapters in Cortex. No measured switching latency, warm-up behavior, or memory pressure envelope is documented.

Impact:
- Deployment may meet correctness but miss UX/perf expectations.

### 4. Medium: Data hygiene filters are broad but not explicit enough
Bifurcation currently skips only a few directory names (`build`, `.venv`, `node_modules`, `.git`, `derived`) and ingests whole files as `text`.

Impact:
- Risk of noisy/duplicate/irrelevant samples inflating dataset size without adding signal.

## Recommended Execution Plan

### Phase A (Immediate)
1. Dry-run `mlx_train_janus.sh` for both `jana` and `janice` in a machine with `mlx_lm` installed.
2. Record launch logs plus adapter output paths.
3. Add explicit base-model mapping check (`jana=3B`, `janice=7B/14B`) to align with spec.

Done criteria:
- Script exits non-zero on missing prerequisites.
- `jana` and `janice` commands both launch training correctly with expected base models.

### Phase B (Data Quality)
1. Extend bifurcation to include weighted intent tags:
   - Modern: Swift/SwiftUI/C++23/build orchestration/tooling.
   - Retro: 65816/PPU/DMA/HDMA/ROM/disassembly/lore.
2. Add optional exclusion manifests to avoid known low-signal corpora.
3. Emit manifest stats (token counts, top path contributors, overlap warnings).

Done criteria:
- New manifest generated for both splits.
- Per-split topic keyword distributions align with role intent.

### Phase C (Eval Gate)
1. Create Janus eval pack with three sections:
   - `role_fit_jana`
   - `role_fit_janice`
   - `cross_contamination`
2. Define promotion thresholds:
   - Jana role-fit >= 0.80, Janice role-fit >= 0.80
   - contamination <= 0.20
3. Track latency metrics for adapter swap in Cortex.

Done criteria:
- Eval JSON report produced for each candidate pair.
- Pass/fail promotion decision is automated.

## Suggested Artifact Additions
- `training/evals/janus_role_eval_v1.jsonl`
- `training/evals/janus_role_eval_runner.py`
- `training/datasets/janus_bifurcated/manifest.json`
- `docs/ops/JANUS_DEPLOY_BENCHMARK.md`

## Actions Completed In This Session
- Added `training/evals/janus_role_eval_v1.jsonl` (18 cases across role-fit and contamination).
- Added `training/scripts/janus_role_eval_runner.py` with threshold-based promotion gates:
  - `jana_role_fit >= 0.80`
  - `janice_role_fit >= 0.80`
  - `contamination_rate <= 0.20`
- Verified runner syntax (`python3 -m py_compile`) and pack structure (`wc/head`).

## Phase C Trial Run (2026-02-28)
- Command run:
  - `python3 /Users/scawful/src/training/scripts/janus_role_eval_runner.py --endpoint http://127.0.0.1:11440/v1/chat/completions --eval-pack /Users/scawful/src/training/evals/janus_role_eval_v1.jsonl --jana-model Qwen/Qwen2.5-3B-Instruct --janice-model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --out /Users/scawful/src/training/evals/janus_role_eval_report_20260228_run1.json`
- Report:
  - `jana_role_fit=0.8333`
  - `janice_role_fit=1.0`
  - `contamination_rate=1.0`
  - `promote=False`
- Reliability note:
  - Cross-contamination section failures were dominated by endpoint/runtime instability (`curl timeout`, `empty reply`, endpoint down) rather than clean semantic failures.
  - Action: re-run the same eval after stabilizing/restarting Cortex service, then compare against this baseline report.

## Recommendation
Proceed with Janus Sisters as an active track, but treat it as an **ops + eval hardening** project first. The concept is strong and data exists; the next gains come from executable training scripts, cleaner split heuristics, and strict role-separation gates before broad deployment.
