"""
ASAR build orchestration for Oracle-of-Secrets.

Builds ROMs in sandboxes using the asar assembler.
"""

import subprocess
import shutil
import re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from .worktree import Sandbox


@dataclass
class BuildResult:
    """Result of an ASAR build."""

    success: bool
    rom_path: Path | None = None
    symbols_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    build_time_seconds: float = 0.0
    output: str = ""


class AsarBuilder:
    """
    ASAR build orchestration for Oracle-of-Secrets.

    Handles building the ROM hack in a sandbox environment.
    """

    # Default paths (can be overridden)
    ASAR_PATH = Path("~/src/third_party/asar-repo/build/asar/bin/asar").expanduser()
    BASE_ROM_NAME = "oos168_test2.sfc"
    OUTPUT_ROM_NAME = "oos91x.sfc"
    MAIN_ASM = "Oracle_main.asm"

    # Error patterns
    ERROR_PATTERN = re.compile(r"^(.+?):(\d+): error: (.+)$", re.MULTILINE)
    WARNING_PATTERN = re.compile(r"^(.+?):(\d+): warning: (.+)$", re.MULTILINE)

    def __init__(
        self,
        asar_path: Path | None = None,
        base_rom_path: Path | None = None,
    ):
        self.asar_path = asar_path or self.ASAR_PATH

        if not self.asar_path.exists():
            raise FileNotFoundError(f"ASAR not found at {self.asar_path}")

    def build(
        self,
        sandbox: Sandbox,
        generate_symbols: bool = True,
    ) -> BuildResult:
        """
        Build the Oracle-of-Secrets ROM in a sandbox.

        Args:
            sandbox: The sandbox to build in
            generate_symbols: Whether to generate symbol files

        Returns:
            BuildResult with success status and paths
        """
        start_time = datetime.now()

        # Paths within sandbox
        roms_dir = sandbox.worktree_path / "Roms"
        base_rom = roms_dir / self.BASE_ROM_NAME
        output_rom = roms_dir / self.OUTPUT_ROM_NAME
        main_asm = sandbox.worktree_path / self.MAIN_ASM

        # Verify required files exist
        if not main_asm.exists():
            return BuildResult(
                success=False,
                errors=[f"Main ASM file not found: {main_asm}"],
            )

        if not base_rom.exists():
            return BuildResult(
                success=False,
                errors=[f"Base ROM not found: {base_rom}"],
            )

        # Copy base ROM to output
        shutil.copy2(base_rom, output_rom)

        # Build command
        cmd = [str(self.asar_path)]

        if generate_symbols:
            cmd.append("--symbols=wla")

        cmd.extend([str(main_asm), str(output_rom)])

        try:
            result = subprocess.run(
                cmd,
                cwd=sandbox.worktree_path,
                capture_output=True,
                text=True,
                timeout=60,  # 1 minute timeout
            )

            # Parse output for errors and warnings
            output = result.stdout + result.stderr
            errors = self._parse_errors(output)
            warnings = self._parse_warnings(output)

            # Check for symbols file
            symbols_path = None
            if generate_symbols:
                possible_symbols = output_rom.with_suffix(".sym")
                if possible_symbols.exists():
                    symbols_path = possible_symbols

            build_time = (datetime.now() - start_time).total_seconds()

            if result.returncode == 0 and not errors:
                return BuildResult(
                    success=True,
                    rom_path=output_rom,
                    symbols_path=symbols_path,
                    warnings=warnings,
                    build_time_seconds=build_time,
                    output=output,
                )
            else:
                return BuildResult(
                    success=False,
                    errors=errors or [f"Build failed with return code {result.returncode}"],
                    warnings=warnings,
                    build_time_seconds=build_time,
                    output=output,
                )

        except subprocess.TimeoutExpired:
            return BuildResult(
                success=False,
                errors=["Build timed out after 60 seconds"],
                build_time_seconds=60.0,
            )
        except Exception as e:
            return BuildResult(
                success=False,
                errors=[f"Build exception: {str(e)}"],
            )

    def validate_snippet(
        self,
        code: str,
        sandbox: Sandbox | None = None,
    ) -> BuildResult:
        """
        Validate a code snippet using ASAR without full build.

        Creates a minimal test file and attempts to assemble it.
        """
        # Create a minimal test wrapper
        test_code = f"""
lorom

org $008000
{code}
"""

        # Use a temp file for validation
        if sandbox:
            test_file = sandbox.worktree_path / "_test_snippet.asm"
            test_rom = sandbox.worktree_path / "_test_snippet.sfc"
        else:
            import tempfile

            temp_dir = Path(tempfile.mkdtemp())
            test_file = temp_dir / "_test_snippet.asm"
            test_rom = temp_dir / "_test_snippet.sfc"

        try:
            # Write test file
            test_file.write_text(test_code)

            # Create empty ROM (ASAR needs a target file)
            test_rom.write_bytes(b"\x00" * 0x8000)

            # Run ASAR
            result = subprocess.run(
                [str(self.asar_path), str(test_file), str(test_rom)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            output = result.stdout + result.stderr
            errors = self._parse_errors(output)
            warnings = self._parse_warnings(output)

            return BuildResult(
                success=result.returncode == 0 and not errors,
                errors=errors,
                warnings=warnings,
                output=output,
            )

        except Exception as e:
            return BuildResult(
                success=False,
                errors=[f"Validation error: {str(e)}"],
            )
        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()
            if test_rom.exists():
                test_rom.unlink()

    def _parse_errors(self, output: str) -> list[str]:
        """Parse ASAR output for error messages."""
        errors = []
        for match in self.ERROR_PATTERN.finditer(output):
            file_path, line_num, message = match.groups()
            errors.append(f"{file_path}:{line_num}: {message}")
        return errors

    def _parse_warnings(self, output: str) -> list[str]:
        """Parse ASAR output for warning messages."""
        warnings = []
        for match in self.WARNING_PATTERN.finditer(output):
            file_path, line_num, message = match.groups()
            warnings.append(f"{file_path}:{line_num}: {message}")
        return warnings
