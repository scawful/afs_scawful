"""MCP tool definitions for afs_scawful extension.

Exposes training infrastructure, assembly tools, and knowledge lookups
as MCP tools discoverable by any MCP client connected to AFS.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_training_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return current training dashboard status as JSON."""
    try:
        from .dashboard import Dashboard

        dashboard = Dashboard()
        costs, budget = dashboard.get_status()
        return {
            "instances": [c.to_dict() for c in costs],
            "budget": {
                "daily_cost": budget.daily_cost,
                "daily_percent": budget.daily_percent,
                "status": budget.status,
            },
        }
    except Exception as exc:
        return {"error": str(exc)}


def _handle_training_paths(arguments: dict[str, Any]) -> dict[str, Any]:
    """Resolve configured training paths."""
    from .paths import resolve_datasets_root, resolve_index_root, resolve_training_root

    return {
        "training_root": str(resolve_training_root()),
        "datasets_root": str(resolve_datasets_root()),
        "index_root": str(resolve_index_root()),
    }


def _handle_infra_config(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return current infrastructure configuration."""
    from .infra_config import get_config

    config = get_config()
    return {
        "vultr": {
            "default_gpu_plan": config.vultr.default_gpu_plan,
            "default_region": config.vultr.default_region,
            "max_runtime_hours": config.vultr.max_runtime_hours,
        },
        "backup": {
            "primary_host": config.backup.primary_host,
            "primary_path": config.backup.primary_path,
        },
        "training": {
            "remote_training_dir": config.training.remote_training_dir,
            "checkpoint_interval_steps": config.training.checkpoint_interval_steps,
            "datasets_dir": config.training.datasets_dir,
        },
        "monitoring": {
            "idle_threshold_percent": config.monitoring.idle_threshold_percent,
            "idle_alert_minutes": config.monitoring.idle_alert_minutes,
            "idle_shutdown_minutes": config.monitoring.idle_shutdown_minutes,
            "disk_warning_threshold": config.monitoring.disk_warning_threshold,
        },
    }


def _handle_vast_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """Get status of a Vast.ai training instance."""
    from .vast import (
        build_status_report,
        format_status,
    )

    name = arguments.get("name")
    instance_id = arguments.get("instance_id")
    training_dir = arguments.get("training_dir", "/opt/training")
    include_remote = arguments.get("include_remote", True)

    try:
        report = build_status_report(
            instance_id=instance_id,
            name=name,
            metadata_path=None,
            instances_dir=None,
            training_dir=training_dir,
            include_remote=include_remote,
        )
        return {
            "formatted": format_status(report),
            "data": report.to_dict(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _handle_vast_instances(arguments: dict[str, Any]) -> dict[str, Any]:
    """List known Vast.ai instance names."""
    from .vast import list_instance_names

    return {"instances": list_instance_names()}


def _handle_assemble(arguments: dict[str, Any]) -> dict[str, Any]:
    """Assemble 65816 code with asar."""
    code = arguments.get("code", "")
    if not code:
        return {"error": "No code provided"}

    code_match = re.search(r"```(?:asm|assembly)?\n(.*?)```", code, re.DOTALL)
    if code_match:
        code = code_match.group(1)

    if "lorom" not in code.lower() and "hirom" not in code.lower():
        code = "lorom\n\n" + code
    if "org " not in code.lower():
        code = code.replace("lorom\n", "lorom\n\norg $008000\n")

    asar_path = arguments.get("asar_path", "asar")

    with tempfile.TemporaryDirectory() as tmpdir:
        asm_path = Path(tmpdir) / "input.asm"
        rom_path = Path(tmpdir) / "output.sfc"
        asm_path.write_text(code)
        rom_path.write_bytes(b"\x00" * 0x80000)

        try:
            result = subprocess.run(
                [asar_path, "--no-title-check", str(asm_path), str(rom_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            return {"error": f"asar not found at {asar_path}"}
        except subprocess.TimeoutExpired:
            return {"error": "Assembly timed out"}

        if result.returncode == 0:
            rom_data = rom_path.read_bytes()
            code_bytes = sum(1 for b in rom_data if b != 0)
            return {
                "success": True,
                "code_bytes": code_bytes,
                "source": code,
            }

        errors = result.stderr or result.stdout
        return {"error": f"Assembly failed:\n{errors}", "source": code}


def _handle_alert_send(arguments: dict[str, Any]) -> dict[str, Any]:
    """Send an alert via the configured alert dispatcher."""
    from .alerting import Alert, AlertDispatcher, AlertLevel

    message = arguments.get("message", "")
    if not message:
        return {"error": "No message provided"}

    title = arguments.get("title", "AFS Alert")
    level_str = arguments.get("level", "info")
    try:
        level = AlertLevel(level_str)
    except ValueError:
        level = AlertLevel.INFO

    tags = arguments.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    dispatcher = AlertDispatcher()
    alert = Alert(
        level=level,
        title=title,
        message=message,
        instance=arguments.get("instance"),
        cost=arguments.get("cost"),
        tags=tags,
    )
    sent = dispatcher.send(alert)
    return {"sent": sent}


def _handle_models_list(arguments: dict[str, Any]) -> dict[str, Any]:
    """List expert models registered in the orchestrator."""
    from .claude_orchestrator import EXPERT_MODELS

    return {
        "models": {
            name: {
                "ollama_tag": model.ollama_tag,
                "description": model.description,
                "domains": model.domains,
            }
            for name, model in EXPERT_MODELS.items()
        }
    }


def _handle_resource_index(arguments: dict[str, Any]) -> dict[str, Any]:
    """Rebuild or query the resource index."""
    action = arguments.get("action", "stats")

    from .resource_index import ResourceIndexer

    indexer = ResourceIndexer()

    if action == "rebuild":
        indexer.rebuild()
        return {"status": "rebuilt", "count": len(indexer.entries)}

    if action == "search":
        query = arguments.get("query", "")
        if not query:
            return {"error": "No query provided"}
        results = indexer.search(query)
        return {"results": [str(r) for r in results[:20]]}

    return {"entry_count": len(indexer.entries)}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def register_mcp_tools() -> list[dict[str, Any]]:
    """Return MCP tool definitions for the afs_scawful extension."""
    return [
        {
            "name": "training.status",
            "description": "Get training dashboard status: active instances, costs, and budget",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": _handle_training_status,
        },
        {
            "name": "training.paths",
            "description": "Resolve configured training, dataset, and index root paths",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": _handle_training_paths,
        },
        {
            "name": "infra.config",
            "description": "Show infrastructure configuration (GPU plans, backup, monitoring thresholds)",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": _handle_infra_config,
        },
        {
            "name": "vast.status",
            "description": "Get Vast.ai instance status including GPU, disk, and training state",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Instance name (from infra/vast/instances/)",
                    },
                    "instance_id": {
                        "type": "string",
                        "description": "Vast instance ID (alternative to name)",
                    },
                    "training_dir": {
                        "type": "string",
                        "description": "Remote training directory",
                        "default": "/opt/training",
                    },
                    "include_remote": {
                        "type": "boolean",
                        "description": "SSH into instance for live GPU/disk/log data",
                        "default": True,
                    },
                },
            },
            "handler": _handle_vast_status,
        },
        {
            "name": "vast.instances",
            "description": "List known Vast.ai instance names from metadata",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": _handle_vast_instances,
        },
        {
            "name": "assembly.compile",
            "description": "Assemble 65816 ASM code with the asar assembler",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "65816 assembly source code",
                    },
                    "asar_path": {
                        "type": "string",
                        "description": "Path to asar binary (defaults to 'asar' on PATH)",
                    },
                },
                "required": ["code"],
            },
            "handler": _handle_assemble,
        },
        {
            "name": "alert.send",
            "description": "Send an alert via ntfy.sh (training events, budget warnings, etc.)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Alert message body",
                    },
                    "title": {
                        "type": "string",
                        "description": "Alert title",
                        "default": "AFS Alert",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["info", "warning", "critical", "urgent"],
                        "description": "Alert priority level",
                        "default": "info",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Alert tags",
                    },
                    "instance": {
                        "type": "string",
                        "description": "Instance label",
                    },
                    "cost": {
                        "type": "number",
                        "description": "Associated cost value",
                    },
                },
                "required": ["message"],
            },
            "handler": _handle_alert_send,
        },
        {
            "name": "models.experts",
            "description": "List expert models (Nayru, Veran, Farore, Majora) and their domains",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": _handle_models_list,
        },
        {
            "name": "resource.index",
            "description": "Query or rebuild the ROM hacking resource index",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["stats", "search", "rebuild"],
                        "description": "Action to perform",
                        "default": "stats",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (required when action=search)",
                    },
                },
            },
            "handler": _handle_resource_index,
        },
    ]
