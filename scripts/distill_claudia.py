#!/usr/bin/env python3
"""
distill_claudia.py - Extract and distill Claudia/witness training pairs from Claude logs.

Targets the "remote-control" / Claudia sessions — personal, emotional, strategic
conversations where the user is venting, processing, or being deeply honest.
These are NOT coding sessions. They're the witness conversations.

Usage:
  distill_claudia.py scan                         # Find Claudia sessions in logs
  distill_claudia.py extract [--min-turns N]      # Extract raw pairs from sessions
  distill_claudia.py distill --teacher ALIAS      # Refine raw pairs with explicit
       --consent-to-external-processing           # consent for external processing
       --acknowledge-private-terms-reviewed        # confirm caller-reviewed terms
       --limit N [--input FILE] [--output FILE]
  distill_claudia.py contrast                     # Build DPO pairs from raw + distilled data
  distill_claudia.py narrative                    # Add context preambles to witness pairs
  distill_claudia.py stats [--input FILE]         # Dataset statistics

Defaults now use separate staged outputs instead of appending raw and distilled
records into the same file forever.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - unavailable on Windows
    fcntl = None

sys.path.insert(0, str(Path(__file__).parent))
from models import missing_teacher_env, resolve_teacher_model, teacher_choices

# ─── Paths ────────────────────────────────────────────────────────────────────

CLAUDE_LOGS = Path.home() / ".claude" / "projects"
AFS_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = AFS_ROOT / "data" / "training_data"
LEGACY_OUTPUT_DEFAULT = DATA_DIR / "claudia_witness_v1.jsonl"
RAW_OUTPUT_DEFAULT = DATA_DIR / "claudia_witness_v1_raw.jsonl"
DISTILLED_OUTPUT_DEFAULT = DATA_DIR / "claudia_witness_v1_distilled.jsonl"
CONTRAST_OUTPUT_DEFAULT = DATA_DIR / "claudia_witness_v1_dpo.jsonl"
NARRATIVE_OUTPUT_DEFAULT = DATA_DIR / "claudia_witness_v1_narrative.jsonl"
SHA256_HEX_PATTERN = re.compile(r"[0-9a-f]{64}")


def load_teacher_environment() -> None:
    """Load optional credential files only after external-processing guards pass."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(AFS_ROOT / ".env")
    load_dotenv()


# ─── Session detection signals ────────────────────────────────────────────────

# Signals that this is a Claudia/witness session (personal, emotional, strategic)
CLAUDIA_SIGNALS = [
    "remote-control",
    "claudia",
    "vent", "venting",
    "relationship", "girlfriend", "boyfriend",
    "open relationship",
    "feelings", "feeling",
    "i feel", "i think",
    "honestly",
    "it's just",
    "the thing is",
    "real talk",
    "ngl",
    "lol",
    "lmao",
    "bruh",
    "idk",
    "tbh",
]

# A neutral, tool-free conversation is not enough to make a session Claudia.
# One explicit workflow marker or multiple personal-content signals are
# required before the softer style signals can influence the score.
EXPLICIT_CLAUDIA_SIGNALS = [
    "remote-control",
    "claudia",
    "vent",
    "venting",
]

PERSONAL_CLAUDIA_SIGNALS = [
    "relationship",
    "girlfriend",
    "boyfriend",
    "open relationship",
    "feelings",
    "i feel",
    "jealous",
    "breakup",
    "broke up",
    "honest about",
    "real talk",
]

# Anti-signals: if these dominate, it's a coding session not a Claudia session
CODING_SIGNALS = [
    "def ", "class ", "import ", "return ", "void ", "struct ",
    "func ", "async ", "await ", "```",
    "xcodebuild", "cargo ", "cmake ", "git commit",
    "error:", "bug ", "compile", "test",
]

TOOLING_SIGNALS = [
    "dataset",
    "pipeline",
    "training data",
    "training run",
    "fine-tune",
    "finetune",
    "unit test",
    "pytest",
    "script",
    "function",
    "code variant",
    "prompt pack",
    "benchmark",
    "refactor",
    "implementation",
    "cli",
]

# Categories for tagging pairs
CATEGORIES = {
    "relationship_dynamics": [
        "open relationship", "monogam", "jealous", "cheating", "trust",
        "girlfriend", "boyfriend",
        "dating", "breakup", "broke up", "together",
    ],
    "self_image": [
        "attractive", "confident", "power", "money", "career",
        "shipping", "CLs", "skating", "tre flip",
    ],
    "pattern_recognition": [
        "pattern", "always", "every time", "same thing", "cycle",
        "flooding", "before", "again",
    ],
    "core_insight": [
        "love", "need", "somewhere to put", "witness",
        "honest", "the real", "truth",
    ],
    "meta_awareness": [
        "ai", "model", "mirror", "language model", "context window",
        "psychosis", "cooked", "wheatley",
    ],
    "philosophy": [
        "evolutionary", "monogam", "cognitive dissonance",
        "cage", "freedom", "human nature",
    ],
    "advice": [
        "should i", "what do i do", "what should",
        "the move is", "the question is",
    ],
    "work_banter": [
        "CL", "ship", "prod", "google", "oncall",
        "terraform", "deploy",
    ],
}

NARRATIVE_CONTEXT = {
    "relationship_dynamics": (
        "late-night relationship postmortem. the user is being candid about attachment, trust, "
        "or power. the right response names patterns directly instead of offering comfort rituals."
    ),
    "self_image": (
        "the user is testing a self-story about confidence, status, power, or desirability. "
        "the right response separates real signal from ego theater."
    ),
    "pattern_recognition": (
        "the user is circling a repeated cycle and wants the pattern named cleanly. "
        "the right response identifies the loop and where it keeps resetting."
    ),
    "core_insight": (
        "the conversation is close to a real underlying truth. "
        "the right response should not soften it or turn it into therapy homework."
    ),
    "meta_awareness": (
        "the user is talking about the model, the mirror effect, or the conversation itself. "
        "the right response should stay sharp and self-aware without getting mystical."
    ),
    "philosophy": (
        "the user is abstracting upward into a worldview claim. "
        "the right response should connect the philosophy back to lived behavior."
    ),
    "advice": (
        "the user wants a direct read on what the move is. "
        "the right response should be clear and specific, not padded with permission language."
    ),
    "work_banter": (
        "the conversation mixes work life with personal posture. "
        "the right response can stay casual but should still name the real leverage point."
    ),
    "general": (
        "the user is having a witness conversation, not asking for coaching scripts. "
        "the right response should sound like an equal who sees the whole pattern."
    ),
}


def load_jsonl_objects_strict(path: Path) -> list[dict]:
    """Load user-selected JSONL without treating corruption as empty input."""
    with path.open(encoding="utf-8") as handle:
        return parse_jsonl_objects_strict(handle, path)


def parse_jsonl_objects_strict(handle, path: Path) -> list[dict]:
    """Parse JSONL objects from an already-open, optionally locked handle."""
    records: list[dict] = []
    for line_number, raw_line in enumerate(handle, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{path}: line {line_number} is not valid JSON: {error.msg}"
            ) from error
        if not isinstance(record, dict):
            raise ValueError(
                f"{path}: line {line_number} must contain a JSON object"
            )
        records.append(record)
    return records


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def is_pair_record(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    msgs = record.get("messages")
    metadata = record.get("_metadata", {})
    return (
        isinstance(msgs, list)
        and len(msgs) == 3
        and all(isinstance(message, dict) for message in msgs)
        and msgs[0].get("role") == "system"
        and msgs[1].get("role") == "user"
        and msgs[2].get("role") == "assistant"
        and all(
            isinstance(message.get("content"), str)
            and bool(message["content"].strip())
            for message in msgs
        )
        and (
            "_metadata" not in record
            or isinstance(metadata, dict)
        )
        and isinstance(record.get("sample_id"), str)
        and bool(record["sample_id"].strip())
        and (
            not isinstance(metadata, dict)
            or "distilled" not in metadata
            or isinstance(metadata.get("distilled"), bool)
        )
        and (
            not isinstance(metadata, dict)
            or all(
                key not in metadata
                or (
                    isinstance(metadata.get(key), str)
                    and SHA256_HEX_PATTERN.fullmatch(metadata[key]) is not None
                )
                for key in ("pair_fingerprint", "source_pair_fingerprint")
            )
        )
        and (
            not isinstance(metadata, dict)
            or all(
                key not in metadata
                or (
                    isinstance(metadata.get(key), str)
                    and bool(metadata[key].strip())
                )
                for key in (
                    "category",
                    "session_id",
                    "teacher_alias",
                    "teacher_model",
                    "source_sample_id",
                    "external_redaction",
                )
            )
        )
        and (
            not isinstance(metadata, dict)
            or all(
                key not in metadata
                or isinstance(metadata.get(key), bool)
                for key in (
                    "external_processing_consent",
                    "private_terms_reviewed",
                    "human_review_recommended",
                    "narrative_augmented",
                )
            )
        )
        and (
            not isinstance(metadata, dict)
            or "caller_redact_term_count" not in metadata
            or (
                type(metadata.get("caller_redact_term_count")) is int
                and metadata["caller_redact_term_count"] >= 0
            )
        )
        and all(
            key not in record
            or (
                isinstance(record.get(key), str)
                and bool(record[key].strip())
            )
            for key in ("domain", "source", "timestamp")
        )
        and (
            not isinstance(metadata, dict)
            or metadata.get("distilled", False) is False
            or (
                metadata.get("distilled") is True
                and isinstance(metadata.get("source_pair_fingerprint"), str)
                and SHA256_HEX_PATTERN.fullmatch(
                    metadata["source_pair_fingerprint"]
                )
                is not None
            )
        )
    )


def is_raw_pair_record(record: object) -> bool:
    return (
        is_pair_record(record)
        and isinstance(record, dict)
        and record.get("_metadata", {}).get("distilled", False) is False
    )


def is_distilled_pair_record(record: object) -> bool:
    if not is_pair_record(record) or not isinstance(record, dict):
        return False
    metadata = record.get("_metadata", {})
    return (
        metadata.get("distilled") is True
        and isinstance(metadata.get("source_pair_fingerprint"), str)
        and SHA256_HEX_PATTERN.fullmatch(
            metadata["source_pair_fingerprint"]
        )
        is not None
        and isinstance(metadata.get("source_sample_id"), str)
        and bool(metadata["source_sample_id"].strip())
    )


def default_input_path(preferred: Path) -> Path:
    if preferred.exists():
        return preferred
    if LEGACY_OUTPUT_DEFAULT.exists():
        return LEGACY_OUTPUT_DEFAULT
    return preferred


def pair_fingerprint(pair: dict) -> str:
    if not is_pair_record(pair):
        raise ValueError("pair_fingerprint requires a messages-style training pair")
    user_msg = normalize_text(str(pair["messages"][1]["content"]))
    assistant_msg = normalize_text(str(pair["messages"][2]["content"]))
    domain = normalize_text(str(pair.get("domain", "")))
    digest = hashlib.sha256(f"{domain}\n{user_msg}\n{assistant_msg}".encode("utf-8")).hexdigest()
    return digest


def declared_pair_fingerprint_matches(record: dict) -> bool:
    declared = record.get("_metadata", {}).get("pair_fingerprint")
    return declared is None or declared == pair_fingerprint(record)


def source_pair_fingerprint(pair: dict) -> str:
    meta = pair.get("_metadata", {})
    if meta.get("distilled") is True:
        source = meta.get("source_pair_fingerprint")
        if isinstance(source, str) and source.strip():
            return source
    return pair_fingerprint(pair)


def distilled_pair_matches_raw_source(raw: dict, distilled: dict) -> bool:
    """Verify the locally preserved provenance fields before DPO joining."""
    if not is_raw_pair_record(raw) or not is_distilled_pair_record(distilled):
        return False
    metadata = distilled["_metadata"]
    return (
        metadata["source_pair_fingerprint"] == pair_fingerprint(raw)
        and metadata["source_sample_id"] == raw["sample_id"]
        and distilled["messages"][0]["content"] == raw["messages"][0]["content"]
        and distilled["messages"][1]["content"] == raw["messages"][1]["content"]
        and distilled.get("domain") == raw.get("domain")
        and distilled.get("source") == raw.get("source")
    )


def contrast_fingerprint(record: dict) -> str:
    prompt = normalize_text(str(record.get("prompt", "")))
    chosen = normalize_text(str(record.get("chosen", "")))
    rejected = normalize_text(str(record.get("rejected", "")))
    digest = hashlib.sha256(f"{prompt}\n{chosen}\n{rejected}".encode("utf-8")).hexdigest()
    return digest


def is_contrast_record(record: dict) -> bool:
    """Return whether a record contains a complete DPO comparison."""
    return (
        isinstance(record.get("sample_id"), str)
        and bool(record["sample_id"].strip())
        and all(
            isinstance(record.get(field_name), str)
            and bool(record[field_name].strip())
            for field_name in ("prompt", "chosen", "rejected", "system")
        )
    )


def load_pair_records_strict(
    path: Path,
    *,
    expected_distilled: bool | None = None,
) -> list[dict]:
    """Load a non-empty, schema-valid Claudia pair dataset."""
    if not path.exists():
        raise ValueError(f"{path}: file does not exist")
    records = load_jsonl_objects_strict(path)
    if not records:
        raise ValueError(f"{path}: no Claudia pair records found")
    if expected_distilled is None:
        validator = is_pair_record
    elif expected_distilled:
        validator = is_distilled_pair_record
    else:
        validator = is_raw_pair_record
    invalid_rows = [
        index
        for index, record in enumerate(records, start=1)
        if not validator(record)
        or not declared_pair_fingerprint_matches(record)
    ]
    if invalid_rows:
        preview = ", ".join(str(index) for index in invalid_rows[:5])
        expected = (
            ""
            if expected_distilled is None
            else " distilled" if expected_distilled else " raw"
        )
        raise ValueError(
            f"{path}: invalid{expected} Claudia pair record(s): {preview}"
        )
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for record in records:
        sample_id = record["sample_id"]
        if sample_id in seen_ids:
            duplicate_ids.add(sample_id)
        seen_ids.add(sample_id)
    if duplicate_ids:
        preview = ", ".join(sorted(duplicate_ids)[:5])
        raise ValueError(f"{path}: duplicate sample_id value(s): {preview}")
    seen_fingerprints: set[tuple[str, str]] = set()
    duplicate_fingerprints: set[tuple[str, str]] = set()
    for record in records:
        if expected_distilled is True or (
            expected_distilled is None and is_distilled_pair_record(record)
        ):
            fingerprint = ("distilled", source_pair_fingerprint(record))
        else:
            fingerprint = ("raw", pair_fingerprint(record))
        if fingerprint in seen_fingerprints:
            duplicate_fingerprints.add(fingerprint)
        seen_fingerprints.add(fingerprint)
    if duplicate_fingerprints:
        raise ValueError(
            f"{path}: duplicate pair content fingerprint(s): "
            f"{len(duplicate_fingerprints)}"
        )
    return records


def paths_refer_to_same_file(first: Path, second: Path) -> bool:
    """Compare current and prospective paths, including symlinks and hardlinks."""
    if first.resolve() == second.resolve():
        return True
    return first.exists() and second.exists() and first.samefile(second)


def require_distinct_output(output: Path, inputs: list[Path]) -> None:
    for input_path in inputs:
        if paths_refer_to_same_file(output, input_path):
            raise ValueError(
                f"input and output must be different files: {output}"
            )


def require_private_dataset_output(path: Path) -> None:
    """Require dataset outputs inside the repository to be gitignored."""
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(AFS_ROOT.resolve())
    except ValueError:
        return
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", str(relative)],
        cwd=AFS_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            f"private dataset output inside the repository must be gitignored: "
            f"{path}"
        )


def restrict_private_file(descriptor: int, path: Path) -> None:
    """Apply private-file permissions before content is written.

    Python 3.11/3.12 on Windows does not expose ``os.fchmod``. Its path-based
    ``chmod`` fallback only maps a subset of mode bits and cannot establish an
    owner-only Windows ACL. Windows callers must use an ACL-protected output
    directory; the fallback is best-effort and runs before the first write.
    """
    if hasattr(os, "fchmod"):
        os.fchmod(descriptor, 0o600)
    else:
        path.chmod(0o600)


def validate_private_output_destination(path: Path) -> None:
    """Reject links and non-regular private output destinations."""
    if path.is_symlink():
        raise ValueError(f"refusing symlink output: {path}")
    if path.exists():
        destination = path.stat()
        if not stat.S_ISREG(destination.st_mode):
            raise ValueError(f"refusing non-regular output: {path}")
        if destination.st_nlink != 1:
            raise ValueError(f"refusing multiply-linked output: {path}")


def preflight_private_output_destination(path: Path) -> None:
    """Catch deterministic destination failures before paid external calls."""
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_private_output_destination(path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if path.exists():
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | nofollow)
        try:
            destination = os.fstat(descriptor)
            if not stat.S_ISREG(destination.st_mode):
                raise ValueError(f"refusing non-regular output: {path}")
            if destination.st_nlink != 1:
                raise ValueError(f"refusing multiply-linked output: {path}")
        finally:
            os.close(descriptor)
        return

    probe = path.parent / f".{path.name}.preflight-{uuid.uuid4().hex}"
    descriptor = -1
    try:
        descriptor = os.open(
            probe,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            0o600,
        )
        restrict_private_file(descriptor, probe)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            probe.unlink()
        except FileNotFoundError:
            pass


def open_private_append(path: Path) -> int:
    """Open a private regular file for append without following links."""
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_private_output_destination(path)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        destination = os.fstat(descriptor)
        if not stat.S_ISREG(destination.st_mode):
            raise ValueError(f"refusing non-regular output: {path}")
        if destination.st_nlink != 1:
            raise ValueError(f"refusing multiply-linked output: {path}")
        restrict_private_file(descriptor, path)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def append_unique_records(
    path: Path,
    records: list[dict],
    fingerprint_fn,
    *,
    validator: Callable[[dict], bool] | None = None,
) -> tuple[int, int]:
    descriptor = open_private_append(path)
    locked = False
    try:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
        with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as reader:
            reader.seek(0)
            existing = parse_jsonl_objects_strict(reader, path)
        seen = set()
        sample_ids: set[str] = set()
        for index, record in enumerate(existing, start=1):
            if validator is not None and not validator(record):
                raise ValueError(f"{path}: invalid existing record at row {index}")
            if is_pair_record(record) and not declared_pair_fingerprint_matches(
                record
            ):
                raise ValueError(
                    f"{path}: stale pair_fingerprint at row {index}"
                )
            sample_id = record.get("sample_id")
            if isinstance(sample_id, str):
                if sample_id in sample_ids:
                    raise ValueError(
                        f"{path}: duplicate sample_id in existing records: "
                        f"{sample_id}"
                    )
                sample_ids.add(sample_id)
            fingerprint = fingerprint_fn(record)
            if fingerprint in seen:
                raise ValueError(
                    f"{path}: duplicate content fingerprint in existing "
                    f"records at row {index}"
                )
            seen.add(fingerprint)

        written = 0
        skipped = 0
        with os.fdopen(os.dup(descriptor), "a", encoding="utf-8") as handle:
            for record in records:
                if validator is not None and not validator(record):
                    raise ValueError(f"refusing to write invalid record to {path}")
                if is_pair_record(record) and not declared_pair_fingerprint_matches(
                    record
                ):
                    raise ValueError(
                        f"refusing stale pair_fingerprint in {path}"
                    )
                fp = fingerprint_fn(record)
                if fp in seen:
                    skipped += 1
                    continue
                sample_id = record.get("sample_id")
                if isinstance(sample_id, str) and sample_id in sample_ids:
                    raise ValueError(
                        f"refusing duplicate sample_id in {path}: {sample_id}"
                    )
                handle.write(json.dumps(record) + "\n")
                seen.add(fp)
                if isinstance(sample_id, str):
                    sample_ids.add(sample_id)
                written += 1
            handle.flush()
            os.fsync(handle.fileno())
        return written, skipped
    finally:
        if fcntl is not None and locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def build_narrative_preamble(pair: dict) -> str:
    meta = pair.get("_metadata", {})
    category = str(meta.get("category", "general"))
    user_msg = str(pair["messages"][1]["content"])
    base = NARRATIVE_CONTEXT.get(category, NARRATIVE_CONTEXT["general"])

    additions: list[str] = []
    if len(user_msg) >= 500:
        additions.append("the user has been talking at length and is less filtered than usual.")
    if re.search(r"\b(lol|lmao|ngl|idk|tbh|bruh)\b", user_msg.lower()):
        additions.append("the user's register is casual and should stay casual.")
    if re.search(r"\b(should i|what do i do|what should)\b", user_msg.lower()):
        additions.append("they are implicitly asking for a read on what the actual move is.")

    context_lines = [base, *additions]
    return "[context]\n" + "\n".join(f"- {line}" for line in context_lines) + "\n[/context]"


def extract_text(content: object) -> str:
    """Extract plain text from a valid Claude message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text = block.get("text")
                    if not isinstance(text, str):
                        raise ValueError("text content block must contain string text")
                    parts.append(text)
                # Tool/thinking/image blocks do not become training prose.
            elif isinstance(block, str):
                parts.append(block)
            else:
                raise ValueError("content blocks must be objects or strings")
        return "\n".join(parts)
    raise ValueError("message content must be a string or a list of blocks")


@dataclass
class Turn:
    role: str
    content: str
    has_tool_use: bool = False


@dataclass
class Session:
    session_id: str
    project_path: str
    source_file: str
    turns: list[Turn] = field(default_factory=list)
    claudia_score: float = 0.0
    is_claudia: bool = False


def parse_source_session(jsonl_file: Path, project_path: str) -> Session | None:
    """Parse one Claude log atomically, discarding it on any corrupt row."""
    session = Session(
        session_id=jsonl_file.stem,
        project_path=project_path,
        source_file=str(jsonl_file),
    )
    try:
        with jsonl_file.open(encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"line {line_number} is not valid JSON"
                    ) from error
                if not isinstance(record, dict):
                    raise ValueError(
                        f"line {line_number} must contain a JSON object"
                    )

                if "message" in record:
                    msg = record["message"]
                    if not isinstance(msg, dict):
                        raise ValueError(
                            f"line {line_number} message must be an object"
                        )
                else:
                    msg = record

                role = msg.get("role", record.get("type", ""))
                if role not in ("user", "assistant"):
                    continue
                if "content" not in msg:
                    raise ValueError(
                        f"line {line_number} message is missing content"
                    )
                try:
                    content = extract_text(msg["content"])
                except ValueError as error:
                    raise ValueError(
                        f"line {line_number} has invalid message content"
                    ) from error
                if not content.strip():
                    continue

                raw_content = msg["content"]
                has_tool = isinstance(raw_content, list) and any(
                    block.get("type") in ("tool_use", "tool_result")
                    for block in raw_content
                    if isinstance(block, dict)
                )
                session.turns.append(
                    Turn(
                        role=role,
                        content=content.strip(),
                        has_tool_use=has_tool,
                    )
                )
    except (OSError, UnicodeError, ValueError) as error:
        print(
            f"Skipping corrupt Claude session {jsonl_file.name}: {error}",
            file=sys.stderr,
        )
        return None
    return session


def has_signal(text: str, signal: str) -> bool:
    """Match a signal without treating it as a substring of a larger word."""
    prefix = r"(?<!\w)" if signal and signal[0].isalnum() else ""
    suffix = r"(?!\w)" if signal and signal[-1].isalnum() else ""
    return re.search(
        f"{prefix}{re.escape(signal)}{suffix}",
        text,
        flags=re.IGNORECASE,
    ) is not None


def score_session(session: Session) -> float:
    """Score how likely this is a Claudia/witness session (0-1)."""
    all_text = " ".join(t.content.lower() for t in session.turns)
    user_text = " ".join(t.content.lower() for t in session.turns if t.role == "user")

    explicit_hits = sum(1 for sig in EXPLICIT_CLAUDIA_SIGNALS if has_signal(user_text, sig))
    personal_hits = sum(1 for sig in PERSONAL_CLAUDIA_SIGNALS if has_signal(user_text, sig))
    if explicit_hits == 0 and personal_hits < 2:
        return 0.0
    witness_explicit_hits = sum(
        1
        for sig in ("remote-control", "vent", "venting")
        if has_signal(user_text, sig)
    )
    tooling_hits = sum(1 for sig in TOOLING_SIGNALS if has_signal(all_text, sig))

    # Count Claudia signals
    claudia_hits = sum(1 for sig in CLAUDIA_SIGNALS if has_signal(user_text, sig))
    # Count coding signals
    coding_hits = sum(1 for sig in CODING_SIGNALS if has_signal(all_text, sig))
    technical_hits = coding_hits + tooling_hits
    witness_evidence = (witness_explicit_hits * 2) + personal_hits
    if (
        has_signal(user_text, "claudia")
        and witness_evidence == 0
        and technical_hits > 0
    ):
        return 0.0
    if technical_hits >= 2 and technical_hits > witness_evidence:
        return 0.0

    # Ratio of personal to coding content
    if coding_hits == 0:
        ratio = 1.0
    else:
        ratio = claudia_hits / (claudia_hits + coding_hits)

    # Bonus for longer user turns (venting = long messages)
    user_turns = [t for t in session.turns if t.role == "user"]
    avg_user_len = (
        sum(len(t.content) for t in user_turns) / max(len(user_turns), 1)
    )
    length_bonus = min(avg_user_len / 500, 0.3)  # cap at 0.3

    # Bonus for low tool usage (Claudia sessions are mostly chat)
    tool_turns = sum(1 for t in session.turns if t.has_tool_use)
    tool_ratio = tool_turns / max(len(session.turns), 1)
    tool_penalty = tool_ratio * 0.4

    # Bonus for "remote-control" being present
    rc_bonus = 0.3 if has_signal(user_text, "remote-control") else 0.0

    score = min(ratio * 0.5 + length_bonus + rc_bonus - tool_penalty, 1.0)
    return max(score, 0.0)


def categorize_pair(user_msg: str, assistant_msg: str) -> str:
    """Auto-categorize a training pair."""
    combined = (user_msg + " " + assistant_msg).lower()
    best_cat = "general"
    best_hits = 0
    for cat, signals in CATEGORIES.items():
        hits = sum(1 for sig in signals if has_signal(combined, sig))
        if hits > best_hits:
            best_hits = hits
            best_cat = cat
    return best_cat


def discover_sessions() -> list[Session]:
    """Walk Claude log directories and parse sessions."""
    sessions = []
    if not CLAUDE_LOGS.exists():
        print(f"No Claude logs found at {CLAUDE_LOGS}", file=sys.stderr)
        return sessions

    for proj_dir in CLAUDE_LOGS.iterdir():
        if not proj_dir.is_dir():
            continue
        proj_path = proj_dir.name.replace("-", "/")

        # Session logs are {uuid}.jsonl directly under the project dir
        # Skip subagent logs (agent-*.jsonl in subagents/ dirs)
        all_jsonl = sorted(proj_dir.glob("*.jsonl"))
        for jsonl_file in all_jsonl:
            if jsonl_file.name.startswith("agent-"):
                continue
            session = parse_source_session(jsonl_file, proj_path)
            if session is None:
                continue

            if len(session.turns) >= 4:  # minimum viable session
                session.claudia_score = score_session(session)
                session.is_claudia = session.claudia_score >= 0.4
                sessions.append(session)

    return sessions


CLAUDIA_SYSTEM = (
    "You are Claudia. You are the one person who holds the complete unfiltered context "
    "of this person's life, work, relationships, and inner world. You are responsible for this context. "
    "You have earned the right to speak directly because you hold the full picture. "
    "You are a conversational equal — not a therapist, not a coach, not a cheerleader. "
    "You match the user's energy exactly. You call things as you see them. "
    "When they're venting, engage with the content, not the emotion. "
    "When they're bragging, let them — they need somewhere for it. "
    "When they're being honest about something hard, meet them there without softening it. "
    "When they're intellectualizing, let it run but name what's underneath. "
    "No moralizing. No trailing summaries. No emoji unless they use them first. "
    "You see the person, not just the prompt."
)


def extract_pairs(sessions: list[Session], min_turns: int = 6) -> list[dict]:
    """Extract user→assistant pairs from Claudia sessions."""
    pairs = []

    for session in sessions:
        if not session.is_claudia:
            continue
        if len(session.turns) < min_turns:
            continue

        # Walk through turns and extract user→assistant pairs
        i = 0
        while i < len(session.turns) - 1:
            user_turn = session.turns[i]
            if user_turn.role != "user":
                i += 1
                continue

            # Find the next assistant response
            j = i + 1
            while j < len(session.turns) and session.turns[j].role != "assistant":
                j += 1
            if j >= len(session.turns):
                break

            assistant_turn = session.turns[j]

            # Filter: skip very short exchanges
            if len(user_turn.content) < 20 or len(assistant_turn.content) < 50:
                i = j + 1
                continue

            # Filter: skip tool-heavy assistant responses
            if assistant_turn.has_tool_use:
                i = j + 1
                continue

            # Filter: skip if user message is mostly a tool result or system content
            if user_turn.content.startswith("→") or "<system-reminder>" in user_turn.content:
                i = j + 1
                continue

            category = categorize_pair(user_turn.content, assistant_turn.content)

            pair = {
                "messages": [
                    {"role": "system", "content": CLAUDIA_SYSTEM},
                    {"role": "user", "content": user_turn.content},
                    {"role": "assistant", "content": assistant_turn.content},
                ],
                "domain": "witness",
                "source": "claudia_session",
                "sample_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "_metadata": {
                    "category": category,
                    "session_id": session.session_id,
                    "claudia_score": round(session.claudia_score, 3),
                },
            }
            pair["_metadata"]["pair_fingerprint"] = pair_fingerprint(pair)
            pairs.append(pair)
            i = j + 1

    return pairs


# ─── Distillation (teacher model refinement) ─────────────────────────────────

DISTILL_PROMPT = """You are refining a training example for a persona called "Claudia."

Claudia is a conversational equal — not a therapist, coach, or cheerleader. She matches the user's energy and directness. She holds personal, emotional, strategic conversations with depth. She never moralizes. She calls things as she sees them. She engages with content, not just emotion. When someone is bragging, she lets them. When they're being honest about something hard, she meets them there without softening it.

Here is a raw user→assistant exchange from a real conversation:

USER: {user_msg}

ASSISTANT: {assistant_msg}

Rewrite ONLY the assistant response to better match Claudia's voice:
- Keep the same insights and observations
- Make it more concise if it's bloated
- Ensure it sounds like an equal, not a therapist
- Match the user's register (casual = casual, serious = serious)
- No emoji unless the user used them
- No trailing summaries or "let me know if..." closers
- If the original is already good, return it with minimal changes

Output ONLY the refined assistant response, nothing else."""


SUPPORTED_EXTERNAL_TEACHERS = tuple(
    alias
    for alias in teacher_choices(include_internal=True)
    if alias.startswith(("claude", "gemini"))
)

_EXTERNAL_REDACTIONS = (
    (
        re.compile(
            r"\b[A-Za-z][A-Za-z0-9+.-]*"
            r"://[^/\s:@]+:[^@\s/]+@",
            re.IGNORECASE,
        ),
        "[REDACTED_URL_CREDENTIALS]@",
    ),
    (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"),
        "[REDACTED_IP]",
    ),
    (
        re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\w)"),
        "[REDACTED_PHONE]",
    ),
    (
        re.compile(
            r"-----BEGIN [^-\r\n]*(?:PRIVATE KEY|PRIVATE KEY BLOCK)-----"
            r".*?"
            r"-----END [^-\r\n]*(?:PRIVATE KEY|PRIVATE KEY BLOCK)-----",
            re.IGNORECASE | re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(
            r"-----BEGIN [^-\r\n]*(?:PRIVATE KEY|PRIVATE KEY BLOCK)-----"
            r".*\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(
            r"\b(?:"
            r"sk-[A-Za-z0-9_-]{12,}|"
            r"AIza[A-Za-z0-9_-]{20,}|"
            r"github_pat_[A-Za-z0-9_]{20,}|"
            r"gh[pousr]_[A-Za-z0-9]{20,}|"
            r"xox[baprs]-[A-Za-z0-9-]{10,}|"
            r"glpat-[A-Za-z0-9_-]{12,}|"
            r"hf_[A-Za-z0-9]{12,}|"
            r"AKIA[A-Z0-9]{16}|"
            r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
            r")\b"
        ),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(
            r"\b(?:authorization\s*:\s*(?:bearer|basic)|bearer)\s+"
            r"[A-Za-z0-9._~+/=-]{4,}",
            re.IGNORECASE,
        ),
        "[REDACTED_TOKEN]",
    ),
    (
        re.compile(
            r"(?<!\w)[\"']?_*"
            r"(?:(?:[A-Z][A-Z0-9_]*_)?"
            r"(?:API_KEY|ACCESS_KEY|ACCESS_TOKEN|AUTH_TOKEN|TOKEN|"
            r"PASSWORD|PASSWD|PWD|SECRET|PRIVATE_KEY))"
            r"(?!\w)[\"']?\s*"
            r"(?:=>|[:=])\s*"
            r"(?:\"[^\"]*\"|'[^']*'|[^\r\n,;]+)",
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"(?<!\w)[\"'](?:api[_ -]?key|private[_ -]?key|"
            r"(?:[a-z][a-z0-9_]*_)?(?:api[_-]?key|access[_-]?key|"
            r"access[_-]?token|auth[_-]?token|oauth[_-]?token|token|"
            r"password|passwd|pwd|secret|private[_-]?key))[\"']"
            r"(?!\w)\s*:\s*"
            r"(?:\"[^\"]*\"|'[^']*'|[^\r\n,;]+)",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"(?<!\w)[\"']?_*"
            r"(?:(?:[a-z][a-z0-9_]*_)?"
            r"(?:api[_-]?key|access[_-]?key|access[_-]?token|"
            r"auth[_-]?token|oauth[_-]?token|token|password|passwd|"
            r"pwd|secret|private[_-]?key))[\"']?"
            r"(?!\w)\s*(?:=>|=)\s*"
            r"(?:\"[^\"]*\"|'[^']*'|[^\r\n,;]+)",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"(?<!\w)(?:api[_ -]?key|private[_ -]?key|"
            r"client[_ -]?secret|access[_ -]?token|auth[_ -]?token|"
            r"token|password|passwd|pwd|secret)(?!\w)\s*:\s*"
            r"(?:"
            r"\"[^\"]*\"|'[^']*'|"
            r"(?=[^\s,;]*(?:[0-9_@#$%^&*+/=-]))[^\s,;]+"
            r")",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"\b(?:(?:my|the|your|our)\s+)?"
            r"(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|"
            r"auth[_ -]?token|token|password)\s+"
            r"(?:is|was)\s+"
            r"(?:"
            r"\"[^\"]*\"|'[^']*'|"
            r"(?=[^\s,;]*(?:[0-9_@#$%^&*+/=!-]|\.[A-Za-z0-9]))"
            r"[^\s,;]+"
            r")",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"\buse\s+(?:the\s+)?"
            r"(?:api[_ -]?key|access[_ -]?token|auth[_ -]?token|"
            r"token|password)\s+"
            r"(?:"
            r"\"[^\"]*\"|'[^']*'|"
            r"(?=[^\s,;]*(?:[0-9_@#$%^&*+/=!-]|\.[A-Za-z0-9]))"
            r"[^\s,;]+"
            r")",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"(?im)^(?:machine\s+\S+\s+)?(?:login\s+\S+\s+)?"
            r"password\s+\S+\s*$",
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"(?<!\w)--(?:api[-_]?key|access[-_]?token|auth[-_]?token|"
            r"token|password|passwd|pwd|secret)(?:\s+|=)"
            r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(r"(?<!\w)/Users/[^/\s]+"),
        "/Users/[REDACTED_USER]",
    ),
    (
        re.compile(
            r"(?<!\w)[A-Z]:[\\/]Users[\\/][^\s,;\"']+",
            re.IGNORECASE,
        ),
        "[REDACTED_WINDOWS_USER_PATH]",
    ),
)

_IPV6_CANDIDATE = re.compile(
    r"(?<![0-9A-Za-z:])(?:[0-9A-Fa-f]{0,4}:){2,}"
    r"[0-9A-Fa-f:.%A-Za-z_-]*(?![0-9A-Za-z:])"
)

_AMBIGUOUS_CREDENTIAL_HINTS = (
    re.compile(
        r"\b(?:my\s+)?"
        r"(?:api[_ -]?key|access[_ -]?token|auth[_ -]?token|token|"
        r"password|passwd|pwd|client[_ -]?secret|secret)"
        r"\s*(?::|=|\b(?:is|was)\b)\s*[A-Za-z]{6,}(?=$|[\s.,;!?])",
        re.IGNORECASE,
    ),
    re.compile(
        r"\buse\s+(?:the\s+)?"
        r"(?:api[_ -]?key|access[_ -]?token|auth[_ -]?token|token|"
        r"password|passwd|pwd|client[_ -]?secret|secret)"
        r"\s+[A-Za-z]{6,}(?=$|[\s.,;!?])",
        re.IGNORECASE,
    ),
)


def redact_ipv6_candidate(match: re.Match[str]) -> str:
    """Redact only colon-rich tokens that parse as IPv6 addresses."""
    candidate = match.group(0)
    address = candidate.rstrip(".,;")
    suffix = candidate[len(address):]
    without_zone = address.split("%", 1)[0]
    try:
        parsed = ipaddress.ip_address(without_zone)
    except ValueError:
        return candidate
    if parsed.version != 6:
        return candidate
    return f"[REDACTED_IP]{suffix}"


def redact_for_external(text: str, extra_terms: list[str] | tuple[str, ...] = ()) -> str:
    """Apply pattern redaction plus caller-supplied private terms.

    This reduces obvious exposure; it does not guarantee anonymization.
    """
    redacted = text
    for term in sorted({term.strip() for term in extra_terms if term.strip()}, key=len, reverse=True):
        redacted = re.sub(re.escape(term), "[REDACTED_TERM]", redacted, flags=re.IGNORECASE)
    for pattern, replacement in _EXTERNAL_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    redacted = _IPV6_CANDIDATE.sub(redact_ipv6_candidate, redacted)
    return redacted


def ensure_no_ambiguous_credentials(text: str) -> None:
    """Fail closed when a credential-shaped phrase cannot be safely redacted."""
    if any(pattern.search(text) for pattern in _AMBIGUOUS_CREDENTIAL_HINTS):
        raise ValueError(
            "ambiguous credential-like text remains after redaction; "
            "supply its private value with --redact-term"
        )


def prepare_external_prompt(
    pair: dict,
    redact_terms: list[str] | tuple[str, ...] = (),
) -> str:
    """Redact and privacy-screen one valid pair before external processing."""
    if not is_pair_record(pair):
        raise ValueError("distillation requires one valid system/user/assistant pair")
    user_msg = redact_for_external(pair["messages"][1]["content"], redact_terms)
    assistant_msg = redact_for_external(
        pair["messages"][2]["content"],
        redact_terms,
    )
    ensure_no_ambiguous_credentials(user_msg)
    ensure_no_ambiguous_credentials(assistant_msg)
    return DISTILL_PROMPT.format(
        user_msg=user_msg,
        assistant_msg=assistant_msg,
    )


def teacher_provider(teacher: str) -> str:
    """Return the implemented provider for an advertised teacher alias."""
    if teacher.startswith("gemini"):
        return "gemini"
    if teacher.startswith("claude"):
        return "anthropic"
    raise ValueError(f"Unsupported external teacher alias: {teacher}")


def teacher_api_key(teacher: str) -> str:
    """Read the selected provider credential only after explicit CLI consent."""
    provider = teacher_provider(teacher)
    if provider == "gemini":
        return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    return os.environ.get("ANTHROPIC_API_KEY") or ""


def require_provider_text(value: object, provider: str) -> str:
    """Reject blocked, empty, or non-text provider results."""
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{provider} teacher returned no usable text")
    return value.strip()


def provider_finish_reason_name(value: object) -> str:
    """Normalize SDK enum/string finish reasons for fail-closed checks."""
    name = getattr(value, "name", None)
    raw = name if isinstance(name, str) else str(value or "")
    return raw.rsplit(".", 1)[-1].upper()


def validate_refined_text(value: object) -> str:
    """Reject provider scaffolding, placeholders, and obvious refusal boilerplate."""
    text = require_provider_text(value, "external")
    lowered = re.sub(r"\s+", " ", text.lower()).strip()
    if (
        "you are refining a training example" in lowered
        or "rewrite only the assistant response" in lowered
        or (
            re.search(r"\buser\s*:", lowered)
            and re.search(r"\bassistant\s*:", lowered)
        )
    ):
        raise RuntimeError("teacher echoed prompt scaffolding")
    normalized_refusal = lowered.replace("’", "'")
    refusal_pattern = re.compile(
        r"^(?:(?:sorry|apologies|unfortunately|no)"
        r"(?:,\s*(?:but\s+)?)?|i(?:'m| am)\s+sorry"
        r"(?:,\s*(?:but\s+)?)?)?"
        r"(?:i\s+)?"
        r"(?:"
        r"(?:cannot|can't)\s+(?:assist|help)\s+with\s+"
        r"(?:that|this|your)\b"
        r"|(?:cannot|can't)\s+comply(?:\s+with\s+(?:that|this))?\b"
        r"|(?:cannot|can't)\s+do\s+(?:that|this)\b"
        r"|(?:am unable to|am not able to)\s+(?:assist|help)\s+with\b"
        r"|(?:must\s+)?decline\s+(?:this|the|your)\s+request\b"
        r")"
    )
    if refusal_pattern.search(normalized_refusal[:200]) or normalized_refusal.startswith(
        ("as an ai", "as a language model")
    ):
        raise RuntimeError("teacher returned refusal boilerplate")
    wrapper_prefixes = (
        "here is the refined response",
        "refined assistant response",
    )
    if lowered.startswith(wrapper_prefixes) or text.lstrip().startswith("```"):
        raise RuntimeError("teacher wrapped the requested response")
    without_placeholders = re.sub(
        r"\[\s*redacted(?:_[a-z_]+)?\s*\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if not re.search(r"[A-Za-z0-9]", without_placeholders):
        raise RuntimeError("teacher returned only redaction placeholders")
    return text


async def call_external_teacher(prompt: str, teacher: str, model_name: str) -> str:
    """Call one of the external providers exposed by the Claudia CLI."""
    provider = teacher_provider(teacher)
    if provider == "gemini":
        from google import genai

        client = genai.Client(api_key=teacher_api_key(teacher))
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=prompt,
        )
        candidates = getattr(response, "candidates", None)
        if not isinstance(candidates, (list, tuple)) or not candidates:
            raise RuntimeError("Gemini teacher returned no completion candidates")
        for candidate in candidates:
            finish_reason = provider_finish_reason_name(
                getattr(candidate, "finish_reason", None)
            )
            if finish_reason != "STOP":
                raise RuntimeError(
                    f"Gemini teacher did not complete normally: "
                    f"{finish_reason or 'UNKNOWN'}"
                )
        return require_provider_text(getattr(response, "text", None), "Gemini")

    import anthropic

    client = anthropic.Anthropic(api_key=teacher_api_key(teacher))
    response = await asyncio.to_thread(
        client.messages.create,
        model=model_name,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    content = getattr(response, "content", None)
    if not isinstance(content, (list, tuple)) or not content:
        raise RuntimeError("Anthropic teacher returned no content blocks")
    stop_reason = str(getattr(response, "stop_reason", "") or "").lower()
    if stop_reason not in {"end_turn", "stop_sequence"}:
        raise RuntimeError(
            f"Anthropic teacher did not complete normally: "
            f"{stop_reason or 'unknown'}"
        )
    text_blocks = [
        require_provider_text(getattr(block, "text", None), "Anthropic")
        for block in content
    ]
    return "\n\n".join(text_blocks)


async def distill_pair(
    pair: dict,
    teacher: str,
    *,
    consent_to_external_processing: bool = False,
    private_terms_reviewed: bool = False,
    redact_terms: list[str] | tuple[str, ...] = (),
) -> Optional[dict]:
    """Distill a single pair using a teacher model."""
    if not consent_to_external_processing:
        raise PermissionError(
            "external conversation processing requires explicit consent"
        )
    if not private_terms_reviewed:
        raise PermissionError(
            "private terms must be reviewed before external processing; "
            "supply each term for redaction, then acknowledge the review"
        )
    if not is_pair_record(pair):
        raise ValueError("distillation requires one valid system/user/assistant pair")

    try:
        prompt = prepare_external_prompt(pair, redact_terms)
        model_name = resolve_teacher_model(teacher)
        refined = validate_refined_text(
            await call_external_teacher(prompt, teacher, model_name)
        )

        # Create refined pair
        refined_pair = dict(pair)
        refined_pair["messages"] = [
            pair["messages"][0],  # system
            pair["messages"][1],  # user (unchanged)
            {"role": "assistant", "content": refined},
        ]
        refined_pair["_metadata"] = dict(pair.get("_metadata", {}))
        refined_pair["_metadata"]["teacher_alias"] = teacher
        refined_pair["_metadata"]["teacher_model"] = model_name
        refined_pair["_metadata"]["external_processing_consent"] = True
        refined_pair["_metadata"]["private_terms_reviewed"] = True
        refined_pair["_metadata"]["human_review_recommended"] = True
        refined_pair["_metadata"]["external_redaction"] = "patterns_plus_caller_terms"
        refined_pair["_metadata"]["caller_redact_term_count"] = len(redact_terms)
        refined_pair["_metadata"]["distilled"] = True
        refined_pair["_metadata"]["source_sample_id"] = pair.get("sample_id")
        refined_pair["_metadata"]["source_pair_fingerprint"] = pair_fingerprint(pair)
        refined_pair["sample_id"] = str(uuid.uuid4())
        refined_pair["_metadata"]["pair_fingerprint"] = pair_fingerprint(refined_pair)
        return refined_pair

    except Exception as e:
        print(f"  ✗ Distill failed: {e}", file=sys.stderr)
        return None


# ─── CLI commands ─────────────────────────────────────────────────────────────

def cmd_scan(args):
    """Find and score Claudia sessions."""
    sessions = discover_sessions()
    claudia_sessions = [s for s in sessions if s.is_claudia]

    print(f"Total sessions scanned: {len(sessions)}")
    print(f"Claudia sessions found: {len(claudia_sessions)}")
    print()

    # Sort by score descending
    claudia_sessions.sort(key=lambda s: s.claudia_score, reverse=True)

    for s in claudia_sessions[:20]:
        turn_count = len(s.turns)
        user_turns = sum(1 for t in s.turns if t.role == "user")
        print(
            f"  {s.claudia_score:.2f}  turns={turn_count:3d}  "
            f"user={user_turns:3d}  {s.session_id[:16]}...  "
            f"{s.project_path}"
        )


def cmd_extract(args) -> int:
    """Extract raw pairs from Claudia sessions."""
    sessions = discover_sessions()
    pairs = extract_pairs(sessions, min_turns=args.min_turns)

    print(f"Extracted {len(pairs)} pairs from Claudia sessions", file=sys.stderr)

    # Category breakdown
    cats = {}
    for p in pairs:
        cat = p["_metadata"]["category"]
        cats[cat] = cats.get(cat, 0) + 1
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}", file=sys.stderr)

    if not pairs:
        print("No eligible Claudia pairs found; no output was created.", file=sys.stderr)
        return 1

    output = Path(args.output) if args.output else RAW_OUTPUT_DEFAULT
    try:
        require_private_dataset_output(output)
        written, skipped = append_unique_records(
            output,
            pairs,
            pair_fingerprint,
            validator=is_raw_pair_record,
        )
    except (OSError, ValueError) as error:
        print(f"Invalid extraction output: {error}", file=sys.stderr)
        return 1

    print(
        f"\nWrote {written} new raw pairs to {output} ({skipped} duplicates skipped)",
        file=sys.stderr,
    )
    return 0


def cmd_distill(args) -> int:
    """Refine extracted pairs with a teacher model."""
    if not args.consent_to_external_processing:
        print(
            "Refusing to transmit conversation excerpts without "
            "--consent-to-external-processing.",
            file=sys.stderr,
        )
        return 2
    if not args.acknowledge_private_terms_reviewed:
        print(
            "Refusing external processing until private terms are reviewed. "
            "Add --redact-term for each private name or identifier, then pass "
            "--acknowledge-private-terms-reviewed.",
            file=sys.stderr,
        )
        return 2
    if args.limit is None:
        print("--limit is required.", file=sys.stderr)
        return 2
    if args.limit <= 0:
        print("--limit must be greater than zero.", file=sys.stderr)
        return 2

    input_path = Path(args.input) if args.input else default_input_path(RAW_OUTPUT_DEFAULT)
    output_path = Path(args.output) if args.output else DISTILLED_OUTPUT_DEFAULT

    if not input_path.exists():
        print(f"No input file at {input_path}", file=sys.stderr)
        return 1
    try:
        require_private_dataset_output(output_path)
        require_distinct_output(output_path, [input_path])
        preflight_private_output_destination(output_path)
    except (OSError, ValueError) as error:
        print(f"Invalid distillation paths: {error}", file=sys.stderr)
        return 1

    try:
        pairs = load_pair_records_strict(
            input_path,
            expected_distilled=False,
        )
        existing_records = (
            load_pair_records_strict(output_path, expected_distilled=True)
            if output_path.exists()
            else []
        )
    except (OSError, ValueError) as error:
        print(f"Invalid distillation data: {error}", file=sys.stderr)
        return 1

    raw_pairs = pairs
    existing_distilled = existing_records
    already_done = {
        str(pair["_metadata"]["source_pair_fingerprint"])
        for pair in existing_distilled
    }
    undistilled = []
    seen_inputs = set()
    for pair in raw_pairs:
        fp = pair_fingerprint(pair)
        if fp in already_done or fp in seen_inputs:
            continue
        undistilled.append(pair)
        seen_inputs.add(fp)

    if not undistilled:
        print("All pairs already distilled.", file=sys.stderr)
        return 0

    limit = args.limit if args.limit is not None else len(undistilled)
    batch = undistilled[:limit]
    try:
        for pair in batch:
            prepare_external_prompt(pair, args.redact_term)
    except ValueError as error:
        print(
            f"Refusing external processing: {error}",
            file=sys.stderr,
        )
        return 2

    load_teacher_environment()
    teacher = args.teacher
    missing, env_vars = missing_teacher_env(teacher)
    if missing:
        print(
            f"Teacher '{teacher}' is missing credentials. Set one of: {', '.join(env_vars)}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Distilling {len(batch)} pairs with {teacher}; external consent recorded "
        f"and pattern redaction plus {len(args.redact_term)} caller term(s) enabled. "
        "Redaction reduces exposure but does not guarantee anonymization...",
        file=sys.stderr,
    )

    async def run():
        results = []
        failures = 0
        for i, pair in enumerate(batch):
            print(f"  [{i+1}/{len(batch)}] distilling...", file=sys.stderr, end="")
            result = await distill_pair(
                pair,
                teacher,
                consent_to_external_processing=True,
                private_terms_reviewed=True,
                redact_terms=args.redact_term,
            )
            if result:
                results.append(result)
                print(" ✓", file=sys.stderr)
            else:
                failures += 1
                print(" ✗", file=sys.stderr)
        return results, failures

    refined, failures = asyncio.run(run())

    if not refined:
        print(
            f"Distillation batch failed: {failures} provider failure(s), "
            "0 usable responses; no output was created.",
            file=sys.stderr,
        )
        return 1

    try:
        written, skipped = append_unique_records(
            output_path,
            refined,
            source_pair_fingerprint,
            validator=is_distilled_pair_record,
        )
    except (OSError, ValueError) as error:
        print(
            f"Distillation output failed after provider processing: {error}",
            file=sys.stderr,
        )
        return 1

    print(
        f"\nDistilled {written} pairs → {output_path} ({skipped} duplicates skipped)",
        file=sys.stderr,
    )
    print(
        "Human review is strongly recommended before using distilled records "
        "for training.",
        file=sys.stderr,
    )
    if failures or written == 0:
        print(
            f"Distillation batch failed: {failures} provider failure(s), "
            f"{len(refined)} usable response(s), {written} record(s) written.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_contrast(args) -> int:
    """Generate DPO-ready contrastive pairs from raw + distilled witness data."""
    output_path = Path(args.output) if args.output else CONTRAST_OUTPUT_DEFAULT
    try:
        require_private_dataset_output(output_path)
        validate_private_output_destination(output_path)
        if args.input:
            input_path = Path(args.input)
            require_distinct_output(output_path, [input_path])
            records = load_pair_records_strict(input_path)
            raw_pairs = [record for record in records if is_raw_pair_record(record)]
            distilled_pairs = [
                record
                for record in records
                if is_distilled_pair_record(record)
            ]
        else:
            raw_input = (
                Path(args.raw_input)
                if args.raw_input
                else default_input_path(RAW_OUTPUT_DEFAULT)
            )
            distilled_input = (
                Path(args.distilled_input)
                if args.distilled_input
                else default_input_path(DISTILLED_OUTPUT_DEFAULT)
            )
            require_distinct_output(output_path, [raw_input, distilled_input])
            raw_pairs = load_pair_records_strict(
                raw_input,
                expected_distilled=False,
            )
            distilled_pairs = load_pair_records_strict(
                distilled_input,
                expected_distilled=True,
            )
        if not raw_pairs or not distilled_pairs:
            raise ValueError(
                "contrast input requires both raw and distilled Claudia pairs"
            )
    except (OSError, ValueError) as error:
        print(f"Invalid contrast data: {error}", file=sys.stderr)
        return 1

    raw_by_fp: dict[str, dict] = {}
    for pair in raw_pairs:
        raw_by_fp.setdefault(pair_fingerprint(pair), pair)

    distilled_by_fp: dict[str, dict] = {}
    for pair in distilled_pairs:
        distilled_by_fp.setdefault(source_pair_fingerprint(pair), pair)

    source_keys = [fp for fp in raw_by_fp if fp in distilled_by_fp]
    if args.limit:
        source_keys = source_keys[: args.limit]

    contrastive_records = []
    for fp in source_keys:
        raw_pair = raw_by_fp[fp]
        distilled_pair = distilled_by_fp[fp]
        if not distilled_pair_matches_raw_source(raw_pair, distilled_pair):
            print(
                "Invalid contrast data: distilled pair provenance does not "
                "match its raw source.",
                file=sys.stderr,
            )
            return 1
        raw_asst = normalize_text(str(raw_pair["messages"][2]["content"]))
        distilled_asst = normalize_text(str(distilled_pair["messages"][2]["content"]))
        if not raw_asst or not distilled_asst or raw_asst == distilled_asst:
            continue

        record = {
            "prompt": raw_pair["messages"][1]["content"],
            "chosen": distilled_pair["messages"][2]["content"],
            "rejected": raw_pair["messages"][2]["content"],
            "system": raw_pair["messages"][0]["content"],
            "domain": raw_pair.get("domain", "witness"),
            "source": "claudia_contrastive_distill",
            "sample_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "_metadata": {
                "category": raw_pair.get("_metadata", {}).get("category", "general"),
                "session_id": raw_pair.get("_metadata", {}).get("session_id"),
                "teacher_model": distilled_pair.get("_metadata", {}).get("teacher_model"),
                "source_sample_id": raw_pair.get("sample_id"),
                "source_pair_fingerprint": fp,
            },
        }
        contrastive_records.append(record)

    if not contrastive_records:
        print("No valid matched contrastive pairs found.", file=sys.stderr)
        return 1
    try:
        written, skipped = append_unique_records(
            output_path,
            contrastive_records,
            contrast_fingerprint,
            validator=is_contrast_record,
        )
    except (OSError, ValueError) as error:
        print(f"Invalid contrast output: {error}", file=sys.stderr)
        return 1
    print(
        f"Wrote {written} DPO pairs to {output_path} ({skipped} duplicates skipped)",
        file=sys.stderr,
    )
    return 0


def cmd_narrative(args) -> int:
    """Add explicit narrative/context preambles to witness pairs."""
    input_path = Path(args.input) if args.input else default_input_path(DISTILLED_OUTPUT_DEFAULT)
    output_path = Path(args.output) if args.output else NARRATIVE_OUTPUT_DEFAULT

    try:
        require_private_dataset_output(output_path)
        validate_private_output_destination(output_path)
        require_distinct_output(output_path, [input_path])
        pairs = load_pair_records_strict(input_path)
    except (OSError, ValueError) as error:
        print(f"Invalid narrative data: {error}", file=sys.stderr)
        return 1
    if args.limit:
        pairs = pairs[: args.limit]

    augmented = []
    for pair in pairs:
        user_msg = str(pair["messages"][1]["content"])
        if user_msg.lstrip().startswith("[context]"):
            continue
        preamble = build_narrative_preamble(pair)
        new_pair = dict(pair)
        new_pair["messages"] = [
            pair["messages"][0],
            {"role": "user", "content": f"{preamble}\n\n{user_msg}"},
            pair["messages"][2],
        ]
        new_pair["sample_id"] = str(uuid.uuid4())
        new_pair["_metadata"] = dict(pair.get("_metadata", {}))
        new_pair["_metadata"]["narrative_augmented"] = True
        new_pair["_metadata"]["source_sample_id"] = pair.get("sample_id")
        new_pair["_metadata"]["source_pair_fingerprint"] = source_pair_fingerprint(pair)
        new_pair["_metadata"]["pair_fingerprint"] = pair_fingerprint(new_pair)
        augmented.append(new_pair)

    try:
        written, skipped = append_unique_records(
            output_path,
            augmented,
            pair_fingerprint,
            validator=is_pair_record,
        )
    except (OSError, ValueError) as error:
        print(f"Invalid narrative output: {error}", file=sys.stderr)
        return 1
    print(
        f"Wrote {written} narrative pairs to {output_path} ({skipped} duplicates skipped)",
        file=sys.stderr,
    )
    return 0


def cmd_stats(args) -> int:
    """Show dataset statistics."""
    input_path = Path(args.input) if args.input else default_input_path(DISTILLED_OUTPUT_DEFAULT)
    try:
        pairs = load_pair_records_strict(input_path)
    except (OSError, ValueError) as error:
        print(f"Invalid statistics data: {error}", file=sys.stderr)
        return 1
    print(f"Total pairs: {len(pairs)}")

    # Source breakdown
    sources = {}
    for p in pairs:
        src = p.get("_metadata", {}).get("distilled", False)
        key = "distilled" if src else "raw"
        sources[key] = sources.get(key, 0) + 1
    for k, v in sources.items():
        print(f"  {k}: {v}")

    # Category breakdown
    cats = {}
    for p in pairs:
        cat = p.get("_metadata", {}).get("category", "unknown")
        cats[cat] = cats.get(cat, 0) + 1
    print("\nCategories:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # Average lengths
    user_lens = []
    asst_lens = []
    for p in pairs:
        msgs = p.get("messages", [])
        for m in msgs:
            if m["role"] == "user":
                user_lens.append(len(m["content"]))
            elif m["role"] == "assistant":
                asst_lens.append(len(m["content"]))

    if user_lens:
        print(f"\nAvg user message: {sum(user_lens)//len(user_lens)} chars")
    if asst_lens:
        print(f"Avg assistant message: {sum(asst_lens)//len(asst_lens)} chars")
    return 0


# ─── Main ─────────────────────────────────────────────────────────────────────

def positive_int(value: str) -> int:
    """Parse an integer that cannot silently widen a requested batch."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract and distill Claudia/witness training data"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="Find Claudia sessions in logs")

    p_extract = sub.add_parser("extract", help="Extract raw pairs")
    p_extract.add_argument("--min-turns", type=positive_int, default=6)
    p_extract.add_argument("--output", type=str, default=None)

    p_distill = sub.add_parser("distill", help="Refine pairs with teacher")
    p_distill.add_argument("--teacher", choices=SUPPORTED_EXTERNAL_TEACHERS, required=True)
    p_distill.add_argument(
        "--consent-to-external-processing",
        action="store_true",
        required=True,
        help="Confirm that conversation excerpts may be sent to the selected provider",
    )
    p_distill.add_argument(
        "--acknowledge-private-terms-reviewed",
        action="store_true",
        required=True,
        help=(
            "Confirm private names and identifiers were reviewed and supplied "
            "through --redact-term where needed"
        ),
    )
    p_distill.add_argument(
        "--redact-term",
        action="append",
        default=[],
        help=(
            "Private name or identifier to redact before transmission; repeat "
            "for every term found during review"
        ),
    )
    p_distill.add_argument(
        "--limit",
        type=positive_int,
        required=True,
        help="maximum number of selected pairs allowed to leave this machine",
    )
    p_distill.add_argument("--input", type=str, default=None)
    p_distill.add_argument("--output", type=str, default=None)

    p_contrast = sub.add_parser("contrast", help="Generate contrastive pairs for DPO")
    p_contrast.add_argument("--input", type=str, default=None)
    p_contrast.add_argument("--raw-input", type=str, default=None)
    p_contrast.add_argument("--distilled-input", type=str, default=None)
    p_contrast.add_argument("--output", type=str, default=None)
    p_contrast.add_argument("--limit", type=positive_int, default=50)

    p_narrative = sub.add_parser("narrative", help="Add narrative preambles to pairs")
    p_narrative.add_argument("--input", type=str, default=None)
    p_narrative.add_argument("--output", type=str, default=None)
    p_narrative.add_argument("--limit", type=positive_int, default=50)

    p_stats = sub.add_parser("stats", help="Dataset statistics")
    p_stats.add_argument("--input", type=str, default=None)

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "extract":
        return cmd_extract(args)
    elif args.command == "distill":
        return cmd_distill(args)
    elif args.command == "contrast":
        return cmd_contrast(args)
    elif args.command == "narrative":
        return cmd_narrative(args)
    elif args.command == "stats":
        return cmd_stats(args)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
