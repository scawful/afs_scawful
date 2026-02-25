---
name: alttp-disasm-labels
description: Read and interpret the Link to the Past (ALTTP) disassembly with label/symbol context. Use when mapping ROM/CPU addresses to labels, searching usdasm/jpdasm sources, or cross-referencing routines with Hyrule Historian, z3dk label indexes, or z3ed output.
---

# ALTTP Disassembly Labels

## Overview
Resolve addresses and symbols across ALTTP disassembly sources (usdasm/jpdasm) so runtime traces and bug reports map to the correct routines and data.

## Quick start
1. Query Hyrule Historian first for symbols or addresses:
   - `mcp__hyrule-historian__lookup("Link_Main")`
   - `mcp__hyrule-historian__lookup("$07A123")`
2. Search raw disassembly when you need file context:
   - `rg -n "Link_Main" ~/src/hobby/alttp-gigaleak/DISASM/usdasm`
3. If labels look stale or missing, refresh the z3dk label indexes (see references) or run:
   - `python3 ~/src/hobby/oracle-of-secrets/scripts/mesen2_client.py labels-refresh`

## Decision guide
- **Symbol -> code context:** Hyrule Historian lookup, then `rg` in usdasm.
- **Address -> symbol:** Hyrule Historian lookup; fallback to the label index CSV.
- **Behavior -> candidate routines:** Hyrule Historian search, then scan the relevant bank file.

## Working rules
- Prefer US `usdasm` for address parity with tooling; use JP `jpdasm` when US exports are missing.
- Keep label indexes and disassembly roots aligned before drawing conclusions.

## References
- `references/paths-and-sources.md`
- `references/label-indexes.md`
- `references/lookup-patterns.md`
