"""Extension agent registrations for afs-scawful."""

from __future__ import annotations

from .agent_resource_indexer import (
    AGENT_DESCRIPTION as INDEXER_DESCRIPTION,
    AGENT_NAME as INDEXER_NAME,
    main as indexer_main,
)
from .agent_training_monitor import (
    AGENT_DESCRIPTION as MONITOR_DESCRIPTION,
    AGENT_NAME as MONITOR_NAME,
    main as monitor_main,
)
from .claude_orchestrator import (
    AGENT_DESCRIPTION as ORCHESTRATOR_DESCRIPTION,
    AGENT_NAME as ORCHESTRATOR_NAME,
    main as orchestrator_main,
)


def register_agents():
    return [
        {
            "name": ORCHESTRATOR_NAME,
            "description": ORCHESTRATOR_DESCRIPTION,
            "entrypoint": orchestrator_main,
        },
        {
            "name": MONITOR_NAME,
            "description": MONITOR_DESCRIPTION,
            "entrypoint": monitor_main,
        },
        {
            "name": INDEXER_NAME,
            "description": INDEXER_DESCRIPTION,
            "entrypoint": indexer_main,
        },
    ]
