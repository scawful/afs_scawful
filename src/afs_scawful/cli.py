"""AFS Scawful command-line helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Iterable

from .config import load_research_overrides
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
from .models import (
    list_models,
    get_model_info,
    deploy_to_ollama,
    test_model_ollama,
    test_model_python,
    chat_with_model,
    backup_model,
    verify_backups,
    print_model_status,
)
from .cost_tracker import VultrCostTracker, format_cost_report
from .budget import BudgetEnforcer, format_budget_status
from .dashboard import Dashboard
from .alerting import AlertDispatcher, Alert, AlertLevel


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
    overrides_path = args.overrides or os.getenv("AFS_RESEARCH_OVERRIDES")
    overrides = load_research_overrides(
        Path(overrides_path).expanduser().resolve() if overrides_path else None
    )
    catalog = build_research_catalog(
        root,
        overrides=overrides,
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


def _models_list_command(args: argparse.Namespace) -> int:
    """List all available trained models."""
    models = list_models()
    if not models:
        print("No models found in models/ directory")
        return 1

    for model in models:
        status_symbols = []
        if model.has_lora:
            status_symbols.append("L")
        if model.has_merged:
            status_symbols.append("M")
        if model.has_gguf:
            status_symbols.append("G")
        if model.has_ollama:
            status_symbols.append("O")

        status = "".join(status_symbols) if status_symbols else "-"
        print(f"{model.name}\t{model.size_gb:.1f}GB\t[{status}]\t{len(model.checkpoints)} checkpoints")

    print()
    print("Status codes: L=LoRA, M=Merged, G=GGUF, O=Ollama")
    return 0


def _models_status_command(args: argparse.Namespace) -> int:
    """Show detailed status for a model."""
    model = get_model_info(args.model)
    if not model:
        print(f"Error: Model '{args.model}' not found")
        print()
        print("Available models:")
        for m in list_models():
            print(f"  {m.name}")
        return 1

    print_model_status(model)
    return 0


def _models_deploy_command(args: argparse.Namespace) -> int:
    """Deploy a model to the specified target."""
    model = get_model_info(args.model)
    if not model:
        print(f"Error: Model '{args.model}' not found")
        return 1

    if not model.has_lora:
        print(f"Error: Model '{args.model}' has no LoRA adapters")
        return 1

    if args.target == "ollama":
        print(f"Deploying {args.model} to Ollama (quantization: {args.quantization})...")
        success = deploy_to_ollama(
            args.model,
            quantization=args.quantization,
            skip_merge=args.skip_merge,
            skip_gguf=args.skip_gguf,
        )
        if success:
            print()
            print(f"✓ Model deployed successfully!")
            print(f"  Test it: afs models test {args.model}")
            print(f"  Chat with it: afs models chat {args.model}")
            return 0
        else:
            print("✗ Deployment failed")
            return 1
    else:
        print(f"Error: Unknown target '{args.target}'")
        return 1


def _models_test_command(args: argparse.Namespace) -> int:
    """Test a deployed model."""
    model = get_model_info(args.model)
    if not model:
        print(f"Error: Model '{args.model}' not found")
        return 1

    if args.method == "ollama":
        if not model.has_ollama:
            print(f"Error: Model '{args.model}' not deployed to Ollama")
            print(f"Deploy it first: afs models deploy {args.model}")
            return 1

        print(f"Testing {args.model} with Ollama...")
        success = test_model_ollama(args.model)
        return 0 if success else 1

    elif args.method == "python":
        if not model.has_lora:
            print(f"Error: Model '{args.model}' has no LoRA adapters")
            return 1

        prompt = args.prompt or "What is the SNES accumulator register?"
        print(f"Testing {args.model} with Python CLI...")
        print(f"Prompt: {prompt}")
        print()
        success = test_model_python(args.model, prompt)
        return 0 if success else 1

    else:
        print(f"Error: Unknown test method '{args.method}'")
        return 1


def _models_chat_command(args: argparse.Namespace) -> int:
    """Start interactive chat with a model."""
    model = get_model_info(args.model)
    if not model:
        print(f"Error: Model '{args.model}' not found")
        return 1

    if not model.has_ollama:
        print(f"Error: Model '{args.model}' not deployed to Ollama")
        print(f"Deploy it first: afs models deploy {args.model}")
        return 1

    print(f"Starting chat with {args.model}...")
    print("(Press Ctrl+D or type /bye to exit)")
    print()
    success = chat_with_model(args.model)
    return 0 if success else 1


def _models_backup_command(args: argparse.Namespace) -> int:
    """Backup a model to all configured locations."""
    model = get_model_info(args.model)
    if not model:
        print(f"Error: Model '{args.model}' not found")
        return 1

    print(f"Backing up {args.model} to all locations...")
    success = backup_model(args.model)
    return 0 if success else 1


def _models_verify_command(args: argparse.Namespace) -> int:
    """Verify model backups exist."""
    model = get_model_info(args.model)
    if not model:
        print(f"Error: Model '{args.model}' not found")
        return 1

    print(f"Verifying backups for {args.model}...")
    success = verify_backups(args.model)
    return 0 if success else 1


# Cost tracking commands
def _cost_status_command(args: argparse.Namespace) -> int:
    """Show current running costs."""
    try:
        tracker = VultrCostTracker()
        costs = tracker.get_instance_costs()

        if not costs:
            print("No active training instances.")
            return 0

        for cost in costs:
            print(
                f"{cost.instance_name}: ${cost.total_cost:.2f} "
                f"({cost.hours_running:.1f}h @ ${cost.hourly_rate:.2f}/h) [{cost.status}]"
            )
        print(f"\nTotal: ${sum(c.total_cost for c in costs):.2f}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _cost_daily_command(args: argparse.Namespace) -> int:
    """Show daily cost summary."""
    try:
        tracker = VultrCostTracker()
        summary = tracker.get_daily_summary()
        print(format_cost_report(summary))
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _cost_balance_command(args: argparse.Namespace) -> int:
    """Show account balance."""
    try:
        tracker = VultrCostTracker()
        balance = tracker.get_account_balance()
        print(f"Balance: ${balance['balance']:.2f}")
        print(f"Pending charges: ${balance['pending_charges']:.2f}")
        if balance['last_payment_date']:
            print(f"Last payment: ${balance['last_payment_amount']:.2f} on {balance['last_payment_date']}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


# Budget commands
def _budget_check_command(args: argparse.Namespace) -> int:
    """Check budget status."""
    try:
        enforcer = BudgetEnforcer()
        status = enforcer.check_budget()
        print(format_budget_status(status, enforcer.config))
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _budget_enforce_command(args: argparse.Namespace) -> int:
    """Enforce budget limits (may trigger alerts)."""
    try:
        enforcer = BudgetEnforcer()
        status = enforcer.enforce(dry_run=args.dry_run)
        print(format_budget_status(status, enforcer.config))
        if status.status == "exceeded":
            return 2
        elif status.status == "critical":
            return 1
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


# Dashboard commands
def _dashboard_command(args: argparse.Namespace) -> int:
    """Show the training dashboard."""
    try:
        dashboard = Dashboard()
        if args.watch:
            dashboard.watch(interval=args.interval)
        else:
            print(dashboard.render(compact=args.compact))
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


# Alert commands
def _alert_test_command(args: argparse.Namespace) -> int:
    """Send a test alert."""
    try:
        dispatcher = AlertDispatcher()
        alert = Alert(
            level=AlertLevel.INFO,
            title="Test Alert",
            message="This is a test alert from AFS training infrastructure.",
            tags=["test"],
        )
        if dispatcher.send(alert):
            print("Test alert sent successfully!")
            return 0
        else:
            print("Failed to send test alert.")
            return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


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
    research_catalog.add_argument("--overrides", help="Overrides JSON path.")
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

    # Models command group
    models_parser = subparsers.add_parser("models", help="Model deployment and management.")
    models_sub = models_parser.add_subparsers(dest="models_command")

    # afs models list
    models_list = models_sub.add_parser("list", help="List all trained models.")
    models_list.set_defaults(func=_models_list_command)

    # afs models status <model>
    models_status = models_sub.add_parser("status", help="Show detailed model status.")
    models_status.add_argument("model", help="Model name (e.g., 7b_asm_v4)")
    models_status.set_defaults(func=_models_status_command)

    # afs models deploy <model>
    models_deploy = models_sub.add_parser("deploy", help="Deploy a model to a target.")
    models_deploy.add_argument("model", help="Model name (e.g., 7b_asm_v4)")
    models_deploy.add_argument(
        "--target",
        choices=["ollama"],
        default="ollama",
        help="Deployment target (default: ollama)",
    )
    models_deploy.add_argument(
        "--quantization",
        choices=["Q4_K_M", "Q5_K_M", "Q8_0", "Q4_K_S"],
        default="Q4_K_M",
        help="GGUF quantization level (default: Q4_K_M)",
    )
    models_deploy.add_argument(
        "--skip-merge",
        action="store_true",
        help="Skip LoRA merge if already done",
    )
    models_deploy.add_argument(
        "--skip-gguf",
        action="store_true",
        help="Skip GGUF conversion if already done",
    )
    models_deploy.set_defaults(func=_models_deploy_command)

    # afs models test <model>
    models_test = models_sub.add_parser("test", help="Test a deployed model.")
    models_test.add_argument("model", help="Model name (e.g., 7b_asm_v4)")
    models_test.add_argument(
        "--method",
        choices=["ollama", "python"],
        default="ollama",
        help="Test method (default: ollama)",
    )
    models_test.add_argument(
        "--prompt",
        help="Custom test prompt (for python method)",
    )
    models_test.set_defaults(func=_models_test_command)

    # afs models chat <model>
    models_chat = models_sub.add_parser("chat", help="Interactive chat with a model.")
    models_chat.add_argument("model", help="Model name (e.g., 7b_asm_v4)")
    models_chat.set_defaults(func=_models_chat_command)

    # afs models backup <model>
    models_backup = models_sub.add_parser("backup", help="Backup a model to all locations.")
    models_backup.add_argument("model", help="Model name (e.g., 7b_asm_v4)")
    models_backup.set_defaults(func=_models_backup_command)

    # afs models verify <model>
    models_verify = models_sub.add_parser("verify", help="Verify model backups.")
    models_verify.add_argument("model", help="Model name (e.g., 7b_asm_v4)")
    models_verify.set_defaults(func=_models_verify_command)

    # Cost command group
    cost_parser = subparsers.add_parser("cost", help="Cost tracking and monitoring.")
    cost_sub = cost_parser.add_subparsers(dest="cost_command")

    # afs cost status
    cost_status = cost_sub.add_parser("status", help="Show current running costs.")
    cost_status.set_defaults(func=_cost_status_command)

    # afs cost daily
    cost_daily = cost_sub.add_parser("daily", help="Show daily cost summary.")
    cost_daily.set_defaults(func=_cost_daily_command)

    # afs cost balance
    cost_balance = cost_sub.add_parser("balance", help="Show account balance.")
    cost_balance.set_defaults(func=_cost_balance_command)

    # Budget command group
    budget_parser = subparsers.add_parser("budget", help="Budget management and enforcement.")
    budget_sub = budget_parser.add_subparsers(dest="budget_command")

    # afs budget check
    budget_check = budget_sub.add_parser("check", help="Check budget status.")
    budget_check.set_defaults(func=_budget_check_command)

    # afs budget enforce
    budget_enforce = budget_sub.add_parser("enforce", help="Enforce budget limits.")
    budget_enforce.add_argument(
        "--dry-run",
        action="store_true",
        help="Check only, don't take action",
    )
    budget_enforce.set_defaults(func=_budget_enforce_command)

    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Training status dashboard.")
    dashboard_parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously update dashboard",
    )
    dashboard_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Update interval in seconds (default: 30)",
    )
    dashboard_parser.add_argument(
        "--compact",
        action="store_true",
        help="Show compact single-line status",
    )
    dashboard_parser.set_defaults(func=_dashboard_command)

    # Alert command group
    alert_parser = subparsers.add_parser("alert", help="Alert management.")
    alert_sub = alert_parser.add_subparsers(dest="alert_command")

    # afs alert test
    alert_test = alert_sub.add_parser("test", help="Send a test alert.")
    alert_test.set_defaults(func=_alert_test_command)

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
    if args.command == "models" and not getattr(args, "models_command", None):
        parser.print_help()
        return 1
    if args.command == "cost" and not getattr(args, "cost_command", None):
        parser.print_help()
        return 1
    if args.command == "budget" and not getattr(args, "budget_command", None):
        parser.print_help()
        return 1
    if args.command == "alert" and not getattr(args, "alert_command", None):
        parser.print_help()
        return 1
    # Dashboard command doesn't have subcommands
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
