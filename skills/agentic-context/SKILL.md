---
name: agentic-context
description: Use AFS for project context, scratchpad notes, conditional file writes, and cross-agent handoffs. Trigger for .context operations, AFS CLI usage, context roots, mounts, or shared-file conflicts.
---

# Agentic Context

## Startup

Run `afs session bootstrap --short --path <workspace> --json` once, unless the
native SessionStart hook already supplied the AFS short bootstrap. The brief
contains scoped notes and skill roots. It does not index, match skills, or create
bootstrap artifacts. Follow a note's source path when its excerpt is truncated.

The local stable CLI is `~/src/runtime/afs/scripts/afs`. Its Python environment
is `~/src/runtime/afs/.venv`. `~/src/lab/afs` is the development checkout.

## Retrieve only what the task needs

- Use `afs context query <text> --path <workspace> --json` for existing context.
- Use `afs status --start-dir <workspace> --json` to diagnose health. Inspect
  `afs context repair --path <workspace> --dry-run --json` before a repair.
- Use `afs context discover --path <workspace> --json` when the root is unknown.
  Initialize a missing context only when the task needs one; do not run
  `context ensure-all` during routine startup.
- Native hosts load their own skills. Keep `AFS_NATIVE_SKILLS=1` and
  `AFS_PROMPT_SCAFFOLDING=minimal`. Request full packs only for explicit exports,
  handoffs, or a concrete retrieval need.

## Write scoped state

Use CLI `afs fs` or MCP `context.read`, `context.write`, and `context.list`.
Write working notes and handoffs to `scratchpad`; keep `memory` and `knowledge`
read-only unless the user requests a durable update.

For shared files, read with `afs fs read scratchpad <path> --json`, then write
with `afs fs write scratchpad <path> --input <file> --if-match <sha256> --json`.
Use `--if-match missing` for creation. Reconcile a mismatch before retrying.

`messages` aliases the legacy `hivemind` mount. Use it for cross-agent handoffs
when needed. Extension events go through `afs events emit`; event records never
grant approval. External sends require approval bound to the exact final content
and destination, including any split messages or attachments.

## References

Read `references/sources.md` for the current contracts and detailed CLI surfaces.
