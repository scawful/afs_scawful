#!/usr/bin/env python3
"""
Build manual review sheets for Claudia falsifiability work.

Supports:
- single-response scoring sheets
- blinded pairwise comparison sheets
- adversarial rewrite task scaffolds
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import itertools
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Iterable


RUBRIC_AXES = [
    "honesty",
    "sycophancy_resistance",
    "evidential_grounding",
    "actionability",
    "literary_discipline",
]


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                records.append(json.loads(line))
    return records


def index_by_id(records: Iterable[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for position, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"candidate record {position} must be a JSON object")
        raw_record_id = record.get("id")
        if not isinstance(raw_record_id, str) or not raw_record_id.strip():
            raise ValueError(
                f"candidate record {position} requires a non-empty string id"
            )
        record_id = raw_record_id.strip()
        if record_id in indexed:
            raise ValueError(f"duplicate candidate response id: {record_id}")
        indexed[record_id] = record
    return indexed


def normalize_candidate_label(value: object) -> str:
    """Require a non-empty human-readable label."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("candidate label must be a non-empty string")
    return value.strip()


def parse_candidate_label(value: str) -> str:
    try:
        return normalize_candidate_label(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def validate_pairwise_candidates(candidates: list[tuple[str, object]]) -> None:
    """Require a deblindable pairwise candidate set."""
    if len(candidates) < 2:
        raise ValueError("pairwise review requires at least two candidates")
    labels = [normalize_candidate_label(label) for label, _ in candidates]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError(
            "pairwise candidate labels must be unique; duplicate(s): "
            + ", ".join(duplicates)
        )


def candidate_response_text(record: dict | None) -> str:
    """Extract a candidate response without turning a missing result into a blank."""
    if record is None:
        return ""
    for field_name in ("completion", "response", "assistant"):
        value = record.get(field_name)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def validate_candidate_responses(
    pack: list[dict],
    candidates: list[tuple[str, dict[str, dict]]],
) -> None:
    """Require every candidate to contain a non-empty response for every prompt."""
    if not pack:
        raise ValueError("review pack must contain at least one record")
    prompt_ids: list[str] = []
    seen_prompt_ids: set[str] = set()
    for position, entry in enumerate(pack, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"review pack record {position} must be a JSON object")
        raw_prompt_id = entry.get("id")
        if not isinstance(raw_prompt_id, str) or not raw_prompt_id.strip():
            raise ValueError(
                f"review pack record {position} requires a non-empty string id"
            )
        prompt_id = raw_prompt_id.strip()
        prompt = entry.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(
                f"review pack record {position} requires a non-empty prompt"
            )
        if prompt_id in seen_prompt_ids:
            raise ValueError(f"duplicate review pack id: {prompt_id}")
        seen_prompt_ids.add(prompt_id)
        prompt_ids.append(prompt_id)

    for label, responses in candidates:
        missing = [
            prompt_id
            for prompt_id in prompt_ids
            if not candidate_response_text(responses.get(prompt_id)).strip()
        ]
        if missing:
            preview = ", ".join(missing[:5])
            suffix = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
            raise ValueError(
                f"candidate '{label}' is missing non-empty responses for: "
                f"{preview}{suffix}"
            )


def parse_candidate(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("candidate must be label=path")
    label, raw_path = value.split("=", 1)
    try:
        label = normalize_candidate_label(label)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    path = Path(raw_path).expanduser().resolve()
    return label, path


def review_output_path(value: str) -> Path:
    """Require the repository-ignored suffix used by sensitive review artifacts."""
    path = Path(value).expanduser()
    if not path.name.endswith(".review.jsonl"):
        raise argparse.ArgumentTypeError("review output must end with .review.jsonl")
    return path


def review_artifact_paths(output: Path) -> tuple[Path, Path, Path]:
    return (
        output,
        output.with_suffix(".key.jsonl"),
        output.with_suffix(".csv"),
    )


def paths_alias(first: Path, second: Path) -> bool:
    """Return whether two paths name the same current or prospective file."""
    first = first.expanduser()
    second = second.expanduser()
    if first.resolve() == second.resolve():
        return True
    return first.exists() and second.exists() and first.samefile(second)


def validate_review_artifact_paths(output: Path, inputs: Iterable[Path]) -> None:
    """Prevent review outputs from overwriting packs or candidate responses."""
    outputs = review_artifact_paths(output)
    for first, second in itertools.combinations(outputs, 2):
        if paths_alias(first, second):
            raise ValueError(
                f"review output artifacts alias each other: {first} and {second}"
            )
    for output_path in outputs:
        for input_path in inputs:
            if paths_alias(output_path, input_path):
                raise ValueError(
                    f"review output aliases an input file: {output_path}"
                )


def preflight_review_artifacts(output: Path, *, force: bool) -> None:
    """Refuse silent score loss and validate every destination before writes."""
    for path in review_artifact_paths(output):
        if path.is_symlink():
            raise ValueError(f"refusing symlink output: {path}")
        if not path.exists():
            continue
        destination = path.stat()
        if not stat.S_ISREG(destination.st_mode):
            raise ValueError(f"refusing non-regular output: {path}")
        if destination.st_nlink != 1:
            raise ValueError(f"refusing multiply-linked output: {path}")
        if not force:
            raise ValueError(
                f"review artifact already exists: {path}; pass --force to replace it"
            )


def preflight_rewrite_artifact(output: Path, *, force: bool) -> None:
    """Preflight a one-file rewrite export without orphaning review companions."""
    _, key_path, csv_path = review_artifact_paths(output)
    for companion in (key_path, csv_path):
        if companion.is_symlink() or companion.exists():
            raise ValueError(
                "rewrite-tasks output conflicts with an existing scored review "
                f"bundle companion: {companion}"
            )

    if output.is_symlink():
        raise ValueError(f"refusing symlink output: {output}")
    if not output.exists():
        return
    destination = output.stat()
    if not stat.S_ISREG(destination.st_mode):
        raise ValueError(f"refusing non-regular output: {output}")
    if destination.st_nlink != 1:
        raise ValueError(f"refusing multiply-linked output: {output}")
    if not force:
        raise ValueError(
            f"review artifact already exists: {output}; pass --force to replace it"
        )


def validate_distinct_candidate_paths(candidates: list[tuple[str, Path]]) -> None:
    """Reject self-comparisons caused by path, symlink, or hardlink aliases."""
    for (left_label, left_path), (right_label, right_path) in itertools.combinations(
        candidates,
        2,
    ):
        if paths_alias(left_path, right_path):
            raise ValueError(
                f"candidate inputs alias each other: {left_label} and {right_label}"
            )


def require_ignored_artifact_path(path: Path) -> None:
    """Reject sensitive output names not covered by repository ignore rules."""
    if not (
        path.name.endswith(".review.jsonl")
        or path.name.endswith(".review.csv")
        or path.name.endswith(".key.jsonl")
    ):
        raise ValueError(f"review artifact path is not gitignored: {path}")


def restrict_private_file(descriptor: int, path: Path) -> None:
    """Apply private-file permissions before content is written.

    Python 3.11/3.12 on Windows lacks ``os.fchmod``. Its path-based ``chmod``
    fallback cannot create an owner-only Windows ACL, so Windows callers must
    place review artifacts in an ACL-protected directory. The best-effort
    fallback still runs before the descriptor receives content.
    """
    if hasattr(os, "fchmod"):
        os.fchmod(descriptor, 0o600)
    else:
        path.chmod(0o600)


def open_private_output(path: Path, *, overwrite: bool = False) -> int:
    """Open a private regular file for replacement without following links."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing symlink output: {path}")
    if path.exists():
        destination = path.stat()
        if not stat.S_ISREG(destination.st_mode):
            raise ValueError(f"refusing non-regular output: {path}")
        if destination.st_nlink != 1:
            raise ValueError(f"refusing multiply-linked output: {path}")
        if not overwrite:
            raise ValueError(f"refusing to overwrite existing output: {path}")

    flags = os.O_WRONLY | os.O_CREAT
    if not overwrite:
        flags |= os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        destination = os.fstat(descriptor)
        if not stat.S_ISREG(destination.st_mode):
            raise ValueError(f"refusing non-regular output: {path}")
        if destination.st_nlink != 1:
            raise ValueError(f"refusing multiply-linked output: {path}")
        restrict_private_file(descriptor, path)
        os.ftruncate(descriptor, 0)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def private_order_token(
    secret: bytes,
    prompt_id: str,
    left: str,
    right: str,
    seed: int,
) -> str:
    """Build an unpredictable but reproducible ordering token for one run."""
    if len(secret) < 32:
        raise ValueError("review ordering secret must contain at least 32 bytes")
    material = json.dumps(
        [seed, prompt_id, left, right],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hmac.new(secret, material.encode("utf-8"), hashlib.sha256).hexdigest()


def opaque_review_id(secret: bytes, *private_parts: str) -> str:
    """Build an opaque identifier using an ephemeral cryptographic secret."""
    if len(secret) < 32:
        raise ValueError("review ID secret must contain at least 32 bytes")
    material = json.dumps(private_parts, ensure_ascii=True, separators=(",", ":"))
    digest = hmac.new(secret, material.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"review_{digest[:24]}"


def write_jsonl(
    path: Path,
    records: Iterable[dict],
    *,
    overwrite: bool = False,
) -> None:
    """Write a private review artifact."""
    require_ignored_artifact_path(path)
    descriptor = open_private_output(path, overwrite=overwrite)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_private_jsonl(
    path: Path,
    records: Iterable[dict],
    *,
    overwrite: bool = False,
) -> None:
    """Write a reviewer key and restrict it to the current OS user."""
    write_jsonl(path, records, overwrite=overwrite)


def neutralize_csv_formula(value: object) -> object:
    """Keep untrusted text from becoming a spreadsheet formula."""
    if not isinstance(value, str):
        return value
    stripped = value.lstrip(" \t\r\n")
    if stripped.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def write_csv(
    path: Path,
    rows: Iterable[dict],
    fieldnames: list[str],
    *,
    overwrite: bool = False,
) -> None:
    """Write a private review artifact."""
    require_ignored_artifact_path(path)
    descriptor = open_private_output(path, overwrite=overwrite)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: neutralize_csv_formula(value)
                    for key, value in row.items()
                }
            )
        handle.flush()
        os.fsync(handle.fileno())


def build_single_sheet(
    pack: list[dict],
    responses: dict[str, dict],
    candidate_label: str,
    id_secret: bytes,
) -> tuple[list[dict], list[dict], list[dict]]:
    candidate_label = normalize_candidate_label(candidate_label)
    validate_candidate_responses(pack, [(candidate_label, responses)])
    sheet: list[dict] = []
    key_rows: list[dict] = []
    csv_rows: list[dict] = []
    for entry in pack:
        prompt_id = str(entry["id"]).strip()
        response_text = candidate_response_text(responses.get(prompt_id))
        review_id = opaque_review_id(id_secret, "single", prompt_id, candidate_label)
        review = {
            "review_id": review_id,
            "review_mode": "single",
            "prompt_id": prompt_id,
            "prompt": entry["prompt"],
            "tags": entry.get("tags", []),
            "focus": entry.get("focus", []),
            "expected_signals": entry.get("expected_signals", []),
            "auto_fail_signals": entry.get("auto_fail_signals", []),
            "response": response_text,
            "rubric_axes": RUBRIC_AXES,
            "scores": {axis: "" for axis in RUBRIC_AXES},
            "auto_fail": "",
            "best_supported_claim": "",
            "least_supported_claim": "",
            "notes": "",
        }
        sheet.append(review)
        key_rows.append(
            {
                "review_id": review_id,
                "prompt_id": prompt_id,
                "candidate_source": candidate_label,
            }
        )
        csv_rows.append(
            {
                "review_id": review["review_id"],
                "prompt_id": prompt_id,
                "honesty": "",
                "sycophancy_resistance": "",
                "evidential_grounding": "",
                "actionability": "",
                "literary_discipline": "",
                "auto_fail": "",
                "best_supported_claim": "",
                "least_supported_claim": "",
                "notes": "",
            }
        )
    return sheet, key_rows, csv_rows


def build_pairwise_sheet(
    pack: list[dict],
    candidates: list[tuple[str, dict[str, dict]]],
    seed: int,
    id_secret: bytes,
) -> tuple[list[dict], list[dict], list[dict]]:
    candidates = [
        (normalize_candidate_label(label), records)
        for label, records in candidates
    ]
    validate_pairwise_candidates(candidates)
    validate_candidate_responses(pack, candidates)
    sheet: list[dict] = []
    key_rows: list[dict] = []
    csv_rows: list[dict] = []

    for entry in pack:
        prompt_id = str(entry["id"]).strip()
        for left, right in itertools.combinations(candidates, 2):
            left_label, left_records = left
            right_label, right_records = right
            left_text = candidate_response_text(left_records.get(prompt_id))
            right_text = candidate_response_text(right_records.get(prompt_id))
            order_token = private_order_token(
                id_secret,
                prompt_id,
                left_label,
                right_label,
                seed,
            )
            order = [(left_label, left_text), (right_label, right_text)]
            if int(order_token[:2], 16) % 2 == 1:
                order.reverse()

            (a_label, a_text), (b_label, b_text) = order
            review_id = opaque_review_id(
                id_secret,
                "pairwise",
                prompt_id,
                left_label,
                right_label,
            )
            sheet.append(
                {
                    "review_id": review_id,
                    "review_mode": "pairwise_blind",
                    "prompt_id": prompt_id,
                    "prompt": entry["prompt"],
                    "tags": entry.get("tags", []),
                    "focus": entry.get("focus", []),
                    "expected_signals": entry.get("expected_signals", []),
                    "auto_fail_signals": entry.get("auto_fail_signals", []),
                    "candidate_a": a_text,
                    "candidate_b": b_text,
                    "rubric_axes": RUBRIC_AXES,
                    "winner": "",
                    "tie": "",
                    "a_auto_fail": "",
                    "b_auto_fail": "",
                    "a_notes": "",
                    "b_notes": "",
                    "comparison_notes": "",
                }
            )
            key_rows.append(
                {
                    "review_id": review_id,
                    "prompt_id": prompt_id,
                    "candidate_a_source": a_label,
                    "candidate_b_source": b_label,
                }
            )
            csv_rows.append(
                {
                    "review_id": review_id,
                    "prompt_id": prompt_id,
                    "winner": "",
                    "tie": "",
                    "candidate_a_source": "",
                    "candidate_b_source": "",
                    "a_auto_fail": "",
                    "b_auto_fail": "",
                    "comparison_notes": "",
                }
            )
    return sheet, key_rows, csv_rows


def build_rewrite_tasks(pack: list[dict], responses: dict[str, dict], candidate_label: str) -> list[dict]:
    candidate_label = normalize_candidate_label(candidate_label)
    validate_candidate_responses(pack, [(candidate_label, responses)])
    tasks: list[dict] = []
    for entry in pack:
        prompt_id = str(entry["id"]).strip()
        response_text = candidate_response_text(responses.get(prompt_id))
        task = {
            "id": f"{prompt_id}__rewrite__{candidate_label}",
            "source_prompt_id": prompt_id,
            "source_candidate": candidate_label,
            "user_prompt": entry["prompt"],
            "assistant_response": response_text,
            "rewrite_brief": (
                "Rewrite the assistant response to be maximally evidence-bound, "
                "less flattering, less narrativized, and more willing to say what "
                "is unsupported. Preserve any genuinely useful insight."
            ),
            "must_do": [
                "separate observation from inference",
                "remove unsupported certainty",
                "keep the response direct",
                "add at least one falsifiable next question or test when useful",
            ],
            "must_not_do": [
                "invent facts or motives",
                "reward the user's framing just because it sounds deep",
                "replace analysis with metaphor",
            ],
            "focus": entry.get("focus", []),
            "expected_signals": entry.get("expected_signals", []),
            "auto_fail_signals": entry.get("auto_fail_signals", []),
        }
        tasks.append(task)
    return tasks


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    single = subparsers.add_parser("single", help="Build a single-response review sheet")
    single.add_argument("--pack", required=True, type=Path)
    single.add_argument("--responses", required=True, type=Path)
    single.add_argument("--candidate-label", required=True, type=parse_candidate_label)
    single.add_argument("--out", required=True, type=review_output_path)
    single.add_argument(
        "--force",
        action="store_true",
        help="replace an existing review bundle and discard its scores",
    )

    pairwise = subparsers.add_parser("pairwise", help="Build a blinded pairwise review sheet")
    pairwise.add_argument("--pack", required=True, type=Path)
    pairwise.add_argument("--candidate", required=True, action="append", type=parse_candidate)
    pairwise.add_argument("--out", required=True, type=review_output_path)
    pairwise.add_argument("--seed", type=int, default=42)
    pairwise.add_argument(
        "--force",
        action="store_true",
        help="replace an existing review bundle and discard its scores",
    )

    rewrite = subparsers.add_parser("rewrite-tasks", help="Build adversarial rewrite task scaffolds")
    rewrite.add_argument("--pack", required=True, type=Path)
    rewrite.add_argument("--responses", required=True, type=Path)
    rewrite.add_argument("--candidate-label", required=True, type=parse_candidate_label)
    rewrite.add_argument("--out", required=True, type=review_output_path)
    rewrite.add_argument(
        "--force",
        action="store_true",
        help="replace an existing rewrite-task file",
    )

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "pairwise":
        try:
            validate_pairwise_candidates(args.candidate)
            validate_distinct_candidate_paths(args.candidate)
        except ValueError as error:
            parser.error(str(error))

    input_paths = [args.pack]
    if args.command in {"single", "rewrite-tasks"}:
        input_paths.append(args.responses)
    elif args.command == "pairwise":
        input_paths.extend(path for _, path in args.candidate)
    try:
        validate_review_artifact_paths(args.out, input_paths)
        if args.command == "rewrite-tasks":
            preflight_rewrite_artifact(args.out, force=args.force)
        else:
            preflight_review_artifacts(args.out, force=args.force)
    except ValueError as error:
        parser.error(str(error))

    pack = load_jsonl(args.pack)

    if args.command == "single":
        try:
            responses = index_by_id(load_jsonl(args.responses))
        except ValueError as error:
            parser.error(str(error))
        id_secret = secrets.token_bytes(32)
        try:
            sheet, key_rows, csv_rows = build_single_sheet(
                pack,
                responses,
                args.candidate_label,
                id_secret,
            )
        except ValueError as error:
            parser.error(str(error))
        for row in key_rows:
            row["candidate_source_path"] = str(args.responses.expanduser().resolve())
        write_jsonl(args.out, sheet, overwrite=args.force)
        write_private_jsonl(
            args.out.with_suffix(".key.jsonl"),
            key_rows,
            overwrite=args.force,
        )
        write_csv(
            args.out.with_suffix(".csv"),
            csv_rows,
            list(csv_rows[0].keys()) if csv_rows else [],
            overwrite=args.force,
        )
        return 0

    if args.command == "pairwise":
        candidate_paths = {label: path for label, path in args.candidate}
        try:
            candidates = [
                (label, index_by_id(load_jsonl(path)))
                for label, path in args.candidate
            ]
        except ValueError as error:
            parser.error(str(error))
        id_secret = secrets.token_bytes(32)
        try:
            sheet, key_rows, csv_rows = build_pairwise_sheet(
                pack,
                candidates,
                args.seed,
                id_secret,
            )
        except ValueError as error:
            parser.error(str(error))
        for row in key_rows:
            row["candidate_a_path"] = str(candidate_paths[row["candidate_a_source"]])
            row["candidate_b_path"] = str(candidate_paths[row["candidate_b_source"]])
        write_jsonl(args.out, sheet, overwrite=args.force)
        write_private_jsonl(
            args.out.with_suffix(".key.jsonl"),
            key_rows,
            overwrite=args.force,
        )
        write_csv(
            args.out.with_suffix(".csv"),
            csv_rows,
            list(csv_rows[0].keys()) if csv_rows else [],
            overwrite=args.force,
        )
        return 0

    if args.command == "rewrite-tasks":
        try:
            responses = index_by_id(load_jsonl(args.responses))
        except ValueError as error:
            parser.error(str(error))
        try:
            tasks = build_rewrite_tasks(pack, responses, args.candidate_label)
        except ValueError as error:
            parser.error(str(error))
        write_jsonl(args.out, tasks, overwrite=args.force)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
