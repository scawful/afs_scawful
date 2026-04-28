from __future__ import annotations

from pathlib import Path

from afs_scawful import paths


def test_resolve_training_paths_fall_back_when_configured_root_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fallback = tmp_path / "training"
    fallback.mkdir()
    (fallback / "datasets").mkdir()
    (fallback / "index").mkdir()

    missing = tmp_path / "missing-mount" / "afs_training"
    config_path = tmp_path / "training_paths.toml"
    config_path.write_text(
        "\n".join(
            [
                "[paths]",
                f'training_root = "{missing}"',
                f'datasets = "{missing / "datasets"}"',
                f'index_root = "{missing / "index"}"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "default_training_root", lambda: fallback)

    assert paths.resolve_training_root(config_path) == fallback
    assert paths.resolve_datasets_root(config_path) == fallback / "datasets"
    assert paths.resolve_index_root(config_path) == fallback / "index"


def test_resolve_training_paths_prefer_existing_configured_root(tmp_path: Path) -> None:
    configured = tmp_path / "afs_training"
    (configured / "datasets").mkdir(parents=True)
    (configured / "index").mkdir()
    config_path = tmp_path / "training_paths.toml"
    config_path.write_text(
        "\n".join(
            [
                "[paths]",
                f'training_root = "{configured}"',
                f'datasets = "{configured / "datasets"}"',
                f'index_root = "{configured / "index"}"',
            ]
        ),
        encoding="utf-8",
    )

    assert paths.resolve_training_root(config_path) == configured
    assert paths.resolve_datasets_root(config_path) == configured / "datasets"
    assert paths.resolve_index_root(config_path) == configured / "index"
