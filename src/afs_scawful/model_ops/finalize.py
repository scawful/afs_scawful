"""Generic remote finalization helpers for multi-phase training runs."""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .. import vast
from .active_runs import normalize_remote_dir, probe_remote_run, remote_command
from .tracks import get_phase_order, validate_track_spec


@dataclass(frozen=True)
class RemoteRunTarget:
    """Resolved remote SSH target for a training run."""

    host: str
    port: int
    remote_dir: str
    instance_id: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class FinalizeResult:
    """Finalizer output after remote artifacts are downloaded."""

    completed_phase: str
    local_run_dir: Path
    downloaded: dict[str, Path]


def run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture output."""

    return subprocess.run(command, cwd=cwd, check=check, text=True, capture_output=True)


def timestamp() -> str:
    """Return a human-readable timestamp."""

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def print_status(message: str) -> None:
    """Print a timestamped status line."""

    print(f"[{timestamp()}] {message}", flush=True)


def resolve_remote_target(
    *,
    host: str | None = None,
    port: int | None = None,
    remote_dir: str,
    instance_id: str | None = None,
    instance_name: str | None = None,
    metadata_path: Path | None = None,
    instances_dir: Path | None = None,
) -> RemoteRunTarget:
    """Resolve a remote target either directly or through AFS Vast metadata."""

    if host and port:
        return RemoteRunTarget(host=host, port=int(port), remote_dir=remote_dir, instance_id=instance_id)

    resolved_id, resolved_label, metadata = vast.resolve_instance_selection(
        instance_id=instance_id,
        name=instance_name,
        metadata_path=metadata_path,
        instances_dir=instances_dir,
    )
    instance = vast.fetch_instance_info(resolved_id)
    ssh_host = instance.ssh_host or metadata.get("ssh_host")
    ssh_port = instance.ssh_port or metadata.get("ssh_port")
    if not ssh_host or not ssh_port:
        raise ValueError("resolved Vast instance is missing SSH host or port")
    return RemoteRunTarget(
        host=str(ssh_host),
        port=int(ssh_port),
        remote_dir=remote_dir,
        instance_id=resolved_id,
        label=instance.label or resolved_label,
    )


def scp_command(host: str, port: int, remote_path: str, local_path: str) -> list[str]:
    """Build a recursive SCP command."""

    return [
        "scp",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-P",
        str(port),
        "-r",
        f"root@{host}:{remote_path}",
        local_path,
    ]


def get_remote_log_tail(
    target: RemoteRunTarget,
    log_name: str,
    *,
    lines: int = 60,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run,
) -> str:
    """Read the tail of a remote log file."""

    command = (
        f"cd {normalize_remote_dir(target.remote_dir)} && "
        f"python3 - <<'PY'\n"
        f"from pathlib import Path\n"
        f"p = Path({log_name!r})\n"
        f"if p.exists():\n"
        f"    data = p.read_text(errors='replace').splitlines()\n"
        f"    print('\\n'.join(data[-{lines}:]))\n"
        f"PY"
    )
    result = runner(remote_command(target.host, target.port, f"bash -lc {shlex.quote(command)}"), check=False)
    return result.stdout.strip()


def ensure_remote_phase_started(
    target: RemoteRunTarget,
    track_spec: dict[str, Any],
    phase_name: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run,
) -> bool:
    """Start the next phase remotely when an auto-start command exists."""

    validated = validate_track_spec(track_spec)
    command = validated.get("auto_start_commands", {}).get(phase_name)
    if not command:
        return False

    phase_spec = validated["phases"][phase_name]
    pid_path = phase_spec.get("pid")
    shell_command = f"cd {normalize_remote_dir(target.remote_dir)} || exit 1\n{command}"
    if pid_path:
        shell_command += f"\nprintf '%s\\n' \"$!\" > {shlex.quote(pid_path)}"
    runner(remote_command(target.host, target.port, f"bash -lc {shlex.quote(shell_command)}"), check=False)
    return True


def _phase_ready(status: dict[str, Any]) -> bool:
    return bool(status.get("artifact_ready") or status.get("merged"))


def wait_for_remote_completion(
    target: RemoteRunTarget,
    track_spec: dict[str, Any],
    *,
    poll_seconds: int = 120,
    wait_for_start: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run,
    status_provider: Callable[[RemoteRunTarget, dict[str, Any]], dict[str, Any]] | None = None,
    log_tail_provider: Callable[[RemoteRunTarget, str], str] | None = None,
    phase_starter: Callable[[RemoteRunTarget, dict[str, Any], str], bool] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    status_printer: Callable[[str], None] = print_status,
) -> str:
    """Wait for the final phase artifact to appear, auto-starting later phases when configured."""

    validated = validate_track_spec(track_spec)
    phase_order = get_phase_order(validated)
    final_phase = phase_order[-1]
    seen_start = False
    seen_ready: set[str] = set()
    probe = status_provider or (
        lambda remote_target, spec: probe_remote_run(
            {"host": remote_target.host, "port": remote_target.port, "remote_dir": remote_target.remote_dir},
            spec,
            runner=runner,
        )
    )
    tail = log_tail_provider or (lambda remote_target, log_name: get_remote_log_tail(remote_target, log_name, runner=runner))
    starter = phase_starter or (
        lambda remote_target, spec, phase_name: ensure_remote_phase_started(
            remote_target,
            spec,
            phase_name,
            runner=runner,
        )
    )

    while True:
        status = probe(target, validated)
        if status.get("error"):
            raise RuntimeError(status["error"])

        if any(phase.get("running") or _phase_ready(phase) for phase in status.values()):
            seen_start = True

        summary = " | ".join(
            f"{phase_name}: running={status.get(phase_name, {}).get('running', False)} merged={_phase_ready(status.get(phase_name, {}))}"
            for phase_name in phase_order
        )
        status_printer(f"remote status | {summary}")

        if _phase_ready(status.get(final_phase, {})):
            status_printer(f"remote {final_phase} artifact is ready")
            return final_phase

        if wait_for_start and not seen_start:
            sleeper(poll_seconds)
            continue

        for index, phase_name in enumerate(phase_order):
            phase_status = status.get(phase_name, {})
            if _phase_ready(phase_status):
                if phase_name not in seen_ready:
                    status_printer(f"remote {phase_name} artifact is ready")
                    seen_ready.add(phase_name)
                continue

            if phase_status.get("running"):
                break

            if index == 0:
                raise RuntimeError(
                    f"{phase_name} exited without artifact output.\n\nLast log lines:\n{tail(target, validated['phases'][phase_name].get('log', ''))}"
                )

            previous_phase = phase_order[index - 1]
            if _phase_ready(status.get(previous_phase, {})):
                started = starter(target, validated, phase_name)
                if not started:
                    raise RuntimeError(
                        f"{phase_name} is ready to start but no auto-start command is configured."
                    )
                status_printer(f"requested remote start for {phase_name}")
                break

            raise RuntimeError(
                f"{phase_name} is not running and previous phase {previous_phase} is not ready."
            )

        sleeper(poll_seconds)


def unique_local_run_dir(base_dir: Path) -> Path:
    """Return a timestamp-suffixed run dir if the base dir already exists."""

    if not base_dir.exists():
        return base_dir
    suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
    return base_dir.with_name(f"{base_dir.name}-{suffix}")


def download_remote_artifacts(
    target: RemoteRunTarget,
    local_run_dir: Path,
    track_spec: dict[str, Any],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run,
    status_printer: Callable[[str], None] = print_status,
) -> dict[str, Path]:
    """Download declared remote artifacts into a local run directory."""

    validated = validate_track_spec(track_spec)
    local_run_dir.mkdir(parents=True, exist_ok=True)
    status_printer(f"downloading artifacts into {local_run_dir}")
    remote_base = normalize_remote_dir(target.remote_dir)
    downloaded: dict[str, Path] = {}
    for local_name, remote_rel in validated.get("downloads", {}).items():
        target_path = local_run_dir / local_name
        runner(
            scp_command(target.host, target.port, f"{remote_base}/{remote_rel}", str(target_path)),
            check=True,
        )
        downloaded[local_name] = target_path
    return downloaded


def finalize_remote_run(
    target: RemoteRunTarget,
    track_spec: dict[str, Any],
    *,
    local_run_dir: Path,
    poll_seconds: int = 120,
    wait_for_start: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run,
    sleeper: Callable[[float], None] = time.sleep,
    status_printer: Callable[[str], None] = print_status,
) -> FinalizeResult:
    """Wait for remote completion and download declared artifacts."""

    completed_phase = wait_for_remote_completion(
        target,
        track_spec,
        poll_seconds=poll_seconds,
        wait_for_start=wait_for_start,
        runner=runner,
        sleeper=sleeper,
        status_printer=status_printer,
    )
    downloaded = download_remote_artifacts(
        target,
        local_run_dir,
        track_spec,
        runner=runner,
        status_printer=status_printer,
    )
    return FinalizeResult(
        completed_phase=completed_phase,
        local_run_dir=local_run_dir,
        downloaded=downloaded,
    )
