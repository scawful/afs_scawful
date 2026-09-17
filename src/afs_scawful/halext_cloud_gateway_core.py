"""Core helpers for the halext.org cloud inference gateway."""

from __future__ import annotations

import json
import os
import re
import time
import tomllib
import uuid
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from pathlib import Path
from typing import Literal

ProviderName = Literal["openai", "anthropic", "google", "lmstudio", "lmstudio_win"]


@dataclass(frozen=True)
class GatewayModelSpec:
    """Public model exposed by the halext cloud gateway."""

    public_id: str
    provider: ProviderName
    provider_model: str
    display_name: str
    aliases: tuple[str, ...] = ()
    openai_api_mode: str | None = None
    description: str = ""
    append_to_last_user_message: str = ""
    fallback_backends: tuple["GatewayModelBackend", ...] = ()
    # Names clients may request that must NEVER count as evidence these weights are present.
    # `aliases` does both jobs for legacy specs, which is how a short alias such as "scawfulbot"
    # could match a box's "scawfulbot-gemma4-...gguf" and serve a lane under the wrong weights.
    request_aliases: tuple[str, ...] = ()
    # Manifest lanes pin the host and file hash. Legacy/cloud specs leave both unset.
    host: str | None = None
    sha256: str | None = None
    # Legacy specs historically exposed provider IDs as request aliases. Manifest lanes keep
    # backend evidence private so a filename can never become another lane's public request ID.
    expose_backend_ids: bool = True

    def backend_ids(self) -> tuple[str, ...]:
        candidates: list[str] = []
        for backend in self.backends():
            candidates.extend((backend.provider_model, *backend.aliases))
        return tuple(candidates)

    def all_ids(self) -> tuple[str, ...]:
        candidates = [self.public_id, *self.request_aliases]
        if self.expose_backend_ids:
            candidates.extend(self.backend_ids())
        return tuple(candidates)

    def backends(self) -> tuple["GatewayModelBackend", ...]:
        return (
            GatewayModelBackend(
                provider=self.provider,
                provider_model=self.provider_model,
                aliases=self.aliases,
                host=self.host,
                sha256=self.sha256,
            ),
            *self.fallback_backends,
        )

    def live_route(self, snapshot: "AvailabilitySnapshot") -> "GatewayModelSpec | None":
        for backend in self.backends():
            provider_state = snapshot.providers.get(backend.provider)
            if not _backend_matches_provider_snapshot(backend, provider_state):
                continue
            resolved_model = (
                _resolve_lmstudio_chat_model_id(backend, provider_state)
                if backend.provider in ("lmstudio", "lmstudio_win")
                else backend.provider_model
            )
            if (
                backend.provider == self.provider
                and backend.provider_model == self.provider_model
                and backend.aliases == self.aliases
            ):
                if resolved_model == self.provider_model:
                    return self
                return replace(self, provider_model=resolved_model)
            return replace(
                self,
                provider=backend.provider,
                provider_model=resolved_model,
                aliases=backend.aliases,
                host=backend.host,
                sha256=backend.sha256,
            )
        return None


@dataclass(frozen=True)
class GatewayModelBackend:
    """Alternate upstream that can satisfy the same public model ID."""

    provider: ProviderName
    provider_model: str
    aliases: tuple[str, ...] = ()
    host: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class ProviderAvailability:
    """Availability snapshot for one upstream provider."""

    healthy: bool
    models: tuple[str, ...]
    error: str | None = None
    host: str | None = None
    model_sha256: dict[str, str] = field(default_factory=dict)
    identity_error: str | None = None


@dataclass(frozen=True)
class AvailabilitySnapshot:
    """Gateway-wide provider availability."""

    created: float
    providers: dict[ProviderName, ProviderAvailability]


_QUANT_SUFFIX = re.compile(r"[-@](?P<quant>i?q\d[a-z0-9_]*|f16|f32|bf16)$", re.IGNORECASE)


def _strip_quant_suffix(name: str) -> str:
    """"model-q4_k_m.gguf" -> "model". Only recognised quant tags are stripped."""
    stem = name[:-5] if name.endswith(".gguf") else name
    return _QUANT_SUFFIX.sub("", stem)


def _quant_from_model_id(name: str) -> str | None:
    """Return a recognised quant from either `model@q8_0` or `model-q8_0.gguf`."""
    normalized = _normalize_model_id(name).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = normalized[:-5] if normalized.endswith(".gguf") else normalized
    match = _QUANT_SUFFIX.search(stem)
    return match.group("quant").lower() if match else None


def _lmstudio_raw_id_matches_candidate(raw_id: str, candidate: str) -> bool:
    """Match LM Studio model ids that may be path- or quant-suffixed (Windows / Medical Mechanica)."""

    lid = _normalize_model_id(raw_id)
    cand = _normalize_model_id(candidate)
    if not cand:
        return False
    if lid == cand:
        return True
    # LM Studio relabels a model as "name@quant" the moment a second quant of it exists. Compare the
    # base name, and when both sides state a quant they must agree: a q5 build is not the q8 weights.
    raw_base, _, raw_quant = lid.partition("@")
    cand_base, _, cand_quant = cand.partition("@")
    if raw_base == cand_base and raw_quant and not cand_quant:
        return True
    if raw_quant and cand_quant and (raw_base, raw_quant) != (cand_base, cand_quant):
        return False
    # Avoid loose suffix matches on very short slugs.
    min_len = 10
    if len(cand) < min_len:
        return lid.endswith("/" + cand) or lid.endswith("\\" + cand)
    # Path suffixes only. A bare endswith let any id ending in an alias bind to that lane, e.g.
    # "some-other-lmstudio@q5_k_m" satisfying the alias "lmstudio@q5_k_m".
    if lid.endswith("/" + cand) or lid.endswith("\\" + cand):
        return True
    base = lid.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    b = _normalize_model_id(base)
    if b == cand:
        return True
    # A filename may carry its quant as a suffix ("…-q4_k_m.gguf") rather than "@q4_k_m". Strip a
    # recognised quant and compare exactly; anything else after the name is a different model.
    if _strip_quant_suffix(b) == cand:
        return True
    # No prefix matching: "scawfulbot-qwen3-8b-v1" must not be satisfied by a differently trained
    # "scawfulbot-qwen3-8b-v1-dpo", and a short alias must not swallow a whole family.
    return False


def _lmstudio_match_rank(raw_id: str, candidate: str) -> int:
    """0 no match, 1 base-only, 2 the quant agrees (or neither side states one).

    A box lists every quant it holds: asking for "qwen35-v1-dpo" while it serves both
    "@q5_k_m" and "@q8_0" must not take whichever comes first in its list.
    """
    if not _lmstudio_raw_id_matches_candidate(raw_id, candidate):
        return 0
    _, _, raw_quant = _normalize_model_id(raw_id).partition("@")
    _, _, cand_quant = _normalize_model_id(candidate).partition("@")
    return 1 if raw_quant and not cand_quant else 2


def _normalized_host(value: str | None) -> str:
    return (value or "").strip().lower().split(".", 1)[0]


def _model_sha256(state: ProviderAvailability, raw_id: str) -> str | None:
    for key in (raw_id, raw_id.lower(), _normalize_model_id(raw_id)):
        value = state.model_sha256.get(key)
        if value:
            return value.lower()
    wanted = _normalize_model_id(raw_id)
    for key, value in state.model_sha256.items():
        if _normalize_model_id(key) == wanted:
            return value.lower()
    return None


def _backend_identity_matches(
    raw_id: str,
    backend: GatewayModelBackend,
    state: ProviderAvailability,
) -> bool:
    if backend.host and _normalized_host(backend.host) != _normalized_host(state.host):
        return False
    if not backend.sha256:
        return True
    measured = _model_sha256(state, raw_id)
    # Exact equality: a prefix comparison accepts any file sharing those leading hex digits, and the
    # whole point of pinning by hash is that only these bytes may answer for this lane.
    return measured is not None and measured == backend.sha256.lower()


def _lmstudio_backend_match_rank(
    raw_id: str,
    backend: GatewayModelBackend,
    state: ProviderAvailability | None = None,
) -> int:
    candidates = (backend.provider_model, *backend.aliases)
    declared_quants = {
        quant for candidate in candidates
        if (quant := _quant_from_model_id(candidate)) is not None
    }
    raw_quant = _quant_from_model_id(raw_id)
    if raw_quant and declared_quants and raw_quant not in declared_quants:
        return 0
    if state is not None and not _backend_identity_matches(raw_id, backend, state):
        return 0
    return max(
        (_lmstudio_match_rank(raw_id, candidate)
         for candidate in candidates),
        default=0,
    )


def _lmstudio_raw_matches_backend(
    raw_id: str,
    backend: GatewayModelBackend,
    state: ProviderAvailability,
) -> bool:
    return _lmstudio_backend_match_rank(raw_id, backend, state) > 0


def _resolve_lmstudio_chat_model_id(backend: GatewayModelBackend, state: ProviderAvailability) -> str:
    best_rank, best_raw = 0, None
    for raw in state.models:
        rank = _lmstudio_backend_match_rank(raw, backend, state)
        if rank > best_rank:
            best_rank, best_raw = rank, raw
    return best_raw if best_raw is not None else backend.provider_model


def _backend_matches_provider_snapshot(
    backend: GatewayModelBackend,
    state: ProviderAvailability | None,
) -> bool:
    if state is None or not state.healthy:
        return False
    if backend.provider in ("lmstudio", "lmstudio_win"):
        return any(_lmstudio_raw_matches_backend(model_id, backend, state) for model_id in state.models)
    if backend.host and _normalized_host(backend.host) != _normalized_host(state.host):
        return False
    live_ids = {_normalize_model_id(model_id) for model_id in state.models}
    candidates = (
        _normalize_model_id(backend.provider_model),
        *(_normalize_model_id(alias) for alias in backend.aliases),
    )
    candidates = tuple(c for c in candidates if c)
    matching = [model_id for model_id in state.models if _normalize_model_id(model_id) in candidates]
    return any(_backend_identity_matches(model_id, backend, state) for model_id in matching)


def ordered_live_route_specs(
    spec: GatewayModelSpec,
    snapshot: AvailabilitySnapshot,
) -> tuple[GatewayModelSpec, ...]:
    """Concrete per-backend routes for chat, in catalog order (Mac lane before Windows fallbacks)."""

    routes: list[GatewayModelSpec] = []
    for backend in spec.backends():
        state = snapshot.providers.get(backend.provider)
        if not _backend_matches_provider_snapshot(backend, state):
            continue
        resolved_model = (
            _resolve_lmstudio_chat_model_id(backend, state)
            if backend.provider in ("lmstudio", "lmstudio_win")
            else backend.provider_model
        )
        routes.append(
            replace(
                spec,
                provider=backend.provider,
                provider_model=resolved_model,
                aliases=backend.aliases,
                host=backend.host,
                sha256=backend.sha256,
            )
        )
    return tuple(routes)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTING_MANIFEST_PATH = Path(
    os.environ.get("HALEXT_ROUTING_MANIFEST_PATH", PROJECT_ROOT / "config/routing_manifest.toml")
).expanduser()
DEFAULT_CHAT_REGISTRY_PATH = PROJECT_ROOT / "config" / "chat_registry.toml"

STATIC_MODEL_SPECS: tuple[GatewayModelSpec, ...] = (
    GatewayModelSpec(
        public_id="scawfulbot-gemma4",
        provider="lmstudio",
        provider_model="gguf/scawful/scawfulbot-gemma4-e4b-sft-dpo-q4km.gguf",
        display_name="Scawfulbot Gemma 4",
        aliases=("scawfulbot-gemma4-e4b-sft-dpo-q4km",),
        description="Mac-hosted Gemma 4 scawfulbot lane via LM Studio.",
        fallback_backends=(
            GatewayModelBackend(
                provider="lmstudio_win",
                provider_model="gguf/lmstudio/scawfulbot-gemma4-e4b-sft-dpo-q4km.gguf",
                aliases=("scawfulbot-gemma4",),
            ),
        ),
    ),
    GatewayModelSpec(
        public_id="scawfulbot-qwen3",
        provider="lmstudio",
        provider_model="scawfulbot-qwen3-8b-v1-mlx",
        aliases=("scawfulbot-qwen3-8b-v1-mlx",),
        display_name="Scawfulbot Qwen 3",
        description="Mac-hosted Qwen 3 scawfulbot lane via LM Studio.",
        append_to_last_user_message=" /no_think",
        fallback_backends=(
            GatewayModelBackend(
                provider="lmstudio_win",
                provider_model="scawfulbot-qwen3-8b-v1",
                aliases=(
                    "scawfulbot-qwen3-8b-v1",
                    "scawfulbot-qwen3-8b-v1-q4_k_m",
                ),
            ),
        ),
    ),
    GatewayModelSpec(
        # Promoted 2026-09-16 after the Claude judge eval: curated+masked SFT passes 47% of cases with
        # the system prompt and 32% without it, against 3% and 0% for the April DPO model it replaces
        # (paired diff +0.45 [+0.33, +0.57]; noise floor is 9 points). The legacy v1-dpo aliases now
        # resolve here on purpose: this is the promoted scawfulbot lane. The old weights stay
        # addressable as scawfulbot-qwen35-v1-dpo-q8 below.
        public_id="scawfulbot-qwen35",
        provider="lmstudio_win",
        provider_model="qwen35-curated-masked",
        aliases=(
            "qwen35-curated-masked",  # medical-mechanica LM Studio key (models/scawfulbot/qwen35-curated-masked/)
            "scawfulbot-qwen35-curated-masked",
            "lmstudio@q5_k_m",
            "scawfulbot-qwen35-v1-dpo",
            "scawfulbot-qwen35-v1-dpo-q5_k_m",
            "scawfulbot-qwen35-v1-sft",
            "scawfulbot-qwen35-v1-sft-q5_k_m",
        ),
        display_name="Scawfulbot Qwen 3.5",
        description="Qwen 3.5 scawfulbot, promoted 2026-09-16 (curated corpus, response-only loss).",
        # No Mac fallback: that box only holds the April weights, and falling back to them would serve
        # a different model under the same name, which is the silent substitution this gateway refuses.
    ),
    GatewayModelSpec(
        public_id="scawfulbot-qwen35-v1-dpo-q8",
        provider="lmstudio_win",
        provider_model="qwen35-v1-dpo@q8_0",
        aliases=("qwen35-v1-dpo@q8_0", "qwen35-v1-dpo"),
        display_name="Scawfulbot Qwen 3.5 (April DPO)",
        description="Superseded 2026-09-16; kept addressable for comparison against the promoted lane.",
    ),
    # -- Windows-hosted Oracle models (medical-mechanica via LM Studio) --
    # Qwen2.5 current fleet (will be replaced by Qwen3 after rebase)
    GatewayModelSpec(
        public_id="oracle-nayru",
        provider="lmstudio_win",
        provider_model="gguf/lmstudio/nayru-v9-q8_0.gguf",
        display_name="Oracle Nayru",
        aliases=("nayru", "nayru-v9"),
        description="Windows-hosted teacher/explainer — routine docs, references, context.",
    ),
    GatewayModelSpec(
        public_id="oracle-din",
        provider="lmstudio_win",
        provider_model="gguf/lmstudio/din-v4.gguf",
        display_name="Oracle Din",
        aliases=("din", "din-v4"),
        description="Windows-hosted optimization specialist — code perf, ASM hot paths.",
    ),
    GatewayModelSpec(
        public_id="oracle-farore",
        provider="lmstudio_win",
        provider_model="gguf/lmstudio/farore-v5-q8_0.gguf",
        display_name="Oracle Farore",
        aliases=("farore", "farore-v5"),
        description="Windows-hosted fast debugger — room inspection, breakpoints, diagnostics.",
    ),
    GatewayModelSpec(
        public_id="oracle-veran",
        provider="lmstudio_win",
        provider_model="gguf/lmstudio/veran-v4.gguf",
        display_name="Oracle Veran",
        aliases=("veran", "veran-v4"),
        description="Windows-hosted deep analysis — cross-system investigation.",
    ),
    GatewayModelSpec(
        public_id="oracle-majora",
        provider="lmstudio_win",
        provider_model="gguf/lmstudio/majora-v2-q8_0.gguf",
        display_name="Oracle Majora",
        aliases=("majora", "majora-v2"),
        description="Windows-hosted architecture specialist — subsystems, cross-references.",
    ),
    GatewayModelSpec(
        public_id="gemini-2.5-pro",
        provider="google",
        provider_model="models/gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        aliases=("gemini-2.5-pro",),
        description="Google reasoning and long-context synthesis model.",
    ),
    GatewayModelSpec(
        public_id="gemini-3-pro",
        provider="google",
        provider_model="models/gemini-3-pro-preview",
        display_name="Gemini 3 Pro",
        aliases=("gemini-3-pro-preview",),
        description="High-capability Gemini cloud analysis model.",
    ),
    GatewayModelSpec(
        public_id="gemini-3.1-pro",
        provider="google",
        provider_model="models/gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro",
        aliases=("gemini-3.1-pro-preview",),
        description="Primary partner-safe reasoning model.",
    ),
    GatewayModelSpec(
        public_id="gemini-3-flash",
        provider="google",
        provider_model="models/gemini-3-flash-preview",
        display_name="Gemini 3 Flash",
        aliases=("gemini-3-flash-preview",),
        description="Fast lightweight companion model.",
    ),
    GatewayModelSpec(
        public_id="claude-sonnet-4.6",
        provider="anthropic",
        provider_model="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        aliases=("claude-sonnet-4-6",),
        description="High quality Anthropic fallback.",
    ),
    GatewayModelSpec(
        public_id="claude-sonnet-4.5",
        provider="anthropic",
        provider_model="sonnet-4.5",
        display_name="Claude Sonnet 4.5",
        aliases=("sonnet-4.5",),
        description="Balanced Anthropic reasoning and code assistance model.",
    ),
    GatewayModelSpec(
        public_id="claude-opus-4.5",
        provider="anthropic",
        provider_model="opus-4.5",
        display_name="Claude Opus 4.5",
        aliases=("opus-4.5",),
        description="Deep Anthropic reasoning and high-accuracy writing model.",
    ),
    GatewayModelSpec(
        public_id="claude-opus-4.6",
        provider="anthropic",
        provider_model="claude-opus-4-6",
        display_name="Claude Opus 4.6",
        aliases=("opus-4.6", "claude-opus-4-6"),
        description="Premium Anthropic distillation and reasoning reference.",
    ),
    GatewayModelSpec(
        public_id="claude-haiku-4.5",
        provider="anthropic",
        provider_model="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        aliases=("claude-haiku-4-5", "claude-haiku-4-5-20251001"),
        description="Fast Anthropic fallback.",
    ),
    GatewayModelSpec(
        public_id="gpt-5",
        provider="openai",
        provider_model="gpt-5",
        display_name="GPT-5",
        aliases=("gpt-5",),
        openai_api_mode="responses",
        description="OpenAI reasoning model.",
    ),
    GatewayModelSpec(
        public_id="gpt-5.4",
        provider="openai",
        provider_model="gpt-5.4",
        display_name="GPT-5.4",
        aliases=("gpt-5.4",),
        openai_api_mode="responses",
        description="OpenAI frontier reasoning model.",
    ),
    GatewayModelSpec(
        public_id="gpt-5.2",
        provider="openai",
        provider_model="gpt-5.2",
        display_name="GPT-5.2",
        aliases=("gpt-5.2",),
        openai_api_mode="responses",
        description="OpenAI generalist reasoning and tool workflow model.",
    ),
    GatewayModelSpec(
        public_id="gpt-5-mini",
        provider="openai",
        provider_model="gpt-5-mini",
        display_name="GPT-5 Mini",
        aliases=("gpt-5-mini",),
        openai_api_mode="responses",
        description="Fast OpenAI fallback.",
    ),
    GatewayModelSpec(
        public_id="codex-5.3",
        provider="openai",
        provider_model="codex-5.3",
        display_name="Codex 5.3",
        aliases=("codex-5.3",),
        openai_api_mode="responses",
        description="OpenAI coding-specialist model.",
    ),
)

PRIORITY_PREFERRED_IDS: tuple[str, ...] = (
    "gemini-3.1-pro",
    "gemini-2.5-pro",
    "gemini-3-pro",
    "gemini-3-flash",
    "claude-sonnet-4.6",
    "claude-sonnet-4.5",
    "claude-opus-4.6",
    "claude-opus-4.5",
    "claude-haiku-4.5",
    "gpt-5",
    "gpt-5.4",
    "gpt-5.2",
    "gpt-5-mini",
    "codex-5.3",
    "scawfulbot-gemma4",
    "scawfulbot-qwen35",
    "scawfulbot-qwen3",
    "oracle-nayru",
    "oracle-din",
    "oracle-farore",
    "oracle-veran",
    "oracle-majora",
)


def _normalize_model_id(value: str) -> str:
    return value.strip().lower()


def _normalize_registry_provider(value: str) -> ProviderName | None:
    normalized = value.strip().lower()
    if normalized == "gemini":
        return "google"
    if normalized == "openai":
        return "openai"
    if normalized == "anthropic":
        return "anthropic"
    return None


def _humanize_public_id(public_id: str) -> str:
    if public_id.startswith("claude-"):
        label = public_id.replace("claude-", "Claude ", 1)
    elif public_id.startswith("gemini-"):
        label = public_id.replace("gemini-", "Gemini ", 1)
    elif public_id.startswith("gpt-"):
        label = public_id.replace("gpt-", "GPT-", 1)
    elif public_id.startswith("codex-"):
        label = public_id.replace("codex-", "Codex ", 1)
    else:
        label = public_id.replace("-", " ")
    parts = [part.upper() if part.isupper() else part.capitalize() for part in label.split("-")]
    return " ".join(parts)


def _canonical_public_id(provider: ProviderName, name: str, model_id: str) -> str:
    cleaned_name = name.strip()
    cleaned_model_id = model_id.strip()
    if provider == "google":
        if cleaned_name == "gemini-3-flash-preview":
            return "gemini-3-flash"
        if cleaned_name == "gemini-3-pro-preview":
            return "gemini-3-pro"
        return cleaned_name or cleaned_model_id.removeprefix("models/")
    if provider == "anthropic":
        if cleaned_name.startswith("claude-"):
            return cleaned_name
        if cleaned_name.startswith(("sonnet-", "opus-", "haiku-")):
            return f"claude-{cleaned_name}"
        if cleaned_model_id.startswith("claude-"):
            dotted = cleaned_model_id.replace("-4-6", "-4.6").replace("-4-5", "-4.5")
            return dotted
        return cleaned_name or cleaned_model_id
    return cleaned_name or cleaned_model_id


def _registry_aliases(provider: ProviderName, public_id: str, name: str, model_id: str) -> tuple[str, ...]:
    aliases: list[str] = []
    for candidate in (name, model_id):
        cleaned = candidate.strip()
        if cleaned and cleaned.lower() != public_id.lower():
            aliases.append(cleaned)
    if provider == "google" and model_id.startswith("models/"):
        stripped = model_id.split("/", 1)[1]
        if stripped.lower() != public_id.lower():
            aliases.append(stripped)
    if provider == "anthropic" and public_id.startswith("claude-"):
        without_prefix = public_id.removeprefix("claude-")
        if without_prefix.lower() != public_id.lower():
            aliases.append(without_prefix)
    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = alias.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(alias)
    return tuple(deduped)


def _merge_specs(specs: list[GatewayModelSpec]) -> tuple[GatewayModelSpec, ...]:
    merged: dict[str, GatewayModelSpec] = {}
    for spec in specs:
        key = _normalize_model_id(spec.public_id)
        existing = merged.get(key)
        if existing is None:
            merged[key] = spec
            continue
        # A manifest lane is authoritative. Registry/static metadata must not add requestable
        # aliases or discard its host/hash identity merely because the public IDs coincide.
        if not existing.expose_backend_ids:
            continue
        if not spec.expose_backend_ids:
            merged[key] = spec
            continue
        aliases: list[str] = []
        seen: set[str] = set()
        for alias in (*existing.aliases, *spec.aliases):
            normalized = alias.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            aliases.append(alias)
        request_aliases: list[str] = []
        seen_requests: set[str] = set()
        for alias in (*existing.request_aliases, *spec.request_aliases):
            normalized = alias.lower()
            if normalized in seen_requests:
                continue
            seen_requests.add(normalized)
            request_aliases.append(alias)
        merged[key] = replace(
            existing,
            display_name=existing.display_name or spec.display_name,
            aliases=tuple(aliases),
            openai_api_mode=existing.openai_api_mode or spec.openai_api_mode,
            description=existing.description or spec.description,
            append_to_last_user_message=(
                existing.append_to_last_user_message or spec.append_to_last_user_message
            ),
            request_aliases=tuple(request_aliases),
        )
    return tuple(merged.values())


def _validate_request_namespace(specs: tuple[GatewayModelSpec, ...]) -> None:
    owners: dict[str, str] = {}
    for spec in specs:
        for request_id in spec.all_ids():
            normalized = _normalize_model_id(request_id)
            owner = owners.get(normalized)
            if owner is not None and owner != spec.public_id:
                raise ValueError(
                    f"model id {request_id!r} is claimed by both {owner!r} and {spec.public_id!r}"
                )
            owners[normalized] = spec.public_id


def load_registry_model_specs(registry_path: Path | None = None) -> tuple[GatewayModelSpec, ...]:
    path = registry_path or DEFAULT_CHAT_REGISTRY_PATH
    if not path.exists():
        return ()
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("models", [])
    if not isinstance(rows, list):
        return ()

    specs: list[GatewayModelSpec] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        provider = _normalize_registry_provider(str(row.get("provider", "")))
        if provider is None:
            continue
        name = str(row.get("name", "")).strip()
        model_id = str(row.get("model_id", "")).strip()
        if not name or not model_id:
            continue
        public_id = _canonical_public_id(provider, name, model_id)
        specs.append(
            GatewayModelSpec(
                public_id=public_id,
                provider=provider,
                provider_model=model_id if provider != "google" or model_id.startswith("models/") else f"models/{model_id}",
                display_name=_humanize_public_id(public_id),
                aliases=_registry_aliases(provider, public_id, name, model_id),
                openai_api_mode=(
                    "responses"
                    if provider == "openai" and (public_id.startswith("gpt-5") or public_id.startswith("codex-5"))
                    else None
                ),
                description=str(row.get("role", "")).strip(),
            )
        )
    return tuple(specs)


def load_gateway_model_specs(
    registry_path: Path | None = None,
    manifest_path: Path | None = None,
) -> tuple[GatewayModelSpec, ...]:
    """Catalog order: routing manifest, then static specs, then the chat registry.

    Manifest lanes come first so they win `resolve_model_spec`, which takes the first spec claiming
    an id. A static spec whose public_id or aliases a lane already claims is dropped entirely: two
    specs fishing in one name space is how a request for the promoted lane could land on the weights
    it replaced.
    """
    from .routing_manifest import load_manifest, manifest_specs

    # A broken manifest raises ManifestError here rather than silently falling back to stale routing.
    path = manifest_path or DEFAULT_ROUTING_MANIFEST_PATH
    lane_specs: tuple[GatewayModelSpec, ...] = manifest_specs(load_manifest(path))
    # Reserve backend evidence as well as public request IDs. Evidence is deliberately not
    # requestable, and a legacy/static spec must not make it requestable again.
    reserved = {
        _normalize_model_id(model_id)
        for spec in lane_specs
        for model_id in (*spec.all_ids(), *spec.backend_ids())
    }
    legacy = [
        spec for spec in (*STATIC_MODEL_SPECS, *load_registry_model_specs(registry_path))
        if not reserved.intersection(_normalize_model_id(model_id) for model_id in spec.all_ids())
    ]
    catalog = _merge_specs([*lane_specs, *legacy])
    _validate_request_namespace(catalog)
    return catalog


def build_default_priority(catalog: tuple[GatewayModelSpec, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for public_id in PRIORITY_PREFERRED_IDS:
        if public_id in seen:
            continue
        if any(spec.public_id == public_id for spec in catalog):
            seen.add(public_id)
            ordered.append(public_id)
    for spec in catalog:
        if spec.public_id in seen:
            continue
        seen.add(spec.public_id)
        ordered.append(spec.public_id)
    return tuple(ordered)


DEFAULT_MODEL_SPECS: tuple[GatewayModelSpec, ...] = load_gateway_model_specs()
DEFAULT_PRIORITY: tuple[str, ...] = build_default_priority(DEFAULT_MODEL_SPECS)


def resolve_model_spec(
    requested_model: str,
    catalog: tuple[GatewayModelSpec, ...] = DEFAULT_MODEL_SPECS,
) -> GatewayModelSpec | None:
    """Resolve a public or provider model identifier to a gateway spec."""

    requested = _normalize_model_id(requested_model)
    if not requested:
        return None
    for spec in catalog:
        if any(_normalize_model_id(candidate) == requested for candidate in spec.all_ids()):
            return spec
    return None


def extract_system_and_messages(
    messages: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    """Split OpenAI-style messages into one system prompt plus chat history."""

    system_parts: list[str] = []
    chat_messages: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
            continue
        if role not in {"user", "assistant"}:
            continue
        chat_messages.append({"role": role, "content": content})
    return "\n\n".join(system_parts), chat_messages


def _merge_consecutive_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for message in messages:
        role = message["role"]
        content = message["content"]
        if merged and merged[-1]["role"] == role:
            merged[-1]["content"] = f"{merged[-1]['content']}\n\n{content}"
            continue
        merged.append({"role": role, "content": content})
    return merged


def normalize_messages_for_provider(
    provider: ProviderName,
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Normalize OpenAI-style chat history for a specific provider."""

    if provider == "google":
        normalized = []
        for message in messages:
            role = "model" if message["role"] == "assistant" else "user"
            normalized.append({"role": role, "content": message["content"]})
        return _merge_consecutive_messages(normalized)
    return _merge_consecutive_messages(messages)


def apply_route_message_hints(
    route: GatewayModelSpec,
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Apply route-specific message tweaks before the provider call."""

    if not route.append_to_last_user_message:
        return list(messages)

    updated = [dict(message) for message in messages]
    for index in range(len(updated) - 1, -1, -1):
        if updated[index].get("role") != "user":
            continue
        content = updated[index].get("content", "")
        if route.append_to_last_user_message.strip() in content:
            break
        updated[index]["content"] = f"{content}{route.append_to_last_user_message}"
        break
    return updated


def available_model_specs(
    snapshot: AvailabilitySnapshot,
    catalog: tuple[GatewayModelSpec, ...] = DEFAULT_MODEL_SPECS,
) -> list[GatewayModelSpec]:
    """Filter the public catalog to models currently backed by a healthy provider."""

    available: list[GatewayModelSpec] = []
    for spec in catalog:
        live_spec = spec.live_route(snapshot)
        if live_spec is not None:
            available.append(live_spec)
    return available


def choose_route(
    requested_model: str,
    snapshot: AvailabilitySnapshot,
    catalog: tuple[GatewayModelSpec, ...] = DEFAULT_MODEL_SPECS,
    priority: tuple[str, ...] = DEFAULT_PRIORITY,
) -> GatewayModelSpec | None:
    """Pick the requested route when live, otherwise fall back to the best live model."""

    live_specs = available_model_specs(snapshot, catalog)
    live_by_public_id = {spec.public_id: spec for spec in live_specs}
    requested_spec = resolve_model_spec(requested_model, catalog)
    if requested_spec and requested_spec.public_id in live_by_public_id:
        return live_by_public_id[requested_spec.public_id]
    for public_id in priority:
        spec = live_by_public_id.get(public_id)
        if spec:
            return spec
    # Never hand back the requested spec unresolved. The caller compares public_id to decide whether
    # substitution happened, so returning it here read as "the requested model is live" and POSTed a
    # dead id upstream, where LM Studio's own loose matching could load different weights.
    return None


def build_models_payload(
    snapshot: AvailabilitySnapshot,
    catalog: tuple[GatewayModelSpec, ...] = DEFAULT_MODEL_SPECS,
) -> dict[str, object]:
    """Build an OpenAI-compatible /v1/models payload."""

    now = int(snapshot.created)
    rows = [
        {
            "id": spec.public_id,
            "object": "model",
            "created": now,
            "owned_by": "halext",
        }
        for spec in available_model_specs(snapshot, catalog)
    ]
    return {"object": "list", "data": rows}


def build_chat_payload(
    model_id: str,
    text: str,
    *,
    completion_tokens: int = 0,
    prompt_tokens: int = 0,
    reasoning_content: str | None = None,
    response_id: str | None = None,
    created: int | None = None,
) -> dict[str, object]:
    """Build an OpenAI-compatible non-streaming chat response."""

    resolved_id = response_id or f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created_at = created or int(time.time())
    message: dict[str, object] = {"role": "assistant", "content": text}
    if reasoning_content and reasoning_content.strip():
        message["reasoning_content"] = reasoning_content.strip()
    return {
        "id": resolved_id,
        "object": "chat.completion",
        "created": created_at,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def build_stream_frames(
    model_id: str,
    text: str,
    *,
    reasoning_content: str | None = None,
    response_id: str | None = None,
    created: int | None = None,
    chunk_size: int = 96,
) -> list[str]:
    """Build SSE frames for an OpenAI-compatible streaming response."""

    resolved_id = response_id or f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created_at = created or int(time.time())
    frames = [
        {
            "id": resolved_id,
            "object": "chat.completion.chunk",
            "created": created_at,
            "model": model_id,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
    ]
    reasoning_text = (reasoning_content or "").strip()
    for index in range(0, len(reasoning_text), max(1, chunk_size)):
        frames.append(
            {
                "id": resolved_id,
                "object": "chat.completion.chunk",
                "created": created_at,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"reasoning_content": reasoning_text[index:index + max(1, chunk_size)]},
                        "finish_reason": None,
                    }
                ],
            }
        )
    for index in range(0, len(text), max(1, chunk_size)):
        frames.append(
            {
                "id": resolved_id,
                "object": "chat.completion.chunk",
                "created": created_at,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": text[index:index + max(1, chunk_size)]},
                        "finish_reason": None,
                    }
                ],
            }
        )
    frames.append(
        {
            "id": resolved_id,
            "object": "chat.completion.chunk",
            "created": created_at,
            "model": model_id,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )
    return [f"data: {json.dumps(frame, separators=(',', ':'))}\n\n" for frame in frames] + ["data: [DONE]\n\n"]
