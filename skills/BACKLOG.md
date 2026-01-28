# Skills Backlog

Saved: 2026-01-25

## Active Initiative: Autonomous Debugging (Phase 4 Complete)
*See `docs/internal/plans/robustness-optimization-roadmap.md`.*

### Phase 3: Repair (Pending)
- [ ] **`patch_synthesizer.py`**: Loop to generate -> verify ASM.

---

## Completed

- **hyrule-navigator**: "Autonomous Player" implemented. `world_graph.json` generated, pathfinding verified. `z3ed` JSON output fixed.
- **trace-detective**: Scaffolded and enriched.
- **memory-cartographer**: Implemented `scripts/ai/memory_cartographer.py` (interactive RAM analysis).
- **romhack-asm-tuner**: Implemented `scripts/ai/asm_tuner.py` (syntax/style/patch checker).
- **z3ed-symbol-cli**: (Phase 1 P0) `z3ed` now supports symbol resolution (`rom-resolve-address`, `rom-find-symbol`).
- **visual-verifier**: (Phase 2 P1) Screenshot diffing and regression testing implemented.
- **headless-harness**: (Phase 1 P1) `scripts/ai/run_agent_test.sh` created for CI automation.
- **code-navigator**: (Phase 2 P2) `scripts/ai/code_graph.py` implemented for static analysis (Callers/Writes).
- **crash-investigator**: (Phase 3 P0) `scripts/ai/crash_dump.py` implemented (Trace Capture + Symbol Resolution).
- **sentinel**: (Phase 3 P1) `scripts/ai/sentinel.py` implemented (Softlock/Crash Watchdog).
- **source-blame**: (Phase 3 P2) `z3ed` + `crash_dump.py` now support source map resolution and snippet extraction.
- **chaos-monkey**: (Phase 4 P0) `scripts/ai/fuzzer.py` implemented (Random Input Stress Testing).
- **semantic-query**: (Phase 4 P2) `scripts/ai/state_query.py` implemented (Natural language state checks).
- **lag-detector**: (Phase 4 P1) `scripts/ai/profiler.py` implemented (PC Sampling & Hotspots).
- **diff-runner**: (Phase 4 P3) `scripts/ai/diff_runner.py` implemented (Regression Testing).

## Future Ideas

- **zelda-dialogue-style-trainer**: Build dialogue style datasets and eval voice fidelity.
- **lttp-world-knowledge-builder**: Assemble lore/map/item corpora and retrieval indexes.
