"""Re-expose legacy AFS command groups through the afs-scawful extension."""

from __future__ import annotations

import argparse


def register_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register command groups that no longer ship in core AFS by default."""
    try:
        from afs.cli import (
            active_learning,
            benchmark,
            claude,
            comparison,
            distillation,
            encoder,
            entity,
            generator,
            generators,
            pipeline,
            tokenizer,
            training,
        )
        from afs_scawful import gateway_cli
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise RuntimeError(
            "afs-scawful extension requires the core afs package on PYTHONPATH"
        ) from exc

    for module in (
        training,
        generators,
        tokenizer,
        encoder,
        entity,
        pipeline,
        active_learning,
        generator,
        gateway_cli,
        benchmark,
        distillation,
        comparison,
        claude,
    ):
        module.register_parsers(subparsers)
