from __future__ import annotations

from afs_scawful.oracle import OracleEmbeddingGenerator, TriforceOrchestrator


def test_oracle_runtime_exports_move_to_extension() -> None:
    assert OracleEmbeddingGenerator is not None
    assert TriforceOrchestrator is not None


def test_oracle_runtime_constructs_orchestrator() -> None:
    orchestrator = TriforceOrchestrator(verbose=False)
    assert orchestrator is not None
