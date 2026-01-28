---
name: semantic-query
description: High-level state query tool for Oracle of Secrets. Maps natural language questions ("is_safe", "has bow") to complex RAM inspections.
---

# Semantic Query

## Scope
- Abstract raw RAM addresses into boolean/value predicates.
- Provide a unified interface for agents to check game state.

## Core Capabilities

### 1. Context Queries
- `is_overworld`: Are we in the overworld?
- `is_dungeon`: Are we inside a dungeon?
- `in_cutscene`: Is a cutscene active?
- `can_control`: Does the player have control?

### 2. State Queries
- `is_safe`: Is Link alive?
- `has <item>`: Do we possess a specific item? (e.g., `has bow`, `has somaria`).
- `rupees`: Return current rupee count.

## Workflow

1.  **Agent Logic**: "I need to warp, but only if I'm safe and outdoors."
2.  **Check**: `semantic-query is_safe` -> `True`.
3.  **Check**: `semantic-query is_overworld` -> `True`.
4.  **Action**: Proceed with warp.

## Dependencies
- **Tool**: `~/src/hobby/yaze/scripts/ai/state_query.py`.
- **Mesen2**: Running with socket server.

## Example Prompts
- "Check if Link is currently in a cutscene."
- "Do we have the Cane of Somaria?"
- "Is the player currently in control of Link?"
