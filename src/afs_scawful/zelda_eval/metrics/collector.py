"""
Metrics collection and aggregation for evaluation analysis.

Provides:
- Per-expert performance metrics
- Per-tool success rates
- MoE routing analysis
- Benchmark difficulty calibration
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .logger import EvalEvent, ExpertRoutingEvent, ToolCallEvent, ThinkingEvent, IterationEvent


@dataclass
class ExpertMetrics:
    """Metrics for a single expert model."""
    name: str
    total_calls: int = 0
    avg_confidence: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_response_time_ms: float = 0.0
    routing_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total > 0 else 0.0


@dataclass
class ToolMetrics:
    """Metrics for a single tool."""
    name: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    avg_duration_ms: float = 0.0
    error_types: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_calls if self.total_calls > 0 else 0.0


@dataclass
class BenchmarkMetrics:
    """Metrics for a single benchmark."""
    benchmark_id: str
    category: str = ""
    difficulty: str = ""
    attempts: int = 0
    successes: int = 0
    avg_iterations: float = 0.0
    avg_duration_seconds: float = 0.0
    experts_used: dict[str, int] = field(default_factory=dict)
    tools_used: dict[str, int] = field(default_factory=dict)
    thinking_used_count: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts > 0 else 0.0


@dataclass
class EvalMetrics:
    """Aggregated metrics for an evaluation session."""
    session_id: str
    start_time: str
    end_time: str | None = None

    # Totals
    total_benchmarks: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_iterations: int = 0
    total_tool_calls: int = 0
    total_expert_calls: int = 0
    total_thinking_uses: int = 0
    total_backtracks: int = 0

    # Per-entity metrics
    expert_metrics: dict[str, ExpertMetrics] = field(default_factory=dict)
    tool_metrics: dict[str, ToolMetrics] = field(default_factory=dict)
    benchmark_metrics: dict[str, BenchmarkMetrics] = field(default_factory=dict)

    # MoE analysis
    routing_distribution: dict[str, float] = field(default_factory=dict)
    avg_routing_confidence: float = 0.0
    low_confidence_routes: int = 0  # Routes with confidence < 0.5

    @property
    def overall_success_rate(self) -> float:
        total = self.total_successes + self.total_failures
        return self.total_successes / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "totals": {
                "benchmarks": self.total_benchmarks,
                "successes": self.total_successes,
                "failures": self.total_failures,
                "iterations": self.total_iterations,
                "tool_calls": self.total_tool_calls,
                "expert_calls": self.total_expert_calls,
                "thinking_uses": self.total_thinking_uses,
                "backtracks": self.total_backtracks,
                "success_rate": self.overall_success_rate,
            },
            "moe_analysis": {
                "routing_distribution": self.routing_distribution,
                "avg_routing_confidence": self.avg_routing_confidence,
                "low_confidence_routes": self.low_confidence_routes,
            },
            "expert_metrics": {k: asdict(v) for k, v in self.expert_metrics.items()},
            "tool_metrics": {k: asdict(v) for k, v in self.tool_metrics.items()},
            "benchmark_metrics": {k: asdict(v) for k, v in self.benchmark_metrics.items()},
        }
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class MetricsCollector:
    """
    Collects and aggregates metrics from evaluation events.

    Use as a handler for EvalLogger to automatically collect metrics.
    """

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.metrics = EvalMetrics(
            session_id=self.session_id,
            start_time=datetime.now().isoformat(),
        )
        self._routing_confidences: list[float] = []
        self._current_benchmark: str | None = None
        self._benchmark_iterations: dict[str, list[float]] = {}
        self._benchmark_durations: dict[str, list[float]] = {}

    def __call__(self, event: EvalEvent) -> None:
        """Handle an event (for use as EvalLogger handler)."""
        self.process_event(event)

    def process_event(self, event: EvalEvent) -> None:
        """Process an evaluation event and update metrics."""
        if event.benchmark_id:
            self._current_benchmark = event.benchmark_id

        if isinstance(event, ExpertRoutingEvent):
            self._process_expert_routing(event)
        elif isinstance(event, ToolCallEvent):
            self._process_tool_call(event)
        elif isinstance(event, ThinkingEvent):
            self._process_thinking(event)
        elif isinstance(event, IterationEvent):
            self._process_iteration(event)

    def _process_expert_routing(self, event: ExpertRoutingEvent) -> None:
        """Process expert routing event."""
        expert = event.expert_chosen
        self.metrics.total_expert_calls += 1

        # Initialize expert metrics if needed
        if expert not in self.metrics.expert_metrics:
            self.metrics.expert_metrics[expert] = ExpertMetrics(name=expert)

        em = self.metrics.expert_metrics[expert]
        em.total_calls += 1

        # Update confidence tracking
        self._routing_confidences.append(event.confidence)
        if event.confidence < 0.5:
            self.metrics.low_confidence_routes += 1

        # Track routing reasons
        if event.routing_reason:
            reason = event.routing_reason[:50]  # Truncate for grouping
            em.routing_reasons[reason] = em.routing_reasons.get(reason, 0) + 1

        # Update benchmark metrics
        if self._current_benchmark:
            bm = self._get_benchmark_metrics(self._current_benchmark)
            bm.experts_used[expert] = bm.experts_used.get(expert, 0) + 1

    def _process_tool_call(self, event: ToolCallEvent) -> None:
        """Process tool call event."""
        tool = event.tool_name
        self.metrics.total_tool_calls += 1

        # Initialize tool metrics if needed
        if tool not in self.metrics.tool_metrics:
            self.metrics.tool_metrics[tool] = ToolMetrics(name=tool)

        tm = self.metrics.tool_metrics[tool]
        tm.total_calls += 1
        if event.success:
            tm.successes += 1
        else:
            tm.failures += 1
            if event.error:
                error_type = event.error.split(":")[0][:30]  # Truncate for grouping
                tm.error_types[error_type] = tm.error_types.get(error_type, 0) + 1

        # Update duration tracking
        if event.duration_ms > 0:
            # Running average
            tm.avg_duration_ms = (
                (tm.avg_duration_ms * (tm.total_calls - 1) + event.duration_ms) / tm.total_calls
            )

        # Update benchmark metrics
        if self._current_benchmark:
            bm = self._get_benchmark_metrics(self._current_benchmark)
            bm.tools_used[tool] = bm.tools_used.get(tool, 0) + 1

    def _process_thinking(self, event: ThinkingEvent) -> None:
        """Process thinking event."""
        self.metrics.total_thinking_uses += 1

        # Update benchmark metrics
        if self._current_benchmark:
            bm = self._get_benchmark_metrics(self._current_benchmark)
            bm.thinking_used_count += 1

    def _process_iteration(self, event: IterationEvent) -> None:
        """Process iteration event."""
        self.metrics.total_iterations += 1

        # Track expert success/failure
        if event.expert_used and event.expert_used in self.metrics.expert_metrics:
            em = self.metrics.expert_metrics[event.expert_used]
            if event.success:
                em.tasks_completed += 1
            else:
                em.tasks_failed += 1

        # Track benchmark iterations
        if self._current_benchmark:
            if self._current_benchmark not in self._benchmark_iterations:
                self._benchmark_iterations[self._current_benchmark] = []
            self._benchmark_iterations[self._current_benchmark].append(event.iteration)

            if event.duration_seconds > 0:
                if self._current_benchmark not in self._benchmark_durations:
                    self._benchmark_durations[self._current_benchmark] = []
                self._benchmark_durations[self._current_benchmark].append(event.duration_seconds)

    def _get_benchmark_metrics(self, benchmark_id: str) -> BenchmarkMetrics:
        """Get or create benchmark metrics."""
        if benchmark_id not in self.metrics.benchmark_metrics:
            self.metrics.benchmark_metrics[benchmark_id] = BenchmarkMetrics(
                benchmark_id=benchmark_id
            )
        return self.metrics.benchmark_metrics[benchmark_id]

    def record_benchmark_result(
        self,
        benchmark_id: str,
        success: bool,
        iterations: int,
        duration_seconds: float,
        category: str = "",
        difficulty: str = "",
    ) -> None:
        """Record final result for a benchmark."""
        bm = self._get_benchmark_metrics(benchmark_id)
        bm.category = category
        bm.difficulty = difficulty
        bm.attempts += 1

        if success:
            bm.successes += 1
            self.metrics.total_successes += 1
        else:
            self.metrics.total_failures += 1

        self.metrics.total_benchmarks += 1

        # Update averages
        bm.avg_iterations = (
            (bm.avg_iterations * (bm.attempts - 1) + iterations) / bm.attempts
        )
        bm.avg_duration_seconds = (
            (bm.avg_duration_seconds * (bm.attempts - 1) + duration_seconds) / bm.attempts
        )

    def record_backtrack(self) -> None:
        """Record a backtrack event."""
        self.metrics.total_backtracks += 1

    def finalize(self) -> EvalMetrics:
        """Finalize metrics and compute aggregates."""
        self.metrics.end_time = datetime.now().isoformat()

        # Compute routing distribution
        if self.metrics.total_expert_calls > 0:
            for expert, em in self.metrics.expert_metrics.items():
                self.metrics.routing_distribution[expert] = (
                    em.total_calls / self.metrics.total_expert_calls
                )

        # Compute average routing confidence
        if self._routing_confidences:
            self.metrics.avg_routing_confidence = (
                sum(self._routing_confidences) / len(self._routing_confidences)
            )

        # Compute expert average confidences
        # (This would require tracking per-expert confidences, simplified here)

        return self.metrics

    def save(self, path: Path | str) -> None:
        """Save metrics to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.finalize().to_json())

    def print_report(self) -> None:
        """Print a detailed metrics report."""
        m = self.finalize()

        print("\n" + "=" * 60)
        print("ZELDA EVALUATION METRICS REPORT")
        print("=" * 60)
        print(f"Session: {m.session_id}")
        print(f"Duration: {m.start_time} → {m.end_time}")

        print("\n--- OVERALL ---")
        print(f"Benchmarks: {m.total_benchmarks}")
        print(f"Success rate: {m.overall_success_rate:.1%} ({m.total_successes}/{m.total_benchmarks})")
        print(f"Total iterations: {m.total_iterations}")
        print(f"Backtracks: {m.total_backtracks}")

        print("\n--- MoE ROUTING ---")
        print(f"Total expert calls: {m.total_expert_calls}")
        print(f"Avg routing confidence: {m.avg_routing_confidence:.1%}")
        print(f"Low confidence routes (<50%): {m.low_confidence_routes}")
        print("\nDistribution:")
        for expert, pct in sorted(m.routing_distribution.items(), key=lambda x: -x[1]):
            calls = m.expert_metrics[expert].total_calls if expert in m.expert_metrics else 0
            success = m.expert_metrics[expert].success_rate if expert in m.expert_metrics else 0
            print(f"  {expert:10} {pct:6.1%} ({calls} calls, {success:.0%} success)")

        print("\n--- TOOL USAGE ---")
        print(f"Total tool calls: {m.total_tool_calls}")
        for tool, tm in sorted(m.tool_metrics.items(), key=lambda x: -x[1].total_calls):
            print(f"  {tool:25} {tm.total_calls:4} calls, {tm.success_rate:.0%} success, {tm.avg_duration_ms:.0f}ms avg")
            if tm.error_types:
                for err, count in list(tm.error_types.items())[:2]:
                    print(f"      └─ {err}: {count}")

        print("\n--- THINKING ---")
        print(f"Extended thinking used: {m.total_thinking_uses} times")

        if m.benchmark_metrics:
            print("\n--- BENCHMARK BREAKDOWN ---")
            # Group by category
            by_category: dict[str, list[BenchmarkMetrics]] = {}
            for bm in m.benchmark_metrics.values():
                cat = bm.category or "uncategorized"
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(bm)

            for category, benchmarks in sorted(by_category.items()):
                successes = sum(b.successes for b in benchmarks)
                attempts = sum(b.attempts for b in benchmarks)
                rate = successes / attempts if attempts > 0 else 0
                print(f"\n  {category}: {rate:.0%} ({successes}/{attempts})")
                for bm in sorted(benchmarks, key=lambda x: -x.success_rate)[:5]:
                    status = "✓" if bm.success_rate > 0.5 else "✗"
                    print(f"    {status} {bm.benchmark_id[:40]:40} {bm.success_rate:.0%} ({bm.avg_iterations:.1f} iters)")

        print("\n" + "=" * 60)
