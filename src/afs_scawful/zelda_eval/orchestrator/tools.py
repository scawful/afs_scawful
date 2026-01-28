"""
Tool definitions for the Gemini orchestrator.

Maps orchestrator tool calls to:
- yaze-debugger MCP tools (emulator control, memory, behavioral testing)
- Sandbox operations (worktree, build, apply patches)
- Expert routing (invoke 7B specialists via Ollama)
"""

from dataclasses import dataclass, field
from typing import Any, Callable
from pathlib import Path


@dataclass
class ToolDefinition:
    """Definition of a tool available to the orchestrator."""
    name: str
    description: str
    parameters: dict[str, Any]
    category: str  # "emulator", "sandbox", "expert", "knowledge"
    mcp_server: str | None = None  # Which MCP server provides this


# Emulator tools (yaze-debugger MCP)
EMULATOR_TOOLS = [
    ToolDefinition(
        name="validate_asm",
        description="Validate 65816 assembly code syntax without full ROM build",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The 65816 assembly code to validate"
                },
                "context": {
                    "type": "string",
                    "description": "Optional surrounding code context"
                }
            },
            "required": ["code"]
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="assemble_and_run",
        description="Assemble code and execute it in the emulator, returning the result",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The 65816 assembly code to assemble and run"
                },
                "entry_point": {
                    "type": "string",
                    "description": "Label or address to start execution"
                },
                "max_cycles": {
                    "type": "integer",
                    "description": "Maximum CPU cycles to run (default 1000)"
                }
            },
            "required": ["code"]
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="read_memory",
        description="Read bytes from emulator memory",
        parameters={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Memory address (e.g., '$7E0000' or '0x7E0000')"
                },
                "length": {
                    "type": "integer",
                    "description": "Number of bytes to read (default 16)"
                }
            },
            "required": ["address"]
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="write_memory",
        description="Write bytes to emulator memory",
        parameters={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Memory address to write to"
                },
                "data": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Bytes to write (as integers 0-255)"
                }
            },
            "required": ["address", "data"]
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="get_cpu_state",
        description="Get current CPU register state",
        parameters={
            "type": "object",
            "properties": {}
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="get_disassembly",
        description="Disassemble code at an address",
        parameters={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Address to disassemble from"
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of lines to disassemble (default 10)"
                }
            },
            "required": ["address"]
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="add_breakpoint",
        description="Add a breakpoint at an address",
        parameters={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Address for breakpoint"
                },
                "condition": {
                    "type": "string",
                    "description": "Optional condition expression"
                }
            },
            "required": ["address"]
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="get_game_state",
        description="Get ALTTP game state (Link position, health, items, etc.)",
        parameters={
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific fields to query (e.g., ['link_x', 'link_y', 'health'])"
                }
            }
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
    ToolDefinition(
        name="behavioral_test_run",
        description="Run a behavioral test with code snippet and expected outcomes",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Assembly code to test"
                },
                "setup": {
                    "type": "object",
                    "description": "Initial state setup (memory values, registers)"
                },
                "assertions": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Expected outcomes to verify"
                }
            },
            "required": ["code", "assertions"]
        },
        category="emulator",
        mcp_server="yaze-debugger",
    ),
]

# Sandbox tools (internal)
SANDBOX_TOOLS = [
    ToolDefinition(
        name="create_sandbox",
        description="Create a new git worktree sandbox for testing",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID to associate with sandbox"
                }
            }
        },
        category="sandbox",
    ),
    ToolDefinition(
        name="apply_patch",
        description="Apply a code change to a file in the sandbox",
        parameters={
            "type": "object",
            "properties": {
                "sandbox_id": {
                    "type": "string",
                    "description": "ID of the sandbox to modify"
                },
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the file"
                },
                "content": {
                    "type": "string",
                    "description": "New file content"
                }
            },
            "required": ["sandbox_id", "file_path", "content"]
        },
        category="sandbox",
    ),
    ToolDefinition(
        name="build_sandbox",
        description="Build the ROM in a sandbox using ASAR",
        parameters={
            "type": "object",
            "properties": {
                "sandbox_id": {
                    "type": "string",
                    "description": "ID of the sandbox to build"
                },
                "generate_symbols": {
                    "type": "boolean",
                    "description": "Whether to generate symbol file (default true)"
                }
            },
            "required": ["sandbox_id"]
        },
        category="sandbox",
    ),
    ToolDefinition(
        name="read_sandbox_file",
        description="Read a file from the sandbox",
        parameters={
            "type": "object",
            "properties": {
                "sandbox_id": {
                    "type": "string",
                    "description": "ID of the sandbox"
                },
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the file"
                }
            },
            "required": ["sandbox_id", "file_path"]
        },
        category="sandbox",
    ),
    ToolDefinition(
        name="cleanup_sandbox",
        description="Remove a sandbox and its worktree",
        parameters={
            "type": "object",
            "properties": {
                "sandbox_id": {
                    "type": "string",
                    "description": "ID of the sandbox to remove"
                }
            },
            "required": ["sandbox_id"]
        },
        category="sandbox",
    ),
]

# Expert routing tools (internal)
EXPERT_TOOLS = [
    ToolDefinition(
        name="route_to_expert",
        description="""Route a query to a specialist 7B expert model trained on 65816/SNES/ALTTP.
ALWAYS use this tool for technical questions. Choose the right expert:
- din: Assembly OPTIMIZATION, cycle counting, making code faster/smaller
- nayru: Code GENERATION, writing new routines, implementing features
- farore: DEBUGGING, finding bugs, fixing errors, analyzing failures
- veran: Code ANALYSIS, explaining code, documentation, understanding behavior

The expert will provide a detailed technical response based on their specialty.""",
        parameters={
            "type": "object",
            "properties": {
                "expert": {
                    "type": "string",
                    "enum": ["din", "nayru", "farore", "veran"],
                    "description": "Which expert to consult: din (optimize), nayru (generate), farore (debug), veran (analyze)"
                },
                "prompt": {
                    "type": "string",
                    "description": "The specific technical question or task for the expert"
                },
                "context": {
                    "type": "string",
                    "description": "Relevant code, error messages, or background info"
                }
            },
            "required": ["expert", "prompt"]
        },
        category="expert",
    ),
    ToolDefinition(
        name="expert_consensus",
        description="Query multiple experts and synthesize their responses. Use when you need perspectives from different specialties.",
        parameters={
            "type": "object",
            "properties": {
                "experts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Which experts to consult (din, nayru, farore, veran)"
                },
                "prompt": {
                    "type": "string",
                    "description": "The prompt/query for experts"
                }
            },
            "required": ["experts", "prompt"]
        },
        category="expert",
    ),
]

# Knowledge tools (book-of-mudora, hyrule-historian MCPs)
KNOWLEDGE_TOOLS = [
    ToolDefinition(
        name="lookup_ram_address",
        description="Look up what a RAM address is used for in ALTTP",
        parameters={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "RAM address to look up (e.g., '$7E0000')"
                }
            },
            "required": ["address"]
        },
        category="knowledge",
        mcp_server="book-of-mudora",
    ),
    ToolDefinition(
        name="lookup_routine",
        description="Look up information about an ALTTP routine",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Routine name or address"
                }
            },
            "required": ["name"]
        },
        category="knowledge",
        mcp_server="book-of-mudora",
    ),
    ToolDefinition(
        name="search_disassembly",
        description="Search the ALTTP disassembly for patterns or text",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "file_filter": {
                    "type": "string",
                    "description": "Optional file pattern to search in"
                }
            },
            "required": ["query"]
        },
        category="knowledge",
        mcp_server="hyrule-historian",
    ),
]


def get_all_tools() -> list[ToolDefinition]:
    """Get all available tool definitions."""
    return EMULATOR_TOOLS + SANDBOX_TOOLS + EXPERT_TOOLS + KNOWLEDGE_TOOLS


def get_tools_by_category(category: str) -> list[ToolDefinition]:
    """Get tools filtered by category."""
    return [t for t in get_all_tools() if t.category == category]


def get_tool_schemas() -> list[dict]:
    """Get tool schemas in Gemini function declaration format."""
    tools = get_all_tools()
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in tools
    ]


class ToolExecutor:
    """
    Executes tool calls by routing to appropriate backends.

    Connects tool calls to:
    - MCP servers (yaze-debugger, book-of-mudora, etc.)
    - Internal sandbox operations
    - Expert model registry
    """

    def __init__(
        self,
        sandbox_manager=None,
        sandbox_builder=None,
        expert_registry=None,
        mcp_client=None,
    ):
        self.sandbox_manager = sandbox_manager
        self.sandbox_builder = sandbox_builder
        self.expert_registry = expert_registry
        self.mcp_client = mcp_client

        # Map tool names to handlers
        self._handlers: dict[str, Callable] = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register tool handlers."""
        # Sandbox handlers
        if self.sandbox_manager:
            self._handlers["create_sandbox"] = self._handle_create_sandbox
            self._handlers["apply_patch"] = self._handle_apply_patch
            self._handlers["read_sandbox_file"] = self._handle_read_sandbox_file
            self._handlers["cleanup_sandbox"] = self._handle_cleanup_sandbox

        if self.sandbox_builder:
            self._handlers["build_sandbox"] = self._handle_build_sandbox

        # Expert handlers
        if self.expert_registry:
            self._handlers["route_to_expert"] = self._handle_route_to_expert
            self._handlers["expert_consensus"] = self._handle_expert_consensus

        # MCP handlers would be registered when MCP client is available
        # For now, these are stubs that indicate MCP is needed

    async def execute(self, tool_name: str, arguments: dict) -> dict[str, Any]:
        """Execute a tool call and return results."""
        if tool_name in self._handlers:
            return await self._handlers[tool_name](arguments)

        # Check if it's an MCP tool
        tool_def = next((t for t in get_all_tools() if t.name == tool_name), None)
        if tool_def and tool_def.mcp_server:
            return await self._handle_mcp_tool(tool_def, arguments)

        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
        }

    async def _handle_create_sandbox(self, args: dict) -> dict:
        """Handle create_sandbox tool call."""
        session_id = args.get("session_id")
        sandbox = self.sandbox_manager.create_sandbox(session_id=session_id)
        return {
            "success": True,
            "sandbox_id": sandbox.id,
            "worktree_path": str(sandbox.worktree_path),
            "branch_name": sandbox.branch_name,
        }

    async def _handle_apply_patch(self, args: dict) -> dict:
        """Handle apply_patch tool call."""
        sandbox_id = args["sandbox_id"]
        file_path = args["file_path"]
        content = args["content"]

        success = self.sandbox_manager.apply_patch(sandbox_id, file_path, content)
        return {
            "success": success,
            "file_path": file_path,
        }

    async def _handle_build_sandbox(self, args: dict) -> dict:
        """Handle build_sandbox tool call."""
        sandbox_id = args["sandbox_id"]
        generate_symbols = args.get("generate_symbols", True)

        sandbox = self.sandbox_manager.get_sandbox(sandbox_id)
        if not sandbox:
            return {"success": False, "error": f"Sandbox not found: {sandbox_id}"}

        result = self.sandbox_builder.build(sandbox, generate_symbols=generate_symbols)
        return {
            "success": result.success,
            "rom_path": str(result.rom_path) if result.rom_path else None,
            "symbols_path": str(result.symbols_path) if result.symbols_path else None,
            "errors": result.errors,
            "warnings": result.warnings,
            "build_time": result.build_time_seconds,
        }

    async def _handle_read_sandbox_file(self, args: dict) -> dict:
        """Handle read_sandbox_file tool call."""
        sandbox_id = args["sandbox_id"]
        file_path = args["file_path"]

        sandbox = self.sandbox_manager.get_sandbox(sandbox_id)
        if not sandbox:
            return {"success": False, "error": f"Sandbox not found: {sandbox_id}"}

        full_path = sandbox.worktree_path / file_path
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = full_path.read_text()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_cleanup_sandbox(self, args: dict) -> dict:
        """Handle cleanup_sandbox tool call."""
        sandbox_id = args["sandbox_id"]
        success = self.sandbox_manager.cleanup_sandbox(sandbox_id)
        return {"success": success}

    async def _handle_route_to_expert(self, args: dict) -> dict:
        """Handle route_to_expert tool call."""
        expert = args["expert"]
        prompt = args["prompt"]
        context = args.get("context", "")

        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        try:
            response = await self.expert_registry.generate(expert, full_prompt)
            return {
                "success": True,
                "expert": expert,
                "response": response,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _handle_expert_consensus(self, args: dict) -> dict:
        """Handle expert_consensus tool call."""
        experts = args["experts"]
        prompt = args["prompt"]

        responses = {}
        for expert in experts:
            try:
                response = await self.expert_registry.generate(expert, prompt)
                responses[expert] = response
            except Exception as e:
                responses[expert] = f"Error: {e}"

        return {
            "success": True,
            "responses": responses,
        }

    async def _handle_mcp_tool(self, tool_def: ToolDefinition, args: dict) -> dict:
        """Handle tool calls that route to MCP servers."""
        if not self.mcp_client:
            return {
                "success": False,
                "error": f"MCP client not configured for {tool_def.mcp_server}",
            }

        try:
            result = await self.mcp_client.call_tool(
                server=tool_def.mcp_server,
                tool=tool_def.name,
                arguments=args,
            )
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
