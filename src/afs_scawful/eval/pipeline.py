"""Eval pipeline for end-to-end model evaluation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..integrations.ollama_client import ModelResponse, OllamaClient, Prompt
from ..integrations.google_genai_client import GoogleAIStudioClient, VertexAIClient
from ..training import TrainingSample
from ..validators import AsmValidator, ValidationResult
from ..validators.asar_validator_v2 import AsarValidatorV2
from .config import EvalConfig

logger = logging.getLogger(__name__)


# Patterns for detecting prompt category
_EXPLANATION_PATTERNS = [
    r"explain\s+(?:what|how|why)",
    r"what\s+(?:does|is)\s+(?:the\s+)?(?:address|memory|register)",
    r"describe\s+(?:the|how)",
    r"what\s+(?:is|are)\s+stored?\s+(?:in|at)",
    r"tell\s+me\s+about",
]
_CODE_PATTERNS = [
    r"write\s+(?:a\s+)?(?:65816|asm|assembly|routine|subroutine|function|code)",
    r"create\s+(?:a\s+)?(?:patch|hack|routine)",
    r"implement\s+(?:a\s+)?",
    r"fix\s+(?:the|this)\s+(?:bug|code|routine)",
    r"optimize\s+(?:the|this)",
]

_explanation_regexes = [re.compile(p, re.IGNORECASE) for p in _EXPLANATION_PATTERNS]
_code_regexes = [re.compile(p, re.IGNORECASE) for p in _CODE_PATTERNS]


def detect_category(prompt_text: str) -> str:
    """Auto-detect prompt category based on content."""
    # Check for explanation patterns first
    for pattern in _explanation_regexes:
        if pattern.search(prompt_text):
            return "explanation"

    # Check for code generation patterns
    for pattern in _code_regexes:
        if pattern.search(prompt_text):
            return "code_generation"

    # Default to code generation (requires validation)
    return "code_generation"


def validate_text_response(text: str) -> ValidationResult:
    """Validate a text/explanation response (no ASM validation)."""
    # Basic quality checks for explanation responses
    errors = []
    warnings = []
    score = 0.5

    # Check minimum length
    if len(text.strip()) < 20:
        errors.append("Response too short")
        score = 0.1
    elif len(text.strip()) < 50:
        warnings.append("Response is brief")
        score = 0.4
    else:
        score = 0.7

    # Check for substantive content (not just punctuation/whitespace)
    words = re.findall(r'\b[a-zA-Z]+\b', text)
    if len(words) < 5:
        errors.append("Response lacks substantive content")
        score = min(score, 0.2)
    elif len(words) >= 20:
        score = min(score + 0.2, 1.0)

    # Check for technical terms (ALTTP/65816 context)
    technical_terms = [
        r'\$[0-9A-Fa-f]{2,6}',  # hex addresses
        r'\b(?:LDA|STA|JMP|JSR|RTS|RTL)\b',  # opcodes
        r'\blink\b',  # game character
        r'\b(?:rupee|heart|sword|shield|item)\b',  # game items
        r'\b(?:WRAM|SRAM|ROM|bank)\b',  # memory terms
    ]
    tech_count = sum(1 for p in technical_terms if re.search(p, text, re.IGNORECASE))
    if tech_count >= 2:
        score = min(score + 0.1, 1.0)

    return ValidationResult(
        valid=len(errors) == 0,
        score=score,
        errors=errors,
        warnings=warnings,
        details={"word_count": len(words), "tech_term_count": tech_count},
    )


@dataclass
class EvalResult:
    """Result of evaluating a single prompt."""
    prompt: Prompt
    response: ModelResponse
    validation: ValidationResult
    category: str = ""

    @property
    def success(self) -> bool:
        return self.validation.valid and self.response.error is None

    @property
    def score(self) -> float:
        if self.response.error:
            return 0.0
        return self.validation.score

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": {
                "instruction": self.prompt.instruction,
                "input": self.prompt.input,
                "category": self.prompt.category,
            },
            "response": self.response.to_dict(),
            "validation": self.validation.to_dict(),
            "success": self.success,
            "score": self.score,
        }


@dataclass
class EvalReport:
    """Report of evaluation results."""
    config: EvalConfig
    results: list[EvalResult]
    start_time: datetime
    end_time: datetime
    model_name: str = ""

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @property
    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.response.latency_ms for r in self.results) / len(self.results)

    @property
    def avg_tokens_per_second(self) -> float:
        tps_values = [r.response.tokens_per_second for r in self.results if r.response.tokens_per_second > 0]
        return sum(tps_values) / len(tps_values) if tps_values else 0.0

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    def by_category(self) -> dict[str, list[EvalResult]]:
        """Group results by category."""
        categories: dict[str, list[EvalResult]] = {}
        for result in self.results:
            cat = result.category or "uncategorized"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(result)
        return categories

    def category_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics per category."""
        stats = {}
        for category, results in self.by_category().items():
            passed = sum(1 for r in results if r.success)
            scores = [r.score for r in results]
            stats[category] = {
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
                "pass_rate": passed / len(results) if results else 0.0,
                "avg_score": sum(scores) / len(scores) if scores else 0.0,
            }
        return stats

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "pass_rate": self.pass_rate,
                "avg_score": self.avg_score,
                "avg_latency_ms": self.avg_latency_ms,
                "avg_tokens_per_second": self.avg_tokens_per_second,
            },
            "by_category": self.category_stats(),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self, include_samples: bool = True, max_sample_length: int = 500) -> str:
        """Generate markdown report."""
        lines = [
            f"# Eval Report: {self.model_name}",
            "",
            f"**Generated:** {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Duration:** {self.duration_seconds:.1f}s",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Prompts | {self.total} |",
            f"| Passed | {self.passed} ({self.pass_rate:.1%}) |",
            f"| Failed | {self.failed} |",
            f"| Avg Score | {self.avg_score:.2f} |",
            f"| Avg Latency | {self.avg_latency_ms:.0f}ms |",
            f"| Avg Tokens/s | {self.avg_tokens_per_second:.1f} |",
            "",
        ]

        # Category breakdown
        cat_stats = self.category_stats()
        if len(cat_stats) > 1:
            lines.extend([
                "## By Category",
                "",
                "| Category | Total | Passed | Pass Rate | Avg Score |",
                "|----------|-------|--------|-----------|-----------|",
            ])
            for cat, stats in sorted(cat_stats.items()):
                lines.append(
                    f"| {cat} | {stats['total']} | {stats['passed']} | "
                    f"{stats['pass_rate']:.1%} | {stats['avg_score']:.2f} |"
                )
            lines.append("")

        # Failed samples
        failed = [r for r in self.results if not r.success]
        if failed and include_samples:
            lines.extend([
                "## Failed Samples",
                "",
            ])
            for i, result in enumerate(failed[:10], 1):
                prompt_text = result.prompt.instruction[:max_sample_length]
                if len(result.prompt.instruction) > max_sample_length:
                    prompt_text += "..."

                response_text = result.response.text[:max_sample_length]
                if len(result.response.text) > max_sample_length:
                    response_text += "..."

                lines.extend([
                    f"### {i}. {result.category or 'uncategorized'}",
                    "",
                    f"**Prompt:** {prompt_text}",
                    "",
                    f"**Response:**",
                    "```",
                    response_text,
                    "```",
                    "",
                    f"**Errors:** {', '.join(result.validation.errors[:3]) or 'None'}",
                    "",
                ])

        return "\n".join(lines)


class EvalPipeline:
    """End-to-end evaluation pipeline."""

    def __init__(self, config: EvalConfig | None = None):
        self.config = config or EvalConfig()
        self.client = self._build_client()
        self._init_validators()

    def _build_client(self):
        provider = self.config.model.provider
        if provider == "ollama":
            return OllamaClient(
                base_url=self.config.model.base_url,
                timeout=self.config.model.timeout_seconds,
            )
        if provider == "studio":
            return GoogleAIStudioClient(
                api_key_env=self.config.model.studio_api_key_env,
                timeout=self.config.model.timeout_seconds,
            )
        if provider == "vertex":
            return VertexAIClient(
                project=self.config.model.vertex_project,
                location=self.config.model.vertex_location,
                gcloud_path=self.config.model.gcloud_path,
                timeout=self.config.model.timeout_seconds,
            )
        raise ValueError(f"Unknown model provider: {provider}")

    def _init_validators(self) -> None:
        """Initialize validators based on config."""
        self.validators = []

        if self.config.validation.use_asm:
            self.validators.append(AsmValidator())

        if self.config.validation.use_asar_v2:
            self.validators.append(AsarValidatorV2(
                rom_type=self.config.validation.asar_rom_type,
                extract_symbols=self.config.validation.extract_symbols,
                semantic_analysis=self.config.validation.use_semantic,
            ))

    async def validate_response(
        self,
        response: ModelResponse,
        category: str = "",
    ) -> ValidationResult:
        """Validate a model response based on category."""
        if response.error:
            return ValidationResult(
                valid=False,
                score=0.0,
                errors=[f"Model error: {response.error}"],
            )

        # Check if this category should skip ASM validation
        skip_asm = category in self.config.validation.skip_asm_categories

        if skip_asm:
            # Use text-based validation for explanation/documentation
            result = validate_text_response(response.text)
            result.details["category"] = category
            result.details["validation_mode"] = "text"
            return result

        # Full ASM validation for code generation
        sample = TrainingSample(
            instruction="",
            input="",
            output=response.text,
            domain="asm",
        )

        # Run all validators and combine results
        all_errors: list[str] = []
        all_warnings: list[str] = []
        all_details: dict[str, Any] = {"category": category, "validation_mode": "asm"}
        scores: list[float] = []

        for validator in self.validators:
            if validator.can_validate(sample):
                result = await validator.validate(sample)
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)
                all_details[validator.name] = result.to_dict()
                scores.append(result.score)

        avg_score = sum(scores) / len(scores) if scores else 0.5

        return ValidationResult(
            valid=len(all_errors) == 0,
            score=avg_score,
            errors=all_errors,
            warnings=all_warnings,
            details=all_details,
        )

    async def eval_single(self, prompt: Prompt) -> EvalResult:
        """Evaluate a single prompt."""
        response = await self.client.generate(
            model=self.config.model.name,
            prompt=prompt.full_prompt,
            system=self.config.model.system_prompt,
            temperature=self.config.model.temperature,
            top_p=self.config.model.top_p,
            max_tokens=self.config.model.max_tokens,
        )

        # Use provided category or auto-detect from prompt
        category = prompt.category or detect_category(prompt.instruction)

        validation = await self.validate_response(response, category=category)

        return EvalResult(
            prompt=prompt,
            response=response,
            validation=validation,
            category=category,
        )

    async def eval_batch(
        self,
        prompts: list[Prompt],
        progress_callback: callable | None = None,
    ) -> EvalReport:
        """Evaluate a batch of prompts."""
        start_time = datetime.now()

        # Check model availability when listing is supported
        supports_listing = getattr(self.client, "supports_model_listing", False)
        if supports_listing:
            available = await self.client.list_models()
            if available and not await self.client.model_exists(self.config.model.name):
                raise RuntimeError(
                    f"Model '{self.config.model.name}' not found. "
                    f"Available: {', '.join(available) or 'none'}"
                )

        semaphore = asyncio.Semaphore(self.config.concurrency)
        completed = 0

        async def eval_with_progress(prompt: Prompt) -> EvalResult:
            nonlocal completed
            async with semaphore:
                result = await self.eval_single(prompt)
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(prompts), result)
                return result

        tasks = [eval_with_progress(p) for p in prompts]
        results = await asyncio.gather(*tasks)

        end_time = datetime.now()

        return EvalReport(
            config=self.config,
            results=list(results),
            start_time=start_time,
            end_time=end_time,
            model_name=self.config.model.name,
        )

    async def eval_interactive(self, prompt_text: str) -> EvalResult:
        """Run a single interactive evaluation with auto-category detection."""
        # Don't set category - let eval_single auto-detect from prompt text
        prompt = Prompt(instruction=prompt_text, category="")
        return await self.eval_single(prompt)

    async def eval_file(self, path: Path) -> EvalReport:
        """Evaluate prompts from a JSONL file."""
        prompts = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    prompts.append(Prompt(
                        instruction=data.get("instruction", data.get("prompt", "")),
                        input=data.get("input", ""),
                        category=data.get("category", ""),
                        expected_keywords=data.get("expected_keywords", []),
                    ))
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid JSON line: %s", line[:50])

        return await self.eval_batch(prompts)
