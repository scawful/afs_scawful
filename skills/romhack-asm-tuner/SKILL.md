---
name: romhack-asm-tuner
description: SNES Assembly (65816) patch manager. Curates ASM snippets, verifies patches with Asar/Z3DK, and manages the code library for Oracle of Secrets.
---

# ROMHack ASM Tuner

## Scope
- Write, verify, and apply 65816 ASM patches.
- Manage a library of ASM snippets (routines, hooks, data tables).
- Run `asar` (or `z3asm`) to verify syntax and bank limits.
- Curate the `oracle-of-secrets` codebase conventions.

## Core Capabilities

### 1. ASM Verification
Check if a snippet is valid 65816 code.
- Uses `z3asm` (part of Z3DK) to dry-run assembly.
- Checks for bank overflow, label collisions, and addressing mode errors.

### 2. Patch Management
- `apply <file.asm>`: Patches the ROM (using `build_rom.sh` or `z3asm`).
- `revert`: Rolls back the last patch (via git or backup).

### 3. Codebase Curation
Enforce style guides:
- **Namespaces:** `Oracle.{Scope}`.
- **Labels:** `.` for local, `..` for nested.
- **Defines:** Use `!Define` for constants.
- **Long Addressing:** `$7E` access must use `STA.l` ($8F).

## Workflow

1.  **Draft:** "Write a routine to heal Link."
2.  **Verify:** `asm-tuner verify heal.asm`.
3.  **Refine:** "Fix the bank wrapper (missing PHB/PLB)."
4.  **Commit:** Save to `src/hobby/oracle-of-secrets/Core/Link/Heal.asm`.

## Dependencies
- **Z3DK**: `z3asm` binary (`~/src/hobby/z3dk/build/src/z3asm/bin/z3asm`).
- **Repo**: `~/src/hobby/oracle-of-secrets`.
- **Tool**: `~/src/hobby/yaze/scripts/ai/asm_tuner.py`.

## Example Prompts
- "Verify the syntax of `src/hobby/oracle-of-secrets/Core/Link/Heal.asm`."
- "Check this ASM snippet for style violations."
- "Does this routine use long addressing for WRAM?"
- "Draft a routine to increase Rupees by 50."

## Troubleshooting
- **z3asm Not Found**: Check `~/src/hobby/z3dk/build/` for the binary. Rebuild Z3DK if missing.
- **Syntax Errors**: Ensure all labels and defines are declared or included. The verifier runs in isolation, so missing includes will cause errors.
- **Style False Positives**: The regex checker is strict. Use `.l` suffix explicitly for all $7E/$7F accesses.

