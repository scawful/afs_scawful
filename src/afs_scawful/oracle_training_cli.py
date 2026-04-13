"""Thin CLI entrypoints for Zelda/oracle training ops."""

from __future__ import annotations

import argparse
from pathlib import Path

from .model_ops import finalize_remote_run, write_active_runs_note
from .model_ops.finalize import resolve_remote_target, unique_local_run_dir
from .oracle_training import ZELDA_TRACK_SPECS, build_zelda_bundle, get_zelda_track_spec, validate_zelda_bundle_spec
from .oracle_training.zelda_eval_hooks import build_zelda_eval_plan, format_eval_plan, run_zelda_eval_hooks
from .oracle_training.zelda_registry_hooks import (
    build_zelda_registry_plan,
    format_registry_plan,
    run_zelda_registry_hooks,
)


def _default_artifact_path(local_run_dir: Path) -> Path:
    adapter_path = local_run_dir / "adapter_final"
    if adapter_path.exists():
        return adapter_path
    entries = sorted(path for path in local_run_dir.iterdir()) if local_run_dir.exists() else []
    if entries:
        return entries[0]
    return adapter_path


def build_bundle_command(args: argparse.Namespace) -> int:
    included = build_zelda_bundle(
        args.track,
        Path(args.output),
        repo_root=Path(args.repo_root).expanduser().resolve() if args.repo_root else None,
        training_root=Path(args.training_root).expanduser().resolve() if args.training_root else None,
        datasets_root=Path(args.datasets_root).expanduser().resolve() if args.datasets_root else None,
    )
    print(Path(args.output).expanduser().resolve())
    for item in included:
        print(item)
    return 0


def validate_bundle_command(args: argparse.Namespace) -> int:
    selected = validate_zelda_bundle_spec(
        args.track,
        repo_root=Path(args.repo_root).expanduser().resolve() if args.repo_root else None,
        training_root=Path(args.training_root).expanduser().resolve() if args.training_root else None,
        datasets_root=Path(args.datasets_root).expanduser().resolve() if args.datasets_root else None,
    )
    for item in selected["all_paths"]:
        print(item)
    return 0


def render_runs_command(args: argparse.Namespace) -> int:
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    written = write_active_runs_note(
        Path(args.config).expanduser().resolve(),
        ZELDA_TRACK_SPECS,
        output_path=output_path,
        no_probe_remote=args.no_probe_remote,
    )
    print(written)
    return 0


def finalize_run_command(args: argparse.Namespace) -> int:
    spec = get_zelda_track_spec(args.track)
    remote_dir = args.remote_dir or spec["remote_root"]
    target = resolve_remote_target(
        host=args.host,
        port=args.port,
        remote_dir=remote_dir,
        instance_id=args.instance_id,
        instance_name=args.instance_name,
        metadata_path=Path(args.metadata).expanduser().resolve() if args.metadata else None,
        instances_dir=Path(args.instances_dir).expanduser().resolve() if args.instances_dir else None,
    )
    default_local = Path.home() / "src" / "training" / "cloud_runs" / args.track
    local_run_dir = unique_local_run_dir(
        Path(args.local_run_dir).expanduser().resolve() if args.local_run_dir else default_local
    )
    result = finalize_remote_run(
        target,
        spec,
        local_run_dir=local_run_dir,
        poll_seconds=args.poll_seconds,
        wait_for_start=args.wait_for_start,
    )
    artifact_path = _default_artifact_path(result.local_run_dir)

    if args.run_eval_hooks:
        eval_plan = build_zelda_eval_plan(
            args.track,
            local_run_dir=result.local_run_dir,
            remote_target=target,
            adapter_path=artifact_path,
            training_root=Path(args.training_root).expanduser().resolve() if args.training_root else None,
            eval_pack_path=Path(args.eval_pack).expanduser().resolve() if args.eval_pack else None,
        )
        print(format_eval_plan(eval_plan))
        run_zelda_eval_hooks(eval_plan)

    if args.run_registry_hooks:
        registry_plan = build_zelda_registry_plan(
            args.track,
            artifact_path=artifact_path,
            training_models_root=Path(args.training_models_root).expanduser().resolve() if args.training_models_root else None,
            training_root=Path(args.training_root).expanduser().resolve() if args.training_root else None,
            model_mgr_path=Path(args.model_mgr).expanduser().resolve() if args.model_mgr else None,
            quantizations=args.registry_quantize or None,
            include_mlx=args.include_mlx,
            backup=args.backup,
        )
        print(format_registry_plan(registry_plan))
        run_zelda_registry_hooks(registry_plan)

    print(result.local_run_dir)
    return 0


def eval_hooks_command(args: argparse.Namespace) -> int:
    spec = get_zelda_track_spec(args.track)
    remote_target = None
    if args.host and args.port:
        remote_target = resolve_remote_target(host=args.host, port=args.port, remote_dir=args.remote_dir or spec["remote_root"])
    plan = build_zelda_eval_plan(
        args.track,
        local_run_dir=Path(args.run_dir).expanduser().resolve(),
        remote_target=remote_target,
        adapter_path=Path(args.adapter_path).expanduser().resolve() if args.adapter_path else None,
        training_root=Path(args.training_root).expanduser().resolve() if args.training_root else None,
        eval_pack_path=Path(args.eval_pack).expanduser().resolve() if args.eval_pack else None,
    )
    print(format_eval_plan(plan))
    if args.run:
        run_zelda_eval_hooks(plan)
    return 0


def registry_hooks_command(args: argparse.Namespace) -> int:
    plan = build_zelda_registry_plan(
        args.track,
        artifact_path=Path(args.artifact_path).expanduser().resolve(),
        training_models_root=Path(args.training_models_root).expanduser().resolve() if args.training_models_root else None,
        training_root=Path(args.training_root).expanduser().resolve() if args.training_root else None,
        model_mgr_path=Path(args.model_mgr).expanduser().resolve() if args.model_mgr else None,
        quantizations=args.quantize or None,
        include_mlx=args.include_mlx,
        backup=args.backup,
    )
    print(format_registry_plan(plan))
    if args.run:
        run_zelda_registry_hooks(plan)
    return 0


def _register_subcommands(oracle_sub) -> None:
    build_bundle = oracle_sub.add_parser("build-bundle", help="Build a Zelda/oracle training bundle.")
    build_bundle.add_argument("--track", required=True)
    build_bundle.add_argument("--output", required=True)
    build_bundle.add_argument("--repo-root")
    build_bundle.add_argument("--training-root")
    build_bundle.add_argument("--datasets-root")
    build_bundle.set_defaults(func=build_bundle_command)

    validate_bundle = oracle_sub.add_parser("validate-bundle", help="Validate bundle inputs for a track.")
    validate_bundle.add_argument("--track", required=True)
    validate_bundle.add_argument("--repo-root")
    validate_bundle.add_argument("--training-root")
    validate_bundle.add_argument("--datasets-root")
    validate_bundle.set_defaults(func=validate_bundle_command)

    render_runs = oracle_sub.add_parser("render-runs", help="Render an active-runs note using Zelda track specs.")
    render_runs.add_argument("--config", required=True)
    render_runs.add_argument("--output")
    render_runs.add_argument("--no-probe-remote", action="store_true")
    render_runs.set_defaults(func=render_runs_command)

    finalize_run = oracle_sub.add_parser("finalize-run", help="Wait for a remote run and download its artifacts.")
    finalize_run.add_argument("--track", required=True)
    finalize_run.add_argument("--host")
    finalize_run.add_argument("--port", type=int)
    finalize_run.add_argument("--remote-dir")
    finalize_run.add_argument("--instance-id")
    finalize_run.add_argument("--instance-name")
    finalize_run.add_argument("--metadata")
    finalize_run.add_argument("--instances-dir")
    finalize_run.add_argument("--local-run-dir")
    finalize_run.add_argument("--poll-seconds", type=int, default=120)
    finalize_run.add_argument("--wait-for-start", action="store_true")
    finalize_run.add_argument("--run-eval-hooks", action="store_true")
    finalize_run.add_argument("--eval-pack")
    finalize_run.add_argument("--run-registry-hooks", action="store_true")
    finalize_run.add_argument("--training-root")
    finalize_run.add_argument("--training-models-root")
    finalize_run.add_argument("--model-mgr")
    finalize_run.add_argument("--registry-quantize", action="append")
    finalize_run.add_argument("--include-mlx", action="store_true")
    finalize_run.add_argument("--backup", action="store_true")
    finalize_run.set_defaults(func=finalize_run_command)

    eval_hooks = oracle_sub.add_parser("eval-hooks", help="Print or run Zelda eval hooks for a finished run.")
    eval_hooks.add_argument("--track", required=True)
    eval_hooks.add_argument("--run-dir", required=True)
    eval_hooks.add_argument("--host")
    eval_hooks.add_argument("--port", type=int)
    eval_hooks.add_argument("--remote-dir")
    eval_hooks.add_argument("--adapter-path")
    eval_hooks.add_argument("--training-root")
    eval_hooks.add_argument("--eval-pack")
    eval_hooks.add_argument("--run", action="store_true")
    eval_hooks.set_defaults(func=eval_hooks_command)

    registry_hooks = oracle_sub.add_parser("registry-hooks", help="Print or run registry/model-mgr hooks.")
    registry_hooks.add_argument("--track", required=True)
    registry_hooks.add_argument("--artifact-path", required=True)
    registry_hooks.add_argument("--training-models-root")
    registry_hooks.add_argument("--training-root")
    registry_hooks.add_argument("--model-mgr")
    registry_hooks.add_argument("--quantize", action="append")
    registry_hooks.add_argument("--include-mlx", action="store_true")
    registry_hooks.add_argument("--backup", action="store_true")
    registry_hooks.add_argument("--run", action="store_true")
    registry_hooks.set_defaults(func=registry_hooks_command)


def register_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("oracle-training", help="Zelda/oracle training operations.")
    oracle_sub = parser.add_subparsers(dest="oracle_training_command")
    _register_subcommands(oracle_sub)

    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="afs_scawful.oracle_training")
    subparsers = parser.add_subparsers(dest="oracle_training_command")
    _register_subcommands(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "oracle_training_command", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
