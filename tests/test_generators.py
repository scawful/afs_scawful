from __future__ import annotations

from pathlib import Path

from afs_scawful.generators import DocSectionConfig, DocSectionGenerator


def test_doc_section_generator_basic(tmp_path: Path) -> None:
    doc_path = tmp_path / "guide.md"
    doc_path.write_text(
        "# Intro\n\nThis is a short intro section.\n\n# Details\n\nMore details here.\n",
        encoding="utf-8",
    )

    config = DocSectionConfig(min_chars=10, max_chars=200)
    generator = DocSectionGenerator(resource_roots=[tmp_path], config=config)
    result = generator.generate()

    assert result.samples
    assert result.samples[0].domain == "docs"
