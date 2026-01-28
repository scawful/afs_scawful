"""
Agentic problem-solving loop for Zelda evaluation.

Implements the multi-step reasoning loop that:
1. Plans tasks with the orchestrator
2. Executes steps with tool calls
3. Routes to expert models as needed
4. Applies extended thinking for hard problems
5. Reflects on progress and adjusts strategy
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
import json

from ..orchestrator.gemini import (
    GeminiOrchestrator,
    TaskPlan,
    ThinkingLevel,
    ThinkingResult,
    OrchestratorResponse,
)
from ..orchestrator.tools import ToolExecutor, get_tool_schemas
from ..experts.registry import ExpertRegistry
from ..metrics.logger import EvalLogger
from ..metrics.collector import MetricsCollector


class LoopState(Enum):
    """State of the agentic loop."""
    INITIALIZING = "initializing"
    PLANNING = "planning"
    EXECUTING = "executing"
    THINKING = "thinking"
    ROUTING = "routing"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IterationResult:
    """Result of a single loop iteration."""
    iteration: int
    state: LoopState
    step: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    expert_used: str | None = None
    thinking_used: bool = False
    success: bool = False
    output: str = ""
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class LoopResult:
    """Final result of the agentic loop."""
    task: str
    success: bool
    iterations: list[IterationResult]
    total_duration_seconds: float
    final_output: str
    sandbox_id: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopConfig:
    """Configuration for the agentic loop."""
    max_iterations: int = 10
    reflection_interval: int = 3  # Reflect every N iterations
    thinking_threshold: float = 0.5  # Use thinking when confidence below this
    backtrack_on_failure: bool = True
    create_sandbox: bool = True  # Auto-create sandbox for code tasks


class AgenticLoop:
    """
    Multi-step problem-solving loop for Zelda evaluation.

    Coordinates:
    - GeminiOrchestrator for planning and tool calling
    - ExpertRegistry for specialist model routing
    - ToolExecutor for executing tool calls
    - Sandbox management for code testing
    - EvalLogger for detailed observability
    """

    def __init__(
        self,
        orchestrator: GeminiOrchestrator | None = None,
        expert_registry: ExpertRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        config: LoopConfig | None = None,
        on_iteration: Callable[[IterationResult], None] | None = None,
        logger: EvalLogger | None = None,
        metrics_collector: MetricsCollector | None = None,
    ):
        self.config = config or LoopConfig()
        self.on_iteration = on_iteration

        # Initialize components
        self.orchestrator = orchestrator or GeminiOrchestrator(
            tools=get_tool_schemas()
        )
        self.expert_registry = expert_registry or ExpertRegistry()
        self.tool_executor = tool_executor

        # Initialize logging and metrics
        self.logger = logger
        self.metrics = metrics_collector
        if self.logger and self.metrics:
            # Register metrics collector as a logger handler
            self.logger.handlers.append(self.metrics)

        # State tracking
        self.current_state = LoopState.INITIALIZING
        self.iteration_results: list[IterationResult] = []
        self.context: dict[str, Any] = {}
        self.current_sandbox_id: str | None = None
        self.current_benchmark_id: str | None = None

    async def run(
        self,
        task: str,
        initial_context: dict[str, Any] | None = None,
        benchmark_id: str | None = None,
    ) -> LoopResult:
        """
        Run the agentic loop on a task.

        Args:
            task: The task to solve
            initial_context: Optional starting context
            benchmark_id: Optional benchmark ID for logging

        Returns:
            LoopResult with success status and outputs
        """
        start_time = datetime.now()
        self.context = initial_context or {}
        self.context["task"] = task
        self.iteration_results = []
        self.current_benchmark_id = benchmark_id

        if self.logger:
            self.logger.info(f"Starting task: {task[:100]}...", benchmark_id=benchmark_id)

        try:
            # Phase 1: Planning
            self.current_state = LoopState.PLANNING
            plan = await self.orchestrator.plan_task(task, self.context)
            self.context["plan"] = {
                "steps": plan.steps,
                "tools_needed": plan.tools_needed,
                "expert_hints": plan.expert_hints,
                "confidence": plan.confidence,
            }

            # Log the plan
            if self.logger:
                self.logger.plan(
                    task=task,
                    steps=plan.steps,
                    tools_needed=plan.tools_needed,
                    expert_hints=plan.expert_hints,
                    confidence=plan.confidence,
                    thinking_budget=plan.thinking_budget.value,
                    benchmark_id=benchmark_id,
                )

            # Create sandbox if needed for code tasks
            if self.config.create_sandbox and self._is_code_task(task, plan):
                await self._create_sandbox()

            # Phase 2: Execution loop
            for i in range(self.config.max_iterations):
                iteration_start = datetime.now()
                thinking_used = False
                confidence_before = plan.confidence

                # Check if we need extended thinking
                if plan.confidence < self.config.thinking_threshold or (
                    i > 0 and not self.iteration_results[-1].success
                ):
                    self.current_state = LoopState.THINKING
                    thinking_result = await self._apply_thinking(task, plan)
                    thinking_used = True
                    self.context["thinking"] = {
                        "reasoning": thinking_result.reasoning[:1000],  # Truncate
                        "conclusions": thinking_result.conclusions,
                        "confidence": thinking_result.confidence,
                    }

                    # Log thinking
                    if self.logger:
                        self.logger.thinking(
                            level=plan.thinking_budget.value,
                            tokens=thinking_result.tokens_used,
                            reasoning=thinking_result.reasoning,
                            conclusions=thinking_result.conclusions,
                            confidence_before=confidence_before,
                            confidence_after=thinking_result.confidence,
                            benchmark_id=benchmark_id,
                            iteration=i,
                        )

                # Execute next step
                self.current_state = LoopState.EXECUTING
                step_index = self._get_next_step_index()

                if step_index >= len(plan.steps):
                    # All steps completed
                    break

                step = plan.steps[step_index]
                result = await self._execute_step(i, step, plan)
                result.thinking_used = thinking_used

                # Record iteration
                result.duration_seconds = (
                    datetime.now() - iteration_start
                ).total_seconds()
                self.iteration_results.append(result)

                # Log iteration
                if self.logger:
                    self.logger.iteration(
                        iteration=i,
                        step=step,
                        success=result.success,
                        expert_used=result.expert_used,
                        tools_called=[tc["name"] for tc in result.tool_calls],
                        thinking_used=thinking_used,
                        output=result.output,
                        error=result.error,
                        duration=result.duration_seconds,
                        benchmark_id=benchmark_id,
                    )

                if self.on_iteration:
                    self.on_iteration(result)

                # Update context with result
                self.context[f"step_{step_index}_result"] = {
                    "step": step,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                }

                # Reflect periodically
                if (i + 1) % self.config.reflection_interval == 0:
                    self.current_state = LoopState.REFLECTING
                    reflection = await self._reflect(task)
                    self.context["reflection"] = reflection

                    # Log reflection
                    if self.logger:
                        self.logger.reflection(
                            progress=reflection.get("progress_percent", 0),
                            successful=reflection.get("successful_strategies", []),
                            failed=reflection.get("failed_strategies", []),
                            backtrack=reflection.get("should_backtrack", False),
                            next_step=reflection.get("next_step", ""),
                            benchmark_id=benchmark_id,
                            iteration=i,
                        )

                    # Check if we should backtrack
                    if reflection.get("should_backtrack", False):
                        if self.config.backtrack_on_failure:
                            await self._backtrack(reflection)
                            if self.metrics:
                                self.metrics.record_backtrack()

                # Check for completion
                if result.success and step_index == len(plan.steps) - 1:
                    self.current_state = LoopState.COMPLETED
                    break

            # Determine final success
            success = (
                self.current_state == LoopState.COMPLETED
                or (
                    self.iteration_results
                    and self.iteration_results[-1].success
                )
            )

            total_duration = (datetime.now() - start_time).total_seconds()

            # Record benchmark result in metrics
            if self.metrics and benchmark_id:
                self.metrics.record_benchmark_result(
                    benchmark_id=benchmark_id,
                    success=success,
                    iterations=len(self.iteration_results),
                    duration_seconds=total_duration,
                )

            if self.logger:
                status = "SUCCESS" if success else "FAILED"
                self.logger.info(
                    f"Task {status} after {len(self.iteration_results)} iterations ({total_duration:.2f}s)",
                    benchmark_id=benchmark_id,
                )

            return LoopResult(
                task=task,
                success=success,
                iterations=self.iteration_results,
                total_duration_seconds=total_duration,
                final_output=self._get_final_output(),
                sandbox_id=self.current_sandbox_id,
                artifacts=self._collect_artifacts(),
            )

        except Exception as e:
            self.current_state = LoopState.FAILED
            total_duration = (datetime.now() - start_time).total_seconds()

            if self.logger:
                self.logger.error(f"Loop failed: {e}", benchmark_id=benchmark_id)

            return LoopResult(
                task=task,
                success=False,
                iterations=self.iteration_results,
                total_duration_seconds=total_duration,
                final_output=f"Loop failed with error: {e}",
                sandbox_id=self.current_sandbox_id,
            )

    async def _execute_step(
        self,
        iteration: int,
        step: str,
        plan: TaskPlan,
    ) -> IterationResult:
        """Execute a single step in the plan."""
        result = IterationResult(
            iteration=iteration,
            state=LoopState.EXECUTING,
            step=step,
        )

        try:
            # Get orchestrator response
            response = await self.orchestrator.execute_step(step, self.context)

            # Handle tool calls
            if response.tool_calls:
                result.tool_calls = [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ]

                if self.tool_executor:
                    for tc in response.tool_calls:
                        tool_start = time.time()
                        tool_result = await self.tool_executor.execute(
                            tc.name, tc.arguments
                        )
                        tool_duration_ms = (time.time() - tool_start) * 1000

                        self.context[f"tool_{tc.name}"] = tool_result

                        # Log tool call
                        if self.logger:
                            self.logger.tool_call(
                                tool_name=tc.name,
                                arguments=tc.arguments,
                                success=tool_result.get("success", False),
                                result=tool_result,
                                error=tool_result.get("error"),
                                duration_ms=tool_duration_ms,
                                benchmark_id=self.current_benchmark_id,
                                iteration=iteration,
                            )

                        if not tool_result.get("success", False):
                            result.error = tool_result.get("error")

            # Handle expert routing
            if response.expert_recommendation:
                result.expert_used = response.expert_recommendation
                self.current_state = LoopState.ROUTING

                # Get routing confidence from orchestrator
                routing_confidence = 0.8  # Higher default since orchestrator explicitly chose
                if hasattr(response, 'thinking') and response.thinking:
                    routing_confidence = response.thinking.confidence

                # Get expert prompt from response data (if available)
                expert_prompt = response.data.get("expert_prompt", "")
                expert_context = response.data.get("expert_context", "")

                # Build full prompt for expert
                if expert_prompt:
                    full_expert_prompt = expert_prompt
                    if expert_context:
                        full_expert_prompt = f"{expert_context}\n\n{expert_prompt}"
                else:
                    # Fallback to step-based prompt
                    full_expert_prompt = f"Task: {step}\n\nContext: {json.dumps(self.context, default=str)[:2000]}"

                # Log expert routing decision
                if self.logger:
                    self.logger.expert_routing(
                        expert=response.expert_recommendation,
                        confidence=routing_confidence,
                        query=expert_prompt or step,
                        reason=f"Orchestrator called route_to_expert({response.expert_recommendation})",
                        benchmark_id=self.current_benchmark_id,
                        iteration=iteration,
                    )

                expert_response = await self.expert_registry.generate(
                    response.expert_recommendation,
                    full_expert_prompt
                )
                self.context["expert_response"] = expert_response
                result.output = expert_response

            if not result.error:
                result.success = True
                result.output = result.output or response.text

        except Exception as e:
            result.success = False
            result.error = str(e)
            if self.logger:
                self.logger.error(
                    f"Step execution failed: {e}",
                    benchmark_id=self.current_benchmark_id,
                    iteration=iteration,
                )

        return result

    async def _apply_thinking(
        self,
        task: str,
        plan: TaskPlan,
    ) -> ThinkingResult:
        """Apply extended thinking to the problem."""
        # Construct thinking prompt with context
        problem = f"""Task: {task}

Current plan: {json.dumps(plan.steps)}

Previous results: {json.dumps([
    {"step": r.step, "success": r.success, "output": r.output[:200]}
    for r in self.iteration_results[-3:]  # Last 3 iterations
], default=str)}

What is the best approach to complete this task successfully?"""

        return await self.orchestrator.think_extended(
            problem,
            level=plan.thinking_budget,
            context=self.context,
        )

    async def _reflect(self, task: str) -> dict[str, Any]:
        """Reflect on progress and determine adjustments."""
        results = [
            {
                "iteration": r.iteration,
                "step": r.step,
                "success": r.success,
                "output": r.output[:200] if r.output else None,
                "error": r.error,
            }
            for r in self.iteration_results
        ]

        return await self.orchestrator.reflect(results, task)

    async def _backtrack(self, reflection: dict) -> None:
        """Backtrack based on reflection analysis."""
        # Find last successful step
        last_success = -1
        for i, result in enumerate(self.iteration_results):
            if result.success:
                last_success = i

        if last_success >= 0:
            # Reset context to state after last success
            # Remove context from failed steps
            for i in range(last_success + 1, len(self.iteration_results)):
                key = f"step_{i}_result"
                if key in self.context:
                    del self.context[key]

            self.context["backtracked_from"] = len(self.iteration_results)
            self.context["backtracked_to"] = last_success

    async def _create_sandbox(self) -> None:
        """Create a sandbox for code testing."""
        if not self.tool_executor:
            return

        result = await self.tool_executor.execute("create_sandbox", {})
        if result.get("success"):
            self.current_sandbox_id = result.get("sandbox_id")
            self.context["sandbox_id"] = self.current_sandbox_id
            self.context["sandbox_path"] = result.get("worktree_path")

    def _is_code_task(self, task: str, plan: TaskPlan) -> bool:
        """Determine if this task involves code changes."""
        code_keywords = [
            "fix", "implement", "write", "create", "modify", "patch",
            "todo", "bug", "refactor", "optimize", "code", "asm"
        ]
        task_lower = task.lower()
        return any(kw in task_lower for kw in code_keywords) or any(
            tool in ["apply_patch", "build_sandbox"]
            for tool in plan.tools_needed
        )

    def _get_next_step_index(self) -> int:
        """Get the index of the next step to execute."""
        # Count successful steps
        completed = sum(1 for r in self.iteration_results if r.success)

        # If we backtracked, use the backtrack point
        if "backtracked_to" in self.context:
            return self.context.get("backtracked_to", 0) + 1

        return completed

    def _get_final_output(self) -> str:
        """Compile the final output from all iterations."""
        outputs = []
        for result in self.iteration_results:
            if result.success and result.output:
                outputs.append(result.output)

        return "\n\n".join(outputs) if outputs else "No output generated"

    def _collect_artifacts(self) -> dict[str, Any]:
        """Collect artifacts produced during the loop."""
        artifacts = {}

        # Collect tool results
        for key, value in self.context.items():
            if key.startswith("tool_"):
                artifacts[key] = value

        # Collect expert responses
        if "expert_response" in self.context:
            artifacts["expert_response"] = self.context["expert_response"]

        # Collect build results
        if "tool_build_sandbox" in self.context:
            build = self.context["tool_build_sandbox"]
            if build.get("success"):
                artifacts["rom_path"] = build.get("rom_path")
                artifacts["symbols_path"] = build.get("symbols_path")

        return artifacts


class EvaluationRunner:
    """
    Runs evaluation benchmarks through the agentic loop.

    Coordinates benchmark execution and result collection.
    Provides detailed logging and metrics for MoE analysis.
    """

    def __init__(
        self,
        loop: AgenticLoop | None = None,
        config: LoopConfig | None = None,
        logger: EvalLogger | None = None,
        log_file: str | None = None,
        console_output: bool = True,
    ):
        # Initialize logging
        self.logger = logger or EvalLogger(
            log_file=log_file,
            console=console_output,
        )
        self.metrics = MetricsCollector(session_id=self.logger.session_id)

        # Initialize loop with logging
        self.loop = loop or AgenticLoop(
            config=config,
            logger=self.logger,
            metrics_collector=self.metrics,
        )

        self.results: list[tuple[str, LoopResult]] = []

    async def run_benchmark(
        self,
        benchmark_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        category: str = "",
        difficulty: str = "",
    ) -> LoopResult:
        """Run a single benchmark case."""
        self.logger.info(f"Starting benchmark: {benchmark_id}")

        result = await self.loop.run(prompt, context, benchmark_id=benchmark_id)
        self.results.append((benchmark_id, result))

        # Update metrics with category/difficulty info
        if benchmark_id in self.metrics.metrics.benchmark_metrics:
            bm = self.metrics.metrics.benchmark_metrics[benchmark_id]
            bm.category = category
            bm.difficulty = difficulty

        return result

    async def run_benchmarks(
        self,
        benchmarks: list[tuple[str, str, str, str]],  # (id, prompt, category, difficulty)
        concurrency: int = 1,
    ) -> list[tuple[str, LoopResult]]:
        """
        Run multiple benchmarks with optional concurrency.

        Args:
            benchmarks: List of (benchmark_id, prompt, category, difficulty) tuples
            concurrency: Number of concurrent benchmark runs

        Returns:
            List of (benchmark_id, LoopResult) tuples
        """
        self.logger.info(f"Running {len(benchmarks)} benchmarks (concurrency={concurrency})")

        if concurrency == 1:
            # Sequential execution
            for item in benchmarks:
                if len(item) == 2:
                    benchmark_id, prompt = item
                    category, difficulty = "", ""
                else:
                    benchmark_id, prompt, category, difficulty = item
                await self.run_benchmark(benchmark_id, prompt, category=category, difficulty=difficulty)
        else:
            # Concurrent execution (limited)
            semaphore = asyncio.Semaphore(concurrency)

            async def run_with_limit(bid: str, prompt: str, cat: str = "", diff: str = ""):
                async with semaphore:
                    return await self.run_benchmark(bid, prompt, category=cat, difficulty=diff)

            await asyncio.gather(*[
                run_with_limit(
                    item[0], item[1],
                    item[2] if len(item) > 2 else "",
                    item[3] if len(item) > 3 else ""
                )
                for item in benchmarks
            ])

        return self.results

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics of evaluation results."""
        if not self.results:
            return {"total": 0, "success_rate": 0.0}

        successes = sum(1 for _, r in self.results if r.success)
        total = len(self.results)

        return {
            "total": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": successes / total if total > 0 else 0.0,
            "avg_iterations": sum(
                len(r.iterations) for _, r in self.results
            ) / total,
            "avg_duration": sum(
                r.total_duration_seconds for _, r in self.results
            ) / total,
        }

    def get_metrics(self) -> "EvalMetrics":
        """Get detailed metrics from the evaluation."""
        return self.metrics.finalize()

    def print_summary(self) -> None:
        """Print evaluation summary to console."""
        self.logger.print_summary()

    def print_metrics_report(self) -> None:
        """Print detailed metrics report."""
        self.metrics.print_report()

    def save_metrics(self, path: str) -> None:
        """Save metrics to JSON file."""
        self.metrics.save(path)

    def get_expert_analysis(self) -> dict[str, Any]:
        """Get MoE routing analysis."""
        metrics = self.metrics.finalize()
        return {
            "routing_distribution": metrics.routing_distribution,
            "avg_routing_confidence": metrics.avg_routing_confidence,
            "low_confidence_routes": metrics.low_confidence_routes,
            "expert_success_rates": {
                name: em.success_rate
                for name, em in metrics.expert_metrics.items()
            },
            "expert_call_counts": {
                name: em.total_calls
                for name, em in metrics.expert_metrics.items()
            },
        }

    def close(self) -> None:
        """Close the logger and cleanup."""
        self.logger.close()
