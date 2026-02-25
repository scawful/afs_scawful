#!/usr/bin/env python3
"""Build z3dk_training_v1.jsonl from z3dk references and templates."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def _read_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _record(
    instruction: str,
    output: str,
    domain: str,
    source: str,
    metadata: dict | None = None,
) -> dict:
    payload = {
        "instruction": instruction.strip(),
        "input": "",
        "output": output.rstrip(),
        "domain": domain,
        "source": source,
    }
    if metadata:
        payload["_metadata"] = metadata
    return payload


def build_opcode_qa(opcodes: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for op in opcodes:
        mnemonic = op.get("mnemonic", "").strip()
        if not mnemonic:
            continue
        full_name = op.get("full_name", "").strip()
        flags = op.get("flags_affected", op.get("flags", "")).strip()
        description = op.get("description", "").strip()
        example_modes = op.get("addressing_modes", []) or []
        mode_text = ", ".join(m.get("opcode_hex", "") for m in example_modes[:3] if isinstance(m, dict))
        answer = (
            f"{mnemonic} ({full_name})\n"
            f"Flags affected: {flags or 'unknown'}\n\n"
            f"{description}\n\n"
            f"Opcode examples: {mode_text or 'not documented'}"
        )
        rows.append(
            _record(
                instruction=f"Explain 65816 opcode {mnemonic}: purpose, flags, and typical usage.",
                output=answer,
                domain="qa",
                source="z3dk_reference:65816_opcodes.json",
                metadata={"generator": "build_opcode_qa", "mnemonic": mnemonic},
            )
        )
    return rows


def build_register_qa(registers: list[dict], max_samples: int = 32) -> list[dict]:
    """Build a bounded, category-diverse register QA set."""
    rows: list[dict] = []
    by_category: dict[str, list[dict]] = {}

    for reg in registers:
        category = str(reg.get("category", "unknown")).strip().lower() or "unknown"
        by_category.setdefault(category, []).append(reg)

    categories = sorted(by_category.keys())
    category_indexes = {category: 0 for category in categories}

    while len(rows) < max_samples:
        made_progress = False

        for category in categories:
            bucket = by_category[category]
            index = category_indexes[category]
            if index >= len(bucket):
                continue

            reg = bucket[index]
            category_indexes[category] += 1
            made_progress = True

            name = str(reg.get("name", "")).strip()
            addr = str(reg.get("address", "")).strip()
            if not name or not addr:
                continue

            answer = (
                f"Register: {name} ({addr})\n"
                f"Category: {reg.get('category', 'unknown')}\n"
                f"Readable: {reg.get('readable', True)}\n"
                f"Writable: {reg.get('writable', True)}\n\n"
                f"{str(reg.get('description', '')).strip()}"
            )
            rows.append(
                _record(
                    instruction=f"What does SNES register {name} at {addr} do?",
                    output=answer,
                    domain="qa",
                    source="z3dk_reference:snes_registers.json",
                    metadata={"generator": "build_register_qa", "register": name},
                )
            )

            if len(rows) >= max_samples:
                break

        if not made_progress:
            break

    return rows


def build_register_qa_full(registers: list[dict]) -> list[dict]:
    """Build register QA for all entries (diagnostic use)."""
    rows: list[dict] = []
    for reg in registers:
        name = str(reg.get("name", "")).strip()
        addr = str(reg.get("address", "")).strip()
        if not name or not addr:
            continue
        answer = (
            f"Register: {name} ({addr})\n"
            f"Category: {reg.get('category', 'unknown')}\n"
            f"Readable: {reg.get('readable', True)}\n"
            f"Writable: {reg.get('writable', True)}\n\n"
            f"{str(reg.get('description', '')).strip()}"
        )
        rows.append(
            _record(
                instruction=f"What does SNES register {name} at {addr} do?",
                output=answer,
                domain="qa",
                source="z3dk_reference:snes_registers.json",
                metadata={"generator": "build_register_qa", "register": name},
            )
        )
    return rows


def build_hook_writing(templates_dir: Path, count: int = 50) -> list[dict]:
    hook_tmpl = _load_template(templates_dir / "hook.asm.tmpl")
    routine_tmpl = _load_template(templates_dir / "routine.asm.tmpl")
    rows: list[dict] = []

    for i in range(count):
        hook_name = f"Hook_Custom_{i:02d}"
        address = f"{0x088000 + (i * 0x10):06X}"
        entry_8bit = (i % 2) == 0
        entry_state_comment = "A/X/Y in 8-bit mode" if entry_8bit else "A/X/Y in 16-bit mode"
        entry_width_setup = "  SEP #$30" if entry_8bit else "  REP #$30"
        exit_width_restore = "  SEP #$30\n" if entry_8bit else "  REP #$30\n"
        hook_body = hook_tmpl.format(
            name=hook_name,
            address=address,
            entry_state_comment=entry_state_comment,
            entry_width_setup=entry_width_setup,
            exit_width_restore=exit_width_restore,
        )
        routine_body = routine_tmpl.format(
            name=f"{hook_name}_Logic",
            routine_type="subroutine",
            return_instruction="RTL",
            bank_setup="  PHB : PHK : PLB\n",
            preserve_push="  PHX : PHY\n",
            width_comment=entry_state_comment,
            preserve_pull="  PLY : PLX\n",
            bank_restore="  PLB\n",
        )
        rows.append(
            _record(
                instruction=f"Write an Asar hook named {hook_name} targeting ${address} with safe register preservation.",
                output=f"{hook_body}\n\n{routine_body}",
                domain="asm",
                source="z3dk_templates:hook+routine",
                metadata={"generator": "build_hook_writing", "hook_name": hook_name},
            )
        )
    return rows


def _sprite_state_table(name: str, states: int = 3) -> tuple[str, str]:
    table_rows = [f"  dw {name}_State{idx}" for idx in range(states)]
    routines = []
    for idx in range(states):
        routines.append(
            f"{name}_State{idx}:\n{{\n"
            f"  ; TODO: state {idx} logic\n"
            f"  RTS\n"
            f"}}\n"
        )
    return "\n".join(table_rows), "\n".join(routines)


def build_scaffold_completion(templates_dir: Path, count: int = 30) -> list[dict]:
    sprite_tmpl = _load_template(templates_dir / "sprite.asm.tmpl")
    npc_tmpl = _load_template(templates_dir / "npc.asm.tmpl")
    rows: list[dict] = []

    for i in range(count):
        if i % 2 == 0:
            name = f"OracleSprite{i:02d}"
            state_table, state_routines = _sprite_state_table(name, states=3)
            output = sprite_tmpl.format(
                name=name,
                bank=f"{0x2C + (i % 4):02X}",
                namespace="oos",
                state_table=state_table,
                state_routines=state_routines,
            )
            instruction = (
                f"Complete a sprite scaffold for {name} with 3 states "
                f"(init, active, cooldown) using z3dk style."
            )
            metadata = {"generator": "build_scaffold_completion", "kind": "sprite", "name": name}
        else:
            name = f"OracleNpc{i:02d}"
            output = npc_tmpl.format(
                name=name,
                namespace="oos",
                reaction_table="; TODO: add reaction table entries",
                follower_check="; TODO: add follower state checks",
            )
            instruction = f"Complete an NPC scaffold for {name} with dialogue-state handling."
            metadata = {"generator": "build_scaffold_completion", "kind": "npc", "name": name}

        rows.append(
            _record(
                instruction=instruction,
                output=output,
                domain="asm",
                source="z3dk_templates:sprite+npc",
                metadata=metadata,
            )
        )

    return rows


def build_static_analysis(count: int = 20) -> list[dict]:
    bug_patterns = [
        (
            "M/X width mismatch",
            "SEP #$20\nLDA #$1234\nSTA $7E1000\nRTS",
            "A is forced to 8-bit before loading a 16-bit immediate. Use REP #$20 when 16-bit A is required.",
        ),
        (
            "Stack imbalance",
            "PHA\nJSR Work\nRTS",
            "PHA is not paired with PLA. Stack depth is corrupted at RTS.",
        ),
        (
            "JSR/JSL mismatch",
            "JSL LongRoutine\n...\nRTS",
            "Long calls require RTL in the callee/return path, not RTS.",
        ),
        (
            "VRAM timing hazard",
            "STA $2118\nSTA $2119",
            "VRAM writes should occur during blanking periods or forced blank to avoid corruption.",
        ),
        (
            "Branch range risk",
            "BNE far_label",
            "8-bit branch range may overflow if target is farther than +/-127 bytes.",
        ),
    ]

    rows: list[dict] = []
    for i in range(count):
        pattern, snippet, expected = bug_patterns[i % len(bug_patterns)]
        rows.append(
            _record(
                instruction=f"Identify the primary bug in this 65816 snippet ({pattern}) and explain the fix.",
                output=f"Snippet:\n{snippet}\n\nIssue:\n{expected}",
                domain="qa",
                source="z3dk_static_analyzer:patterns",
                metadata={"generator": "build_static_analysis", "pattern": pattern},
            )
        )
    return rows


def build_quirks_qa(quirks: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for quirk in quirks:
        title = str(quirk.get("title", "")).strip()
        if not title:
            continue
        rows.append(
            _record(
                instruction=f"Explain SNES quirk: {title}. Provide a concise workaround.",
                output=(
                    f"{quirk.get('description', '')}\n\n"
                    f"Example:\n{quirk.get('example_code', '')}\n\n"
                    f"Workaround:\n{quirk.get('workaround', '')}"
                ),
                domain="qa",
                source="z3dk_reference:snes_quirks.json",
                metadata={"generator": "build_quirks_qa", "quirk_id": quirk.get("id", "")},
            )
        )
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build z3dk_training_v1 dataset.")
    parser.add_argument(
        "--z3dk-root",
        type=Path,
        default=Path.home() / "src" / "hobby" / "z3dk",
        help="Path to z3dk repository root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / "src" / "training" / "datasets" / "z3dk" / "z3dk_training_v1.jsonl",
        help="Output JSONL dataset path.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed.")
    parser.add_argument(
        "--register-max",
        type=int,
        default=32,
        help="Maximum register QA samples (default: 32).",
    )
    parser.add_argument(
        "--all-registers",
        action="store_true",
        help="Use all register entries instead of capped sampling.",
    )
    args = parser.parse_args()

    z3dk_root = args.z3dk_root.expanduser().resolve()
    refs = z3dk_root / "docs" / "reference"
    templates_dir = z3dk_root / "templates"

    opcodes = _read_json(refs / "65816_opcodes.json")
    registers = _read_json(refs / "snes_registers.json")
    quirks = _read_json(refs / "snes_quirks.json")

    rows: list[dict] = []
    rows.extend(build_opcode_qa(opcodes))
    register_rows = (
        build_register_qa_full(registers)
        if args.all_registers
        else build_register_qa(registers, max_samples=args.register_max)
    )
    rows.extend(register_rows)
    rows.extend(build_hook_writing(templates_dir, count=50))
    rows.extend(build_scaffold_completion(templates_dir, count=30))
    rows.extend(build_static_analysis(count=20))
    rows.extend(build_quirks_qa(quirks))

    rng = random.Random(args.seed)
    rng.shuffle(rows)

    output_path = args.output.expanduser().resolve()
    _write_jsonl(output_path, rows)

    print(f"z3dk_root: {z3dk_root}")
    print(f"output: {output_path}")
    print(f"samples: {len(rows)}")
    print("breakdown:")
    print(f"  build_opcode_qa: {len(opcodes)}")
    print(f"  build_register_qa: {len(register_rows)}")
    print("  build_hook_writing: 50")
    print("  build_scaffold_completion: 30")
    print("  build_static_analysis: 20")
    print(f"  build_quirks_qa: {len(quirks)}")


if __name__ == "__main__":
    main()
