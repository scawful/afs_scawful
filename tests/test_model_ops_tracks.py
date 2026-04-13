from __future__ import annotations

from afs_scawful.model_ops.tracks import apply_track_overrides, get_phase_order, validate_track_spec


def test_validate_track_spec_normalizes_artifact_paths() -> None:
    spec = validate_track_spec(
        {
            "description": "demo",
            "phases": {
                "train": {"pid": "train.pid", "log": "train.log", "merged_dir": "runs/train/merged"},
                "align": {"pid": "align.pid", "log": "align.log", "artifact_path": "runs/align/merged"},
            },
        }
    )

    assert get_phase_order(spec) == ["train", "align"]
    assert spec["phases"]["train"]["artifact_path"] == "runs/train/merged"
    assert spec["phases"]["align"]["artifact_path"] == "runs/align/merged"


def test_apply_track_overrides_is_non_destructive() -> None:
    base = {
        "phases": {
            "train": {"pid": "train.pid", "log": "train.log", "artifact_path": "runs/train/merged"},
            "align": {"pid": "align.pid", "log": "align.log", "artifact_path": "runs/align/merged"},
        },
        "auto_start_commands": {"align": "python align.py"},
    }

    updated = apply_track_overrides(
        base,
        {
            "phase_overrides": {"align": {"log": "logs/align_v2.log"}},
            "auto_start_commands": {"align": "python align_v2.py"},
        },
    )

    assert updated["phases"]["align"]["log"] == "logs/align_v2.log"
    assert updated["auto_start_commands"]["align"] == "python align_v2.py"
    assert base["phases"]["align"]["log"] == "align.log"
