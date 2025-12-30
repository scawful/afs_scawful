from __future__ import annotations

from pathlib import Path

from afs_scawful.research import build_research_catalog, extract_abstract_excerpt


def test_extract_abstract_excerpt() -> None:
    text = "Title\nAbstract\nThis is the abstract.\n1 Introduction\nBody"
    assert extract_abstract_excerpt(text, max_chars=200) == "This is the abstract."


def test_build_research_catalog_regex(tmp_path: Path) -> None:
    research_root = tmp_path / "Research"
    research_root.mkdir()
    pdf_path = research_root / "paper.pdf"
    pdf_path.write_bytes(
        b"not a real pdf /Title (Test Paper) /Author (Jane Doe)",
    )

    catalog = build_research_catalog(research_root, include_abstract=False)
    assert catalog["count"] == 1
    entry = catalog["papers"][0]
    assert entry["title"] == "Test Paper"
    assert entry["author"] == "Jane Doe"
    assert entry["metadata_source"] == "regex"
