from __future__ import annotations

from afs_scawful.extension_agents import register_agents


def test_register_agents_returns_all_agents() -> None:
    agents = register_agents()
    assert len(agents) == 3
    names = {a["name"] for a in agents}
    assert names == {"claude-orchestrator", "training-monitor", "resource-indexer"}


def test_all_agents_have_required_keys() -> None:
    agents = register_agents()
    for agent in agents:
        assert "name" in agent
        assert "description" in agent
        assert "entrypoint" in agent
        assert callable(agent["entrypoint"])
        assert isinstance(agent["name"], str)
        assert isinstance(agent["description"], str)
