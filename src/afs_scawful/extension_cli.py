"""Expose afs-scawful command groups through the AFS extension CLI."""

from __future__ import annotations

import argparse


def register_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register the gateway and vastai groups; core AFS already owns training and claude."""
    try:
        from afs_scawful import gateway_cli
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise RuntimeError(
            "afs-scawful extension requires the core afs package on PYTHONPATH"
        ) from exc

    gateway_cli.register_parsers(subparsers)
