"""
Gemini 3 Flash orchestrator for planning and tool calling.

Uses Gemini 3 Flash Preview as the central orchestrator for:
- Task planning and decomposition
- Tool calling and MCP integration
- Expert routing decisions
- Extended thinking for hard problems
"""

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, AsyncGenerator

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class ThinkingLevel(Enum):
    """Thinking budget levels for extended reasoning."""
    NONE = "none"
    LOW = "low"          # ~1K tokens
    MEDIUM = "medium"    # ~4K tokens
    HIGH = "high"        # ~8K tokens
    MAX = "max"          # ~16K tokens


@dataclass
class TaskPlan:
    """A plan for executing a task."""
    task: str
    steps: list[str]
    tools_needed: list[str]
    expert_hints: list[str]
    confidence: float
    thinking_budget: ThinkingLevel = ThinkingLevel.NONE
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThinkingResult:
    """Result of extended thinking."""
    reasoning: str
    conclusions: list[str]
    confidence: float
    tokens_used: int


@dataclass
class ToolCall:
    """A tool call from the orchestrator."""
    name: str
    arguments: dict[str, Any]


@dataclass
class OrchestratorResponse:
    """Response from the orchestrator."""
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: ThinkingResult | None = None
    expert_recommendation: str | None = None
    should_continue: bool = False
    data: dict[str, Any] = field(default_factory=dict)  # Extra data like expert_prompt


class GeminiOrchestrator:
    """
    Gemini 3 Flash orchestrator for Zelda evaluation.

    Handles:
    - Task planning and decomposition
    - Tool calling via function declarations
    - Expert model routing
    - Extended thinking for complex problems
    """

    MODEL_ID = "gemini-2.0-flash"  # Use stable flash, upgrade to 3.0 when available

    # Thinking token budgets
    THINKING_BUDGETS = {
        ThinkingLevel.NONE: 0,
        ThinkingLevel.LOW: 1024,
        ThinkingLevel.MEDIUM: 4096,
        ThinkingLevel.HIGH: 8192,
        ThinkingLevel.MAX: 16384,
    }

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str | None = None,
        tools: list[dict] | None = None,
    ):
        if not HAS_GENAI:
            raise ImportError(
                "google-genai package not installed. "
                "Install with: pip install google-genai"
            )

        self.model_id = model_id or self.MODEL_ID
        self.tools = tools or []

        # Initialize client - check multiple env var names
        import os
        if api_key:
            self.client = genai.Client(api_key=api_key)
        elif os.environ.get("GEMINI_API_KEY"):
            self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        elif os.environ.get("GOOGLE_API_KEY"):
            self.client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        elif os.environ.get("GOOGLE_GENAI_API_KEY"):
            self.client = genai.Client(api_key=os.environ["GOOGLE_GENAI_API_KEY"])
        else:
            raise ValueError(
                "No API key found. Set GEMINI_API_KEY, GOOGLE_API_KEY, "
                "or GOOGLE_GENAI_API_KEY environment variable."
            )

        # System instruction for Zelda evaluation context
        self.system_instruction = self._build_system_instruction()

    def _build_system_instruction(self) -> str:
        """Build the system instruction for the orchestrator."""
        return """You are an orchestrator for evaluating AI models on SNES/65816 assembly and ALTTP ROM hacking.

CRITICAL: You must use the route_to_expert tool for ALL technical questions about:
- 65816 assembly syntax, addressing modes, instructions
- SNES hardware (DMA, PPU, APU)
- ALTTP memory layout, routines, game mechanics
- Code optimization, generation, debugging, or analysis

Expert specialties (ALWAYS route to the appropriate one):
- din: OPTIMIZATION - cycle counting, making code faster/smaller
- nayru: GENERATION - writing new code, implementing features
- farore: DEBUGGING - finding/fixing bugs, error analysis
- veran: ANALYSIS - explaining code, documentation, understanding

Your workflow:
1. PLAN the task into steps
2. For EACH step, call route_to_expert with the right specialist
3. USE other tools (validate_asm, build_sandbox, etc.) as needed
4. SYNTHESIZE expert responses into final answers

When planning, output JSON:
{"steps": [...], "tools_needed": [...], "expert_hints": [...], "confidence": 0.0-1.0}

IMPORTANT: Do NOT answer technical questions yourself. Route to experts."""

    def _convert_tools_to_declarations(self) -> list:
        """Convert tool definitions to Gemini function declarations."""
        if not self.tools:
            return []

        declarations = []
        for tool in self.tools:
            decl = types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=tool.get("parameters", {}),
            )
            declarations.append(decl)

        return [types.Tool(function_declarations=declarations)]

    async def plan_task(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> TaskPlan:
        """
        Create a plan for executing a task.

        Args:
            task: The task description
            context: Additional context (file contents, previous results, etc.)

        Returns:
            TaskPlan with steps and metadata
        """
        prompt = f"""Plan the following task. Output a JSON object with:
- steps: list of concrete action strings
- tools_needed: list of tool names needed
- expert_hints: list of expert names to consult (din, nayru, farore, veran)
- confidence: float 0.0-1.0

Task: {task}

Context: {json.dumps(context) if context else 'None provided'}

Respond with ONLY the JSON object, no markdown."""

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                temperature=0.3,
            ),
        )

        # Parse response
        try:
            text = response.text.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            # Determine thinking level based on confidence
            confidence = data.get("confidence", 0.5)
            if confidence < 0.3:
                thinking = ThinkingLevel.HIGH
            elif confidence < 0.5:
                thinking = ThinkingLevel.MEDIUM
            elif confidence < 0.7:
                thinking = ThinkingLevel.LOW
            else:
                thinking = ThinkingLevel.NONE

            return TaskPlan(
                task=task,
                steps=data.get("steps", []),
                tools_needed=data.get("tools_needed", []),
                expert_hints=data.get("expert_hints", []),
                confidence=confidence,
                thinking_budget=thinking,
                context=context or {},
            )
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback plan
            return TaskPlan(
                task=task,
                steps=["Analyze the task", "Attempt solution", "Verify result"],
                tools_needed=[],
                expert_hints=["nayru"],  # Default to generation expert
                confidence=0.3,
                thinking_budget=ThinkingLevel.MEDIUM,
                context=context or {},
            )

    async def execute_step(
        self,
        step: str,
        context: dict[str, Any],
        tool_executor: Callable[[str, dict], Any] | None = None,
    ) -> OrchestratorResponse:
        """
        Execute a single step with potential tool calls.

        Args:
            step: The step to execute
            context: Current context/state
            tool_executor: Optional callback to execute tool calls

        Returns:
            OrchestratorResponse with results
        """
        prompt = f"""Execute this step: {step}

Current context:
{json.dumps(context, indent=2)}

If you need to call a tool, respond with a function call.
If you need expert help, recommend which expert to consult.
If you can complete the step directly, provide the result."""

        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=0.2,
        )

        # Add tools if available
        tools = self._convert_tools_to_declarations()
        if tools:
            config.tools = tools

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_id,
            contents=prompt,
            config=config,
        )

        # Parse response for tool calls
        tool_calls = []
        expert_rec = None
        expert_prompt = None
        expert_context = None

        # Check for function calls in response
        if hasattr(response, 'candidates') and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}

                    # Special handling for route_to_expert - extract expert info
                    if fc.name == "route_to_expert":
                        expert_rec = args.get("expert")
                        expert_prompt = args.get("prompt", "")
                        expert_context = args.get("context", "")
                    else:
                        tool_calls.append(ToolCall(
                            name=fc.name,
                            arguments=args,
                        ))

        # Execute non-expert tool calls if executor provided
        if tool_calls and tool_executor:
            for tc in tool_calls:
                result = await asyncio.to_thread(
                    tool_executor, tc.name, tc.arguments
                )
                context[f"tool_result_{tc.name}"] = result

        # Check for expert recommendation in text (fallback)
        # Note: response.text can be None when function calls are returned
        try:
            text = response.text if hasattr(response, 'text') else ""
        except ValueError:
            # Gemini raises ValueError when response contains only function calls
            text = ""

        if not expert_rec and text:
            text_lower = text.lower()
            for expert in ["din", "nayru", "farore", "veran"]:
                if f"consult {expert}" in text_lower or f"route to {expert}" in text_lower:
                    expert_rec = expert
                    break

        # Build response with expert routing info
        resp = OrchestratorResponse(
            text=text or "",
            tool_calls=tool_calls,
            expert_recommendation=expert_rec,
            should_continue=bool(tool_calls) or bool(expert_rec),
        )

        # Attach expert routing details for the loop to use
        if expert_rec:
            resp.data["expert_prompt"] = expert_prompt
            resp.data["expert_context"] = expert_context

        return resp

    async def think_extended(
        self,
        problem: str,
        level: ThinkingLevel = ThinkingLevel.MEDIUM,
        context: dict[str, Any] | None = None,
    ) -> ThinkingResult:
        """
        Apply extended thinking to a complex problem.

        Uses Gemini's thinking mode for deeper reasoning.

        Args:
            problem: The problem to reason about
            level: Thinking budget level
            context: Additional context

        Returns:
            ThinkingResult with reasoning chain
        """
        budget = self.THINKING_BUDGETS[level]

        prompt = f"""Think carefully about this problem. Take your time to reason through it step by step.

Problem: {problem}

Context: {json.dumps(context) if context else 'None'}

Consider:
1. What are the key constraints and requirements?
2. What approaches could work? Pros/cons of each?
3. What 65816/SNES/ALTTP specifics are relevant?
4. What could go wrong? Edge cases?
5. What is the most robust solution?

Provide your complete reasoning, then your conclusions."""

        # Use thinking config if model supports it
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=0.4,
            max_output_tokens=budget + 2048,  # Budget + response
        )

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_id,
            contents=prompt,
            config=config,
        )

        text = response.text if hasattr(response, 'text') else ""

        # Parse conclusions from response
        conclusions = []
        if "conclusion" in text.lower():
            # Extract text after "conclusion"
            parts = text.lower().split("conclusion")
            if len(parts) > 1:
                conclusion_text = parts[-1]
                # Split into individual conclusions
                for line in conclusion_text.split("\n"):
                    line = line.strip()
                    if line and len(line) > 10:
                        conclusions.append(line)

        # Estimate confidence from language
        confidence = 0.5
        if any(w in text.lower() for w in ["certain", "definitely", "clearly"]):
            confidence = 0.8
        elif any(w in text.lower() for w in ["likely", "probably", "should"]):
            confidence = 0.6
        elif any(w in text.lower() for w in ["might", "possibly", "uncertain"]):
            confidence = 0.4

        return ThinkingResult(
            reasoning=text,
            conclusions=conclusions[:5],  # Top 5 conclusions
            confidence=confidence,
            tokens_used=len(text.split()) * 2,  # Rough estimate
        )

    async def route_to_expert(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, float]:
        """
        Decide which expert model should handle a query.

        Args:
            query: The query to route
            context: Additional context

        Returns:
            Tuple of (expert_name, confidence)
        """
        prompt = f"""Which expert should handle this query?

Experts:
- din: Assembly optimization, cycle counting, performance tuning
- nayru: Code generation, writing new routines and features
- farore: Debugging, finding and fixing bugs, error analysis
- veran: Code analysis, documentation, understanding existing code

Query: {query}

Respond with JSON: {{"expert": "name", "confidence": 0.0-1.0, "reason": "brief reason"}}"""

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
            ),
        )

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)
            return data.get("expert", "nayru"), data.get("confidence", 0.5)
        except (json.JSONDecodeError, KeyError):
            # Default to nayru for generation tasks
            return "nayru", 0.5

    async def reflect(
        self,
        results: list[dict],
        original_task: str,
    ) -> dict[str, Any]:
        """
        Reflect on results and determine next steps.

        Args:
            results: List of results from previous iterations
            original_task: The original task being worked on

        Returns:
            Reflection with strategy adjustments
        """
        prompt = f"""Reflect on the progress toward this task:

Task: {original_task}

Results so far:
{json.dumps(results, indent=2)}

Consider:
1. What progress has been made?
2. What worked well? What didn't?
3. Should we change approach?
4. What's the next best step?

Respond with JSON:
{{
    "progress_percent": 0-100,
    "successful_strategies": ["..."],
    "failed_strategies": ["..."],
    "should_backtrack": true/false,
    "next_step": "...",
    "confidence": 0.0-1.0
}}"""

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            return json.loads(text)
        except (json.JSONDecodeError, KeyError):
            return {
                "progress_percent": 50,
                "successful_strategies": [],
                "failed_strategies": [],
                "should_backtrack": False,
                "next_step": "Continue with current approach",
                "confidence": 0.5,
            }
