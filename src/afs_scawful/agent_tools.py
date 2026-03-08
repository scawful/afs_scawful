"""Triforce/65816 agent tools for afs-scawful."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from afs.agent.tools import (
    DEFAULT_ASAR_PATH,
    DEFAULT_CONTEXT_ROOT,
    Tool,
    ToolResult,
    create_afs_tools,
)


async def asar_handler(args: dict[str, Any]) -> ToolResult:
    """Assemble 65816 code with asar."""
    code = args.get("code", "")
    if not code:
        return ToolResult(success=False, content="", error="No code provided")

    code_match = re.search(r"```(?:asm|assembly)?\n(.*?)```", code, re.DOTALL)
    if code_match:
        code = code_match.group(1)

    if "lorom" not in code.lower() and "hirom" not in code.lower():
        code = "lorom\n\n" + code
    if "org " not in code.lower():
        code = code.replace("lorom\n", "lorom\n\norg $008000\n")

    asar_path = args.get("asar_path", str(DEFAULT_ASAR_PATH))

    with tempfile.TemporaryDirectory() as tmpdir:
        asm_path = Path(tmpdir) / "input.asm"
        rom_path = Path(tmpdir) / "output.sfc"
        asm_path.write_text(code)
        rom_path.write_bytes(b"\x00" * 0x80000)

        try:
            result = subprocess.run(
                [asar_path, "--no-title-check", str(asm_path), str(rom_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            return ToolResult(success=False, content="", error=f"asar not found at {asar_path}")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, content="", error="Assembly timed out")

        if result.returncode == 0:
            rom_data = rom_path.read_bytes()
            code_bytes = sum(1 for b in rom_data if b != 0)
            return ToolResult(
                success=True,
                content=f"Assembly successful! {code_bytes} bytes of code generated.",
                metadata={"code_bytes": code_bytes, "source": code},
            )

        errors = result.stderr or result.stdout
        return ToolResult(
            success=False,
            content="",
            error=f"Assembly failed:\n{errors}",
            metadata={"source": code},
        )


async def yaze_mcp_handler(args: dict[str, Any]) -> ToolResult:
    """Query YAZE emulator state via MCP."""
    command = args.get("command", "status")
    mcp_args = args.get("args", {})

    try:
        result = subprocess.run(
            [
                "claude",
                "mcp",
                "call",
                "--server",
                "yaze-debugger",
                "--tool",
                command,
                "--args",
                json.dumps(mcp_args),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return ToolResult(success=False, content="", error="claude CLI not found - MCP tools unavailable")
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, content="", error="MCP call timed out")

    if result.returncode == 0:
        return ToolResult(success=True, content=result.stdout, metadata={"command": command})
    return ToolResult(success=False, content="", error=result.stderr or "MCP call failed")


async def alttp_knowledge_handler(args: dict[str, Any]) -> ToolResult:
    """Look up ALTTP RAM addresses, sprites, and hardware data."""
    query = args.get("query", "")
    if not query:
        return ToolResult(success=False, content="", error="No query provided")

    try:
        result = subprocess.run(
            [
                "claude",
                "mcp",
                "call",
                "--server",
                "hyrule-historian",
                "--tool",
                "search",
                "--args",
                json.dumps({"query": query}),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return ToolResult(
                success=True,
                content=result.stdout,
                metadata={"query": query, "source": "hyrule-historian"},
            )
    except Exception:
        pass

    knowledge_dir = DEFAULT_CONTEXT_ROOT / "knowledge" / "alttp"
    if knowledge_dir.exists():
        try:
            result = subprocess.run(
                ["rg", "--max-count=20", "-i", query, str(knowledge_dir)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip():
                return ToolResult(
                    success=True,
                    content=result.stdout,
                    metadata={"query": query, "source": "local_knowledge"},
                )
        except Exception:
            pass

    return ToolResult(success=False, content="", error=f"No knowledge found for: {query}")


def create_triforce_tools(
    asar_path: str | None = None,
    context_root: Path | None = None,
) -> list[Tool]:
    """Create Triforce assembly tools (includes AFS tools)."""
    afs_tools = create_afs_tools(context_root)
    asar = asar_path or str(DEFAULT_ASAR_PATH)

    async def _assemble(args: dict[str, Any]) -> ToolResult:
        args["asar_path"] = asar
        return await asar_handler(args)

    triforce_specific = [
        Tool(
            name="assemble",
            description="Assemble 65816 code with asar assembler",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "65816 assembly code to compile",
                    }
                },
                "required": ["code"],
            },
            handler=_assemble,
        ),
        Tool(
            name="yaze_debug",
            description="Query YAZE emulator state (registers, memory, breakpoints)",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Debug command (status, read_memory, set_breakpoint, etc.)",
                    },
                    "args": {
                        "type": "object",
                        "description": "Command arguments",
                        "default": {},
                    },
                },
                "required": ["command"],
            },
            handler=yaze_mcp_handler,
        ),
        Tool(
            name="alttp_lookup",
            description="Look up ALTTP RAM addresses, sprites, graphics, or game data",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to look up (e.g., 'Link X position', 'sword sprite', 'DMA registers')",
                    }
                },
                "required": ["query"],
            },
            handler=alttp_knowledge_handler,
        ),
    ]

    return afs_tools + triforce_specific
