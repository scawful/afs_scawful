# STATUS

Last updated: 2026-02-28
Stage: Alpha

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

- medical-mechanica (Windows RTX 5060 Ti 16GB): primary local training node.
- Mac M5: control plane, local eval/serving support.
- Vast.ai: heavy training when needed.

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
- `docs/CURRENT_STATE.md` and session handoff docs must remain synchronized after each training push.
