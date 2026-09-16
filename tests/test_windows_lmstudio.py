from __future__ import annotations

import hashlib
import json

import pytest

from afs_scawful.windows import lmstudio


def test_candidate_model_ids_handles_mlx_suffix() -> None:
    candidates = lmstudio.candidate_model_ids("local-helper-qwen3-8b-v1-mlx")
    assert "local-helper-qwen3-8b-v1-mlx" in candidates
    assert "local-helper-qwen3-8b-v1" in candidates
    assert "gguf/lmstudio/local-helper-qwen3-8b-v1.gguf" in candidates


def test_resolve_available_model_id_prefers_equivalent_remote_name() -> None:
    available = [
        {"modelKey": "gguf/lmstudio/nayru-v9-q8_0.gguf"},
        {"modelKey": "local-helper-qwen3-8b-v1"},
        {"modelKey": "gguf/lmstudio/local-helper-gemma4-e4b-sft-dpo-q4km.gguf"},
    ]
    resolved = lmstudio.resolve_available_model_id("local-helper-qwen3-8b-v1-mlx", available)
    assert resolved == "local-helper-qwen3-8b-v1"


def test_unload_model_uses_loaded_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        lmstudio,
        "loaded_models",
        lambda **kwargs: [{"identifier": "nayru", "modelKey": "gguf/zelda/nayru-9b-q8_0.gguf"}],
    )
    seen: list[list[str]] = []

    def fake_run(args: list[str], **kwargs) -> str:
        seen.append(args)
        return ""

    monkeypatch.setattr(lmstudio, "run_lms", fake_run)
    result = lmstudio.unload_model(target="gguf/zelda/nayru-9b-q8_0.gguf")
    assert result["unloaded"] == ["nayru"]
    assert seen == [["unload", "nayru"]]


def test_load_model_resolves_fuzzy_id_and_includes_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        lmstudio,
        "available_models",
        lambda **kwargs: [{"modelKey": "gguf/zelda/qwen3-oracle-8b-v1-corrective2-q4km.gguf"}],
    )
    monkeypatch.setattr(lmstudio, "loaded_models", lambda **kwargs: [])
    seen: list[list[str]] = []

    def fake_run(args: list[str], **kwargs) -> str:
        seen.append(args)
        return ""

    monkeypatch.setattr(lmstudio, "run_lms", fake_run)
    result = lmstudio.load_model(model_id="qwen3-oracle-8b-v1-corrective2-q4km", identifier="oracle-fast")
    assert result["resolved_model_id"] == "gguf/zelda/qwen3-oracle-8b-v1-corrective2-q4km.gguf"
    assert seen[-1][:5] == ["load", "gguf/zelda/qwen3-oracle-8b-v1-corrective2-q4km.gguf", "--yes", "--identifier", "oracle-fast"]


def test_model_file_identity_hashes_the_indexed_artifact(tmp_path) -> None:
    model_root = tmp_path / "models"
    model_path = model_root / "scawfulbot" / "candidate.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"exact weights")

    identified = lmstudio.model_with_file_identity(
        {"modelKey": "candidate", "path": "scawfulbot/candidate.gguf"},
        model_root=model_root,
    )

    assert identified["sha256"] == hashlib.sha256(b"exact weights").hexdigest()
    assert identified["identitySizeBytes"] == len(b"exact weights")


def test_hostd_model_inventory_exposes_hashes_by_model_key(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    sha = hashlib.sha256(b"weights").hexdigest()
    monkeypatch.setattr(lmstudio, "resolve_lms_path", lambda lms_path=None: "C:/LM Studio/lms.exe")
    monkeypatch.setattr(
        lmstudio,
        "available_models_with_identity",
        lambda **kwargs: [{"modelKey": "candidate", "path": "publisher/candidate.gguf", "sha256": sha}],
    )

    response = TestClient(create_app()).get("/v1/lmstudio/models?include_sha256=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_sha256"]["candidate"] == sha
    assert payload["model_sha256"]["publisher/candidate.gguf"] == sha
    assert payload["host"]


def test_hostd_status_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    monkeypatch.setattr(lmstudio, "resolve_lms_path", lambda lms_path=None: "C:/LM Studio/lms.exe")
    monkeypatch.setattr(lmstudio, "server_status", lambda **kwargs: {"running": True, "port": 1234})
    monkeypatch.setattr(lmstudio, "loaded_models", lambda **kwargs: [{"identifier": "oracle-fast"}])
    monkeypatch.setattr(lmstudio, "available_models", lambda **kwargs: [{"modelKey": "gguf/zelda/qwen3-oracle-8b-v1-corrective2-q4km.gguf"}])

    app = create_app()
    client = TestClient(app)
    response = client.get("/v1/lmstudio/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["server"]["running"] is True
    assert payload["loaded"][0]["identifier"] == "oracle-fast"
