"""Claude SDK orchestrator for personal/domain expert delegation."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from afs.agents.base import (
    AgentResult,
    build_base_parser,
    configure_logging,
    emit_result,
    now_iso,
)

AGENT_NAME = "claude-orchestrator"
AGENT_DESCRIPTION = "Claude-powered orchestrator with local expert delegation and MCP tools"

logger = logging.getLogger(__name__)


@dataclass
class ExpertModel:
    """Local expert model configuration."""

    name: str
    ollama_tag: str
    description: str
    domains: list[str]


@dataclass
class MCPServer:
    """MCP server configuration."""

    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    tools: list[str]
    description: str


EXPERT_MODELS = {
    "nayru": ExpertModel(
        name="nayru",
        ollama_tag="nayru-v7:latest",
        description="65816 ASM generation and explanation",
        domains=["asm", "generation", "65816"],
    ),
    "veran": ExpertModel(
        name="veran",
        ollama_tag="veran-v4:latest",
        description="SNES hardware analysis (PPU, APU, DMA, Mode 7)",
        domains=["hardware", "ppu", "apu", "dma", "mode7"],
    ),
    "farore": ExpertModel(
        name="farore",
        ollama_tag="farore-v5:latest",
        description="65816 debugging and diagnosis",
        domains=["debug", "diagnosis", "bugs"],
    ),
    "majora": ExpertModel(
        name="majora",
        ollama_tag="majora-v2:latest",
        description="Oracle of Secrets architecture specialist",
        domains=["oos", "oracle", "custom"],
    ),
}

_YAZE_MCP_ROOT = os.environ.get("YAZE_MCP_PATH", "/Users/scawful/Code/yaze-mcp")

MCP_SERVERS = {
    "yaze-debugger": MCPServer(
        name="yaze-debugger",
        command=f"{_YAZE_MCP_ROOT}/venv/bin/python",
        args=[f"{_YAZE_MCP_ROOT}/server.py"],
        env={"PYTHONPATH": _YAZE_MCP_ROOT},
        tools=[
            "control_emulator",
            "step_emulator",
            "run_to_breakpoint",
            "get_debug_status",
            "get_game_state",
            "read_memory",
            "write_memory",
            "add_breakpoint",
            "remove_breakpoint",
            "list_breakpoints",
            "get_disassembly",
            "validate_asm",
            "assemble_and_run",
            "get_rom_info",
            "read_rom_bytes",
            "read_overworld_map",
            "read_dungeon_room",
            "create_snapshot",
            "list_snapshots",
        ],
        description="YAZE emulator debugging via gRPC",
    ),
}


def query_ollama(model_tag: str, prompt: str, timeout: int = 120) -> str:
    """Query a local Ollama model synchronously."""
    try:
        result = subprocess.run(
            ["ollama", "run", model_tag, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Error: Query timed out"
    except FileNotFoundError:
        return "Error: Ollama not found"
    except Exception as exc:
        return f"Error: {exc}"


async def run_orchestrator(
    prompt: str,
    working_dir: Path | None = None,
    enable_mcp: bool = False,
) -> dict[str, Any]:
    """Run the Claude orchestrator with expert model delegation."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError:
        return {
            "status": "error",
            "error": "claude-agent-sdk not installed. Run: pip install claude-agent-sdk",
        }

    expert_info = []
    for name, model in EXPERT_MODELS.items():
        expert_info.append(f"- **{name}** ({model.ollama_tag}): {model.description}")
        expert_info.append(f"  Domains: {', '.join(model.domains)}")

    expert_info_str = "\n".join(expert_info)

    mcp_tool_info = ""
    if enable_mcp:
        mcp_tool_info = """

## YAZE Emulator Tools
You also have access to YAZE emulator tools for live debugging (if YAZE is running with gRPC):
- yaze_read_memory / yaze_write_memory: Read/write emulator memory
- yaze_disassemble: Get disassembly at any address
- yaze_validate_asm: Validate assembly code with ASAR
- yaze_game_state: Get current game state (Link position, health)
- yaze_debug_status: Get emulator status and CPU state
- yaze_add_breakpoint / yaze_step: Set breakpoints and step through code"""

    system_prompt = f"""You are an orchestrator agent for personal ROM hacking and 65816 assembly development.

## Expert Models
You can delegate to specialized local expert models via Ollama. Use the Bash tool:
```bash
ollama run <model_tag> "<question>"
```

Available experts:
{expert_info_str}

## Usage Guidelines
1. Determine which expert or experts best fit the request.
2. Delegate to the appropriate expert(s) using `ollama run`.
3. Synthesize their responses into a coherent answer.
4. Add your own reasoning and context as needed.

For complex questions, consult multiple experts and combine their knowledge.{mcp_tool_info}"""

    mcp_servers: dict[str, object] = {}
    if enable_mcp:
        mcp_servers["yaze-debugger"] = {
            "command": MCP_SERVERS["yaze-debugger"].command,
            "args": MCP_SERVERS["yaze-debugger"].args,
            "env": MCP_SERVERS["yaze-debugger"].env,
        }

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers=mcp_servers if mcp_servers else None,
        cwd=str(working_dir) if working_dir else None,
        permission_mode="bypassPermissions",
    )

    messages = []
    try:
        async for message in query(prompt=prompt, options=options):
            messages.append(message)
            if hasattr(message, "content"):
                for block in getattr(message, "content", []):
                    if hasattr(block, "type") and block.type == "tool_use":
                        logger.info("Tool call: %s", block.name)

        final_text = ""
        for msg in messages:
            if hasattr(msg, "content"):
                for block in msg.content:
                    if hasattr(block, "text"):
                        final_text += block.text

        return {
            "status": "success",
            "response": final_text,
            "message_count": len(messages),
        }
    except Exception as exc:
        logger.exception("Orchestrator error")
        return {
            "status": "error",
            "error": str(exc),
        }


async def run_interactive(
    working_dir: Path | None = None,
    enable_mcp: bool = False,
) -> None:
    """Run an interactive session with the orchestrator."""
    print("Claude Orchestrator with Local Expert Models")
    print("Available experts: nayru, veran, farore, majora")
    if enable_mcp:
        print("MCP tools enabled: yaze-debugger")
    print("Type 'quit' or 'exit' to end session.\n")

    while True:
        try:
            prompt = input("You: ").strip()
            if not prompt:
                continue
            if prompt.lower() in ("quit", "exit"):
                print("Goodbye!")
                break

            result = await run_orchestrator(prompt, working_dir, enable_mcp)
            if result["status"] == "success":
                print(f"\nClaude: {result['response']}\n")
            else:
                print(f"\nError: {result.get('error', 'Unknown error')}\n")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            break


def main(args: Sequence[str] | None = None) -> int:
    """Main entrypoint for the claude-orchestrator agent."""
    parser = build_base_parser(AGENT_DESCRIPTION)
    parser.add_argument("--prompt", help="Single prompt to run (non-interactive mode).")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode.")
    parser.add_argument("--working-dir", help="Working directory for the agent.")
    parser.add_argument(
        "--with-mcp",
        action="store_true",
        help="Enable MCP tools (yaze-debugger).",
    )

    parsed = parser.parse_args(args)
    configure_logging(parsed.quiet)

    started = now_iso()
    working_dir = Path(parsed.working_dir).expanduser() if parsed.working_dir else None

    if parsed.interactive:
        asyncio.run(run_interactive(working_dir, parsed.with_mcp))
        return 0

    if not parsed.prompt:
        parser.error("Either --prompt or --interactive is required")

    result_data = asyncio.run(run_orchestrator(parsed.prompt, working_dir, parsed.with_mcp))
    result = AgentResult(
        name=AGENT_NAME,
        status=result_data.get("status", "unknown"),
        started_at=started,
        finished_at=now_iso(),
        duration_seconds=0,
        payload=result_data,
    )

    output_path = Path(parsed.output) if parsed.output else None
    emit_result(
        result,
        output_path=output_path,
        force_stdout=parsed.stdout,
        pretty=parsed.pretty,
    )
    return 0 if result_data.get("status") == "success" else 1
