"""Extension agent registrations for afs-scawful."""

from __future__ import annotations

from .claude_orchestrator import AGENT_DESCRIPTION, AGENT_NAME, main


def register_agents():
    return [
        {
            "name": AGENT_NAME,
            "description": AGENT_DESCRIPTION,
            "entrypoint": main,
        }
    ]
