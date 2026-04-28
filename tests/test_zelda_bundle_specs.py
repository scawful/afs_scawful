from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from afs_scawful.oracle_training.zelda_bundle_specs import (
    build_zelda_bundle,
    get_zelda_bundle_spec,
    validate_zelda_bundle_spec,
)


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_oracle_main_bundle_spec_builds_through_shared_bundle_core(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    training_root = tmp_path / "training"
    datasets_root = tmp_path / "datasets"

    _write(repo_root / "docs" / "VAST_SETUP.md")
    _write(repo_root / "docs" / "MODEL_PORTFOLIO.md")
    _write(repo_root / "docs" / "eval" / "ORACLE_EVAL_MATRIX_V1_20260415.md")
    _write(repo_root / "docs" / "eval" / "oracle_boundary_effort_matrix_v1.jsonl")
    _write(repo_root / "config" / "chat_registry.toml")
    _write(training_root / "scripts" / "train_switchhook_27b_vast.py")
    _write(training_root / "scripts" / "eval_iquest_zelda.py")
    _write(training_root / "scripts" / "summarize_switchhook_live_smoke.py")
    _write(training_root / "scripts" / "run_switchhook_live_eval_vast.sh")
    _write(training_root / "evals" / "switchhook_live_smoke_v1.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "train.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "val.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "metadata.json", "{}\n")

    spec = get_zelda_bundle_spec(
        "oracle_main_27b_v1",
        repo_root=repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )
    validated = validate_zelda_bundle_spec(
        "oracle_main_27b_v1",
        repo_root=repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )
    output = tmp_path / "oracle-main.tgz"
    included = build_zelda_bundle(
        "oracle_main_27b_v1",
        output,
        repo_root=repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )

    assert spec["required_paths"]
    assert "scripts/train_switchhook_27b_vast.py" in validated["all_paths"]
    assert "datasets/switchhook_27b_v1/train.jsonl" in included
    with tarfile.open(output, "r:gz") as archive:
        names = archive.getnames()
    assert "scripts/train_switchhook_27b_vast.py" in names
    assert "datasets/switchhook_27b_v1/metadata.json" in names
    assert "docs/VAST_SETUP.md" in names


def test_legacy_switchhook_bundle_alias_resolves_to_oracle_main(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    training_root = tmp_path / "training"
    datasets_root = tmp_path / "datasets"

    _write(repo_root / "docs" / "VAST_SETUP.md")
    _write(repo_root / "docs" / "MODEL_PORTFOLIO.md")
    _write(repo_root / "docs" / "eval" / "ORACLE_EVAL_MATRIX_V1_20260415.md")
    _write(repo_root / "docs" / "eval" / "oracle_boundary_effort_matrix_v1.jsonl")
    _write(repo_root / "config" / "chat_registry.toml")
    _write(training_root / "scripts" / "train_switchhook_27b_vast.py")
    _write(training_root / "scripts" / "eval_iquest_zelda.py")
    _write(training_root / "scripts" / "summarize_switchhook_live_smoke.py")
    _write(training_root / "evals" / "switchhook_live_smoke_v1.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "train.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "val.jsonl")
    _write(datasets_root / "switchhook_27b_v1" / "metadata.json", "{}\n")

    spec = get_zelda_bundle_spec(
        "switchhook_27b_v1",
        repo_root=repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )

    assert spec["required_paths"]


def test_zelda_16b_bundle_spec_requires_repo_owned_train_wrapper(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    training_root = tmp_path / "training"
    datasets_root = tmp_path / "datasets"

    _write(repo_root / "docs" / "ZELDA_16B_TRAINING_PLAN.md")
    _write(repo_root / "docs" / "VAST_SETUP.md")
    _write(repo_root / "docs" / "MODEL_PORTFOLIO.md")
    _write(repo_root / "scripts" / "dataset_qa_summary.py")
    _write(repo_root / "scripts" / "train_zelda_16b_v1.py")
    _write(training_root / "scripts" / "eval_iquest_zelda.py")
    _write(training_root / "evals" / "iquest_zelda_golden_v1.jsonl")
    _write(datasets_root / "zelda_16b_mix_v1" / "train.jsonl")
    _write(datasets_root / "zelda_16b_mix_v1" / "val.jsonl")
    _write(datasets_root / "zelda_16b_mix_v1" / "metadata.json", "{}\n")

    validated = validate_zelda_bundle_spec(
        "zelda_16b_v1",
        repo_root=repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )

    assert "scripts/train_zelda_16b_v1.py" in validated["all_paths"]
    assert "evals/iquest_zelda_golden_v1.jsonl" in validated["all_paths"]
    assert "datasets/zelda_16b_mix_v1/train.jsonl" in validated["all_paths"]


@pytest.mark.parametrize(
    ("track_name", "persona"),
    [
        ("din_qwen35_thinker_v1", "din"),
        ("nayru_qwen35_thinker_v1", "nayru"),
        ("farore_qwen35_thinker_v1", "farore"),
    ],
)
def test_qwen35_thinker_bundle_spec_uses_shared_wrapper_and_dataset_convention(
    tmp_path: Path,
    track_name: str,
    persona: str,
) -> None:
    repo_root = tmp_path / "repo"
    training_root = tmp_path / "training"
    datasets_root = tmp_path / "datasets"

    _write(repo_root / "docs" / "VAST_SETUP.md")
    _write(repo_root / "docs" / "MODEL_PORTFOLIO.md")
    _write(repo_root / "config" / "chat_registry.toml")
    _write(repo_root / "scripts" / "train_oracle_qwen35_thinker.py")
    _write(training_root / "scripts" / "eval_iquest_zelda.py")
    _write(training_root / "evals" / "iquest_zelda_golden_v1.jsonl")
    _write(datasets_root / "oracle_qwen35_thinkers" / persona / "train.jsonl")
    _write(datasets_root / "oracle_qwen35_thinkers" / persona / "val.jsonl")
    _write(datasets_root / "oracle_qwen35_thinkers" / persona / "metadata.json", "{}\n")

    validated = validate_zelda_bundle_spec(
        track_name,
        repo_root=repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )
    output = tmp_path / f"{persona}-thinker.tgz"
    build_zelda_bundle(
        track_name,
        output,
        repo_root=repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )

    assert "scripts/train_oracle_qwen35_thinker.py" in validated["all_paths"]
    assert f"datasets/oracle_qwen35_thinkers/{persona}/train.jsonl" in validated["all_paths"]
    with tarfile.open(output, "r:gz") as archive:
        names = archive.getnames()
    assert "scripts/train_oracle_qwen35_thinker.py" in names
    assert f"datasets/oracle_qwen35_thinkers/{persona}/metadata.json" in names


def test_unknown_zelda_bundle_spec_raises() -> None:
    with pytest.raises(KeyError):
        get_zelda_bundle_spec("unknown-track")
