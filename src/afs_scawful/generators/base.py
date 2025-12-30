"""Generator base classes for AFS Scawful."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..training import TrainingSample


@dataclass
class GenerationResult:
    samples: list[TrainingSample] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, object]:
        return {
            "samples": [sample.to_dict() for sample in self.samples],
            "errors": list(self.errors),
            "skipped": self.skipped,
            "generated_at": self.generated_at,
        }


class BaseGenerator(ABC):
    def __init__(self, name: str, domain: str) -> None:
        self.name = name
        self.domain = domain

    @abstractmethod
    def generate(self) -> GenerationResult:
        raise NotImplementedError


def write_jsonl(samples: Iterable[TrainingSample], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [sample.to_jsonl_entry() for sample in samples]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
