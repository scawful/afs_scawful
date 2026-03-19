"""Background agent: training monitor.

Checks Vast.ai training instances for health issues and sends alerts.
Designed to run as a periodic AFS background agent.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from afs.agents.base import (
    AgentResult,
    build_base_parser,
    configure_logging,
    emit_result,
    now_iso,
)

AGENT_NAME = "training-monitor"
AGENT_DESCRIPTION = "Monitor Vast.ai training instances and send health alerts"

logger = logging.getLogger(__name__)


def _check_all_instances() -> dict:
    """Check all known Vast instances and collect health reports."""
    from .vast import (
        build_status_report,
        format_status,
        list_instance_names,
        send_alerts,
    )
    from .infra_config import get_config

    config = get_config()
    instance_names = list_instance_names()

    if not instance_names:
        return {
            "checked": 0,
            "issues": [],
            "alerts_sent": 0,
            "message": "No Vast instances configured",
        }

    results = []
    total_issues = 0
    total_alerts = 0

    for name in instance_names:
        try:
            report = build_status_report(
                instance_id=None,
                name=name,
                metadata_path=None,
                instances_dir=None,
                training_dir=config.training.remote_training_dir,
                include_remote=True,
            )
            alert_sent = send_alerts(report)
            results.append({
                "name": name,
                "status": format_status(report),
                "issues": len(report.issues),
                "alert_sent": alert_sent,
            })
            total_issues += len(report.issues)
            if alert_sent:
                total_alerts += 1
        except Exception as exc:
            logger.warning("Failed to check instance %s: %s", name, exc)
            results.append({
                "name": name,
                "error": str(exc),
            })

    return {
        "checked": len(instance_names),
        "instances": results,
        "total_issues": total_issues,
        "alerts_sent": total_alerts,
    }


def main(args: Sequence[str] | None = None) -> int:
    """Main entrypoint for the training-monitor agent."""
    parser = build_base_parser(AGENT_DESCRIPTION)
    parsed = parser.parse_args(args)
    configure_logging(parsed.quiet)

    started = now_iso()
    logger.info("Training monitor starting")

    try:
        payload = _check_all_instances()
        status = "success"
    except Exception as exc:
        logger.exception("Training monitor failed")
        payload = {"error": str(exc)}
        status = "error"

    result = AgentResult(
        name=AGENT_NAME,
        status=status,
        started_at=started,
        finished_at=now_iso(),
        duration_seconds=0,
        payload=payload,
        metrics={
            "instances_checked": payload.get("checked", 0),
            "issues_found": payload.get("total_issues", 0),
            "alerts_sent": payload.get("alerts_sent", 0),
        },
    )

    output_path = Path(parsed.output) if parsed.output else None
    emit_result(result, output_path=output_path, force_stdout=parsed.stdout, pretty=parsed.pretty)
    return 0 if status == "success" else 1
