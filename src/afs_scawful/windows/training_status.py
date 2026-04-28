from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_WSL_TRAIN_ROOT = "/mnt/d/src/training"


def status_snapshot(
    *,
    task: str,
    config: str,
    train_root: str | None = None,
    run_dir: str | Path | None = None,
    log_dir: str | Path | None = None,
    tail: int | None = None,
) -> dict[str, Any]:
    task_value = str(task or "").strip()
    config_value = str(config or "").strip()
    train_root_path = resolve_train_root(train_root)
    config_path = resolve_config_path(config_value, train_root_path)
    run_dir_path = resolve_run_dir(run_dir, train_root_path)
    log_dir_path = resolve_log_dir(log_dir, train_root_path)
    tail_lines = 40 if tail is None else max(int(tail), 0)

    warnings: list[str] = []
    config_data: dict[str, Any] = {}
    output_dir: Path | None = None
    metrics_path: Path | None = None
    run_state_path: Path | None = None
    config_error: str | None = None
    if config_value:
        try:
            config_data = parse_config(config_path)
            output_dir = resolve_output_dir_from_config(config_data, train_root_path)
            metrics_path = output_dir / "metrics.jsonl"
            run_state_path = output_dir / "run_state.json"
        except Exception as exc:
            config_error = str(exc)
            warnings.append(f"config parse failed: {exc}")

    stems = runtime_stems(task_value, config_path if config_value else None, config_data)
    pid_file = resolve_runtime_file(
        stems,
        ".pid",
        candidate_pid_dirs(
            run_dir_path,
            log_dir_path,
            train_root_path,
            explicit_run_dir=run_dir is not None,
            explicit_log_dir=log_dir is not None,
        ),
        fallback=run_dir_path / f"{stems[0]}.pid",
    )
    stdout_log = resolve_runtime_file(
        stems,
        ".out.log",
        candidate_log_dirs(log_dir_path, train_root_path, explicit_log_dir=log_dir is not None),
        fallback=log_dir_path / f"{stems[0]}.out.log",
    )
    stderr_log = resolve_runtime_file(
        stems,
        ".err.log",
        candidate_log_dirs(log_dir_path, train_root_path, explicit_log_dir=log_dir is not None),
        fallback=log_dir_path / f"{stems[0]}.err.log",
    )

    pid = _read_pid(pid_file)
    pid_live = _pid_is_live(pid)
    process_command = None
    if not pid_live:
        process_match = find_training_process(config_path if config_value else None, task_value, stems)
        if process_match:
            pid = process_match["pid"]
            pid_live = True
            process_command = process_match.get("command")
            warnings.append("pid file is missing or stale; matched running process by config/task")

    metrics = parse_metrics(metrics_path) if metrics_path else {}
    run_state = parse_run_state(run_state_path) if run_state_path else {}
    if metrics_path and not metrics_path.exists():
        warnings.append(f"metrics file missing: {metrics_path}")
    if run_state_path and not run_state_path.exists():
        warnings.append(f"run state file missing: {run_state_path}")

    train_start = metrics.get("train_start")
    last_metric = metrics.get("last_metric")
    last_checkpoint = metrics.get("last_checkpoint")
    train_end = metrics.get("train_end")
    phase = run_state.get("phase")
    phase_status = run_state.get("status")
    phase_updated_at = run_state.get("updated_at")
    phase_message = run_state.get("message")
    phase_error = run_state.get("error_type")

    current_step = metrics.get("current_step")
    total_steps = metrics.get("total_steps")
    last_loss = metrics.get("last_loss")
    progress_pct = None
    if isinstance(current_step, int) and isinstance(total_steps, int) and total_steps > 0:
        progress_pct = round((current_step / total_steps) * 100, 1)

    eta_seconds = metrics.get("eta_seconds")
    eta = _format_duration(eta_seconds) if isinstance(eta_seconds, (int, float)) else None

    if pid_live:
        state = "running"
    elif train_end:
        state = "completed"
    elif phase_status == "completed":
        state = "completed"
    elif phase_status == "failed":
        state = "failed"
    else:
        state = "stopped"

    if not pid_live and phase_status == "running" and not train_end:
        warnings.append(f"last known phase before stop: {phase}")

    payload: dict[str, Any] = {
        "source": "filesystem",
        "state": state,
        "task": task_value,
        "config": str(config_path),
        "train_root": str(train_root_path),
        "output_dir": str(output_dir) if output_dir else None,
        "metrics_path": str(metrics_path) if metrics_path else None,
        "run_state_path": str(run_state_path) if run_state_path else None,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "pid_file": str(pid_file),
        "pid": pid if pid_live else None,
        "pid_live": pid_live,
        "process_command": process_command,
        "phase": phase,
        "phase_status": phase_status,
        "phase_updated_at": phase_updated_at,
        "phase_message": phase_message,
        "phase_error": phase_error,
        "run_state": run_state or None,
        "current_step": current_step,
        "total_steps": total_steps,
        "progress_pct": progress_pct,
        "last_loss": last_loss,
        "eta_seconds": eta_seconds,
        "eta": eta,
        "train_start": train_start,
        "last_metric": last_metric,
        "last_checkpoint": last_checkpoint,
        "train_end": train_end,
        "stdout_tail": _tail_lines(stdout_log, tail_lines),
        "stderr_tail": _tail_lines(stderr_log, tail_lines),
        "checkpoints": list_checkpoints(output_dir),
        "warnings": warnings,
    }
    if config_error:
        payload["config_error"] = config_error
    return payload


def resolve_train_root(train_root: str | None) -> Path:
    candidate = str(train_root or DEFAULT_WSL_TRAIN_ROOT).strip()
    return _path_from_maybe_wsl(candidate)


def resolve_run_dir(run_dir: str | Path | None, train_root: Path) -> Path:
    if run_dir is not None:
        return _path_from_maybe_wsl(str(run_dir))
    return _default_afs_root(train_root) / "run"


def resolve_log_dir(log_dir: str | Path | None, train_root: Path) -> Path:
    if log_dir is not None:
        return _path_from_maybe_wsl(str(log_dir))
    return _default_afs_root(train_root) / "logs"


def resolve_config_path(config: str, train_root: Path) -> Path:
    if not config:
        raise ValueError("config is required")
    if config.startswith("/workspace/training"):
        return _normalize_workspace_path(config, train_root)
    if config.startswith("/mnt/"):
        return _path_from_maybe_wsl(config)
    config_path = Path(config)
    if config_path.is_absolute():
        return config_path
    return train_root / config.replace("/", os.sep)


def resolve_output_dir(config_path: Path, train_root: Path) -> Path:
    data = parse_config(config_path)
    return resolve_output_dir_from_config(data, train_root)


def parse_config(config_path: Path) -> dict[str, Any]:
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def resolve_output_dir_from_config(data: dict[str, Any], train_root: Path) -> Path:
    output_value = str(data.get("paths", {}).get("output_dir") or "").strip()
    if not output_value:
        return train_root / "output"
    return _normalize_workspace_path(output_value, train_root)


def runtime_stems(task: str, config_path: Path | None, config_data: dict[str, Any] | None = None) -> list[str]:
    raw_values = [task]
    model_name = (config_data or {}).get("model", {}).get("name")
    if isinstance(model_name, str):
        raw_values.append(model_name)
    if config_path is not None:
        raw_values.append(config_path.stem)

    stems: list[str] = []
    for value in raw_values:
        for candidate in runtime_stem_aliases(value):
            if candidate and candidate not in stems:
                stems.append(candidate)
    return stems or ["training"]


def runtime_stem_aliases(value: str) -> list[str]:
    normalized = _slugify(str(value or "").strip().replace("_", "-"))
    aliases = [normalized]
    aliases.append(re.sub(r"-v([0-9]+)$", r"\1", normalized))
    aliases.append(re.sub(r"-v([0-9]+)-(dpo|kto|sft)-", r"-\2-", normalized))
    return [alias for alias in aliases if alias]


def candidate_pid_dirs(
    run_dir: Path,
    log_dir: Path,
    train_root: Path,
    *,
    explicit_run_dir: bool,
    explicit_log_dir: bool,
) -> list[Path]:
    dirs = [run_dir]
    if not explicit_run_dir:
        dirs.extend([train_root / "run", log_dir])
        if not explicit_log_dir:
            dirs.append(train_root / "logs")
    return unique_paths(dirs)


def candidate_log_dirs(log_dir: Path, train_root: Path, *, explicit_log_dir: bool) -> list[Path]:
    dirs = [log_dir]
    if not explicit_log_dir:
        dirs.append(train_root / "logs")
    return unique_paths(dirs)


def resolve_runtime_file(stems: list[str], suffix: str, dirs: list[Path], *, fallback: Path) -> Path:
    candidates = [directory / f"{stem}{suffix}" for directory in dirs for stem in stems]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else fallback


def find_training_process(config_path: Path | None, task: str, stems: list[str]) -> dict[str, Any] | None:
    needles = runtime_process_needles(config_path, task, stems)
    if not needles:
        return None
    if os.name == "nt":
        return find_windows_python_process(needles)
    return find_posix_python_process(needles)


def runtime_process_needles(config_path: Path | None, task: str, stems: list[str]) -> list[str]:
    values: list[str] = []
    if config_path is not None:
        values.extend([str(config_path), config_path.name])
    values.extend([task, *stems])

    needles: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if len(normalized) >= 4 and normalized not in needles:
            needles.append(normalized)
    return needles


def find_windows_python_process(needles: list[str]) -> dict[str, Any] | None:
    script = (
        "$needles = @("
        + ", ".join(powershell_quote(needle) for needle in needles)
        + ")\n"
        "$procs = Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' OR Name = 'pythonw.exe'\"\n"
        "foreach ($proc in $procs) {\n"
        "  $cmd = [string]$proc.CommandLine\n"
        "  if (-not $cmd) { continue }\n"
        "  foreach ($needle in $needles) {\n"
        "    if ($needle -and $cmd.Contains([string]$needle)) {\n"
        "      [pscustomobject]@{ pid = [int]$proc.ProcessId; command = $cmd } | ConvertTo-Json -Compress\n"
        "      exit 0\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    pid = _coerce_int(data.get("pid"))
    if pid is None or not _pid_is_live(pid):
        return None
    return {"pid": pid, "command": data.get("command")}


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def find_posix_python_process(needles: list[str]) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,comm=,args="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    current_pid = os.getpid()
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 3:
            continue
        pid = _coerce_int(parts[0])
        command_name = parts[1]
        command = parts[2]
        if pid is None or pid == current_pid or "python" not in command_name.lower():
            continue
        if any(needle in command for needle in needles):
            return {"pid": pid, "command": command}
    return None


def unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def list_checkpoints(output_dir: Path | None) -> list[str]:
    if output_dir is None or not output_dir.exists():
        return []
    return sorted(
        entry.name
        for entry in output_dir.iterdir()
        if entry.is_dir() and entry.name.startswith("checkpoint-")
    )


def parse_metrics(metrics_path: Path | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "train_start": None,
        "last_metric": None,
        "last_checkpoint": None,
        "train_end": None,
        "current_step": None,
        "total_steps": None,
        "last_loss": None,
        "eta_seconds": None,
    }
    if metrics_path is None or not metrics_path.exists():
        return payload

    records: list[dict[str, Any]] = []
    for line in metrics_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        return payload

    train_start = next((row for row in records if row.get("type") == "train_start"), None)
    last_metric = next(
        (row for row in reversed(records) if row.get("type") == "metrics" and row.get("step") is not None),
        None,
    )
    last_checkpoint = next((row for row in reversed(records) if row.get("type") == "checkpoint"), None)
    train_end = next((row for row in reversed(records) if row.get("type") == "train_end"), None)
    last_progress = next(
        (
            row
            for row in reversed(records)
            if row.get("type") in {"metrics", "checkpoint", "train_end"} and row.get("step") is not None
        ),
        None,
    )
    last_loss_record = next(
        (row for row in reversed(records) if row.get("loss") is not None or row.get("last_loss") is not None),
        None,
    )

    payload["train_start"] = train_start
    payload["last_metric"] = last_metric
    payload["last_checkpoint"] = last_checkpoint
    payload["train_end"] = train_end
    payload["total_steps"] = _coerce_int(train_start.get("total_steps")) if isinstance(train_start, dict) else None
    payload["current_step"] = _coerce_int(last_progress.get("step")) if isinstance(last_progress, dict) else None
    if isinstance(last_loss_record, dict):
        payload["last_loss"] = last_loss_record.get("loss", last_loss_record.get("last_loss"))
    payload["eta_seconds"] = _estimate_eta_seconds(train_start, last_progress, payload["total_steps"])
    return payload


def parse_run_state(run_state_path: Path | None) -> dict[str, Any]:
    if run_state_path is None or not run_state_path.exists():
        return {}
    try:
        data = json.loads(run_state_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _estimate_eta_seconds(
    train_start: dict[str, Any] | None,
    last_progress: dict[str, Any] | None,
    total_steps: int | None,
) -> int | None:
    if not isinstance(train_start, dict) or not isinstance(last_progress, dict):
        return None
    current_step = _coerce_int(last_progress.get("step"))
    if current_step is None or total_steps is None or current_step <= 0 or total_steps <= 0:
        return None
    if current_step >= total_steps:
        return 0
    start_ts = _parse_ts(train_start.get("timestamp"))
    last_ts = _parse_ts(last_progress.get("timestamp"))
    if start_ts is None or last_ts is None:
        return None
    elapsed = (last_ts - start_ts).total_seconds()
    if elapsed <= 0:
        return None
    remaining = (elapsed / current_step) * (total_steps - current_step)
    return max(int(round(remaining)), 0)


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _slugify(task: str) -> str:
    if not task:
        return "training"
    return re.sub(r"[^A-Za-z0-9._-]", "_", task)


def _read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    raw = pid_file.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _pid_is_live(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_is_live(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _windows_pid_is_live(pid: int) -> bool:
    try:
        import ctypes
    except ImportError:
        return False

    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _tail_lines(path: Path, count: int) -> list[str]:
    if count <= 0 or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-count:]


def _default_afs_root(train_root: Path) -> Path:
    drive = train_root.drive.rstrip(":")
    if drive:
        return Path(f"{drive}:\\afs_training")
    return Path("/mnt/d/afs_training")


def _normalize_workspace_path(value: str, train_root: Path) -> Path:
    if value.startswith("/workspace/training"):
        suffix = value[len("/workspace/training"):].lstrip("/").replace("/", os.sep)
        return train_root if not suffix else train_root / suffix
    return _path_from_maybe_wsl(value)


def _path_from_maybe_wsl(value: str) -> Path:
    candidate = str(value or "").strip()
    if candidate.startswith("/mnt/") and len(candidate) >= 7:
        drive = candidate[5]
        if drive.isalpha() and candidate[6] == "/":
            suffix = candidate[7:].replace("/", "\\")
            return Path(f"{drive.upper()}:\\{suffix}")
    return Path(candidate)


def _format_duration(seconds: int | float | None) -> str | None:
    if seconds is None:
        return None
    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s"
