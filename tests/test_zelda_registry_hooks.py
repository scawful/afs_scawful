from __future__ import annotations

from pathlib import Path

from afs_scawful.oracle_training.zelda_registry_hooks import build_zelda_registry_plan, run_zelda_registry_hooks


def test_switchhook_registry_plan_includes_merge_and_convert_steps(tmp_path: Path) -> None:
    artifact = tmp_path / "adapter_final"
    artifact.mkdir()
    (artifact / "adapter_model.safetensors").write_text("stub\n", encoding="utf-8")

    plan = build_zelda_registry_plan(
        "switchhook_27b_v1",
        artifact_path=artifact,
        training_root=tmp_path / "training",
        training_models_root=tmp_path / "models_root",
        model_mgr_path=tmp_path / "model-mgr",
        quantizations=["q4km", "q8"],
        include_mlx=True,
    )

    names = [item["name"] for item in plan["commands"]]
    assert names[:2] == ["merge_adapter", "convert_q4km"]
    assert "convert_q8" in names
    assert "mlx_convert" in names
    assert plan["environment"]["MODELS_DIR"] == str((tmp_path / "models_root").resolve())
    assert plan["registry_updates"][0]["model_name"] == "switchhook-plan"
    assert plan["registry_updates"][0]["model_id"] == "gguf/zelda/switchhook-27b-v1-q4km.gguf"


def test_registry_plan_for_merged_model_skips_merge(tmp_path: Path) -> None:
    merged = tmp_path / "iquest-40b-v3"
    merged.mkdir()

    plan = build_zelda_registry_plan(
        "iquest_40b_v3",
        artifact_path=merged,
        training_root=tmp_path / "training",
        model_mgr_path=tmp_path / "model-mgr",
    )

    assert plan["commands"][0]["name"] == "convert_q4km"
    assert plan["environment"]["MODELS_DIR"] == str(tmp_path.resolve())


def test_run_zelda_registry_hooks_executes_commands(tmp_path: Path) -> None:
    plan = {
        "environment": {"MODELS_DIR": str(tmp_path / "models")},
        "commands": [
            {"name": "convert_q4km", "command": ["bash", "/tmp/model-mgr", "convert", "demo", "--quantize", "q4km"]},
            {"name": "artifacts_index", "command": ["bash", "/tmp/model-mgr", "artifacts-index"]},
        ],
    }
    seen: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_runner(command, *, env=None, check=True):
        seen.append((list(command), dict(env or {})))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    results = run_zelda_registry_hooks(plan, runner=fake_runner)

    assert [item["name"] for item in results] == ["convert_q4km", "artifacts_index"]
    assert seen[0][1]["MODELS_DIR"] == str(tmp_path / "models")
