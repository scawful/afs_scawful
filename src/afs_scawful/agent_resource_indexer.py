"""Background agent: resource indexer.

Rebuilds the ROM hacking resource index and dataset registry.
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

AGENT_NAME = "resource-indexer"
AGENT_DESCRIPTION = "Rebuild resource index and dataset registry"

logger = logging.getLogger(__name__)


def _rebuild_indexes() -> dict:
    """Rebuild resource index and dataset registry."""
    from .resource_index import ResourceIndexer
    from .registry import build_dataset_registry, write_dataset_registry
    from .paths import resolve_datasets_root, resolve_index_root

    results: dict = {}

    # Resource index
    try:
        indexer = ResourceIndexer()
        indexer.rebuild()
        results["resource_index"] = {
            "status": "rebuilt",
            "entries": len(indexer.entries),
        }
    except Exception as exc:
        logger.warning("Resource index rebuild failed: %s", exc)
        results["resource_index"] = {"status": "error", "error": str(exc)}

    # Dataset registry
    try:
        datasets_root = resolve_datasets_root()
        index_root = resolve_index_root()
        if datasets_root.exists():
            registry = build_dataset_registry(datasets_root)
            output_path = index_root / "dataset_registry.json"
            write_dataset_registry(registry, output_path)
            results["dataset_registry"] = {
                "status": "rebuilt",
                "datasets": len(registry),
                "output": str(output_path),
            }
        else:
            results["dataset_registry"] = {
                "status": "skipped",
                "reason": f"datasets root not found: {datasets_root}",
            }
    except Exception as exc:
        logger.warning("Dataset registry rebuild failed: %s", exc)
        results["dataset_registry"] = {"status": "error", "error": str(exc)}

    return results


def main(args: Sequence[str] | None = None) -> int:
    """Main entrypoint for the resource-indexer agent."""
    parser = build_base_parser(AGENT_DESCRIPTION)
    parsed = parser.parse_args(args)
    configure_logging(parsed.quiet)

    started = now_iso()
    logger.info("Resource indexer starting")

    try:
        payload = _rebuild_indexes()
        status = "success"
    except Exception as exc:
        logger.exception("Resource indexer failed")
        payload = {"error": str(exc)}
        status = "error"

    result = AgentResult(
        name=AGENT_NAME,
        status=status,
        started_at=started,
        finished_at=now_iso(),
        duration_seconds=0,
        payload=payload,
    )

    output_path = Path(parsed.output) if parsed.output else None
    emit_result(result, output_path=output_path, force_stdout=parsed.stdout, pretty=parsed.pretty)
    return 0 if status == "success" else 1
