"""Eval hook plans for Zelda/oracle training tracks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..model_ops.active_runs import normalize_remote_dir
from ..model_ops.finalize import RemoteRunTarget
from ..paths import resolve_training_root
from .zelda_tracks import get_zelda_track_spec


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture output."""

    return subprocess.run(command, check=check, text=True, capture_output=True)


def _default_eval_dir(local_run_dir: Path) -> Path:
    return local_run_dir.expanduser().resolve() / "eval"


def _default_switchhook_remote_adapter_dir(track_spec: dict[str, Any], remote_target: RemoteRunTarget) -> str:
    artifact_rel = track_spec["phases"]["train"]["artifact_path"]
    return f"{normalize_remote_dir(remote_target.remote_dir)}/{artifact_rel}"


def _resolve_eval_pack_path(
    *,
    training_root: Path,
    default_pack: str,
    override_path: Path | None,
) -> Path:
    if override_path is not None:
        return override_path.expanduser().resolve()

    eval_pack = training_root / "evals" / default_pack
    if eval_pack.suffix:
        return eval_pack.expanduser().resolve()
    return eval_pack.with_suffix(".jsonl").expanduser().resolve()


def _build_local_golden_eval_plan(
    track_name: str,
    *,
    spec: dict[str, Any],
    local_run_dir: Path,
    adapter_path: Path | None,
    training_root: Path | None,
    eval_pack_path: Path | None,
) -> list[dict[str, Any]]:
    resolved_training_root = (training_root or resolve_training_root()).expanduser().resolve()
    resolved_adapter = (adapter_path or (local_run_dir / "adapter_final")).expanduser().resolve()
    resolved_eval_pack = _resolve_eval_pack_path(
        training_root=resolved_training_root,
        default_pack=str(spec.get("metadata", {}).get("eval_pack", "iquest_zelda_golden_v1")),
        override_path=eval_pack_path,
    )
    eval_dir = _default_eval_dir(local_run_dir)
    output_name = f"{track_name}_eval.jsonl"
    hook_name = {
        "iquest_40b_v3": "iquest_zelda_golden_eval",
        "zelda_16b_v1": "zelda_16b_golden_eval",
    }.get(track_name, f"{track_name}_golden_eval")
    eval_output = eval_dir / output_name
    command = [
        "python3",
        str(resolved_training_root / "scripts" / "eval_iquest_zelda.py"),
        "--model",
        spec["model_name"],
        "--adapter",
        str(resolved_adapter),
        "--prompt-pack",
        str(resolved_eval_pack),
        "--out",
        str(eval_output),
        "--temperature",
        "0.0",
        "--top-p",
        "1.0",
    ]
    return [
        {
            "name": hook_name,
            "description": "Local CUDA eval against the golden Zelda prompt pack.",
            "command": command,
            "outputs": [str(eval_output)],
        }
    ]


def build_zelda_eval_plan(
    track_name: str,
    *,
    local_run_dir: Path,
    remote_target: RemoteRunTarget | None = None,
    adapter_path: Path | None = None,
    training_root: Path | None = None,
    eval_pack_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Build the post-run eval hook plan for a Zelda/oracle track."""

    spec = get_zelda_track_spec(track_name)
    resolved_training_root = (training_root or resolve_training_root()).expanduser().resolve()
    eval_dir = _default_eval_dir(local_run_dir)

    if track_name == "switchhook_27b_v1":
        if remote_target is None:
            raise ValueError("switchhook_27b_v1 eval hooks require a remote target")
        eval_copy = eval_dir / "switchhook_live_smoke.jsonl"
        summary_copy = eval_dir / "switchhook_live_smoke.summary.json"
        details_copy = eval_dir / "switchhook_live_smoke.scored.jsonl"
        command = [
            "bash",
            str(resolved_training_root / "scripts" / "run_switchhook_live_eval_vast.sh"),
            "--vast-host",
            remote_target.host,
            "--vast-port",
            str(remote_target.port),
            "--base-model",
            spec["model_name"],
            "--adapter-dir",
            _default_switchhook_remote_adapter_dir(spec, remote_target),
            "--local-eval-copy",
            str(eval_copy),
            "--local-summary-copy",
            str(summary_copy),
            "--local-details-copy",
            str(details_copy),
        ]
        return [
            {
                "name": "switchhook_live_smoke",
                "description": "Remote live smoke eval for Switchhook on the Vast box.",
                "command": command,
                "outputs": [str(eval_copy), str(summary_copy), str(details_copy)],
            }
        ]

    if track_name == "iquest_40b_v3":
        return _build_local_golden_eval_plan(
            track_name,
            spec=spec,
            local_run_dir=local_run_dir,
            adapter_path=adapter_path,
            training_root=training_root,
            eval_pack_path=eval_pack_path,
        )

    if track_name == "zelda_16b_v1":
        return _build_local_golden_eval_plan(
            track_name,
            spec=spec,
            local_run_dir=local_run_dir,
            adapter_path=adapter_path,
            training_root=training_root,
            eval_pack_path=eval_pack_path,
        )

    if spec.get("metadata", {}).get("thinking_tier") == "high" and spec.get("metadata", {}).get("eval_pack"):
        return _build_local_golden_eval_plan(
            track_name,
            spec=spec,
            local_run_dir=local_run_dir,
            adapter_path=adapter_path,
            training_root=training_root,
            eval_pack_path=eval_pack_path,
        )

    return [
        {
            "name": "manual_eval_setup",
            "manual": True,
            "description": "No automated eval hook is configured yet for this track.",
            "notes": spec.get("metadata", {}).get("notes", []),
        }
    ]


def run_zelda_eval_hooks(
    plan: list[dict[str, Any]],
    *,
    runner=run,
) -> list[dict[str, Any]]:
    """Execute a Zelda eval hook plan."""

    results: list[dict[str, Any]] = []
    for hook in plan:
        if hook.get("manual"):
            results.append({"name": hook["name"], "skipped": True, "reason": "manual"})
            continue
        command = list(hook["command"])
        result = runner(command, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"eval hook failed: {hook['name']}")
        results.append(
            {
                "name": hook["name"],
                "command": command,
                "outputs": list(hook.get("outputs", [])),
            }
        )
    return results


def format_eval_plan(plan: list[dict[str, Any]]) -> str:
    """Render an eval plan as formatted JSON."""

    return json.dumps(plan, indent=2)
