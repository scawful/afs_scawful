#!/usr/bin/env python3
"""
Normalize JSONL datasets for ASM training.

Fixes:
- Instruction cleanup (strip file markers / address noise).
- Missing domain/source defaults.
- Merges legacy `metadata` into `_metadata`.
- Generates instructions from labels when missing/low-signal.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Tuple


FILE_MARKER_PATTERNS = [
    r";\s*\*?\$[0-9A-Fa-f]+-\$[0-9A-Fa-f]+\s*(LOCAL|LONG|JUMP\s*LOCATION|ALTERNATE\s*ENTRY\s*POINT|DATA|MAIN\s*ENTRY\s*POINT)?\.?",
    r"\*\$[0-9A-Fa-f]+-\$[0-9A-Fa-f]+\s*(LOCAL|LONG|JUMP\s*LOCATION|ALTERNATE\s*ENTRY\s*POINT|DATA|MAIN\s*ENTRY\s*POINT)?\.?",
    r"={4,}",
    r"-{4,}",
    r";\s*TODO\s*$",
    r";\s*\$[0-9A-Fa-f]+\s*$",
]

_file_marker_regexes = [re.compile(p, re.IGNORECASE) for p in FILE_MARKER_PATTERNS]
_org_regex = re.compile(r"\borg\s+\$[0-9A-Fa-f]+\b", re.IGNORECASE)
_address_regex = re.compile(r"\$[0-9A-Fa-f]{4,6}\b")

_label_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)::?\s*$")
_label_colon_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*:\s*(?:\{\\s*)?$")

VALID_MNEMONICS = {
    "LDA", "LDX", "LDY", "STA", "STX", "STY", "STZ",
    "TAX", "TAY", "TXA", "TYA", "TXS", "TSX", "TCD", "TDC", "TCS", "TSC", "TXY", "TYX",
    "PHA", "PHP", "PHX", "PHY", "PHB", "PHD", "PHK",
    "PLA", "PLP", "PLX", "PLY", "PLB", "PLD",
    "PEA", "PEI", "PER",
    "ADC", "SBC", "INC", "INX", "INY", "DEC", "DEX", "DEY",
    "CMP", "CPX", "CPY",
    "AND", "ORA", "EOR", "BIT",
    "ASL", "LSR", "ROL", "ROR",
    "BCC", "BCS", "BEQ", "BMI", "BNE", "BPL", "BVC", "BVS", "BRA", "BRL",
    "JMP", "JML", "JSR", "JSL", "RTS", "RTL", "RTI",
    "CLC", "CLD", "CLI", "CLV", "SEC", "SED", "SEI",
    "REP", "SEP",
    "NOP", "WDM", "STP", "WAI", "XBA", "XCE",
    "MVP", "MVN",
    "BRK", "COP",
    "TRB", "TSB",
}

DATA_DIRECTIVES = {
    "db", "dw", "dl", "dd", "incbin", "org", "base", "pad", "warnpc", "assert", "print", "printt",
    "incsrc", "include", "pushpc", "pullpc",
}


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"_parse_error": True}


def clean_instruction(text: str) -> Tuple[str, bool]:
    original = text
    cleaned = text
    for pattern in _file_marker_regexes:
        cleaned = pattern.sub("", cleaned)
    cleaned = _org_regex.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[\s,;:]+$", "", cleaned).strip()
    return cleaned, cleaned != original


def strip_address_noise(text: str) -> str:
    cleaned = _org_regex.sub("", text)
    cleaned = _address_regex.sub("", cleaned)
    cleaned = cleaned.replace("org", "")
    cleaned = re.sub(r"[\s,;:]+", " ", cleaned).strip()
    return cleaned


def extract_label(output: str) -> str | None:
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#_"):
            continue
        match = _label_re.match(line) or _label_colon_re.match(line)
        if match:
            return match.group(1)
    return None


def classify_output_kind(output: str) -> str:
    found_data = False
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("#_"):
            line = line.split(":", 1)[-1].strip()
        if ":" in line:
            label_part, rest = line.split(":", 1)
            if label_part and label_part.replace("_", "").isalnum():
                line = rest.strip()
        tokens = line.split()
        if not tokens:
            continue
        token = tokens[0].upper()
        if token in VALID_MNEMONICS:
            return "code"
        if token.lower() in DATA_DIRECTIVES:
            found_data = True
    return "data" if found_data else "unknown"


def normalize_instruction(
    instruction: str,
    output: str,
    stats: Counter,
) -> tuple[str, dict]:
    flags: dict[str, object] = {}
    cleaned, was_cleaned = clean_instruction(instruction)
    if was_cleaned:
        stats["instruction_cleaned"] += 1
        flags["instruction_cleaned"] = True

    lower = cleaned.lower()
    prefix = "write a 65816 routine that"
    if lower.startswith(prefix):
        desc = cleaned[len(prefix):].strip()
        desc_check = strip_address_noise(desc).strip(" .;:-")
        if not re.search(r"[A-Za-z]", desc_check):
            cleaned = ""
        else:
            desc = desc.strip(" .;:-")
            cleaned = f"Write a 65816 routine that {desc}."

    if cleaned:
        return cleaned, flags

    label = extract_label(output)
    if not label:
        return "", flags

    kind = classify_output_kind(output)
    stats[f"instruction_generated_{kind}"] += 1
    flags["instruction_generated"] = True
    flags["instruction_generated_kind"] = kind
    if kind == "data":
        return f"Define the ASM data table {label}.", flags
    return f"Write a 65816 routine named {label}.", flags


def infer_domain(record: dict) -> str:
    instruction = str(record.get("instruction", "")).lower()
    if instruction.startswith("summarize") and "asm change" in instruction:
        return "asm-git"
    if instruction.startswith("summarize"):
        return "asm-comment"
    if instruction.startswith("write a 65816 routine"):
        return "asm-generate"
    return "asm"


def normalize_record(
    record: dict,
    default_domain: str,
    default_source: str,
    stats: Counter,
    *,
    drop_todo: bool,
) -> dict | None:
    if record.get("_parse_error"):
        stats["parse_error"] += 1
        return None

    output = (record.get("output") or "").strip()
    if not output:
        stats["drop_missing_output"] += 1
        return None

    instruction = (record.get("instruction") or "").strip()
    if not instruction:
        stats["instruction_missing"] += 1

    metadata = record.get("_metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    legacy_meta = record.pop("metadata", None)
    if isinstance(legacy_meta, dict) and legacy_meta:
        metadata.update(legacy_meta)
        stats["metadata_merged"] += 1

    normalized_instruction, instr_flags = normalize_instruction(instruction, output, stats)
    if not normalized_instruction:
        stats["drop_empty_instruction"] += 1
        return None
    if drop_todo and "todo" in normalized_instruction.lower():
        stats["drop_todo_instruction"] += 1
        return None

    record["instruction"] = normalized_instruction
    record["output"] = output

    domain = (record.get("domain") or "").strip()
    if not domain:
        domain = default_domain or infer_domain(record)
        record["domain"] = domain
        stats["domain_defaulted"] += 1

    source = (record.get("source") or "").strip()
    if not source:
        source = default_source or "unknown"
        record["source"] = source
        stats["source_defaulted"] += 1

    metadata["normalized"] = True
    metadata.update(instr_flags)
    record["_metadata"] = metadata
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize ASM JSONL datasets.")
    parser.add_argument("--input", type=Path, required=True, help="Input JSONL dataset.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path.")
    parser.add_argument("--rejected", type=Path, help="Optional rejected JSONL path.")
    parser.add_argument("--report", type=Path, help="Optional JSON report path.")
    parser.add_argument("--default-domain", type=str, default="asm", help="Default domain if missing.")
    parser.add_argument("--default-source", type=str, default="", help="Default source if missing.")
    parser.add_argument("--drop-todo", action="store_true", help="Drop instructions containing TODO.")
    args = parser.parse_args()

    stats: Counter = Counter()
    kept = 0
    rejected_records = []

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.rejected:
        args.rejected.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as out_handle:
        for record in iter_jsonl(args.input):
            stats["total"] += 1
            normalized = normalize_record(
                record,
                args.default_domain,
                args.default_source,
                stats,
                drop_todo=args.drop_todo,
            )
            if normalized is None:
                if args.rejected:
                    rejected_records.append(record)
                continue
            out_handle.write(json.dumps(normalized, ensure_ascii=True) + "\n")
            kept += 1

    stats["kept"] = kept
    stats["dropped"] = stats["total"] - kept

    if args.rejected:
        with args.rejected.open("w", encoding="utf-8") as rej_handle:
            for record in rejected_records:
                rej_handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    if args.report:
        report = {
            "input": str(args.input),
            "output": str(args.output),
            "rejected": str(args.rejected) if args.rejected else None,
            "stats": dict(stats),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"normalized: {kept} / {stats['total']} -> {args.output}")
    if args.rejected:
        print(f"rejected: {stats['dropped']} -> {args.rejected}")
    if args.report:
        print(f"report: {args.report}")


if __name__ == "__main__":
    main()
