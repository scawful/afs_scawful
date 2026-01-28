"""Alerting system with ntfy.sh integration.

Provides unified alerting for training events, budget warnings, and system alerts.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


class AlertLevel(Enum):
    """Alert priority levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    URGENT = "urgent"


@dataclass
class Alert:
    """An alert to be sent."""

    level: AlertLevel
    title: str
    message: str
    instance: Optional[str] = None
    cost: Optional[float] = None
    tags: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AlertConfig:
    """Alert configuration."""

    ntfy_topic: str = "afs-training"
    ntfy_server: str = "https://ntfy.sh"
    enabled: bool = True

    # Event toggles
    alert_on_training_start: bool = True
    alert_on_training_complete: bool = True
    alert_on_training_failed: bool = True
    alert_on_eval_complete: bool = True
    alert_on_backup_complete: bool = True
    alert_on_export_complete: bool = True
    alert_on_budget_warning: bool = True
    alert_on_idle_detection: bool = True
    alert_on_disk_warning: bool = True

    @classmethod
    def from_toml(cls, config_path: Path) -> "AlertConfig":
        """Load configuration from TOML file."""
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        alerts = data.get("alerts", {})

        return cls(
            ntfy_topic=alerts.get("ntfy_topic", "afs-training"),
            ntfy_server=alerts.get("ntfy_server", "https://ntfy.sh"),
            alert_on_training_start=alerts.get("alert_on_training_start", True),
            alert_on_training_complete=alerts.get("alert_on_training_complete", True),
            alert_on_training_failed=alerts.get("alert_on_training_failed", True),
            alert_on_eval_complete=alerts.get("alert_on_eval_complete", True),
            alert_on_backup_complete=alerts.get("alert_on_backup_complete", True),
            alert_on_export_complete=alerts.get("alert_on_export_complete", True),
            alert_on_budget_warning=alerts.get("alert_on_budget_warning", True),
            alert_on_idle_detection=alerts.get("alert_on_idle_detection", True),
            alert_on_disk_warning=alerts.get("alert_on_disk_warning", True),
        )

    @classmethod
    def from_env(cls) -> "AlertConfig":
        """Load configuration from environment variables."""
        return cls(
            ntfy_topic=os.environ.get("NTFY_TOPIC", "afs-training"),
            ntfy_server=os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
        )


class AlertDispatcher:
    """Dispatch alerts to configured channels."""

    # Map AlertLevel to ntfy priority
    PRIORITY_MAP = {
        AlertLevel.INFO: "min",
        AlertLevel.WARNING: "low",
        AlertLevel.CRITICAL: "high",
        AlertLevel.URGENT: "urgent",
    }

    def __init__(
        self,
        config: Optional[AlertConfig] = None,
        config_path: Optional[Path] = None,
    ):
        if config:
            self.config = config
        elif config_path:
            self.config = AlertConfig.from_toml(config_path)
        else:
            # Try default path, fall back to env
            default_path = Path(__file__).parent.parent.parent / "config" / "budget.toml"
            if default_path.exists():
                self.config = AlertConfig.from_toml(default_path)
            else:
                self.config = AlertConfig.from_env()

    def send(self, alert: Alert) -> bool:
        """Send alert to all configured channels.

        Returns:
            True if at least one channel succeeded
        """
        if not self.config.enabled:
            return False

        success = False

        # Send to ntfy.sh
        if self.config.ntfy_topic:
            if self._send_ntfy(alert):
                success = True

        # Always log locally
        self._log_alert(alert)

        return success

    def _send_ntfy(self, alert: Alert) -> bool:
        """Send alert via ntfy.sh."""
        url = f"{self.config.ntfy_server}/{self.config.ntfy_topic}"

        # Build message body
        body = alert.message
        if alert.instance:
            body = f"[{alert.instance}] {body}"
        if alert.cost is not None:
            body = f"{body}\nCost: ${alert.cost:.2f}"

        # Build tags
        tags = ["robot"] + alert.tags
        if alert.level == AlertLevel.CRITICAL:
            tags.append("warning")
        elif alert.level == AlertLevel.URGENT:
            tags.append("rotating_light")

        headers = {
            "Title": alert.title,
            "Priority": self.PRIORITY_MAP.get(alert.level, "default"),
            "Tags": ",".join(tags),
        }

        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"Warning: Failed to send ntfy alert: {e}")
            return False

    def _log_alert(self, alert: Alert) -> None:
        """Log alert locally."""
        log_entry = {
            "timestamp": alert.timestamp.isoformat(),
            "level": alert.level.value,
            "title": alert.title,
            "message": alert.message,
            "instance": alert.instance,
            "cost": alert.cost,
        }

        # Try to write to log file
        log_path = Path.home() / ".local" / "share" / "afs" / "alerts.jsonl"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except OSError:
            pass  # Silently fail if we can't write logs


# Convenience functions for common alerts
def alert_training_started(
    model: str,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send alert when training starts."""
    dispatcher = dispatcher or AlertDispatcher()
    if not dispatcher.config.alert_on_training_start:
        return
    alert = Alert(
        level=AlertLevel.INFO,
        title="Training Started",
        message=f"Started training {model}",
        instance=instance,
        tags=["training", "start"],
    )
    dispatcher.send(alert)


def alert_training_complete(
    model: str,
    duration_hours: float,
    cost: Optional[float] = None,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send alert when training completes."""
    dispatcher = dispatcher or AlertDispatcher()
    if not dispatcher.config.alert_on_training_complete:
        return
    alert = Alert(
        level=AlertLevel.INFO,
        title="Training Complete",
        message=f"Completed training {model} in {duration_hours:.1f}h",
        instance=instance,
        cost=cost,
        tags=["training", "complete", "checkmark"],
    )
    dispatcher.send(alert)


def alert_export_complete(
    model: str,
    destination: str,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send alert when export completes."""
    dispatcher = dispatcher or AlertDispatcher()
    if not dispatcher.config.alert_on_export_complete:
        return
    alert = Alert(
        level=AlertLevel.INFO,
        title="Export Complete",
        message=f"Exported {model} to {destination}",
        instance=instance,
        tags=["export", "complete"],
    )
    dispatcher.send(alert)


def alert_budget_warning(
    current_cost: float,
    threshold: float,
    level: AlertLevel = AlertLevel.WARNING,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send budget warning alert."""
    dispatcher = dispatcher or AlertDispatcher()
    percent = (current_cost / threshold) * 100
    if not dispatcher.config.alert_on_budget_warning:
        return
    alert = Alert(
        level=level,
        title="Budget Alert",
        message=f"Daily spending ${current_cost:.2f} ({percent:.0f}% of ${threshold:.2f} limit)",
        cost=current_cost,
        tags=["budget", "money_with_wings"],
    )
    dispatcher.send(alert)


def alert_idle_detected(
    minutes: int,
    gpu_util: float,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send idle detection alert."""
    dispatcher = dispatcher or AlertDispatcher()
    if not dispatcher.config.alert_on_idle_detection:
        return
    alert = Alert(
        level=AlertLevel.WARNING,
        title="GPU Idle",
        message=f"GPU idle for {minutes} minutes ({gpu_util:.0f}% utilization)",
        instance=instance,
        tags=["idle", "zzz"],
    )
    dispatcher.send(alert)


def alert_shutdown_blocked(
    reason: str,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send alert when shutdown is blocked."""
    dispatcher = dispatcher or AlertDispatcher()
    alert = Alert(
        level=AlertLevel.URGENT,
        title="Shutdown Blocked",
        message=f"Shutdown blocked: {reason}. Manual intervention required!",
        instance=instance,
        tags=["shutdown", "warning", "rotating_light"],
    )
    dispatcher.send(alert)


def alert_training_failed(
    model: str,
    reason: str,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send alert when training fails."""
    dispatcher = dispatcher or AlertDispatcher()
    if not dispatcher.config.alert_on_training_failed:
        return
    alert = Alert(
        level=AlertLevel.CRITICAL,
        title="Training Failed",
        message=f"Training failed for {model}: {reason}",
        instance=instance,
        tags=["training", "failed", "warning"],
    )
    dispatcher.send(alert)


def alert_eval_complete(
    model: str,
    output_path: str,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send alert when evaluation completes."""
    dispatcher = dispatcher or AlertDispatcher()
    if not dispatcher.config.alert_on_eval_complete:
        return
    alert = Alert(
        level=AlertLevel.INFO,
        title="Eval Complete",
        message=f"Eval completed for {model}: {output_path}",
        instance=instance,
        tags=["eval", "complete"],
    )
    dispatcher.send(alert)


def alert_backup_complete(
    model: str,
    destination: str,
    instance: Optional[str] = None,
    dispatcher: Optional[AlertDispatcher] = None,
) -> None:
    """Send alert when backup completes."""
    dispatcher = dispatcher or AlertDispatcher()
    if not dispatcher.config.alert_on_backup_complete:
        return
    alert = Alert(
        level=AlertLevel.INFO,
        title="Backup Complete",
        message=f"Backup finished for {model}: {destination}",
        instance=instance,
        tags=["backup", "complete"],
    )
    dispatcher.send(alert)


# CLI interface
if __name__ == "__main__":
    import argparse
    import sys

    def _should_suppress(config: AlertConfig, event: str | None) -> bool:
        if not event:
            return False
        mapping = {
            "training-start": "alert_on_training_start",
            "training-complete": "alert_on_training_complete",
            "training-failed": "alert_on_training_failed",
            "eval-complete": "alert_on_eval_complete",
            "backup-complete": "alert_on_backup_complete",
            "export-complete": "alert_on_export_complete",
            "budget-warning": "alert_on_budget_warning",
            "idle-detected": "alert_on_idle_detection",
            "disk-warning": "alert_on_disk_warning",
        }
        toggle = mapping.get(event)
        return bool(toggle and not getattr(config, toggle, True))

    parser = argparse.ArgumentParser(prog="python -m afs_scawful.alerting")
    subparsers = parser.add_subparsers(dest="command")

    test_parser = subparsers.add_parser("test", help="Send a test alert.")

    send_parser = subparsers.add_parser("send", help="Send a custom alert.")
    send_parser.add_argument("--message", "-m", help="Alert message.")
    send_parser.add_argument("--title", "-t", default="AFS Alert", help="Alert title.")
    send_parser.add_argument(
        "--level",
        choices=[level.value for level in AlertLevel],
        default=AlertLevel.INFO.value,
        help="Alert level.",
    )
    send_parser.add_argument(
        "--tags",
        help="Comma-separated tags (e.g. training,complete).",
    )
    send_parser.add_argument("--instance", help="Instance label or ID.")
    send_parser.add_argument("--cost", type=float, help="Cost value.")
    send_parser.add_argument(
        "--event",
        choices=[
            "training-start",
            "training-complete",
            "training-failed",
            "eval-complete",
            "backup-complete",
            "export-complete",
            "budget-warning",
            "idle-detected",
            "disk-warning",
        ],
        help="Alert event type (respects alert toggles).",
    )
    send_parser.add_argument(
        "legacy_message",
        nargs="?",
        help="Legacy positional message (use --message).",
    )
    send_parser.add_argument(
        "legacy_level",
        nargs="?",
        help="Legacy positional level (use --level).",
    )

    args = parser.parse_args()
    if not args.command:
        print("Usage: python -m afs_scawful.alerting <test|send> [message]")
        sys.exit(1)

    dispatcher = AlertDispatcher()

    if args.command == "test":
        alert = Alert(
            level=AlertLevel.INFO,
            title="Test Alert",
            message="This is a test alert from AFS training infrastructure.",
            tags=["test"],
        )
        if dispatcher.send(alert):
            print("Test alert sent successfully!")
        else:
            print("Failed to send test alert.")
        sys.exit(0)

    if args.command == "send":
        message = args.message or args.legacy_message
        if not message:
            print("Usage: python -m afs_scawful.alerting send --message \"...\"")
            sys.exit(1)
        level_str = args.level
        if args.legacy_level:
            level_str = args.legacy_level
        if _should_suppress(dispatcher.config, args.event):
            print("Alert suppressed by config.")
            sys.exit(0)
        tags = []
        if args.tags:
            tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
        alert = Alert(
            level=AlertLevel(level_str),
            title=args.title,
            message=message,
            instance=args.instance,
            cost=args.cost,
            tags=tags,
        )
        if dispatcher.send(alert):
            print("Alert sent!")
            sys.exit(0)
        print("Failed to send alert.")
        sys.exit(1)

    print(f"Unknown command: {args.command}")
    sys.exit(1)
