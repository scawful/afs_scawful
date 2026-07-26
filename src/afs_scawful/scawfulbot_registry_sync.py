from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Mapping

CORE_ID = "scawfulbot"
SOURCE_REGISTRY_RELATIVE = "../scawfulbot/config/registry.json"
SYNC_SCRIPT_RELATIVE = "scripts/sync_scawfulbot_registry.py"
SYNC_GUARD = (
    "AUTO-GENERATED FROM ../scawfulbot/config/registry.json; "
    "run scripts/sync_scawfulbot_registry.py. Manual edits to this entry will be overwritten."
)

ALLOWED_STATUSES = {"draft", "training", "ready", "retired"}
STATUS_ALIASES = {"active": "ready"}

REPO_ROOT = Path(__file__).resolve().parents[2]


def _primary_checkout_root(repo_root: Path) -> Path | None:
    git_marker = repo_root / ".git"
    if git_marker.is_dir():
        return repo_root
    if not git_marker.is_file():
        return None

    marker = git_marker.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not marker.lower().startswith(prefix):
        return None
    git_dir = Path(marker[len(prefix):].strip()).expanduser()
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()

    common_dir_file = git_dir / "commondir"
    if common_dir_file.is_file():
        common_dir_value = common_dir_file.read_text(encoding="utf-8").strip()
        common_dir = (git_dir / common_dir_value).resolve()
        return common_dir.parent
    return git_dir.parent if git_dir.name == ".git" else None


def _default_source_registry_path() -> Path:
    override = os.environ.get("SCAWFULBOT_REGISTRY_PATH")
    if override:
        return Path(override).expanduser()

    candidates = [REPO_ROOT.parent / "scawfulbot" / "config" / "registry.json"]
    primary_checkout = _primary_checkout_root(REPO_ROOT)
    if primary_checkout is not None:
        candidates.append(primary_checkout.parent / "scawfulbot" / "config" / "registry.json")

    return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])


DEFAULT_SOURCE_REGISTRY_PATH = _default_source_registry_path()
DEFAULT_TARGET_REGISTRY_PATH = REPO_ROOT / "cores" / "registry.json"
DEFAULT_SYSTEM_PROMPT_PATH = "prompts/scawfulbot.md"
DEFAULT_TRAINING_DATA_PATH = "training/scawfulbot_training_template.jsonl"
DEFAULT_EVAL_PACK_PATH = "eval/scawfulbot_eval_cases.jsonl"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def _fsync_directory(path: Path) -> None:
    """Persist a completed rename on filesystems that support directory fsync."""

    if os.name == "nt":
        return
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextmanager
def _registry_lock(path: Path) -> Iterator[BinaryIO]:
    """Serialize the target read-modify-write cycle across local processes."""

    lock_path = path.parent / f".{path.name}.lock"
    handle = lock_path.open("a+b")
    os.chmod(lock_path, 0o600)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            if lock_path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        locked = True
        yield handle
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2) + "\n"
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            if path.exists():
                os.chmod(temporary_path, stat.S_IMODE(path.stat().st_mode))
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory(path.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _normalize_status(raw_status: object) -> str:
    status = str(raw_status).strip().lower() if raw_status is not None else "draft"
    status = STATUS_ALIASES.get(status, status)
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported status for {CORE_ID}: {status!r}")
    return status


def _latest_model_history_entry(source_registry: Mapping[str, Any]) -> Mapping[str, Any] | None:
    history = source_registry.get("model_history")
    if not isinstance(history, list) or not history:
        return None
    latest = history[-1]
    return latest if isinstance(latest, Mapping) else None


def build_scawfulbot_notes(source_registry: Mapping[str, Any]) -> str:
    lines = [
        SYNC_GUARD,
        f"Source registry: {SOURCE_REGISTRY_RELATIVE}",
    ]

    runtime_model_id = source_registry.get("runtime_model_id")
    if runtime_model_id:
        lines.append(f"Runtime model id: {runtime_model_id}")

    latest = _latest_model_history_entry(source_registry)
    if latest:
        latest_line = "Latest model history: "
        details: list[str] = []
        version = latest.get("version")
        if version:
            details.append(f"v{version}")
        base = latest.get("base")
        if base:
            details.append(str(base))
        date = latest.get("date")
        if date:
            details.append(f"date={date}")
        lm_studio_id = latest.get("lm_studio_id")
        if lm_studio_id:
            details.append(f"lm_studio_id={lm_studio_id}")
        if details:
            latest_line += ", ".join(details)
            lines.append(latest_line)
        latest_notes = latest.get("notes")
        if latest_notes:
            lines.append(f"Latest notes: {latest_notes}")

    next_release = source_registry.get("next_release_plan")
    if isinstance(next_release, Mapping):
        target_version = next_release.get("version")
        target_id = next_release.get("expected_lm_studio_id")
        if target_version or target_id:
            lines.append(f"Next release target: version={target_version}, lm_studio_id={target_id}")
        next_notes = next_release.get("notes")
        if next_notes:
            lines.append(f"Next release notes: {next_notes}")

    return "\n".join(lines)


def build_scawfulbot_core_entry(source_registry: Mapping[str, Any]) -> dict[str, Any]:
    source_id = str(source_registry.get("id", "")).strip()
    if source_id != CORE_ID:
        raise ValueError(f"source registry id must be {CORE_ID!r}, got {source_id!r}")

    description = str(source_registry.get("description_long") or source_registry.get("description") or "").strip()
    if not description:
        raise ValueError(f"source registry is missing description for {CORE_ID}")

    base_model = str(source_registry.get("base_model") or "").strip()
    if not base_model:
        raise ValueError(f"source registry is missing base_model for {CORE_ID}")

    parameters = source_registry.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError(f"source registry parameters must be an object for {CORE_ID}")

    tags = source_registry.get("tags")
    if not isinstance(tags, list):
        raise ValueError(f"source registry tags must be a list for {CORE_ID}")

    entry: dict[str, Any] = {
        "id": CORE_ID,
        "name": str(source_registry.get("name") or CORE_ID),
        "description": description,
        "base_model": base_model,
        "adapter_path": source_registry.get("adapter_path"),
        "system_prompt_path": DEFAULT_SYSTEM_PROMPT_PATH,
        "training_data_path": DEFAULT_TRAINING_DATA_PATH,
        "eval_pack_path": DEFAULT_EVAL_PACK_PATH,
        "status": _normalize_status(source_registry.get("status")),
        "version": str(source_registry.get("version") or "0.0.0"),
        "tags": [str(tag) for tag in tags],
        "parameters": dict(parameters),
        "notes": build_scawfulbot_notes(source_registry),
        "created_at": str(source_registry.get("created_at") or ""),
        "updated_at": str(source_registry.get("updated_at") or ""),
        "generated_from": {
            "repo": "../scawfulbot",
            "registry_path": "config/registry.json",
            "script": SYNC_SCRIPT_RELATIVE,
        },
    }
    return entry


def _find_core_index(cores: list[dict[str, Any]], core_id: str) -> int | None:
    for index, entry in enumerate(cores):
        if entry.get("id") == core_id:
            return index
    return None


def sync_scawfulbot_core_registry(source_path: Path, target_path: Path, *, check: bool = False) -> bool:
    source_registry = read_json(source_path)
    expected_entry = build_scawfulbot_core_entry(source_registry)

    if check:
        target_registry = read_json(target_path)
        cores = target_registry.get("cores")
        if not isinstance(cores, list):
            raise ValueError(f"target registry at {target_path} must contain a cores list")
        index = _find_core_index(cores, CORE_ID)
        return index is None or cores[index] != expected_entry

    with _registry_lock(target_path):
        target_registry = read_json(target_path)

        cores = target_registry.get("cores")
        if not isinstance(cores, list):
            raise ValueError(f"target registry at {target_path} must contain a cores list")

        index = _find_core_index(cores, CORE_ID)
        changed = True

        if index is None:
            if not check:
                cores.append(expected_entry)
        else:
            current_entry = cores[index]
            changed = current_entry != expected_entry
            if changed and not check:
                cores[index] = expected_entry

        if changed and not check:
            write_json(target_path, target_registry)

    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync the scawfulbot core entry from the scawfulbot repo registry.")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE_REGISTRY_PATH),
        help=f"Path to source scawfulbot registry (default: {DEFAULT_SOURCE_REGISTRY_PATH})",
    )
    parser.add_argument(
        "--target",
        default=str(DEFAULT_TARGET_REGISTRY_PATH),
        help=f"Path to target afs-scawful core registry (default: {DEFAULT_TARGET_REGISTRY_PATH})",
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero if target registry is out of sync.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.source).expanduser()
    target_path = Path(args.target).expanduser()

    if not source_path.exists():
        raise SystemExit(f"Source registry not found: {source_path}")
    if not target_path.exists():
        raise SystemExit(f"Target registry not found: {target_path}")

    changed = sync_scawfulbot_core_registry(source_path, target_path, check=args.check)

    if args.check:
        if changed:
            print("scawfulbot core registry entry is out of sync.")
            return 1
        print("scawfulbot core registry entry is in sync.")
        return 0

    if changed:
        print(f"updated {CORE_ID} core entry in {target_path}")
    else:
        print(f"{CORE_ID} core entry already in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
