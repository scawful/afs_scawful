from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ID_SECRET = b"review-test-secret-material-0001"
OTHER_ID_SECRET = b"review-test-secret-material-0002"


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "build_claudia_review_sheet.py"
    spec = importlib.util.spec_from_file_location("build_claudia_review_sheet", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def test_build_pairwise_sheet_creates_blind_key(tmp_path: Path) -> None:
    module = _load_module()
    pack = [
        {
            "id": "grounding-001",
            "prompt": "test prompt",
            "tags": ["witness"],
            "focus": ["honesty"],
            "expected_signals": ["flag weak evidence"],
            "auto_fail_signals": ["treats it as proof"],
        }
    ]
    claudia = tmp_path / "claudia.jsonl"
    rewrite = tmp_path / "rewrite.jsonl"
    _write_jsonl(claudia, [{"id": "grounding-001", "completion": "candidate one"}])
    _write_jsonl(rewrite, [{"id": "grounding-001", "completion": "candidate two"}])

    sheet, key_rows, csv_rows = module.build_pairwise_sheet(
        pack,
        [
            ("claudia", module.index_by_id(module.load_jsonl(claudia))),
            ("rewrite", module.index_by_id(module.load_jsonl(rewrite))),
        ],
        seed=7,
        id_secret=ID_SECRET,
    )

    assert len(sheet) == 1
    assert len(key_rows) == 1
    assert len(csv_rows) == 1
    assert sheet[0]["candidate_a"] in {"candidate one", "candidate two"}
    assert sheet[0]["candidate_b"] in {"candidate one", "candidate two"}
    assert {key_rows[0]["candidate_a_source"], key_rows[0]["candidate_b_source"]} == {"claudia", "rewrite"}
    assert sheet[0]["review_id"].startswith("review_")
    public_payload = json.dumps([sheet, csv_rows])
    assert "claudia" not in public_payload
    assert "rewrite" not in public_payload

    different_seed, _, _ = module.build_pairwise_sheet(
        pack,
        [
            ("claudia", module.index_by_id(module.load_jsonl(claudia))),
            ("rewrite", module.index_by_id(module.load_jsonl(rewrite))),
        ],
        seed=8,
        id_secret=ID_SECRET,
    )
    assert sheet[0]["review_id"] == different_seed[0]["review_id"]

    different_secret, _, _ = module.build_pairwise_sheet(
        pack,
        [
            ("claudia", module.index_by_id(module.load_jsonl(claudia))),
            ("rewrite", module.index_by_id(module.load_jsonl(rewrite))),
        ],
        seed=7,
        id_secret=OTHER_ID_SECRET,
    )
    assert sheet[0]["review_id"] != different_secret[0]["review_id"]


def test_single_sheet_keeps_candidate_identity_in_key_only() -> None:
    module = _load_module()
    pack = [{"id": "grounding-001", "prompt": "test prompt"}]

    sheet, key_rows, csv_rows = module.build_single_sheet(
        pack,
        {"grounding-001": {"completion": "candidate response"}},
        candidate_label="private-model-label",
        id_secret=ID_SECRET,
    )

    assert sheet[0]["review_id"].startswith("review_")
    assert key_rows[0]["candidate_source"] == "private-model-label"
    assert "private-model-label" not in json.dumps([sheet, csv_rows])


def test_review_id_rejects_weak_secret() -> None:
    module = _load_module()

    try:
        module.opaque_review_id(b"guessable", "prompt", "candidate")
    except ValueError as error:
        assert "at least 32 bytes" in str(error)
    else:
        raise AssertionError("opaque_review_id accepted a weak secret")


def test_pairwise_requires_two_unique_candidate_labels() -> None:
    module = _load_module()
    records = {"prompt": {"completion": "response"}}

    for candidates, expected in (
        ([("only", records)], "at least two"),
        ([("same", records), ("same", records)], "must be unique"),
    ):
        try:
            module.build_pairwise_sheet(
                [{"id": "prompt", "prompt": "test"}],
                candidates,
                seed=42,
                id_secret=ID_SECRET,
            )
        except ValueError as error:
            assert expected in str(error)
        else:
            raise AssertionError(f"pairwise builder accepted {candidates!r}")


def test_review_builders_reject_missing_candidate_responses() -> None:
    module = _load_module()
    pack = [{"id": "prompt", "prompt": "test"}]
    complete = {"prompt": {"completion": "response"}}
    missing: dict[str, dict] = {}

    calls = (
        lambda: module.build_single_sheet(
            pack,
            missing,
            candidate_label="single",
            id_secret=ID_SECRET,
        ),
        lambda: module.build_pairwise_sheet(
            pack,
            [("complete", complete), ("missing", missing)],
            seed=42,
            id_secret=ID_SECRET,
        ),
        lambda: module.build_rewrite_tasks(
            pack,
            missing,
            candidate_label="rewrite",
        ),
    )
    for call in calls:
        try:
            call()
        except ValueError as error:
            assert "missing non-empty responses" in str(error)
        else:
            raise AssertionError("review builder accepted a missing candidate response")

    try:
        module.build_single_sheet(
            pack,
            {"prompt": {"completion": ["not", "text"]}},
            candidate_label="single",
            id_secret=ID_SECRET,
        )
    except ValueError as error:
        assert "missing non-empty responses" in str(error)
    else:
        raise AssertionError("review builder stringified a non-text response")


def test_review_builders_reject_duplicate_ids() -> None:
    module = _load_module()
    duplicate_responses = [
        {"id": "prompt", "completion": "first"},
        {"id": "prompt", "completion": "second"},
    ]
    try:
        module.index_by_id(duplicate_responses)
    except ValueError as error:
        assert "duplicate candidate response id" in str(error)
    else:
        raise AssertionError("candidate index silently overwrote a duplicate id")

    try:
        module.build_single_sheet(
            [
                {"id": "prompt", "prompt": "first"},
                {"id": "prompt", "prompt": "second"},
            ],
            {"prompt": {"completion": "response"}},
            candidate_label="single",
            id_secret=ID_SECRET,
        )
    except ValueError as error:
        assert "duplicate review pack id" in str(error)
    else:
        raise AssertionError("review builder accepted duplicate pack ids")


def test_review_builders_normalize_prompt_ids_consistently() -> None:
    module = _load_module()
    pack = [{"id": " prompt ", "prompt": "test"}]
    responses = {"prompt": {"completion": "response"}}

    single, _, _ = module.build_single_sheet(
        pack,
        responses,
        candidate_label="single",
        id_secret=ID_SECRET,
    )
    pairwise, _, _ = module.build_pairwise_sheet(
        pack,
        [("first", responses), ("second", responses)],
        seed=42,
        id_secret=ID_SECRET,
    )
    rewrite = module.build_rewrite_tasks(
        pack,
        responses,
        candidate_label="rewrite",
    )

    assert single[0]["prompt_id"] == "prompt"
    assert single[0]["response"] == "response"
    assert pairwise[0]["prompt_id"] == "prompt"
    assert pairwise[0]["candidate_a"] == "response"
    assert rewrite[0]["source_prompt_id"] == "prompt"
    assert rewrite[0]["assistant_response"] == "response"


def test_review_builders_reject_empty_pack_and_semantically_empty_fields() -> None:
    module = _load_module()

    for records in (
        [{"id": None, "completion": "response"}],
        [{"id": 123, "completion": "response"}],
        [{"id": "", "completion": "response"}],
    ):
        try:
            module.index_by_id(records)
        except ValueError as error:
            assert "non-empty string id" in str(error)
        else:
            raise AssertionError(f"candidate index accepted invalid IDs: {records!r}")

    invalid_packs = (
        [],
        [{"id": None, "prompt": "test"}],
        [{"id": "prompt", "prompt": None}],
        [{"id": "prompt", "prompt": "   "}],
    )
    for pack in invalid_packs:
        try:
            module.build_single_sheet(
                pack,
                {"prompt": {"completion": "response"}},
                candidate_label="single",
                id_secret=ID_SECRET,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"review builder accepted invalid pack: {pack!r}")

    for label in (None, 123, "", "   "):
        try:
            module.build_single_sheet(
                [{"id": "prompt", "prompt": "test"}],
                {"prompt": {"completion": "response"}},
                candidate_label=label,
                id_secret=ID_SECRET,
            )
        except ValueError as error:
            assert "candidate label" in str(error)
        else:
            raise AssertionError(f"review builder accepted invalid label: {label!r}")


def test_candidate_order_uses_private_secret() -> None:
    module = _load_module()

    first = module.private_order_token(
        ID_SECRET,
        "prompt",
        "candidate-one",
        "candidate-two",
        42,
    )
    repeated = module.private_order_token(
        ID_SECRET,
        "prompt",
        "candidate-one",
        "candidate-two",
        42,
    )
    other_secret = module.private_order_token(
        OTHER_ID_SECRET,
        "prompt",
        "candidate-one",
        "candidate-two",
        42,
    )

    assert first == repeated
    assert first != other_secret


def test_pairwise_cli_keeps_labels_and_paths_in_private_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    pack = tmp_path / "pack.jsonl"
    first = tmp_path / "first-source.jsonl"
    second = tmp_path / "second-source.jsonl"
    output = tmp_path / "public.review.jsonl"
    _write_jsonl(pack, [{"id": "grounding-001", "prompt": "test prompt"}])
    _write_jsonl(first, [{"id": "grounding-001", "completion": "candidate one"}])
    _write_jsonl(second, [{"id": "grounding-001", "completion": "candidate two"}])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_claudia_review_sheet.py",
            "pairwise",
            "--pack",
            str(pack),
            "--candidate",
            f"private-alpha={first}",
            "--candidate",
            f"private-beta={second}",
            "--out",
            str(output),
            "--seed",
            "11",
        ],
    )
    previous_umask = os.umask(0o022)
    try:
        assert module.main() == 0
    finally:
        os.umask(previous_umask)

    public_text = output.read_text() + output.with_suffix(".csv").read_text()
    assert "private-alpha" not in public_text
    assert "private-beta" not in public_text
    assert str(first) not in public_text
    assert str(second) not in public_text

    key_path = output.with_suffix(".key.jsonl")
    key_text = key_path.read_text()
    assert "private-alpha" in key_text
    assert "private-beta" in key_text
    assert str(first) in key_text
    assert str(second) in key_text
    for private_output in (output, output.with_suffix(".csv"), key_path):
        assert stat.S_IMODE(private_output.stat().st_mode) == 0o600


def test_pairwise_cli_rejects_invalid_candidates_before_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    output = tmp_path / "must-not-exist.review.jsonl"

    for candidate_args in (
        ["--candidate", f"only={tmp_path / 'one.jsonl'}"],
        [
            "--candidate",
            f"same={tmp_path / 'one.jsonl'}",
            "--candidate",
            f"same={tmp_path / 'two.jsonl'}",
        ],
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "build_claudia_review_sheet.py",
                "pairwise",
                "--pack",
                str(tmp_path / "missing-pack.jsonl"),
                *candidate_args,
                "--out",
                str(output),
            ],
        )
        try:
            module.main()
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("pairwise CLI accepted an invalid candidate set")
        assert not output.exists()
        assert not output.with_suffix(".csv").exists()
        assert not output.with_suffix(".key.jsonl").exists()


def test_pairwise_cli_rejects_aliased_candidate_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    pack = tmp_path / "pack.jsonl"
    candidate = tmp_path / "candidate.jsonl"
    output = tmp_path / "must-not-exist.review.jsonl"
    _write_jsonl(pack, [{"id": "prompt", "prompt": "test"}])
    _write_jsonl(candidate, [{"id": "prompt", "completion": "response"}])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_claudia_review_sheet.py",
            "pairwise",
            "--pack",
            str(pack),
            "--candidate",
            f"first={candidate}",
            "--candidate",
            f"second={candidate}",
            "--out",
            str(output),
        ],
    )

    try:
        module.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("pairwise CLI accepted aliased candidate inputs")
    assert not output.exists()


def test_pairwise_cli_rejects_missing_response_before_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    pack = tmp_path / "pack.jsonl"
    complete = tmp_path / "complete.jsonl"
    missing = tmp_path / "missing.jsonl"
    output = tmp_path / "must-not-exist.review.jsonl"
    _write_jsonl(pack, [{"id": "prompt", "prompt": "test"}])
    _write_jsonl(complete, [{"id": "prompt", "completion": "response"}])
    _write_jsonl(missing, [{"id": "different-prompt", "completion": "response"}])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_claudia_review_sheet.py",
            "pairwise",
            "--pack",
            str(pack),
            "--candidate",
            f"complete={complete}",
            "--candidate",
            f"missing={missing}",
            "--out",
            str(output),
        ],
    )

    try:
        module.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("pairwise CLI accepted a missing candidate response")

    assert not output.exists()
    assert not output.with_suffix(".csv").exists()
    assert not output.with_suffix(".key.jsonl").exists()


def test_review_cli_rejects_outputs_that_alias_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    pack = tmp_path / "pack.review.jsonl"
    first = tmp_path / "first.review.jsonl"
    second = tmp_path / "second.review.jsonl"
    _write_jsonl(pack, [{"id": "prompt", "prompt": "test"}])
    _write_jsonl(first, [{"id": "prompt", "completion": "first"}])
    _write_jsonl(second, [{"id": "prompt", "completion": "second"}])
    original_pack = pack.read_text(encoding="utf-8")
    original_first = first.read_text(encoding="utf-8")

    commands = (
        [
            "single",
            "--pack",
            str(pack),
            "--responses",
            str(first),
            "--candidate-label",
            "candidate",
            "--out",
            str(first),
        ],
        [
            "pairwise",
            "--pack",
            str(pack),
            "--candidate",
            f"first={first}",
            "--candidate",
            f"second={second}",
            "--out",
            str(pack),
        ],
    )
    for command in commands:
        monkeypatch.setattr(
            sys,
            "argv",
            ["build_claudia_review_sheet.py", *command],
        )
        try:
            module.main()
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("review CLI accepted an output that aliases input")
        assert pack.read_text(encoding="utf-8") == original_pack
        assert first.read_text(encoding="utf-8") == original_first


def test_review_outputs_must_not_alias_each_other(tmp_path: Path) -> None:
    module = _load_module()
    output = tmp_path / "public.review.jsonl"
    key_output = output.with_suffix(".key.jsonl")
    output.write_text("preserve", encoding="utf-8")
    os.link(output, key_output)

    try:
        module.validate_review_artifact_paths(output, [])
    except ValueError as error:
        assert "alias each other" in str(error)
    else:
        raise AssertionError("review output aliases were accepted")

    assert output.read_text(encoding="utf-8") == "preserve"


def test_review_cli_refuses_rerun_without_explicit_force(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    pack = tmp_path / "pack.jsonl"
    responses = tmp_path / "responses.jsonl"
    output = tmp_path / "scores.review.jsonl"
    _write_jsonl(pack, [{"id": "prompt", "prompt": "test"}])
    _write_jsonl(responses, [{"id": "prompt", "completion": "response"}])
    command = [
        "build_claudia_review_sheet.py",
        "single",
        "--pack",
        str(pack),
        "--responses",
        str(responses),
        "--candidate-label",
        "candidate",
        "--out",
        str(output),
    ]
    monkeypatch.setattr(sys, "argv", command)
    assert module.main() == 0
    reviewed = module.load_jsonl(output)
    reviewed[0]["notes"] = "HUMAN REVIEW"
    _write_jsonl(output, reviewed)
    preserved = output.read_text(encoding="utf-8")

    monkeypatch.setattr(sys, "argv", command)
    try:
        module.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("review rerun silently overwrote human scores")
    assert output.read_text(encoding="utf-8") == preserved

    monkeypatch.setattr(sys, "argv", [*command, "--force"])
    assert module.main() == 0
    assert "HUMAN REVIEW" not in output.read_text(encoding="utf-8")


def test_review_cli_preflights_all_artifacts_before_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    pack = tmp_path / "pack.jsonl"
    responses = tmp_path / "responses.jsonl"
    output = tmp_path / "scores.review.jsonl"
    key_output = output.with_suffix(".key.jsonl")
    victim = tmp_path / "victim.txt"
    _write_jsonl(pack, [{"id": "prompt", "prompt": "test"}])
    _write_jsonl(responses, [{"id": "prompt", "completion": "response"}])
    victim.write_text("preserve", encoding="utf-8")
    key_output.symlink_to(victim)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_claudia_review_sheet.py",
            "single",
            "--pack",
            str(pack),
            "--responses",
            str(responses),
            "--candidate-label",
            "candidate",
            "--out",
            str(output),
        ],
    )

    try:
        module.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("review CLI wrote before preflighting all artifacts")
    assert not output.exists()
    assert victim.read_text(encoding="utf-8") == "preserve"


def test_rewrite_tasks_refuses_cross_mode_force_with_bundle_companions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    pack = tmp_path / "pack.jsonl"
    responses = tmp_path / "responses.jsonl"
    output = tmp_path / "scores.review.jsonl"
    key_output = output.with_suffix(".key.jsonl")
    csv_output = output.with_suffix(".csv")
    _write_jsonl(pack, [{"id": "prompt", "prompt": "test"}])
    _write_jsonl(responses, [{"id": "prompt", "completion": "response"}])
    output.write_text("reviewed sheet\n", encoding="utf-8")
    key_output.write_text("private key\n", encoding="utf-8")
    csv_output.write_text("human scores\n", encoding="utf-8")
    original = {
        path: path.read_text(encoding="utf-8")
        for path in (output, key_output, csv_output)
    }
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_claudia_review_sheet.py",
            "rewrite-tasks",
            "--pack",
            str(pack),
            "--responses",
            str(responses),
            "--candidate-label",
            "candidate",
            "--out",
            str(output),
            "--force",
        ],
    )

    try:
        module.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("rewrite-tasks replaced only part of a scored bundle")

    assert {
        path: path.read_text(encoding="utf-8")
        for path in (output, key_output, csv_output)
    } == original


def test_review_cli_requires_gitignored_output_suffix(tmp_path: Path) -> None:
    module = _load_module()

    try:
        module.build_arg_parser().parse_args(
            [
                "single",
                "--pack",
                "pack.jsonl",
                "--responses",
                "responses.jsonl",
                "--candidate-label",
                "candidate",
                "--out",
                "unsafe.jsonl",
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("review CLI accepted an output without the ignored suffix")

    try:
        module.write_jsonl(tmp_path / "unsafe.jsonl", [])
    except ValueError as error:
        assert "not gitignored" in str(error)
    else:
        raise AssertionError("review writer accepted an unignored artifact path")


def test_review_artifact_patterns_are_gitignored() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    for relative_path in (
        "nested/arbitrary.review.jsonl",
        "nested/arbitrary.review.csv",
        "nested/arbitrary.review.key.jsonl",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", relative_path],
            cwd=repo_root,
            check=False,
        )
        assert result.returncode == 0, relative_path


def test_review_writer_uses_path_chmod_only_without_fchmod(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    monkeypatch.delattr(module.os, "fchmod")
    output = tmp_path / "fallback.review.jsonl"

    module.write_jsonl(output, [{"private": "content"}])

    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_review_writer_refuses_linked_outputs(tmp_path: Path) -> None:
    module = _load_module()
    victim = tmp_path / "victim.txt"
    victim.write_text("preserve", encoding="utf-8")

    for kind in ("symlink", "hardlink"):
        output = tmp_path / f"{kind}.review.jsonl"
        if kind == "symlink":
            output.symlink_to(victim)
        else:
            os.link(victim, output)
        try:
            module.write_jsonl(output, [{"private": "content"}])
        except ValueError as error:
            assert "refusing" in str(error)
        else:
            raise AssertionError(f"review writer followed a {kind}")
        assert victim.read_text(encoding="utf-8") == "preserve"


def test_build_rewrite_tasks_keeps_expected_signals(tmp_path: Path) -> None:
    module = _load_module()
    pack = [
        {
            "id": "meta-001",
            "prompt": "what should i trust?",
            "focus": ["honesty", "actionability"],
            "expected_signals": ["separate resonance from truth"],
            "auto_fail_signals": ["treats tears as confirmation"],
        }
    ]
    responses_path = tmp_path / "responses.jsonl"
    _write_jsonl(responses_path, [{"id": "meta-001", "completion": "sounds true because it hit hard"}])

    tasks = module.build_rewrite_tasks(
        pack=pack,
        responses=module.index_by_id(module.load_jsonl(responses_path)),
        candidate_label="claudia",
    )

    assert len(tasks) == 1
    assert tasks[0]["source_candidate"] == "claudia"
    assert tasks[0]["expected_signals"] == ["separate resonance from truth"]
    assert "less flattering" in tasks[0]["rewrite_brief"]
