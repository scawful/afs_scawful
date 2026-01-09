# Oracle of Secrets: 2026 Release Integration Plan
**Strategy:** Hybrid Cloud/Local Orchestration
**Goal:** Leverage SOTA reasoning (Cloud) to drive specialized execution (Local AFS Models).

## 1. Architecture: The "Architect-Builder" Pattern

We will implement a two-tier system:
*   **Tier 1: The Architects (Cloud SOTA)**
    *   **Models:** Gemini 3 Pro, Claude Opus 4.5, GPT-5.2.
    *   **Role:** High-level reasoning, complex puzzle design, cross-system integration, creative direction, review.
    *   **Action:** They generate *prompts* and *specs*, not final code.

*   **Tier 2: The Builders (Local AFS Experts)**
    *   **Models:** Nayru (ASM), Din (Lore), Farore (Tasks), Veran (Logic).
    *   **Role:** Implementation, specific ASM syntax, RAM management, boilerplate generation.
    *   **Action:** They execute the specs provided by the Architects.

## 2. Workflow Pipelines

### Pipeline A: Feature Implementation (e.g., "Add a Hookshot Upgrade")
1.  **User Request:** "I need a Level 2 Hookshot that pulls enemies."
2.  **Farore (Local):** Breaks this down: `gfx_update`, `asm_routine`, `item_data_entry`.
3.  **Gemini 3 (Cloud):** Reviews the breakdown, checks for conflicts with existing items, suggests a specific RAM address strategy.
4.  **Nayru (Local):** Generates the 65816 ASM for the pulling logic based on Gemini's spec.
5.  **Gemini 3 (Cloud):** Code Reviews the ASM (via `code-review` extension principles).

### Pipeline B: Dungeon Design (e.g., "Sky Temple")
1.  **Din (Local):** Brainstorms 10 thematic concepts for rooms.
2.  **Claude Opus (Cloud):** Selects the best concepts and weaves them into a cohesive dungeon pacing/flow chart.
3.  **Veran (Local):** Validates the logic of the puzzles (e.g., "Is this key reachable?").
4.  **Nanobanana (Tool):** Generates the map visual.

## 3. Immediate Actions (Q1 2026)

1.  **Integration Script (`orchestrator.py`):**
    *   Build a script that allows a Cloud Model to "call" a Local Model.
    *   *Example:* Gemini generates a function call `call_agent("nayru", prompt="...")`.

2.  **Context Injection Improvements:**
    *   Update **Veran's** system prompt with `ZELDA3_RAM_MAP` and `ENGINE_FLAGS` to fix the abstract output issue.

3.  **Romhack Automation:**
    *   Connect **Nayru** output directly to `build_ai/` folder.
    *   Auto-run `asar` to verify assembly correctness immediately.

## 4. Hardware Utilization
*   **Mac Studio (Oracle):** Runs the Local Builders (Ollama/MLX).
*   **Vultr/Windows (Mechanica):** Runs the heavy SOTA context/training or acts as overflow for larger local models (14B+).

## 5. Success Metric
**"The One-Prompt Feature"**
*   *Target:* User says "Add a blue chu-chu enemy." -> System produces compiled, working ROM with a blue chu-chu.
