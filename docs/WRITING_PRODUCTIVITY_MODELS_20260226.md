# Writing + Productivity Model Plan (2026-02-26)

Scope: propose next local models for journaling, poems, essay writing, and task management.
Assumes current stack (Echo/Sibyl/Lancer/Anamnesis/Morpheus + LM Studio routing).

## Proposed Models

| Model | Size | Role | Primary Data |
|------|------|------|------|
| **journalist-v1** | 3B | Daily reflection partner, converts raw entries into structured insight | EchoFlow entries, personal journal prompts, anonymized reflection logs |
| **poet-v1** | 1.5B or 3B | Poetry drafting and style variation (haiku/free verse/sonnet-like constraints) | Curated poem corpus + personal voice style snippets |
| **essayist-v1** | 3B (v1) | Long-form argumentation, outline-to-draft, revision passes | Long-form notes/docs/commit rationale + essay-style instruction pairs |
| **steward-v1** | 3B | Task management operator: triage, sequencing, execution checkpoints | Sibyl/Lancer datasets + halext-org task patterns + completed task histories |

## Why This Split

- Journaling and task-management should stay deterministic and low-latency.
- Poetry benefits from high creativity and smaller fast iteration loops.
- Essays need stronger coherence over longer context windows.
- Separate experts avoid role conflict between emotional reflection, creative language, and operational planning.

## Router Intents (Draft)

- `journal`, `reflect`, `daily log`, `what did i learn` -> `journalist`
- `poem`, `verse`, `haiku`, `rewrite poetically` -> `poet`
- `essay`, `argument`, `thesis`, `long-form draft` -> `essayist`
- `plan tasks`, `prioritize`, `next actions`, `weekly plan` -> `steward`

## Dataset Build Plan

1. `journalist-v1`
- Mine EchoFlow reflection-style entries and convert to `messages` format.
- Add pairs: raw journal -> summary, summary -> next-day intention.
- Include explicit "unknown / insufficient data" examples to prevent overconfident interpretation.

2. `poet-v1`
- Build prompt bank by form: free verse, short imagist, constrained syllable, metaphor remix.
- Add style-transfer pairs from literal prose -> poetic version.
- Keep strict filter for cliché and over-ornamented output.

3. `essayist-v1`
- Generate outline-first training pairs:
  - prompt -> thesis + outline
  - outline -> section draft
  - draft -> revision pass (clarity/tightness/citation placeholders)
- Include anti-slop negative pairs to reduce generic filler.

4. `steward-v1`
- Merge Sibyl (triage) + Lancer (single action) behaviors into phased plans:
  - triage -> sequence -> first action -> review checkpoint
- Add task state transitions from halext-org patterns where available.

## Eval Packs Needed

- `docs/eval/journalist_eval_v1.jsonl`
  - coherence, emotional fidelity, no fabricated memory, useful next-step prompts.
- `docs/eval/poet_eval_v1.jsonl`
  - imagery density, originality, form adherence, tone control.
- `docs/eval/essayist_eval_v1.jsonl`
  - thesis clarity, structure, paragraph cohesion, revision quality.
- `docs/eval/steward_eval_v1.jsonl`
  - priority quality, actionability, sequencing correctness, over-planning avoidance.

## Rollout Order

1. `steward-v1` (highest immediate utility, lowest risk)
2. `journalist-v1`
3. `essayist-v1`
4. `poet-v1`

## Execution Update (Completed 2026-02-28)

- `steward-v1` dataset generated to 40 samples and trained on medical-mechanica.
- `journalist-v1` dataset generated to 40 samples and trained on medical-mechanica.
- `poet-v1` dataset generated to 40 samples and trained on medical-mechanica.
- `essayist-v1` dataset generated to 40 samples and trained on medical-mechanica.
- v2 regeneration + promotion:
  - `poet_v2` generated with OpenAI teacher (`synthetic_fallback=0/40`)
  - `essayist_v2` generated with Gemini teacher (`synthetic_fallback=0/40`)
- v3 poet tightening + promotion:
  - `poet_v3` generated with explicit compact constraints (`4-10 lines`, `<120 words`)
  - writing eval improved from 5/8 (`poet_v2`) to 8/8 (`poet_v3`)
- Promoted GGUF artifacts:
  - `gguf/afs/steward_v1-q8_0.gguf`
  - `gguf/afs/journalist_v1-q8_0.gguf`
  - `gguf/afs/poet_v3-q8_0.gguf`
  - `gguf/afs/essayist_v2-q8_0.gguf`
- Router + registry wired in `config/chat_registry.toml`:
  - task-management intents -> `steward`
  - journaling intents -> `journalist`
  - poem/verse intents -> `poet`
  - essay/thesis intents -> `essayist`
- Note: `poet_v1` / `essayist_v1` synthetic fallback runs are retained as historical artifacts but superseded by v2.

## Immediate Next Commands

- Build eval packs:
  - `docs/eval/poet_eval_v1.jsonl`
  - `docs/eval/essayist_eval_v1.jsonl`
- Add quality gates:
  - style adherence + cliché rate for `poet_v3`
  - thesis coherence + paragraph transitions for `essayist_v2`

## Execution Update (Continued 2026-02-28)

- Added strict poetry form gate:
  - `scripts/poet_form_eval.py`
  - checks: haiku/limerick/sonnet/imagist/free_verse with explicit fail reasons.
- Built repair set from form failures:
  - `scripts/build_poet_v5_repair_dataset.py`
  - output: `docs/eval/poet_repair_v5_20260228/`
- Trained and exported `poet_v5`:
  - artifact: `gguf/afs/poet_v5-q8_0.gguf`
- Latest strict form eval results:
  - `docs/eval/poet_form_eval_v4_vs_v5_20260228.json`: `v4=7/13`, `v5=7/13`
  - `docs/eval/poet_form_eval_v3_v4_v5_t02_20260228.json` (`temperature=0.2`): `v3=6/13`, `v4=4/13`, `v5=7/13`
- Registry promotion decisions:
  - `poet` -> `gguf/afs/poet_v5-q8_0.gguf`
  - `conductor` -> `gguf/afs/conductor_v3-q8_0.gguf`

## Execution Update (Steward v2, 2026-02-28)

- Added strict Steward gate:
  - `scripts/steward_eval.py`
  - checks: non-destructive planning, first irreversible action, numbered sequence, checkpoints.
- Built failure-driven repair set:
  - `scripts/build_steward_v2_repair_dataset.py`
  - output: `docs/eval/steward_repair_v2_20260228/` (57 rows).
- Trained + exported `steward_v2`:
  - artifact: `gguf/afs/steward_v2-q8_0.gguf`
- Eval results:
  - `docs/eval/steward_eval_v1_vs_v2_20260228.json` (`temperature=0.35`): `v1=1/10`, `v2=5/10`
  - `docs/eval/steward_eval_v1_vs_v2_t02_20260228.json` (`temperature=0.2`): `v1=1/10`, `v2=8/10`
- Registry update:
  - `steward` -> `gguf/afs/steward_v2-q8_0.gguf`
  - `steward.temperature` -> `0.2`

## Execution Update (Steward v3, 2026-02-28)

- Built checkpoint-targeted repair set:
  - `scripts/build_steward_v3_checkpoint_dataset.py`
  - output: `docs/eval/steward_repair_v3_20260228/` (18 rows, checkpoint-focused).
- Trained + exported `steward_v3`:
  - artifact: `gguf/afs/steward_v3-q8_0.gguf`
- Side-by-side strict eval (`steward_v2` vs `steward_v3`):
  - `docs/eval/steward_eval_v2_vs_v3_t02_20260228.json`: `v2=8/10`, `v3=7/10`
  - `docs/eval/steward_eval_v2_vs_v3_t03_20260228.json`: `v2=6/10`, `v3=7/10`
  - `docs/eval/steward_eval_v2_vs_v3_t035_20260228.json`: `v2=3/10`, `v3=9/10`
- Promotion decision:
  - `steward` -> `gguf/afs/steward_v3-q8_0.gguf`
  - `steward.temperature` -> `0.3` (better aggregate actionability than `v2`; avoids `v2` collapse at higher temperature).
