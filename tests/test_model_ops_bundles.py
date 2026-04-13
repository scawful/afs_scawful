from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from afs_scawful.model_ops.bundles import BundleSpecError, build_bundle, validate_bundle_paths


def test_validate_bundle_paths_requires_required_entries(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("hello\n", encoding="utf-8")

    selected = validate_bundle_paths(
        root,
        {
            "required_paths": ["README.md"],
            "optional_paths": ["missing.json"],
        },
    )

    assert selected["required_paths"] == ["README.md"]
    assert selected["optional_paths"] == []


def test_build_bundle_includes_required_and_present_optional_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "train.toml").write_text("epochs=1\n", encoding="utf-8")
    output = tmp_path / "bundle.tgz"

    included = build_bundle(
        root,
        output,
        {
            "required_paths": ["README.md"],
            "optional_paths": ["config/train.toml", "missing.json"],
        },
    )

    assert included == ["README.md", "config/train.toml"]
    with tarfile.open(output, "r:gz") as archive:
        names = archive.getnames()
    assert "README.md" in names
    assert "config/train.toml" in names


def test_build_bundle_supports_absolute_sources_with_custom_archive_names(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external.jsonl"
    external.write_text('{"text":"hi"}\n', encoding="utf-8")
    output = tmp_path / "bundle.tgz"

    included = build_bundle(
        root,
        output,
        {
            "required_paths": [
                {"path": external, "arcname": "datasets/external.jsonl"},
            ],
        },
    )

    assert included == ["datasets/external.jsonl"]
    with tarfile.open(output, "r:gz") as archive:
        assert "datasets/external.jsonl" in archive.getnames()


def test_build_bundle_raises_for_missing_required_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(BundleSpecError):
        build_bundle(root, tmp_path / "bundle.tgz", {"required_paths": ["README.md"]})
