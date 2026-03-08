from __future__ import annotations

from afs_scawful.extension_agents import register_agents


def test_register_agents_exposes_claude_orchestrator() -> None:
    agents = register_agents()
    assert agents
    assert agents[0]["name"] == "claude-orchestrator"
    assert callable(agents[0]["entrypoint"])
