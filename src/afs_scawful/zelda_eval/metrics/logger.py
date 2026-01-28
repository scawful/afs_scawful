"""
Structured logging for Zelda evaluation system.

Captures detailed events for debugging and analysis:
- Expert routing decisions (MoE)
- Tool calls and results
- Extended thinking usage
- Iteration progress and outcomes
"""

import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TextIO


class LogLevel(Enum):
    """Log levels for evaluation events."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    METRIC = "metric"  # Special level for metrics/telemetry


@dataclass
class EvalEvent:
    """Base event for evaluation logging."""
    timestamp: str
    event_type: str
    session_id: str | None = None
    benchmark_id: str | None = None
    iteration: int | None = None
    level: str = "info"
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


@dataclass
class ExpertRoutingEvent(EvalEvent):
    """Event for expert routing decisions."""
    expert_chosen: str = ""
    confidence: float = 0.0
    query_preview: str = ""
    routing_reason: str = ""
    alternatives: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self):
        self.event_type = "expert_routing"


@dataclass
class ToolCallEvent(EvalEvent):
    """Event for tool call execution."""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    success: bool = False
    result_preview: str = ""
    error: str | None = None
    duration_ms: float = 0.0

    def __post_init__(self):
        self.event_type = "tool_call"


@dataclass
class ThinkingEvent(EvalEvent):
    """Event for extended thinking usage."""
    thinking_level: str = ""
    tokens_used: int = 0
    reasoning_preview: str = ""
    conclusions: list[str] = field(default_factory=list)
    confidence_before: float = 0.0
    confidence_after: float = 0.0

    def __post_init__(self):
        self.event_type = "thinking"


@dataclass
class IterationEvent(EvalEvent):
    """Event for iteration completion."""
    step: str = ""
    success: bool = False
    expert_used: str | None = None
    tools_called: list[str] = field(default_factory=list)
    thinking_used: bool = False
    output_preview: str = ""
    error: str | None = None
    duration_seconds: float = 0.0

    def __post_init__(self):
        self.event_type = "iteration"


@dataclass
class PlanEvent(EvalEvent):
    """Event for task planning."""
    task: str = ""
    steps: list[str] = field(default_factory=list)
    tools_needed: list[str] = field(default_factory=list)
    expert_hints: list[str] = field(default_factory=list)
    confidence: float = 0.0
    thinking_budget: str = ""

    def __post_init__(self):
        self.event_type = "plan"


@dataclass
class ReflectionEvent(EvalEvent):
    """Event for reflection/backtracking."""
    progress_percent: int = 0
    successful_strategies: list[str] = field(default_factory=list)
    failed_strategies: list[str] = field(default_factory=list)
    should_backtrack: bool = False
    next_step: str = ""
    backtrack_to: int | None = None

    def __post_init__(self):
        self.event_type = "reflection"


class EvalLogger:
    """
    Structured logger for evaluation events.

    Supports multiple output modes:
    - Console (colored, human-readable)
    - JSON file (structured, machine-readable)
    - Custom handlers (callbacks)
    """

    # ANSI colors for console output
    COLORS = {
        "debug": "\033[90m",     # Gray
        "info": "\033[0m",       # Default
        "warn": "\033[33m",      # Yellow
        "error": "\033[31m",     # Red
        "metric": "\033[36m",    # Cyan
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
    }

    # Symbols for event types
    SYMBOLS = {
        "expert_routing": "🎯",
        "tool_call": "🔧",
        "thinking": "💭",
        "iteration": "🔄",
        "plan": "📋",
        "reflection": "🪞",
        "default": "📝",
    }

    def __init__(
        self,
        session_id: str | None = None,
        log_file: Path | str | None = None,
        console: bool = True,
        json_output: bool = True,
        min_level: LogLevel = LogLevel.INFO,
        handlers: list[Callable[[EvalEvent], None]] | None = None,
    ):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.min_level = min_level
        self.console = console
        self.json_output = json_output
        self.handlers = handlers or []

        # Set up file output
        self.log_file: TextIO | None = None
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = open(log_path, "a")

        # Event history for analysis
        self.events: list[EvalEvent] = []

        # Counters for quick stats
        self.stats = {
            "expert_calls": {},      # expert_name -> count
            "tool_calls": {},        # tool_name -> {success: n, fail: n}
            "thinking_uses": 0,
            "iterations": 0,
            "successes": 0,
            "failures": 0,
            "backtrack_count": 0,
        }

    def _should_log(self, level: LogLevel) -> bool:
        """Check if event should be logged based on min level."""
        levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR, LogLevel.METRIC]
        return levels.index(level) >= levels.index(self.min_level)

    def _format_console(self, event: EvalEvent) -> str:
        """Format event for console output."""
        c = self.COLORS
        symbol = self.SYMBOLS.get(event.event_type, self.SYMBOLS["default"])
        level_color = c.get(event.level, c["info"])

        # Base format
        time_str = event.timestamp.split("T")[1][:8] if "T" in event.timestamp else event.timestamp
        header = f"{c['dim']}{time_str}{c['reset']} {symbol} "

        # Type-specific formatting
        if isinstance(event, ExpertRoutingEvent):
            conf_color = c["bold"] if event.confidence > 0.7 else c["warn"] if event.confidence > 0.4 else c["error"]
            return (
                f"{header}{c['bold']}Expert Routing{c['reset']}: "
                f"{event.expert_chosen} {conf_color}({event.confidence:.0%}){c['reset']}\n"
                f"    Query: {event.query_preview[:60]}...\n"
                f"    Reason: {event.routing_reason}"
            )

        elif isinstance(event, ToolCallEvent):
            status = f"{c['bold']}OK{c['reset']}" if event.success else f"{c['error']}FAIL{c['reset']}"
            result = f"\n    Result: {event.result_preview[:80]}..." if event.result_preview else ""
            error = f"\n    {c['error']}Error: {event.error}{c['reset']}" if event.error else ""
            return (
                f"{header}{c['bold']}Tool Call{c['reset']}: "
                f"{event.tool_name} [{status}] ({event.duration_ms:.0f}ms)"
                f"{result}{error}"
            )

        elif isinstance(event, ThinkingEvent):
            return (
                f"{header}{c['bold']}Extended Thinking{c['reset']} "
                f"({event.thinking_level}, {event.tokens_used} tokens)\n"
                f"    Confidence: {event.confidence_before:.0%} → {event.confidence_after:.0%}\n"
                f"    Conclusions: {', '.join(event.conclusions[:3])}"
            )

        elif isinstance(event, IterationEvent):
            status = f"{c['bold']}OK{c['reset']}" if event.success else f"{c['error']}FAIL{c['reset']}"
            expert = f" → {event.expert_used}" if event.expert_used else ""
            tools = f" [tools: {', '.join(event.tools_called)}]" if event.tools_called else ""
            thinking = " 💭" if event.thinking_used else ""
            error = f"\n    {c['error']}Error: {event.error}{c['reset']}" if event.error else ""
            return (
                f"{header}{c['bold']}Iteration {event.iteration}{c['reset']} [{status}] "
                f"({event.duration_seconds:.2f}s){expert}{tools}{thinking}\n"
                f"    Step: {event.step[:60]}...{error}"
            )

        elif isinstance(event, PlanEvent):
            return (
                f"{header}{c['bold']}Plan Created{c['reset']} "
                f"(confidence: {event.confidence:.0%}, thinking: {event.thinking_budget})\n"
                f"    Task: {event.task[:60]}...\n"
                f"    Steps: {len(event.steps)}, Tools: {event.tools_needed}, Experts: {event.expert_hints}"
            )

        elif isinstance(event, ReflectionEvent):
            backtrack = f" {c['warn']}→ BACKTRACK to {event.backtrack_to}{c['reset']}" if event.should_backtrack else ""
            return (
                f"{header}{c['bold']}Reflection{c['reset']} ({event.progress_percent}% complete){backtrack}\n"
                f"    ✓ Worked: {', '.join(event.successful_strategies[:2]) or 'none'}\n"
                f"    ✗ Failed: {', '.join(event.failed_strategies[:2]) or 'none'}\n"
                f"    Next: {event.next_step[:60]}..."
            )

        else:
            return f"{header}{level_color}{event.message}{c['reset']}"

    def log(self, event: EvalEvent) -> None:
        """Log an evaluation event."""
        # Set session ID if not set
        if not event.session_id:
            event.session_id = self.session_id

        # Set timestamp if not set
        if not event.timestamp:
            event.timestamp = datetime.now().isoformat()

        # Store event
        self.events.append(event)

        # Update stats
        self._update_stats(event)

        # Check level
        level = LogLevel(event.level) if isinstance(event.level, str) else event.level
        if not self._should_log(level):
            return

        # Console output
        if self.console:
            print(self._format_console(event))

        # JSON file output
        if self.log_file and self.json_output:
            self.log_file.write(event.to_json() + "\n")
            self.log_file.flush()

        # Custom handlers
        for handler in self.handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"Handler error: {e}", file=sys.stderr)

    def _update_stats(self, event: EvalEvent) -> None:
        """Update internal statistics based on event."""
        if isinstance(event, ExpertRoutingEvent):
            expert = event.expert_chosen
            self.stats["expert_calls"][expert] = self.stats["expert_calls"].get(expert, 0) + 1

        elif isinstance(event, ToolCallEvent):
            tool = event.tool_name
            if tool not in self.stats["tool_calls"]:
                self.stats["tool_calls"][tool] = {"success": 0, "fail": 0}
            key = "success" if event.success else "fail"
            self.stats["tool_calls"][tool][key] += 1

        elif isinstance(event, ThinkingEvent):
            self.stats["thinking_uses"] += 1

        elif isinstance(event, IterationEvent):
            self.stats["iterations"] += 1
            if event.success:
                self.stats["successes"] += 1
            else:
                self.stats["failures"] += 1

        elif isinstance(event, ReflectionEvent):
            if event.should_backtrack:
                self.stats["backtrack_count"] += 1

    # Convenience methods for common events
    def expert_routing(
        self,
        expert: str,
        confidence: float,
        query: str,
        reason: str = "",
        alternatives: list[tuple[str, float]] | None = None,
        benchmark_id: str | None = None,
        iteration: int | None = None,
    ) -> None:
        """Log an expert routing decision."""
        self.log(ExpertRoutingEvent(
            timestamp=datetime.now().isoformat(),
            event_type="expert_routing",
            benchmark_id=benchmark_id,
            iteration=iteration,
            expert_chosen=expert,
            confidence=confidence,
            query_preview=query[:200],
            routing_reason=reason,
            alternatives=alternatives or [],
        ))

    def tool_call(
        self,
        tool_name: str,
        arguments: dict,
        success: bool,
        result: Any = None,
        error: str | None = None,
        duration_ms: float = 0.0,
        benchmark_id: str | None = None,
        iteration: int | None = None,
    ) -> None:
        """Log a tool call."""
        result_preview = ""
        if result:
            result_str = str(result)
            result_preview = result_str[:200] if len(result_str) > 200 else result_str

        self.log(ToolCallEvent(
            timestamp=datetime.now().isoformat(),
            event_type="tool_call",
            benchmark_id=benchmark_id,
            iteration=iteration,
            level="info" if success else "error",
            tool_name=tool_name,
            arguments=arguments,
            success=success,
            result_preview=result_preview,
            error=error,
            duration_ms=duration_ms,
        ))

    def thinking(
        self,
        level: str,
        tokens: int,
        reasoning: str,
        conclusions: list[str],
        confidence_before: float,
        confidence_after: float,
        benchmark_id: str | None = None,
        iteration: int | None = None,
    ) -> None:
        """Log extended thinking usage."""
        self.log(ThinkingEvent(
            timestamp=datetime.now().isoformat(),
            event_type="thinking",
            benchmark_id=benchmark_id,
            iteration=iteration,
            thinking_level=level,
            tokens_used=tokens,
            reasoning_preview=reasoning[:300],
            conclusions=conclusions,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
        ))

    def iteration(
        self,
        iteration: int,
        step: str,
        success: bool,
        expert_used: str | None = None,
        tools_called: list[str] | None = None,
        thinking_used: bool = False,
        output: str = "",
        error: str | None = None,
        duration: float = 0.0,
        benchmark_id: str | None = None,
    ) -> None:
        """Log iteration completion."""
        self.log(IterationEvent(
            timestamp=datetime.now().isoformat(),
            event_type="iteration",
            benchmark_id=benchmark_id,
            iteration=iteration,
            level="info" if success else "error",
            step=step,
            success=success,
            expert_used=expert_used,
            tools_called=tools_called or [],
            thinking_used=thinking_used,
            output_preview=output[:200],
            error=error,
            duration_seconds=duration,
        ))

    def plan(
        self,
        task: str,
        steps: list[str],
        tools_needed: list[str],
        expert_hints: list[str],
        confidence: float,
        thinking_budget: str,
        benchmark_id: str | None = None,
    ) -> None:
        """Log task planning."""
        self.log(PlanEvent(
            timestamp=datetime.now().isoformat(),
            event_type="plan",
            benchmark_id=benchmark_id,
            task=task,
            steps=steps,
            tools_needed=tools_needed,
            expert_hints=expert_hints,
            confidence=confidence,
            thinking_budget=thinking_budget,
        ))

    def reflection(
        self,
        progress: int,
        successful: list[str],
        failed: list[str],
        backtrack: bool,
        next_step: str,
        backtrack_to: int | None = None,
        benchmark_id: str | None = None,
        iteration: int | None = None,
    ) -> None:
        """Log reflection event."""
        self.log(ReflectionEvent(
            timestamp=datetime.now().isoformat(),
            event_type="reflection",
            benchmark_id=benchmark_id,
            iteration=iteration,
            level="warn" if backtrack else "info",
            progress_percent=progress,
            successful_strategies=successful,
            failed_strategies=failed,
            should_backtrack=backtrack,
            next_step=next_step,
            backtrack_to=backtrack_to,
        ))

    def info(self, message: str, **kwargs) -> None:
        """Log an info message."""
        self.log(EvalEvent(
            timestamp=datetime.now().isoformat(),
            event_type="info",
            level="info",
            message=message,
            data=kwargs,
        ))

    def error(self, message: str, **kwargs) -> None:
        """Log an error message."""
        self.log(EvalEvent(
            timestamp=datetime.now().isoformat(),
            event_type="error",
            level="error",
            message=message,
            data=kwargs,
        ))

    def get_stats(self) -> dict:
        """Get current statistics."""
        return self.stats.copy()

    def get_expert_distribution(self) -> dict[str, int]:
        """Get distribution of expert calls."""
        return self.stats["expert_calls"].copy()

    def get_tool_success_rates(self) -> dict[str, float]:
        """Get success rate per tool."""
        rates = {}
        for tool, counts in self.stats["tool_calls"].items():
            total = counts["success"] + counts["fail"]
            rates[tool] = counts["success"] / total if total > 0 else 0.0
        return rates

    def print_summary(self) -> None:
        """Print a summary of the evaluation session."""
        c = self.COLORS
        print(f"\n{c['bold']}═══ Evaluation Summary ═══{c['reset']}")
        print(f"Session: {self.session_id}")
        print(f"Events logged: {len(self.events)}")

        print(f"\n{c['bold']}Iterations:{c['reset']}")
        total = self.stats["iterations"]
        if total > 0:
            rate = self.stats["successes"] / total
            print(f"  Total: {total}, Success: {self.stats['successes']}, Fail: {self.stats['failures']}")
            print(f"  Success rate: {rate:.1%}")
            print(f"  Backtracks: {self.stats['backtrack_count']}")

        print(f"\n{c['bold']}Expert Distribution:{c['reset']}")
        for expert, count in sorted(self.stats["expert_calls"].items(), key=lambda x: -x[1]):
            print(f"  {expert}: {count} calls")

        print(f"\n{c['bold']}Tool Usage:{c['reset']}")
        for tool, counts in sorted(self.stats["tool_calls"].items(), key=lambda x: -(x[1]["success"] + x[1]["fail"])):
            total = counts["success"] + counts["fail"]
            rate = counts["success"] / total if total > 0 else 0
            status = f"{c['bold']}{rate:.0%}{c['reset']}" if rate > 0.8 else f"{c['warn']}{rate:.0%}{c['reset']}"
            print(f"  {tool}: {total} calls ({status} success)")

        print(f"\n{c['bold']}Thinking:{c['reset']}")
        print(f"  Extended thinking used: {self.stats['thinking_uses']} times")

    def close(self) -> None:
        """Close the logger and any open files."""
        if self.log_file:
            self.log_file.close()
            self.log_file = None
