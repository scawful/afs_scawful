from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from typing import Any


DEFAULT_WSL_DISTRO = os.environ.get("AFS_WSL_DISTRO", "Ubuntu")
DEFAULT_WSL_TIMEOUT_S = 60.0

STATUS_PY = textwrap.dedent(
    """
    import json
    import pathlib
    import shutil
    import subprocess

    def cmd_output(argv):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=20)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if result.returncode != 0:
            return {"ok": False, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        return {"ok": True, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}

    home = pathlib.Path.home()
    payload = {
        "home": str(home),
        "src_link": str(home / "src"),
        "src_link_exists": (home / "src").exists(),
        "env_file": str(home / ".config/afs/wsl-training.env.sh"),
        "env_file_exists": (home / ".config/afs/wsl-training.env.sh").exists(),
        "src_root_exists": pathlib.Path("/mnt/d/src").exists(),
        "training_root_exists": pathlib.Path("/mnt/d/src/training").exists(),
        "python3": shutil.which("python3") or "",
        "nvidia_smi": cmd_output(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]),
    }
    print(json.dumps(payload))
    """
).strip()

ENVS_PY = textwrap.dedent(
    """
    import json
    import pathlib

    home = pathlib.Path.home()
    venv_root = home / ".venvs"
    entries = []
    for name in ("src-training", "text-serve", "diffusers"):
        venv_dir = venv_root / name
        entries.append(
            {
                "name": name,
                "path": str(venv_dir),
                "exists": venv_dir.exists(),
                "python": str(venv_dir / "bin/python"),
                "python_exists": (venv_dir / "bin/python").exists(),
            }
        )
    print(json.dumps({"venvs": entries}))
    """
).strip()


def _wsl_exec_argv(argv: list[str], *, distro: str) -> list[str]:
    return ["wsl.exe", "-d", distro, "--", *argv]


def _argv_display(argv: list[str]) -> str:
    return " ".join(json.dumps(item) if any(ch.isspace() for ch in item) else item for item in argv)


def run_wsl_bash(
    command: str,
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    timeout: float = DEFAULT_WSL_TIMEOUT_S,
) -> str:
    return run_wsl_command(["bash", "-lc", command], distro=distro, timeout=timeout)


def _run_wsl_bash_via_redirect(
    command: str,
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    timeout: float = DEFAULT_WSL_TIMEOUT_S,
) -> str:
    return _run_wsl_command_via_redirect(["bash", "-lc", command], distro=distro, timeout=timeout)


def run_wsl_command(
    argv: list[str],
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    timeout: float = DEFAULT_WSL_TIMEOUT_S,
) -> str:
    display = _argv_display(argv)
    try:
        result = subprocess.run(
            _wsl_exec_argv(argv, distro=distro),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            return _run_wsl_command_via_redirect(argv, distro=distro, timeout=timeout)
        raise RuntimeError(f"WSL command timed out after {timeout:.0f}s: {display}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "WSL command failed"
        if os.name == "nt" and "Wsl/Service/0x800703e3" in detail:
            return _run_wsl_command_via_redirect(argv, distro=distro, timeout=timeout)
        raise RuntimeError(detail)
    return result.stdout.strip()


def _run_wsl_command_via_redirect(
    argv: list[str],
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    timeout: float = DEFAULT_WSL_TIMEOUT_S,
) -> str:
    display = _argv_display(argv)
    with tempfile.TemporaryDirectory(prefix="afs-hostd-wsl-") as temp_dir:
        out_path = os.path.join(temp_dir, "stdout.txt")
        err_path = os.path.join(temp_dir, "stderr.txt")
        with open(out_path, "w", encoding="utf-8", errors="replace") as stdout_handle, open(
            err_path, "w", encoding="utf-8", errors="replace"
        ) as stderr_handle:
            try:
                result = subprocess.run(
                    _wsl_exec_argv(argv, distro=distro),
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"WSL command timed out after {timeout:.0f}s: {display}") from exc
        stdout = _read_text_if_exists(out_path)
        stderr = _read_text_if_exists(err_path)
        if result.returncode != 0:
            detail = stderr.strip() or stdout.strip() or "WSL command failed"
            raise RuntimeError(detail)
        return stdout.strip()


def _read_text_if_exists(path: str) -> str:
    if not os.path.exists(path):
        return ""
    for encoding in ("utf-8", "utf-16le", "cp1252"):
        try:
            with open(path, "r", encoding=encoding, errors="strict") as handle:
                return handle.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def run_wsl_json(
    command: str,
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    timeout: float = DEFAULT_WSL_TIMEOUT_S,
) -> dict[str, Any]:
    output = run_wsl_bash(command, distro=distro, timeout=timeout)
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"WSL command returned non-JSON output:\n{output}") from exc


def run_wsl_json_command(
    argv: list[str],
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    timeout: float = DEFAULT_WSL_TIMEOUT_S,
) -> dict[str, Any]:
    output = run_wsl_command(argv, distro=distro, timeout=timeout)
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"WSL command returned non-JSON output:\n{output}") from exc


def wsl_list_verbose(*, timeout: float = DEFAULT_WSL_TIMEOUT_S) -> str:
    try:
        result = subprocess.run(
            ["wsl.exe", "-l", "-v"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("wsl -l -v timed out") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "wsl -l -v failed"
        raise RuntimeError(detail)
    return result.stdout.replace("\x00", "").strip()


def status(*, distro: str = DEFAULT_WSL_DISTRO) -> dict[str, Any]:
    payload = run_wsl_json_command(
        ["python3", "-c", STATUS_PY],
        distro=distro,
        timeout=max(DEFAULT_WSL_TIMEOUT_S, 45.0),
    )
    payload["distro"] = distro
    payload["wsl_list"] = wsl_list_verbose()
    return payload


def envs(*, distro: str = DEFAULT_WSL_DISTRO) -> dict[str, Any]:
    payload = run_wsl_json_command(
        ["python3", "-c", ENVS_PY],
        distro=distro,
        timeout=max(DEFAULT_WSL_TIMEOUT_S, 30.0),
    )
    payload["distro"] = distro
    return payload


def vllm_action(
    action: str,
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    model: str | None = None,
    host: str | None = None,
    port: int | None = None,
    served_name: str | None = None,
    max_model_len: int | None = None,
) -> dict[str, Any]:
    args = ["bash", "/mnt/d/src/training/scripts/wsl_vllm_service.sh", action, "--json"]
    if model:
        args.extend(["--model", model])
    if host:
        args.extend(["--host", host])
    if port:
        args.extend(["--port", str(port)])
    if served_name:
        args.extend(["--served-name", served_name])
    if max_model_len:
        args.extend(["--max-model-len", str(max_model_len)])
    payload = run_wsl_json_command(args, distro=distro, timeout=max(DEFAULT_WSL_TIMEOUT_S, 60.0))
    payload["distro"] = distro
    return payload


def eval_action(
    action: str,
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    name: str,
    model: str,
    adapter: str,
    prompt_pack: str,
    out: str,
    script: str | None = None,
    python_bin: str | None = None,
    max_new_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    seed: int | None = None,
    limit: int | None = None,
    attn: str | None = None,
    use_quant: bool | None = None,
) -> dict[str, Any]:
    args = [
        "bash",
        "/mnt/d/src/training/scripts/wsl_eval_service.sh",
        action,
        "--name",
        name,
        "--model",
        model,
        "--adapter",
        adapter,
        "--prompt-pack",
        prompt_pack,
        "--out",
        out,
        "--json",
    ]
    if script:
        args.extend(["--script", script])
    if python_bin:
        args.extend(["--python", python_bin])
    if max_new_tokens is not None:
        args.extend(["--max-new-tokens", str(max_new_tokens)])
    if temperature is not None:
        args.extend(["--temperature", str(temperature)])
    if top_p is not None:
        args.extend(["--top-p", str(top_p)])
    if seed is not None:
        args.extend(["--seed", str(seed)])
    if limit is not None:
        args.extend(["--limit", str(limit)])
    if attn:
        args.extend(["--attn", attn])
    if use_quant is False:
        args.append("--no-quant")
    payload = run_wsl_json_command(args, distro=distro, timeout=max(DEFAULT_WSL_TIMEOUT_S, 60.0))
    payload["distro"] = distro
    return payload


def training_action(
    action: str,
    *,
    distro: str = DEFAULT_WSL_DISTRO,
    task: str,
    config: str,
    train_root: str | None = None,
    venv_dir: str | None = None,
    tail: int | None = None,
) -> dict[str, Any]:
    args = ["bash", "/mnt/d/src/training/scripts/wsl_training_service.sh", action, "--task", task, "--config", config, "--json"]
    if train_root:
        args.extend(["--train-root", train_root])
    normalized_venv = _normalize_venv_dir(venv_dir)
    if normalized_venv:
        args.extend(["--venv", normalized_venv])
    if tail:
        args.extend(["--tail", str(tail)])
    payload = run_wsl_json_command(args, distro=distro, timeout=max(DEFAULT_WSL_TIMEOUT_S, 60.0))
    payload["distro"] = distro
    return payload


def _normalize_venv_dir(venv_dir: str | None) -> str | None:
    if not venv_dir:
        return None
    candidate = venv_dir.strip()
    if not candidate:
        return None
    if candidate == "~" or candidate.startswith("~/"):
        return None
    return candidate
