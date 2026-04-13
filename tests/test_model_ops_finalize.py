from __future__ import annotations

from pathlib import Path

import pytest

from afs_scawful.model_ops.finalize import RemoteRunTarget, unique_local_run_dir, wait_for_remote_completion


TRACK_SPEC = {
    "phase_order": ["train", "align"],
    "phases": {
        "train": {"pid": "train.pid", "log": "logs/train.log", "artifact_path": "runs/train/merged"},
        "align": {"pid": "align.pid", "log": "logs/align.log", "artifact_path": "runs/align/merged"},
    },
    "auto_start_commands": {"align": "python align.py --input runs/train/merged"},
    "downloads": {"merged": "runs/align/merged"},
}


def test_unique_local_run_dir_suffixes_when_existing(tmp_path: Path) -> None:
    base = tmp_path / "run"
    base.mkdir()

    resolved = unique_local_run_dir(base)

    assert resolved != base
    assert resolved.name.startswith("run-")


def test_wait_for_remote_completion_starts_next_phase_when_previous_artifact_ready() -> None:
    target = RemoteRunTarget(host="ssh.vast.ai", port=22, remote_dir="/opt/training")
    statuses = iter(
        [
            {
                "train": {"running": True, "artifact_ready": False, "log": "logs/train.log"},
                "align": {"running": False, "artifact_ready": False, "log": "logs/align.log"},
            },
            {
                "train": {"running": False, "artifact_ready": True, "log": "logs/train.log"},
                "align": {"running": False, "artifact_ready": False, "log": "logs/align.log"},
            },
            {
                "train": {"running": False, "artifact_ready": True, "log": "logs/train.log"},
                "align": {"running": True, "artifact_ready": False, "log": "logs/align.log"},
            },
            {
                "train": {"running": False, "artifact_ready": True, "log": "logs/train.log"},
                "align": {"running": False, "artifact_ready": True, "log": "logs/align.log"},
            },
        ]
    )
    started: list[str] = []
    messages: list[str] = []

    completed = wait_for_remote_completion(
        target,
        TRACK_SPEC,
        poll_seconds=0,
        status_provider=lambda _target, _spec: next(statuses),
        phase_starter=lambda _target, _spec, phase_name: started.append(phase_name) or True,
        sleeper=lambda _seconds: None,
        status_printer=messages.append,
    )

    assert completed == "align"
    assert started == ["align"]
    assert any("requested remote start for align" in message for message in messages)


def test_wait_for_remote_completion_raises_when_first_phase_exits_without_artifact() -> None:
    target = RemoteRunTarget(host="ssh.vast.ai", port=22, remote_dir="/opt/training")

    with pytest.raises(RuntimeError, match="train exited without artifact output"):
        wait_for_remote_completion(
            target,
            TRACK_SPEC,
            poll_seconds=0,
            status_provider=lambda _target, _spec: {
                "train": {"running": False, "artifact_ready": False, "log": "logs/train.log"},
                "align": {"running": False, "artifact_ready": False, "log": "logs/align.log"},
            },
            log_tail_provider=lambda _target, _log_name: "Traceback...",
            sleeper=lambda _seconds: None,
            status_printer=lambda _message: None,
        )
