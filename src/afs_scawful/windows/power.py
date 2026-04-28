from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIVE_SCHEME_RE = re.compile(r"Power Scheme GUID:\s*([0-9A-Fa-f-]+)\s*(?:\((.*?)\))?")
CURRENT_AC_INDEX_RE = re.compile(r"Current AC Power Setting Index:\s*0x([0-9A-Fa-f]+)", re.IGNORECASE)

STATE_PATH_ENV = "AFS_HOSTD_POWER_STATE_PATH"
DEFAULT_STATE_PATH = r"D:\afs_training\run\afs_hostd_power_state.json"
POWERCFG_TIMEOUT_S = 20.0
SLEEP_SUBGROUP = "SUB_SLEEP"
STANDBY_IDLE = "STANDBYIDLE"
HIBERNATE_IDLE = "HIBERNATEIDLE"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def power_state_path() -> Path:
    return Path(os.environ.get(STATE_PATH_ENV, DEFAULT_STATE_PATH))


def _run_powercfg(args: list[str], *, timeout: float = POWERCFG_TIMEOUT_S) -> str:
    result = subprocess.run(
        ["powercfg", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "powercfg failed"
        raise RuntimeError(detail)
    return result.stdout.strip() or result.stderr.strip()


def _parse_active_scheme(output: str) -> tuple[str, str | None]:
    match = ACTIVE_SCHEME_RE.search(output)
    if not match:
        raise RuntimeError(f"could not parse active power scheme from output:\n{output}")
    return match.group(1), (match.group(2) or "").strip() or None


def _parse_current_ac_index(output: str) -> int:
    match = CURRENT_AC_INDEX_RE.search(output)
    if not match:
        raise RuntimeError(f"could not parse AC power setting from output:\n{output}")
    return int(match.group(1), 16)


def active_scheme() -> dict[str, Any]:
    guid, name = _parse_active_scheme(_run_powercfg(["/getactivescheme"]))
    return {"guid": guid, "name": name}


def query_ac_setting_seconds(setting_alias: str, *, scheme: str = "SCHEME_CURRENT") -> int:
    output = _run_powercfg(["/query", scheme, SLEEP_SUBGROUP, setting_alias])
    return _parse_current_ac_index(output)


def set_ac_setting_seconds(setting_alias: str, seconds: int, *, scheme: str = "SCHEME_CURRENT") -> None:
    _run_powercfg(["/setacvalueindex", scheme, SLEEP_SUBGROUP, setting_alias, str(int(seconds))])


def apply_scheme(scheme: str = "SCHEME_CURRENT") -> None:
    _run_powercfg(["/S", scheme])


def load_saved_state() -> dict[str, Any] | None:
    path = power_state_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(payload: dict[str, Any]) -> Path:
    path = power_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def clear_saved_state() -> None:
    path = power_state_path()
    if path.exists():
        path.unlink()


def current_policy() -> dict[str, Any]:
    scheme = active_scheme()
    path = power_state_path()
    saved = load_saved_state()
    standby = query_ac_setting_seconds(STANDBY_IDLE)
    hibernate = query_ac_setting_seconds(HIBERNATE_IDLE)
    return {
        "active_scheme_guid": scheme["guid"],
        "active_scheme_name": scheme["name"],
        "ac_standby_seconds": standby,
        "ac_hibernate_seconds": hibernate,
        "sleep_suppressed_on_ac": standby == 0 and hibernate == 0,
        "saved_state_path": str(path),
        "saved_state_present": path.exists(),
        "saved_state": saved,
    }


def suppress_sleep_for_training() -> dict[str, Any]:
    before = current_policy()
    saved = before.get("saved_state")
    if not isinstance(saved, dict) or saved.get("active_scheme_guid") != before["active_scheme_guid"]:
        save_state(
            {
                "saved_at": _utc_now(),
                "reason": "training_active",
                "active_scheme_guid": before["active_scheme_guid"],
                "active_scheme_name": before["active_scheme_name"],
                "ac_standby_seconds": before["ac_standby_seconds"],
                "ac_hibernate_seconds": before["ac_hibernate_seconds"],
            }
        )
    set_ac_setting_seconds(STANDBY_IDLE, 0)
    set_ac_setting_seconds(HIBERNATE_IDLE, 0)
    apply_scheme()
    after = current_policy()
    return {
        "action": "training_on",
        "changed": not before["sleep_suppressed_on_ac"],
        "before": before,
        "after": after,
        "saved_state_path": str(power_state_path()),
    }


def restore_sleep_policy() -> dict[str, Any]:
    before = current_policy()
    saved = load_saved_state()
    if not isinstance(saved, dict):
        return {
            "action": "restore",
            "restored": False,
            "reason": "no_saved_state",
            "before": before,
            "saved_state_path": str(power_state_path()),
        }
    saved_guid = str(saved.get("active_scheme_guid") or "")
    current_guid = str(before.get("active_scheme_guid") or "")
    if saved_guid and current_guid and saved_guid != current_guid:
        return {
            "action": "restore",
            "restored": False,
            "reason": "active_scheme_changed",
            "before": before,
            "saved_state": saved,
            "saved_state_path": str(power_state_path()),
        }
    set_ac_setting_seconds(STANDBY_IDLE, int(saved.get("ac_standby_seconds") or 0))
    set_ac_setting_seconds(HIBERNATE_IDLE, int(saved.get("ac_hibernate_seconds") or 0))
    apply_scheme()
    clear_saved_state()
    after = current_policy()
    return {
        "action": "restore",
        "restored": True,
        "before": before,
        "after": after,
        "restored_values": {
            "ac_standby_seconds": int(saved.get("ac_standby_seconds") or 0),
            "ac_hibernate_seconds": int(saved.get("ac_hibernate_seconds") or 0),
        },
        "saved_state_path": str(power_state_path()),
    }
