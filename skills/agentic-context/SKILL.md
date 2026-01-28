---
name: agentic-context
description: Use the Agentic File System (AFS) context model for discovery, mounts, scratchpad memory, and file-based tool workflows. Use when a task involves .context operations, AFS CLI usage, or cross-agent context coordination.
---

# Agentic Context

## Scope
- Operate AFS context safely: discover context roots, read/write scratchpad, and mount knowledge.

## Workflow
1. Locate the active context root.
   - Use `~/src/lab/afs/scripts/afs context discover --path ~/src --json`.
   - Prefer project `.context` when working inside a repo.
2. Ensure context scaffolding exists.
   - Use `~/src/lab/afs/scripts/afs context ensure-all --path ~/src`.
3. Read and write via AFS, not ad-hoc paths.
   - Read: `afs fs read scratchpad state.md --path ~/src`.
   - Write: `afs fs write scratchpad notes.md --path ~/src --content "..."`.
   - List: `afs fs list knowledge --path ~/src --glob "*.md"`.
4. Keep memory and knowledge read-only.
   - Write only to `scratchpad` unless explicitly asked.
5. Use workspace navigation tools.
   - Use `ws list`, `ws find`, and `ws status` for project discovery.
6. Use the AFS CLI wrapper for non-interactive agents.
   - Use `AFS_CLI=~/src/lab/afs/scripts/afs` and `AFS_VENV=~/src/lab/afs/.venv` when needed.

## References
- Read `references/sources.md` for AFS context docs and contracts.