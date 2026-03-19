# Model Portfolio

Last updated: 2026-02-28
Source of truth for all model families, their roles, training status, and how they connect.

---

## System Map

```
You ask something
    │
    ├── oracle router ─────────────────────────────────────────────────────┐
    │   keyword: optimize/explain/autocomplete/analyze/build               │
    │   └── Din / Nayru / Farore / Veran / Agahnim / Majora / Hylia       │
    │       IQuest-40B / Oracle-Tools / Sahasrahla-3B                      │
    │       (65816 ASM, Oracle of Secrets, SNES hardware)                  │
    │                                                                       │
    └── avatar router ─────────────────────────────────────────────────────┘
        keyword: chat/draft/remember/brainstorm/stuck/plan/why-did-i/etc.
        │
        ├── echo          voice, casual conversation, code review
        ├── memory        factual recall (dates, people, places)
        ├── muse          creative divergence, brainstorm
        ├── scribe        convergence, documentation, clean notes
        ├── avatar-mix    composite (Archivist/Muse/Weaver/Ockham/Sentinel)
        │
        └── persona sub-router
            ├── sibyl     ADHD triage, daily planning
            ├── lancer    one imperative action when stuck
            ├── morpheus  moonshot ideas, cross-project connections
            ├── anamnesis decision historian, speaks from the record
            ├── steward   backlog sequencing, execution checkpoints
            ├── journalist journaling reflection and pattern extraction
            ├── poet      poem drafting and style transfer
            └── essayist  thesis-driven long-form drafting
```

---

## Oracle Family — 65816 / SNES / Zelda

Fine-tuned for ROM hacking. All served locally via LM Studio as GGUF.
Routing: keyword-based, default → Veran.

### Core Four (~7B Qwen2.5 Coder)

| Model | Role | Temp | Notes |
|-------|------|------|-------|
| **Din** | Optimization | 0.3 | STZ, backward loops, remove unnecessary SEP/REP. Outputs only the optimized version, never the original. |
| **Nayru** | Explanation / docs | 0.4 | DMA/VRAM/OAM templates, WaitVBlank, controller reads. Patient and thorough. |
| **Farore** | Autocomplete / debug | 0.3 | FIM, register-mode mismatch, stack imbalance, quick-inference. |
| **Veran** | Deep analysis | 0.3 | PPU/DMA/HDMA/Mode7 reference. Large context, edge cases, default fallback. |

### Specialists

| Model | Size | Role |
|-------|------|------|
| **Hylia** | 3B | OOS development history and lore. Timeline context, design rationale. |
| **Majora** | 7B | OOS codebase architecture. Bank map, item/overworld/sprite systems, common bugs (ZSOW desyncs, color math persistence). |
| **Agahnim** | 3B | Build/integration. asar patches, pushpc/pullpc hooks, JSL trampolines, namespace bridging Oracle↔ZScream. |
| **Oracle-Tools** | 7B Coder | Structured tool-calling for emulator workflows. JSON calls for yaze-mcp, Mesen2 socket CLI, memory inspection. |
| **IQuest-Coder-40B** | 40B | Primary ASM coding model. Trained on ASAR-validated gold + OOS source + correction samples (~15k records). Q3_K_M on Mac, served remotely for production. |
| **Sahasrahla-3B** | 3B | Nintendo/ALTTP historian. 10k+ records from legacy hacks (Gigaleak, Poltergeist, ZScreamDungeon). Q4_K_M, llama-server. |

### Oracle Router Rules

```
optimize / faster / performance / cycles / tighten  →  Din
refactor / rewrite / cleanup                        →  Din
explain / document / describe / why / teach         →  Nayru
autocomplete / fim / fill in / snippet / quick      →  Farore
(default)                                           →  Veran
```

---

## Avatar Family — Personal AI Layer

Fine-tuned on Justin's writing, Claude session logs, and workflow data.
Not for code — for voice, recall, and productivity.

### Echo (the voice model)

**Current:** `echo-qwen25-7b-v4plusrepair_microfix_20260212-f16.gguf`
**Eval:** 19/24 (79.2%) on standard eval, 22/24 (92%) with constrained JSON decoding

Lowercase, candid, dry humor, stream-of-consciousness. Five generations:

```
v2 (chat-first)
  └── v3 (personal voice, no Twitter)
        └── v4 (tone distill + tool samples)
              └── v4plusrepair (+ repair dataset)
                    └── microfix (low-LR resume, current)
                          └── microfix2 (pending — repair seed v4 fixes JSON bug)
```

Known issue: 4 JSON eval cases produce empty output in free-form mode. Root cause traced to
self-referential training prompts, wrong hardcoded outputs, and 8× repetition in repair seed.
Fixed in `build_echo_repair_dataset.py` (2026-02-25). Repair seed v4 pushed to medical-mechanica.
Microfix2 run queued after persona training completes.

**Fallback:** `echo-qwen25-1p5b-repair_20260211_morning-f16.gguf` — 88% strictfix eval, fast.

### Supporting Avatars

| Model | Role | Temp |
|-------|------|------|
| **Memory** | Factual recall — dates, places, people, personal facts. Never speculates. | 0.1 |
| **Muse** | Creative divergence — brainstorm, wild concepts, metaphors, absurdist ideas. | 0.9 |
| **Scribe** | Convergence — takes messy input, outputs clean notes, summaries, specs. | 0.2 |

### Avatar-Mix v1 (trained 2026-02-25, ~34 min, RTX 5060 Ti)

**Base:** Qwen2.5-7B-Instruct · **Adapter:** `D:\afs_training\models\avatar_mix_v1\lora_adapters\`
**Training:** 434 samples, 5 epochs, rank 64, final loss 0.456

Five roles in one model, context-switches dynamically:

| Sub-role | Function |
|----------|----------|
| **Archivist** | Recalls decisions from commit history and design docs |
| **Muse** | Lateral non-obvious connections and moonshot ideas |
| **Weaver** | Maps how patterns in one project solve problems in another |
| **Ockham** | Minimal idiomatic code — removes purposeless abstractions |
| **Sentinel** | Finds where code has drifted from documentation; names the exact failure point |

Dataset mix: memory/muse distillation (344) + claude log pairs (136) + weaver Q&A (50) +
anti-slop code examples (80) + swift session logs (17) + others → 434 total curated.

Pending: GGUF conversion → registry entry (`avatar-mix-v1-q8.gguf`).

### Avatar Router Rules

```
remember / recall / memory / what did i             →  memory
draft / summary / note / email / outline / write    →  scribe
brainstorm / idea / creative / story / metaphor     →  muse
reflect / feel / vent / status / chat               →  echo
stuck / paralyzed / can't start / just one thing    →  lancer
why did i / when did i / decision behind            →  anamnesis
plan my day / triage / adhd / brain dump            →  sibyl
moonshot / what if / connect / cross-project        →  morpheus
journal / diary / reflection / personal writing      →  journalist
poem / poetry / verse / lyrics                      →  poet
essay / thesis / argument / article draft           →  essayist
task management / backlog / next actions            →  steward
(default)                                           →  scawful-echo
```

---

## Persona Family — Productivity + Writing Layer

Small 3B Qwen2.5 Instruct adapters. Fast, single-purpose, invoked by keyword from avatar router.
Trained on `data/training_data/*_v1.jsonl` and promoted `v2` datasets where available. QLoRA rank 32, 6 epochs.

**Status (2026-02-28):** all listed persona models trained on medical-mechanica and converted to q8_0 GGUF.

| Model | Samples | Temp | System prompt intent |
|-------|---------|------|----------------------|
| **Sibyl** | 37 | 0.6 | ADHD-aware triage and daily execution planning. |
| **Lancer** | 40 | 0.5 | One imperative next action when stuck. |
| **Morpheus** | 32 | 0.95 | Moonshot ideation rooted in existing projects. |
| **Anamnesis** | 44 | 0.2 | Decision-history recall from real project records. |
| **Monolith** | 40 | 0.1 | Brutalist minimal Bash/C implementation style. |
| **Conductor** | 40 | 0.3 | JSON DAG orchestration for multi-agent handoffs. |
| **Steward** | 40 | 0.3 | Task backlog sequencing and irreversible first actions. |
| **Journalist** | 40 | 0.55 | Daily reflection and pattern extraction. |
| **Poet** | 40 | 0.85 | Poetry drafting, imagery, and tone-preserving rewrite. |
| **Essayist** | 40 | 0.45 | Thesis-driven long-form arguments and revisions. |

---

## Training Infrastructure

| System | Role |
|--------|------|
| **medical-mechanica** | Windows, RTX 5060 Ti 16GB. Local GPU training (7B–3B). |
| **Mac M5 (Oracle)** | Control plane, small inference, Q3_K_M 40B via llama-server. |
| **Vast.ai** | Heavy fine-tunes (A100/4090). Used for Echo v4, IQuest-40B, Memory Archivist. |

**Serving:** LM Studio (port 1234) is the preferred local inference server.
All models registered in `config/chat_registry.toml` with system prompts and temperature.

---

## Datasets (Feb 2026 snapshot)

| Dataset | Records | Purpose |
|---------|---------|---------|
| `memory_muse_distill_v1` | 344 | Avatar persona distillation |
| `claude_log_pairs` | 136 | Real Claude sessions (chatml) |
| `cpp_log_pairs` | 3,270 | yaze/Oracle C++ sessions (pairs) |
| `anti_slop_v1` | 80 | Clean code examples, no-bloat responses |
| `weaver_v1` | 50 | Cross-project Q&A (Gemini-distilled) |
| `avatar_mix_v1` | 434 | Avatar-Mix training set (curated mix) |
| `sibyl_v1` | 14 | Sibyl persona |
| `lancer_v1` | 38 | Lancer persona |
| `morpheus_v1` | 10 | Morpheus persona |
| `anamnesis_v1` | 22 | Anamnesis persona |
| `steward_v1` | 40 | Task-management persona |
| `journalist_v1` | 40 | Journaling-reflection persona |
| `poet_v1` | 40 | Poetry persona |
| `essayist_v1` | 40 | Essay persona |
| `poet_v2` | 40 | Poetry persona (live-teacher refresh) |
| `poet_v3` | 40 | Poetry persona (compact-form constraints, promoted) |
| `essayist_v2` | 40 | Essay persona (live-teacher refresh) |
| `swift_log_pairs` | 17 | EchoFlow/iOS sessions (chatml) |

Full inventory and pipeline scripts: `docs/MODEL_TRAINING_STRATEGY.md`.

---

## Proposed Writing + Task Models (2026-02-26)

For journaling, poems, essays, and task management expansion, see:

- `docs/WRITING_PRODUCTIVITY_MODELS_20260226.md`
