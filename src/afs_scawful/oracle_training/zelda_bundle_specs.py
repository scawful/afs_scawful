"""Bundle specs for Zelda/oracle training tracks."""

from __future__ import annotations

from pathlib import Path

from ..model_ops.bundles import BundleSelection, build_bundle, validate_bundle_paths
from ..paths import resolve_datasets_root, resolve_training_root
from .zelda_tracks import ORACLE_MAIN_TRACK_NAME, ORACLE_QWEN35_THINKER_PERSONAS, get_zelda_track_spec, resolve_zelda_track_name


REPO_ROOT = Path(__file__).resolve().parents[3]
BundleSpec = dict[str, list[object]]


def _repo_entry(path: str) -> str:
    return path


def _external_entry(path: Path, arcname: str) -> dict[str, str]:
    return {"path": str(path), "arcname": arcname}


def _oracle_main_bundle_spec(repo_root: Path, training_root: Path, datasets_root: Path) -> BundleSpec:
    return {
        "required_paths": [
            _repo_entry("docs/VAST_SETUP.md"),
            _repo_entry("docs/MODEL_PORTFOLIO.md"),
            _repo_entry("docs/eval/ORACLE_EVAL_MATRIX_V1_20260415.md"),
            _repo_entry("docs/eval/oracle_boundary_effort_matrix_v1.jsonl"),
            _repo_entry("config/chat_registry.toml"),
            _external_entry(training_root / "scripts" / "train_switchhook_27b_vast.py", "scripts/train_switchhook_27b_vast.py"),
            _external_entry(training_root / "scripts" / "eval_iquest_zelda.py", "scripts/eval_iquest_zelda.py"),
            _external_entry(training_root / "scripts" / "summarize_switchhook_live_smoke.py", "scripts/summarize_switchhook_live_smoke.py"),
            _external_entry(training_root / "evals" / "switchhook_live_smoke_v1.jsonl", "evals/switchhook_live_smoke_v1.jsonl"),
            _external_entry(datasets_root / "switchhook_27b_v1" / "train.jsonl", "datasets/switchhook_27b_v1/train.jsonl"),
            _external_entry(datasets_root / "switchhook_27b_v1" / "val.jsonl", "datasets/switchhook_27b_v1/val.jsonl"),
            _external_entry(datasets_root / "switchhook_27b_v1" / "metadata.json", "datasets/switchhook_27b_v1/metadata.json"),
        ],
        "optional_paths": [
            _external_entry(datasets_root / "switchhook_27b_v1" / "test.jsonl", "datasets/switchhook_27b_v1/test.jsonl"),
            _external_entry(training_root / "scripts" / "run_switchhook_live_eval_vast.sh", "scripts/run_switchhook_live_eval_vast.sh"),
            _external_entry(training_root / "scripts" / "push_vast_hf_token.sh", "scripts/push_vast_hf_token.sh"),
            _external_entry(training_root / "scripts" / "run_vast_training_with_watch.sh", "scripts/run_vast_training_with_watch.sh"),
        ],
    }


def _iquest_bundle_spec(repo_root: Path, training_root: Path, datasets_root: Path) -> BundleSpec:
    return {
        "required_paths": [
            _repo_entry("docs/VAST_SETUP.md"),
            _repo_entry("docs/MODEL_PORTFOLIO.md"),
            _external_entry(training_root / "scripts" / "train_iquest_40b.py", "scripts/train_iquest_40b.py"),
            _external_entry(training_root / "scripts" / "eval_iquest_zelda.py", "scripts/eval_iquest_zelda.py"),
            _external_entry(training_root / "evals" / "iquest_zelda_golden_v1.jsonl", "evals/iquest_zelda_golden_v1.jsonl"),
            _external_entry(datasets_root / "iquest_40b_unified_v3" / "train.jsonl", "datasets/iquest_40b_unified_v3/train.jsonl"),
            _external_entry(datasets_root / "iquest_40b_unified_v3" / "val.jsonl", "datasets/iquest_40b_unified_v3/val.jsonl"),
            _external_entry(datasets_root / "iquest_40b_unified_v3" / "metadata.json", "datasets/iquest_40b_unified_v3/metadata.json"),
        ],
        "optional_paths": [
            _external_entry(datasets_root / "iquest_40b_unified_v3" / "test.jsonl", "datasets/iquest_40b_unified_v3/test.jsonl"),
            _external_entry(training_root / "scripts" / "watch_iquest_training_and_backup.sh", "scripts/watch_iquest_training_and_backup.sh"),
        ],
    }


def _zelda_16b_bundle_spec(repo_root: Path, training_root: Path, datasets_root: Path) -> BundleSpec:
    return {
        "required_paths": [
            _repo_entry("docs/ZELDA_16B_TRAINING_PLAN.md"),
            _repo_entry("docs/VAST_SETUP.md"),
            _repo_entry("docs/MODEL_PORTFOLIO.md"),
            _repo_entry("scripts/dataset_qa_summary.py"),
            _repo_entry("scripts/train_zelda_16b_v1.py"),
            _external_entry(training_root / "scripts" / "eval_iquest_zelda.py", "scripts/eval_iquest_zelda.py"),
            _external_entry(training_root / "evals" / "iquest_zelda_golden_v1.jsonl", "evals/iquest_zelda_golden_v1.jsonl"),
            _external_entry(datasets_root / "zelda_16b_mix_v1" / "train.jsonl", "datasets/zelda_16b_mix_v1/train.jsonl"),
            _external_entry(datasets_root / "zelda_16b_mix_v1" / "val.jsonl", "datasets/zelda_16b_mix_v1/val.jsonl"),
            _external_entry(datasets_root / "zelda_16b_mix_v1" / "metadata.json", "datasets/zelda_16b_mix_v1/metadata.json"),
        ],
        "optional_paths": [
            _external_entry(datasets_root / "zelda_16b_mix_v1" / "eval.jsonl", "datasets/zelda_16b_mix_v1/eval.jsonl"),
            _external_entry(training_root / "scripts" / "push_vast_hf_token.sh", "scripts/push_vast_hf_token.sh"),
            _external_entry(training_root / "scripts" / "run_vast_training_with_watch.sh", "scripts/run_vast_training_with_watch.sh"),
        ],
    }


def _oracle_qwen35_thinker_bundle_spec(
    track_name: str,
    repo_root: Path,
    training_root: Path,
    datasets_root: Path,
) -> BundleSpec:
    track = get_zelda_track_spec(track_name)
    dataset_dir = Path(str(track["metadata"]["dataset_dir"]))
    arc_root = Path("datasets") / dataset_dir
    return {
        "required_paths": [
            _repo_entry("docs/VAST_SETUP.md"),
            _repo_entry("docs/MODEL_PORTFOLIO.md"),
            _repo_entry("config/chat_registry.toml"),
            _repo_entry("scripts/train_oracle_qwen35_thinker.py"),
            _external_entry(training_root / "scripts" / "eval_iquest_zelda.py", "scripts/eval_iquest_zelda.py"),
            _external_entry(training_root / "evals" / "iquest_zelda_golden_v1.jsonl", "evals/iquest_zelda_golden_v1.jsonl"),
            _external_entry(datasets_root / dataset_dir / "train.jsonl", str(arc_root / "train.jsonl")),
            _external_entry(datasets_root / dataset_dir / "val.jsonl", str(arc_root / "val.jsonl")),
            _external_entry(datasets_root / dataset_dir / "metadata.json", str(arc_root / "metadata.json")),
        ],
        "optional_paths": [
            _external_entry(datasets_root / dataset_dir / "eval.jsonl", str(arc_root / "eval.jsonl")),
            _external_entry(training_root / "scripts" / "push_vast_hf_token.sh", "scripts/push_vast_hf_token.sh"),
            _external_entry(training_root / "scripts" / "run_vast_training_with_watch.sh", "scripts/run_vast_training_with_watch.sh"),
        ],
    }


def get_zelda_bundle_spec(
    track_name: str,
    *,
    repo_root: Path | None = None,
    training_root: Path | None = None,
    datasets_root: Path | None = None,
) -> BundleSpec:
    """Return a bundle spec for a Zelda/oracle training track."""

    resolved_repo_root = (repo_root or REPO_ROOT).expanduser().resolve()
    resolved_training_root = (training_root or resolve_training_root()).expanduser().resolve()
    resolved_datasets_root = (datasets_root or resolve_datasets_root()).expanduser().resolve()
    resolved_track_name = resolve_zelda_track_name(track_name)
    builders = {
        ORACLE_MAIN_TRACK_NAME: _oracle_main_bundle_spec,
        "iquest_40b_v3": _iquest_bundle_spec,
        "zelda_16b_v1": _zelda_16b_bundle_spec,
    }
    if resolved_track_name in ORACLE_QWEN35_THINKER_PERSONAS:
        return _oracle_qwen35_thinker_bundle_spec(
            resolved_track_name,
            resolved_repo_root,
            resolved_training_root,
            resolved_datasets_root,
        )
    try:
        builder = builders[resolved_track_name]
    except KeyError as exc:
        raise KeyError(f"unknown Zelda bundle spec: {track_name}") from exc
    return builder(resolved_repo_root, resolved_training_root, resolved_datasets_root)


def validate_zelda_bundle_spec(
    track_name: str,
    *,
    repo_root: Path | None = None,
    training_root: Path | None = None,
    datasets_root: Path | None = None,
) -> BundleSelection:
    """Validate a Zelda bundle spec against the local filesystem."""

    resolved_repo_root = (repo_root or REPO_ROOT).expanduser().resolve()
    spec = get_zelda_bundle_spec(
        track_name,
        repo_root=resolved_repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )
    return validate_bundle_paths(resolved_repo_root, spec)


def build_zelda_bundle(
    track_name: str,
    output_path: Path,
    *,
    repo_root: Path | None = None,
    training_root: Path | None = None,
    datasets_root: Path | None = None,
) -> list[str]:
    """Build a Zelda/oracle training bundle using the shared model_ops builder."""

    resolved_repo_root = (repo_root or REPO_ROOT).expanduser().resolve()
    spec = get_zelda_bundle_spec(
        track_name,
        repo_root=resolved_repo_root,
        training_root=training_root,
        datasets_root=datasets_root,
    )
    return build_bundle(resolved_repo_root, output_path, spec)
