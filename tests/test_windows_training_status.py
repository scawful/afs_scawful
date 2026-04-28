from __future__ import annotations

import json
import os

import pytest

from afs_scawful.windows import training_status


def test_status_snapshot_reads_metrics_and_logs(tmp_path):
    train_root = tmp_path / "training"
    config_path = train_root / "configs/zelda/qwen3_oracle_14b_v2.toml"
    output_dir = train_root / "output/qwen3-oracle-14b-v2"
    run_dir = tmp_path / "run"
    log_dir = tmp_path / "logs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        """
[model]
name = "qwen3-oracle-14b-v2"
base = "Qwen/Qwen3-14B"

[paths]
output_dir = "/workspace/training/output/qwen3-oracle-14b-v2"
""".strip(),
        encoding="utf-8",
    )
    metrics_path = output_dir / "metrics.jsonl"
    records = [
        {"type": "train_start", "total_steps": 100, "timestamp": "2026-04-20T14:00:00+00:00"},
        {"type": "metrics", "step": 10, "loss": 1.2, "timestamp": "2026-04-20T14:05:00+00:00"},
        {"type": "checkpoint", "step": 10, "last_loss": 1.2, "timestamp": "2026-04-20T14:05:10+00:00"},
        {"type": "train_end", "step": 100, "last_loss": 0.4, "timestamp": "2026-04-20T15:00:00+00:00"},
    ]
    metrics_path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    (output_dir / "checkpoint-10").mkdir()
    (log_dir / "qwen3-oracle-14b-v2.out.log").write_text("stdout line 1\nstdout line 2\n", encoding="utf-8")
    (log_dir / "qwen3-oracle-14b-v2.err.log").write_text("stderr line 1\n", encoding="utf-8")

    payload = training_status.status_snapshot(
        task="qwen3-oracle-14b-v2",
        config=str(config_path),
        train_root=str(train_root),
        run_dir=run_dir,
        log_dir=log_dir,
        tail=2,
    )

    assert payload["state"] == "completed"
    assert payload["source"] == "filesystem"
    assert payload["current_step"] == 100
    assert payload["total_steps"] == 100
    assert payload["last_loss"] == 0.4
    assert payload["eta_seconds"] == 0
    assert payload["checkpoints"] == ["checkpoint-10"]
    assert payload["stdout_tail"] == ["stdout line 1", "stdout line 2"]
    assert payload["stderr_tail"] == ["stderr line 1"]


def test_status_snapshot_marks_running_when_pid_is_live(tmp_path):
    train_root = tmp_path / "training"
    config_path = train_root / "configs/zelda/qwen35_oracle_fast_v2.toml"
    output_dir = train_root / "output/qwen35-oracle-fast-v2"
    run_dir = tmp_path / "run"
    log_dir = tmp_path / "logs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        """
[model]
name = "qwen35-oracle-fast-v2"
base = "Qwen/Qwen3-8B"

[paths]
output_dir = "/workspace/training/output/qwen35-oracle-fast-v2"
""".strip(),
        encoding="utf-8",
    )
    metrics_path = output_dir / "metrics.jsonl"
    records = [
        {"type": "train_start", "total_steps": 200, "timestamp": "2026-04-20T14:00:00+00:00"},
        {"type": "metrics", "step": 50, "loss": 0.8, "timestamp": "2026-04-20T14:25:00+00:00"},
    ]
    metrics_path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    (run_dir / "qwen35-oracle-fast-v2.pid").write_text(str(os.getpid()), encoding="utf-8")

    payload = training_status.status_snapshot(
        task="qwen35-oracle-fast-v2",
        config=str(config_path),
        train_root=str(train_root),
        run_dir=run_dir,
        log_dir=log_dir,
        tail=1,
    )

    assert payload["state"] == "running"
    assert payload["pid"] == os.getpid()
    assert payload["current_step"] == 50
    assert payload["total_steps"] == 200
    assert payload["eta_seconds"] == 4500
    assert payload["eta"] == "1h15m"


def test_status_snapshot_falls_back_to_train_root_logs_and_config_stem(tmp_path):
    train_root = tmp_path / "training"
    config_path = train_root / "configs/zelda/oracle_qwen35_9b_dpo_prod_v1.toml"
    output_dir = train_root / "output/oracle-qwen35-9b-v1-dpo-prod1"
    log_dir = train_root / "logs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        """
[model]
name = "oracle-qwen35-9b-v1-dpo-prod1"
base = "/workspace/training/models/qwen35-oracle-9b-v1/merged"

[paths]
output_dir = "/workspace/training/output/oracle-qwen35-9b-v1-dpo-prod1"
""".strip(),
        encoding="utf-8",
    )
    metrics_path = output_dir / "metrics.jsonl"
    records = [
        {"type": "train_start", "total_steps": 55, "timestamp": "2026-04-26T07:56:43+00:00"},
        {"type": "metrics", "step": 15, "loss": 0.6931, "timestamp": "2026-04-26T13:07:32+00:00"},
    ]
    metrics_path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    (log_dir / "oracle-qwen35-9b-dpo-prod1.pid").write_text(str(os.getpid()), encoding="utf-8")
    (log_dir / "oracle-qwen35-9b-dpo-prod1.out.log").write_text("runner-start\n", encoding="utf-8")
    (log_dir / "oracle-qwen35-9b-dpo-prod1.err.log").write_text("31%|###\n", encoding="utf-8")

    payload = training_status.status_snapshot(
        task="oracle-qwen35-9b-v1-dpo-prod1",
        config=str(config_path),
        train_root=str(train_root),
        tail=1,
    )

    assert payload["state"] == "running"
    assert payload["pid"] == os.getpid()
    assert payload["pid_file"].endswith("oracle-qwen35-9b-dpo-prod1.pid")
    assert payload["stdout_log"].endswith("oracle-qwen35-9b-dpo-prod1.out.log")
    assert payload["stderr_tail"] == ["31%|###"]
    assert payload["current_step"] == 15
    assert payload["total_steps"] == 55


def test_status_snapshot_matches_running_process_when_pid_file_is_stale(tmp_path, monkeypatch):
    train_root = tmp_path / "training"
    config_path = train_root / "configs/zelda/oracle_qwen35_9b_dpo_prod_v1.toml"
    output_dir = train_root / "output/oracle-qwen35-9b-v1-dpo-prod1"
    log_dir = train_root / "logs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        """
[model]
name = "oracle-qwen35-9b-v1-dpo-prod1"

[paths]
output_dir = "/workspace/training/output/oracle-qwen35-9b-v1-dpo-prod1"
""".strip(),
        encoding="utf-8",
    )
    (output_dir / "metrics.jsonl").write_text(
        json.dumps({"type": "train_start", "total_steps": 55, "timestamp": "2026-04-26T07:56:43+00:00"})
        + "\n"
        + json.dumps({"type": "metrics", "step": 20, "loss": 0.7, "timestamp": "2026-04-26T14:07:32+00:00"})
        + "\n",
        encoding="utf-8",
    )
    (log_dir / "oracle-qwen35-9b-dpo-prod1.pid").write_text("99999999", encoding="utf-8")

    monkeypatch.setattr(
        training_status,
        "find_training_process",
        lambda config_path, task, stems: {"pid": os.getpid(), "command": "python train_zelda_dpo.py"},
    )

    payload = training_status.status_snapshot(
        task="oracle-qwen35-9b-v1-dpo-prod1",
        config=str(config_path),
        train_root=str(train_root),
        tail=1,
    )

    assert payload["state"] == "running"
    assert payload["pid"] == os.getpid()
    assert payload["process_command"] == "python train_zelda_dpo.py"
    assert "pid file is missing or stale" in payload["warnings"][0]


def test_status_snapshot_uses_run_state_before_metrics_exist(tmp_path):
    train_root = tmp_path / "training"
    config_path = train_root / "configs/zelda/qwen3_oracle_14b_v7.toml"
    output_dir = train_root / "output/qwen3-oracle-14b-v7"
    run_dir = tmp_path / "run"
    log_dir = tmp_path / "logs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        """
[model]
name = "qwen3-oracle-14b-v7"
base = "Qwen/Qwen3-14B"

[paths]
output_dir = "/workspace/training/output/qwen3-oracle-14b-v7"
""".strip(),
        encoding="utf-8",
    )
    (run_dir / "qwen3-oracle-14b-v7.pid").write_text(str(os.getpid()), encoding="utf-8")
    (output_dir / "run_state.json").write_text(
        json.dumps(
            {
                "task": "qwen3-oracle-14b-v7",
                "status": "running",
                "phase": "loading_base_model",
                "message": "",
                "updated_at": "2026-04-21T23:55:00+00:00",
            }
        ) + "\n",
        encoding="utf-8",
    )

    payload = training_status.status_snapshot(
        task="qwen3-oracle-14b-v7",
        config=str(config_path),
        train_root=str(train_root),
        run_dir=run_dir,
        log_dir=log_dir,
        tail=1,
    )

    assert payload["state"] == "running"
    assert payload["phase"] == "loading_base_model"
    assert payload["phase_status"] == "running"
    assert payload["current_step"] is None


def test_status_snapshot_marks_failed_from_run_state(tmp_path):
    train_root = tmp_path / "training"
    config_path = train_root / "configs/zelda/qwen3_oracle_14b_v7.toml"
    output_dir = train_root / "output/qwen3-oracle-14b-v7"
    run_dir = tmp_path / "run"
    log_dir = tmp_path / "logs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        """
[model]
name = "qwen3-oracle-14b-v7"
base = "Qwen/Qwen3-14B"

[paths]
output_dir = "/workspace/training/output/qwen3-oracle-14b-v7"
""".strip(),
        encoding="utf-8",
    )
    (output_dir / "run_state.json").write_text(
        json.dumps(
            {
                "task": "qwen3-oracle-14b-v7",
                "status": "failed",
                "phase": "loading_base_model",
                "message": "boom",
                "error_type": "RuntimeError",
                "updated_at": "2026-04-21T23:56:00+00:00",
            }
        ) + "\n",
        encoding="utf-8",
    )

    payload = training_status.status_snapshot(
        task="qwen3-oracle-14b-v7",
        config=str(config_path),
        train_root=str(train_root),
        run_dir=run_dir,
        log_dir=log_dir,
        tail=1,
    )

    assert payload["state"] == "failed"
    assert payload["phase"] == "loading_base_model"
    assert payload["phase_status"] == "failed"
    assert payload["phase_error"] == "RuntimeError"
    assert payload["phase_message"] == "boom"


def test_training_status_endpoint_uses_filesystem_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    monkeypatch.setattr(
        training_status,
        "status_snapshot",
        lambda **kwargs: {"state": "running", "task": kwargs["task"], "current_step": 30, "total_steps": 100},
    )

    client = TestClient(create_app())
    response = client.get(
        "/v1/training/status",
        params={"task": "oracle-main", "config": "configs/zelda/qwen3_oracle_14b_v2.toml"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "running"
    assert payload["current_step"] == 30
    assert payload["total_steps"] == 100
    assert "ts" in payload
