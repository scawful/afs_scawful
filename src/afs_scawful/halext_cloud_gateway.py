"""Private OpenAI-compatible cloud gateway for halext.org."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from .halext_cloud_gateway_core import (
    DEFAULT_MODEL_SPECS,
    AvailabilitySnapshot,
    ProviderAvailability,
    ProviderName,
    apply_route_message_hints,
    build_default_priority,
    build_chat_payload,
    build_models_payload,
    build_stream_frames,
    choose_route,
    extract_system_and_messages,
    load_gateway_model_specs,
    normalize_messages_for_provider,
    ordered_live_route_specs,
    resolve_model_spec,
)
from .windows import WindowsHostClient

logger = logging.getLogger(__name__)

DEFAULT_ENV_FILE = Path("~/.config/afs/secrets.env").expanduser()
DEFAULT_TOKEN_CONFIG_FILE = Path("~/.config/afs/halext_gateway_tokens.json").expanduser()
DEFAULT_COMPANION_ALLOWED_MODELS: tuple[str, ...] = (
    "gemini-3-flash",
    "gemini-3.1-pro",
    "claude-sonnet-4.6",
    "scawfulbot-gemma4",
    "scawfulbot-qwen35",
    "scawfulbot-qwen3",
)


@dataclass(frozen=True)
class ChatMessageRow:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class SimpleChatRequest:
    model: str
    messages: list[ChatMessageRow]
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int | None = None
    stream: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SimpleChatRequest":
        model = str(payload.get("model", "")).strip()
        if not model:
            raise ValueError("model is required")

        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            raise ValueError("messages must be a non-empty array")

        messages: list[ChatMessageRow] = []
        for raw_message in raw_messages:
            if not isinstance(raw_message, dict):
                raise ValueError("message rows must be objects")
            role = str(raw_message.get("role", "")).strip()
            content = str(raw_message.get("content", "")).strip()
            if not role or not content:
                raise ValueError("each message must include role and content")
            messages.append(ChatMessageRow(role=role, content=content))

        temperature = float(payload.get("temperature", 0.7))
        top_p = float(payload.get("top_p", 0.9))
        raw_max_tokens = payload.get("max_tokens")
        max_tokens = int(raw_max_tokens) if raw_max_tokens is not None else None
        stream = bool(payload.get("stream", False))
        return cls(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stream=stream,
        )


@dataclass(frozen=True)
class AccessProfile:
    profile_id: str
    token: str
    allowed_public_ids: frozenset[str] | None = None
    allow_issue_reports: bool = True

    @property
    def is_owner(self) -> bool:
        return self.allowed_public_ids is None

    def filter_catalog(self, catalog: tuple[Any, ...]) -> tuple[Any, ...]:
        if self.allowed_public_ids is None:
            return catalog
        return tuple(spec for spec in catalog if spec.public_id in self.allowed_public_ids)

    def filter_priority(self, priority: tuple[str, ...]) -> tuple[str, ...]:
        if self.allowed_public_ids is None:
            return priority
        return tuple(model_id for model_id in priority if model_id in self.allowed_public_ids)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _bootstrap_env() -> None:
    env_file = Path(os.environ.get("HALEXT_GATEWAY_ENV_FILE", "")).expanduser()
    if not str(env_file) or str(env_file) == ".":
        env_file = DEFAULT_ENV_FILE
    _load_env_file(env_file)


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _normalize_profile_allowed_models(raw: Any) -> frozenset[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned or cleaned == "*":
            return None
        return frozenset(_parse_csv(cleaned))
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
        if "*" in values:
            return None
        return frozenset(values)
    return None


def load_access_profiles() -> tuple[AccessProfile, ...]:
    file_path = Path(os.environ.get("HALEXT_GATEWAY_TOKENS_FILE", "")).expanduser()
    if not str(file_path) or str(file_path) == ".":
        file_path = DEFAULT_TOKEN_CONFIG_FILE
    if file_path.exists():
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        rows = payload.get("profiles", [])
        profiles: list[AccessProfile] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            token = str(row.get("token", "")).strip()
            profile_id = str(row.get("profile", "")).strip()
            if not token or not profile_id:
                continue
            profiles.append(
                AccessProfile(
                    profile_id=profile_id,
                    token=token,
                    allowed_public_ids=_normalize_profile_allowed_models(row.get("allowed_models")),
                    allow_issue_reports=bool(row.get("allow_issue_reports", True)),
                )
            )
        if profiles:
            return tuple(profiles)

    profiles = []
    owner_token = (
        os.environ.get("HALEXT_GATEWAY_OWNER_TOKEN", "").strip()
        or os.environ.get("HALEXT_GATEWAY_TOKEN", "").strip()
    )
    companion_token = os.environ.get("HALEXT_GATEWAY_COMPANION_TOKEN", "").strip()
    companion_allowed = _parse_csv(
        os.environ.get("HALEXT_GATEWAY_COMPANION_ALLOWED_MODELS", ",".join(DEFAULT_COMPANION_ALLOWED_MODELS))
    )
    if owner_token:
        profiles.append(AccessProfile(profile_id="owner", token=owner_token))
    if companion_token:
        profiles.append(
            AccessProfile(
                profile_id="companion",
                token=companion_token,
                allowed_public_ids=frozenset(companion_allowed),
            )
        )
    return tuple(profiles)


class HalextCloudGateway:
    """Provider-backed gateway for the public halext.org edge."""

    def __init__(self, cache_ttl_seconds: int = 60):
        self.cache_ttl_seconds = cache_ttl_seconds
        self._snapshot: AvailabilitySnapshot | None = None
        self._lock = asyncio.Lock()
        self._clients: dict[ProviderName, Any] = {}
        self._catalog = DEFAULT_MODEL_SPECS
        self._priority = build_default_priority(self._catalog)
        self._access_profiles: tuple[AccessProfile, ...] = ()

    async def startup(self) -> None:
        _bootstrap_env()
        registry_override = os.environ.get("HALEXT_CHAT_REGISTRY_PATH", "").strip()
        self._catalog = load_gateway_model_specs(Path(registry_override).expanduser() if registry_override else None)
        self._priority = build_default_priority(self._catalog)
        self._access_profiles = load_access_profiles()
        self._clients = {
            "openai": self._build_openai_client(),
            "anthropic": self._build_anthropic_client(),
            "google": self._build_google_client(),
            "lmstudio": self._build_lmstudio_client(),
            "lmstudio_win": self._build_lmstudio_win_client(),
        }

    async def shutdown(self) -> None:
        client = self._clients.get("google")
        close = getattr(client, "close", None)
        if close:
            await close()

    def _build_openai_client(self) -> Any:
        from .integrations.openai_client import OpenAIClient

        base_url = os.environ.get("HALEXT_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        return OpenAIClient(base_url=base_url, timeout=90)

    def _build_anthropic_client(self) -> Any:
        from .integrations.anthropic_client import AnthropicClient

        base_url = os.environ.get("HALEXT_ANTHROPIC_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL")
        return AnthropicClient(base_url=base_url, timeout=90)

    def _build_google_client(self) -> Any:
        from .integrations.google_genai_client import GoogleAIStudioClient

        base_url = os.environ.get("HALEXT_GEMINI_BASE_URL") or os.environ.get("GEMINI_BASE_URL")
        if base_url:
            return GoogleAIStudioClient(base_url=base_url, timeout=90)
        return GoogleAIStudioClient(timeout=90)

    def _build_lmstudio_client(self) -> Any:
        from .integrations.openai_client import OpenAIClient

        base_url = os.environ.get("HALEXT_LMSTUDIO_BASE_URL", "").strip()
        if not base_url:
            return None

        api_key = os.environ.get("HALEXT_LMSTUDIO_API_KEY", "").strip()
        return OpenAIClient(
            api_key=api_key or None,
            api_key_env="HALEXT_LMSTUDIO_API_KEY",
            base_url=base_url,
            timeout=90,
            send_authorization=bool(api_key),
        )

    def _build_lmstudio_win_client(self) -> Any:
        from .integrations.openai_client import OpenAIClient

        base_url = os.environ.get("HALEXT_LMSTUDIO_WIN_BASE_URL", "").strip()
        if not base_url:
            return None

        api_key = os.environ.get("HALEXT_LMSTUDIO_WIN_API_KEY", "").strip()
        return OpenAIClient(
            api_key=api_key or None,
            api_key_env="HALEXT_LMSTUDIO_WIN_API_KEY",
            base_url=base_url,
            timeout=90,
            send_authorization=bool(api_key),
        )

    async def _provider_models(self, provider: ProviderName) -> ProviderAvailability:
        client = self._clients[provider]
        if client is None:
            return ProviderAvailability(healthy=False, models=(), error="not configured")
        try:
            models = tuple(await client.list_models())
            if not models:
                return ProviderAvailability(healthy=False, models=(), error="no models")
            return ProviderAvailability(healthy=True, models=models)
        except Exception as exc:
            logger.exception("Provider model listing failed: %s", provider)
            return ProviderAvailability(healthy=False, models=(), error=str(exc))

    async def availability_snapshot(self, force: bool = False) -> AvailabilitySnapshot:
        async with self._lock:
            now = time.time()
            if not force and self._snapshot and (now - self._snapshot.created) < self.cache_ttl_seconds:
                return self._snapshot
            provider_names: tuple[ProviderName, ...] = ("openai", "anthropic", "google", "lmstudio", "lmstudio_win")
            results = await asyncio.gather(
                *(self._provider_models(provider) for provider in provider_names),
            )
            snapshot = AvailabilitySnapshot(
                created=now,
                providers={provider: result for provider, result in zip(provider_names, results, strict=True)},
            )
            self._snapshot = snapshot
            return snapshot

    def resolve_access_profile(self, authorization_header: str | None) -> AccessProfile | None:
        if not authorization_header:
            return None
        scheme, _, token = authorization_header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        candidate = token.strip()
        for profile in self._access_profiles:
            if secrets.compare_digest(profile.token, candidate):
                return profile
        return None

    async def chat(self, request: Any, access_profile: AccessProfile) -> tuple[dict[str, object], str]:
        filtered_catalog = access_profile.filter_catalog(self._catalog)
        filtered_priority = access_profile.filter_priority(self._priority)
        requested_spec = resolve_model_spec(request.model, self._catalog)
        if requested_spec and requested_spec not in filtered_catalog:
            raise PermissionError(f"Model '{requested_spec.public_id}' is not available for this token")
        snapshot = await self.availability_snapshot()
        route = choose_route(request.model, snapshot, catalog=filtered_catalog, priority=filtered_priority)
        if route is None:
            raise RuntimeError("No cloud models available")

        system_text, chat_messages = extract_system_and_messages(
            [message.to_dict() for message in request.messages]
        )

        routes_to_try: list[Any]
        if (
            requested_spec is not None
            and requested_spec in filtered_catalog
            and route.public_id == requested_spec.public_id
        ):
            ordered = ordered_live_route_specs(requested_spec, snapshot)
            routes_to_try = list(ordered) if ordered else [route]
        else:
            routes_to_try = [route]

        last_error: str | None = None
        chosen_route: Any | None = None
        response: Any | None = None
        for spec_route in routes_to_try:
            normalized_messages = normalize_messages_for_provider(spec_route.provider, chat_messages)
            normalized_messages = apply_route_message_hints(spec_route, normalized_messages)
            if not normalized_messages:
                raise ValueError("No user or assistant messages supplied")
            response = await self._chat_provider(
                route=spec_route,
                messages=normalized_messages,
                system_text=system_text,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens or 1024,
            )
            if not response.error:
                chosen_route = spec_route
                break
            last_error = str(response.error)

        if chosen_route is None or response is None or response.error:
            raise RuntimeError(last_error or "upstream chat failed")
        payload = build_chat_payload(
            chosen_route.public_id,
            response.text,
            completion_tokens=response.tokens_generated,
            reasoning_content=getattr(response, "reasoning_content", None),
        )
        return payload, chosen_route.public_id

    async def _chat_provider(
        self,
        *,
        route: Any,
        messages: list[dict[str, str]],
        system_text: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> Any:
        client = self._clients[route.provider]
        if client is None:
            raise RuntimeError(f"{route.provider} upstream not configured")
        kwargs = {
            "model": route.provider_model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "system": system_text,
        }
        if route.provider == "anthropic":
            kwargs["top_p"] = None
        if route.provider == "google":
            # Gemini reasoning-capable models can consume a tiny token budget on
            # internal thoughts and return empty visible text. Keep a safer floor.
            kwargs["max_tokens"] = max(max_tokens, 256)
        if route.provider == "openai" and route.openai_api_mode:
            kwargs["max_tokens"] = max(max_tokens, 256)
            kwargs["temperature"] = None
            kwargs["top_p"] = None
            kwargs["options"] = {"api_mode": route.openai_api_mode}
        return await client.chat(**kwargs)


def _issue_report_dir() -> Path:
    raw = os.environ.get("HALEXT_ISSUE_REPORT_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("~/.local/share/halext/scawfulbot/issues").expanduser()


def _slugify(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    collapsed = "-".join(part for part in cleaned.split("-") if part)
    return collapsed or "report"


def _format_issue_markdown(report_id: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload.get('issueType', 'issue')} ({payload.get('severity', 'unknown')})",
        "",
        f"- id: `{report_id}`",
        f"- app: `{payload.get('app', 'unknown')}`",
        f"- timestamp: `{payload.get('timestamp', '')}`",
        f"- thread: `{payload.get('threadTitle', '')}`",
        f"- scope: `{payload.get('scope', '')}`",
        f"- contact: `{payload.get('contact', '')}`",
        f"- task mode: `{payload.get('taskMode', '')}`",
        f"- routing: `{payload.get('routingMode', '')}`",
    ]

    if payload.get("model"):
        lines.append(f"- model: `{payload['model']}`")
    if payload.get("provider"):
        lines.append(f"- provider: `{payload['provider']}`")
    if payload.get("routerStatus"):
        lines.append(f"- router status: `{payload['routerStatus']}`")
    if payload.get("error"):
        lines.append(f"- error: `{payload['error']}`")

    sections = [
        ("Report", payload.get("reportBody")),
        ("Note", payload.get("note")),
        ("Expected", payload.get("expectedBehavior")),
        ("Actual", payload.get("actualBehavior")),
        ("Repro", payload.get("reproSteps")),
        ("Prompt Excerpt", payload.get("promptExcerpt")),
        ("Reply Excerpt", payload.get("replyExcerpt")),
    ]
    for title, body in sections:
        body_text = str(body or "").strip()
        if not body_text:
            continue
        lines.extend(["", f"## {title}", "", body_text])

    return "\n".join(lines).strip() + "\n"


def _persist_issue_report(payload: dict[str, Any]) -> tuple[str, Path]:
    issue_dir = _issue_report_dir()
    issue_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    issue_type = _slugify(str(payload.get("issueType", "issue")))
    severity = _slugify(str(payload.get("severity", "unknown")))
    report_id = f"{timestamp}-{severity}-{issue_type}"

    json_path = issue_dir / f"{report_id}.json"
    markdown_path = issue_dir / f"{report_id}.md"

    record = {
        "id": report_id,
        "receivedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "payload": payload,
    }
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(_format_issue_markdown(report_id, payload), encoding="utf-8")
    return report_id, markdown_path


def _issue_preview(payload: dict[str, Any]) -> str:
    for key in ("reportBody", "note", "actualBehavior", "reproSteps", "expectedBehavior"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value[:240]
    return ""


def _summarize_issue_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload", {}) if isinstance(record.get("payload"), dict) else {}
    return {
        "id": record.get("id", ""),
        "receivedAt": record.get("receivedAt", ""),
        "issueType": payload.get("issueType", ""),
        "severity": payload.get("severity", ""),
        "app": payload.get("app", ""),
        "threadTitle": payload.get("threadTitle", ""),
        "scope": payload.get("scope", ""),
        "contact": payload.get("contact", ""),
        "taskMode": payload.get("taskMode", ""),
        "routingMode": payload.get("routingMode", ""),
        "model": payload.get("model", ""),
        "provider": payload.get("provider", ""),
        "routerStatus": payload.get("routerStatus", ""),
        "error": payload.get("error", ""),
        "preview": _issue_preview(payload),
    }


def _load_issue_report_summaries(limit: int = 20) -> list[dict[str, Any]]:
    issue_dir = _issue_report_dir()
    if not issue_dir.exists():
        return []

    reports: list[dict[str, Any]] = []
    for path in sorted(issue_dir.glob("*.json"), reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reports.append(_summarize_issue_record(record))
        if len(reports) >= max(1, limit):
            break
    return reports


def _halext_admin_base_url() -> str:
    base = os.environ.get("HALEXT_ADMIN_API_BASE_URL", "").strip()
    if not base:
        base = "http://127.0.0.1:8000/api/admin"
    return base.rstrip("/")


def _halext_admin_token() -> str:
    return os.environ.get("HALEXT_ADMIN_API_TOKEN", "").strip()


def _halext_admin_is_configured() -> bool:
    return bool(_halext_admin_token())


def _halext_admin_request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    token = _halext_admin_token()
    if not token:
        raise RuntimeError("HALEXT_ADMIN_API_TOKEN is not configured")

    url = f"{_halext_admin_base_url()}/{path.lstrip('/')}"
    body = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return response.getcode(), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw) if raw else {}
        except Exception:
            detail = {"detail": raw or f"HTTP {exc.code}"}
        return exc.code, detail
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to reach halext admin API: {exc.reason}") from exc


def _windows_hostd_base_url() -> str:
    return (
        os.environ.get("HALEXT_WINDOWS_HOSTD_URL", "").strip()
        or os.environ.get("AFS_HOSTD_URL", "").strip()
    ).rstrip("/")


def _windows_hostd_token() -> str:
    return (
        os.environ.get("HALEXT_WINDOWS_HOSTD_TOKEN", "").strip()
        or os.environ.get("AFS_HOSTD_TOKEN", "").strip()
    )


def _windows_hostd_is_configured() -> bool:
    return bool(_windows_hostd_base_url())


def _windows_wsl_distro() -> str:
    return (
        os.environ.get("HALEXT_WINDOWS_WSL_DISTRO", "").strip()
        or os.environ.get("AFS_WSL_DISTRO", "").strip()
        or "Ubuntu"
    )


def _env_int(name: str, default: int | None = None) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _windows_vllm_target() -> dict[str, Any]:
    return {
        "distro": _windows_wsl_distro(),
        "model": os.environ.get("HALEXT_WINDOWS_VLLM_MODEL", "").strip() or "/mnt/d/models/scawful/scawfulbot-qwen3-8b-v1",
        "host": os.environ.get("HALEXT_WINDOWS_VLLM_HOST", "").strip() or "127.0.0.1",
        "port": _env_int("HALEXT_WINDOWS_VLLM_PORT", 8008) or 8008,
        "servedName": os.environ.get("HALEXT_WINDOWS_VLLM_SERVED_NAME", "").strip() or "scawfulbot-qwen3-8b-v1",
        "maxModelLen": _env_int("HALEXT_WINDOWS_VLLM_MAX_MODEL_LEN", 4096) or 4096,
    }


def _windows_training_target() -> dict[str, Any]:
    task = os.environ.get("HALEXT_WINDOWS_TRAINING_TASK", "").strip() or None
    config = os.environ.get("HALEXT_WINDOWS_TRAINING_CONFIG", "").strip() or None
    train_root = os.environ.get("HALEXT_WINDOWS_TRAINING_ROOT", "").strip() or None
    venv_dir = os.environ.get("HALEXT_WINDOWS_TRAINING_VENV", "").strip() or None
    return {
        "configured": bool(task and config),
        "distro": _windows_wsl_distro(),
        "task": task,
        "config": config,
        "trainRoot": train_root,
        "venvDir": venv_dir,
    }


def _windows_hostd_client() -> WindowsHostClient:
    base_url = _windows_hostd_base_url()
    if not base_url:
        raise RuntimeError("HALEXT_WINDOWS_HOSTD_URL is not configured")
    return WindowsHostClient(
        hostd_url=base_url,
        token=_windows_hostd_token() or None,
        timeout=10.0,
    )


def _windows_host_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _windows_hostd_client().request_hostd_json(path, method=method, payload=payload)


def _windows_host_status_payload() -> dict[str, Any]:
    training_target = _windows_training_target()
    payload: dict[str, Any] = {
        "configured": _windows_hostd_is_configured(),
        "baseUrl": _windows_hostd_base_url() or None,
        "hostdHealth": None,
        "hostStatus": None,
        "wslStatus": None,
        "wslEnvs": None,
        "vllm": None,
        "training": None,
        "probeErrors": {},
        "error": None,
        "targets": {
            "vllm": _windows_vllm_target(),
            "training": training_target,
        },
        "allowedActions": {
            "vllm": ["start", "stop"],
            "training": ["start", "stop"] if training_target["configured"] else [],
        },
    }
    if not payload["configured"]:
        return payload

    try:
        payload["hostdHealth"] = _windows_host_request("GET", "/healthz")
    except RuntimeError as exc:
        payload["error"] = str(exc)
        return payload

    probes: list[tuple[str, str]] = [
        ("hostStatus", "/v1/status"),
        ("wslStatus", f"/v1/wsl/status?{urllib.parse.urlencode({'distro': _windows_wsl_distro()})}"),
        ("wslEnvs", f"/v1/wsl/envs?{urllib.parse.urlencode({'distro': _windows_wsl_distro()})}"),
        (
            "vllm",
            f"/v1/vllm/status?{urllib.parse.urlencode(_compact_dict({'distro': _windows_wsl_distro(), 'model': _windows_vllm_target()['model'], 'port': _windows_vllm_target()['port'], 'served_name': _windows_vllm_target()['servedName']}))}",
        ),
    ]
    if training_target["configured"]:
        probes.append(
            (
                "training",
                f"/v1/training/status?{urllib.parse.urlencode(_compact_dict({'distro': training_target['distro'], 'task': training_target['task'], 'config': training_target['config'], 'train_root': training_target['trainRoot'], 'venv_dir': training_target['venvDir']}))}",
            )
        )

    for key, path in probes:
        try:
            payload[key] = _windows_host_request("GET", path)
        except RuntimeError as exc:
            cast_errors = payload["probeErrors"]
            if isinstance(cast_errors, dict):
                cast_errors[key] = str(exc)

    return payload


def _security_checks(access_profiles: tuple[AccessProfile, ...]) -> list[dict[str, str]]:
    by_id = {profile.profile_id: profile for profile in access_profiles}
    owner = by_id.get("owner")
    companion = by_id.get("companion")
    checks: list[dict[str, str]] = []

    checks.append(
        {
            "code": "owner_token_present",
            "level": "ok" if owner else "warn",
            "detail": "Owner token configured" if owner else "Owner token missing",
        }
    )
    checks.append(
        {
            "code": "companion_token_present",
            "level": "ok" if companion else "warn",
            "detail": "Companion token configured" if companion else "Companion token missing",
        }
    )
    checks.append(
        {
            "code": "split_tokens",
            "level": "ok" if owner and companion and owner.token != companion.token else "warn",
            "detail": "Owner and companion use distinct tokens"
            if owner and companion and owner.token != companion.token
            else "Owner and companion are not split cleanly",
        }
    )
    checks.append(
        {
            "code": "companion_scoped",
            "level": "ok" if companion and companion.allowed_public_ids is not None else "warn",
            "detail": "Companion token has a scoped allowlist"
            if companion and companion.allowed_public_ids is not None
            else "Companion token is not restricted to an allowlist",
        }
    )
    checks.append(
        {
            "code": "admin_proxy_configured",
            "level": "ok" if _halext_admin_is_configured() else "warn",
            "detail": "Admin proxy token configured"
            if _halext_admin_is_configured()
            else "HALEXT_ADMIN_API_TOKEN is missing",
        }
    )

    return checks


def create_app() -> Any:
    from fastapi import Body, FastAPI, HTTPException, Request as FastAPIRequest
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse

    globals()["Request"] = FastAPIRequest

    gateway = HalextCloudGateway()

    def _require_owner_profile(request: FastAPIRequest) -> AccessProfile:
        access_profile = _require_access_profile(request)
        if not access_profile.is_owner:
            raise HTTPException(status_code=403, detail="Owner access required")
        return access_profile

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await gateway.startup()
        yield
        await gateway.shutdown()

    app = FastAPI(
        title="Halext Cloud Gateway",
        description="Private OpenAI-compatible gateway for cloud providers behind halext.org.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        snapshot = await gateway.availability_snapshot(force=True)
        return {
            "status": "healthy" if any(state.healthy for state in snapshot.providers.values()) else "degraded",
            "providers": {
                name: {
                    "healthy": state.healthy,
                    "models": list(state.models),
                    "error": state.error,
                }
                for name, state in snapshot.providers.items()
            },
        }

    def _require_access_profile(request: Request) -> AccessProfile:
        profile = gateway.resolve_access_profile(request.headers.get("authorization"))
        if profile is None:
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token")
        return profile

    @app.get("/v1/models")
    async def list_models(request: Request) -> dict[str, object]:
        access_profile = _require_access_profile(request)
        snapshot = await gateway.availability_snapshot(force=True)
        return build_models_payload(snapshot, access_profile.filter_catalog(gateway._catalog))

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: Request,
        request_payload: dict[str, Any] = Body(...),
    ) -> Any:
        access_profile = _require_access_profile(request)
        try:
            chat_request = SimpleChatRequest.from_payload(request_payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            payload, routed_model = await gateway.chat(chat_request, access_profile)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        if not chat_request.stream:
            return JSONResponse(payload)

        async def event_stream():
            message = payload["choices"][0]["message"]
            for frame in build_stream_frames(
                routed_model,
                str(message["content"]),
                reasoning_content=message.get("reasoning_content") if isinstance(message, dict) else None,
            ):
                yield frame

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/v1/scawfulbot/issues")
    @app.post("/v1/scawfulbot/issues")
    async def create_issue_report(
        request: Request,
        request_payload: dict[str, Any] = Body(...),
    ) -> Any:
        access_profile = _require_access_profile(request)
        if not access_profile.allow_issue_reports:
            raise HTTPException(status_code=403, detail="Issue reporting disabled for this token")
        report_body = str(request_payload.get("reportBody", "")).strip()
        issue_type = str(request_payload.get("issueType", "")).strip()
        severity = str(request_payload.get("severity", "")).strip()
        if not report_body or not issue_type or not severity:
            raise HTTPException(status_code=400, detail="issueType, severity, and reportBody are required")

        report_id, path = _persist_issue_report(request_payload)
        return JSONResponse(
            {
                "ok": True,
                "id": report_id,
                "stored": str(path),
            },
            status_code=201,
        )

    @app.get("/api/v1/scawfulbot/issues")
    @app.get("/v1/scawfulbot/issues")
    async def list_issue_reports(
        request: Request,
        limit: int = 20,
    ) -> Any:
        _require_owner_profile(request)
        reports = _load_issue_report_summaries(limit=limit)
        return JSONResponse(
            {
                "ok": True,
                "issueReportDir": str(_issue_report_dir()),
                "count": len(reports),
                "reports": reports,
            }
        )

    @app.get("/api/v1/scawfulbot/owner/status")
    @app.get("/v1/scawfulbot/owner/status")
    async def owner_status(
        request: Request,
    ) -> Any:
        _require_owner_profile(request)
        recent_issues = _load_issue_report_summaries(limit=8)
        admin_payload: dict[str, Any] = {
            "configured": _halext_admin_is_configured(),
            "baseUrl": _halext_admin_base_url(),
            "serverStatus": None,
            "error": None,
            "allowedActions": ["restart", "reload"],
        }
        if admin_payload["configured"]:
            try:
                status_code, payload = _halext_admin_request("GET", "server/status")
                if status_code == 200:
                    admin_payload["serverStatus"] = payload
                else:
                    admin_payload["error"] = payload.get("detail", f"HTTP {status_code}") if isinstance(payload, dict) else str(payload)
            except RuntimeError as exc:
                admin_payload["error"] = str(exc)

        return JSONResponse(
            {
                "ok": True,
                "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "issueReportDir": str(_issue_report_dir()),
                "issueCount": len(list(_issue_report_dir().glob("*.json"))) if _issue_report_dir().exists() else 0,
                "recentIssues": recent_issues,
                "securityChecks": _security_checks(gateway._access_profiles),
                "admin": admin_payload,
                "windowsHost": _windows_host_status_payload(),
            }
        )

    @app.post("/api/v1/scawfulbot/owner/services/{service}/action")
    @app.post("/v1/scawfulbot/owner/services/{service}/action")
    async def owner_service_action(
        service: str,
        request: Request,
        request_payload: dict[str, Any] = Body(...),
    ) -> Any:
        _require_owner_profile(request)
        action = str(request_payload.get("action", "")).strip().lower()
        if action not in {"restart", "reload"}:
            raise HTTPException(status_code=400, detail="Only restart and reload are allowed")

        if not _halext_admin_is_configured():
            raise HTTPException(status_code=503, detail="HALEXT_ADMIN_API_TOKEN is not configured")

        try:
            status_code, payload = _halext_admin_request(
                "POST",
                f"services/{service}/action",
                {"action": action},
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        if status_code >= 400:
            detail = payload.get("detail", f"HTTP {status_code}") if isinstance(payload, dict) else str(payload)
            raise HTTPException(status_code=status_code, detail=detail)

        return JSONResponse(
            {
                "ok": True,
                "service": service,
                "action": action,
                "result": payload,
            }
        )

    @app.post("/api/v1/scawfulbot/owner/windows/{service}/{action}")
    @app.post("/v1/scawfulbot/owner/windows/{service}/{action}")
    async def owner_windows_action(
        service: str,
        action: str,
        request: Request,
    ) -> Any:
        _require_owner_profile(request)
        normalized_service = service.strip().lower()
        normalized_action = action.strip().lower()
        if normalized_service not in {"vllm", "training"}:
            raise HTTPException(status_code=404, detail="Unsupported Windows host service")
        if normalized_action not in {"start", "stop"}:
            raise HTTPException(status_code=400, detail="Only start and stop are allowed")
        if not _windows_hostd_is_configured():
            raise HTTPException(status_code=503, detail="HALEXT_WINDOWS_HOSTD_URL is not configured")

        try:
            if normalized_service == "vllm":
                target = _windows_vllm_target()
                request_payload = {
                    "distro": target["distro"],
                    "model": target["model"],
                    "host": target["host"],
                    "port": target["port"],
                    "served_name": target["servedName"],
                    "max_model_len": target["maxModelLen"],
                }
                result = _windows_host_request("POST", f"/v1/vllm/{normalized_action}", request_payload)
            else:
                target = _windows_training_target()
                if not target["configured"]:
                    raise HTTPException(status_code=503, detail="Windows training target is not configured")
                request_payload = _compact_dict(
                    {
                        "distro": target["distro"],
                        "task": target["task"],
                        "config": target["config"],
                        "train_root": target["trainRoot"],
                        "venv_dir": target["venvDir"],
                    }
                )
                result = _windows_host_request("POST", f"/v1/training/{normalized_action}", request_payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return JSONResponse(
            {
                "ok": True,
                "service": normalized_service,
                "action": normalized_action,
                "result": result,
            }
        )

    return app


def main() -> int:
    import uvicorn

    host = os.environ.get("HALEXT_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("HALEXT_GATEWAY_PORT", "4100"))
    uvicorn.run(
        "afs_scawful.halext_cloud_gateway:create_app",
        factory=True,
        host=host,
        port=port,
        proxy_headers=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
