"""Vast AI monitoring helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .alerting import Alert, AlertDispatcher, AlertLevel
from .infra_config import get_config
from .paths import resolve_index_root


@dataclass
class VastInstanceInfo:
    """Vast instance metadata."""

    instance_id: str
    label: Optional[str]
    status: Optional[str]
    gpu_name: Optional[str]
    gpu_ram: Optional[float]
    num_gpus: Optional[int]
    hourly_rate: Optional[float]
    ssh_host: Optional[str]
    ssh_port: Optional[int]


@dataclass
class VastRemoteStatus:
    """Remote training status gathered via SSH."""

    training_status: Optional[str]
    gpu_utilization: Optional[float]
    gpu_memory_used: Optional[float]
    gpu_memory_total: Optional[float]
    disk_used_percent: Optional[float]
    disk_used: Optional[str]
    disk_total: Optional[str]
    disk_mount: Optional[str]
    log_path: Optional[str]
    log_mtime: Optional[int]
    log_age_seconds: Optional[int]
    log_tail: Optional[str]
    log_errors: list[str] = field(default_factory=list)


@dataclass
class VastIssue:
    """Issue detected during health checks."""

    level: AlertLevel
    kind: str
    message: str


@dataclass
class VastStatusReport:
    """Combined Vast instance + remote status."""

    instance: Optional[VastInstanceInfo]
    remote: Optional[VastRemoteStatus]
    issues: list[VastIssue]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        instance = self.instance
        remote = self.remote
        return {
            "timestamp": self.timestamp.isoformat(),
            "instance": None
            if not instance
            else {
                "instance_id": instance.instance_id,
                "label": instance.label,
                "status": instance.status,
                "gpu_name": instance.gpu_name,
                "gpu_ram": instance.gpu_ram,
                "num_gpus": instance.num_gpus,
                "hourly_rate": instance.hourly_rate,
                "ssh_host": instance.ssh_host,
                "ssh_port": instance.ssh_port,
            },
            "remote": None
            if not remote
            else {
                "training_status": remote.training_status,
                "gpu_utilization": remote.gpu_utilization,
                "gpu_memory_used": remote.gpu_memory_used,
                "gpu_memory_total": remote.gpu_memory_total,
                "disk_used_percent": remote.disk_used_percent,
                "disk_used": remote.disk_used,
                "disk_total": remote.disk_total,
                "disk_mount": remote.disk_mount,
                "log_path": remote.log_path,
                "log_mtime": remote.log_mtime,
                "log_age_seconds": remote.log_age_seconds,
                "log_errors": remote.log_errors,
            },
            "issues": [
                {
                    "level": issue.level.value,
                    "kind": issue.kind,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
        }


def resolve_instances_dir(instances_dir: Optional[Path] = None) -> Path:
    """Resolve the Vast instance metadata directory."""
    if instances_dir:
        return instances_dir
    env_dir = os.getenv("AFS_VAST_INSTANCES_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "infra" / "vast" / "instances"


def list_instance_names(instances_dir: Optional[Path] = None) -> list[str]:
    instances_dir = resolve_instances_dir(instances_dir)
    if not instances_dir.exists():
        return []
    return sorted(path.stem for path in instances_dir.glob("*.json"))


def _find_vast_cli() -> str:
    for candidate in ("vastai", "vast"):
        if shutil.which(candidate):
            return candidate
    raise FileNotFoundError("vastai CLI not found in PATH.")


def _parse_json_payload(payload: str) -> dict:
    payload = payload.strip()
    if payload.startswith("{") and payload.endswith("}"):
        return json.loads(payload)
    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Unable to parse JSON payload.")
    return json.loads(payload[start : end + 1])


def _extract_marker_json(text: str, marker: str = "AFS_JSON") -> Optional[dict]:
    start_token = f"{marker}_START"
    end_token = f"{marker}_END"
    start = text.find(start_token)
    end = text.find(end_token)
    if start == -1 or end == -1 or end <= start:
        return None
    start = start + len(start_token)
    payload = text[start:end].strip()
    if not payload:
        return None
    return _parse_json_payload(payload)


def load_instance_metadata(
    name: str,
    instances_dir: Optional[Path] = None,
) -> dict:
    instances_dir = resolve_instances_dir(instances_dir)
    metadata_path = instances_dir / f"{name}.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Instance metadata not found: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _pick_default_instance(instances_dir: Path) -> Optional[str]:
    if not instances_dir.exists():
        return None
    candidates = sorted(instances_dir.glob("*.json"))
    if len(candidates) != 1:
        return None
    return candidates[0].stem


def resolve_instance_selection(
    instance_id: Optional[str],
    name: Optional[str],
    metadata_path: Optional[Path],
    instances_dir: Optional[Path],
) -> tuple[str, Optional[str], dict]:
    if instance_id:
        return str(instance_id), name, {}

    env_instance_id = os.getenv("AFS_VAST_INSTANCE_ID")
    if env_instance_id:
        return env_instance_id, name, {}

    env_name = os.getenv("AFS_VAST_INSTANCE_NAME")
    if not name and env_name:
        name = env_name

    metadata: dict = {}
    if metadata_path:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        resolved_id = metadata.get("instance_id")
        if not resolved_id:
            raise ValueError("Instance metadata missing instance_id.")
        return str(resolved_id), metadata.get("label") or name, metadata

    if not name:
        default_name = _pick_default_instance(resolve_instances_dir(instances_dir))
        if default_name:
            name = default_name

    if not name:
        raise ValueError("No Vast instance specified.")

    metadata = load_instance_metadata(name, instances_dir=instances_dir)
    resolved_id = metadata.get("instance_id")
    if not resolved_id:
        raise ValueError("Instance metadata missing instance_id.")
    return str(resolved_id), metadata.get("label") or name, metadata


def fetch_instance_info(instance_id: str) -> VastInstanceInfo:
    vast_cli = _find_vast_cli()
    result = subprocess.run(
        [vast_cli, "show", "instance", str(instance_id), "--raw"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "vastai show instance failed.")
    data = _parse_json_payload(result.stdout)

    ports = data.get("ports") or {}
    ssh_port = None
    if ports.get("22/tcp"):
        try:
            ssh_port = int(ports["22/tcp"][0]["HostPort"])
        except (KeyError, ValueError, TypeError):
            ssh_port = None
    if not ssh_port:
        ssh_port = data.get("ssh_port")

    ssh_host = data.get("ssh_host")
    if ports.get("22/tcp") and data.get("public_ipaddr"):
        ssh_host = data.get("public_ipaddr")
    if not ssh_host:
        ssh_host = data.get("public_ipaddr")

    return VastInstanceInfo(
        instance_id=str(data.get("id") or instance_id),
        label=data.get("label"),
        status=data.get("actual_status"),
        gpu_name=data.get("gpu_name"),
        gpu_ram=data.get("gpu_ram"),
        num_gpus=data.get("num_gpus"),
        hourly_rate=data.get("dph_total"),
        ssh_host=ssh_host,
        ssh_port=ssh_port,
    )


def _build_remote_script(training_dir: str, log_lines: int) -> str:
    return textwrap.dedent(
        f"""
        python3 - <<'PY'
        import json
        import os
        import shlex
        import subprocess

        def run(cmd):
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                return proc.stdout.strip()
            except Exception:
                return ""

        training_dir = {training_dir!r}
        log_lines = {int(log_lines)}
        log_dir = os.path.join(training_dir, "logs")
        gpu_line = run(
            "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total "
            "--format=csv,noheader,nounits | head -1"
        )
        gpu_name = run("nvidia-smi --query-gpu=name --format=csv,noheader | head -1")
        training_line = run("pgrep -af 'train_peft|train' | head -1")
        training_status = "TRAINING" if training_line else "IDLE"
        log_path = run(f"ls -t {{log_dir}}/*.log 2>/dev/null | head -1")
        log_mtime = 0
        if log_path:
            mtime_str = run("stat -c %Y " + shlex.quote(log_path))
            try:
                log_mtime = int(mtime_str.strip())
            except Exception:
                log_mtime = 0
        log_tail = ""
        if log_path:
            log_tail = run("tail -n " + str(log_lines) + " " + shlex.quote(log_path))
        disk_line = run("df -P " + shlex.quote(training_dir) + " | tail -1")

        disk = {{}}
        if disk_line:
            parts = disk_line.split()
            if len(parts) >= 6:
                disk = {{
                    "filesystem": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "use_percent": parts[4],
                    "mount": parts[5],
                }}

        gpu = {{}}
        if gpu_line:
            parts = [p.strip() for p in gpu_line.split(",")]
            if len(parts) >= 3:
                try:
                    gpu = {{
                        "utilization": float(parts[0]),
                        "memory_used": float(parts[1]),
                        "memory_total": float(parts[2]),
                    }}
                except ValueError:
                    gpu = {{"raw": gpu_line}}

        payload = {{
            "gpu": gpu,
            "gpu_name": gpu_name or None,
            "training_status": training_status,
            "log_path": log_path or None,
            "log_mtime": log_mtime,
            "log_tail": log_tail,
            "disk": disk,
        }}

        print("AFS_JSON_START")
        print(json.dumps(payload))
        print("AFS_JSON_END")
        PY
        """
    ).strip()


def _run_ssh(
    ssh_host: str,
    ssh_port: int,
    command: str,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ssh",
            "-p",
            str(ssh_port),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "LogLevel=ERROR",
            f"root@{ssh_host}",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def fetch_remote_status(
    ssh_host: str,
    ssh_port: int,
    training_dir: str,
    log_lines: int = 120,
) -> Optional[VastRemoteStatus]:
    script = _build_remote_script(training_dir=training_dir, log_lines=log_lines)
    result = _run_ssh(ssh_host, ssh_port, script, timeout=60)
    if result.returncode != 0:
        return None

    payload = _extract_marker_json(result.stdout, marker="AFS_JSON")
    if not payload:
        return None

    gpu = payload.get("gpu") or {}
    disk = payload.get("disk") or {}
    log_mtime = payload.get("log_mtime") or 0
    log_mtime = int(log_mtime) if isinstance(log_mtime, (int, float)) else 0
    log_age = int(time.time()) - log_mtime if log_mtime else None

    disk_use_percent = None
    use_percent = disk.get("use_percent")
    if isinstance(use_percent, str) and use_percent.endswith("%"):
        try:
            disk_use_percent = float(use_percent.rstrip("%"))
        except ValueError:
            disk_use_percent = None

    log_tail = payload.get("log_tail") or ""
    log_errors = detect_log_errors(log_tail)

    return VastRemoteStatus(
        training_status=payload.get("training_status"),
        gpu_utilization=gpu.get("utilization"),
        gpu_memory_used=gpu.get("memory_used"),
        gpu_memory_total=gpu.get("memory_total"),
        disk_used_percent=disk_use_percent,
        disk_used=disk.get("used"),
        disk_total=disk.get("size"),
        disk_mount=disk.get("mount"),
        log_path=payload.get("log_path"),
        log_mtime=log_mtime or None,
        log_age_seconds=log_age,
        log_tail=log_tail or None,
        log_errors=log_errors,
    )


def detect_log_errors(log_tail: str) -> list[str]:
    if not log_tail:
        return []
    patterns = {
        "traceback": re.compile(r"Traceback", re.IGNORECASE),
        "cuda_oom": re.compile(r"CUDA out of memory", re.IGNORECASE),
        "runtime_error": re.compile(r"RuntimeError", re.IGNORECASE),
        "value_error": re.compile(r"ValueError", re.IGNORECASE),
        "assert_error": re.compile(r"AssertionError", re.IGNORECASE),
        "exception": re.compile(r"Exception", re.IGNORECASE),
        "error_line": re.compile(r"^error", re.IGNORECASE | re.MULTILINE),
    }
    hits = []
    for label, pattern in patterns.items():
        if pattern.search(log_tail):
            hits.append(label)
    return hits


def build_status_report(
    instance_id: Optional[str],
    name: Optional[str],
    metadata_path: Optional[Path],
    instances_dir: Optional[Path],
    training_dir: str,
    include_remote: bool = True,
    log_lines: int = 120,
) -> VastStatusReport:
    resolved_id, resolved_label, metadata = resolve_instance_selection(
        instance_id=instance_id,
        name=name,
        metadata_path=metadata_path,
        instances_dir=instances_dir,
    )
    instance = fetch_instance_info(resolved_id)

    ssh_host = instance.ssh_host or metadata.get("ssh_host")
    ssh_port = instance.ssh_port or metadata.get("ssh_port")
    if not instance.label and resolved_label:
        instance.label = resolved_label
    if not instance.ssh_host and ssh_host:
        instance.ssh_host = ssh_host
    if not instance.ssh_port and ssh_port:
        try:
            instance.ssh_port = int(ssh_port)
        except (TypeError, ValueError):
            instance.ssh_port = None

    remote_status = None
    if include_remote and instance.ssh_host and instance.ssh_port:
        remote_status = fetch_remote_status(
            instance.ssh_host,
            int(instance.ssh_port),
            training_dir=training_dir,
            log_lines=log_lines,
        )

    report = VastStatusReport(
        instance=instance,
        remote=remote_status,
        issues=[],
    )
    report.issues = check_health(report)
    return report


def check_health(report: VastStatusReport) -> list[VastIssue]:
    config = get_config()
    issues: list[VastIssue] = []

    if report.instance is None:
        issues.append(
            VastIssue(
                level=AlertLevel.CRITICAL,
                kind="instance_missing",
                message="No Vast instance metadata available.",
            )
        )
        return issues

    status = report.instance.status
    if status and status != "running":
        issues.append(
            VastIssue(
                level=AlertLevel.CRITICAL,
                kind="instance_state",
                message=f"Instance status is {status}.",
            )
        )

    remote = report.remote
    if remote is None:
        issues.append(
            VastIssue(
                level=AlertLevel.CRITICAL,
                kind="ssh_unavailable",
                message="SSH unavailable; remote status not collected.",
            )
        )
        return issues

    if remote.training_status == "IDLE":
        issues.append(
            VastIssue(
                level=AlertLevel.WARNING,
                kind="training_idle",
                message="Training process not detected.",
            )
        )

    if remote.log_path is None:
        issues.append(
            VastIssue(
                level=AlertLevel.WARNING,
                kind="log_missing",
                message="No training log found under /opt/training/logs.",
            )
        )

    if remote.log_age_seconds is not None:
        idle_seconds = config.monitoring.idle_alert_minutes * 60
        if remote.log_age_seconds > idle_seconds:
            issues.append(
                VastIssue(
                    level=AlertLevel.WARNING,
                    kind="log_stale",
                    message=f"Training log is stale ({remote.log_age_seconds}s).",
                )
            )

    if (
        remote.gpu_utilization is not None
        and remote.training_status == "TRAINING"
        and remote.gpu_utilization < config.monitoring.idle_threshold_percent
    ):
        issues.append(
            VastIssue(
                level=AlertLevel.WARNING,
                kind="gpu_idle",
                message=f"GPU utilization low ({remote.gpu_utilization:.1f}%).",
            )
        )

    if remote.disk_used_percent is not None:
        threshold = config.monitoring.disk_warning_threshold
        if remote.disk_used_percent >= threshold:
            level = (
                AlertLevel.CRITICAL
                if remote.disk_used_percent >= min(99, threshold + 10)
                else AlertLevel.WARNING
            )
            issues.append(
                VastIssue(
                    level=level,
                    kind="disk_warning",
                    message=f"Disk usage high ({remote.disk_used_percent:.0f}%).",
                )
            )

    for error in remote.log_errors:
        issues.append(
            VastIssue(
                level=AlertLevel.CRITICAL,
                kind="log_error",
                message=f"Log error pattern detected: {error}.",
            )
        )

    return issues


def format_status(report: VastStatusReport) -> str:
    instance = report.instance
    remote = report.remote
    issues = report.issues

    def fmt_value(value: Optional[object], suffix: str = "") -> str:
        if value is None or value == "":
            return "Unknown / needs verification"
        return f"{value}{suffix}"

    lines = []
    if instance is None:
        lines.append("Vast Instance: Unknown / needs verification")
    else:
        label = instance.label or "Unknown / needs verification"
        lines.append(f"Vast Instance: {label} ({instance.instance_id})")
        lines.append(f"Status: {fmt_value(instance.status)}")
        if instance.gpu_name or instance.num_gpus:
            gpu_desc = f"{instance.num_gpus or '?'}x {instance.gpu_name or 'Unknown / needs verification'}"
            lines.append(f"GPU: {gpu_desc}")
        else:
            lines.append("GPU: Unknown / needs verification")
        if instance.gpu_ram:
            lines.append(f"VRAM: {instance.gpu_ram} MiB")
        if instance.hourly_rate is not None:
            lines.append(f"Rate: ${instance.hourly_rate:.3f}/hr")
        lines.append(
            f"SSH: {fmt_value(instance.ssh_host)}:{fmt_value(instance.ssh_port)}"
        )

    if remote is None:
        lines.append("Remote: Unknown / needs verification")
    else:
        lines.append(f"Remote Training: {fmt_value(remote.training_status)}")
        if remote.gpu_utilization is not None:
            lines.append(
                f"GPU Utilization: {remote.gpu_utilization:.1f}% "
                f"({remote.gpu_memory_used}/{remote.gpu_memory_total} MiB)"
            )
        if remote.disk_used_percent is not None:
            lines.append(
                f"Disk: {remote.disk_used_percent:.0f}% "
                f"({remote.disk_used}/{remote.disk_total}) "
                f"mount={remote.disk_mount}"
            )
        if remote.log_path:
            age = (
                f"{remote.log_age_seconds}s"
                if remote.log_age_seconds is not None
                else "Unknown / needs verification"
            )
            lines.append(f"Log: {remote.log_path} (age {age})")

    if not issues:
        lines.append("Issues: none")
    else:
        lines.append("Issues:")
        for issue in issues:
            lines.append(f"- [{issue.level.value}] {issue.message}")

    return "\n".join(lines)


def write_status_json(report: VastStatusReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def default_status_output_path() -> Path:
    return resolve_index_root() / "vast_status.json"


def send_alerts(report: VastStatusReport, dispatcher: Optional[AlertDispatcher] = None) -> bool:
    if not report.issues:
        return False

    dispatcher = dispatcher or AlertDispatcher()
    filtered: list[VastIssue] = []
    for issue in report.issues:
        if (
            issue.kind in {"training_idle", "gpu_idle", "log_stale"}
            and not dispatcher.config.alert_on_idle_detection
        ):
            continue
        if issue.kind == "disk_warning" and not dispatcher.config.alert_on_disk_warning:
            continue
        filtered.append(issue)

    if not filtered:
        return False

    level_rank = {
        AlertLevel.INFO: 0,
        AlertLevel.WARNING: 1,
        AlertLevel.CRITICAL: 2,
        AlertLevel.URGENT: 3,
    }
    highest = max(filtered, key=lambda issue: level_rank.get(issue.level, 0)).level

    instance_label = (
        report.instance.label if report.instance and report.instance.label else None
    )
    message = "\n".join(f"- {issue.message}" for issue in filtered)
    alert = Alert(
        level=highest,
        title="Vast training issue detected",
        message=message,
        instance=instance_label,
        tags=["vast", "training"],
    )
    return dispatcher.send(alert)
