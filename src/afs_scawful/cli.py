"""AFS Scawful command-line helpers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from .registry import index_datasets, build_dataset_registry, write_dataset_registry
from .resource_index import ResourceIndexer
from .paths import resolve_datasets_root, resolve_index_root


def _datasets_index_command(args: argparse.Namespace) -> int:
    datasets_root = (
        Path(args.root).expanduser().resolve() if args.root else resolve_datasets_root()
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else resolve_index_root() / "dataset_registry.json"
    )
    registry = build_dataset_registry(datasets_root)
    write_dataset_registry(registry, output_path)
    print(f"dataset_registry: {output_path}")
    return 0


def _resources_index_command(args: argparse.Namespace) -> int:
    indexer = ResourceIndexer(
        index_path=Path(args.output).expanduser().resolve()
        if args.output
        else None,
        resource_roots=[Path(path).expanduser().resolve() for path in args.root]
        if args.root
        else None,
        search_patterns=args.pattern if args.pattern else None,
        exclude_patterns=args.exclude if args.exclude else None,
    )
    result = indexer.build_index()
    output_path = indexer.write_index(result)
    print(f"resource_index: {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="afs_scawful")
    subparsers = parser.add_subparsers(dest="command")

    datasets_parser = subparsers.add_parser("datasets", help="Dataset registry tools.")
    datasets_sub = datasets_parser.add_subparsers(dest="datasets_command")

    datasets_index = datasets_sub.add_parser("index", help="Build dataset registry.")
    datasets_index.add_argument("--root", help="Datasets root override.")
    datasets_index.add_argument("--output", help="Output registry path.")
    datasets_index.set_defaults(func=_datasets_index_command)

    resources_parser = subparsers.add_parser("resources", help="Resource index tools.")
    resources_sub = resources_parser.add_subparsers(dest="resources_command")

    resources_index = resources_sub.add_parser("index", help="Build resource index.")
    resources_index.add_argument(
        "--root",
        action="append",
        help="Resource root override (repeatable).",
    )
    resources_index.add_argument(
        "--pattern",
        action="append",
        help="Search pattern override (repeatable).",
    )
    resources_index.add_argument(
        "--exclude",
        action="append",
        help="Exclude pattern override (repeatable).",
    )
    resources_index.add_argument("--output", help="Output index path.")
    resources_index.set_defaults(func=_resources_index_command)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    if args.command == "datasets" and not getattr(args, "datasets_command", None):
        parser.print_help()
        return 1
    if args.command == "resources" and not getattr(args, "resources_command", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
