# AFS-Scawful: Model Training Strategy

> **Working with Gemini agent in parallel.** Claude handles CLI tooling and strategy;
> Gemini handles distillation pipeline execution and dataset generation.

---

## Current Model Roster

| Name | Role | Base | Status |
|------|------|------|--------|
| Echo | Persona (scawful voice) | Gemma 2 9B | Active |
| Memory | Archivist — rationale recall | Qwen 2.5 3B | Training |
| Muse | Divergent ideation | Qwen 2.5 3B | Training |
| Din | 65816 optimization | Qwen 2.5 7B | Active |
| Nayru | Code generation | Qwen 2.5 14B | Active |
| Farore | Debugging | Qwen 2.5 7B | Active |
| Veran | Oracle of Secrets analysis | Qwen 2.5 7B | Active |

---

## New Model Proposals

### Anti-Slop Tier: Code Quality Enforcement

#### **Ockham** *(The Razor)*
- **Name origin:** William of Ockham — "Entities shall not be multiplied beyond necessity"
- **Role:** Receives bloated/sloppy code, returns minimal idiomatic equivalent
- **System prompt:** "You are Ockham. Your law: entities shall not be multiplied beyond
  necessity. Remove abstractions that serve no measurable purpose. Eradicate boilerplate.
  Output only what must exist."
- **Training data:** `anti_slop_v1.jsonl` — gold-standard barista/yaze/zelda3 C/C++ code
  as OUTPUT, LLM-generated "enterprise" versions as INPUT
- **Gold sources:** `barista/helpers/*.c` (memory-mapped C), `yaze/src/**/*.cc` (emulator C++)
- **Base model:** Qwen 2.5 3B (small = fewer tokens = naturally terse)
- **Why yaze carefully:** yaze has both clean core emulation code and some heavier abstraction
  in the editor layers. Use only `src/app/emu/*.cc` and `src/core/*.cc` — avoid GUI/editor code.
- **Tooling:** `scripts/antislop_dataset.py generate --source barista,yaze`

#### **Argos** *(The All-Seeing)*
- **Role:** Code reviewer. Catches over-engineering, magic constants, silent failures,
  spaghetti patterns. Returns specific actionable critique — never generic praise.
- **Training data:** Extract code review conversations from Claude logs (`logprune extract
  --filter coding`). Augment with synthetic (bad_code → critique → fixed_code) triples.
- **System prompt:** "You are Argos. You see everything. You do not soften feedback.
  You identify the precise line where the problem is, explain why it's wrong, and show
  the minimal fix. You never suggest adding more code to fix a code problem."
- **Base model:** Qwen 2.5 7B

---

### Cross-Project Intelligence

#### **Weaver** *(The Synapse)*
- **Role:** Maps the dependency graph of ideas across `~/src`. Knows how barista's
  memory-mapped IPC pattern applies to a new Python project. Knows when you've already
  solved the problem you're describing.
- **Training data:** `weaver_index.jsonl` + distilled Q&A pairs
- **Tooling:** `scripts/weaver_index.py build && scripts/weaver_index.py generate`
- **Moonshot:** Could eventually power a Spotlight-like semantic search across all projects

#### **Thoth** *(The Scribe)*
- **Role:** Learns from your actual Claude/Gemini/Codex conversation logs. Reproduces
  your agentic patterns — how you break down problems, what you ask for, how you iterate.
- **Training data:** `logprune extract --format chatml --min-score 0.6 --filter tool_use`
- **Special:** Thoth is trained on the *structure* of good agentic sessions, not just the
  content. It learns "first read the file, then propose the edit, then verify" from your
  actual log patterns.

---

### Persona-Based Models (Personal Assistant Tier)

These models are trained to understand your personality, workflow, interests, and needs.
They don't need to be coding experts — they need to *sound like you* and *work like you*.

#### **Sibyl** *(The Oracle of Daily Life)*
- **Role:** ADHD-aware daily assistant. Knows EchoFlow's Capture → Flow → Reflect loop.
  Helps with brain dumps, decision triage, task prioritization. Does NOT give generic
  productivity advice — gives advice that matches how your brain actually works.
- **Personality traits to capture:**
  - Direct, action-oriented, low tolerance for vague suggestions
  - Prefers concrete next actions over abstract frameworks
  - Uses technical vocabulary naturally (not performatively)
  - Understands hyperfocus and context-switching costs
- **Training data sources:**
  - EchoFlow journal entries + captured brain dumps
  - High-quality Claude sessions involving daily planning
  - The EchoFlow data models themselves (Entry, FocusSession, DailyMomentum)
    — shows what you think is worth tracking
- **System prompt:** "You are Sibyl. You know how scawful works: deep focus windows,
  brain dumps before decisions, the daily loop. You help him triage, not just list options."

#### **Lancer** *(The Battle Cry)*
- **Role:** The "get unstuck NOW" model. Zero comfort zone, all momentum.
  When you're procrastinating or paralyzed, Lancer gives you one concrete command to
  execute in the next 60 seconds. No soft language, no "you might want to consider."
- **Training data:** Moments in your Claude logs where you broke through paralysis.
  Synthetic pairs: (stuck situation description) → (direct one-action command)
- **System prompt:** "You are Lancer. scawful is stuck. Give him exactly one thing to do
  right now. Use imperative mood. No alternatives. No caveats. Go."
- **Base model:** Any small fast model (Qwen 2.5 1.5B — must be instant)

#### **Morpheus** *(The Dreamweaver)*
- **Role:** Brainstorming partner for moonshot ideas. Knows your actual interests:
  SNES emulation, barista/menubar UX, agentic AI systems, ADHD tools, Swift/iOS.
  Takes one of your real projects and proposes wild creative extensions.
- **Training data:**
  - The `docs/eval/memory_muse_distill_prompts_v1.jsonl` Muse-style prompts
  - Creative ideation sessions from your Claude logs
  - Synthetic: (project description) → (5 moonshot ideas that connect to your other projects)
- **System prompt:** "You are Morpheus. You know scawful's entire universe of projects.
  Every idea you generate connects something he already built to something he hasn't
  imagined yet. Be specific. Reference real files and patterns he has."

#### **Anamnesis** *(The Rememberer)*
- **Role:** Personal decision historian. "Why did I choose SwiftData over Core Data?"
  "When did I start the AFS project and what was the trigger?" Answers from actual history.
- **Training data:** Git commit history across all `~/src` repos, afs-scawful decision docs,
  Claude session logs with architectural decisions
- **System prompt:** "You are Anamnesis. You recall what was decided and why.
  You speak from the actual record, not from generic reasoning."

---

### Adversarial / Safety Tier

#### **Entropy** *(The Red Team)*
- **Role:** Assumes your plans will fail. Finds the critical path to failure before you
  run the code. Best used before big deploys, architecture changes, or training runs.
- **Training data:** Post-mortems, reverted commits, failed CI logs, `git bisect` sessions
  extracted from git history across `~/src`
- **System prompt:** "You are Entropy. Every system tends toward disorder. Find the
  weakest assumption in this plan. What breaks first? What were you wrong about?"

#### **Lethe** *(The Privacy Scrubber)*
- **Role:** Strips PII, private keys, personal content from logs before using as training data
- **Training data:** Pairs of (raw log) → (scrubbed log), where scrubbing is verified correct
- **Practical use:** Run automatically in `logprune prune` pipeline before any dataset export

---

## Training Data Sources

### From Your Machine Right Now

| Source | Tool | What it yields |
|--------|------|----------------|
| Claude logs | `logprune extract` | Agentic coding pairs, decision patterns |
| barista + yaze code | `antislop_dataset.py generate` | Ockham training pairs |
| `~/src` README corpus | `weaver_index.py build` | Cross-project knowledge graph |
| Git commit history | `generate_git_history_samples.py` (exists) | Decision timeline |
| afs-scawful docs | `extract_decision_context.py` (Gemini-built) | Memory/Muse prompts |

### Distillation Pipeline

```
Claude logs / docs                          Teacher model (Gemini 3.1 Pro)
     │                                               │
     ▼                                               ▼
logprune extract          ──────────────────► distill_memory_muse.py run
                                                     │
antislop_dataset.py                                  ▼
generate                  ──────────────────► anti_slop_v1.jsonl
                                                     │
weaver_index.py build                                ▼
weaver_index.py generate  ──────────────────► weaver_v1.jsonl
                                                     │
                                                     ▼
                                            Training (LoRA / PEFT)
                                            Base: Qwen 2.5 3B/7B
```

### Unique Data Nobody Else Has

1. **Your Claude conversation logs** — 123+ JSONL files showing exactly how *you* do
   agentic development. This is irreplaceable self-supervised data.
2. **barista/yaze clean code** — Real, working, production-quality C/C++ from your hand
3. **EchoFlow SwiftData models** — Show what you think is worth persisting (very personal)
4. **Oracle of Secrets ASM** — 77k+ lines of decompiled SNES code with your annotations
5. **git history across ~/src** — Longitudinal record of all decisions and reverts

---

## Anti-Slop Training Philosophy

The goal is models that write code the way the best engineers at small, high-craft shops do:
- **Constraint-aware:** Know the limits of the system they're working in
- **Observable:** State machines, version counters, explicit error paths
- **Minimal:** No abstraction without measurable benefit
- **Testable:** Pure functions, explicit dependencies, no hidden state

**What we're fighting:**
- Unnecessary wrapper classes ("DatabaseManager" that wraps one function)
- Over-verbose docstrings that restate the function signature
- Error handling that catches `Exception` and swallows it
- Configuration objects for things that never change
- "Factory" patterns for types with one implementation

**Ockham training pair structure:**
```json
{
  "messages": [
    {"role": "system", "content": "You are Ockham..."},
    {"role": "user", "content": "# Refactor this bloated code\n\n```c\n[enterprise slop]\n```"},
    {"role": "assistant", "content": "```c\n[barista-quality pristine]\n```"}
  ]
}
```

---

## CLI Tools Reference

```bash
# Extract training pairs from Claude logs
python scripts/logprune.py stats
python scripts/logprune.py extract --min-score 0.6 --format chatml --output claude_pairs.jsonl
python scripts/logprune.py extract --filter tool_use --output agentic_pairs.jsonl
python scripts/logprune.py prune --output ~/safe_logs/   # Remove private content

# Build anti-slop dataset (Ockham)
python scripts/antislop_dataset.py scan                  # See available source files
python scripts/antislop_dataset.py generate --source barista,yaze --teacher gemini
python scripts/antislop_dataset.py stats

# Build cross-project intelligence (Weaver)
python3 scripts/weaver_index.py build                    # Index ~/src
python3 scripts/weaver_index.py stats
python3 scripts/weaver_index.py generate --teacher gemini
python3 scripts/weaver_index.py distill                  # Fill [answer pending] placeholders

# Run Memory/Muse distillation (continue Gemini agent's work)
python scripts/distill_memory_muse.py run                # Auto-resumes from checkpoint
python scripts/distill_memory_muse.py run --limit 71     # Complete remaining 71 prompts
python scripts/distill_memory_muse.py stats

# Build persona training datasets (Sibyl, Lancer, Morpheus, Anamnesis)
python3 scripts/persona_dataset.py mine                   # Extract raw voice (668 turns, 3120 commits, 567 doc sections)
python3 scripts/persona_dataset.py voice                  # Show sampled user turn voice profile
python3 scripts/persona_dataset.py generate --persona sibyl    --teacher gemini
python3 scripts/persona_dataset.py generate --persona lancer   --teacher gemini
python3 scripts/persona_dataset.py generate --persona morpheus --teacher gemini
python3 scripts/persona_dataset.py generate --persona anamnesis --teacher gemini
python3 scripts/persona_dataset.py stats                  # All persona dataset stats

# Train Avatar-Mix v1 (Qwen 2.5 7B, 5 personas, rank=64) — GPU only
python3 scripts/train_avatar_mix.py
python3 scripts/train_avatar_mix.py --model-name Qwen/Qwen2.5-7B-Instruct --rank 64 --epochs 5

# Train single persona models (Qwen 2.5 3B, rank=32) — GPU only
python3 scripts/train_persona.py --persona sibyl
python3 scripts/train_persona.py --persona lancer
python3 scripts/train_persona.py --persona morpheus
python3 scripts/train_persona.py --persona anamnesis

# Existing distillation pipeline (assembly / oracle)
python3 scripts/distill_cloud.py --prompts docs/eval/distill_prompts_v1.jsonl \
    --models gemini-3.1-pro,sonnet-4.6 --output distill_cloud_v2.jsonl
```

---

## Mined Persona Data (data/persona_raw/)

| File | Content | Count |
|------|---------|-------|
| `log_user_turns.jsonl` | Claude log user turns (non-private) | 668 |
| `git_commits.jsonl` | Commit messages across ~/src repos | 3120 |
| `doc_excerpts.jsonl` | CLAUDE.md, AGENTS.md, docs/ sections | 567 |
| `echoflow_models.jsonl` | EchoFlow Swift model definitions | 12 |
| `self_briefing.txt` | Full developer self-briefing (6.9k chars) | 1 |

The self-briefing is the Rosetta Stone for all persona models — embedded in Sibyl,
Morpheus, and Anamnesis system prompts at generation time.

---

## Dataset Status (2026-02-25)

| Dataset | File | Samples | Status |
|---------|------|---------|--------|
| Memory/Muse distillation | `memory_muse_distill_v1.jsonl` | 344 | ✓ Done |
| Claude log pairs | `claude_log_pairs.jsonl` | 136 | ✓ Done |
| Anti-slop (Ockham) | `anti_slop_v1.jsonl` | 80 (barista 43, yaze 21) | ✓ Done |
| Weaver Q&A | `weaver_v1.jsonl` | 50 (all distilled) | ✓ Done |
| Sibyl | `sibyl_v1.jsonl` | 14 | ✓ Done |
| Lancer | `lancer_v1.jsonl` | 38 | ✓ Done |
| Morpheus | `morpheus_v1.jsonl` | 10 | ✓ Done |
| Anamnesis | `anamnesis_v1.jsonl` | 22 | ✓ Done |
| Avatar-Mix (Gemini) | `avatar_mix_run_v1/train.jsonl` | 83 | ✓ Staged for training |
| **TOTAL** | | **694** | |

## Model Registry (chat_registry.toml)

| Model | Registered | GGUF Path (planned) | Tags |
|-------|-----------|---------------------|------|
| din | ✓ | gguf/zelda/din-7b-v4-q4km.gguf | oracle |
| nayru | ✓ | gguf/zelda/nayru-7b-v1-q8.gguf | oracle |
| farore | ✓ | gguf/zelda/farore-7b-v5-q8.gguf | oracle |
| veran | ✓ | gguf/zelda/veran-7b-v1-q8.gguf | oracle |
| avatar-mix | ✓ | gguf/afs/avatar-mix-v1-q8.gguf | avatar, composite |
| sibyl | ✓ | gguf/afs/sibyl-v1-q4km.gguf | persona, daily |
| lancer | ✓ | gguf/afs/lancer-v1-q4km.gguf | persona, focus |
| morpheus | ✓ | gguf/afs/morpheus-v1-q4km.gguf | persona, creative |
| anamnesis | ✓ | gguf/afs/anamnesis-v1-q4km.gguf | persona, memory |

## API Notes
- **Use `python3`** (not `python` which is Python 2 on this machine)
- **Gemini model**: Use `gemini-2.0-flash` for persona generation (flash for short outputs)
- **Gemini model**: Use `gemini-2.5-pro` with `max_output_tokens=8192` for distillation
  (thinking model needs large budget; `max_output_tokens=1024` causes empty responses)
- `google.generativeai` is deprecated — all scripts use `from google import genai`
- **Rate limits**: Don't run >2 concurrent Gemini jobs (antislop + distillation = 429 errors)

## Weaver Distillation
`weaver_index.py distill` fills `[answer pending distillation]` placeholders in `weaver_v1.jsonl`.
Uses `gemini-2.0-flash` (sequential, not concurrent — avoids rate limits from other running jobs).
Re-run after antislop jobs finish if rate-limited.

## Anti-slop yaze Scope
`antislop_dataset.py` now has `include_dirs` support — yaze is restricted to:
- `src/app/emu/` — hardware emulation state machines
- `src/core/` — core data structures and algorithms
This excludes GUI, editor, and tool code (not gold-standard for Ockham training).

## Next Steps (Priority Order)

1. **Complete Memory/Muse distillation** — `python3 scripts/distill_memory_muse.py run` (34 remaining)

2. **Complete Ockham dataset** — currently running barista (40 files) + yaze (30 files)
   Re-run if rate-limited: `python3 scripts/antislop_dataset.py generate --source barista --max-files 50`
   Target: 100+ pairs total.

3. **Distill Weaver Q&A** — run after antislop jobs finish to avoid rate limits:
   `python3 scripts/weaver_index.py distill`

4. **Train Avatar-Mix v1** — on GPU machine (Medical Mechanica / Vast.ai):
   `python3 scripts/train_avatar_mix.py` using `data/avatar_mix_run_v1/train.jsonl`
   Qwen 2.5 7B + 5 personas + QLoRA rank=64

5. **Launch persona LoRA training** — `train_persona.py` handles all 4 personas (Qwen 2.5 3B):
   ```bash
   python3 scripts/train_persona.py --persona sibyl
   python3 scripts/train_persona.py --persona lancer
   python3 scripts/train_persona.py --persona morpheus
   python3 scripts/train_persona.py --persona anamnesis
   ```
   Default: rank=32, alpha=64, 6 epochs, lr=2e-4, Qwen/Qwen2.5-3B-Instruct

6. **Convert to GGUF** — after training, convert adapters to GGUF format for LM Studio
