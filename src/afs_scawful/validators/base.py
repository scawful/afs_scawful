"""Base validator interfaces for AFS Scawful."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..training import TrainingSample


@dataclass
class ValidationResult:
    valid: bool
    score: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "score": self.score,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "details": dict(self.details),
        }


class Validator(ABC):
    def __init__(self, name: str, domain: str) -> None:
        self.name = name
        self.domain = domain

    @abstractmethod
    async def validate(self, sample: TrainingSample) -> ValidationResult:
        raise NotImplementedError

    def can_validate(self, sample: TrainingSample) -> bool:
        return sample.domain == self.domain

    async def validate_batch(self, samples: list[TrainingSample]) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for sample in samples:
            if self.can_validate(sample):
                results.append(await self.validate(sample))
            else:
                results.append(
                    ValidationResult(
                        valid=True,
                        score=1.0,
                        warnings=[f"{self.name} skipped: domain mismatch"],
                    )
                )
        return results


class CompositeValidator(Validator):
    def __init__(self, validators: list[Validator]) -> None:
        super().__init__("CompositeValidator", "all")
        self.validators = validators

    def can_validate(self, sample: TrainingSample) -> bool:
        return any(validator.can_validate(sample) for validator in self.validators)

    async def validate(self, sample: TrainingSample) -> ValidationResult:
        applicable = [v for v in self.validators if v.can_validate(sample)]
        if not applicable:
            return ValidationResult(valid=True, score=1.0, warnings=["No applicable validators"])

        errors: list[str] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}
        scores: list[float] = []

        for validator in applicable:
            result = await validator.validate(sample)
            errors.extend(result.errors)
            warnings.extend(result.warnings)
            details[validator.name] = result.to_dict()
            scores.append(result.score)

        score = sum(scores) / len(scores) if scores else 1.0
        return ValidationResult(
            valid=len(errors) == 0,
            score=score,
            errors=errors,
            warnings=warnings,
            details=details,
        )
