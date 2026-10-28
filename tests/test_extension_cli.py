from __future__ import annotations

import argparse

from afs_scawful.extension_cli import register_parsers


def _command_choices(parser) -> set[str]:
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if choices:
            return set(choices.keys())
    return set()


def test_extension_cli_registers_alongside_core_command_groups() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    # Core AFS registers these before extensions; argparse rejects duplicates.
    subparsers.add_parser("training")
    subparsers.add_parser("claude")

    register_parsers(subparsers)
    commands = _command_choices(parser)

    assert {"training", "claude", "gateway", "vastai"} <= commands
