from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")

from afs_scawful.gateway_server import PERSONAS
from afs_scawful.moe.router import RouterConfig


def test_gateway_server_keeps_persona_models_in_extension() -> None:
    assert {"din", "nayru", "farore", "veran", "scribe"}.issubset(PERSONAS)


def test_router_defaults_live_in_extension() -> None:
    names = [expert.name for expert in RouterConfig.default().experts]
    assert names == ["din", "nayru", "farore"]
