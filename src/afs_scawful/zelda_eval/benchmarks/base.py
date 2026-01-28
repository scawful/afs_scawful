"""
Base classes for Zelda model benchmarks.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from datetime import datetime


class BenchmarkCategory(Enum):
    """Categories of benchmark tests."""

    # Knowledge benchmarks
    KNOWLEDGE_65816 = "knowledge_65816"  # 65816 instruction set, addressing modes
    KNOWLEDGE_ALTTP = "knowledge_alttp"  # ALTTP memory map, routines, game state
    KNOWLEDGE_SNES = "knowledge_snes"  # SNES hardware (DMA, PPU, APU)

    # Task benchmarks
    ORACLE_TODOS = "oracle_todos"  # Real TODOs from Oracle-of-Secrets
    ORACLE_BUGS = "oracle_bugs"  # Known bugs to fix
    CODE_GENERATION = "code_generation"  # Write assembly routines
    CODE_OPTIMIZATION = "code_optimization"  # Optimize existing code
    DEBUGGING = "debugging"  # Find and fix bugs
    TOOL_CALLING = "tool_calling"  # MCP tool usage


class Difficulty(Enum):
    """Difficulty levels for benchmarks."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


@dataclass
class BenchmarkCase:
    """A single benchmark test case."""

    id: str
    category: BenchmarkCategory
    prompt: str
    difficulty: Difficulty = Difficulty.MEDIUM

    # Optional fields
    expected_output: str | None = None  # For exact match or LLM judge reference
    reference_files: list[str] = field(default_factory=list)  # Files for context
    tool_hints: list[str] = field(default_factory=list)  # MCP tools that might help
    tags: list[str] = field(default_factory=list)  # For filtering
    metadata: dict[str, Any] = field(default_factory=dict)  # Extra info

    # For Oracle tasks
    source_file: str | None = None  # Where the TODO came from
    source_line: int | None = None  # Line number in source

    def __post_init__(self):
        if isinstance(self.category, str):
            self.category = BenchmarkCategory(self.category)
        if isinstance(self.difficulty, str):
            self.difficulty = Difficulty(self.difficulty)


@dataclass
class BenchmarkResult:
    """Result of running a benchmark case."""

    case_id: str
    expert: str  # Which expert model was used
    success: bool
    response: str

    # Metrics
    syntax_valid: bool | None = None  # ASAR compilation success
    behavioral_pass: bool | None = None  # Emulator test pass
    quality_score: float | None = None  # LLM judge score (0-1)

    # Timing
    latency_ms: float = 0.0
    thinking_tokens: int = 0
    output_tokens: int = 0

    # Tool usage
    tools_called: list[str] = field(default_factory=list)
    iterations: int = 1

    # Errors
    error: str | None = None

    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BenchmarkSuite:
    """A collection of benchmark cases."""

    name: str
    description: str
    cases: list[BenchmarkCase] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.now)

    def filter_by_category(self, category: BenchmarkCategory) -> list[BenchmarkCase]:
        """Get cases matching a category."""
        return [c for c in self.cases if c.category == category]

    def filter_by_difficulty(self, difficulty: Difficulty) -> list[BenchmarkCase]:
        """Get cases matching a difficulty level."""
        return [c for c in self.cases if c.difficulty == difficulty]

    def filter_by_tags(self, tags: list[str]) -> list[BenchmarkCase]:
        """Get cases that have any of the specified tags."""
        tag_set = set(tags)
        return [c for c in self.cases if tag_set & set(c.tags)]

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self):
        return iter(self.cases)
