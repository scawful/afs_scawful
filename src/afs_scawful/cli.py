"""AFS Scawful command-line helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
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
from .validators import default_validators, enhanced_validators
from .eval import EvalConfig, EvalPipeline
from .integrations.ollama_client import Prompt
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
from .chat_harness import run_chat, load_chat_registry, build_provider
from .cost_tracker import VultrCostTracker, format_cost_report
from .budget import BudgetEnforcer, format_budget_status
from .dashboard import Dashboard
from .alerting import AlertDispatcher, Alert, AlertLevel
from .infra_config import get_config
from .vast import (
    build_status_report,
    default_status_output_path,
    format_status,
    list_instance_names,
    send_alerts,
    write_status_json,
)


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


def _chat_run_command(args: argparse.Namespace) -> int:
    """Run interactive chat with provider and router support."""
    registry_path = (
        Path(args.registry_path).expanduser().resolve()
        if args.registry_path
        else None
    )
    system_path = (
        Path(args.system_file).expanduser().resolve()
        if args.system_file
        else None
    )
    return run_chat(
        model=args.model,
        router=args.router,
        provider=args.provider,
        system=args.system,
        system_path=system_path,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        ollama_host=args.ollama_host,
        registry_path=registry_path,
        enable_tools=args.tools,
    )


def _chat_list_models_command(args: argparse.Namespace) -> int:
    """List available chat models."""
    registry_path = (
        Path(args.registry_path).expanduser().resolve()
        if args.registry_path
        else None
    )

    if args.registry:
        registry = load_chat_registry(registry_path)
        models = registry.list_models(provider=args.provider)
        if not models:
            print("No registry models found.")
            return 1
        for model in models:
            role = f" - {model.role}" if model.role else ""
            print(f"{model.name} ({model.provider}:{model.model_id}){role}")
        return 0

    provider = args.provider or "ollama"
    client = build_provider(provider, ollama_host=args.ollama_host)

    async def run():
        if not getattr(client, "supports_model_listing", False):
            print("Provider does not support model listing.")
            return 1
        models = await client.list_models()
        if not models:
            print("No models returned.")
            return 1
        for name in models:
            print(name)
        return 0

    try:
        return asyncio.run(run())
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _chat_list_routers_command(args: argparse.Namespace) -> int:
    """List available chat routers."""
    registry_path = (
        Path(args.registry_path).expanduser().resolve()
        if args.registry_path
        else None
    )
    registry = load_chat_registry(registry_path)
    routers = registry.list_routers()
    if not routers:
        print("No routers found.")
        return 1
    for router in routers:
        print(f"{router.name} ({router.strategy}) - {router.description}")
    return 0


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


def _alert_send_command(args: argparse.Namespace) -> int:
    """Send a custom alert."""
    try:
        dispatcher = AlertDispatcher()
        if args.event:
            toggles = {
                "training-start": "alert_on_training_start",
                "training-complete": "alert_on_training_complete",
                "training-failed": "alert_on_training_failed",
                "eval-complete": "alert_on_eval_complete",
                "backup-complete": "alert_on_backup_complete",
                "export-complete": "alert_on_export_complete",
                "budget-warning": "alert_on_budget_warning",
                "idle-detected": "alert_on_idle_detection",
                "disk-warning": "alert_on_disk_warning",
            }
            toggle = toggles.get(args.event)
            if toggle and not getattr(dispatcher.config, toggle, True):
                print(f"Alert suppressed by config ({toggle}=false).")
                return 0
        tags = []
        if args.tags:
            tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
        alert = Alert(
            level=AlertLevel(args.level),
            title=args.title,
            message=args.message,
            instance=args.instance,
            cost=args.cost,
            tags=tags,
        )
        if dispatcher.send(alert):
            print("Alert sent.")
            return 0
        print("Failed to send alert.")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


# Vast commands
def _resolve_vast_output_path(args: argparse.Namespace) -> Path | None:
    output_path = None
    if getattr(args, "write_index", False):
        output_path = default_status_output_path()
    if getattr(args, "output", None):
        output_path = Path(args.output).expanduser().resolve()
    return output_path


def _build_vast_report_from_args(args: argparse.Namespace):
    instances_dir = (
        Path(args.instances_dir).expanduser().resolve() if args.instances_dir else None
    )
    metadata_path = (
        Path(args.metadata).expanduser().resolve() if args.metadata else None
    )
    training_dir = args.training_dir or get_config().training.remote_training_dir
    include_remote = not args.skip_remote
    return build_status_report(
        instance_id=args.id,
        name=args.name,
        metadata_path=metadata_path,
        instances_dir=instances_dir,
        training_dir=training_dir,
        include_remote=include_remote,
        log_lines=args.log_lines,
    )


def _build_vast_reports_from_args(args: argparse.Namespace) -> list:
    if not getattr(args, "all", False):
        return [_build_vast_report_from_args(args)]

    instances_dir = (
        Path(args.instances_dir).expanduser().resolve() if args.instances_dir else None
    )
    names = list_instance_names(instances_dir)
    if not names:
        raise ValueError("No Vast instances found in metadata directory.")

    reports = []
    for name in names:
        clone = argparse.Namespace(**vars(args))
        clone.id = None
        clone.name = name
        clone.metadata = None
        reports.append(_build_vast_report_from_args(clone))
    return reports


def _write_vast_reports_json(reports: list, output_path: Path) -> None:
    if len(reports) == 1:
        write_status_json(reports[0], output_path)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [report.to_dict() for report in reports]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _print_vast_reports(reports: list) -> None:
    for idx, report in enumerate(reports):
        if idx:
            print("\n" + ("-" * 60) + "\n")
        print(format_status(report))


def _vast_status_command(args: argparse.Namespace) -> int:
    """Show Vast training status."""
    try:
        reports = _build_vast_reports_from_args(args)
        output_path = _resolve_vast_output_path(args)
        if output_path:
            _write_vast_reports_json(reports, output_path)
        if args.json:
            payload = [report.to_dict() for report in reports]
            if len(payload) == 1:
                payload = payload[0]
            print(json.dumps(payload, indent=2))
        elif not args.quiet:
            _print_vast_reports(reports)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        instances_dir = (
            Path(args.instances_dir).expanduser().resolve() if args.instances_dir else None
        )
        names = list_instance_names(instances_dir)
        if names:
            print("Known Vast instances:")
            for name in names:
                print(f"  - {name}")
        return 1


def _vast_check_command(args: argparse.Namespace) -> int:
    """Check Vast instance health and optionally alert."""
    try:
        reports = _build_vast_reports_from_args(args)
        output_path = _resolve_vast_output_path(args)
        if output_path:
            _write_vast_reports_json(reports, output_path)
        if args.json:
            payload = [report.to_dict() for report in reports]
            if len(payload) == 1:
                payload = payload[0]
            print(json.dumps(payload, indent=2))
        elif not args.quiet:
            _print_vast_reports(reports)
        if args.alert:
            for report in reports:
                send_alerts(report)
        if any(report.issues for report in reports) and not args.no_fail:
            return 2
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _vast_watch_command(args: argparse.Namespace) -> int:
    """Continuously watch Vast status."""
    output_path = _resolve_vast_output_path(args)
    try:
        while True:
            reports = _build_vast_reports_from_args(args)
            if output_path:
                _write_vast_reports_json(reports, output_path)
            if args.alert:
                for report in reports:
                    send_alerts(report)
            if args.json:
                payload = [report.to_dict() for report in reports]
                if len(payload) == 1:
                    payload = payload[0]
                print(json.dumps(payload, indent=2))
            elif not args.quiet:
                print("\033[2J\033[H", end="")
                _print_vast_reports(reports)
                print(f"\nRefreshing in {args.interval}s... (Ctrl+C to exit)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        if not args.quiet:
            print("\nExiting Vast watch.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


# Eval commands
def _apply_model_overrides(config: EvalConfig, args: argparse.Namespace) -> None:
    if getattr(args, "model", None):
        config.model.name = args.model
    if getattr(args, "provider", None):
        config.model.provider = args.provider
    if getattr(args, "base_url", None):
        config.model.base_url = args.base_url
    if getattr(args, "studio_key_env", None):
        config.model.studio_api_key_env = args.studio_key_env
    if getattr(args, "vertex_project", None):
        config.model.vertex_project = args.vertex_project
    if getattr(args, "vertex_location", None):
        config.model.vertex_location = args.vertex_location
    if getattr(args, "gcloud_path", None):
        config.model.gcloud_path = args.gcloud_path


def _eval_test_command(args: argparse.Namespace) -> int:
    """Run a single evaluation test."""
    config = EvalConfig()
    _apply_model_overrides(config, args)

    pipeline = EvalPipeline(config)

    async def run():
        result = await pipeline.eval_interactive(args.prompt)
        print(f"\n{'='*60}")
        print(f"Prompt: {args.prompt}")
        print(f"{'='*60}")
        print(f"\nResponse:\n{result.response.text}")
        print(f"\n{'='*60}")
        print(f"Valid: {'Yes' if result.success else 'No'}")
        print(f"Score: {result.score:.2f}")
        print(f"Latency: {result.response.latency_ms:.0f}ms")
        if result.response.tokens_per_second > 0:
            print(f"Tokens/s: {result.response.tokens_per_second:.1f}")
        if result.validation.errors:
            print(f"\nErrors:")
            for err in result.validation.errors[:5]:
                print(f"  - {err}")
        if result.validation.details:
            print(f"\nDetails:")
            for key, val in result.validation.details.items():
                if isinstance(val, dict) and "score" in val:
                    print(f"  {key}: score={val['score']:.2f}")
        return 0 if result.success else 1

    try:
        return asyncio.run(run())
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _eval_batch_command(args: argparse.Namespace) -> int:
    """Run batch evaluation from a prompts file."""
    config = EvalConfig()
    if args.config:
        config = EvalConfig.from_yaml(Path(args.config))
    _apply_model_overrides(config, args)

    pipeline = EvalPipeline(config)
    prompts_path = Path(args.prompts).expanduser().resolve()

    def progress(done: int, total: int, result):
        status = "pass" if result.success else "FAIL"
        print(f"[{done}/{total}] {status} score={result.score:.2f} {result.category}")

    async def run():
        report = await pipeline.eval_file(prompts_path)

        # Print summary
        print(f"\n{'='*60}")
        print(f"Evaluation Complete: {report.model_name}")
        print(f"{'='*60}")
        print(f"Total: {report.total}")
        print(f"Passed: {report.passed} ({report.pass_rate:.1%})")
        print(f"Failed: {report.failed}")
        print(f"Avg Score: {report.avg_score:.2f}")
        print(f"Avg Latency: {report.avg_latency_ms:.0f}ms")
        print(f"Duration: {report.duration_seconds:.1f}s")

        # Write report
        if args.report:
            report_path = Path(args.report).expanduser().resolve()
            if args.format == "json":
                report_path.write_text(report.to_json())
            else:
                report_path.write_text(report.to_markdown())
            print(f"\nReport saved: {report_path}")

        return 0 if report.pass_rate >= 0.5 else 1

    try:
        return asyncio.run(run())
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _eval_live_command(args: argparse.Namespace) -> int:
    """Interactive evaluation REPL."""
    config = EvalConfig()
    _apply_model_overrides(config, args)

    pipeline = EvalPipeline(config)

    print(f"Interactive Eval Mode - Model: {config.model.name}")
    print("Enter prompts to evaluate (Ctrl+D or 'exit' to quit)")
    print("-" * 60)

    async def eval_prompt(prompt_text: str):
        result = await pipeline.eval_interactive(prompt_text)
        print(f"\nResponse:")
        print(result.response.text)
        print(f"\n[{'PASS' if result.success else 'FAIL'}] "
              f"score={result.score:.2f} latency={result.response.latency_ms:.0f}ms")
        if result.validation.errors:
            for err in result.validation.errors[:3]:
                print(f"  Error: {err}")
        print()

    try:
        while True:
            try:
                prompt = input(">>> ").strip()
                if not prompt or prompt.lower() in ("exit", "quit", "/bye"):
                    break
                asyncio.run(eval_prompt(prompt))
            except EOFError:
                break
        print("\nExiting.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _eval_list_models_command(args: argparse.Namespace) -> int:
    """List available models for a provider."""
    config = EvalConfig()
    _apply_model_overrides(config, args)
    pipeline = EvalPipeline(config)

    async def run():
        models = await pipeline.client.list_models()
        if not models:
            print("No models returned.")
            return 1
        for name in models:
            print(name)
        return 0

    try:
        return asyncio.run(run())
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _eval_dataset_command(args: argparse.Namespace) -> int:
    """Validate a training dataset."""
    from .validators.asar_validator_v2 import AsarValidatorV2
    from .validators import AsmValidator

    dataset_path = Path(args.input).expanduser().resolve()
    if not dataset_path.exists():
        print(f"Error: Dataset not found: {dataset_path}")
        return 1

    validators = []
    if not args.skip_asm:
        validators.append(AsmValidator())
    if not args.skip_asar:
        validators.append(AsarValidatorV2(
            semantic_analysis=not args.skip_semantic,
        ))

    async def validate_dataset():
        passed = 0
        failed = 0
        total = 0

        with open(dataset_path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    sample = TrainingSample.from_dict(data)
                except Exception as e:
                    print(f"Line {line_num}: Parse error - {e}")
                    failed += 1
                    continue

                total += 1
                all_valid = True
                for validator in validators:
                    if validator.can_validate(sample):
                        result = await validator.validate(sample)
                        if not result.valid:
                            all_valid = False
                            if args.verbose:
                                print(f"Line {line_num}: {validator.name} failed - {result.errors[:1]}")
                            break

                if all_valid:
                    passed += 1
                else:
                    failed += 1

                if total % 100 == 0:
                    print(f"Processed {total} samples...")

        print(f"\n{'='*60}")
        print(f"Dataset Validation: {dataset_path.name}")
        print(f"{'='*60}")
        print(f"Total: {total}")
        print(f"Passed: {passed} ({passed/total*100:.1f}%)" if total > 0 else "Passed: 0")
        print(f"Failed: {failed}")
        return 0 if failed == 0 else 1

    try:
        return asyncio.run(validate_dataset())
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _add_vast_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", help="Vast instance id")
    parser.add_argument("--name", help="Instance label (matches metadata filename)")
    parser.add_argument("--metadata", help="Path to instance metadata JSON")
    parser.add_argument("--instances-dir", help="Directory containing instance metadata JSON")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Report on all instances in the metadata directory",
    )
    parser.add_argument(
        "--training-dir",
        help="Remote training directory (default: /opt/training)",
    )
    parser.add_argument(
        "--skip-remote",
        action="store_true",
        help="Skip SSH status checks",
    )
    parser.add_argument(
        "--log-lines",
        type=int,
        default=120,
        help="Log tail lines to scan (default: 120)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--output", help="Write JSON to this path")
    parser.add_argument(
        "--write-index",
        action="store_true",
        help="Write JSON to training index (vast_status.json)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-JSON output",
    )


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

    # Chat command group
    chat_parser = subparsers.add_parser("chat", help="Interactive chat harness.")
    chat_sub = chat_parser.add_subparsers(dest="chat_command")

    chat_run = chat_sub.add_parser("run", help="Interactive chat session.")
    chat_run.add_argument("--model", help="Model name or alias (default: none)")
    chat_run.add_argument("--router", help="Router name (from registry)")
    chat_run.add_argument(
        "--provider",
        choices=["ollama", "studio", "vertex"],
        help="Provider for direct model chat",
    )
    chat_run.add_argument("--system", help="System prompt override")
    chat_run.add_argument("--system-file", help="Path to system prompt file")
    chat_run.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature")
    chat_run.add_argument("--top-p", type=float, default=0.8, help="Top-p sampling")
    chat_run.add_argument("--max-tokens", type=int, default=512, help="Max response tokens")
    chat_run.add_argument("--ollama-host", help="Ollama host override")
    chat_run.add_argument("--registry-path", help="Chat registry TOML path")
    chat_run.add_argument("--tools", action="store_true", help="Enable AFS tools")
    chat_run.set_defaults(func=_chat_run_command)

    chat_list_models = chat_sub.add_parser("list-models", help="List chat models.")
    chat_list_models.add_argument(
        "--provider",
        choices=["ollama", "studio", "vertex"],
        help="Provider to query",
    )
    chat_list_models.add_argument(
        "--registry",
        action="store_true",
        help="List registry models instead of provider",
    )
    chat_list_models.add_argument("--ollama-host", help="Ollama host override")
    chat_list_models.add_argument("--registry-path", help="Chat registry TOML path")
    chat_list_models.set_defaults(func=_chat_list_models_command)

    chat_list_routers = chat_sub.add_parser("list-routers", help="List chat routers.")
    chat_list_routers.add_argument("--registry-path", help="Chat registry TOML path")
    chat_list_routers.set_defaults(func=_chat_list_routers_command)

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

    # Vast command group
    vast_parser = subparsers.add_parser("vast", help="Vast AI monitoring.")
    vast_sub = vast_parser.add_subparsers(dest="vast_command")

    vast_status = vast_sub.add_parser("status", help="Show Vast training status.")
    _add_vast_common_args(vast_status)
    vast_status.set_defaults(func=_vast_status_command)

    vast_check = vast_sub.add_parser("check", help="Health check and optional alerting.")
    _add_vast_common_args(vast_check)
    vast_check.add_argument(
        "--alert",
        action="store_true",
        help="Send alerts when issues are detected",
    )
    vast_check.add_argument(
        "--no-fail",
        action="store_true",
        help="Exit 0 even when issues are detected",
    )
    vast_check.set_defaults(func=_vast_check_command)

    vast_watch = vast_sub.add_parser("watch", help="Continuously monitor Vast status.")
    _add_vast_common_args(vast_watch)
    vast_watch.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Update interval in seconds (default: 30)",
    )
    vast_watch.add_argument(
        "--alert",
        action="store_true",
        help="Send alerts when issues are detected",
    )
    vast_watch.set_defaults(func=_vast_watch_command)

    # Alert command group
    alert_parser = subparsers.add_parser("alert", help="Alert management.")
    alert_sub = alert_parser.add_subparsers(dest="alert_command")

    # afs alert test
    alert_test = alert_sub.add_parser("test", help="Send a test alert.")
    alert_test.set_defaults(func=_alert_test_command)

    # afs alert send --message "..."
    alert_send = alert_sub.add_parser("send", help="Send a custom alert.")
    alert_send.add_argument("--message", "-m", required=True, help="Alert message.")
    alert_send.add_argument("--title", "-t", default="AFS Alert", help="Alert title.")
    alert_send.add_argument(
        "--level",
        choices=[level.value for level in AlertLevel],
        default=AlertLevel.INFO.value,
        help="Alert level.",
    )
    alert_send.add_argument(
        "--event",
        choices=[
            "training-start",
            "training-complete",
            "training-failed",
            "eval-complete",
            "backup-complete",
            "export-complete",
            "budget-warning",
            "idle-detected",
            "disk-warning",
        ],
        help="Alert event type (respects alert toggles).",
    )
    alert_send.add_argument(
        "--tags",
        help="Comma-separated tags (e.g. training,complete).",
    )
    alert_send.add_argument("--instance", help="Instance label or ID.")
    alert_send.add_argument("--cost", type=float, help="Cost value.")
    alert_send.set_defaults(func=_alert_send_command)

    # Eval command group
    eval_parser = subparsers.add_parser("eval", help="Model evaluation tools.")
    eval_sub = eval_parser.add_subparsers(dest="eval_command")

    # afs eval test --prompt "..."
    eval_test = eval_sub.add_parser("test", help="Run a single evaluation test.")
    eval_test.add_argument("--prompt", "-p", required=True, help="Prompt to evaluate.")
    eval_test.add_argument("--model", "-m", help="Model name (default: nayru-7b-v1:latest)")
    eval_test.add_argument("--provider", choices=["ollama", "studio", "vertex"], help="Model provider")
    eval_test.add_argument("--base-url", help="Ollama base URL override")
    eval_test.add_argument("--studio-key-env", help="Env var for AI Studio API key")
    eval_test.add_argument("--vertex-project", help="Vertex AI project id")
    eval_test.add_argument("--vertex-location", help="Vertex AI location")
    eval_test.add_argument("--gcloud-path", help="Path to gcloud binary")
    eval_test.set_defaults(func=_eval_test_command)

    # afs eval batch --prompts file.jsonl
    eval_batch = eval_sub.add_parser("batch", help="Batch evaluation from prompts file.")
    eval_batch.add_argument("--prompts", "-p", required=True, help="JSONL file with prompts.")
    eval_batch.add_argument("--report", "-r", help="Output report path.")
    eval_batch.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown")
    eval_batch.add_argument("--model", "-m", help="Model name override.")
    eval_batch.add_argument("--config", "-c", help="YAML config file.")
    eval_batch.add_argument("--provider", choices=["ollama", "studio", "vertex"], help="Model provider")
    eval_batch.add_argument("--base-url", help="Ollama base URL override")
    eval_batch.add_argument("--studio-key-env", help="Env var for AI Studio API key")
    eval_batch.add_argument("--vertex-project", help="Vertex AI project id")
    eval_batch.add_argument("--vertex-location", help="Vertex AI location")
    eval_batch.add_argument("--gcloud-path", help="Path to gcloud binary")
    eval_batch.set_defaults(func=_eval_batch_command)

    # afs eval live
    eval_live = eval_sub.add_parser("live", help="Interactive evaluation REPL.")
    eval_live.add_argument("--model", "-m", help="Model name (default: nayru-7b-v1:latest)")
    eval_live.add_argument("--provider", choices=["ollama", "studio", "vertex"], help="Model provider")
    eval_live.add_argument("--base-url", help="Ollama base URL override")
    eval_live.add_argument("--studio-key-env", help="Env var for AI Studio API key")
    eval_live.add_argument("--vertex-project", help="Vertex AI project id")
    eval_live.add_argument("--vertex-location", help="Vertex AI location")
    eval_live.add_argument("--gcloud-path", help="Path to gcloud binary")
    eval_live.set_defaults(func=_eval_live_command)

    # afs eval list-models
    eval_list = eval_sub.add_parser("list-models", help="List models for a provider.")
    eval_list.add_argument("--provider", choices=["ollama", "studio", "vertex"], help="Model provider")
    eval_list.add_argument("--base-url", help="Ollama base URL override")
    eval_list.add_argument("--studio-key-env", help="Env var for AI Studio API key")
    eval_list.add_argument("--vertex-project", help="Vertex AI project id")
    eval_list.add_argument("--vertex-location", help="Vertex AI location")
    eval_list.add_argument("--gcloud-path", help="Path to gcloud binary")
    eval_list.set_defaults(func=_eval_list_models_command)

    # afs eval dataset --input train.jsonl
    eval_dataset = eval_sub.add_parser("dataset", help="Validate a training dataset.")
    eval_dataset.add_argument("--input", "-i", required=True, help="Dataset JSONL file.")
    eval_dataset.add_argument("--verbose", "-v", action="store_true", help="Show validation errors.")
    eval_dataset.add_argument("--skip-asm", action="store_true", help="Skip ASM validator.")
    eval_dataset.add_argument("--skip-asar", action="store_true", help="Skip ASAR validator.")
    eval_dataset.add_argument("--skip-semantic", action="store_true", help="Skip semantic analysis.")
    eval_dataset.set_defaults(func=_eval_dataset_command)

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
    if args.command == "chat" and not getattr(args, "chat_command", None):
        parser.print_help()
        return 1
    if args.command == "cost" and not getattr(args, "cost_command", None):
        parser.print_help()
        return 1
    if args.command == "budget" and not getattr(args, "budget_command", None):
        parser.print_help()
        return 1
    if args.command == "vast" and not getattr(args, "vast_command", None):
        parser.print_help()
        return 1
    if args.command == "alert" and not getattr(args, "alert_command", None):
        parser.print_help()
        return 1
    if args.command == "eval" and not getattr(args, "eval_command", None):
        parser.print_help()
        return 1
    # Dashboard command doesn't have subcommands
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
