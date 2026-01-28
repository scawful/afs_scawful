#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync agent tool policy to global locations.")
    parser.add_argument(
        "--policy",
        default=str(Path(__file__).resolve().parents[1] / "policies" / "agent_tools.json"),
        help="Path to agent tools policy JSON",
    )
    parser.add_argument(
        "--targets",
        default="context,config",
        help="Comma-separated targets: context,config,harness",
    )
    parser.add_argument(
        "--harnesses",
        default="claude,codex,gemini",
        help="Comma-separated harness names for harness exports",
    )
    parser.add_argument(
        "--context-root",
        default=str(Path("~/.context").expanduser()),
        help="Context root (default: ~/.context)",
    )
    parser.add_argument(
        "--config-root",
        default=str(Path("~/.config/agent-tools").expanduser()),
        help="Config root for policy exports",
    )
    parser.add_argument(
        "--wire",
        action="store_true",
        help="Symlink harness exports into harness config directories",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing wired files by backing them up",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing")
    return parser.parse_args()


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    return path.with_name(f"{path.name}.bak.{stamp}")


def ensure_symlink(src: Path, dest: Path, *, force: bool, dry_run: bool) -> None:
    src_resolved = src.resolve()
    exists = dest.exists() or dest.is_symlink()

    if exists:
        if dest.is_symlink():
            current = dest.resolve(strict=False)
            if current == src_resolved:
                print(f"ok: {dest} -> {current}")
                return
            if not force:
                print(f"skip: {dest} points to {current}")
                return
            backup = backup_path(dest)
            print(f"backup: {dest} -> {backup}")
            if not dry_run:
                dest.rename(backup)
        else:
            if not force:
                print(f"skip: {dest} exists and is not a symlink")
                return
            backup = backup_path(dest)
            print(f"backup: {dest} -> {backup}")
            if not dry_run:
                dest.rename(backup)

    print(f"link: {dest} -> {src_resolved}")
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(src_resolved)


def load_policy(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_export(policy: dict, source: str) -> dict:
    allow_entries = policy.get("shell", {}).get("allow", [])
    expanded = []
    allowlist = []
    for entry in allow_entries:
        command = str(entry.get("command", "")).strip()
        if not command:
            continue
        pattern = f"Bash({command}:*)"
        allowlist.append(pattern)
        expanded.append(
            {
                "command": command,
                "pattern": pattern,
                "reason": entry.get("reason", ""),
            }
        )

    return {
        "version": policy.get("version", 1),
        "generated": timestamp(),
        "source": source,
        "shell": {
            "allow": expanded,
            "allowlist": allowlist,
        },
    }


def build_harness_export(base_export: dict, harness: str) -> dict:
    allowlist = base_export.get("shell", {}).get("allowlist", [])
    return {
        "version": base_export.get("version", 1),
        "generated": base_export.get("generated"),
        "source": base_export.get("source"),
        "harness": harness,
        "tools": {
            "shell": {
                "allowlist": allowlist,
            }
        },
    }


def write_json(path: Path, payload: dict, dry_run: bool) -> None:
    print(f"write: {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def format_codex_rule(command: str) -> str:
    parts = ["/bin/zsh", "-lc", command]
    encoded = ", ".join(json.dumps(part) for part in parts)
    return f'prefix_rule(pattern=[{encoded}], decision="allow")'


def render_codex_block(commands: list[str]) -> str:
    lines = [
        "# BEGIN agent-tools sync",
        "# Managed by policy_sync.py",
    ]
    for command in commands:
        lines.append(format_codex_rule(command))
    lines.append("# END agent-tools sync")
    return "\n".join(lines)


def update_codex_rules(path: Path, commands: list[str], dry_run: bool) -> None:
    if not commands:
        print(f"skip: no shell commands to wire into {path}")
        return

    begin = "# BEGIN agent-tools sync"
    end = "# END agent-tools sync"
    block = render_codex_block(commands)

    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if begin in text and end in text:
        prefix, rest = text.split(begin, 1)
        _, suffix = rest.split(end, 1)
        new_text = prefix.rstrip() + "\n\n" + block + "\n" + suffix.lstrip()
    else:
        glue = "\n\n" if text.strip() else ""
        new_text = text.rstrip() + glue + block + "\n"

    if new_text == text:
        print(f"ok: {path} unchanged")
        return

    backup = backup_path(path)
    print(f"backup: {path} -> {backup}")
    print(f"write: {path}")
    if dry_run:
        return
    if path.exists():
        backup.write_text(text, encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    targets = {t.strip() for t in args.targets.split(",") if t.strip()}
    harnesses = [h.strip() for h in args.harnesses.split(",") if h.strip()]

    policy_path = Path(args.policy).expanduser()
    if not policy_path.exists():
        raise SystemExit(f"Policy not found: {policy_path}")

    policy = load_policy(policy_path)
    export = build_export(policy, str(policy_path))
    commands = [
        str(entry.get("command", "")).strip()
        for entry in policy.get("shell", {}).get("allow", [])
        if entry.get("command")
    ]

    if "context" in targets:
        context_root = Path(args.context_root).expanduser()
        write_json(context_root / "knowledge" / "agent_tools.json", export, args.dry_run)

    if "config" in targets:
        config_root = Path(args.config_root).expanduser()
        write_json(config_root / "agent_tools.json", export, args.dry_run)

    if "harness" in targets:
        config_root = Path(args.config_root).expanduser()
        harness_paths = {
            "claude": Path("~/.claude/agent_tools.json").expanduser(),
            "codex": Path("~/.codex/agent_tools.json").expanduser(),
            "gemini": Path("~/.gemini/agent_tools.json").expanduser(),
        }
        for harness in harnesses:
            payload = build_harness_export(export, harness)
            export_path = config_root / f"agent_tools.{harness}.json"
            write_json(export_path, payload, args.dry_run)
            if args.wire:
                dest = harness_paths.get(harness)
                if dest is None:
                    print(f"skip: no wire target for {harness}")
                    continue
                ensure_symlink(export_path, dest, force=args.force, dry_run=args.dry_run)
        if args.wire and "codex" in harnesses:
            update_codex_rules(Path("~/.codex/rules/default.rules").expanduser(), commands, args.dry_run)


if __name__ == "__main__":
    main()
