from __future__ import annotations

from pathlib import Path

from afs_scawful.resource_index import ResourceIndexer


def test_resource_indexer_dedupes(tmp_path: Path) -> None:
    root = tmp_path / "resources"
    root.mkdir()

    (root / "a.txt").write_text("same\n", encoding="utf-8")
    (root / "b.txt").write_text("same\n", encoding="utf-8")
    (root / "c.md").write_text("diff\n", encoding="utf-8")

    indexer = ResourceIndexer(
        resource_roots=[root],
        search_patterns=["**/*.txt", "**/*.md"],
        exclude_patterns=[],
        index_path=tmp_path / "index.json",
    )

    result = indexer.build_index()
    assert result.total_files == 2
    assert result.duplicates_found == 1
    assert result.by_type.get("text", 0) == 1
    assert result.by_type.get("markdown", 0) == 1
