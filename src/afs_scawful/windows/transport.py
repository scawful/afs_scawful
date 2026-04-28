from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence
from urllib import error, request


DEFAULT_WINDOWS_HOST = "medical-mechanica"
DEFAULT_POWERSHELL_EXE = "powershell"


@dataclass(frozen=True)
class WindowsHostTarget:
    host: str = DEFAULT_WINDOWS_HOST
    ssh_bin: str = "ssh"
    powershell_exe: str = DEFAULT_POWERSHELL_EXE
    ssh_args: tuple[str, ...] = ()

    def ssh_command(self, remote_command: str) -> list[str]:
        return [self.ssh_bin, *self.ssh_args, self.host, remote_command]


def encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def run_local(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), text=True, capture_output=True)


def run_remote_ps(host: str | WindowsHostTarget, script: str) -> subprocess.CompletedProcess[str]:
    target = host if isinstance(host, WindowsHostTarget) else WindowsHostTarget(host=host)
    payload = encode_powershell(script)
    remote_command = f"{target.powershell_exe} -NoProfile -EncodedCommand {payload}"
    return run_local(target.ssh_command(remote_command))


def require_ok(result: subprocess.CompletedProcess[str], context: str) -> str:
    if result.returncode != 0:
        raise RuntimeError(
            f"{context} failed with code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout.strip()


def parse_json_output(result: subprocess.CompletedProcess[str], context: str) -> dict[str, Any]:
    output = require_ok(result, context)
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{context} returned non-JSON output:\n{output}") from exc


def ensure_list(value: object) -> list[object]:
    if value is None or value == {}:
        return []
    if isinstance(value, list):
        return value
    return [value]


@dataclass(frozen=True)
class WindowsHostClient:
    target: WindowsHostTarget = WindowsHostTarget()
    hostd_url: str | None = None
    token: str | None = None
    timeout: float = 10.0

    def run_powershell(self, script: str) -> subprocess.CompletedProcess[str]:
        return run_remote_ps(self.target, script)

    def run_powershell_json(self, script: str, context: str) -> dict[str, Any]:
        return parse_json_output(self.run_powershell(script), context)

    def request_hostd_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.hostd_url:
            raise RuntimeError("hostd_url is not configured")
        url = f"{self.hostd_url.rstrip('/')}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"hostd request failed: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"hostd request failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"hostd returned non-JSON output:\n{raw}") from exc
