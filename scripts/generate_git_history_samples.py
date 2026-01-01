#!/usr/bin/env python3
"""
Generate training samples from git history diffs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import List


def run_git(repo: Path, args: List[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout


def get_commit_hashes(repo: Path, max_commits: int, since: str | None, paths: List[str]) -> List[str]:
    args = ["log", "--pretty=format:%H", f"-n{max_commits}"]
    if since:
        args.append(f"--since={since}")
    if paths:
        args.append("--")
        args.extend(paths)
    output = run_git(repo, args)
    return [line.strip() for line in output.splitlines() if line.strip()]


def get_commit_message(repo: Path, commit_hash: str) -> str:
    output = run_git(repo, ["log", "-1", "--pretty=format:%s%n%n%b", commit_hash])
    return output.strip()


def get_commit_diff(repo: Path, commit_hash: str, paths: List[str]) -> str:
    args = ["show", "--unified=3", "--no-color", commit_hash]
    if paths:
        args.append("--")
        args.extend(paths)
    return run_git(repo, args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True, help="Git repo to scan.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path.")
    parser.add_argument("--max-commits", type=int, default=200, help="Max commits to scan.")
    parser.add_argument("--since", type=str, default=None, help="Git since filter (e.g. '6 months ago').")
    parser.add_argument(
        "--paths",
        nargs="*",
        default=["*.asm"],
        help="Path filters (default: *.asm).",
    )
    parser.add_argument("--max-lines", type=int, default=200, help="Max diff lines per sample.")
    parser.add_argument("--min-lines", type=int, default=5, help="Min diff lines per sample.")
    args = parser.parse_args()

    if not args.repo.exists():
        raise SystemExit(f"Repo not found: {args.repo}")

    commits = get_commit_hashes(args.repo, args.max_commits, args.since, args.paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with args.output.open("w", encoding="utf-8") as handle:
        for commit_hash in commits:
            message = get_commit_message(args.repo, commit_hash)
            if not message:
                continue
            diff = get_commit_diff(args.repo, commit_hash, args.paths)
            lines = diff.splitlines()
            if len(lines) < args.min_lines:
                continue
            if len(lines) > args.max_lines:
                lines = lines[: args.max_lines]
                diff = "\n".join(lines)
            record = {
                "instruction": "Summarize the intent of this ASM change.",
                "input": f"```diff\n{diff}\n```",
                "output": message,
                "domain": "asm-git",
                "source": str(args.repo),
                "commit": commit_hash,
            }
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            count += 1

    print(f"Generated {count} samples -> {args.output}")


if __name__ == "__main__":
    main()
