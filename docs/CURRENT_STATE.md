# Current State (2026-02-28)

Scope: avatar/persona training continuity for `afs-scawful`.

## Production Baseline

- Primary avatar model: `echo-qwen25-7b-v4plusrepair_microfix3_20260225-q8_0.gguf`
- Eval status: 24/24 pass on `docs/eval/echoflow_avatar_eval_v2.jsonl`
- Registry defaults updated in `config/chat_registry.toml` (`scawful-echo`, `echo`, `avatar`)

## Completed Since Prior Jan State

- Echo JSON empty-output failure chain diagnosed and fixed through repair-seed v4/v5 + microfix2/microfix3.
- Avatar-Mix v1 training confirmed complete and converted to GGUF.
- Persona models (`sibyl`, `lancer`, `morpheus`, `anamnesis`) retrained on expanded datasets and converted to GGUF.
- Persona model ids in registry now point to deployed q8_0 artifacts.

## Open Work

1. Smoke eval all persona models via router/`afs chat` to confirm prompt injection behavior end-to-end.
2. Smoke eval Avatar-Mix role switching and decide if formal eval pack should be added.
3. Create and train new persona tracks:
   - `monolith` (brutalist code)
   - `conductor` (JSON DAG orchestration)
4. Expand avatar eval pack beyond current 24-case set.

## Fresh Run Results (2026-02-28)

- `monolith_v1` dataset expanded to 40 samples and trained on medical-mechanica.
- `conductor_v1` dataset expanded to 40 samples and trained on medical-mechanica.
- Adapters saved at:
  - `D:\afs_training\adapters\monolith_v1\`
  - `D:\afs_training\adapters\conductor_v1\`
- GGUFs created and synced locally:
  - `~/models/gguf/afs/monolith_v1-q8_0.gguf`
  - `~/models/gguf/afs/conductor_v2_microfix2-q8_0.gguf`
  - `~/models/gguf/afs/steward_v1-q8_0.gguf`
  - `~/models/gguf/afs/journalist_v1-q8_0.gguf`
  - `~/models/gguf/afs/poet_v3-q8_0.gguf`
  - `~/models/gguf/afs/essayist_v2-q8_0.gguf`
- LM Studio smoke:
  - Monolith: basic Bash prompt passes.
  - Conductor (iterative): `v2` = 5/8, `v2_microfix` = 6/8, `v2_microfix2` = 8/8.
- Promoted Conductor model id:
  - `gguf/afs/conductor_v2_microfix2-q8_0.gguf`
- Added writing/productivity personas:
  - `steward` for task management/backlog sequencing
  - `journalist` for journaling reflection
  - `poet` for poem drafting/style transfer
  - `essayist` for thesis-driven long-form writing
- Dataset quality update:
  - `poet_v2`: generated with OpenAI teacher, `synthetic_fallback=0/40`
  - `poet_v3`: regenerated with strict compact-form constraints (`4-10 lines`, `<120 words`)
  - `essayist_v2`: generated with Gemini teacher, `synthetic_fallback=0/40`
- Registry promotion update:
  - `poet` -> `gguf/afs/poet_v3-q8_0.gguf`
  - `essayist` -> `gguf/afs/essayist_v2-q8_0.gguf`
- Writing eval update:
  - baseline `poet_v2`: 5/8 (all fails = overlength)
  - promoted `poet_v3`: 8/8
  - `essayist_v2`: 8/8
- Eval reports:
  - `docs/eval/conductor_json_smoke_freeform_20260226.json`
  - `docs/eval/conductor_json_smoke_freeform_v2_20260226.json`
  - `docs/eval/conductor_json_smoke_freeform_v2_microfix_20260226.json`
  - `docs/eval/conductor_json_smoke_freeform_v2_microfix2_20260226.json`
  - `docs/eval/writing_smoke_eval_20260228.json` (baseline: poet_v2=5/8, essayist_v2=8/8)
  - `docs/eval/writing_smoke_eval_poet_v3_20260228.json` (promoted: poet_v3=8/8, essayist_v2=8/8)

## Continuation Notes

- Session handoff reference: `docs/AVATAR_PERSONA_SESSION_20260225.md`
- New continuation target: build eval packs for `poet` and `essayist` and run quality gates for v2/v3 iteration.
- Fast audit command:
  - `python3 scripts/dataset_audit.py --section data`
