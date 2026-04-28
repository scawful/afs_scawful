from __future__ import annotations

import pytest

from afs_scawful.windows import lmstudio
from afs_scawful.windows import power
from afs_scawful.windows import training_status
from afs_scawful.windows import wsl


def test_mode_status_infers_train_from_running_training(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    monkeypatch.setattr(power, "current_policy", lambda: {"sleep_suppressed_on_ac": True})
    monkeypatch.setattr(lmstudio, "resolve_lms_path", lambda lms_path=None: "C:/LM Studio/lms.exe")
    monkeypatch.setattr(lmstudio, "server_status", lambda **kwargs: {"running": True, "port": 1234})
    monkeypatch.setattr(lmstudio, "loaded_models", lambda **kwargs: [])

    def fake_vllm_action(action: str, **kwargs):
        assert action == "status"
        return {"state": "stopped"}

    monkeypatch.setattr(wsl, "vllm_action", fake_vllm_action)
    monkeypatch.setattr(
        training_status,
        "status_snapshot",
        lambda **kwargs: {"state": "running", "task": kwargs["task"], "config": kwargs["config"]},
    )

    client = TestClient(create_app())
    response = client.get(
        "/v1/mode",
        params={"task": "oracle-main", "config": "configs/zelda/qwen3_oracle_14b_v2.toml"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode_hint"]["mode"] == "train"
    assert payload["mode_hint"]["reason"] == "training_running"


def test_set_mode_train_coordinates_power_vllm_and_lmstudio(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    monkeypatch.setattr(power, "current_policy", lambda: {"sleep_suppressed_on_ac": False})
    monkeypatch.setattr(power, "suppress_sleep_for_training", lambda: {"changed": True})
    monkeypatch.setattr(lmstudio, "resolve_lms_path", lambda lms_path=None: "C:/LM Studio/lms.exe")
    monkeypatch.setattr(lmstudio, "server_status", lambda **kwargs: {"running": True, "port": 1234})
    monkeypatch.setattr(lmstudio, "loaded_models", lambda **kwargs: [{"identifier": "oracle-fast", "modelKey": "gguf/zelda/oracle-fast.gguf"}])
    monkeypatch.setattr(lmstudio, "unload_model", lambda **kwargs: {"all": kwargs.get("all_models"), "unloaded": ["oracle-fast"]})

    seen: list[tuple[str, str]] = []

    def fake_vllm_action(action: str, **kwargs):
        if action == "status":
            return {"state": "running", "served_name": "oracle-fast"}
        if action == "stop":
            seen.append(("vllm", action))
            return {"state": "stopped"}
        raise AssertionError(action)

    monkeypatch.setattr(wsl, "vllm_action", fake_vllm_action)
    monkeypatch.setattr(
        wsl,
        "training_action",
        lambda action, **kwargs: {"state": "unknown" if action == "status" else "stopped"},
    )

    client = TestClient(create_app())
    response = client.post("/v1/mode", json={"mode": "train"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_mode"] == "train"
    assert payload["effective_actions"]["stop_vllm"] is True
    surfaces = [item["surface"] for item in payload["actions"]]
    assert "power" in surfaces
    assert "vllm" in surfaces
    assert "lmstudio" in surfaces
