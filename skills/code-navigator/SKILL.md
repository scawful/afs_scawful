---
name: code-navigator
description: Static analysis tool for ASM codebases. Builds call graphs, finds callers/callees, and identifies memory write locations.
---

# Code Navigator

## Scope
- Static analysis of 65816 ASM.
- Call hierarchy resolution (`JSL`, `JSR`, `JML`).
- RAM usage tracking (`STA`, `STX`, `STY`).

## Core Capabilities

### 1. Find Callers
Who calls a specific routine?
- `callers Link_Hurt` -> Returns list of routines and file locations.

### 2. Find Writes
Who writes to a specific RAM address?
- `writes 7E0010` -> Returns routines that modify GameMode.

### 3. Graph Export
Generate a JSON call graph for visualization or LLM context.
- `graph --out codebase.json`

## Dependencies
- **Tool**: `~/src/hobby/yaze/scripts/ai/code_graph.py`.
- **Repo**: `~/src/hobby/oracle-of-secrets` (or any ASM folder).

## Example Prompts
- "Who calls `Link_ResetProperties`?"
- "Which routines write to the Ocarina flag at `$7E0300`?"
- "Generate a call graph of the Music subsystem."

## Limitations
- **Regex-based**: Does not evaluate macros or conditional assembly (`if`).
- **Indirect Calls**: Cannot resolve `JSR ($0000,X)`.
