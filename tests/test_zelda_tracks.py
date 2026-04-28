from __future__ import annotations

import json
from pathlib import Path

from afs_scawful.model_ops.active_runs import render_active_runs_note
from afs_scawful.oracle_training.zelda_tracks import ORACLE_QWEN35_THINKER_PERSONAS, get_zelda_track_spec, list_zelda_tracks


def test_list_zelda_tracks_exposes_known_tracks() -> None:
    tracks = list_zelda_tracks()

    assert "oracle_main_27b_v1" in tracks
    assert "iquest_40b_v3" in tracks
    assert "zelda_16b_v1" in tracks
    assert "nayru_qwen35_thinker_v1" in tracks
    assert "din_qwen35_thinker_v1" in tracks
    assert "farore_qwen35_thinker_v1" in tracks
    assert "switchhook_27b_v1" not in tracks
    assert "oracle_tools_qwen35_thinker_v1" not in tracks
    assert "veran_qwen35_thinker_v1" not in tracks
    assert "majora_qwen35_thinker_v1" not in tracks
    assert "hylia_qwen35_thinker_v1" not in tracks
    assert "agahnim_qwen35_thinker_v1" not in tracks
    assert "sahasrahla_qwen35_thinker_v1" not in tracks


def test_oracle_main_track_is_model_ops_compatible() -> None:
    spec = get_zelda_track_spec("oracle_main_27b_v1")

    assert spec["bundle_name"] == "oracle_main_27b_v1"
    assert spec["remote_root"] == "/workspace/training"
    assert spec["phase_order"] == ["train"]
    assert spec["phases"]["train"]["log"] == "logs/switchhook-27b-v1.log"
    assert spec["phases"]["train"]["artifact_path"] == "output/switchhook-27b-v1/final"
    assert spec["downloads"]["adapter_final"] == "output/switchhook-27b-v1/final"
    assert spec["metadata"]["eval_matrix_pack"] == "oracle_boundary_effort_matrix_v1"
    assert spec["metadata"]["eval_matrix_doc"] == "docs/eval/ORACLE_EVAL_MATRIX_V1_20260415.md"
    assert spec["metadata"]["chat_registry_models"] == ["oracle"]


def test_legacy_switchhook_and_oracle_tools_aliases_resolve_to_oracle_main_track() -> None:
    switchhook_spec = get_zelda_track_spec("switchhook_27b_v1")
    oracle_tools_spec = get_zelda_track_spec("oracle_tools_qwen35_thinker_v1")

    assert switchhook_spec["bundle_name"] == "oracle_main_27b_v1"
    assert oracle_tools_spec["bundle_name"] == "oracle_main_27b_v1"
    assert switchhook_spec["metadata"]["resolved_from_alias"] == "switchhook_27b_v1"
    assert oracle_tools_spec["metadata"]["resolved_from_alias"] == "oracle_tools_qwen35_thinker_v1"


def test_zelda_16b_track_uses_repo_owned_wrapper() -> None:
    spec = get_zelda_track_spec("zelda_16b_v1")

    assert spec["phases"]["train"]["process_pattern"] == "train_zelda_16b_v1.py"
    assert spec["metadata"]["eval_pack"] == "iquest_zelda_golden_v1"


def test_nayru_thinker_track_uses_shared_qwen35_wrapper() -> None:
    spec = get_zelda_track_spec("nayru_qwen35_thinker_v1")

    assert spec["model_name"] == "Qwen/Qwen3.5-9B"
    assert spec["remote_root"] == "/opt/training"
    assert spec["phases"]["train"]["process_pattern"] == "train_oracle_qwen35_thinker.py"
    assert spec["metadata"]["dataset_dir"] == "oracle_qwen35_thinkers/nayru"
    assert spec["metadata"]["chat_registry_models"] == ["nayru"]


def test_farore_thinker_track_uses_debugging_specialist_role() -> None:
    spec = get_zelda_track_spec("farore_qwen35_thinker_v1")

    assert spec["model_name"] == "Qwen/Qwen3.5-9B"
    assert spec["phases"]["train"]["pid"] == "logs/farore-qwen35-thinker-v1.pid"
    assert spec["metadata"]["dataset_dir"] == "oracle_qwen35_thinkers/farore"
    assert spec["metadata"]["chat_registry_models"] == ["farore"]
    assert "Autocomplete" not in spec["metadata"]["role"]
    assert "FIM" not in spec["metadata"]["role"]


def test_qwen35_thinker_tracks_cover_expected_named_oracles() -> None:
    expected_personas = {
        "din",
        "nayru",
        "farore",
    }
    thinker_personas = {item["persona"] for item in ORACLE_QWEN35_THINKER_PERSONAS.values()}

    assert thinker_personas == expected_personas


def test_oracle_main_track_renders_through_shared_active_runs_core(tmp_path: Path) -> None:
    track_spec = get_zelda_track_spec("oracle_main_27b_v1")
    config = {
        "output_path": str(tmp_path / "active-runs.md"),
        "runs": [
            {
                "title": "Oracle-Main Vast",
                "track": "oracle_main_27b_v1",
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
                "log": "logs/switchhook-27b-v1.log",
            }
        }
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    note = render_active_runs_note(
        config,
        {"oracle_main_27b_v1": track_spec},
        output_path=Path(config["output_path"]),
        runner=fake_runner,
    )

    assert "## Oracle-Main Vast" in note
    assert "- track: `oracle_main_27b_v1`" in note
    assert "- phase: Train running" in note
