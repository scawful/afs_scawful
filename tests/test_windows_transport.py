from __future__ import annotations

import base64
import subprocess

import pytest

from afs_scawful.windows.transport import (
    WindowsHostClient,
    WindowsHostTarget,
    encode_powershell,
    ensure_list,
    parse_json_output,
)


def test_encode_powershell_round_trips_utf16le() -> None:
    script = "Write-Output 'oracle-fast'"
    payload = encode_powershell(script)
    decoded = base64.b64decode(payload).decode("utf-16le")
    assert decoded == script


def test_windows_host_target_builds_expected_ssh_command() -> None:
    target = WindowsHostTarget(host="medical-mechanica", ssh_args=("-o", "BatchMode=yes"))
    command = target.ssh_command("powershell -NoProfile -Command Get-Date")
    assert command == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "medical-mechanica",
        "powershell -NoProfile -Command Get-Date",
    ]


def test_parse_json_output_returns_empty_dict_for_empty_stdout() -> None:
    result = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")
    assert parse_json_output(result, "empty") == {}


def test_parse_json_output_rejects_non_json() -> None:
    result = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="not json", stderr="")
    with pytest.raises(RuntimeError, match="non-JSON"):
        parse_json_output(result, "bad-json")


def test_ensure_list_normalizes_scalar_and_none() -> None:
    assert ensure_list(None) == []
    assert ensure_list({}) == []
    assert ensure_list("oracle") == ["oracle"]
    assert ensure_list(["oracle"]) == ["oracle"]


def test_windows_host_client_requires_hostd_url() -> None:
    client = WindowsHostClient(target=WindowsHostTarget(host="medical-mechanica"))
    with pytest.raises(RuntimeError, match="hostd_url"):
        client.request_hostd_json("/v1/status")
