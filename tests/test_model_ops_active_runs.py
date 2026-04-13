from __future__ import annotations

import json
from pathlib import Path

from afs_scawful.model_ops.active_runs import apply_run_overrides, render_active_runs_note


TRACK_SPECS = {
    "zelda_smoke": {
        "description": "Smoke-test Zelda track",
        "phase_order": ["train", "align"],
        "phases": {
            "train": {"pid": "train.pid", "log": "logs/train.log", "artifact_path": "runs/train/merged"},
            "align": {"pid": "align.pid", "log": "logs/align.log", "artifact_path": "runs/align/merged"},
        },
        "auto_start_commands": {"align": "python align.py --input runs/train/merged"},
    }
}


def test_apply_run_overrides_updates_phase_paths_without_mutating_track() -> None:
    run_cfg = {
        "remote_override": {
            "align": {
                "log": "logs/align_retry.log",
                "artifact_path": "runs/align/retry_merged",
            }
        }
    }

    updated = apply_run_overrides(TRACK_SPECS["zelda_smoke"], run_cfg)

    assert updated["phases"]["align"]["log"] == "logs/align_retry.log"
    assert updated["phases"]["align"]["artifact_path"] == "runs/align/retry_merged"
    assert TRACK_SPECS["zelda_smoke"]["phases"]["align"]["log"] == "logs/align.log"


def test_render_active_runs_note_without_remote_probe(tmp_path: Path) -> None:
    output_path = tmp_path / "active-runs.md"
    config = {
        "output_path": str(output_path),
        "runs": [
            {
                "title": "Zelda smoke",
                "track": "zelda_smoke",
                "run_tag": "zelda-smoke-v1",
                "instance_id": "123",
                "host": "ssh9.vast.ai",
                "port": 19999,
                "label": "zelda-smoke",
                "remote_dir": "/opt/training",
                "notes": ["dataset: zelda_16b_mix_v1"],
            }
        ],
        "other_cloud_state": ["idle backup host: `halext-nj`"],
        "local_artifacts": ["latest eval bundle: `evals/zelda_smoke.json`"],
    }

    note = render_active_runs_note(config, TRACK_SPECS, output_path=output_path, no_probe_remote=True)

    assert "## Zelda smoke" in note
    assert "- track: `zelda_smoke`" in note
    assert "- run tag: `zelda-smoke-v1`" in note
    assert "## Other cloud state" in note
    assert "## Local artifacts" in note


def test_render_active_runs_note_shows_next_action_when_next_phase_is_idle(tmp_path: Path) -> None:
    output_path = tmp_path / "active-runs.md"
    config = {
        "output_path": str(output_path),
        "runs": [
            {
                "title": "Zelda smoke",
                "track": "zelda_smoke",
                "remote_dir": "/opt/training",
                "host": "ssh9.vast.ai",
                "port": 19999,
            }
        ],
    }

    def fake_runner(command: list[str], *, check: bool = True):
        payload = {
            "train": {"running": False, "artifact_ready": True, "log": "logs/train.log"},
            "align": {"running": False, "artifact_ready": False, "log": "logs/align.log"},
        }
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    note = render_active_runs_note(config, TRACK_SPECS, output_path=output_path, runner=fake_runner)

    assert "- phase: Align ready; idle on last probe" in note
    assert "- next action: `python align.py --input runs/train/merged`" in note
