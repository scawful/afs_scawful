from __future__ import annotations

from pathlib import Path

from afs_scawful.oracle_training.zelda_registry_hooks import build_zelda_registry_plan, run_zelda_registry_hooks


def test_oracle_main_registry_plan_includes_merge_and_convert_steps(tmp_path: Path) -> None:
    artifact = tmp_path / "adapter_final"
    artifact.mkdir()
    (artifact / "adapter_model.safetensors").write_text("stub\n", encoding="utf-8")

    plan = build_zelda_registry_plan(
        "oracle_main_27b_v1",
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
    assert "MODEL_MGR_PYTHON" in plan["environment"]
    assert "python" in Path(plan["commands"][0]["command"][0]).name
    assert {item["model_name"] for item in plan["registry_updates"]} == {"oracle"}
    assert all(item["model_id"] == "gguf/zelda/switchhook-27b-v1-q4km.gguf" for item in plan["registry_updates"])


def test_legacy_switchhook_registry_alias_resolves_to_oracle_main(tmp_path: Path) -> None:
    artifact = tmp_path / "adapter_final"
    artifact.mkdir()
    (artifact / "adapter_model.safetensors").write_text("stub\n", encoding="utf-8")

    plan = build_zelda_registry_plan(
        "switchhook_27b_v1",
        artifact_path=artifact,
        training_root=tmp_path / "training",
        training_models_root=tmp_path / "models_root",
        model_mgr_path=tmp_path / "model-mgr",
    )

    assert plan["model_name"] == "switchhook-27b-v1"


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
    assert "MODEL_MGR_PYTHON" in plan["environment"]


def test_nayru_thinker_registry_plan_targets_chat_registry_model(tmp_path: Path) -> None:
    artifact = tmp_path / "adapter_final"
    artifact.mkdir()
    (artifact / "adapter_model.safetensors").write_text("stub\n", encoding="utf-8")

    plan = build_zelda_registry_plan(
        "nayru_qwen35_thinker_v1",
        artifact_path=artifact,
        training_root=tmp_path / "training",
        training_models_root=tmp_path / "models_root",
        model_mgr_path=tmp_path / "model-mgr",
    )
    registry_updates = plan["registry_updates"]

    assert plan["model_name"] == "nayru-qwen35-thinker-v1"
    assert registry_updates
    assert registry_updates[0]["model_name"] == "nayru"
    assert registry_updates[0]["model_id"] == "gguf/zelda/nayru-qwen35-thinker-v1-q4km.gguf"


def test_farore_thinker_registry_plan_targets_chat_registry_model(tmp_path: Path) -> None:
    artifact = tmp_path / "adapter_final"
    artifact.mkdir()
    (artifact / "adapter_model.safetensors").write_text("stub\n", encoding="utf-8")

    plan = build_zelda_registry_plan(
        "farore_qwen35_thinker_v1",
        artifact_path=artifact,
        training_root=tmp_path / "training",
        training_models_root=tmp_path / "models_root",
        model_mgr_path=tmp_path / "model-mgr",
    )

    assert plan["model_name"] == "farore-qwen35-thinker-v1"
    assert plan["registry_updates"] == [
        {
            "model_name": "farore",
            "model_id": "gguf/zelda/farore-qwen35-thinker-v1-q4km.gguf",
        }
    ]


def test_run_zelda_registry_hooks_executes_commands(tmp_path: Path) -> None:
    plan = {
        "environment": {"MODELS_DIR": str(tmp_path / "models")},
        "commands": [
            {"name": "convert_q4km", "command": ["bash", "/tmp/model-mgr", "convert", "demo", "--quantize", "q4km"]},
            {"name": "artifacts_index", "command": ["bash", "/tmp/model-mgr", "artifacts-index"]},
        ],
    }
    seen: list[tuple[list[str], dict[str, str]]] = []

    def fake_runner(command, *, env=None, check=True):
        seen.append((list(command), dict(env or {})))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    results = run_zelda_registry_hooks(plan, runner=fake_runner)

    assert [item["name"] for item in results] == ["convert_q4km", "artifacts_index"]
    first_env = seen[0][1]
    assert first_env["MODELS_DIR"] == str(tmp_path / "models")
