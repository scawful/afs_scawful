#!/usr/bin/env python3
import argparse
import json
import os
import secrets
import shutil
import time
from pathlib import Path


TRASH_ROOT = Path(os.environ.get("AGENT_TRASH_ROOT", "~/Archives/agent-trash")).expanduser()
MANIFEST = TRASH_ROOT / "manifest.jsonl"
APPROVAL_FILE = Path(
    os.environ.get("AGENT_DELETE_APPROVAL_FILE", "~/.config/agent-tools/delete_approval.json")
).expanduser()
APPROVAL_MAX_TTL_MIN = int(os.environ.get("AGENT_DELETE_APPROVAL_MAX_TTL_MIN", "1440"))


def now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def epoch_iso(epoch: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def ensure_trash_root(dry_run: bool) -> None:
    if dry_run:
        return
    TRASH_ROOT.mkdir(parents=True, exist_ok=True)


def record_event(payload: dict, dry_run: bool) -> None:
    if dry_run:
        return
    with MANIFEST.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def ensure_approval_dir(dry_run: bool) -> None:
    if dry_run:
        return
    APPROVAL_FILE.parent.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)
    return cleaned or "item"


def resolve_path(path: str) -> Path:
    """Return an absolute path without resolving symlinks."""
    return Path(path).expanduser().absolute()


def is_within_trash(path: Path) -> bool:
    try:
        path.relative_to(TRASH_ROOT.resolve())
        return True
    except ValueError:
        return False


def estimate_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except FileNotFoundError:
            continue
    return total


def load_approval() -> dict | None:
    if not APPROVAL_FILE.exists():
        return None
    try:
        data = json.loads(APPROVAL_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def approval_active() -> dict | None:
    data = load_approval()
    if not data:
        return None
    try:
        expires_at = int(data.get("expires_at_epoch", 0))
    except (TypeError, ValueError):
        return None
    if time.time() >= expires_at:
        return None
    return data


def load_manifest_states() -> dict:
    states = {}
    if not MANIFEST.exists():
        return states
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_id = event.get("id")
        if not entry_id:
            continue
        states[entry_id] = event
    return states


def trash_paths(paths: list[str], reason: str | None, dry_run: bool) -> None:
    ensure_trash_root(dry_run)
    for raw in paths:
        path = resolve_path(raw)
        if not path.exists() and not path.is_symlink():
            print(f"missing: {path}")
            continue
        token = secrets.token_hex(3)
        stamp = now_stamp()
        dest_name = f"{stamp}_{token}_{safe_name(path.name)}"
        dest = TRASH_ROOT / dest_name
        size_bytes = estimate_size(path)
        event = {
            "id": f"{stamp}_{token}",
            "action": "trash",
            "timestamp": now_iso(),
            "src": str(path),
            "dest": str(dest),
            "size_bytes": size_bytes,
            "reason": reason or "",
        }
        print(f"trash: {path} -> {dest}")
        if not dry_run:
            shutil.move(str(path), str(dest))
        record_event(event, dry_run)


def list_trash() -> None:
    ensure_trash_root(False)
    states = load_manifest_states()
    tracked = {Path(event["dest"]).resolve(): event for event in states.values() if event.get("dest")}

    items = []
    for entry in TRASH_ROOT.iterdir():
        if entry.name == MANIFEST.name:
            continue
        resolved = entry.resolve()
        event = tracked.get(resolved)
        if event and event.get("action") == "purge":
            continue
        if event:
            items.append(
                {
                    "id": event.get("id"),
                    "path": str(entry),
                    "reason": event.get("reason", ""),
                    "size_bytes": event.get("size_bytes", 0),
                }
            )
        else:
            items.append(
                {
                    "id": "untracked",
                    "path": str(entry),
                    "reason": "",
                    "size_bytes": entry.stat().st_size if entry.is_file() else 0,
                }
            )

    if not items:
        print("trash empty")
        return

    for item in items:
        print(f"{item['id']}  {item['path']}  {item['size_bytes']} bytes  {item['reason']}")


def approval_status() -> None:
    data = load_approval()
    if not data:
        print("approval: none")
        return
    try:
        expires_at = int(data.get("expires_at_epoch", 0))
    except (TypeError, ValueError):
        print("approval: invalid")
        return
    now = int(time.time())
    if now >= expires_at:
        print(f"approval: expired at {epoch_iso(expires_at)}")
        return
    remaining = max(0, expires_at - now)
    minutes = remaining // 60
    print(f"approval: active until {epoch_iso(expires_at)} ({minutes}m remaining)")


def approve(ttl_minutes: int, note: str, dry_run: bool) -> None:
    if ttl_minutes <= 0:
        raise SystemExit("TTL must be positive.")
    if ttl_minutes > APPROVAL_MAX_TTL_MIN:
        raise SystemExit(f"TTL exceeds max of {APPROVAL_MAX_TTL_MIN} minutes.")
    ensure_approval_dir(dry_run)
    issued_at_epoch = int(time.time())
    expires_at_epoch = issued_at_epoch + ttl_minutes * 60
    payload = {
        "issued_at_epoch": issued_at_epoch,
        "issued_at": epoch_iso(issued_at_epoch),
        "expires_at_epoch": expires_at_epoch,
        "expires_at": epoch_iso(expires_at_epoch),
        "ttl_minutes": ttl_minutes,
        "note": note or "",
        "approved_by": os.environ.get("USER", ""),
    }
    print(f"approval: active until {payload['expires_at']} ({ttl_minutes}m)")
    if not dry_run:
        APPROVAL_FILE.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def revoke_approval(dry_run: bool) -> None:
    if not APPROVAL_FILE.exists():
        print("approval: none")
        return
    print("approval: revoked")
    if not dry_run:
        APPROVAL_FILE.unlink()


def purge_target(target: str, yes: bool, dry_run: bool) -> None:
    approval = approval_active()
    if not yes and not approval:
        raise SystemExit(
            "Refusing to purge without --yes or active approval. "
            "Run: agent_delete.py approve --ttl 30"
        )

    resolved = resolve_path(target)
    states = load_manifest_states()

    event = states.get(target)
    dest = None
    if event and event.get("dest"):
        dest = Path(event["dest"]).expanduser().resolve()
    elif resolved.exists():
        dest = resolved
    else:
        raise SystemExit(f"Unknown id/path: {target}")

    if not is_within_trash(dest):
        raise SystemExit(f"Refusing to purge outside trash root: {dest}")

    print(f"purge: {dest}")
    if not dry_run:
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()

    record_event(
        {
            "id": target if event else "untracked",
            "action": "purge",
            "timestamp": now_iso(),
            "dest": str(dest),
            "approval_mode": "yes" if yes else "file",
            "approval_expires_at": approval.get("expires_at") if approval else "",
        },
        dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Trash-first delete helper.")
    sub = parser.add_subparsers(dest="command")

    trash_cmd = sub.add_parser("trash", help="Move paths into agent trash")
    trash_cmd.add_argument("paths", nargs="+", help="Paths to move")
    trash_cmd.add_argument("--reason", default="", help="Reason for deletion")
    trash_cmd.add_argument("--dry-run", action="store_true", help="Show actions without writing")

    list_cmd = sub.add_parser("list", help="List trash entries")

    purge_cmd = sub.add_parser("purge", help="Permanently delete a trash entry")
    purge_cmd.add_argument("target", help="Trash id or path")
    purge_cmd.add_argument("--yes", action="store_true", help="Confirm purge")
    purge_cmd.add_argument("--dry-run", action="store_true", help="Show actions without writing")

    approve_cmd = sub.add_parser("approve", help="Grant purge approval for a short TTL")
    approve_cmd.add_argument("--ttl", type=int, default=30, help="Approval TTL in minutes")
    approve_cmd.add_argument("--note", default="", help="Approval note")
    approve_cmd.add_argument("--dry-run", action="store_true", help="Show actions without writing")

    status_cmd = sub.add_parser("status", help="Show current approval status")

    revoke_cmd = sub.add_parser("revoke", help="Revoke active approval")
    revoke_cmd.add_argument("--dry-run", action="store_true", help="Show actions without writing")

    args = parser.parse_args()

    if args.command == "trash":
        trash_paths(args.paths, args.reason, args.dry_run)
    elif args.command == "list":
        list_trash()
    elif args.command == "purge":
        purge_target(args.target, args.yes, args.dry_run)
    elif args.command == "approve":
        approve(args.ttl, args.note, args.dry_run)
    elif args.command == "status":
        approval_status()
    elif args.command == "revoke":
        revoke_approval(args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
