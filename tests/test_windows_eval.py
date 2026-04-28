from __future__ import annotations

import pytest

from afs_scawful.windows import wsl


def test_eval_status_endpoint_uses_eval_action(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    def fake_eval_action(action: str, **kwargs):
        assert action == "status"
        return {"state": "running", "name": kwargs["name"], "out": kwargs["out"]}

    monkeypatch.setattr(wsl, "eval_action", fake_eval_action)

    client = TestClient(create_app())
    response = client.get(
        "/v1/eval/status",
        params={
            "name": "oracle-main-capability",
            "model": "Qwen/Qwen3-14B",
            "adapter": "/mnt/d/src/training/output/qwen3-oracle-14b-v2/final",
            "prompt_pack": "/mnt/d/src/training/evals/oracle_main_capability_eval_v1.jsonl",
            "out": "/mnt/d/src/training/evals/runs/qwen3_oracle_14b_v2_oracle_main_capability_eval_v1.jsonl",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "running"
    assert payload["name"] == "oracle-main-capability"
    assert "ts" in payload


def test_eval_start_endpoint_validates_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    monkeypatch.setattr(wsl, "eval_action", lambda action, **kwargs: {"state": "running"})

    client = TestClient(create_app())
    response = client.post("/v1/eval/start", json={"name": "oracle-main-capability"})
    assert response.status_code == 400
    assert "missing required eval fields" in response.text
