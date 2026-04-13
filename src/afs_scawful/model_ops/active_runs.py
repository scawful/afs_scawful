"""Active-run probing and scratchpad rendering helpers."""

from __future__ import annotations

import json
import shlex
import subprocess
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from .tracks import apply_track_overrides, get_phase_order, validate_track_spec


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture output."""

    return subprocess.run(command, text=True, capture_output=True, check=check)


def remote_command(host: str, port: int, command: str) -> list[str]:
    """Build an SSH command for a remote probe."""

    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-p",
        str(port),
        f"root@{host}",
        command,
    ]


def normalize_remote_dir(remote_dir: str) -> str:
    """Expand ~/ for remote bash invocations."""

    if remote_dir.startswith("~/"):
        return "$HOME/" + remote_dir[2:]
    return remote_dir


def _phase_probe_script(track_spec: dict[str, Any]) -> str:
    phases = {
        name: {
            "pid": phase.get("pid"),
            "log": phase.get("log"),
            "artifact_path": phase.get("artifact_path"),
            "process_pattern": phase.get("process_pattern", ""),
        }
        for name, phase in validate_track_spec(track_spec)["phases"].items()
    }
    payload = json.dumps(phases)
    return f"""
from pathlib import Path
import json
import subprocess

phase_specs = json.loads({payload!r})

def phase_info(spec):
    pid_path = Path(spec["pid"]) if spec.get("pid") else None
    log_path = Path(spec["log"]) if spec.get("log") else None
    artifact_path = Path(spec["artifact_path"]) if spec.get("artifact_path") else None
    pid = pid_path.read_text().strip() if pid_path and pid_path.exists() else None
    running = bool(pid and Path(f"/proc/{{pid}}").exists())
    process_pattern = spec.get("process_pattern") or ""
    if not running and process_pattern:
        proc = subprocess.run(
            f"ps -ef | grep -E {{process_pattern!r}} | grep -v grep | head -n 1",
            shell=True,
            capture_output=True,
            text=True,
        )
        line = proc.stdout.strip()
        if line:
            parts = line.split()
            if len(parts) > 1:
                pid = parts[1]
            running = True
    return {{
        "pid": pid,
        "running": running,
        "artifact_ready": bool(artifact_path and artifact_path.exists()),
        "merged": bool(artifact_path and artifact_path.exists()),
        "artifact_path": spec.get("artifact_path"),
        "log": spec.get("log"),
        "log_exists": bool(log_path and log_path.exists()),
        "log_size": log_path.stat().st_size if log_path and log_path.exists() else 0,
    }}

print(json.dumps({{name: phase_info(spec) for name, spec in phase_specs.items()}}))
"""


def probe_remote_run(
    run_cfg: dict[str, Any],
    track_spec: dict[str, Any],
    *,
    runner=run,
) -> dict[str, Any]:
    """Probe a remote run over SSH and return phase status."""

    host = run_cfg["host"]
    port = int(run_cfg["port"])
    remote_dir = normalize_remote_dir(run_cfg["remote_dir"])
    script = _phase_probe_script(track_spec)
    inner_command = f"cd {remote_dir} && python3 - <<'PY'\n{script}\nPY"
    command = f"bash -lc {shlex.quote(inner_command)}"
    result = runner(remote_command(host, port, command), check=False)
    if result.returncode != 0:
        return {
            "error": (result.stderr or result.stdout).strip() or "remote probe failed",
        }
    return json.loads(result.stdout)


def _normalize_run_overrides(run_cfg: dict[str, Any]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    phase_overrides = deepcopy(run_cfg.get("phase_overrides", {}))
    for phase_name, phase_override in run_cfg.get("remote_override", {}).items():
        phase_overrides.setdefault(phase_name, {}).update(phase_override)
    if phase_overrides:
        overrides["phase_overrides"] = phase_overrides
    if run_cfg.get("auto_start_commands"):
        overrides["auto_start_commands"] = deepcopy(run_cfg["auto_start_commands"])
    if run_cfg.get("phase_order"):
        overrides["phase_order"] = list(run_cfg["phase_order"])
    return overrides


def apply_run_overrides(track_spec: dict[str, Any], run_cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply run-level overrides to a track spec."""

    return apply_track_overrides(track_spec, _normalize_run_overrides(run_cfg))


def heading_for_output(output_path: Path) -> str:
    """Build a markdown heading based on the output filename."""

    stem = output_path.stem
    parts = stem.split("-")
    if len(parts) >= 3 and all(part.isdigit() for part in parts[-3:]):
        suffix = "-".join(parts[-3:])
    else:
        suffix = date.today().isoformat()
    return f"# active runs - {suffix}"


def _phase_ready(status: dict[str, Any]) -> bool:
    return bool(status.get("artifact_ready") or status.get("merged"))


def _phase_title(track_spec: dict[str, Any], phase_name: str) -> str:
    return track_spec["phases"][phase_name].get("title", phase_name.replace("_", " ").title())


def _phase_summary_lines(track_spec: dict[str, Any], status: dict[str, Any]) -> list[str]:
    phase_order = get_phase_order(track_spec)
    if all(_phase_ready(status.get(name, {})) for name in phase_order):
        return ["- phase: Final artifact ready"]

    for index, phase_name in enumerate(phase_order):
        phase_status = status.get(phase_name, {})
        title = _phase_title(track_spec, phase_name)
        if phase_status.get("running"):
            return [f"- phase: {title} running"]
        if _phase_ready(phase_status):
            continue
        previous_ready = index == 0 or all(_phase_ready(status.get(name, {})) for name in phase_order[:index])
        if previous_ready:
            lines = [f"- phase: {title} ready; idle on last probe"]
            command = track_spec.get("auto_start_commands", {}).get(phase_name)
            if command:
                lines.append(f"- next action: `{command}`")
            return lines
    return ["- phase: unknown / needs manual check"]


def render_run_section(
    run_cfg: dict[str, Any],
    track_spec: dict[str, Any],
    status: dict[str, Any] | None,
    *,
    probe_skipped: bool = False,
) -> list[str]:
    """Render one active-run section."""

    lines = [f"## {run_cfg['title']}", ""]
    lines.append(f"- track: `{run_cfg['track']}`")
    if run_cfg.get("run_tag"):
        lines.append(f"- run tag: `{run_cfg['run_tag']}`")
    if run_cfg.get("instance_id"):
        lines.append(f"- instance: `{run_cfg['instance_id']}`")
    if run_cfg.get("host") and run_cfg.get("port"):
        lines.append(f"- host: `{run_cfg['host']}:{run_cfg['port']}`")
    if run_cfg.get("label"):
        lines.append(f"- label: `{run_cfg['label']}`")
    if run_cfg.get("state"):
        lines.append(f"- state: `{run_cfg['state']}`")
    lines.append(f"- remote root: `{run_cfg['remote_dir']}`")
    if run_cfg.get("launcher"):
        lines.append(f"- launcher: `{run_cfg['launcher']}`")
    if probe_skipped:
        lines.append("- remote probe: skipped by config")

    phase_order = get_phase_order(track_spec)
    if status and not status.get("error"):
        for phase_name in phase_order:
            phase_status = status.get(phase_name, {})
            title = _phase_title(track_spec, phase_name)
            lines.append(
                f"- {title}: running={phase_status.get('running', False)} "
                f"merged={_phase_ready(phase_status)} log=`{phase_status.get('log', track_spec['phases'][phase_name].get('log', ''))}`"
            )
        lines.extend(_phase_summary_lines(track_spec, status))
    elif status and status.get("error"):
        lines.append(f"- status probe error: `{status['error']}`")

    for note in run_cfg.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return lines


def load_active_runs_config(config_path: Path) -> dict[str, Any]:
    """Load an active-runs config file."""

    return json.loads(config_path.read_text(encoding="utf-8"))


def render_active_runs_note(
    config: dict[str, Any],
    track_specs: dict[str, dict[str, Any]],
    *,
    output_path: Path | None = None,
    no_probe_remote: bool = False,
    runner=run,
) -> str:
    """Render a complete active-runs markdown note."""

    resolved_output = output_path or Path(config.get("output_path", f"active-runs-{date.today().isoformat()}.md"))
    lines = [heading_for_output(resolved_output), ""]

    for run_cfg in config.get("runs", []):
        base_track_spec = track_specs[run_cfg["track"]]
        track_spec = apply_run_overrides(base_track_spec, run_cfg)
        probe_skipped = bool(run_cfg.get("probe_remote") is False)
        should_probe = not no_probe_remote and not probe_skipped and run_cfg.get("host") and run_cfg.get("port")
        status = probe_remote_run(run_cfg, track_spec, runner=runner) if should_probe else None
        lines.extend(render_run_section(run_cfg, track_spec, status, probe_skipped=probe_skipped))

    other_cloud_state = config.get("other_cloud_state", [])
    if other_cloud_state:
        lines.extend(["## Other cloud state", ""])
        for item in other_cloud_state:
            lines.append(f"- {item}")
        lines.append("")

    local_artifacts = config.get("local_artifacts", [])
    if local_artifacts:
        lines.extend(["## Local artifacts", ""])
        for item in local_artifacts:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_active_runs_note(
    config_path: Path,
    track_specs: dict[str, dict[str, Any]],
    *,
    output_path: Path | None = None,
    no_probe_remote: bool = False,
    runner=run,
) -> Path:
    """Render and write an active-runs note from config."""

    config = load_active_runs_config(config_path)
    resolved_output = output_path or Path(config["output_path"])
    note = render_active_runs_note(
        config,
        track_specs,
        output_path=resolved_output,
        no_probe_remote=no_probe_remote,
        runner=runner,
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(note, encoding="utf-8")
    return resolved_output
