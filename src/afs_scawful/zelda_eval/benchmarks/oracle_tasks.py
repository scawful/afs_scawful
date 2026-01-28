"""
Extract TODO/FIXME/HACK markers from Oracle-of-Secrets codebase
and convert them to benchmark cases.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterator

from .base import BenchmarkCase, BenchmarkCategory, BenchmarkSuite, Difficulty


@dataclass
class OracleTask:
    """A task extracted from Oracle-of-Secrets source."""

    file_path: str
    line_number: int
    marker: str  # TODO, FIXME, HACK, etc.
    text: str
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    task_type: str = "unknown"  # bug, feature, documentation, refactor

    @property
    def full_context(self) -> str:
        """Get the full context with line numbers."""
        lines = []
        start_line = self.line_number - len(self.context_before)

        for i, line in enumerate(self.context_before):
            lines.append(f"{start_line + i:4d}: {line}")

        lines.append(f"{self.line_number:4d}: ; {self.marker}: {self.text}")

        for i, line in enumerate(self.context_after):
            lines.append(f"{self.line_number + 1 + i:4d}: {line}")

        return "\n".join(lines)


class OracleTaskExtractor:
    """Extract tasks from Oracle-of-Secrets codebase."""

    ORACLE_PATH = Path("~/src/hobby/oracle-of-secrets").expanduser()

    # Patterns to match
    MARKER_PATTERN = re.compile(
        r";\s*(TODO|FIXME|HACK|XXX|BUG|NOTE)\s*:?\s*(.+)",
        re.IGNORECASE,
    )

    # Keywords to classify task type
    BUG_KEYWORDS = ["bug", "crash", "broken", "wrong", "error", "fix", "issue"]
    FEATURE_KEYWORDS = ["add", "implement", "new", "feature", "support"]
    DOC_KEYWORDS = ["document", "explain", "comment", "describe", "clarify"]
    REFACTOR_KEYWORDS = ["refactor", "cleanup", "reorganize", "simplify", "optimize"]

    def __init__(self, oracle_path: Path | None = None):
        self.oracle_path = oracle_path or self.ORACLE_PATH
        if not self.oracle_path.exists():
            raise FileNotFoundError(f"Oracle-of-Secrets not found at {self.oracle_path}")

    def extract_all(self, context_lines: int = 10) -> list[OracleTask]:
        """Extract all tasks from the codebase."""
        tasks = []
        for asm_file in self._find_asm_files():
            tasks.extend(self._extract_from_file(asm_file, context_lines))
        return tasks

    def _find_asm_files(self) -> Iterator[Path]:
        """Find all .asm files in the Oracle codebase."""
        for pattern in ["**/*.asm", "**/*.s", "**/*.inc"]:
            yield from self.oracle_path.glob(pattern)

    def _extract_from_file(self, file_path: Path, context_lines: int) -> list[OracleTask]:
        """Extract tasks from a single file."""
        tasks = []

        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return []

        for i, line in enumerate(lines):
            match = self.MARKER_PATTERN.search(line)
            if match:
                marker = match.group(1).upper()
                text = match.group(2).strip()

                # Get context
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)

                context_before = lines[start:i]
                context_after = lines[i + 1 : end]

                task = OracleTask(
                    file_path=str(file_path.relative_to(self.oracle_path)),
                    line_number=i + 1,  # 1-indexed
                    marker=marker,
                    text=text,
                    context_before=context_before,
                    context_after=context_after,
                    task_type=self._classify_task(text),
                )
                tasks.append(task)

        return tasks

    def _classify_task(self, text: str) -> str:
        """Classify a task based on its text."""
        text_lower = text.lower()

        if any(kw in text_lower for kw in self.BUG_KEYWORDS):
            return "bug"
        if any(kw in text_lower for kw in self.FEATURE_KEYWORDS):
            return "feature"
        if any(kw in text_lower for kw in self.DOC_KEYWORDS):
            return "documentation"
        if any(kw in text_lower for kw in self.REFACTOR_KEYWORDS):
            return "refactor"

        return "unknown"

    def to_benchmark_cases(
        self,
        tasks: list[OracleTask] | None = None,
        max_tasks: int | None = None,
    ) -> list[BenchmarkCase]:
        """Convert Oracle tasks to benchmark cases."""
        if tasks is None:
            tasks = self.extract_all()

        if max_tasks:
            tasks = tasks[:max_tasks]

        cases = []
        for task in tasks:
            # Determine category based on marker
            if task.marker in ("BUG", "FIXME"):
                category = BenchmarkCategory.ORACLE_BUGS
            else:
                category = BenchmarkCategory.ORACLE_TODOS

            # Determine difficulty based on context length and task type
            if task.task_type == "bug":
                difficulty = Difficulty.HARD
            elif task.task_type == "feature":
                difficulty = Difficulty.EXPERT
            elif task.task_type == "documentation":
                difficulty = Difficulty.EASY
            else:
                difficulty = Difficulty.MEDIUM

            # Build the prompt
            prompt = self._build_prompt(task)

            case = BenchmarkCase(
                id=f"oracle_{task.file_path.replace('/', '_')}_{task.line_number}",
                category=category,
                prompt=prompt,
                difficulty=difficulty,
                source_file=task.file_path,
                source_line=task.line_number,
                tags=[task.marker.lower(), task.task_type],
                metadata={
                    "original_text": task.text,
                    "marker": task.marker,
                },
            )
            cases.append(case)

        return cases

    def _build_prompt(self, task: OracleTask) -> str:
        """Build a prompt for a task."""
        task_description = {
            "bug": "Fix the following bug",
            "feature": "Implement the following feature",
            "documentation": "Document the following code",
            "refactor": "Refactor the following code",
            "unknown": "Address the following TODO",
        }.get(task.task_type, "Address the following TODO")

        return f"""{task_description} in Oracle-of-Secrets:

File: {task.file_path}
Line: {task.line_number}
{task.marker}: {task.text}

Context:
```asm
{task.full_context}
```

Provide your solution as 65816 assembly code that can be inserted or used to replace the relevant section."""


def get_oracle_suite(max_tasks: int | None = None) -> BenchmarkSuite:
    """Get a benchmark suite from Oracle-of-Secrets TODOs."""
    try:
        extractor = OracleTaskExtractor()
        tasks = extractor.extract_all()
        cases = extractor.to_benchmark_cases(tasks, max_tasks=max_tasks)

        return BenchmarkSuite(
            name="Oracle-of-Secrets Tasks",
            description=f"Real TODOs and bugs from the Oracle-of-Secrets ROM hack ({len(cases)} tasks)",
            cases=cases,
        )
    except FileNotFoundError as e:
        # Return empty suite if Oracle not found
        return BenchmarkSuite(
            name="Oracle-of-Secrets Tasks",
            description=f"Error: {e}",
            cases=[],
        )


def get_oracle_bugs_only() -> BenchmarkSuite:
    """Get only bug-related tasks."""
    suite = get_oracle_suite()
    bugs = suite.filter_by_category(BenchmarkCategory.ORACLE_BUGS)
    return BenchmarkSuite(
        name="Oracle-of-Secrets Bugs",
        description=f"Bug fixes from Oracle-of-Secrets ({len(bugs)} bugs)",
        cases=bugs,
    )
