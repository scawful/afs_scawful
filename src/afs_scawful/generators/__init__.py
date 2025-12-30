"""Generator registry for AFS Scawful."""

from .base import BaseGenerator, GenerationResult, write_jsonl
from .doc_sections import DocSectionConfig, DocSectionGenerator

__all__ = [
    "BaseGenerator",
    "DocSectionConfig",
    "DocSectionGenerator",
    "GenerationResult",
    "write_jsonl",
]
