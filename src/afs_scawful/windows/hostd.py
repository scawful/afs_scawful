from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import lmstudio
from . import power
from . import training_status as training_runtime
from . import wsl


SUPPORTED_MODES = {"interactive", "serve", "train"}
SERVICE_NAME = "afs-hostd"
DEPLOYMENT_PHASE = "0"
HOSTD_API_VERSION = "0.1.1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _package_version() -> str:
    try:
        return metadata.version("afs_scawful")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def _file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _source_file_payload(path: Path) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": str(path),
        "sha256": _file_sha256(path),
    }
    try:
        stat = path.stat()
    except OSError as exc:
        payload["error"] = str(exc)
        return payload
    payload["size_bytes"] = stat.st_size
    payload["mtime"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
    return payload


def _run_git(args: list[str], *, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _git_payload(path: Path) -> dict[str, object]:
    root = _run_git(["rev-parse", "--show-toplevel"], cwd=path.parent)
    if not root:
        return {
            "available": False,
            "reason": "not_a_git_checkout",
        }
    root_path = Path(root)
    commit = _run_git(["rev-parse", "HEAD"], cwd=root_path)
    short = _run_git(["rev-parse", "--short", "HEAD"], cwd=root_path)
    dirty = _run_git(["status", "--short"], cwd=root_path)
    return {
        "available": True,
        "root": str(root_path),
        "commit": commit,
        "short": short,
        "dirty": bool(dirty),
    }


def _version_payload() -> dict[str, object]:
    module_path = Path(__file__).resolve()
    return {
        "service": SERVICE_NAME,
        "phase": DEPLOYMENT_PHASE,
        "hostd_api_version": HOSTD_API_VERSION,
        "package_version": _package_version(),
        "host": platform.node(),
        "platform": platform.platform(),
        "module": _source_file_payload(module_path),
        "git": _git_payload(module_path),
        "deployment": {
            "revision": os.environ.get("AFS_HOSTD_REVISION"),
            "source_sha256": os.environ.get("AFS_HOSTD_SOURCE_SHA256"),
        },
        "ts": _utc_now(),
    }


def _load_fastapi():
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "fastapi is not installed. Install afs_scawful[gateway] or add fastapi+uvicorn to the host env."
        ) from exc
    return FastAPI, Depends, Header, HTTPException


def _is_running_state(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return str(payload.get("state") or "").lower() == "running"


def _mode_defaults(mode: str) -> dict[str, bool]:
    if mode == "train":
        return {
            "stop_vllm": True,
            "unload_lmstudio": True,
            "stop_training": False,
        }
    if mode == "serve":
        return {
            "stop_vllm": False,
            "unload_lmstudio": False,
            "stop_training": False,
        }
    return {
        "stop_vllm": True,
        "unload_lmstudio": True,
        "stop_training": False,
    }


def _lmstudio_mode_snapshot(*, lms_path: str | None = None) -> dict[str, Any]:
    loaded = lmstudio.loaded_models(lms_path=lms_path)
    server = lmstudio.server_status(lms_path=lms_path)
    return {
        "lms_path": lmstudio.resolve_lms_path(lms_path),
        "server": server,
        "loaded": loaded,
        "loaded_count": len(loaded),
        "loaded_model_ids": [
            (entry.get("identifier") or entry.get("modelKey") or entry.get("id"))
            for entry in loaded
            if isinstance(entry, dict)
        ],
    }


def _training_mode_snapshot(
    *,
    task: str | None,
    config: str | None,
    distro: str,
    train_root: str | None,
    venv_dir: str | None,
    tail: int | None,
) -> dict[str, Any]:
    task_value = str(task or "").strip()
    config_value = str(config or "").strip()
    if not task_value or not config_value:
        return {
            "checked": False,
            "reason": "task_and_config_required",
            "state": "unknown",
        }
    payload = training_runtime.status_snapshot(
        task=task_value,
        config=config_value,
        train_root=train_root,
        tail=tail,
    )
    payload["checked"] = True
    return payload


def _mode_hint(snapshot: dict[str, Any]) -> dict[str, str]:
    training_payload = snapshot.get("training") if isinstance(snapshot.get("training"), dict) else {}
    vllm_payload = snapshot.get("vllm") if isinstance(snapshot.get("vllm"), dict) else {}
    lmstudio_payload = snapshot.get("lmstudio") if isinstance(snapshot.get("lmstudio"), dict) else {}
    power_payload = snapshot.get("power") if isinstance(snapshot.get("power"), dict) else {}
    if _is_running_state(training_payload):
        return {"mode": "train", "reason": "training_running"}
    if _is_running_state(vllm_payload):
        return {"mode": "serve", "reason": "vllm_running"}
    if int(lmstudio_payload.get("loaded_count") or 0) > 0:
        return {"mode": "serve", "reason": "lmstudio_loaded"}
    if bool(power_payload.get("sleep_suppressed_on_ac")):
        return {"mode": "train", "reason": "power_locked_for_training"}
    return {"mode": "interactive", "reason": "no_gpu_runtime_active"}


def _mode_snapshot(
    *,
    task: str | None,
    config: str | None,
    distro: str,
    train_root: str | None,
    venv_dir: str | None,
    tail: int | None,
    lms_path: str | None,
    served_name: str | None,
    model: str | None,
    port: int | None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []

    try:
        power_payload: dict[str, Any] = power.current_policy()
    except Exception as exc:
        power_payload = {"error": str(exc)}
        warnings.append({"surface": "power", "error": str(exc)})

    try:
        lmstudio_payload = _lmstudio_mode_snapshot(lms_path=lms_path)
    except Exception as exc:
        lmstudio_payload = {"error": str(exc), "loaded_count": 0, "loaded": []}
        warnings.append({"surface": "lmstudio", "error": str(exc)})

    try:
        vllm_payload = wsl.vllm_action(
            "status",
            distro=distro,
            served_name=served_name,
            model=model,
            port=port,
        )
    except Exception as exc:
        vllm_payload = {"error": str(exc), "state": "unknown"}
        warnings.append({"surface": "vllm", "error": str(exc)})

    try:
        training_payload = _training_mode_snapshot(
            task=task,
            config=config,
            distro=distro,
            train_root=train_root,
            venv_dir=venv_dir,
            tail=tail,
        )
    except Exception as exc:
        training_payload = {"error": str(exc), "checked": False, "state": "unknown"}
        warnings.append({"surface": "training", "error": str(exc)})

    snapshot = {
        "power": power_payload,
        "lmstudio": lmstudio_payload,
        "vllm": vllm_payload,
        "training": training_payload,
        "warnings": warnings,
    }
    snapshot["mode_hint"] = _mode_hint(snapshot)
    return snapshot


def _apply_mode(
    *,
    mode: str,
    task: str | None,
    config: str | None,
    distro: str,
    train_root: str | None,
    venv_dir: str | None,
    tail: int | None,
    lms_path: str | None,
    served_name: str | None,
    model: str | None,
    port: int | None,
    stop_vllm: bool | None,
    unload_lmstudio: bool | None,
    stop_training: bool | None,
) -> dict[str, Any]:
    requested_mode = str(mode or "").strip().lower()
    if requested_mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode: {mode}")

    defaults = _mode_defaults(requested_mode)
    effective = {
        "stop_vllm": defaults["stop_vllm"] if stop_vllm is None else bool(stop_vllm),
        "unload_lmstudio": defaults["unload_lmstudio"] if unload_lmstudio is None else bool(unload_lmstudio),
        "stop_training": defaults["stop_training"] if stop_training is None else bool(stop_training),
    }

    before = _mode_snapshot(
        task=task,
        config=config,
        distro=distro,
        train_root=train_root,
        venv_dir=venv_dir,
        tail=tail,
        lms_path=lms_path,
        served_name=served_name,
        model=model,
        port=port,
    )
    actions: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    try:
        if requested_mode in {"train", "serve"}:
            actions.append({"surface": "power", "result": power.suppress_sleep_for_training()})
        else:
            actions.append({"surface": "power", "result": power.restore_sleep_policy()})
    except Exception as exc:
        warnings.append({"surface": "power", "error": str(exc)})

    if effective["stop_training"]:
        task_value = str(task or "").strip()
        config_value = str(config or "").strip()
        if not task_value or not config_value:
            warnings.append({"surface": "training", "error": "task and config are required to stop training"})
        elif _is_running_state(before.get("training") if isinstance(before.get("training"), dict) else {}):
            try:
                actions.append(
                    {
                        "surface": "training",
                        "result": wsl.training_action(
                            "stop",
                            distro=distro,
                            task=task_value,
                            config=config_value,
                            train_root=train_root,
                            venv_dir=venv_dir,
                            tail=tail,
                        ),
                    }
                )
            except Exception as exc:
                warnings.append({"surface": "training", "error": str(exc)})

    if effective["stop_vllm"]:
        if _is_running_state(before.get("vllm") if isinstance(before.get("vllm"), dict) else {}):
            try:
                actions.append(
                    {
                        "surface": "vllm",
                        "result": wsl.vllm_action(
                            "stop",
                            distro=distro,
                            served_name=served_name,
                            model=model,
                            port=port,
                        ),
                    }
                )
            except Exception as exc:
                warnings.append({"surface": "vllm", "error": str(exc)})

    if effective["unload_lmstudio"]:
        loaded_count = int((before.get("lmstudio") or {}).get("loaded_count") or 0)
        if loaded_count > 0:
            try:
                actions.append(
                    {
                        "surface": "lmstudio",
                        "result": lmstudio.unload_model(all_models=True, lms_path=lms_path),
                    }
                )
            except Exception as exc:
                warnings.append({"surface": "lmstudio", "error": str(exc)})

    after = _mode_snapshot(
        task=task,
        config=config,
        distro=distro,
        train_root=train_root,
        venv_dir=venv_dir,
        tail=tail,
        lms_path=lms_path,
        served_name=served_name,
        model=model,
        port=port,
    )

    return {
        "requested_mode": requested_mode,
        "effective_actions": effective,
        "before": before,
        "actions": actions,
        "warnings": warnings,
        "after": after,
    }


def create_app(*, token: str | None = None):
    FastAPI, Depends, Header, HTTPException = _load_fastapi()

    def require_auth(authorization: str | None = Header(default=None)) -> None:
        if not token:
            return
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="unauthorized")

    app = FastAPI(
        title=SERVICE_NAME,
        version=HOSTD_API_VERSION,
        summary="Phase-0 Windows host control plane for medical-mechanica",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "phase": DEPLOYMENT_PHASE,
            "hostd_api_version": HOSTD_API_VERSION,
            "ts": _utc_now(),
        }

    @app.get("/v1/version", dependencies=[Depends(require_auth)])
    def version() -> dict[str, object]:
        return _version_payload()

    @app.get("/v1/status", dependencies=[Depends(require_auth)])
    def status() -> dict[str, object]:
        return {
            "service": SERVICE_NAME,
            "phase": DEPLOYMENT_PHASE,
            "hostd_api_version": HOSTD_API_VERSION,
            "version": _version_payload(),
            "host": platform.node(),
            "platform": platform.platform(),
            "planned_surfaces": {
                "lmstudio": ["status", "models", "loaded", "load", "unload"],
                "wsl": ["status", "envs", "vllm.status", "vllm.start", "vllm.stop", "training.status", "training.start", "training.stop", "eval.status", "eval.start", "eval.stop"],
                "power": ["status", "training_on", "restore"],
                "mode": ["status", "set"],
                "actions": ["submit", "status", "cancel", "events"],
            },
            "implemented_surfaces": [
                "healthz",
                "version",
                "status",
                "lmstudio.status",
                "lmstudio.models",
                "lmstudio.loaded",
                "lmstudio.load",
                "lmstudio.unload",
                "wsl.status",
                "wsl.envs",
                "vllm.status",
                "vllm.start",
                "vllm.stop",
                "training.status",
                "training.start",
                "training.stop",
                "eval.status",
                "eval.start",
                "eval.stop",
                "power.status",
                "power.training_on",
                "power.restore",
                "mode.status",
                "mode.set",
            ],
            "ts": _utc_now(),
        }

    @app.get("/v1/lmstudio/status", dependencies=[Depends(require_auth)])
    def lmstudio_status(endpoint: str = lmstudio.DEFAULT_LMSTUDIO_ENDPOINT, lms_path: str | None = None) -> dict[str, object]:
        return {
            "endpoint": endpoint,
            "lms_path": lmstudio.resolve_lms_path(lms_path),
            "server": lmstudio.server_status(lms_path=lms_path),
            "loaded": lmstudio.loaded_models(lms_path=lms_path),
            "available": lmstudio.available_models(lms_path=lms_path),
            "ts": _utc_now(),
        }

    @app.get("/v1/lmstudio/models", dependencies=[Depends(require_auth)])
    def lmstudio_models(lms_path: str | None = None) -> dict[str, object]:
        models = lmstudio.available_models(lms_path=lms_path)
        return {
            "lms_path": lmstudio.resolve_lms_path(lms_path),
            "models": models,
            "model_ids": [key for entry in models for key in lmstudio.loaded_model_lookup_keys(entry)],
            "ts": _utc_now(),
        }

    @app.get("/v1/lmstudio/loaded", dependencies=[Depends(require_auth)])
    def lmstudio_loaded(lms_path: str | None = None) -> dict[str, object]:
        loaded = lmstudio.loaded_models(lms_path=lms_path)
        return {
            "lms_path": lmstudio.resolve_lms_path(lms_path),
            "loaded": loaded,
            "loaded_model_ids": [
                (entry.get("identifier") or entry.get("modelKey") or entry.get("id"))
                for entry in loaded
                if isinstance(entry, dict)
            ],
            "ts": _utc_now(),
        }

    @app.post("/v1/lmstudio/load", dependencies=[Depends(require_auth)])
    def lmstudio_load(payload: dict[str, object]) -> dict[str, object]:
        model_id = str(payload.get("model_id") or "").strip()
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id is required")
        result = lmstudio.load_model(
            model_id=model_id,
            identifier=str(payload.get("identifier") or "").strip() or None,
            context_length=int(payload["context_length"]) if payload.get("context_length") else None,
            parallel=int(payload["parallel"]) if payload.get("parallel") else None,
            gpu=str(payload.get("gpu") or "").strip() or None,
            ttl=int(payload["ttl"]) if payload.get("ttl") else None,
            estimate_only=bool(payload.get("estimate_only", False)),
            exclusive=bool(payload.get("exclusive", False)),
            lms_path=str(payload.get("lms_path") or "").strip() or None,
        )
        result["ts"] = _utc_now()
        result["lms_path"] = lmstudio.resolve_lms_path(str(payload.get("lms_path") or "").strip() or None)
        return result

    @app.post("/v1/lmstudio/unload", dependencies=[Depends(require_auth)])
    def lmstudio_unload(payload: dict[str, object]) -> dict[str, object]:
        result = lmstudio.unload_model(
            target=str(payload.get("target") or ""),
            all_models=bool(payload.get("all_models", False)),
            lms_path=str(payload.get("lms_path") or "").strip() or None,
        )
        result["ts"] = _utc_now()
        result["lms_path"] = lmstudio.resolve_lms_path(str(payload.get("lms_path") or "").strip() or None)
        return result

    @app.get("/v1/wsl/status", dependencies=[Depends(require_auth)])
    def wsl_status(distro: str | None = None) -> dict[str, object]:
        payload = wsl.status(distro=distro or wsl.DEFAULT_WSL_DISTRO)
        payload["ts"] = _utc_now()
        return payload

    @app.get("/v1/wsl/envs", dependencies=[Depends(require_auth)])
    def wsl_envs(distro: str | None = None) -> dict[str, object]:
        payload = wsl.envs(distro=distro or wsl.DEFAULT_WSL_DISTRO)
        payload["ts"] = _utc_now()
        return payload

    @app.get("/v1/power/status", dependencies=[Depends(require_auth)])
    def power_status() -> dict[str, object]:
        payload = power.current_policy()
        payload["ts"] = _utc_now()
        return payload

    @app.post("/v1/power/training-on", dependencies=[Depends(require_auth)])
    def power_training_on() -> dict[str, object]:
        payload = power.suppress_sleep_for_training()
        payload["ts"] = _utc_now()
        return payload

    @app.post("/v1/power/restore", dependencies=[Depends(require_auth)])
    def power_restore() -> dict[str, object]:
        payload = power.restore_sleep_policy()
        payload["ts"] = _utc_now()
        return payload

    @app.get("/v1/mode", dependencies=[Depends(require_auth)])
    def mode_status(
        task: str | None = None,
        config: str | None = None,
        distro: str | None = None,
        train_root: str | None = None,
        venv_dir: str | None = None,
        tail: int | None = None,
        lms_path: str | None = None,
        served_name: str | None = None,
        model: str | None = None,
        port: int | None = None,
    ) -> dict[str, object]:
        payload = _mode_snapshot(
            task=task,
            config=config,
            distro=distro or wsl.DEFAULT_WSL_DISTRO,
            train_root=train_root,
            venv_dir=venv_dir,
            tail=tail,
            lms_path=lms_path,
            served_name=served_name,
            model=model,
            port=port,
        )
        payload["ts"] = _utc_now()
        return payload

    @app.post("/v1/mode", dependencies=[Depends(require_auth)])
    def mode_set(payload: dict[str, object]) -> dict[str, object]:
        mode = str(payload.get("mode") or "").strip().lower()
        if mode not in SUPPORTED_MODES:
            raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(SUPPORTED_MODES)}")
        result = _apply_mode(
            mode=mode,
            task=str(payload.get("task") or "").strip() or None,
            config=str(payload.get("config") or "").strip() or None,
            distro=str(payload.get("distro") or "") or wsl.DEFAULT_WSL_DISTRO,
            train_root=str(payload.get("train_root") or "").strip() or None,
            venv_dir=str(payload.get("venv_dir") or "").strip() or None,
            tail=int(payload["tail"]) if payload.get("tail") else None,
            lms_path=str(payload.get("lms_path") or "").strip() or None,
            served_name=str(payload.get("served_name") or "").strip() or None,
            model=str(payload.get("model") or "").strip() or None,
            port=int(payload["port"]) if payload.get("port") else None,
            stop_vllm=bool(payload["stop_vllm"]) if "stop_vllm" in payload else None,
            unload_lmstudio=bool(payload["unload_lmstudio"]) if "unload_lmstudio" in payload else None,
            stop_training=bool(payload["stop_training"]) if "stop_training" in payload else None,
        )
        result["ts"] = _utc_now()
        return result

    @app.get("/v1/vllm/status", dependencies=[Depends(require_auth)])
    def vllm_status(distro: str | None = None, served_name: str | None = None, model: str | None = None, port: int | None = None) -> dict[str, object]:
        payload = wsl.vllm_action(
            "status",
            distro=distro or wsl.DEFAULT_WSL_DISTRO,
            served_name=served_name,
            model=model,
            port=port,
        )
        payload["ts"] = _utc_now()
        return payload

    @app.post("/v1/vllm/start", dependencies=[Depends(require_auth)])
    def vllm_start(payload: dict[str, object]) -> dict[str, object]:
        result = wsl.vllm_action(
            "start",
            distro=str(payload.get("distro") or "") or wsl.DEFAULT_WSL_DISTRO,
            model=str(payload.get("model") or "") or None,
            host=str(payload.get("host") or "") or None,
            port=int(payload["port"]) if payload.get("port") else None,
            served_name=str(payload.get("served_name") or "") or None,
            max_model_len=int(payload["max_model_len"]) if payload.get("max_model_len") else None,
        )
        result["ts"] = _utc_now()
        return result

    @app.post("/v1/vllm/stop", dependencies=[Depends(require_auth)])
    def vllm_stop(payload: dict[str, object]) -> dict[str, object]:
        result = wsl.vllm_action(
            "stop",
            distro=str(payload.get("distro") or "") or wsl.DEFAULT_WSL_DISTRO,
            model=str(payload.get("model") or "") or None,
            host=str(payload.get("host") or "") or None,
            port=int(payload["port"]) if payload.get("port") else None,
            served_name=str(payload.get("served_name") or "") or None,
            max_model_len=int(payload["max_model_len"]) if payload.get("max_model_len") else None,
        )
        result["ts"] = _utc_now()
        return result

    @app.get("/v1/eval/status", dependencies=[Depends(require_auth)])
    def eval_status(
        name: str,
        model: str,
        adapter: str,
        prompt_pack: str,
        out: str,
        distro: str | None = None,
        script: str | None = None,
        python_bin: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        seed: int | None = None,
        limit: int | None = None,
        attn: str | None = None,
        use_quant: bool | None = None,
    ) -> dict[str, object]:
        payload = wsl.eval_action(
            "status",
            distro=distro or wsl.DEFAULT_WSL_DISTRO,
            name=name,
            model=model,
            adapter=adapter,
            prompt_pack=prompt_pack,
            out=out,
            script=script,
            python_bin=python_bin,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            seed=seed,
            limit=limit,
            attn=attn,
            use_quant=use_quant,
        )
        payload["ts"] = _utc_now()
        return payload

    @app.post("/v1/eval/start", dependencies=[Depends(require_auth)])
    def eval_start(payload: dict[str, object]) -> dict[str, object]:
        required = {
            "name": str(payload.get("name") or "").strip(),
            "model": str(payload.get("model") or "").strip(),
            "adapter": str(payload.get("adapter") or "").strip(),
            "prompt_pack": str(payload.get("prompt_pack") or "").strip(),
            "out": str(payload.get("out") or "").strip(),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise HTTPException(status_code=400, detail=f"missing required eval fields: {', '.join(missing)}")
        result = wsl.eval_action(
            "start",
            distro=str(payload.get("distro") or "") or wsl.DEFAULT_WSL_DISTRO,
            name=required["name"],
            model=required["model"],
            adapter=required["adapter"],
            prompt_pack=required["prompt_pack"],
            out=required["out"],
            script=str(payload.get("script") or "") or None,
            python_bin=str(payload.get("python_bin") or "") or None,
            max_new_tokens=int(payload["max_new_tokens"]) if payload.get("max_new_tokens") else None,
            temperature=float(payload["temperature"]) if payload.get("temperature") is not None else None,
            top_p=float(payload["top_p"]) if payload.get("top_p") is not None else None,
            seed=int(payload["seed"]) if payload.get("seed") else None,
            limit=int(payload["limit"]) if payload.get("limit") else None,
            attn=str(payload.get("attn") or "") or None,
            use_quant=bool(payload.get("use_quant")) if payload.get("use_quant") is not None else None,
        )
        result["ts"] = _utc_now()
        return result

    @app.post("/v1/eval/stop", dependencies=[Depends(require_auth)])
    def eval_stop(payload: dict[str, object]) -> dict[str, object]:
        required = {
            "name": str(payload.get("name") or "").strip(),
            "model": str(payload.get("model") or "").strip(),
            "adapter": str(payload.get("adapter") or "").strip(),
            "prompt_pack": str(payload.get("prompt_pack") or "").strip(),
            "out": str(payload.get("out") or "").strip(),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise HTTPException(status_code=400, detail=f"missing required eval fields: {', '.join(missing)}")
        result = wsl.eval_action(
            "stop",
            distro=str(payload.get("distro") or "") or wsl.DEFAULT_WSL_DISTRO,
            name=required["name"],
            model=required["model"],
            adapter=required["adapter"],
            prompt_pack=required["prompt_pack"],
            out=required["out"],
            script=str(payload.get("script") or "") or None,
            python_bin=str(payload.get("python_bin") or "") or None,
            max_new_tokens=int(payload["max_new_tokens"]) if payload.get("max_new_tokens") else None,
            temperature=float(payload["temperature"]) if payload.get("temperature") is not None else None,
            top_p=float(payload["top_p"]) if payload.get("top_p") is not None else None,
            seed=int(payload["seed"]) if payload.get("seed") else None,
            limit=int(payload["limit"]) if payload.get("limit") else None,
            attn=str(payload.get("attn") or "") or None,
            use_quant=bool(payload.get("use_quant")) if payload.get("use_quant") is not None else None,
        )
        result["ts"] = _utc_now()
        return result

    @app.get("/v1/training/status", dependencies=[Depends(require_auth)])
    def training_status(task: str, config: str, distro: str | None = None, train_root: str | None = None, venv_dir: str | None = None, tail: int | None = None) -> dict[str, object]:
        payload = training_runtime.status_snapshot(
            task=task,
            config=config,
            train_root=train_root,
            tail=tail,
        )
        if distro:
            payload["distro"] = distro
        if venv_dir:
            payload["venv_dir"] = venv_dir
        payload["ts"] = _utc_now()
        return payload

    @app.post("/v1/training/start", dependencies=[Depends(require_auth)])
    def training_start(payload: dict[str, object]) -> dict[str, object]:
        task = str(payload.get("task") or "").strip()
        config = str(payload.get("config") or "").strip()
        if not task or not config:
            raise HTTPException(status_code=400, detail="task and config are required")
        power_payload = None
        power_warning = None
        try:
            power_payload = power.suppress_sleep_for_training()
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            power_warning = str(exc)
        try:
            result = wsl.training_action(
                "start",
                distro=str(payload.get("distro") or "") or wsl.DEFAULT_WSL_DISTRO,
                task=task,
                config=config,
                train_root=str(payload.get("train_root") or "") or None,
                venv_dir=str(payload.get("venv_dir") or "") or None,
                tail=int(payload["tail"]) if payload.get("tail") else None,
            )
        except Exception:
            if power_payload is not None:
                try:
                    power.restore_sleep_policy()
                except Exception:
                    pass
            raise
        if power_payload is not None:
            result["power"] = power_payload
        if power_warning is not None:
            result["power_warning"] = power_warning
        result["ts"] = _utc_now()
        return result

    @app.post("/v1/training/stop", dependencies=[Depends(require_auth)])
    def training_stop(payload: dict[str, object]) -> dict[str, object]:
        task = str(payload.get("task") or "").strip()
        config = str(payload.get("config") or "").strip()
        if not task or not config:
            raise HTTPException(status_code=400, detail="task and config are required")
        result = wsl.training_action(
            "stop",
            distro=str(payload.get("distro") or "") or wsl.DEFAULT_WSL_DISTRO,
            task=task,
            config=config,
            train_root=str(payload.get("train_root") or "") or None,
            venv_dir=str(payload.get("venv_dir") or "") or None,
            tail=int(payload["tail"]) if payload.get("tail") else None,
        )
        power_warning = None
        if str(result.get("state") or "").lower() == "stopped":
            try:
                result["power"] = power.restore_sleep_policy()
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                power_warning = str(exc)
        if power_warning is not None:
            result["power_warning"] = power_warning
        result["ts"] = _utc_now()
        return result

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "Run the phase-0 afs-hostd skeleton.")
    parser.add_argument("--host", default=os.environ.get("AFS_HOSTD_BIND_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AFS_HOSTD_PORT", "8766")))
    parser.add_argument("--token", default=os.environ.get("AFS_HOSTD_TOKEN"))
    args = parser.parse_args()

    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "uvicorn is not installed. Install afs_scawful[gateway] or add uvicorn to the host env."
        ) from exc

    app = create_app(token=args.token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
