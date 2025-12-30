"""AFS Scawful command-line helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Iterable

from .generators import DocSectionConfig, DocSectionGenerator, write_jsonl
from .registry import build_dataset_registry, index_datasets, write_dataset_registry
from .resource_index import ResourceIndexer
from .paths import resolve_datasets_root, resolve_index_root
from .research import (
    build_research_catalog,
    load_research_catalog,
    open_pdf,
    resolve_paper_path,
    resolve_research_catalog_path,
    resolve_research_root,
    write_research_catalog,
)
from .training import TrainingSample
from .validators import default_validators


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


async def _run_validators(sample: TrainingSample, validators) -> list[tuple[str, object]]:
    results: list[tuple[str, object]] = []
    for validator in validators:
        if validator.can_validate(sample):
            result = await validator.validate(sample)
            results.append((validator.name, result))
    return results


def _validators_list_command(args: argparse.Namespace) -> int:
    validators = default_validators()
    for validator in validators:
        print(f"{validator.name}\t{validator.domain}")
    return 0


def _validators_run_command(args: argparse.Namespace) -> int:
    sample_path = Path(args.sample).expanduser().resolve()
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    sample = TrainingSample.from_dict(payload)

    validators = default_validators()
    if args.name:
        validators = [v for v in validators if v.name in args.name]

    results = asyncio.run(_run_validators(sample, validators))
    if not results:
        print("(no validators)")
        return 1

    overall_ok = True
    for name, result in results:
        status = "ok" if result.valid else "fail"
        if not result.valid:
            overall_ok = False
        print(f"{name}\t{status}\t{result.score:.2f}")
    return 0 if overall_ok else 1


def _generators_doc_sections_command(args: argparse.Namespace) -> int:
    index_path = Path(args.index).expanduser().resolve() if args.index else None
    roots = [Path(path).expanduser().resolve() for path in args.root] if args.root else None
    config = DocSectionConfig(min_chars=args.min_chars, max_chars=args.max_chars)
    generator = DocSectionGenerator(
        resource_index=index_path,
        resource_roots=roots,
        config=config,
    )
    result = generator.generate()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else resolve_index_root() / "doc_sections.jsonl"
    )
    write_jsonl(result.samples, output_path)
    print(f"doc_sections: {output_path}")
    print(
        f"samples={len(result.samples)} skipped={result.skipped} errors={len(result.errors)}"
    )
    if result.errors:
        for err in result.errors[:5]:
            print(f"error: {err}")
    return 0 if not result.errors else 1


def _research_catalog_command(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve() if args.root else resolve_research_root()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else resolve_research_catalog_path()
    )
    catalog = build_research_catalog(
        root,
        include_abstract=not args.no_abstract,
        max_pages=args.max_pages,
        max_abstract_chars=args.max_abstract_chars,
    )
    write_research_catalog(catalog, output_path)
    print(f"research_catalog: {output_path}")
    errors = catalog.get("errors", [])
    print(f"papers={catalog.get('count', 0)} errors={len(errors)}")
    for err in errors[:5]:
        print(f"error: {err.get('path')}: {err.get('error')}")
    return 0 if not errors else 1


def _research_list_command(args: argparse.Namespace) -> int:
    catalog_path = (
        Path(args.catalog).expanduser().resolve()
        if args.catalog
        else resolve_research_catalog_path()
    )
    catalog = load_research_catalog(catalog_path)
    for entry in catalog.get("papers", []):
        if not isinstance(entry, dict):
            continue
        title = entry.get("title") or "(untitled)"
        print(f"{entry.get('id')}\t{title}\t{entry.get('relative_path')}")
    return 0


def _research_show_command(args: argparse.Namespace) -> int:
    catalog_path = (
        Path(args.catalog).expanduser().resolve()
        if args.catalog
        else resolve_research_catalog_path()
    )
    catalog = load_research_catalog(catalog_path)
    entry_path = resolve_paper_path(catalog, args.paper_id)
    if entry_path is None:
        print(f"Paper not found: {args.paper_id}")
        return 1
    for entry in catalog.get("papers", []):
        if entry.get("path") == str(entry_path):
            print(json.dumps(entry, indent=2, sort_keys=True))
            return 0
    print(f"Paper not found: {args.paper_id}")
    return 1


def _research_open_command(args: argparse.Namespace) -> int:
    catalog_path = (
        Path(args.catalog).expanduser().resolve()
        if args.catalog
        else resolve_research_catalog_path()
    )
    catalog = load_research_catalog(catalog_path)
    entry_path = resolve_paper_path(catalog, args.paper_id)
    if entry_path is None:
        print(f"Paper not found: {args.paper_id}")
        return 1
    print(str(entry_path))
    if args.open:
        if not open_pdf(entry_path):
            print("Unable to open PDF with the default viewer.")
            return 1
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

    validators_parser = subparsers.add_parser("validators", help="Validation tools.")
    validators_sub = validators_parser.add_subparsers(dest="validators_command")

    validators_list = validators_sub.add_parser("list", help="List validators.")
    validators_list.set_defaults(func=_validators_list_command)

    validators_run = validators_sub.add_parser("run", help="Validate a sample JSON.")
    validators_run.add_argument("sample", help="Path to sample JSON.")
    validators_run.add_argument(
        "--name",
        action="append",
        help="Validator name to run (repeatable).",
    )
    validators_run.set_defaults(func=_validators_run_command)

    generators_parser = subparsers.add_parser("generators", help="Generator tools.")
    generators_sub = generators_parser.add_subparsers(dest="generators_command")

    doc_sections = generators_sub.add_parser(
        "doc-sections", help="Generate samples from documentation."
    )
    doc_sections.add_argument(
        "--index",
        help="Resource index path override (optional).",
    )
    doc_sections.add_argument(
        "--root",
        action="append",
        help="Resource root override (repeatable).",
    )
    doc_sections.add_argument(
        "--output",
        help="Output JSONL path (default: training index/doc_sections.jsonl).",
    )
    doc_sections.add_argument(
        "--min-chars",
        type=int,
        default=120,
        help="Minimum section length to keep.",
    )
    doc_sections.add_argument(
        "--max-chars",
        type=int,
        default=2000,
        help="Maximum section length to keep.",
    )
    doc_sections.set_defaults(func=_generators_doc_sections_command)

    research_parser = subparsers.add_parser("research", help="Research PDF tools.")
    research_sub = research_parser.add_subparsers(dest="research_command")

    research_catalog = research_sub.add_parser(
        "catalog", help="Build a research PDF catalog."
    )
    research_catalog.add_argument("--root", help="Research root override.")
    research_catalog.add_argument("--output", help="Output catalog path.")
    research_catalog.add_argument(
        "--no-abstract",
        action="store_true",
        help="Skip abstract extraction.",
    )
    research_catalog.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Max pages to scan for abstract extraction.",
    )
    research_catalog.add_argument(
        "--max-abstract-chars",
        type=int,
        default=1200,
        help="Max abstract characters to store.",
    )
    research_catalog.set_defaults(func=_research_catalog_command)

    research_list = research_sub.add_parser("list", help="List catalog entries.")
    research_list.add_argument("--catalog", help="Catalog path override.")
    research_list.set_defaults(func=_research_list_command)

    research_show = research_sub.add_parser("show", help="Show catalog entry JSON.")
    research_show.add_argument("paper_id", help="Catalog id, path, or filename.")
    research_show.add_argument("--catalog", help="Catalog path override.")
    research_show.set_defaults(func=_research_show_command)

    research_open = research_sub.add_parser("open", help="Print or open a PDF.")
    research_open.add_argument("paper_id", help="Catalog id, path, or filename.")
    research_open.add_argument("--catalog", help="Catalog path override.")
    research_open.add_argument(
        "--open",
        action="store_true",
        help="Open using the OS default viewer.",
    )
    research_open.set_defaults(func=_research_open_command)

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
    if args.command == "validators" and not getattr(args, "validators_command", None):
        parser.print_help()
        return 1
    if args.command == "generators" and not getattr(args, "generators_command", None):
        parser.print_help()
        return 1
    if args.command == "research" and not getattr(args, "research_command", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
