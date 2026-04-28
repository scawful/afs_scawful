from __future__ import annotations

import json

import pytest

from afs_scawful.windows import power
from afs_scawful.windows import wsl


def test_current_policy_parses_active_scheme_and_ac_values(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv(power.STATE_PATH_ENV, str(tmp_path / "power_state.json"))

    def fake_run(args: list[str], **kwargs) -> str:
        if args == ["/getactivescheme"]:
            return "Power Scheme GUID: 11111111-2222-3333-4444-555555555555  (Balanced)"
        if args[-1] == power.STANDBY_IDLE:
            return "Current AC Power Setting Index: 0x00000708"
        if args[-1] == power.HIBERNATE_IDLE:
            return "Current AC Power Setting Index: 0x00001c20"
        raise AssertionError(args)

    monkeypatch.setattr(power, "_run_powercfg", fake_run)
    payload = power.current_policy()
    assert payload["active_scheme_guid"] == "11111111-2222-3333-4444-555555555555"
    assert payload["active_scheme_name"] == "Balanced"
    assert payload["ac_standby_seconds"] == 1800
    assert payload["ac_hibernate_seconds"] == 7200
    assert payload["sleep_suppressed_on_ac"] is False
    assert payload["saved_state_present"] is False


def test_suppress_and_restore_sleep_policy_round_trips(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    state_path = tmp_path / "power_state.json"
    monkeypatch.setenv(power.STATE_PATH_ENV, str(state_path))
    values = {
        power.STANDBY_IDLE: 1800,
        power.HIBERNATE_IDLE: 7200,
    }
    seen: list[list[str]] = []

    def fake_run(args: list[str], **kwargs) -> str:
        seen.append(args)
        if args == ["/getactivescheme"]:
            return "Power Scheme GUID: abcdefab-cdef-abcd-efab-cdefabcdefab  (High performance)"
        if args[:4] == ["/query", "SCHEME_CURRENT", power.SLEEP_SUBGROUP, power.STANDBY_IDLE]:
            return f"Current AC Power Setting Index: 0x{values[power.STANDBY_IDLE]:08x}"
        if args[:4] == ["/query", "SCHEME_CURRENT", power.SLEEP_SUBGROUP, power.HIBERNATE_IDLE]:
            return f"Current AC Power Setting Index: 0x{values[power.HIBERNATE_IDLE]:08x}"
        if args[:4] == ["/setacvalueindex", "SCHEME_CURRENT", power.SLEEP_SUBGROUP, power.STANDBY_IDLE]:
            values[power.STANDBY_IDLE] = int(args[4])
            return ""
        if args[:4] == ["/setacvalueindex", "SCHEME_CURRENT", power.SLEEP_SUBGROUP, power.HIBERNATE_IDLE]:
            values[power.HIBERNATE_IDLE] = int(args[4])
            return ""
        if args[:1] == ["/S"]:
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(power, "_run_powercfg", fake_run)

    suppressed = power.suppress_sleep_for_training()
    assert suppressed["after"]["sleep_suppressed_on_ac"] is True
    assert values == {power.STANDBY_IDLE: 0, power.HIBERNATE_IDLE: 0}
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["ac_standby_seconds"] == 1800
    assert saved["ac_hibernate_seconds"] == 7200

    restored = power.restore_sleep_policy()
    assert restored["restored"] is True
    assert values == {power.STANDBY_IDLE: 1800, power.HIBERNATE_IDLE: 7200}
    assert not state_path.exists()


def test_restore_sleep_policy_handles_missing_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv(power.STATE_PATH_ENV, str(tmp_path / "power_state.json"))

    def fake_run(args: list[str], **kwargs) -> str:
        if args == ["/getactivescheme"]:
            return "Power Scheme GUID: 11111111-2222-3333-4444-555555555555  (Balanced)"
        return "Current AC Power Setting Index: 0x00000000"

    monkeypatch.setattr(power, "_run_powercfg", fake_run)
    restored = power.restore_sleep_policy()
    assert restored["restored"] is False
    assert restored["reason"] == "no_saved_state"


def test_hostd_training_start_suppresses_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    monkeypatch.setattr(power, "suppress_sleep_for_training", lambda: {"changed": True, "after": {"sleep_suppressed_on_ac": True}})
    monkeypatch.setattr(
        wsl,
        "training_action",
        lambda *args, **kwargs: {"state": "running", "task": kwargs["task"]},
    )

    client = TestClient(create_app())
    response = client.post(
        "/v1/training/start",
        json={"task": "oracle-main", "config": "configs/zelda/qwen3_oracle_14b_v2.toml"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "running"
    assert payload["power"]["changed"] is True


def test_hostd_training_stop_restores_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from afs_scawful.windows.hostd import create_app

    monkeypatch.setattr(power, "restore_sleep_policy", lambda: {"restored": True})
    monkeypatch.setattr(
        wsl,
        "training_action",
        lambda *args, **kwargs: {"state": "stopped", "task": kwargs["task"]},
    )

    client = TestClient(create_app())
    response = client.post(
        "/v1/training/stop",
        json={"task": "oracle-main", "config": "configs/zelda/qwen3_oracle_14b_v2.toml"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "stopped"
    assert payload["power"]["restored"] is True
