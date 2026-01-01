"""Infrastructure configuration loader.

Loads and provides access to centralized infrastructure configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


@dataclass
class VultrConfig:
    """Vultr deployment configuration."""

    default_gpu_plan: str = "vcg-a100-3c-30g-20vram"
    default_region: str = "sjc"
    max_runtime_hours: int = 48
    ssh_key_id: Optional[str] = None


@dataclass
class BackupConfig:
    """Backup destination configuration."""

    primary_host: str = "halext-nj"
    primary_path: str = "/home/halext/models/afs_training"
    gdrive_folder_id: str = "1EclHzbfNxtC9qVr8baV61GhQrenWdWsJ"
    local_backup_path: str = "models"


@dataclass
class TrainingConfig:
    """Training settings."""

    remote_training_dir: str = "/opt/training"
    checkpoint_interval_steps: int = 50
    export_interval_steps: int = 500
    datasets_dir: str = "/opt/training/datasets"


@dataclass
class MonitoringConfig:
    """Monitoring settings."""

    idle_threshold_percent: int = 5
    idle_alert_minutes: int = 15
    idle_shutdown_minutes: int = 30
    disk_warning_threshold: int = 85
    cost_check_interval: int = 300


@dataclass
class ExportConfig:
    """Export settings."""

    max_retries: int = 5
    retry_delay_seconds: int = 60
    export_timeout_seconds: int = 600
    verify_before_shutdown: bool = True


@dataclass
class LoggingConfig:
    """Logging settings."""

    remote_log_dir: str = "/opt/training/logs"
    local_log_dir: str = "infra/logs"
    max_log_age_days: int = 30


@dataclass
class InfraConfig:
    """Complete infrastructure configuration."""

    vultr: VultrConfig = field(default_factory=VultrConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    exports: ExportConfig = field(default_factory=ExportConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_toml(cls, config_path: Path) -> "InfraConfig":
        """Load configuration from TOML file."""
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        vultr_data = data.get("vultr", {})
        backup_data = data.get("backup", {})
        training_data = data.get("training", {})
        monitoring_data = data.get("monitoring", {})
        exports_data = data.get("exports", {})
        logging_data = data.get("logging", {})

        return cls(
            vultr=VultrConfig(
                default_gpu_plan=vultr_data.get("default_gpu_plan", "vcg-a100-3c-30g-20vram"),
                default_region=vultr_data.get("default_region", "sjc"),
                max_runtime_hours=vultr_data.get("max_runtime_hours", 48),
                ssh_key_id=vultr_data.get("ssh_key_id"),
            ),
            backup=BackupConfig(
                primary_host=backup_data.get("primary_host", "halext-nj"),
                primary_path=backup_data.get("primary_path", "/home/halext/models/afs_training"),
                gdrive_folder_id=backup_data.get("gdrive_folder_id", ""),
                local_backup_path=backup_data.get("local_backup_path", "models"),
            ),
            training=TrainingConfig(
                remote_training_dir=training_data.get("remote_training_dir", "/opt/training"),
                checkpoint_interval_steps=training_data.get("checkpoint_interval_steps", 50),
                export_interval_steps=training_data.get("export_interval_steps", 500),
                datasets_dir=training_data.get("datasets_dir", "/opt/training/datasets"),
            ),
            monitoring=MonitoringConfig(
                idle_threshold_percent=monitoring_data.get("idle_threshold_percent", 5),
                idle_alert_minutes=monitoring_data.get("idle_alert_minutes", 15),
                idle_shutdown_minutes=monitoring_data.get("idle_shutdown_minutes", 30),
                disk_warning_threshold=monitoring_data.get("disk_warning_threshold", 85),
                cost_check_interval=monitoring_data.get("cost_check_interval", 300),
            ),
            exports=ExportConfig(
                max_retries=exports_data.get("max_retries", 5),
                retry_delay_seconds=exports_data.get("retry_delay_seconds", 60),
                export_timeout_seconds=exports_data.get("export_timeout_seconds", 600),
                verify_before_shutdown=exports_data.get("verify_before_shutdown", True),
            ),
            logging=LoggingConfig(
                remote_log_dir=logging_data.get("remote_log_dir", "/opt/training/logs"),
                local_log_dir=logging_data.get("local_log_dir", "infra/logs"),
                max_log_age_days=logging_data.get("max_log_age_days", 30),
            ),
        )

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "InfraConfig":
        """Load configuration from default or specified path."""
        if config_path is None:
            # Try project config directory
            project_config = Path(__file__).parent.parent.parent / "config" / "infra.toml"
            if project_config.exists():
                config_path = project_config
            else:
                # Return defaults
                return cls()

        return cls.from_toml(config_path)


# Singleton instance
_config: Optional[InfraConfig] = None


def get_config() -> InfraConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = InfraConfig.load()
    return _config


def reload_config(config_path: Optional[Path] = None) -> InfraConfig:
    """Reload configuration from disk."""
    global _config
    _config = InfraConfig.load(config_path)
    return _config


# CLI interface
if __name__ == "__main__":
    import json
    import sys

    config = get_config()

    if len(sys.argv) > 1 and sys.argv[1] == "json":
        # Output as JSON for shell scripts
        output = {
            "vultr": {
                "default_gpu_plan": config.vultr.default_gpu_plan,
                "default_region": config.vultr.default_region,
                "max_runtime_hours": config.vultr.max_runtime_hours,
            },
            "backup": {
                "primary_host": config.backup.primary_host,
                "primary_path": config.backup.primary_path,
            },
            "monitoring": {
                "idle_threshold_percent": config.monitoring.idle_threshold_percent,
                "idle_alert_minutes": config.monitoring.idle_alert_minutes,
                "idle_shutdown_minutes": config.monitoring.idle_shutdown_minutes,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print("AFS Infrastructure Configuration")
        print("=" * 40)
        print(f"Vultr Plan: {config.vultr.default_gpu_plan}")
        print(f"Vultr Region: {config.vultr.default_region}")
        print(f"Max Runtime: {config.vultr.max_runtime_hours}h")
        print(f"Backup Host: {config.backup.primary_host}")
        print(f"Backup Path: {config.backup.primary_path}")
        print(f"Idle Threshold: {config.monitoring.idle_threshold_percent}%")
        print(f"Idle Shutdown: {config.monitoring.idle_shutdown_minutes}m")
