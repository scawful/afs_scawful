"""Generate training samples from documentation sections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..resource_index import ResourceIndexer
from ..training import TrainingSample
from .base import BaseGenerator, GenerationResult


@dataclass
class DocSectionConfig:
    min_chars: int = 120
    max_chars: int = 2000
    file_globs: tuple[str, ...] = ("**/*.md", "**/*.txt")


class DocSectionGenerator(BaseGenerator):
    """Build training samples by extracting sections from docs."""

    def __init__(
        self,
        *,
        resource_index: Path | None = None,
        resource_roots: list[Path] | None = None,
        config: DocSectionConfig | None = None,
    ) -> None:
        super().__init__(name="DocSectionGenerator", domain="docs")
        self.resource_index = resource_index
        self.resource_roots = resource_roots
        self.config = config or DocSectionConfig()

    def generate(self) -> GenerationResult:
        result = GenerationResult()
        files = self._collect_files()
        for path in files:
            try:
                samples = self._samples_from_file(path)
                result.samples.extend(samples)
                if not samples:
                    result.skipped += 1
            except Exception as exc:
                result.errors.append(f"{path}: {exc}")
        return result

    def _collect_files(self) -> list[Path]:
        if self.resource_index:
            indexer = ResourceIndexer(index_path=self.resource_index)
            loaded = indexer.load_index()
            if loaded:
                return [item.path for item in loaded.files]

        indexer = ResourceIndexer(
            resource_roots=self.resource_roots,
            search_patterns=list(self.config.file_globs),
        )
        result = indexer.build_index()
        return [item.path for item in result.files]

    def _samples_from_file(self, path: Path) -> list[TrainingSample]:
        if not path.exists() or not path.is_file():
            return []
        text = path.read_text(encoding="utf-8", errors="ignore")
        sections = _split_sections(path, text)
        samples: list[TrainingSample] = []
        for heading, content in sections:
            content = content.strip()
            if len(content) < self.config.min_chars:
                continue
            if len(content) > self.config.max_chars:
                content = content[: self.config.max_chars].rstrip()
            instruction = f"Extract the documentation section '{heading}'."
            sample = TrainingSample(
                instruction=instruction,
                input=f"source: {path.name}",
                output=content,
                domain=self.domain,
                source=str(path),
                metadata={"heading": heading, "path": str(path)},
            )
            samples.append(sample)
        return samples


def _split_sections(path: Path, text: str) -> list[tuple[str, str]]:
    if path.suffix.lower() not in {".md", ".markdown"}:
        content = text.strip()
        if not content:
            return []
        return [(path.stem, content)]

    sections: list[tuple[str, str]] = []
    current_heading = path.stem
    buffer: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if buffer:
                sections.append((current_heading, "\n".join(buffer).strip()))
            current_heading = stripped.lstrip("#").strip() or current_heading
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        sections.append((current_heading, "\n".join(buffer).strip()))
    return sections
