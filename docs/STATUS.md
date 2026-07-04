# STATUS

Last updated: 2026-04-19
Stage: Alpha

## Current top-level snapshot

- avatar/persona baseline in this repo remains active, but Oracle/Zelda work is now a major parallel track
- current Oracle training + catalog status lives in `docs/ORACLE_STATUS_20260416.md`
- current Oracle public contract is:
  - `oracle-fast` first
  - `oracle` second
  - `oracle-pro` only if a larger model clearly earns it
- current Oracle active runs at last sync:
  - `veran-9b` finished; teacher-gate decision still pending
  - `qwen3-oracle-8b-v1-corrective2` remains the measured shared-floor result
  - `qwen3-oracle-14b-v1-r3` is the active 14B retry on a fresh 4090 host after the earlier OOM and lost retry-2 seed host
  - `qwen25-oracle-coder-7b-v2` has been recovered/finalized, but remains a mixed result rather than a promotion
  - `qwen25-oracle-coder-7b-v3` is prepared as the next corrective
  - `qwen35-oracle-fast-v2` remains staged, while the old `qwen35_oracle_14b_v1` prep path is stale because `Qwen/Qwen3.5-14B` is not a public base id

## Model Status

| Model | Status | Quality |
|-------|--------|---------|
| echo-qwen25-7b-v4plusrepair_microfix3 (q8_0) | Production | 24/24 EchoFlow eval |
| echo-qwen25-1p5b-repair (f16) | Fallback | 17/24 endpoint eval (legacy fallback) |
| avatar-mix-v1 (q8_0) | Trained + deployed | Manual smoke pending |
| sibyl_v1 (q8_0) | Trained + deployed | System prompt required |
| lancer_v1 (q8_0) | Trained + deployed | System prompt required |
| morpheus_v1 (q8_0) | Trained + deployed | System prompt required |
| anamnesis_v1 (q8_0) | Trained + deployed | System prompt required |
| monolith-v1 | Trained (adapter) | Seed v1, conversion/eval pending |
| conductor-v2-microfix2 | Production candidate | JSON smoke 8/8 (freeform parse gate) |
| steward_v1 (q8_0) | Trained + deployed | Task-planning smoke pass |
| journalist_v1 (q8_0) | Trained + deployed | Reflection-writing smoke pass |
| poet_v3 (q8_0) | Trained + deployed | Poetry smoke pass (8/8 writing eval) |
| essayist_v2 (q8_0) | Trained + deployed | Essay smoke pass |

Source of truth for model routing and paths: `config/chat_registry.toml`

## Latest Training Outcomes

- Echo microfix3 completed (2026-02-25) and promoted to production.
- Echo eval progression:
  - v4 q4km: 11/24
  - microfix f16: 19/24
  - microfix2 q8_0: 22/24
  - microfix3 q8_0: 24/24
- Avatar-Mix v1 confirmed complete (434 samples, rank 64, 5 epochs).
- Persona v1 models retrained on expanded datasets (sibyl/lancer/morpheus/anamnesis).
- Steward + Journalist v1 completed on medical-mechanica (40 samples each, rank 32, 6 epochs), converted to GGUF, synced local, and added to registry/router.
- Poet + Essayist v1 completed on medical-mechanica (40 samples each, rank 32, 6 epochs), converted to GGUF, synced local, and added to registry/router.
- Poet + Essayist v2 completed from live-teacher datasets (`poet`: OpenAI, `essayist`: Gemini), converted to GGUF, and promoted in router registry.
- Poet v3 completed with strict brevity constraints; writing smoke eval improved from 5/8 to 8/8.

## Infrastructure

- medical-mechanica (Windows + WSL2 RTX `5090`): primary local mixed-use training and inference node.
- Mac M5: control plane and fallback local eval/serving support.
- Vast.ai: fallback for oversized, parallel, or conflict-heavy training when local runtime is not good enough.

## Oracle / Zelda note

- use `docs/ORACLE_STATUS_20260416.md` for the current Oracle wave instead of relying on this generic status page
- use `docs/ORACLE_CATALOG_CONSOLIDATION_PLAN_20260415.md` for the stable public naming contract
- use `docs/ORACLE_TEACHER_DISTILLATION_PLAN_20260416.md` for the current teacher/distill policy

## Current Focus

- [ ] Run end-to-end smoke eval for persona models via `afs chat` (`sibyl`, `lancer`, `morpheus`, `anamnesis`).
- [ ] Run Avatar-Mix multi-role smoke eval and decide if formal eval pack is needed.
- [x] Promote echo microfix3 and update registry.
- [x] Generate Monolith + Conductor training data and run first training pass.
- [x] Convert Monolith + Conductor adapters to GGUF and run LM Studio smoke evals.
- [x] Improve Conductor JSON reliability and retrain (`v2_microfix2`: 8/8 smoke).
- [ ] Expand `echoflow_avatar_eval_v2.jsonl` with harder multi-turn and strict JSON edge cases.

## Known Gaps / Risks

- Persona behavior is strongly system-prompt dependent at current sample sizes.
- Formal eval pack for Avatar-Mix sub-roles is not yet implemented.
- `docs/CURRENT_STATE.md`, `docs/ORACLE_STATUS_20260416.md`, and session handoff docs must remain synchronized after each training push.
