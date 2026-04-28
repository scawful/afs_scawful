from __future__ import annotations

from pathlib import Path

import pytest


def test_hostd_version_endpoint_reports_source_identity() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from afs_scawful.windows import hostd

    client = TestClient(hostd.create_app(token="secret"))
    response = client.get("/v1/version", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    module_path = Path(hostd.__file__).resolve()
    assert payload["service"] == "afs-hostd"
    assert payload["phase"] == "0"
    assert payload["hostd_api_version"] == hostd.HOSTD_API_VERSION
    assert payload["module"]["path"] == str(module_path)
    assert payload["module"]["sha256"] == hostd._file_sha256(module_path)
    assert payload["module"]["size_bytes"] == module_path.stat().st_size
    assert payload["git"]["available"] in {True, False}


def test_hostd_status_embeds_version_payload() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from afs_scawful.windows import hostd

    client = TestClient(hostd.create_app())
    response = client.get("/v1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["hostd_api_version"] == hostd.HOSTD_API_VERSION
    assert "version" in payload["implemented_surfaces"]
    assert payload["version"]["module"]["sha256"] == hostd._file_sha256(Path(hostd.__file__).resolve())
