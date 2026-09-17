from __future__ import annotations

import pytest

from afs_scawful.routing_manifest import (
    Lane,
    LaneBackend,
    ManifestError,
    backend_serves,
    lane_for_request,
    parse_manifest,
    parse_served_id,
    resolve_backend,
)

CURATED_SHA = "b4490ba25882fe825ebd95c4a4af50d419b59e5a6204807f9dc24fa8438fea48"
CURATED = LaneBackend(host="medical-mechanica", provider="lmstudio_win",
                      model="qwen35-curated-masked", quant="q8_0", sha256=CURATED_SHA)


def test_a_box_renaming_a_model_to_name_at_quant_still_resolves():
    # LM Studio relabels a model the moment a second quant of it exists; that rename dropped the
    # promoted lane out of the catalog entirely under the old substring matcher.
    assert backend_serves("qwen35-curated-masked", CURATED)
    assert backend_serves("qwen35-curated-masked@q8_0", CURATED)
    assert resolve_backend(["gguf/zelda/other.gguf", "qwen35-curated-masked@q8_0"], CURATED) == \
        "qwen35-curated-masked@q8_0"


def test_a_different_quant_of_the_same_model_is_not_these_weights():
    assert not backend_serves("qwen35-curated-masked@q5_k_m", CURATED)
    assert resolve_backend(["qwen35-curated-masked@q5_k_m"], CURATED) is None


def test_a_differently_trained_sibling_never_satisfies_the_name():
    sft = LaneBackend(host="h", provider="lmstudio_win", model="scawfulbot-qwen3-8b-v1")
    # The old matcher accepted this by prefix, so a DPO model could answer for the SFT lane.
    assert not backend_serves("scawfulbot-qwen3-8b-v1-dpo", sft)
    assert not backend_serves("some-other-lmstudio@q5_k_m", CURATED), "no unanchored suffix matching"
    assert backend_serves("scawfulbot-qwen3-8b-v1", sft)


def test_parse_served_id_handles_paths_and_missing_quant():
    assert parse_served_id("qwen35-curated-masked@q8_0") == ("qwen35-curated-masked", "q8_0")
    assert parse_served_id("gguf/zelda/oracle-v5.gguf") == ("gguf/zelda/oracle-v5.gguf", None)
    assert parse_served_id("trailing@") == ("trailing@", None)


def _manifest(**overrides):
    lane = {
        "id": "scawfulbot",
        "display_name": "Scawfulbot",
        "serves": [{"host": "medical-mechanica", "provider": "lmstudio_win",
                    "model": "qwen35-curated-masked", "quant": "q8_0", "sha256": "b4490ba25882fe825ebd95c4a4af50d419b59e5a6204807f9dc24fa8438fea48"}],
        "also_answers_to": ["scawfulbot-qwen35"],
        "provenance": {"corpus_sha256": "ad32b2cd6eb9", "eval_pass_system": 0.47},
    }
    lane.update(overrides)
    return {"version": 1, "lanes": [lane]}


def test_a_lane_carries_the_weights_identity_and_its_provenance():
    (lane,) = parse_manifest(_manifest())
    assert lane.backends[0].sha256 == "b4490ba25882fe825ebd95c4a4af50d419b59e5a6204807f9dc24fa8438fea48"
    assert lane.provenance["eval_pass_system"] == 0.47
    assert lane.on_unavailable == "error", "a lane must default to erroring, never substituting"
    assert lane.request_ids() == ("scawfulbot", "scawfulbot-qwen35")


def test_two_lanes_may_not_claim_the_same_request_id():
    data = _manifest()
    data["lanes"].append({"id": "other", "serves": data["lanes"][0]["serves"],
                          "also_answers_to": ["scawfulbot-qwen35"]})
    with pytest.raises(ManifestError) as caught:
        parse_manifest(data)
    assert "scawfulbot-qwen35" in str(caught.value)


def test_lane_ids_cannot_collide_case_insensitively_or_with_backend_evidence():
    data = _manifest()
    data["lanes"].append({
        "id": "SCAWFULBOT-QWEN35",
        "serves": [{
            "host": "other-host",
            "provider": "lmstudio_win",
            "model": "other-model",
            "sha256": "0" * 64,
        }],
    })
    with pytest.raises(ManifestError, match="claimed by both"):
        parse_manifest(data)

    data = _manifest()
    data["lanes"].append({
        "id": "qwen35-curated-masked",
        "serves": [{
            "host": "other-host",
            "provider": "lmstudio_win",
            "model": "other-model",
            "sha256": "0" * 64,
        }],
    })
    with pytest.raises(ManifestError, match="claimed by both"):
        parse_manifest(data)


def test_substituting_another_model_cannot_be_configured():
    with pytest.raises(ManifestError):
        parse_manifest(_manifest(on_unavailable="fallback"))


@pytest.mark.parametrize("bad, reason", [
    ({"version": 2, "lanes": []}, "version"),
    ({"version": 1, "lanes": []}, "empty lanes"),
    ({"version": 1, "lanes": [{"id": "x"}]}, "no serves"),
    ({"version": 1, "lanes": [{"id": "x", "serves": [{"host": "h", "provider": "p"}]}]}, "no model"),
    ({"version": 1, "lanes": [{"id": "x", "serves": [{"host": "h", "provider": "p", "model": "m"}]}]},
     "no hash"),
    ({"version": 1, "lanes": [{"id": "x", "serves": [{"host": "h", "provider": "p", "model": "m",
                                                      "sha256": "abc"}]}]}, "short sha"),
    ({"version": 1, "lanes": [{"id": "x", "serves": [{"host": "h", "provider": "p", "model": "m",
                                                      "sha256": "not-a-sha256"}]}]}, "non-hex hash"),
])
def test_a_broken_manifest_fails_at_load_not_at_request_time(bad, reason):
    with pytest.raises(ManifestError):
        parse_manifest(bad)


def test_request_matching_is_exact_not_fuzzy():
    lanes = parse_manifest(_manifest())
    assert lane_for_request(lanes, "SCAWFULBOT").id == "scawfulbot"
    assert lane_for_request(lanes, " scawfulbot-qwen35 ").id == "scawfulbot"
    for typo in ("scawfulbot-qwen3", "scawfulbot-qwen35-v1-dpo", "scawfulbo"):
        assert lane_for_request(lanes, typo) is None, f"{typo!r} must not resolve to a lane"


def test_lanes_can_declare_tools_for_assistant_surfaces():
    (lane,) = parse_manifest(_manifest(tools=["tasks", "home"]))
    assert lane.tools == ("tasks", "home")
    assert Lane(id="bare", backends=(CURATED,)).tools == ()


def test_a_short_request_alias_is_not_evidence_that_weights_are_present():
    # "scawfulbot" as an availability candidate matched a box's "scawfulbot-gemma4-…gguf", so the
    # lane went live and served the wrong weights under the right name.
    from afs_scawful.routing_manifest import manifest_specs

    (spec,) = manifest_specs(parse_manifest(_manifest(id="scawfulbot-qwen35", also_answers_to=["scawfulbot"])))
    assert spec.request_aliases == ("scawfulbot",), "requestable"
    assert "scawfulbot" not in spec.aliases, "but never counted as these weights"
    assert set(spec.aliases) == {"qwen35-curated-masked", "qwen35-curated-masked@q8_0"}
    assert "scawfulbot" in spec.all_ids(), "still resolvable by request"
    assert "qwen35-curated-masked" not in spec.all_ids(), "backend evidence is not a public request id"


def test_the_quant_a_lane_declares_wins_over_list_order():
    from afs_scawful.halext_cloud_gateway_core import AvailabilitySnapshot, ProviderAvailability
    from afs_scawful.routing_manifest import manifest_specs

    data = _manifest()
    data["lanes"][0]["serves"][0]["model"] = "qwen35-v1-dpo"
    (spec,) = manifest_specs(parse_manifest(data))
    # The box lists every quant it holds, q5 first.
    snap = AvailabilitySnapshot(created=1.0, providers={
        "lmstudio_win": ProviderAvailability(
            healthy=True,
            models=("qwen35-v1-dpo@q5_k_m", "qwen35-v1-dpo@q8_0"),
            host="medical-mechanica",
            model_sha256={"qwen35-v1-dpo@q8_0": "b4490ba25882fe825ebd95c4a4af50d419b59e5a6204807f9dc24fa8438fea48"},
        ),
    })
    live = spec.live_route(snap)
    assert live is not None and live.provider_model == "qwen35-v1-dpo@q8_0"


@pytest.mark.parametrize("reported", [
    "qwen35-v1-dpo@q5_k_m",
    "qwen35-v1-dpo-q5_k_m.gguf",
])
def test_a_wrong_quant_alone_cannot_satisfy_a_quant_pinned_lane(reported):
    from afs_scawful.halext_cloud_gateway_core import AvailabilitySnapshot, ProviderAvailability
    from afs_scawful.routing_manifest import manifest_specs

    data = _manifest()
    data["lanes"][0]["serves"][0]["model"] = "qwen35-v1-dpo"
    (spec,) = manifest_specs(parse_manifest(data))
    snap = AvailabilitySnapshot(created=1.0, providers={
        "lmstudio_win": ProviderAvailability(
            healthy=True,
            models=(reported,),
            host="medical-mechanica",
            model_sha256={reported: "b4490ba25882fe825ebd95c4a4af50d419b59e5a6204807f9dc24fa8438fea48"},
        ),
    })

    assert spec.live_route(snap) is None


@pytest.mark.parametrize("host, measured", [
    ("medical-mechanica", None),
    ("medical-mechanica", "0" * 64),
    ("some-other-host", "b4490ba25882fe825ebd95c4a4af50d419b59e5a6204807f9dc24fa8438fea48" + "0" * 48),
])
def test_a_lane_is_unavailable_without_its_declared_host_and_hash(host, measured):
    from afs_scawful.halext_cloud_gateway_core import AvailabilitySnapshot, ProviderAvailability
    from afs_scawful.routing_manifest import manifest_specs

    (spec,) = manifest_specs(parse_manifest(_manifest()))
    hashes = {"qwen35-curated-masked": measured} if measured else {}
    snap = AvailabilitySnapshot(created=1.0, providers={
        "lmstudio_win": ProviderAvailability(
            healthy=True,
            models=("qwen35-curated-masked",),
            host=host,
            model_sha256=hashes,
        ),
    })

    assert spec.live_route(snap) is None


def test_a_missing_manifest_fails_closed(tmp_path):
    from afs_scawful.halext_cloud_gateway_core import load_gateway_model_specs

    with pytest.raises(ManifestError, match="not found"):
        load_gateway_model_specs(manifest_path=tmp_path / "missing.toml")


def test_registry_metadata_cannot_recombine_a_manifest_lane_namespace(tmp_path):
    from afs_scawful.halext_cloud_gateway_core import (
        load_gateway_model_specs,
        resolve_model_spec,
    )

    registry = tmp_path / "registry.toml"
    registry.write_text(
        """
[[models]]
name = "scawfulbot"
provider = "openai"
model_id = "wrong"
""",
        encoding="utf-8",
    )

    catalog = load_gateway_model_specs(registry_path=registry)
    lane = resolve_model_spec("scawfulbot", catalog)
    assert lane is not None
    assert lane.host == "medical-mechanica"
    assert lane.sha256 == "b4490ba25882fe825ebd95c4a4af50d419b59e5a6204807f9dc24fa8438fea48"
    assert resolve_model_spec("wrong", catalog) is None


def test_distinct_catalog_specs_cannot_share_a_request_id():
    from afs_scawful.halext_cloud_gateway_core import (
        GatewayModelSpec,
        _validate_request_namespace,
    )

    specs = (
        GatewayModelSpec(
            public_id="lane-a",
            provider="openai",
            provider_model="model-a",
            display_name="A",
            aliases=("shared",),
        ),
        GatewayModelSpec(
            public_id="lane-b",
            provider="openai",
            provider_model="model-b",
            display_name="B",
            aliases=("shared",),
        ),
    )
    with pytest.raises(ValueError, match="claimed by both"):
        _validate_request_namespace(specs)


def test_a_prefix_digest_is_refused_at_load():
    # Prefixes were accepted until 2026-09-16. Two problems: a different file sharing those leading
    # digits satisfies the lane, and a prefix cannot be lengthened later without a flag day.
    data = _manifest()
    data["lanes"][0]["serves"][0]["sha256"] = CURATED_SHA[:16]
    with pytest.raises(ManifestError, match="full 64-hex digest"):
        parse_manifest(data)
    for bad in ("", "zz" * 32, CURATED_SHA + "00", CURATED_SHA[:63]):
        data["lanes"][0]["serves"][0]["sha256"] = bad
        with pytest.raises(ManifestError):
            parse_manifest(data)


def test_the_shipped_manifest_pins_full_digests():
    from afs_scawful.routing_manifest import DEFAULT_MANIFEST_PATH, load_manifest
    import re

    for lane in load_manifest(DEFAULT_MANIFEST_PATH):
        for backend in lane.backends:
            assert re.fullmatch(r"[0-9a-f]{64}", backend.sha256 or ""), f"{lane.id} carries a partial digest"
