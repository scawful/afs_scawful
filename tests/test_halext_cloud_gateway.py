from __future__ import annotations

import json
import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - local test env may not have FastAPI extras
    TestClient = None

from afs_scawful.halext_cloud_gateway import AccessProfile
from afs_scawful.halext_cloud_gateway import ChatMessageRow
from afs_scawful.halext_cloud_gateway import HalextCloudGateway
from afs_scawful.halext_cloud_gateway import _persist_issue_report
from afs_scawful.halext_cloud_gateway import create_app
from afs_scawful.halext_cloud_gateway import load_access_profiles
from afs_scawful.halext_cloud_gateway_core import (
    AvailabilitySnapshot,
    ProviderAvailability,
    apply_route_message_hints,
    available_model_specs,
    build_default_priority,
    build_chat_payload,
    build_models_payload,
    build_stream_frames,
    choose_route,
    extract_system_and_messages,
    load_gateway_model_specs,
    load_registry_model_specs,
    normalize_messages_for_provider,
    ordered_live_route_specs,
    resolve_model_spec,
)


def _snapshot(
    *,
    openai: tuple[str, ...] = (),
    anthropic: tuple[str, ...] = (),
    google: tuple[str, ...] = (),
    lmstudio: tuple[str, ...] = (),
    lmstudio_win: tuple[str, ...] = (),
) -> AvailabilitySnapshot:
    return AvailabilitySnapshot(
        created=1_713_000_000.0,
        providers={
            "openai": ProviderAvailability(healthy=bool(openai), models=openai),
            "anthropic": ProviderAvailability(healthy=bool(anthropic), models=anthropic),
            "google": ProviderAvailability(healthy=bool(google), models=google),
            "lmstudio": ProviderAvailability(healthy=bool(lmstudio), models=lmstudio),
            "lmstudio_win": ProviderAvailability(healthy=bool(lmstudio_win), models=lmstudio_win),
        },
    )


def test_resolve_model_spec_accepts_public_and_provider_aliases() -> None:
    gemini = resolve_model_spec("gemini-3.1-pro")
    gemini_preview = resolve_model_spec("models/gemini-3.1-pro-preview")
    haiku = resolve_model_spec("claude-haiku-4-5-20251001")
    sonnet = resolve_model_spec("sonnet-4.6")
    gpt = resolve_model_spec("gpt-5.2")

    assert gemini is not None
    assert gemini_preview is not None
    assert haiku is not None
    assert sonnet is not None
    assert gpt is not None

    assert gemini.provider == "google"
    assert gemini_preview.public_id == "gemini-3.1-pro"
    assert haiku.public_id == "claude-haiku-4.5"
    assert sonnet.public_id == "claude-sonnet-4.6"
    assert gpt.provider == "openai"


def test_registry_specs_load_big_three_catalog() -> None:
    specs = load_registry_model_specs()
    public_ids = {spec.public_id for spec in specs}
    assert "gemini-2.5-pro" in public_ids
    assert "gemini-3-pro" in public_ids
    assert "claude-sonnet-4.6" in public_ids
    assert "claude-opus-4.6" in public_ids
    assert "gpt-5.2" in public_ids
    assert "codex-5.3" in public_ids


def test_gateway_catalog_merges_static_and_registry_specs() -> None:
    catalog = load_gateway_model_specs()
    public_ids = [spec.public_id for spec in catalog]
    assert "scawfulbot-gemma4" in public_ids
    assert "scawfulbot-qwen35" in public_ids
    assert "claude-haiku-4.5" in public_ids
    assert "claude-sonnet-4.6" in public_ids
    assert "codex-5.3" in public_ids
    assert public_ids.count("claude-sonnet-4.6") == 1


def test_default_priority_prefers_cloud_big_three_before_local_models() -> None:
    priority = build_default_priority(load_gateway_model_specs())
    assert priority.index("gemini-3.1-pro") < priority.index("claude-sonnet-4.6")
    assert priority.index("claude-sonnet-4.6") < priority.index("gpt-5.2")
    assert priority.index("gpt-5.2") < priority.index("scawfulbot-gemma4")


def test_extract_system_and_messages_splits_history_cleanly() -> None:
    system, messages = extract_system_and_messages(
        [
            {"role": "system", "content": "top rules"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "system", "content": "extra rules"},
        ]
    )
    assert system == "top rules\n\nextra rules"
    assert messages == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_normalize_messages_for_google_maps_assistant_to_model_and_merges() -> None:
    normalized = normalize_messages_for_provider(
        "google",
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "one"},
            {"role": "assistant", "content": "two"},
        ],
    )
    assert normalized == [
        {"role": "user", "content": "hi"},
        {"role": "model", "content": "one\n\ntwo"},
    ]


def test_available_model_specs_only_returns_live_catalog_rows() -> None:
    snapshot = _snapshot(
        google=("models/gemini-3.1-pro-preview",),
        anthropic=("claude-sonnet-4-6",),
        lmstudio=("gguf/scawful/scawfulbot-gemma4-e4b-sft-dpo-q4km.gguf",),
    )
    assert [spec.public_id for spec in available_model_specs(snapshot)] == [
        "scawfulbot-gemma4",
        "gemini-3.1-pro",
        "claude-sonnet-4.6",
    ]


def test_choose_route_falls_back_to_best_live_model() -> None:
    snapshot = _snapshot(
        openai=("gpt-5",),
        google=("models/gemini-3-flash-preview",),
    )
    route = choose_route("claude-sonnet-4.6", snapshot)
    assert route is not None
    assert route.public_id == "gemini-3-flash"


def test_apply_route_message_hints_appends_no_think_once() -> None:
    route = resolve_model_spec("scawfulbot-qwen3")
    assert route is not None
    messages = [
        {"role": "user", "content": "Reply with exactly: OK"},
        {"role": "assistant", "content": "earlier"},
        {"role": "user", "content": "Do it now"},
    ]

    hinted = apply_route_message_hints(route, messages)
    assert hinted[-1]["content"] == "Do it now /no_think"
    assert apply_route_message_hints(route, hinted)[-1]["content"] == "Do it now /no_think"


def test_live_route_matches_path_qualified_windows_qwen_id() -> None:
    snapshot = _snapshot(
        lmstudio=("noise-unrelated-mlx",),
        lmstudio_win=("lmstudio-community/models/scawfulbot-qwen3-8b-v1-q4_k_m.gguf",),
    )
    spec = resolve_model_spec("scawfulbot-qwen3")
    assert spec is not None
    live = spec.live_route(snapshot)
    assert live is not None
    assert live.provider == "lmstudio_win"
    assert live.provider_model == "lmstudio-community/models/scawfulbot-qwen3-8b-v1-q4_k_m.gguf"


def test_ordered_live_route_specs_lists_mac_then_win_when_both_visible() -> None:
    snapshot = _snapshot(
        lmstudio=("scawfulbot-qwen3-8b-v1-mlx",),
        lmstudio_win=("scawfulbot-qwen3-8b-v1",),
    )
    spec = resolve_model_spec("scawfulbot-qwen3")
    assert spec is not None
    ordered = ordered_live_route_specs(spec, snapshot)
    assert len(ordered) == 2
    assert ordered[0].provider == "lmstudio"
    assert ordered[1].provider == "lmstudio_win"


def test_scawfulbot_routes_can_fall_back_to_windows_scawfulbot_backends() -> None:
    snapshot = _snapshot(
        lmstudio_win=(
            "gguf/lmstudio/scawfulbot-gemma4-e4b-sft-dpo-q4km.gguf",
            "scawfulbot-qwen35-v1-dpo-q5_k_m",
            "scawfulbot-qwen3-8b-v1",
        )
    )

    gemma_route = choose_route("scawfulbot-gemma4", snapshot)
    qwen35_route = choose_route("scawfulbot-qwen35", snapshot)
    qwen_route = choose_route("scawfulbot-qwen3", snapshot)

    assert gemma_route is not None
    assert qwen35_route is not None
    assert qwen_route is not None

    assert gemma_route.provider == "lmstudio_win"
    assert gemma_route.provider_model == "gguf/lmstudio/scawfulbot-gemma4-e4b-sft-dpo-q4km.gguf"
    assert qwen35_route.provider == "lmstudio_win"
    assert qwen35_route.provider_model == "scawfulbot-qwen35-v1-dpo-q5_k_m"
    assert qwen_route.provider == "lmstudio_win"
    assert qwen_route.provider_model == "scawfulbot-qwen3-8b-v1"


def test_build_models_payload_is_openai_compatible() -> None:
    payload = build_models_payload(_snapshot(google=("models/gemini-3.1-pro-preview",)))
    assert payload["object"] == "list"
    assert payload["data"] == [
        {
            "id": "gemini-3.1-pro",
            "object": "model",
            "created": 1_713_000_000,
            "owned_by": "halext",
        }
    ]


def test_build_chat_payload_is_openai_compatible() -> None:
    payload = cast(dict[str, object], build_chat_payload("gemini-3.1-pro", "hello", completion_tokens=12, prompt_tokens=8, response_id="abc", created=5))
    choices = cast(list[dict[str, object]], payload["choices"])
    usage = cast(dict[str, object], payload["usage"])
    assert payload["id"] == "abc"
    assert cast(dict[str, object], choices[0]["message"])["content"] == "hello"
    assert usage["total_tokens"] == 20


def test_build_chat_payload_can_include_reasoning_content() -> None:
    payload = cast(
        dict[str, object],
        build_chat_payload("scawfulbot-qwen35", "OK", reasoning_content="thinking", response_id="abc", created=5),
    )
    choices = cast(list[dict[str, object]], payload["choices"])
    message = cast(dict[str, object], choices[0]["message"])
    assert message["content"] == "OK"
    assert message["reasoning_content"] == "thinking"


def test_openai_client_extracts_lmstudio_reasoning_content() -> None:
    pytest.importorskip("aiohttp")
    from afs_scawful.integrations.openai_client import _extract_reasoning_from_chat

    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "\n\nOK.",
                    "reasoning_content": "Thinking process:\n\nAnswer directly.",
                }
            }
        ]
    }

    assert _extract_reasoning_from_chat(payload) == "Thinking process:\n\nAnswer directly."


def test_build_stream_frames_emit_delta_then_done_marker() -> None:
    frames = build_stream_frames("gemini-3-flash", "hello world", response_id="abc", created=5, chunk_size=5)
    assert frames[-1] == "data: [DONE]\n\n"
    first_payload = json.loads(frames[0][len("data: "):-2])
    second_payload = json.loads(frames[1][len("data: "):-2])
    assert first_payload["choices"][0]["delta"] == {"role": "assistant"}
    assert second_payload["choices"][0]["delta"]["content"] == "hello"


def test_build_stream_frames_emit_reasoning_before_content() -> None:
    frames = build_stream_frames(
        "scawfulbot-qwen35",
        "OK",
        reasoning_content="thinking",
        response_id="abc",
        created=5,
        chunk_size=20,
    )
    assert frames[-1] == "data: [DONE]\n\n"
    first_payload = json.loads(frames[0][len("data: "):-2])
    reasoning_payload = json.loads(frames[1][len("data: "):-2])
    content_payload = json.loads(frames[2][len("data: "):-2])
    assert first_payload["choices"][0]["delta"] == {"role": "assistant"}
    assert reasoning_payload["choices"][0]["delta"] == {"reasoning_content": "thinking"}
    assert content_payload["choices"][0]["delta"] == {"content": "OK"}


def test_persist_issue_report_writes_json_and_markdown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HALEXT_ISSUE_REPORT_DIR", str(tmp_path))
    payload = {
        "issueType": "bug",
        "severity": "high",
        "reportBody": "Report body",
        "threadTitle": "Test Thread",
        "scope": "Scawfulbot",
        "contact": "Justin",
        "taskMode": "Chat",
        "routingMode": "auto-route",
    }

    report_id, markdown_path = _persist_issue_report(payload)

    json_path = tmp_path / f"{report_id}.json"
    assert json_path.exists()
    assert markdown_path.exists()
    stored = json.loads(json_path.read_text(encoding="utf-8"))
    assert stored["id"] == report_id
    assert stored["payload"]["reportBody"] == "Report body"
    assert "Report body" in markdown_path.read_text(encoding="utf-8")


def test_load_access_profiles_supports_json_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "tokens.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {"profile": "owner", "token": "owner-secret", "allowed_models": "*"},
                    {
                        "profile": "companion",
                        "token": "companion-secret",
                        "allowed_models": ["gemini-3-flash", "gemini-3.1-pro", "claude-sonnet-4.6"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HALEXT_GATEWAY_TOKENS_FILE", str(config_path))

    profiles = load_access_profiles()
    assert [profile.profile_id for profile in profiles] == ["owner", "companion"]
    assert profiles[0].allowed_public_ids is None
    assert profiles[1].allowed_public_ids == frozenset({"gemini-3-flash", "gemini-3.1-pro", "claude-sonnet-4.6"})


def test_access_profile_filters_catalog() -> None:
    companion = AccessProfile(
        profile_id="companion",
        token="secret",
        allowed_public_ids=frozenset({"gemini-3-flash", "gemini-3.1-pro", "claude-sonnet-4.6"}),
    )
    filtered = companion.filter_catalog(load_gateway_model_specs())
    assert [spec.public_id for spec in filtered] == [
        "gemini-3.1-pro",
        "gemini-3-flash",
        "claude-sonnet-4.6",
    ]


def test_gateway_resolves_bearer_token_to_profile() -> None:
    gateway = HalextCloudGateway()
    gateway._access_profiles = (
        AccessProfile(profile_id="owner", token="owner-secret"),
        AccessProfile(profile_id="companion", token="companion-secret", allowed_public_ids=frozenset({"gemini-3-flash"})),
    )

    owner = gateway.resolve_access_profile("Bearer owner-secret")
    companion = gateway.resolve_access_profile("Bearer companion-secret")

    assert owner is not None
    assert companion is not None
    assert owner.profile_id == "owner"
    assert companion.profile_id == "companion"
    assert gateway.resolve_access_profile("Bearer nope") is None


@pytest.mark.skipif(TestClient is None, reason="fastapi test client not installed")
def test_owner_issue_listing_requires_owner_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HALEXT_ISSUE_REPORT_DIR", str(tmp_path))
    _persist_issue_report(
        {
            "issueType": "app-bug",
            "severity": "high",
            "reportBody": "Crash in owner mode",
            "threadTitle": "ops",
        }
    )

    async def fake_startup(self: HalextCloudGateway) -> None:
        self._access_profiles = (
            AccessProfile(profile_id="owner", token="owner-secret"),
            AccessProfile(
                profile_id="companion",
                token="companion-secret",
                allowed_public_ids=frozenset({"scawfulbot-qwen3"}),
            ),
        )

    async def fake_shutdown(self: HalextCloudGateway) -> None:
        return None

    monkeypatch.setattr(HalextCloudGateway, "startup", fake_startup)
    monkeypatch.setattr(HalextCloudGateway, "shutdown", fake_shutdown)

    with TestClient(create_app()) as client:
        forbidden = client.get(
            "/api/v1/scawfulbot/issues",
            headers={"Authorization": "Bearer companion-secret"},
        )
        assert forbidden.status_code == 403

        allowed = client.get(
            "/api/v1/scawfulbot/issues",
            headers={"Authorization": "Bearer owner-secret"},
        )
        assert allowed.status_code == 200
        payload = allowed.json()
        assert payload["count"] == 1
        assert payload["reports"][0]["preview"] == "Crash in owner mode"


@pytest.mark.skipif(TestClient is None, reason="fastapi test client not installed")
def test_owner_status_exposes_security_checks_and_admin_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HALEXT_ISSUE_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("HALEXT_ADMIN_API_TOKEN", "admin-token")
    _persist_issue_report(
        {
            "issueType": "model-behavior",
            "severity": "medium",
            "reportBody": "Model routed wrong",
            "threadTitle": "routing",
        }
    )

    async def fake_startup(self: HalextCloudGateway) -> None:
        self._access_profiles = (
            AccessProfile(profile_id="owner", token="owner-secret"),
            AccessProfile(
                profile_id="companion",
                token="companion-secret",
                allowed_public_ids=frozenset({"scawfulbot-qwen3"}),
            ),
        )

    async def fake_shutdown(self: HalextCloudGateway) -> None:
        return None

    monkeypatch.setattr(HalextCloudGateway, "startup", fake_startup)
    monkeypatch.setattr(HalextCloudGateway, "shutdown", fake_shutdown)
    monkeypatch.setattr(
        "afs_scawful.halext_cloud_gateway._halext_admin_request",
        lambda method, path, payload=None: (
            200,
            {
                "hostname": "halext-nj",
                "services": [{"name": "nginx", "status": "active", "last_checked": "2026-04-17T20:00:00Z"}],
            },
        ),
    )

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/v1/scawfulbot/owner/status",
            headers={"Authorization": "Bearer owner-secret"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["issueCount"] == 1
        assert payload["admin"]["configured"] is True
        assert payload["admin"]["serverStatus"]["hostname"] == "halext-nj"
        check_codes = {row["code"] for row in payload["securityChecks"]}
        assert "split_tokens" in check_codes
        assert payload["recentIssues"][0]["issueType"] == "model-behavior"


@pytest.mark.skipif(TestClient is None, reason="fastapi test client not installed")
def test_owner_service_action_only_allows_safe_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, str] | None]] = []

    async def fake_startup(self: HalextCloudGateway) -> None:
        self._access_profiles = (AccessProfile(profile_id="owner", token="owner-secret"),)

    async def fake_shutdown(self: HalextCloudGateway) -> None:
        return None

    monkeypatch.setenv("HALEXT_ADMIN_API_TOKEN", "admin-token")
    monkeypatch.setattr(HalextCloudGateway, "startup", fake_startup)
    monkeypatch.setattr(HalextCloudGateway, "shutdown", fake_shutdown)

    def fake_admin_request(method: str, path: str, payload: dict[str, str] | None = None) -> tuple[int, object]:
        calls.append((method, path, payload))
        return 200, {"service": "nginx", "status": "reloaded"}

    monkeypatch.setattr("afs_scawful.halext_cloud_gateway._halext_admin_request", fake_admin_request)

    with TestClient(create_app()) as client:
        bad = client.post(
            "/api/v1/scawfulbot/owner/services/nginx/action",
            headers={"Authorization": "Bearer owner-secret"},
            json={"action": "stop"},
        )
        assert bad.status_code == 400

        good = client.post(
            "/api/v1/scawfulbot/owner/services/nginx/action",
            headers={"Authorization": "Bearer owner-secret"},
            json={"action": "reload"},
        )
        assert good.status_code == 200
        assert calls == [("POST", "services/nginx/action", {"action": "reload"})]


@pytest.mark.skipif(TestClient is None, reason="fastapi test client not installed")
def test_owner_status_includes_windows_host_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    issue_dir = tmp_path / "issues"
    issue_dir.mkdir()
    monkeypatch.setenv("HALEXT_GATEWAY_ISSUE_REPORT_DIR", str(issue_dir))
    monkeypatch.setenv("HALEXT_WINDOWS_HOSTD_URL", "http://medical-mechanica:8766")
    monkeypatch.setenv("HALEXT_WINDOWS_TRAINING_TASK", "qwen35-oracle-fast-v2")
    monkeypatch.setenv("HALEXT_WINDOWS_TRAINING_CONFIG", "configs/zelda/qwen35_oracle_fast_v2.toml")

    async def fake_startup(self: HalextCloudGateway) -> None:
        self._access_profiles = (AccessProfile(profile_id="owner", token="owner-secret"),)

    async def fake_shutdown(self: HalextCloudGateway) -> None:
        return None

    monkeypatch.setattr(HalextCloudGateway, "startup", fake_startup)
    monkeypatch.setattr(HalextCloudGateway, "shutdown", fake_shutdown)

    def fake_windows_request(method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        assert method == "GET"
        assert payload is None
        if path == "/healthz":
            return {"ok": True, "service": "afs-hostd"}
        if path == "/v1/status":
            return {"host": "medical-mechanica", "implemented_surfaces": ["vllm.start", "training.start"]}
        if path.startswith("/v1/wsl/status?"):
            return {"distro": "Ubuntu", "nvidia_smi": {"ok": True, "stdout": "NVIDIA GeForce RTX 5090, 32607 MiB"}}
        if path.startswith("/v1/wsl/envs?"):
            return {"venvs": [{"name": "text-serve", "exists": True}, {"name": "src-training", "exists": True}]}
        if path.startswith("/v1/vllm/status?"):
            return {"state": "running", "url": "http://127.0.0.1:8008", "served_name": "scawfulbot-qwen3-8b-v1"}
        if path.startswith("/v1/training/status?"):
            return {"state": "stopped", "task": "qwen35-oracle-fast-v2"}
        raise AssertionError(f"unexpected hostd path: {path}")

    monkeypatch.setattr("afs_scawful.halext_cloud_gateway._windows_host_request", fake_windows_request)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/v1/scawfulbot/owner/status",
            headers={"Authorization": "Bearer owner-secret"},
        )

    assert response.status_code == 200
    payload = response.json()
    windows = payload["windowsHost"]
    assert windows["configured"] is True
    assert windows["baseUrl"] == "http://medical-mechanica:8766"
    assert windows["hostdHealth"]["ok"] is True
    assert windows["hostStatus"]["host"] == "medical-mechanica"
    assert windows["wslStatus"]["nvidia_smi"]["stdout"].startswith("NVIDIA GeForce RTX 5090")
    assert windows["vllm"]["state"] == "running"
    assert windows["training"]["task"] == "qwen35-oracle-fast-v2"
    assert windows["targets"]["training"]["configured"] is True
    assert windows["allowedActions"]["vllm"] == ["start", "stop"]


@pytest.mark.skipif(TestClient is None, reason="fastapi test client not installed")
def test_owner_windows_action_proxies_to_hostd(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []
    monkeypatch.setenv("HALEXT_WINDOWS_HOSTD_URL", "http://medical-mechanica:8766")
    monkeypatch.setenv("HALEXT_WINDOWS_TRAINING_TASK", "qwen35-oracle-fast-v2")
    monkeypatch.setenv("HALEXT_WINDOWS_TRAINING_CONFIG", "configs/zelda/qwen35_oracle_fast_v2.toml")

    async def fake_startup(self: HalextCloudGateway) -> None:
        self._access_profiles = (AccessProfile(profile_id="owner", token="owner-secret"),)

    async def fake_shutdown(self: HalextCloudGateway) -> None:
        return None

    monkeypatch.setattr(HalextCloudGateway, "startup", fake_startup)
    monkeypatch.setattr(HalextCloudGateway, "shutdown", fake_shutdown)

    def fake_windows_request(method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        calls.append((method, path, payload))
        return {"state": "running" if path.endswith("/start") else "stopped"}

    monkeypatch.setattr("afs_scawful.halext_cloud_gateway._windows_host_request", fake_windows_request)

    with TestClient(create_app()) as client:
        vllm = client.post(
            "/api/v1/scawfulbot/owner/windows/vllm/start",
            headers={"Authorization": "Bearer owner-secret"},
        )
        training = client.post(
            "/api/v1/scawfulbot/owner/windows/training/stop",
            headers={"Authorization": "Bearer owner-secret"},
        )

    assert vllm.status_code == 200
    assert training.status_code == 200
    assert calls[0][0:2] == ("POST", "/v1/vllm/start")
    assert calls[0][2] == {
        "distro": "Ubuntu",
        "model": "/mnt/d/models/scawful/scawfulbot-qwen3-8b-v1",
        "host": "127.0.0.1",
        "port": 8008,
        "served_name": "scawfulbot-qwen3-8b-v1",
        "max_model_len": 4096,
    }
    assert calls[1] == (
        "POST",
        "/v1/training/stop",
        {
            "distro": "Ubuntu",
            "task": "qwen35-oracle-fast-v2",
            "config": "configs/zelda/qwen35_oracle_fast_v2.toml",
        },
    )


class _DummyProviderClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def chat(self, **kwargs: object) -> object:
        self.kwargs = dict(kwargs)
        return SimpleNamespace(
            text="OK",
            model=str(kwargs["model"]),
            prompt="[]",
            latency_ms=0.0,
            tokens_generated=1,
            done=True,
            error="",
        )


def test_google_route_enforces_minimum_token_budget() -> None:
    async def run() -> None:
        gateway = HalextCloudGateway()
        client = _DummyProviderClient()
        gateway._clients = {"google": client}  # type: ignore[assignment]

        route = resolve_model_spec("gemini-2.5-pro")
        response = await gateway._chat_provider(
            route=route,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            system_text="",
            temperature=0.2,
            top_p=0.9,
            max_tokens=24,
        )

        assert response.text == "OK"
        assert client.kwargs is not None
        assert client.kwargs["max_tokens"] == 256

    asyncio.run(run())


def test_chat_retries_next_lmstudio_backend_on_provider_error(monkeypatch) -> None:
    async def run() -> None:
        gateway = HalextCloudGateway()
        gateway._catalog = load_gateway_model_specs()
        gateway._priority = build_default_priority(gateway._catalog)
        gateway._access_profiles = (AccessProfile(profile_id="owner", token="owner-secret"),)
        snap = _snapshot(
            lmstudio=("scawfulbot-qwen3-8b-v1-mlx",),
            lmstudio_win=("scawfulbot-qwen3-8b-v1",),
        )

        async def fake_snapshot(force: bool = False) -> AvailabilitySnapshot:
            return snap

        calls: list[str] = []

        async def fake_chat_provider(
            *,
            route: object,
            messages: list[dict[str, str]],
            system_text: str,
            temperature: float,
            top_p: float,
            max_tokens: int,
        ) -> object:
            provider_model = getattr(route, "provider_model", "")
            calls.append(str(provider_model))
            if getattr(route, "provider", "") == "lmstudio":
                return SimpleNamespace(
                    text="",
                    model=provider_model,
                    prompt="[]",
                    latency_ms=0.0,
                    tokens_generated=0,
                    done=True,
                    error="HTTP 502: upstream",
                )
            return SimpleNamespace(
                text="from-windows",
                model=provider_model,
                prompt="[]",
                latency_ms=1.0,
                tokens_generated=2,
                done=True,
                error="",
            )

        monkeypatch.setattr(gateway, "availability_snapshot", fake_snapshot)
        monkeypatch.setattr(gateway, "_chat_provider", fake_chat_provider)

        request = SimpleNamespace(
            model="scawfulbot-qwen3",
            messages=[ChatMessageRow(role="user", content="hi")],
            temperature=0.2,
            top_p=0.9,
            max_tokens=24,
        )
        payload, routed = await gateway.chat(request, gateway._access_profiles[0])
        assert routed == "scawfulbot-qwen3"
        assert len(calls) == 2
        assert "mlx" in calls[0]
        assert calls[1] == "scawfulbot-qwen3-8b-v1"
        choices = cast(list[dict[str, object]], payload["choices"])
        assert cast(dict[str, object], choices[0]["message"])["content"] == "from-windows"

    asyncio.run(run())


def test_chat_preserves_provider_reasoning_content(monkeypatch) -> None:
    async def run() -> None:
        gateway = HalextCloudGateway()
        gateway._catalog = load_gateway_model_specs()
        gateway._priority = build_default_priority(gateway._catalog)
        gateway._access_profiles = (AccessProfile(profile_id="owner", token="owner-secret"),)
        snap = _snapshot(lmstudio_win=("scawfulbot-qwen35-v1-sft-q5_k_m",))

        async def fake_snapshot(force: bool = False) -> AvailabilitySnapshot:
            return snap

        async def fake_chat_provider(
            *,
            route: object,
            messages: list[dict[str, str]],
            system_text: str,
            temperature: float,
            top_p: float,
            max_tokens: int,
        ) -> object:
            return SimpleNamespace(
                text="OK",
                model=getattr(route, "provider_model", ""),
                prompt="[]",
                latency_ms=1.0,
                tokens_generated=2,
                done=True,
                error="",
                reasoning_content="thinking",
            )

        monkeypatch.setattr(gateway, "availability_snapshot", fake_snapshot)
        monkeypatch.setattr(gateway, "_chat_provider", fake_chat_provider)

        request = SimpleNamespace(
            model="scawfulbot-qwen35",
            messages=[ChatMessageRow(role="user", content="hi")],
            temperature=0.2,
            top_p=0.9,
            max_tokens=24,
        )
        payload, routed = await gateway.chat(request, gateway._access_profiles[0])
        assert routed == "scawfulbot-qwen35"
        choices = cast(list[dict[str, object]], payload["choices"])
        message = cast(dict[str, object], choices[0]["message"])
        assert message["content"] == "OK"
        assert message["reasoning_content"] == "thinking"

    asyncio.run(run())


def test_companion_profile_rejects_disallowed_explicit_model() -> None:
    async def run() -> None:
        gateway = HalextCloudGateway()
        gateway._catalog = load_gateway_model_specs()
        gateway._priority = build_default_priority(gateway._catalog)
        gateway._snapshot = _snapshot(
            openai=("gpt-5.2",),
            google=("models/gemini-3-flash-preview", "models/gemini-3.1-pro-preview"),
            anthropic=("claude-sonnet-4-6",),
        )
        companion = AccessProfile(
            profile_id="companion",
            token="companion-secret",
            allowed_public_ids=frozenset({"gemini-3-flash", "gemini-3.1-pro", "claude-sonnet-4.6"}),
        )
        request = SimpleNamespace(
            model="gpt-5.2",
            messages=[ChatMessageRow(role="user", content="Reply with exactly: OK")],
            temperature=0.2,
            top_p=0.9,
            max_tokens=24,
        )

        with pytest.raises(PermissionError):
            await gateway.chat(request, companion)

    asyncio.run(run())
