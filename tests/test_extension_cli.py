from __future__ import annotations

import argparse

from afs_scawful.extension_cli import register_parsers


def _command_choices(parser) -> set[str]:
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if choices:
            return set(choices.keys())
    return set()


def test_extension_cli_registers_legacy_command_groups() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    register_parsers(subparsers)
    commands = _command_choices(parser)

    assert "training" in commands
    assert "gateway" in commands
    assert "vastai" in commands
    assert "benchmark" in commands
    assert "comparison" in commands
    assert "claude" in commands
