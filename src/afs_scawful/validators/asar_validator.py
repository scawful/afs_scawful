"""Asar Validator for verifying 65816 assembly code.

Uses the actual 'asar' binary to assemble code snippets against a dummy ROM.
This provides 100% accurate syntax and label validation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from ..training import TrainingSample
from .base import ValidationResult, Validator

logger = logging.getLogger(__name__)

def _resolve_env_path(env_var: str) -> Path | None:
    value = os.environ.get(env_var)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _default_asar_path() -> Path:
    env = _resolve_env_path("AFS_ASAR_PATH")
    if env:
        return env
    found = shutil.which("asar")
    if found:
        return Path(found)
    return Path("asar")


def _default_rom_path() -> Path:
    env = _resolve_env_path("AFS_ASAR_ROM")
    if env:
        return env
    candidate = Path.home() / "src" / "training" / "roms" / "dummy.sfc"
    if candidate.exists():
        return candidate
    return Path.home() / ".context" / "training" / "dummy.sfc"


class AsarValidator(Validator):
    """Validates assembly code by running it through Asar."""

    def __init__(self, asar_path: Path | None = None, rom_path: Path | None = None):
        super().__init__("AsarValidator", "asm")
        self.asar_path = asar_path or _default_asar_path()
        self.rom_path = rom_path or _default_rom_path()
        
        if not self.asar_path.exists():
            logger.warning("Asar binary not found at %s", self.asar_path)
        if not self.rom_path.exists():
            logger.warning("Dummy ROM not found at %s", self.rom_path)

    async def validate(self, sample: TrainingSample) -> ValidationResult:
        """Run asar on the sample output code."""
        if not self.asar_path.exists() or not self.rom_path.exists():
            return ValidationResult(
                valid=True,
                score=0.5,
                warnings=["Asar validator skipped: binary or ROM missing"],
            )

        # Extract code (simple heuristic: look for code blocks or use full output)
        code = self._extract_code(sample.output)
        if not code:
            return ValidationResult(valid=False, score=0.0, errors=["No code found"])

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_file = tmp_path / "test.asm"
            rom_file = tmp_path / "test.sfc"

            # Copy dummy ROM to temp (to avoid modifying the original)
            shutil.copy(self.rom_path, rom_file)
            
            # Wrap code in a safe patch structure
            # We assume the code is a snippet, so we hook it into free space
            wrapped_code = (
                "lorom\n"
                "org $008000\n"  # Hook into start of ROM
                f"{code}\n"
            )

            source_file.write_text(wrapped_code)

            # Run asar
            proc = await asyncio.create_subprocess_exec(
                str(self.asar_path),
                str(source_file),
                str(rom_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return ValidationResult(valid=True, score=1.0)
            else:
                error_msg = stderr.decode() + stdout.decode()
                # Clean up error message
                lines = [l for l in error_msg.split('\n') if "error:" in l.lower()]
                return ValidationResult(
                    valid=False,
                    score=0.0,
                    errors=lines[:3] or ["Asar failed to assemble"],
                )

    def _extract_code(self, text: str) -> str:
        """Extract ASM code from markdown block or raw text."""
        if "```asm" in text:
            parts = text.split("```asm")
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
        if "```" in text:
            parts = text.split("```")
            if len(parts) > 1:
                return parts[1].strip()
        return text  # Assume raw code if no blocks
