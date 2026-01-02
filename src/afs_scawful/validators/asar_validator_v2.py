"""Enhanced ASAR Validator v2 with structured error parsing and semantic analysis.

Extends the basic ASAR validator with:
- Structured error parsing (file, line, column, category)
- Symbol extraction via --symbols=wla
- Semantic scoring based on code quality heuristics
- Multi-ROM type support (lorom/hirom/exlorom)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from ..training import TrainingSample
from .base import ValidationResult, Validator

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Categories of ASAR assembly errors."""
    SYNTAX = "syntax"
    ADDRESSING = "addressing"
    LABEL = "label"
    MACRO = "macro"
    DIRECTIVE = "directive"
    INSTRUCTION = "instruction"
    OTHER = "other"


@dataclass
class AsarError:
    """Structured ASAR error information."""
    file: str
    line: int
    column: int | None
    message: str
    category: ErrorCategory
    raw_line: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "category": self.category.value,
            "raw_line": self.raw_line,
        }


@dataclass
class AsarSymbol:
    """Symbol extracted from ASAR assembly."""
    name: str
    address: int
    bank: int
    symbol_type: Literal["label", "constant", "define"] = "label"
    file: str = ""
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "bank": self.bank,
            "type": self.symbol_type,
            "file": self.file,
            "line": self.line,
        }


@dataclass
class SemanticAnalysis:
    """Semantic analysis of assembly code quality."""
    addressing_modes: list[str] = field(default_factory=list)
    snes_registers: list[str] = field(default_factory=list)
    has_proper_return: bool = False
    has_orphan_labels: bool = False
    instruction_count: int = 0
    label_count: int = 0
    comment_ratio: float = 0.0
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "addressing_modes": self.addressing_modes,
            "snes_registers": self.snes_registers,
            "has_proper_return": self.has_proper_return,
            "has_orphan_labels": self.has_orphan_labels,
            "instruction_count": self.instruction_count,
            "label_count": self.label_count,
            "comment_ratio": self.comment_ratio,
            "score": self.score,
        }


# SNES PPU/APU/DMA registers for semantic analysis
SNES_REGISTERS = {
    "$2100", "$2101", "$2102", "$2103", "$2104", "$2105", "$2106", "$2107",
    "$2108", "$2109", "$210A", "$210B", "$210C", "$210D", "$210E", "$210F",
    "$2110", "$2111", "$2112", "$2113", "$2114", "$2115", "$2116", "$2117",
    "$2118", "$2119", "$211A", "$211B", "$211C", "$211D", "$211E", "$211F",
    "$2120", "$2121", "$2122", "$2123", "$2124", "$2125", "$2126", "$2127",
    "$2128", "$2129", "$212A", "$212B", "$212C", "$212D", "$212E", "$212F",
    "$2130", "$2131", "$2132", "$2133", "$2134", "$2135", "$2136", "$2137",
    "$2138", "$2139", "$213A", "$213B", "$213C", "$213D", "$213E", "$213F",
    "$2140", "$2141", "$2142", "$2143",  # APU
    "$4200", "$4201", "$4202", "$4203", "$4204", "$4205", "$4206", "$4207",
    "$4208", "$4209", "$420A", "$420B", "$420C", "$420D",  # CPU/DMA
    "$4300", "$4301", "$4302", "$4303", "$4304", "$4305", "$4306", "$4307",  # DMA
}

# 65816 instruction mnemonics
VALID_INSTRUCTIONS = {
    "ADC", "AND", "ASL", "BCC", "BCS", "BEQ", "BIT", "BMI", "BNE", "BPL",
    "BRA", "BRK", "BRL", "BVC", "BVS", "CLC", "CLD", "CLI", "CLV", "CMP",
    "COP", "CPX", "CPY", "DEC", "DEX", "DEY", "EOR", "INC", "INX", "INY",
    "JML", "JMP", "JSL", "JSR", "LDA", "LDX", "LDY", "LSR", "MVN", "MVP",
    "NOP", "ORA", "PEA", "PEI", "PER", "PHA", "PHB", "PHD", "PHK", "PHP",
    "PHX", "PHY", "PLA", "PLB", "PLD", "PLP", "PLX", "PLY", "REP", "ROL",
    "ROR", "RTI", "RTL", "RTS", "SBC", "SEC", "SED", "SEI", "SEP", "STA",
    "STP", "STX", "STY", "STZ", "TAX", "TAY", "TCD", "TCS", "TDC", "TRB",
    "TSB", "TSC", "TSX", "TXA", "TXS", "TXY", "TYA", "TYX", "WAI", "WDM",
    "XBA", "XCE",
}


def _resolve_env_path(env_var: str) -> Path | None:
    """Resolve path from environment variable."""
    value = os.environ.get(env_var)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _default_asar_path() -> Path:
    """Find ASAR binary location."""
    env = _resolve_env_path("AFS_ASAR_PATH")
    if env:
        return env
    found = shutil.which("asar")
    if found:
        return Path(found)
    # Check common locations
    third_party = Path.home() / "src" / "third_party" / "asar-repo" / "build" / "asar" / "bin" / "asar"
    if third_party.exists():
        return third_party
    return Path("asar")


def _default_rom_path() -> Path:
    """Find dummy ROM for assembly testing."""
    env = _resolve_env_path("AFS_ASAR_ROM")
    if env:
        return env
    candidate = Path.home() / "src" / "training" / "roms" / "dummy.sfc"
    if candidate.exists():
        return candidate
    return Path.home() / ".context" / "training" / "dummy.sfc"


def _categorize_error(message: str) -> ErrorCategory:
    """Categorize an ASAR error message."""
    msg_lower = message.lower()

    if any(x in msg_lower for x in ["label", "symbol", "undefined", "redefined"]):
        return ErrorCategory.LABEL
    if any(x in msg_lower for x in ["macro", "endmacro"]):
        return ErrorCategory.MACRO
    if any(x in msg_lower for x in ["org", "base", "include", "incsrc", "incbin", "lorom", "hirom"]):
        return ErrorCategory.DIRECTIVE
    if any(x in msg_lower for x in ["addressing", "mode", "operand", "immediate", "direct"]):
        return ErrorCategory.ADDRESSING
    if any(x in msg_lower for x in ["instruction", "opcode", "mnemonic", "unknown command"]):
        return ErrorCategory.INSTRUCTION
    if any(x in msg_lower for x in ["syntax", "parse", "expected", "unexpected"]):
        return ErrorCategory.SYNTAX

    return ErrorCategory.OTHER


def _parse_asar_errors(output: str) -> list[AsarError]:
    """Parse ASAR output into structured errors."""
    errors: list[AsarError] = []

    # ASAR error format: file.asm:line: error: message
    # or: file.asm:line:col: error: message
    error_pattern = re.compile(
        r"^(.+?):(\d+)(?::(\d+))?:\s*error:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE
    )

    for match in error_pattern.finditer(output):
        file_name = match.group(1)
        line_num = int(match.group(2))
        col_num = int(match.group(3)) if match.group(3) else None
        message = match.group(4).strip()

        errors.append(AsarError(
            file=file_name,
            line=line_num,
            column=col_num,
            message=message,
            category=_categorize_error(message),
            raw_line=match.group(0),
        ))

    # Also catch simpler error formats
    simple_pattern = re.compile(r"error:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    for match in simple_pattern.finditer(output):
        msg = match.group(1).strip()
        # Skip if already captured
        if any(msg in e.message for e in errors):
            continue
        errors.append(AsarError(
            file="unknown",
            line=0,
            column=None,
            message=msg,
            category=_categorize_error(msg),
            raw_line=match.group(0),
        ))

    return errors


def _parse_wla_symbols(symbol_content: str) -> list[AsarSymbol]:
    """Parse WLA symbol format output from ASAR.

    Format: bank:addr label
    Example: 00:8000 Reset
    """
    symbols: list[AsarSymbol] = []

    # WLA format: XX:XXXX name
    pattern = re.compile(r"^([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+(\S+)")

    for line in symbol_content.split("\n"):
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("["):
            continue

        match = pattern.match(line)
        if match:
            bank = int(match.group(1), 16)
            addr = int(match.group(2), 16)
            name = match.group(3)

            # Determine symbol type from naming convention
            sym_type: Literal["label", "constant", "define"] = "label"
            if name.startswith("!") or name.startswith("define_"):
                sym_type = "define"
            elif name.isupper() and "_" in name:
                sym_type = "constant"

            symbols.append(AsarSymbol(
                name=name,
                address=addr,
                bank=bank,
                symbol_type=sym_type,
            ))

    return symbols


def _analyze_semantics(code: str) -> SemanticAnalysis:
    """Perform semantic analysis on assembly code."""
    analysis = SemanticAnalysis()

    lines = code.split("\n")
    code_lines = 0
    comment_lines = 0
    labels_defined: set[str] = set()
    labels_used: set[str] = set()

    # Addressing mode patterns
    addr_patterns = {
        "immediate": r"#\$[0-9A-Fa-f]+|#\d+",
        "direct_page": r"\$[0-9A-Fa-f]{2}(?![0-9A-Fa-f])",
        "absolute": r"\$[0-9A-Fa-f]{4}(?![0-9A-Fa-f])",
        "long": r"\$[0-9A-Fa-f]{6}",
        "indexed_x": r",\s*[Xx]",
        "indexed_y": r",\s*[Yy]",
        "indirect": r"\([^)]+\)",
        "stack_relative": r"\$[0-9A-Fa-f]{2},\s*[Ss]",
    }

    modes_found: set[str] = set()
    registers_found: set[str] = set()

    for line in lines:
        # Remove comments for instruction analysis
        code_part = line.split(";")[0].strip()
        comment_part = line[len(code_part):] if ";" in line else ""

        if not code_part:
            if comment_part:
                comment_lines += 1
            continue

        code_lines += 1

        # Check for labels (definition)
        label_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", code_part)
        if label_match:
            labels_defined.add(label_match.group(1))
            analysis.label_count += 1

        # Check for instructions
        tokens = code_part.split()
        if tokens:
            mnemonic = tokens[0].upper().rstrip(":")
            if mnemonic in VALID_INSTRUCTIONS:
                analysis.instruction_count += 1

                # Check for return instructions
                if mnemonic in ("RTS", "RTL", "RTI"):
                    analysis.has_proper_return = True

                # Check addressing modes
                operand = " ".join(tokens[1:]) if len(tokens) > 1 else ""
                for mode_name, pattern in addr_patterns.items():
                    if re.search(pattern, operand):
                        modes_found.add(mode_name)

                # Check for SNES register references
                for reg in SNES_REGISTERS:
                    if reg.lower() in code_part.lower():
                        registers_found.add(reg)

        # Check for label usage (in operands)
        for word in tokens[1:]:
            # Strip addressing prefixes/suffixes
            clean = re.sub(r"[#$(),\[\]]", "", word).strip()
            if clean and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", clean):
                labels_used.add(clean)

    # Calculate orphan labels (defined but never used)
    orphan_labels = labels_defined - labels_used
    analysis.has_orphan_labels = len(orphan_labels) > 0

    analysis.addressing_modes = sorted(modes_found)
    analysis.snes_registers = sorted(registers_found)

    # Calculate comment ratio
    total_lines = code_lines + comment_lines
    analysis.comment_ratio = comment_lines / total_lines if total_lines > 0 else 0.0

    # Calculate semantic score (0.0 - 1.0)
    score = 0.0

    # Points for using various addressing modes (max 0.3)
    score += min(len(modes_found) * 0.05, 0.3)

    # Points for SNES register knowledge (max 0.2)
    score += min(len(registers_found) * 0.04, 0.2)

    # Points for proper return instruction (0.2)
    if analysis.has_proper_return:
        score += 0.2

    # Points for reasonable comment ratio (max 0.1)
    if 0.1 <= analysis.comment_ratio <= 0.5:
        score += 0.1

    # Points for having code at all (0.2)
    if analysis.instruction_count > 0:
        score += 0.2

    # Penalty for orphan labels
    if analysis.has_orphan_labels:
        score = max(0, score - 0.1)

    analysis.score = min(score, 1.0)

    return analysis


class AsarValidatorV2(Validator):
    """Enhanced ASAR validator with structured error parsing and semantic analysis."""

    def __init__(
        self,
        asar_path: Path | None = None,
        rom_path: Path | None = None,
        rom_type: Literal["lorom", "hirom", "exlorom", "exhirom"] = "lorom",
        extract_symbols: bool = True,
        semantic_analysis: bool = True,
    ):
        super().__init__("AsarValidatorV2", "asm")
        self.asar_path = asar_path or _default_asar_path()
        self.rom_path = rom_path or _default_rom_path()
        self.rom_type = rom_type
        self.extract_symbols = extract_symbols
        self.semantic_analysis = semantic_analysis

        if not self.asar_path.exists():
            logger.warning("Asar binary not found at %s", self.asar_path)
        if not self.rom_path.exists():
            logger.warning("Dummy ROM not found at %s", self.rom_path)

    def can_validate(self, sample: TrainingSample) -> bool:
        """Check if this validator can handle the sample."""
        return sample.domain in ("asm", "hack_curated", "65816")

    async def validate(self, sample: TrainingSample) -> ValidationResult:
        """Run enhanced ASAR validation with structured output."""
        if not self.asar_path.exists() or not self.rom_path.exists():
            return ValidationResult(
                valid=True,
                score=0.5,
                warnings=["AsarValidatorV2 skipped: binary or ROM missing"],
            )

        # Extract code from sample
        code = self._extract_code(sample.output)
        if not code:
            return ValidationResult(valid=False, score=0.0, errors=["No code found"])

        # Perform semantic analysis first (doesn't require ASAR)
        semantic: SemanticAnalysis | None = None
        if self.semantic_analysis:
            semantic = _analyze_semantics(code)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_file = tmp_path / "test.asm"
            rom_file = tmp_path / "test.sfc"
            symbols_file = tmp_path / "test.sym"

            # Copy dummy ROM to temp
            shutil.copy(self.rom_path, rom_file)

            # Wrap code in patch structure
            wrapped_code = f"{self.rom_type}\norg $008000\n{code}\n"
            source_file.write_text(wrapped_code)

            # Build ASAR command
            cmd = [str(self.asar_path)]
            if self.extract_symbols:
                cmd.extend(["--symbols=wla", f"--symbols-path={symbols_file}"])
            cmd.extend([str(source_file), str(rom_file)])

            # Run ASAR
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            output = stderr.decode() + stdout.decode()
            success = proc.returncode == 0

            # Parse structured errors
            parsed_errors = _parse_asar_errors(output)

            # Extract symbols if successful
            symbols: list[AsarSymbol] = []
            if success and self.extract_symbols and symbols_file.exists():
                try:
                    symbols = _parse_wla_symbols(symbols_file.read_text())
                except Exception as e:
                    logger.warning("Failed to parse symbols: %s", e)

            # Calculate ROM size change
            assembled_bytes = 0
            if success:
                assembled_bytes = rom_file.stat().st_size - self.rom_path.stat().st_size
                assembled_bytes = max(0, assembled_bytes)

            # Build result
            error_messages = [e.message for e in parsed_errors[:5]]

            # Calculate combined score
            asar_score = 1.0 if success else 0.0
            semantic_score = semantic.score if semantic else 0.5

            # Weighted average: 60% ASAR, 40% semantic
            combined_score = (asar_score * 0.6) + (semantic_score * 0.4)

            details: dict[str, Any] = {
                "assembled": success,
                "assembled_bytes": assembled_bytes,
                "symbol_count": len(symbols),
            }

            if parsed_errors:
                details["errors"] = [e.to_dict() for e in parsed_errors[:10]]
            if symbols:
                details["symbols"] = [s.to_dict() for s in symbols[:20]]
            if semantic:
                details["semantic"] = semantic.to_dict()

            return ValidationResult(
                valid=success,
                score=combined_score,
                errors=error_messages,
                warnings=[],
                details=details,
            )

    def _extract_code(self, text: str) -> str:
        """Extract ASM code from markdown block or raw text."""
        # Try markdown code blocks first
        if "```asm" in text:
            parts = text.split("```asm")
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
        if "```65816" in text:
            parts = text.split("```65816")
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
        if "```" in text:
            parts = text.split("```")
            if len(parts) > 1:
                return parts[1].strip()

        # Assume raw code if no blocks
        return text.strip()
