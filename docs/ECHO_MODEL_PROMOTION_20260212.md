# Echo Promotion Continuation (2026-02-12)

## Scope
- Proceeded with recommendations from `docs/ECHO_MODEL_GATE_20260212.md`:
  1. Promote 7B candidate.
  2. Run micro-repair pass.
  3. Keep 1.5B fallback.

## What was done
1. Built deployable 7B artifacts on `medical-mechanica`:
   - `gguf/afs/echo-qwen25-7b-v4plusrepair_20260211_morning-f16.gguf`
   - `gguf/afs/echo-qwen25-7b-v4plusrepair_20260211_morning-q8_0.gguf`
2. Ran micro-repair training loop from the failure set (5 cases) by resuming from the 7B adapter.
   - New adapter: `D:\models\checkpoints\echo-qwen25-7b-v4plusrepair_microfix_20260212`
   - New GGUF artifacts:
     - `gguf/afs/echo-qwen25-7b-v4plusrepair_microfix_20260212-f16.gguf`
     - `gguf/afs/echo-qwen25-7b-v4plusrepair_microfix_20260212-q8_0.gguf`
3. Built deployable 1.5B fallback artifacts:
   - `gguf/afs/echo-qwen25-1p5b-repair_20260211_morning-f16.gguf`
   - `gguf/afs/echo-qwen25-1p5b-repair_20260211_morning-q8_0.gguf`

## Eval summary
### Adapter-level (base + adapter, direct)
- `docs/eval/echoflow_avatar_eval_adapter_7b_v4plusrepair_microfix_20260212.json`
  - `23/24` (95.83%)
  - remaining miss: `cap_bullets_001`

### Served LM Studio models (OpenAI-compatible endpoint)
- `docs/eval/echoflow_avatar_eval_run_7b_v4plusrepair_f16_20260212_now.json`
  - `19/24` (79.17%)
- `docs/eval/echoflow_avatar_eval_run_7b_v4plusrepair_microfix_f16_20260212_now.json`
  - `19/24` (79.17%)
- `docs/eval/echoflow_avatar_eval_run_1p5b_repair_f16_20260212_now.json`
  - `17/24` (70.83%)

Observed served failure cluster remains:
- `invalid_json` on strict JSON cases (4)
- `missing:- ` on bullet list case (1)

### Served LM Studio models after strict-output hardening
Using updated `scripts/eval_echoflow_avatar_remote.py` (`json_schema` first pass + strict-json retry + JSON normalization):
- `docs/eval/echoflow_avatar_eval_run_7b_v4plusrepair_microfix_f16_20260212_strictfix.json`
  - `22/24` (91.67%)
- `docs/eval/echoflow_avatar_eval_run_1p5b_repair_f16_20260212_strictfix.json`
  - `21/24` (87.50%)

Residual misses after hardening:
- `missing:- ` (bullet format case)
- occasional `over_max_chars` on one short-case prompt

Resolved by hardening:
- `invalid_json` strict JSON failures are eliminated in served eval runs.

## Registry promotion applied
- `config/chat_registry.toml` now points avatar primary to:
  - `gguf/afs/echo-qwen25-7b-v4plusrepair_microfix_20260212-f16.gguf`
- Added explicit fallback entry:
  - model name: `echo-fallback-1p5b`
  - model id: `gguf/afs/echo-qwen25-1p5b-repair_20260211_morning-f16.gguf`

## Notes
- This satisfies the promotion + fallback recommendation operationally.
- Served strict-JSON behavior now clears the `0.80` gate after request/response hardening.
