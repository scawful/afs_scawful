# Yaze AI Integration — Strategic Spec (2026)

**Status:** Proposed
**Extension of:** `yaze_oracle_project_experience.md`
**Goal:** Integrate AFS H-MoE experts directly into the Yaze Dungeon Editor UI.

## 1. The "AiAssistantPanel" (ImGui)

A new sidebar panel in Yaze that provides context-aware AI operations.

### Features

#### A. "Ask Veran" (Analysis)
- **Context:** Automatically bundles the current Room JSON (palette, blockset, tags).
- **Function:** Analyzes the room logic and suggests improvements or explains the intended behavior of vanilla tags.
- **Workflow:** `Yaze` -> `Export Current Room JSON` -> `model_router.py veran` -> `Display Result`.

#### B. "Ask Din" (Optimization)
- **Context:** User highlights a block of code in the "ASM Editor" or "Mutations" view.
- **Function:** Analyzes cycle counts using the `65816_instruction_set.json` knowledge base and suggests a faster/smaller alternative.
- **Workflow:** `Yaze` -> `Extract Selection` -> `model_router.py din` -> `Diff View`.

#### C. "Ask Farore" (Debugging)
- **Context:** Uses the Mesen2 Socket to get current PC and registers.
- **Function:** Explains why the game is blacking out or crashing based on current state + recently applied patches.
- **Workflow:** `Yaze` -> `Mesen2 Bridge (State)` -> `model_router.py farore` -> `Troubleshooting Guide`.

## 2. Technical Architecture

```
┌─────────────────┐      ┌────────────────────────┐      ┌─────────────────┐
│   Yaze (C++)    │      │   AFS Router (Python)  │      │ Local Inference │
│                 │ shell│                        │ HTTP │                 │
│ AiAssistantPanel├─────►│    model_router.py     ├─────►│    LMStudio     │
│                 │      │                        │      │ (Backbone+LoRA) │
└─────────────────┘      └───────────┬────────────┘      └─────────────────┘
                                     │
                                     ▼
                         ┌────────────────────────┐
                         │ AFS Knowledge / Data   │
                         │ (dungeons.json, etc.)  │
                         └────────────────────────┘
```

## 3. Implementation Plan

### Phase 1: AI Sidebar
- Create `src/app/gui/panels/ai_assistant_panel.h/cc`.
- Implement a simple "Chat" interface that calls `afs/model_router.py` via `std::system` or `popen`.

### Phase 2: Context Injection
- Update `DungeonEditorV2` to pass the currently active room data as a temporary JSON file to the router.
- Teach `model_router.py` to parse this specific "Yaze Context" format.

### Phase 3: Inline Diffing
- Implement a "Apply Suggestion" button that uses Yaze's new Undo/Redo system (`DungeonUndoActions`) to apply AI-generated collision or tile changes.

## 4. Dependencies
- `afs/model_router.py` (Established Feb 2026)
- `afs/knowledge/65816_instruction_set.json`
- `ImGui` (Integrated in Yaze)
