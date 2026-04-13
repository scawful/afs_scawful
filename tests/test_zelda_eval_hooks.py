from __future__ import annotations

from pathlib import Path

import pytest

from afs_scawful.model_ops.finalize import RemoteRunTarget
from afs_scawful.oracle_training.zelda_eval_hooks import build_zelda_eval_plan, run_zelda_eval_hooks


def test_switchhook_eval_plan_requires_remote_target(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="remote target"):
        build_zelda_eval_plan("switchhook_27b_v1", local_run_dir=tmp_path)


def test_switchhook_eval_plan_builds_remote_eval_command(tmp_path: Path) -> None:
    target = RemoteRunTarget(host="ssh6.vast.ai", port=22, remote_dir="/workspace/training")
    plan = build_zelda_eval_plan("switchhook_27b_v1", local_run_dir=tmp_path, remote_target=target)

    assert plan[0]["name"] == "switchhook_live_smoke"
    assert plan[0]["command"][0] == "bash"
    assert "run_switchhook_live_eval_vast.sh" in plan[0]["command"][1]
    assert "/workspace/training/output/switchhook-27b-v1/final" in plan[0]["command"]
    assert any(str(tmp_path / "eval" / "switchhook_live_smoke.jsonl") == output for output in plan[0]["outputs"])


def test_iquest_eval_plan_builds_local_eval_command(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter_final"
    adapter.mkdir()

    plan = build_zelda_eval_plan("iquest_40b_v3", local_run_dir=tmp_path, adapter_path=adapter)

    assert plan[0]["name"] == "iquest_zelda_golden_eval"
    assert plan[0]["command"][0] == "python3"
    assert "eval_iquest_zelda.py" in plan[0]["command"][1]
    assert str(adapter) in plan[0]["command"]


def test_zelda_16b_eval_plan_builds_local_eval_command(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter_final"
    adapter.mkdir()

    plan = build_zelda_eval_plan("zelda_16b_v1", local_run_dir=tmp_path, adapter_path=adapter)

    assert plan[0]["name"] == "zelda_16b_golden_eval"
    assert plan[0]["command"][0] == "python3"
    assert "eval_iquest_zelda.py" in plan[0]["command"][1]
    assert str(adapter) in plan[0]["command"]


def test_run_zelda_eval_hooks_skips_manual_entries() -> None:
    results = run_zelda_eval_hooks([{"name": "manual_eval_setup", "manual": True}])

    assert results == [{"name": "manual_eval_setup", "skipped": True, "reason": "manual"}]
