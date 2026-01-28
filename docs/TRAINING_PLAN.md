# Training Plan (AFS Scawful)

Scope: local-only training data pipelines and evaluation for AFS workflows.
Research-only. See `../afs/docs/RESEARCH_SOURCES.md` for citations.

## Goals
- Keep datasets reproducible, small, and auditable.
- Prioritize agentic filesystem primitives before model training complexity.
- Use evaluation loops to avoid training on noise.

## Phase 0 — Inventory + Research Catalog (now)
- Use `afs_scawful research catalog` to index `~/Documents/Research`.
- Keep the catalog JSON in `~/.context/index/research_catalog.json`.
- Verify metadata/abstract excerpts before quoting. [R1]

## Phase 1 — Dataset QA (near-term)
- Expand dataset registry with QA summaries (counts, schema drift, invalid rows).
- Define a minimal JSON schema for training samples.
- Track provenance per dataset and per generator. [R1]

## Phase 2 — Task Design (near-term)
- Start with repo-level navigation tasks that assume a small tool surface. [R3]
- Keep tasks focused on file discovery, symbol lookup, and context assembly.
- Use small, deterministic datasets to validate task framing before scaling.

## Phase 3 — Context Packaging (mid-term)
- Treat training samples as explicit context pipelines with clear state and error
  propagation. [R4]
- Build a minimal "context transcript" format (inputs, tool calls, outputs).

## Phase 4 — Evaluation (mid-term)
- Add human+agent evaluation metrics to avoid overfitting to synthetic tasks. [R7]
- Include tone-variant prompts as a controlled ablation (optional). [R6]

## Phase 5 — Efficiency References (later)
- Use MoE efficiency papers only when scaling becomes a bottleneck. [R5]

## Unknown / needs verification
- Which tasks best reflect AFS workflows (agentic filesystem vs orchestration).
- Whether RL is needed or if supervised data is sufficient for early stages.

## Citations
- [R1] `../afs/docs/RESEARCH_SOURCES.md`
- [R3] `../afs/docs/RESEARCH_SOURCES.md`
- [R4] `../afs/docs/RESEARCH_SOURCES.md`
- [R5] `../afs/docs/RESEARCH_SOURCES.md`
- [R6] `../afs/docs/RESEARCH_SOURCES.md`
- [R7] `../afs/docs/RESEARCH_SOURCES.md`
