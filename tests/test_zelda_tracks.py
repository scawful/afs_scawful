from __future__ import annotations

import json
from pathlib import Path

from afs_scawful.model_ops.active_runs import render_active_runs_note
from afs_scawful.oracle_training.zelda_tracks import get_zelda_track_spec, list_zelda_tracks


def test_list_zelda_tracks_exposes_known_tracks() -> None:
    tracks = list_zelda_tracks()

    assert "switchhook_27b_v1" in tracks
    assert "iquest_40b_v3" in tracks
    assert "zelda_16b_v1" in tracks


def test_switchhook_track_is_model_ops_compatible() -> None:
    spec = get_zelda_track_spec("switchhook_27b_v1")

    assert spec["bundle_name"] == "switchhook_27b_v1"
    assert spec["remote_root"] == "/workspace/training"
    assert spec["phase_order"] == ["train"]
    assert spec["phases"]["train"]["artifact_path"] == "output/switchhook-27b-v1/final"
    assert spec["downloads"]["adapter_final"] == "output/switchhook-27b-v1/final"


def test_zelda_16b_track_uses_repo_owned_wrapper() -> None:
    spec = get_zelda_track_spec("zelda_16b_v1")

    assert spec["phases"]["train"]["process_pattern"] == "train_zelda_16b_v1.py"
    assert spec["metadata"]["eval_pack"] == "iquest_zelda_golden_v1"


def test_switchhook_track_renders_through_shared_active_runs_core(tmp_path: Path) -> None:
    track_spec = get_zelda_track_spec("switchhook_27b_v1")
    config = {
        "output_path": str(tmp_path / "active-runs.md"),
        "runs": [
            {
                "title": "Switchhook Vast",
                "track": "switchhook_27b_v1",
                "run_tag": "switchhook-27b-v1-demo",
                "host": "ssh6.vast.ai",
                "port": 22,
                "remote_dir": track_spec["remote_root"],
            }
        ],
    }

    def fake_runner(command: list[str], *, check: bool = True):
        payload = {
            "train": {
                "running": True,
                "artifact_ready": False,
                "log": "logs/switchhook_train.log",
            }
        }
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    note = render_active_runs_note(
        config,
        {"switchhook_27b_v1": track_spec},
        output_path=Path(config["output_path"]),
        runner=fake_runner,
    )

    assert "## Switchhook Vast" in note
    assert "- track: `switchhook_27b_v1`" in note
    assert "- phase: Train running" in note
