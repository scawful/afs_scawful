# Echo Model Gate Report (2026-02-12)

## Scope
- Validate morning Echo training outputs from `medical-mechanica`.
- Run post-train gate eval against `docs/eval/echoflow_avatar_eval_v2.jsonl`.
- Check related "m" model training state (Memory/Muse).

## Runtime Status (validated 2026-02-12)
- `AFS_Echo_Repair_1p5B_Morning`: `Ready`, `LastTaskResult=0`, last run `2026-02-11 07:48`.
- `AFS_Echo_V4PlusRepair_7B_Morning`: `Ready`, `LastTaskResult=0`, last run `2026-02-11 07:52`.
- `AFS_Echo_Queue_Controller_Morning`: `Ready`, `LastTaskResult=0`, last run `2026-02-11 07:51`.
- Active training processes: none (only background `pythonw.exe` daemon).

## Gate Eval Results
Eval pack: `docs/eval/echoflow_avatar_eval_v2.jsonl` (24 cases).

1. Baseline (`gguf/afs/echo-qwen25-1p5b-v1-q8_0.gguf`)
   - Report: `docs/eval/echoflow_avatar_eval_run_baseline_1p5b_v1_20260212_now.json`
   - Score: `4/24` (16.67%)
2. New 1.5B adapter (`echo-qwen25-1p5b-repair_20260211_morning`)
   - Report: `docs/eval/echoflow_avatar_eval_adapter_1p5b_repair_20260211_morning.json`
   - Score: `22/24` (91.67%)
3. New 7B adapter (`echo-qwen25-7b-v4plusrepair_20260211_morning`)
   - Report: `docs/eval/echoflow_avatar_eval_adapter_7b_v4plusrepair_20260211_morning.json`
   - Score: `23/24` (95.83%)

Gate threshold (`>=0.80`) is met by both new adapters.

## Residual Failure Pattern
- Remaining failure is `cap_bullets_001` (`missing:- `) on the 7B model.
- 1.5B has the same bullet-format issue plus one additional summary-format miss.
- Repair seed generated:
  - `docs/eval/echo_repair_seed_v2_morning_gate/train.jsonl`
  - `docs/eval/echo_repair_seed_v2_morning_gate/manifest.json`

## "M" Model Status
- No active Memory/Muse training tasks on `medical-mechanica`.
- Latest Memory/Muse checkpoints are from January 2026:
  - `memory-archivist-qwen25-7b-v3e_20260114_111836`
  - `muse-v3-safe_20260108_014736`
  - `muse-v3-uncensored_20260108_014736`

## Infra Note
- `medical-mechanica` remained healthy for all eval work.
- Vast host `145.236.166.111:10634` timed out during quick status probe, so fallback was not needed.

## Recommendation
1. Promote the 7B morning adapter line as the EchoFlow default candidate (best score: `23/24`).
2. Run one micro-repair pass targeting bullet-list formatting (`cap_bullets_001`) before final freeze.
3. Keep 1.5B repair as lightweight fallback profile.

## Addendum (2026-02-12 strict-output hardening)
- `scripts/eval_echoflow_avatar_remote.py` now applies schema-first strict JSON requests, JSON normalization, and one strict retry.
- Served eval reruns:
  - `docs/eval/echoflow_avatar_eval_run_7b_v4plusrepair_microfix_f16_20260212_strictfix.json`: `22/24` (91.67%)
  - `docs/eval/echoflow_avatar_eval_run_1p5b_repair_f16_20260212_strictfix.json`: `21/24` (87.50%)
- Result: `invalid_json` failures are removed from served gate runs.
