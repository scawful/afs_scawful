"""Training sample data models for AFS Scawful."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TrainingSample:
    instruction: str
    input: str
    output: str
    domain: str
    source: str = ""
    sample_id: str = ""
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    kg_entities: list[str] = field(default_factory=list)
    kg_validated: bool = False

    def __post_init__(self) -> None:
        if not self.sample_id:
            self.sample_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
            "domain": self.domain,
            "source": self.source,
            "sample_id": self.sample_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "kg_entities": self.kg_entities,
            "kg_validated": self.kg_validated,
        }

    def to_jsonl_entry(self) -> str:
        payload = {
            "instruction": self.instruction,
            "output": self.output,
        }
        if self.input:
            payload["input"] = self.input
        payload["_metadata"] = {
            "sample_id": self.sample_id,
            "domain": self.domain,
            "source": self.source,
            "timestamp": self.timestamp,
        }
        return json.dumps(payload)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainingSample":
        return cls(
            instruction=data.get("instruction", ""),
            input=data.get("input", ""),
            output=data.get("output", ""),
            domain=data.get("domain", ""),
            source=data.get("source", ""),
            sample_id=data.get("sample_id", ""),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}) or {},
            kg_entities=data.get("kg_entities", []) or [],
            kg_validated=bool(data.get("kg_validated", False)),
        )
