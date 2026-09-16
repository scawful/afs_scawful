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

CURATED = LaneBackend(host="medical-mechanica", provider="lmstudio_win",
                      model="qwen35-curated-masked", quant="q8_0", sha256="b4490ba25882fe82")


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
                    "model": "qwen35-curated-masked", "quant": "q8_0", "sha256": "b4490ba25882fe82"}],
        "also_answers_to": ["scawfulbot-qwen35"],
        "provenance": {"corpus_sha256": "ad32b2cd6eb9", "eval_pass_system": 0.47},
    }
    lane.update(overrides)
    return {"version": 1, "lanes": [lane]}


def test_a_lane_carries_the_weights_identity_and_its_provenance():
    (lane,) = parse_manifest(_manifest())
    assert lane.backends[0].sha256 == "b4490ba25882fe82"
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


def test_substituting_another_model_cannot_be_configured():
    with pytest.raises(ManifestError):
        parse_manifest(_manifest(on_unavailable="fallback"))


@pytest.mark.parametrize("bad, reason", [
    ({"version": 2, "lanes": []}, "version"),
    ({"version": 1, "lanes": []}, "empty lanes"),
    ({"version": 1, "lanes": [{"id": "x"}]}, "no serves"),
    ({"version": 1, "lanes": [{"id": "x", "serves": [{"host": "h", "provider": "p"}]}]}, "no model"),
    ({"version": 1, "lanes": [{"id": "x", "serves": [{"host": "h", "provider": "p", "model": "m",
                                                      "sha256": "abc"}]}]}, "short sha"),
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
