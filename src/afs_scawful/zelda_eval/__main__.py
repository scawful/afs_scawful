"""
Zelda Model Evaluation CLI.

Usage:
    python -m afs_scawful.zelda_eval benchmarks list
    python -m afs_scawful.zelda_eval benchmarks run --expert din --category knowledge_65816
    python -m afs_scawful.zelda_eval oracle extract
    python -m afs_scawful.zelda_eval sandbox create
    python -m afs_scawful.zelda_eval vast deploy
    python -m afs_scawful.zelda_eval vast status
"""

import asyncio
import json
import os
import subprocess
import shutil
import click
from pathlib import Path

from .benchmarks.base import BenchmarkCategory, Difficulty
from .benchmarks.knowledge import get_knowledge_suite, get_65816_suite, get_alttp_suite, get_snes_suite
from .benchmarks.oracle_tasks import OracleTaskExtractor, get_oracle_suite
from .experts.registry import ExpertRegistry
from .sandbox.worktree import WorktreeManager, SandboxConfig
from .sandbox.builder import AsarBuilder


@click.group()
def cli():
    """Zelda Model Evaluation & Agentic Testing System."""
    pass


# === Benchmarks Commands ===
@cli.group()
def benchmarks():
    """Manage evaluation benchmarks."""
    pass


@benchmarks.command("list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--difficulty", "-d", help="Filter by difficulty")
def list_benchmarks(category: str | None, difficulty: str | None):
    """List available benchmark cases."""
    suite = get_knowledge_suite()

    if category:
        try:
            cat = BenchmarkCategory(category)
            cases = suite.filter_by_category(cat)
        except ValueError:
            click.echo(f"Unknown category: {category}")
            click.echo(f"Available: {[c.value for c in BenchmarkCategory]}")
            return
    else:
        cases = list(suite)

    if difficulty:
        try:
            diff = Difficulty(difficulty)
            cases = [c for c in cases if c.difficulty == diff]
        except ValueError:
            click.echo(f"Unknown difficulty: {difficulty}")
            return

    click.echo(f"Found {len(cases)} benchmark cases:\n")
    for case in cases:
        click.echo(f"  [{case.difficulty.value:6}] {case.id}")
        click.echo(f"           {case.prompt[:60]}...")
        click.echo()


@benchmarks.command("categories")
def list_categories():
    """List all benchmark categories."""
    click.echo("Benchmark Categories:\n")
    for cat in BenchmarkCategory:
        click.echo(f"  {cat.value}")


@benchmarks.command("run")
@click.option("--expert", "-e", required=True, help="Expert model to evaluate (din, nayru, farore, veran)")
@click.option("--category", "-c", help="Benchmark category to run")
@click.option("--case-id", help="Run a specific case by ID")
@click.option("--output", "-o", type=click.Path(), help="Output file for results")
def run_benchmark(expert: str, category: str | None, case_id: str | None, output: str | None):
    """Run benchmarks against an expert model."""
    registry = ExpertRegistry()
    expert_record = registry.get(expert)

    if not expert_record:
        click.echo(f"Unknown expert: {expert}")
        click.echo(f"Available: {[e.name for e in registry.list_experts()]}")
        return

    suite = get_knowledge_suite()

    if case_id:
        cases = [c for c in suite if c.id == case_id]
        if not cases:
            click.echo(f"Case not found: {case_id}")
            return
    elif category:
        try:
            cat = BenchmarkCategory(category)
            cases = suite.filter_by_category(cat)
        except ValueError:
            click.echo(f"Unknown category: {category}")
            return
    else:
        cases = list(suite)

    click.echo(f"Running {len(cases)} benchmarks with {expert_record.display_name}...")
    click.echo(f"Model: {expert_record.model_id}")
    click.echo()

    # Note: Full evaluation would use the orchestrator
    # For now, just show what would be run
    for case in cases:
        click.echo(f"  Would evaluate: {case.id}")

    click.echo(f"\n(Full evaluation requires running models - not implemented in this minimal CLI)")


# === Oracle Commands ===
@cli.group()
def oracle():
    """Manage Oracle-of-Secrets tasks."""
    pass


@oracle.command("extract")
@click.option("--limit", "-n", type=int, help="Limit number of tasks")
@click.option("--output", "-o", type=click.Path(), help="Output JSON file")
def extract_tasks(limit: int | None, output: str | None):
    """Extract TODOs from Oracle-of-Secrets codebase."""
    try:
        extractor = OracleTaskExtractor()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
        return

    tasks = extractor.extract_all()
    click.echo(f"Found {len(tasks)} tasks")

    # Show distribution
    from collections import Counter
    markers = Counter(t.marker for t in tasks)
    types = Counter(t.task_type for t in tasks)

    click.echo(f"\nBy marker: {dict(markers)}")
    click.echo(f"By type: {dict(types)}")

    if limit:
        tasks = tasks[:limit]

    if output:
        # Convert to benchmark cases and save
        cases = extractor.to_benchmark_cases(tasks)
        output_data = [
            {
                "id": c.id,
                "category": c.category.value,
                "prompt": c.prompt,
                "difficulty": c.difficulty.value,
                "source_file": c.source_file,
                "source_line": c.source_line,
                "tags": c.tags,
            }
            for c in cases
        ]
        Path(output).write_text(json.dumps(output_data, indent=2))
        click.echo(f"\nSaved {len(cases)} benchmark cases to {output}")
    else:
        click.echo("\nSample tasks:")
        for task in tasks[:5]:
            click.echo(f"  {task.file_path}:{task.line_number}")
            click.echo(f"    [{task.marker}] {task.text[:70]}...")
            click.echo()


# === Sandbox Commands ===
@cli.group()
def sandbox():
    """Manage testing sandboxes."""
    pass


@sandbox.command("create")
@click.option("--session-id", help="Session ID to associate")
def create_sandbox(session_id: str | None):
    """Create a new sandbox worktree."""
    try:
        manager = WorktreeManager()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
        return

    sandbox = manager.create_sandbox(session_id=session_id)
    click.echo(f"Created sandbox: {sandbox.id}")
    click.echo(f"Path: {sandbox.worktree_path}")
    click.echo(f"Branch: {sandbox.branch_name}")


@sandbox.command("list")
def list_sandboxes():
    """List active sandboxes."""
    try:
        manager = WorktreeManager()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
        return

    sandboxes = manager.list_sandboxes()
    if not sandboxes:
        click.echo("No active sandboxes")
        return

    click.echo(f"Active sandboxes ({len(sandboxes)}):\n")
    for sb in sandboxes:
        click.echo(f"  {sb.id}")
        click.echo(f"    Status: {sb.status}")
        click.echo(f"    Path: {sb.worktree_path}")
        click.echo(f"    Created: {sb.created_at}")
        click.echo()


@sandbox.command("cleanup")
@click.argument("sandbox_id")
def cleanup_sandbox(sandbox_id: str):
    """Remove a sandbox."""
    try:
        manager = WorktreeManager()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
        return

    if manager.cleanup_sandbox(sandbox_id):
        click.echo(f"Cleaned up sandbox: {sandbox_id}")
    else:
        click.echo(f"Failed to cleanup sandbox: {sandbox_id}")


@sandbox.command("build")
@click.argument("sandbox_id")
def build_sandbox(sandbox_id: str):
    """Build ROM in a sandbox."""
    try:
        manager = WorktreeManager()
        builder = AsarBuilder()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
        return

    sandbox = manager.get_sandbox(sandbox_id)
    if not sandbox:
        click.echo(f"Sandbox not found: {sandbox_id}")
        return

    click.echo(f"Building in {sandbox.worktree_path}...")
    result = builder.build(sandbox)

    if result.success:
        click.echo(f"Build successful!")
        click.echo(f"ROM: {result.rom_path}")
        if result.symbols_path:
            click.echo(f"Symbols: {result.symbols_path}")
        click.echo(f"Time: {result.build_time_seconds:.2f}s")
    else:
        click.echo("Build failed!")
        for error in result.errors:
            click.echo(f"  Error: {error}")

    if result.warnings:
        click.echo(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings[:10]:
            click.echo(f"  {warning}")


# === Experts Commands ===
@cli.group()
def experts():
    """Manage expert models."""
    pass


@experts.command("list")
def list_experts():
    """List available expert models."""
    registry = ExpertRegistry()

    click.echo("Available Experts:\n")
    for expert in registry.list_experts():
        status = "[enabled]" if expert.enabled else "[disabled]"
        click.echo(f"  {expert.name}: {expert.display_name} {status}")
        click.echo(f"      Model: {expert.model_id}")
        click.echo(f"      Specialty: {expert.specialty}")
        click.echo()


@experts.command("check")
@click.option("--ollama-host", envvar="OLLAMA_HOST", help="Ollama host URL")
def check_experts(ollama_host: str | None):
    """Check which experts are available via Ollama."""
    registry = ExpertRegistry(host=ollama_host)

    if ollama_host:
        click.echo(f"Checking Ollama at: {ollama_host}")
    else:
        click.echo(f"Checking Ollama at: {registry.host}")
    click.echo("Checking expert availability...")

    async def check():
        return await registry.check_availability()

    results = asyncio.run(check())

    click.echo("\nExpert Availability:\n")
    for name, available in results.items():
        expert = registry.get(name)
        if available:
            if expert.using_fallback:
                status = f"FALLBACK ({expert.fallback_model_id})"
            else:
                status = f"available ({expert.model_id})"
        else:
            status = "NOT FOUND"
        click.echo(f"  {name}: {status}")
        if not available:
            click.echo(f"      (tried {expert.model_id}, fallback {expert.fallback_model_id})")


# === Agent Commands ===
@cli.group()
def agent():
    """Run agentic evaluation tasks."""
    pass


@agent.command("run")
@click.argument("task")
@click.option("--max-iterations", "-n", type=int, default=10, help="Maximum iterations")
@click.option("--thinking/--no-thinking", default=True, help="Enable extended thinking")
@click.option("--sandbox/--no-sandbox", default=True, help="Auto-create sandbox for code tasks")
@click.option("--output", "-o", type=click.Path(), help="Output file for results")
def run_agent(task: str, max_iterations: int, thinking: bool, sandbox: bool, output: str | None):
    """Run an agentic task with the Gemini orchestrator."""
    try:
        from .agents.loop import AgenticLoop, LoopConfig
        from .orchestrator.gemini import GeminiOrchestrator
        from .orchestrator.tools import ToolExecutor, get_tool_schemas
    except ImportError as e:
        click.echo(f"Import error: {e}")
        click.echo("Make sure google-genai is installed: pip install google-genai")
        return

    config = LoopConfig(
        max_iterations=max_iterations,
        thinking_threshold=0.5 if thinking else 1.0,
        create_sandbox=sandbox,
    )

    # Set up tool executor with sandbox components if available
    tool_executor = None
    try:
        manager = WorktreeManager()
        builder = AsarBuilder()
        registry = ExpertRegistry()
        tool_executor = ToolExecutor(
            sandbox_manager=manager,
            sandbox_builder=builder,
            expert_registry=registry,
        )
    except FileNotFoundError:
        click.echo("Warning: Sandbox not available (Oracle repo not found)")

    def on_iteration(result):
        status = "OK" if result.success else "FAIL"
        click.echo(f"  [{result.iteration}] {result.step[:50]}... [{status}]")
        if result.expert_used:
            click.echo(f"      -> Routed to {result.expert_used}")
        if result.error:
            click.echo(f"      Error: {result.error}")

    try:
        orchestrator = GeminiOrchestrator(tools=get_tool_schemas())
        loop = AgenticLoop(
            orchestrator=orchestrator,
            tool_executor=tool_executor,
            config=config,
            on_iteration=on_iteration,
        )
    except ImportError as e:
        click.echo(f"Failed to initialize orchestrator: {e}")
        return

    click.echo(f"Running agentic task: {task}")
    click.echo(f"Max iterations: {max_iterations}")
    click.echo()

    async def run():
        return await loop.run(task)

    result = asyncio.run(run())

    click.echo()
    click.echo(f"{'=' * 50}")
    click.echo(f"Task: {result.task}")
    click.echo(f"Success: {result.success}")
    click.echo(f"Iterations: {len(result.iterations)}")
    click.echo(f"Duration: {result.total_duration_seconds:.2f}s")

    if result.sandbox_id:
        click.echo(f"Sandbox: {result.sandbox_id}")

    click.echo(f"\nFinal output:\n{result.final_output[:500]}...")

    if output:
        output_data = {
            "task": result.task,
            "success": result.success,
            "iterations": [
                {
                    "iteration": r.iteration,
                    "step": r.step,
                    "success": r.success,
                    "output": r.output,
                    "error": r.error,
                    "expert_used": r.expert_used,
                    "tool_calls": r.tool_calls,
                }
                for r in result.iterations
            ],
            "total_duration_seconds": result.total_duration_seconds,
            "final_output": result.final_output,
            "sandbox_id": result.sandbox_id,
            "artifacts": result.artifacts,
        }
        Path(output).write_text(json.dumps(output_data, indent=2, default=str))
        click.echo(f"\nResults saved to {output}")


@agent.command("todo")
@click.argument("todo_id")
@click.option("--max-iterations", "-n", type=int, default=10, help="Maximum iterations")
def run_todo(todo_id: str, max_iterations: int):
    """Run an agentic task on an Oracle TODO by ID."""
    try:
        extractor = OracleTaskExtractor()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
        return

    tasks = extractor.extract_all()
    cases = extractor.to_benchmark_cases(tasks)

    # Find matching case
    matching = [c for c in cases if todo_id in c.id]
    if not matching:
        click.echo(f"No TODO found matching: {todo_id}")
        click.echo("\nAvailable TODOs:")
        for case in cases[:10]:
            click.echo(f"  {case.id}")
        return

    case = matching[0]
    click.echo(f"Found TODO: {case.id}")
    click.echo(f"Source: {case.source_file}:{case.source_line}")
    click.echo(f"Prompt: {case.prompt[:100]}...")
    click.echo()

    # Run the agent command with this task
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(
        run_agent,
        [case.prompt, "-n", str(max_iterations)],
        catch_exceptions=False,
    )
    click.echo(result.output)


# === Harness Commands ===
@cli.command("eval")
@click.option("--expert", "-e", required=True, help="Expert to evaluate")
@click.option("--category", "-c", help="Benchmark category")
@click.option("--limit", "-n", type=int, help="Limit number of benchmarks")
@click.option("--output", "-o", type=click.Path(), help="Output file for results")
@click.option("--log-file", "-l", type=click.Path(), help="Log file for detailed events (JSON lines)")
@click.option("--metrics-file", "-m", type=click.Path(), help="Metrics file for aggregated stats")
@click.option("--verbose/--quiet", "-v/-q", default=True, help="Verbose console output")
@click.option("--ollama-host", envvar="OLLAMA_HOST", help="Ollama host URL (or set OLLAMA_HOST env var)")
def run_evaluation(
    expert: str,
    category: str | None,
    limit: int | None,
    output: str | None,
    log_file: str | None,
    metrics_file: str | None,
    verbose: bool,
    ollama_host: str | None,
):
    """Run full evaluation harness for an expert model with detailed logging."""
    try:
        from .agents.loop import AgenticLoop, LoopConfig, EvaluationRunner
        from .orchestrator.gemini import GeminiOrchestrator
        from .orchestrator.tools import get_tool_schemas
        from .metrics.logger import EvalLogger
        from .metrics.collector import MetricsCollector
    except ImportError as e:
        click.echo(f"Import error: {e}")
        return

    # Initialize registry with optional remote Ollama host
    registry = ExpertRegistry(host=ollama_host)
    expert_record = registry.get(expert)

    if ollama_host:
        click.echo(f"Using Ollama host: {ollama_host}")

    if not expert_record:
        click.echo(f"Unknown expert: {expert}")
        return

    suite = get_knowledge_suite()

    if category:
        try:
            cat = BenchmarkCategory(category)
            cases = suite.filter_by_category(cat)
        except ValueError:
            click.echo(f"Unknown category: {category}")
            return
    else:
        cases = list(suite)

    if limit:
        cases = cases[:limit]

    click.echo(f"Evaluating {expert_record.display_name} on {len(cases)} benchmarks")
    if log_file:
        click.echo(f"Logging to: {log_file}")
    click.echo()

    config = LoopConfig(max_iterations=5, create_sandbox=False)

    try:
        from .orchestrator.tools import ToolExecutor

        orchestrator = GeminiOrchestrator(tools=get_tool_schemas())

        # Create tool executor with the registry
        tool_executor = ToolExecutor(expert_registry=registry)

        # Initialize with logging
        runner = EvaluationRunner(
            config=config,
            log_file=log_file,
            console_output=verbose,
        )
        # Inject orchestrator and registry with tool executor
        runner.loop.orchestrator = orchestrator
        runner.loop.expert_registry = registry
        runner.loop.tool_executor = tool_executor
    except ImportError as e:
        click.echo(f"Failed to initialize: {e}")
        return

    async def run():
        # Include category and difficulty in benchmarks
        benchmarks = [
            (c.id, c.prompt, c.category.value, c.difficulty.value)
            for c in cases
        ]
        return await runner.run_benchmarks(benchmarks, concurrency=1)

    results = asyncio.run(run())

    # Print detailed metrics report
    click.echo()
    runner.print_metrics_report()

    # Print MoE analysis
    moe_analysis = runner.get_expert_analysis()
    click.echo("\n--- MoE ROUTING ANALYSIS ---")
    click.echo(f"Avg routing confidence: {moe_analysis['avg_routing_confidence']:.1%}")
    click.echo(f"Low confidence routes: {moe_analysis['low_confidence_routes']}")
    click.echo("\nExpert distribution:")
    for expert_name, pct in moe_analysis['routing_distribution'].items():
        success_rate = moe_analysis['expert_success_rates'].get(expert_name, 0)
        calls = moe_analysis['expert_call_counts'].get(expert_name, 0)
        click.echo(f"  {expert_name}: {pct:.1%} of calls, {success_rate:.0%} success ({calls} total)")

    # Save metrics if requested
    if metrics_file:
        runner.save_metrics(metrics_file)
        click.echo(f"\nDetailed metrics saved to {metrics_file}")

    if output:
        output_data = {
            "expert": expert,
            "summary": runner.get_summary(),
            "moe_analysis": moe_analysis,
            "results": [
                {
                    "benchmark_id": bid,
                    "success": r.success,
                    "iterations": len(r.iterations),
                    "duration": r.total_duration_seconds,
                }
                for bid, r in results
            ],
        }
        Path(output).write_text(json.dumps(output_data, indent=2))
        click.echo(f"\nResults saved to {output}")

    runner.close()


# === Vast.ai Commands ===
@cli.group()
def vast():
    """Manage Vast.ai GPU instances for inference."""
    pass


def _get_vast_scripts_dir() -> Path:
    """Get the path to Vast.ai scripts directory."""
    return Path(__file__).parent.parent.parent.parent / "infra" / "vast"


def _get_vast_cli() -> str | None:
    """Find the vastai CLI command."""
    for cmd in ("vastai", "vast"):
        if shutil.which(cmd):
            return cmd
    return None


def _load_instance_metadata(name: str) -> dict | None:
    """Load instance metadata from JSON file."""
    scripts_dir = _get_vast_scripts_dir()
    metadata_path = scripts_dir / "instances" / f"{name}.json"
    if metadata_path.exists():
        return json.loads(metadata_path.read_text())
    return None


@vast.command("deploy")
@click.option("--name", "-n", default="zelda-ollama", help="Instance name/label")
@click.option("--gpu", "-g", default="RTX_4090", help="GPU type (RTX_4090, A100, etc.)")
@click.option("--vram", type=int, default=24, help="Minimum VRAM in GB")
@click.option("--disk", type=int, default=100, help="Disk size in GB")
def vast_deploy(name: str, gpu: str, vram: int, disk: int):
    """Deploy an Ollama inference instance on Vast.ai."""
    scripts_dir = _get_vast_scripts_dir()
    deploy_script = scripts_dir / "vast_deploy_ollama.sh"

    if not deploy_script.exists():
        click.echo(f"Error: Deploy script not found: {deploy_script}")
        return

    if not os.environ.get("VAST_API_KEY"):
        click.echo("Error: VAST_API_KEY environment variable not set")
        click.echo("Get your API key from https://cloud.vast.ai/account/")
        return

    click.echo(f"Deploying Ollama instance: {name}")
    click.echo(f"GPU: {gpu} ({vram}GB VRAM)")
    click.echo(f"Disk: {disk}GB")
    click.echo()

    env = os.environ.copy()
    env["GPU_NAME"] = gpu
    env["GPU_RAM_GB"] = str(vram)
    env["DISK_GB"] = str(disk)

    result = subprocess.run(
        ["bash", str(deploy_script), name],
        env=env,
        cwd=scripts_dir,
    )

    if result.returncode == 0:
        metadata = _load_instance_metadata(name)
        if metadata:
            click.echo()
            click.echo("=" * 50)
            click.echo("Instance deployed! Set OLLAMA_HOST to use:")
            click.echo()
            ssh_host = metadata.get("ssh_host", "UNKNOWN")
            click.echo(f"  export OLLAMA_HOST=http://{ssh_host}:11434")
            click.echo()
            click.echo("Then run evaluation:")
            click.echo("  python -m afs_scawful.zelda_eval eval --expert veran -c knowledge_65816")


@vast.command("status")
@click.option("--name", "-n", default="zelda-ollama", help="Instance name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def vast_status(name: str, as_json: bool):
    """Check status of a Vast.ai instance."""
    metadata = _load_instance_metadata(name)

    if not metadata:
        click.echo(f"No instance found: {name}")
        click.echo("Deploy with: python -m afs_scawful.zelda_eval vast deploy")
        return

    instance_id = metadata.get("instance_id")
    ssh_host = metadata.get("ssh_host")
    ssh_port = metadata.get("ssh_port", 22)

    if as_json:
        click.echo(json.dumps(metadata, indent=2))
        return

    click.echo(f"Instance: {name}")
    click.echo(f"  ID: {instance_id}")
    click.echo(f"  GPU: {metadata.get('gpu_name')} ({metadata.get('num_gpus')}x)")
    click.echo(f"  VRAM: {metadata.get('gpu_ram')} GB")
    click.echo(f"  SSH: {ssh_host}:{ssh_port}")
    click.echo()

    # Try to check if Ollama is responding
    if ssh_host:
        click.echo("Checking Ollama status...")
        try:
            import httpx
            ollama_url = f"http://{ssh_host}:11434/api/tags"
            response = httpx.get(ollama_url, timeout=5.0)
            if response.status_code == 200:
                models = response.json().get("models", [])
                click.echo(f"  Ollama: ONLINE ({len(models)} models)")
                for m in models:
                    click.echo(f"    - {m.get('name')}")
            else:
                click.echo(f"  Ollama: ERROR (status {response.status_code})")
        except Exception as e:
            click.echo(f"  Ollama: OFFLINE or starting ({e})")
            click.echo("  (May take 2-3 minutes after deployment)")

    click.echo()
    click.echo("Connection info:")
    click.echo(f"  export OLLAMA_HOST=http://{ssh_host}:11434")
    click.echo(f"  ssh -p {ssh_port} root@{ssh_host}")


@vast.command("destroy")
@click.option("--name", "-n", default="zelda-ollama", help="Instance name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def vast_destroy(name: str, force: bool):
    """Destroy a Vast.ai instance."""
    metadata = _load_instance_metadata(name)

    if not metadata:
        click.echo(f"No instance found: {name}")
        return

    instance_id = metadata.get("instance_id")

    if not force:
        if not click.confirm(f"Destroy instance {name} (ID: {instance_id})?"):
            return

    vast_cli = _get_vast_cli()
    if not vast_cli:
        click.echo("Error: vastai CLI not found. Install with: pip install vastai")
        return

    result = subprocess.run(
        [vast_cli, "destroy", "instance", str(instance_id)],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo(f"Instance {name} destroyed")
        # Remove metadata file
        scripts_dir = _get_vast_scripts_dir()
        metadata_path = scripts_dir / "instances" / f"{name}.json"
        if metadata_path.exists():
            metadata_path.unlink()
    else:
        click.echo(f"Error: {result.stderr}")


@vast.command("list")
def vast_list():
    """List deployed instances."""
    scripts_dir = _get_vast_scripts_dir()
    instances_dir = scripts_dir / "instances"

    if not instances_dir.exists():
        click.echo("No instances deployed")
        return

    instances = list(instances_dir.glob("*.json"))
    if not instances:
        click.echo("No instances deployed")
        return

    click.echo(f"Deployed instances ({len(instances)}):\n")
    for path in instances:
        name = path.stem
        metadata = json.loads(path.read_text())
        ssh_host = metadata.get("ssh_host", "?")
        gpu = metadata.get("gpu_name", "?")
        click.echo(f"  {name}")
        click.echo(f"    GPU: {gpu}")
        click.echo(f"    OLLAMA_HOST: http://{ssh_host}:11434")
        click.echo()


@vast.command("connect")
@click.option("--name", "-n", default="zelda-ollama", help="Instance name")
def vast_connect(name: str):
    """Print export command for OLLAMA_HOST."""
    metadata = _load_instance_metadata(name)

    if not metadata:
        click.echo(f"No instance found: {name}")
        return

    ssh_host = metadata.get("ssh_host")
    click.echo(f"export OLLAMA_HOST=http://{ssh_host}:11434")


if __name__ == "__main__":
    cli()
