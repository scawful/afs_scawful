from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_LMSTUDIO_ENDPOINT = "http://127.0.0.1:1234/v1"
DEFAULT_LMSTUDIO_TIMEOUT_S = 30.0
_LOCAL_MODEL_EXTENSIONS = (".gguf", ".bin", ".safetensors", ".ggml")
_LOCAL_QUANT_SUFFIX_RE = re.compile(
    r"(?:[-_](?:q\d[a-z0-9_]*|iq\d[a-z0-9_]*|bf16|fp16|fp32|f16|f32|mlx))+$",
    re.IGNORECASE,
)


def _coerce_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def resolve_lms_path(lms_path: str | None = None) -> str:
    override = _coerce_str(lms_path).strip()
    if override:
        if os.path.exists(override):
            return override
        raise RuntimeError(f"Configured LM Studio CLI path not found: {override}")

    from_path = shutil.which("lms")
    if from_path:
        return from_path

    user_profile = os.environ.get("USERPROFILE", "")
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    candidates = [
        os.path.join(user_profile, ".lmstudio", "bin", "lms.exe"),
        os.path.join(local_appdata, "LM Studio", "bin", "lms.exe"),
        os.path.join(local_appdata, "Programs", "LM Studio", "bin", "lms.exe"),
        os.path.join(local_appdata, "Programs", "LM Studio", "resources", "app", ".webpack", "main", "bin", "lms.exe"),
        os.path.join(program_files, "LM Studio", "lms.exe") if program_files else "",
        os.path.join(program_files_x86, "LM Studio", "lms.exe") if program_files_x86 else "",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise RuntimeError(
        "LM Studio CLI not found. Checked PATH and common locations such as %USERPROFILE%\\.lmstudio\\bin\\lms.exe."
    )


def run_lms(
    args: Sequence[str],
    *,
    lms_path: str | None = None,
    timeout: float = DEFAULT_LMSTUDIO_TIMEOUT_S,
) -> str:
    command = [resolve_lms_path(lms_path), *[str(arg) for arg in args]]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"lms command timed out after {timeout:.0f}s: {' '.join(args)}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "lms command failed"
        raise RuntimeError(detail)
    return result.stdout


def _json_from_output(output: str) -> Any:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") or line.startswith("["):
            return json.loads(line)
    raise ValueError("No JSON payload found in lms output")


def _normalized_lookup_keys(value: str) -> set[str]:
    raw = str(value or "").strip()
    if not raw:
        return set()
    slash_normalized = raw.replace("\\", "/").strip("/")
    candidates = {raw.lower(), slash_normalized.lower()}
    basename = slash_normalized.rsplit("/", 1)[-1]
    if basename:
        candidates.add(basename.lower())
        stem = basename
        lowered_stem = stem.lower()
        for extension in _LOCAL_MODEL_EXTENSIONS:
            if lowered_stem.endswith(extension):
                stem = stem[: -len(extension)]
                lowered_stem = stem.lower()
                candidates.add(lowered_stem)
                break
        trimmed = _LOCAL_QUANT_SUFFIX_RE.sub("", stem)
        if trimmed:
            candidates.add(trimmed.lower())
    return {candidate for candidate in candidates if candidate}


def loaded_model_lookup_keys(entry: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in (
        "identifier",
        "modelKey",
        "indexedModelIdentifier",
        "path",
        "displayName",
        "name",
        "model",
        "id",
    ):
        value = entry.get(key)
        if isinstance(value, str) and value and value not in keys:
            keys.append(value)
    return keys


def candidate_model_ids(requested_model_id: str) -> list[str]:
    base = requested_model_id.strip()
    if not base:
        return []
    candidates: list[str] = []

    def add(value: str) -> None:
        if value and value not in candidates:
            candidates.append(value)

    add(base)
    stripped = base[:-4] if base.endswith("-mlx") else base
    add(stripped)
    for value in (base, stripped):
        short = value.rsplit("/", 1)[-1]
        short = short[:-5] if short.endswith(".gguf") else short
        add(short)
        if short and not short.startswith("gguf/"):
            add(f"gguf/lmstudio/{short}.gguf")
            add(f"gguf/ollama/{short}.gguf")
    return candidates


def resolve_available_model_id(requested_model_id: str, available_models: Sequence[Mapping[str, Any]]) -> str:
    requested = requested_model_id.strip()
    if not requested:
        return ""
    available_ids = [key for entry in available_models for key in loaded_model_lookup_keys(entry)]
    if requested in available_ids:
        return requested
    for candidate in candidate_model_ids(requested):
        if candidate in available_ids:
            return candidate
    wanted_keys = set()
    for candidate in candidate_model_ids(requested):
        wanted_keys.update(_normalized_lookup_keys(candidate))
    for entry in available_models:
        for key in loaded_model_lookup_keys(entry):
            if wanted_keys & _normalized_lookup_keys(key):
                for preferred_key in ("modelKey", "id", "path", "indexedModelIdentifier", "displayName", "name"):
                    value = entry.get(preferred_key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                return key
    return requested


def resolve_unload_target(target: str, loaded: Sequence[Mapping[str, Any]]) -> str | None:
    wanted = target.strip()
    if not wanted:
        return None
    lower_wanted = wanted.lower()
    for entry in loaded:
        for key in loaded_model_lookup_keys(entry):
            if key.lower() == lower_wanted:
                identifier = _coerce_str(entry.get("identifier"))
                if identifier:
                    return identifier
                model_key = _coerce_str(entry.get("modelKey")) or _coerce_str(entry.get("id"))
                return model_key or key
    return None


def server_status(*, lms_path: str | None = None) -> dict[str, Any]:
    payload = _json_from_output(run_lms(["server", "status", "--json"], lms_path=lms_path))
    return payload if isinstance(payload, dict) else {}


def available_models(*, lms_path: str | None = None) -> list[dict[str, Any]]:
    payload = _json_from_output(run_lms(["ls", "--json"], lms_path=lms_path))
    return payload if isinstance(payload, list) else []


def loaded_models(*, lms_path: str | None = None) -> list[dict[str, Any]]:
    payload = _json_from_output(run_lms(["ps", "--json"], lms_path=lms_path))
    return payload if isinstance(payload, list) else []


def load_model(
    *,
    model_id: str,
    identifier: str | None = None,
    context_length: int | None = None,
    parallel: int | None = None,
    gpu: str | None = None,
    ttl: int | None = None,
    estimate_only: bool = False,
    exclusive: bool = False,
    lms_path: str | None = None,
) -> dict[str, Any]:
    available = available_models(lms_path=lms_path)
    resolved_model_id = resolve_available_model_id(model_id, available)
    resolved_identifier = identifier or resolved_model_id
    command_results: list[dict[str, Any]] = []
    current_loaded = loaded_models(lms_path=lms_path)

    if exclusive:
        for entry in current_loaded:
            loaded_identifier = _coerce_str(entry.get("identifier")) or _coerce_str(entry.get("modelKey"))
            if loaded_identifier and loaded_identifier != resolved_identifier:
                output = run_lms(["unload", loaded_identifier], lms_path=lms_path, timeout=max(DEFAULT_LMSTUDIO_TIMEOUT_S * 2, 60.0))
                command_results.append({"command": f"lms unload {loaded_identifier}", "output": output})

    if resolved_identifier and any((_coerce_str(entry.get("identifier")) == resolved_identifier) for entry in current_loaded):
        output = run_lms(["unload", resolved_identifier], lms_path=lms_path, timeout=max(DEFAULT_LMSTUDIO_TIMEOUT_S * 2, 60.0))
        command_results.append({"command": f"lms unload {resolved_identifier}", "output": output})

    args = ["load", resolved_model_id, "--yes", "--identifier", resolved_identifier]
    if context_length and context_length > 0:
        args.extend(["--context-length", str(context_length)])
    if parallel and parallel > 0:
        args.extend(["--parallel", str(parallel)])
    if gpu:
        args.extend(["--gpu", str(gpu)])
    if ttl:
        args.extend(["--ttl", str(ttl)])
    if estimate_only:
        args.append("--estimate-only")
    output = run_lms(args, lms_path=lms_path, timeout=max(DEFAULT_LMSTUDIO_TIMEOUT_S * 10, 300.0))
    command_results.append({"command": " ".join(args), "output": output})

    return {
        "requested_model_id": model_id,
        "resolved_model_id": resolved_model_id,
        "identifier": resolved_identifier,
        "estimate_only": estimate_only,
        "exclusive": exclusive,
        "command_results": command_results,
        "loaded": loaded_models(lms_path=lms_path),
        "available": available_models(lms_path=lms_path),
    }


def unload_model(
    *,
    target: str = "",
    all_models: bool = False,
    lms_path: str | None = None,
) -> dict[str, Any]:
    loaded = loaded_models(lms_path=lms_path)
    if all_models:
        unloaded = [
            _coerce_str(entry.get("identifier")) or _coerce_str(entry.get("modelKey"))
            for entry in loaded
        ]
        if loaded:
            output = run_lms(["unload", "--all"], lms_path=lms_path, timeout=max(DEFAULT_LMSTUDIO_TIMEOUT_S * 2, 60.0))
            return {"all": True, "unloaded": unloaded, "output": output}
        return {"all": True, "unloaded": unloaded, "output": ""}
    resolved = resolve_unload_target(target, loaded)
    if not resolved:
        raise RuntimeError(f"Model '{target}' is not currently loaded in LM Studio.")
    output = run_lms(["unload", resolved], lms_path=lms_path, timeout=max(DEFAULT_LMSTUDIO_TIMEOUT_S * 2, 60.0))
    return {"all": False, "unloaded": [resolved], "output": output}
