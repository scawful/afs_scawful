#!/usr/bin/env python3
import argparse
import json
import os
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Sync scawful skills to agent harnesses.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing")
    parser.add_argument("--force", action="store_true", help="Replace conflicting paths (backup first)")
    return parser.parse_args()


def timestamp():
    return time.strftime("%Y%m%d_%H%M%S")


def backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak.{timestamp()}")


def ensure_symlink(src: Path, dest: Path, *, force: bool, dry_run: bool) -> None:
    src_resolved = src.resolve()
    exists = os.path.lexists(dest)

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
        os.symlink(src_resolved, dest)


def write_json(path: Path, payload: dict, *, dry_run: bool) -> None:
    print(f"write: {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def update_extension_enablement(path: Path, name: str, override: str, *, dry_run: bool) -> None:
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = {}

    entry = data.get(name)
    if entry is None:
        data[name] = {"overrides": [override]}
    else:
        overrides = entry.get("overrides")
        if not isinstance(overrides, list):
            overrides = []
        if override not in overrides:
            overrides.append(override)
        entry["overrides"] = overrides
        data[name] = entry

    write_json(path, data, dry_run=dry_run)


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    skills_root = repo_root / "skills"

    if not skills_root.exists():
        raise SystemExit(f"Skills root not found: {skills_root}")

    skill_dirs = sorted(
        [p for p in skills_root.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    )

    if not skill_dirs:
        raise SystemExit("No skills found under skills/")

    home = Path.home()
    claude_root = home / ".claude" / "skills"
    codex_root = home / ".codex" / "skills"
    gemini_ext_root = home / ".gemini" / "extensions" / "scawful-skills"
    context_skills = home / ".context" / "knowledge" / "skills"

    for skill in skill_dirs:
        ensure_symlink(skill, claude_root / skill.name, force=args.force, dry_run=args.dry_run)
        ensure_symlink(skill, codex_root / skill.name, force=args.force, dry_run=args.dry_run)

    if (skills_root / "GEMINI.md").exists():
        gemini_manifest = {
            "name": "scawful-skills",
            "version": "0.1.0",
            "description": "Shared skills for scawful agentic workflows",
            "contextFileName": "GEMINI.md",
        }
        write_json(gemini_ext_root / "gemini-extension.json", gemini_manifest, dry_run=args.dry_run)
        ensure_symlink(
            skills_root / "GEMINI.md",
            gemini_ext_root / "GEMINI.md",
            force=args.force,
            dry_run=args.dry_run,
        )
        update_extension_enablement(
            home / ".gemini" / "extensions" / "extension-enablement.json",
            "scawful-skills",
            f"{home}/*",
            dry_run=args.dry_run,
        )
    else:
        print("skip: skills/GEMINI.md not found; gemini extension not wired")

    if (home / ".context" / "knowledge").exists():
        ensure_symlink(skills_root, context_skills, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
