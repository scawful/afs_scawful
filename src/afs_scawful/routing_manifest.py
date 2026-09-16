"""Routing manifest: which lane serves which weights, on which box.

The gateway's model catalog was 23 hand-written specs with ~60 hand-typed ids, where alias tuples
did double duty as "names a client may request" and "names that count as available". Two failures
came out of that (2026-09-16):

  * LM Studio renames a model to `name@quant` as soon as a second quant of it exists, and the
    availability matcher had no rule for `@`, so a promoted lane could match nothing and disappear.
  * A legacy alias kept on a promoted lane could bind that lane to the weights it replaced, because
    availability matching walks the box's model list and takes the first raw id matching any alias.

A lane here names the weights by sha256, not by a string a box may relabel. Requesting a lane whose
weights are not present is an error: no lane ever answers with different weights than it declares.

  lanes = load_manifest(Path("config/routing_manifest.toml"))
  specs = manifest_specs(lanes)          # GatewayModelSpec tuple for the gateway catalog
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "config/routing_manifest.toml"
UNAVAILABLE_POLICIES = ("error",)


class ManifestError(ValueError):
    """The manifest is unusable. Raised at load time rather than mis-routing at request time."""


@dataclass(frozen=True)
class LaneBackend:
    """One set of weights on one box."""

    host: str
    provider: str
    model: str
    quant: str | None = None
    sha256: str | None = None

    @property
    def served_id(self) -> str:
        """The id a box reports when this model is the only quant present."""
        return self.model

    @property
    def quantised_id(self) -> str | None:
        """The id a box reports once a sibling quant exists (LM Studio's `name@quant` form)."""
        return f"{self.model}@{self.quant}" if self.quant else None

    def ids(self) -> tuple[str, ...]:
        return tuple(value for value in (self.served_id, self.quantised_id) if value)


@dataclass(frozen=True)
class Lane:
    """A name clients request, and the weights that are allowed to answer to it."""

    id: str
    backends: tuple[LaneBackend, ...]
    display_name: str = ""
    description: str = ""
    on_unavailable: str = "error"
    also_answers_to: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    provenance: dict = field(default_factory=dict)

    def request_ids(self) -> tuple[str, ...]:
        """Every id a client may use for this lane. Never used for availability matching."""
        return (self.id, *self.also_answers_to)


def parse_served_id(raw_id: str) -> tuple[str, str | None]:
    """Split a box's model id into (base, quant). `a/b/c@q8_0` -> ("a/b/c", "q8_0")."""
    base, separator, quant = raw_id.partition("@")
    return (base, quant) if separator and quant else (raw_id, None)


def backend_serves(raw_id: str, backend: LaneBackend) -> bool:
    """Does this id from a box denote exactly this backend's weights?

    Exact on the base name, and on the quant when both sides state one. Deliberately not the old
    substring matching: `scawfulbot-qwen3-8b-v1` must not match a differently trained
    `scawfulbot-qwen3-8b-v1-dpo`, and an alias must never match by suffix.
    """
    base, quant = parse_served_id(raw_id.strip())
    if base != backend.model:
        return False
    if quant and backend.quant and quant != backend.quant:
        return False
    return True


def resolve_backend(raw_ids, backend: LaneBackend) -> str | None:
    """The id to send upstream for these weights, or None when the box is not serving them."""
    for raw_id in raw_ids:
        if backend_serves(raw_id, backend):
            return raw_id
    return None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def _backend_from_row(row: dict, lane_id: str) -> LaneBackend:
    for key in ("host", "provider", "model"):
        _require(isinstance(row.get(key), str) and row[key].strip(), f"lane {lane_id!r}: backend needs {key}")
    sha = row.get("sha256")
    _require(isinstance(sha, str), f"lane {lane_id!r}: backend needs sha256")
    sha = sha.strip().lower()
    _require(
        12 <= len(sha) <= 64 and re.fullmatch(r"[0-9a-f]+", sha) is not None,
        f"lane {lane_id!r}: sha256 must be 12 to 64 hex chars",
    )
    quant = row.get("quant")
    _require(quant is None or isinstance(quant, str), f"lane {lane_id!r}: quant must be a string")
    return LaneBackend(host=row["host"], provider=row["provider"], model=row["model"], quant=quant, sha256=sha)


def parse_manifest(data: dict) -> tuple[Lane, ...]:
    _require(data.get("version") == 1, "manifest version must be 1")
    rows = data.get("lanes")
    _require(isinstance(rows, list) and rows, "manifest needs a non-empty [[lanes]] list")
    lanes: list[Lane] = []
    seen: dict[str, str] = {}
    for row in rows:
        lane_id = row.get("id")
        _require(isinstance(lane_id, str) and lane_id.strip(), "every lane needs an id")
        backends = row.get("serves")
        _require(isinstance(backends, list) and backends, f"lane {lane_id!r}: needs at least one entry in serves")
        policy = row.get("on_unavailable", "error")
        _require(policy in UNAVAILABLE_POLICIES,
                 f"lane {lane_id!r}: on_unavailable must be one of {UNAVAILABLE_POLICIES}")
        lane = Lane(
            id=lane_id,
            backends=tuple(_backend_from_row(entry, lane_id) for entry in backends),
            display_name=row.get("display_name", lane_id),
            description=row.get("description", ""),
            on_unavailable=policy,
            also_answers_to=tuple(row.get("also_answers_to", ()) or ()),
            tools=tuple(row.get("tools", ()) or ()),
            provenance=dict(row.get("provenance", {}) or {}),
        )
        declared_ids = (
            *lane.request_ids(),
            *(backend_id for backend in lane.backends for backend_id in backend.ids()),
        )
        for declared_id in declared_ids:
            normalized = declared_id.strip().lower()
            owner = seen.get(normalized)
            _require(
                owner in (None, lane_id),
                f"id {declared_id!r} is claimed by both {owner!r} and {lane_id!r}",
            )
            seen[normalized] = lane_id
        lanes.append(lane)
    return tuple(lanes)


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> tuple[Lane, ...]:
    if not path.exists():
        raise ManifestError(f"routing manifest not found: {path}")
    with path.open("rb") as handle:
        return parse_manifest(tomllib.load(handle))


def manifest_specs(lanes) -> tuple:
    """Turn lanes into gateway catalog specs.

    Aliases are generated, never hand-typed: a lane's declared request ids plus, for each backend,
    the ids that box may report for those exact weights (`model` and `model@quant`). Nothing else
    can bind a lane, which is what kept a legacy alias able to pull a promoted lane back onto the
    weights it replaced.
    """
    from .halext_cloud_gateway_core import GatewayModelBackend, GatewayModelSpec

    specs = []
    for lane in lanes:
        primary, *rest = lane.backends
        specs.append(GatewayModelSpec(
            public_id=lane.id,
            provider=primary.provider,
            provider_model=primary.served_id,
            aliases=primary.ids(),          # what counts as these weights being present
            request_aliases=lane.also_answers_to,  # what a client may call them
            display_name=lane.display_name or lane.id,
            description=lane.description,
            host=primary.host,
            sha256=primary.sha256,
            expose_backend_ids=False,
            fallback_backends=tuple(
                GatewayModelBackend(provider=backend.provider, provider_model=backend.served_id,
                                    aliases=backend.ids(), host=backend.host, sha256=backend.sha256)
                for backend in rest
            ),
        ))
    return tuple(specs)


def lane_for_request(lanes, requested_id: str) -> Lane | None:
    """Exact, case-insensitive match on a lane's declared request ids. No fuzzy matching."""
    wanted = requested_id.strip().lower()
    for lane in lanes:
        if any(wanted == request_id.strip().lower() for request_id in lane.request_ids()):
            return lane
    return None
