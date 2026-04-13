from __future__ import annotations

import json
import re
from pathlib import Path

from afs_scawful.model_ops.active_runs import render_active_runs_note
from afs_scawful.oracle_training.zelda_tracks import ORACLE_QWEN35_THINKER_PERSONAS, get_zelda_track_spec, list_zelda_tracks


def test_list_zelda_tracks_exposes_known_tracks() -> None:
    tracks = list_zelda_tracks()

    assert "switchhook_27b_v1" in tracks
    assert "iquest_40b_v3" in tracks
    assert "zelda_16b_v1" in tracks
    assert "nayru_qwen35_thinker_v1" in tracks
    assert "oracle_tools_qwen35_thinker_v1" in tracks
    assert "sahasrahla_qwen35_thinker_v1" in tracks


def test_switchhook_track_is_model_ops_compatible() -> None:
    spec = get_zelda_track_spec("switchhook_27b_v1")

    assert spec["bundle_name"] == "switchhook_27b_v1"
    assert spec["remote_root"] == "/workspace/training"
    assert spec["phase_order"] == ["train"]
    assert spec["phases"]["train"]["log"] == "logs/switchhook-27b-v1.log"
    assert spec["phases"]["train"]["artifact_path"] == "output/switchhook-27b-v1/final"
    assert spec["downloads"]["adapter_final"] == "output/switchhook-27b-v1/final"


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


def test_sahasrahla_thinker_track_uses_shared_qwen35_wrapper() -> None:
    spec = get_zelda_track_spec("sahasrahla_qwen35_thinker_v1")

    assert spec["model_name"] == "Qwen/Qwen3.5-9B"
    assert spec["phases"]["train"]["pid"] == "logs/sahasrahla-qwen35-thinker-v1.pid"
    assert spec["metadata"]["dataset_dir"] == "oracle_qwen35_thinkers/sahasrahla"
    assert spec["metadata"]["chat_registry_models"] == []


def test_qwen35_thinker_tracks_cover_documented_named_oracles() -> None:
    docs_path = Path(__file__).resolve().parents[1] / "docs" / "MODEL_PORTFOLIO.md"
    docs_text = docs_path.read_text(encoding="utf-8")
    expected_personas = {
        "din",
        "nayru",
        "farore",
        "veran",
        "agahnim",
        "majora",
        "hylia",
        "oracle-tools",
        "sahasrahla",
    }
    documented_names = {
        match.group(1).lower().replace("-3b", "")
        for match in re.finditer(r"\*\*(Din|Nayru|Farore|Veran|Agahnim|Majora|Hylia|Oracle-Tools|Sahasrahla(?:-3B)?)\*\*", docs_text)
    }
    thinker_personas = {item["persona"] for item in ORACLE_QWEN35_THINKER_PERSONAS.values()}

    assert documented_names == expected_personas
    assert thinker_personas == expected_personas


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
                "log": "logs/switchhook-27b-v1.log",
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
