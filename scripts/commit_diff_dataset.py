#!/usr/bin/env python3
"""
commit_diff_dataset.py - Build commit-message ↔ diff training pairs from ~/src repos.

Zero API cost: all data is extracted directly from local git history.
Generates two training directions:
  message→diff : "Implement this change" → actual diff  (code synthesis)
  diff→message : "Write a commit message" → commit text  (code understanding)

Usage:
  commit_diff_dataset.py scan                   # Preview extractable commits
  commit_diff_dataset.py generate [--output FILE] [--max N] [--projects a,b,c]
  commit_diff_dataset.py stats [--input FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

COMMITS_FILE = (
    Path(__file__).resolve().parents[1]
    / "data" / "persona_raw" / "git_commits.jsonl"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "data" / "training_data" / "commit_diff_v1.jsonl"
)

# ─── Repo discovery ───────────────────────────────────────────────────────────

SRC_ROOTS = [
    Path.home() / "src" / "lab",
    Path.home() / "src" / "hobby",
    Path.home() / "src" / "tools",
    Path.home() / "src" / "config",
    Path.home() / "src",
]


def build_repo_map() -> dict[str, Path]:
    """Map project name → git repo path."""
    repos: dict[str, Path] = {}
    seen: set[Path] = set()
    for root in SRC_ROOTS:
        if not root.exists():
            continue
        for child in root.iterdir():
            if child in seen or not child.is_dir():
                continue
            if (child / ".git").exists():
                repos[child.name] = child
                seen.add(child)
            else:
                # one level deeper (e.g. src/config/dotfiles)
                for sub in child.iterdir():
                    if sub not in seen and sub.is_dir() and (sub / ".git").exists():
                        repos[sub.name] = sub
                        seen.add(sub)
    return repos


# ─── Filtering ────────────────────────────────────────────────────────────────

MIN_LINES = 4
MAX_LINES = 120
MAX_FILES = 6

# Files whose diffs add noise but no signal
SKIP_PATTERNS = re.compile(
    r"(package-lock\.json|yarn\.lock|Cargo\.lock|poetry\.lock"
    r"|\.min\.js|\.min\.css|__pycache__|\.pyc"
    r"|\.pb\.go|_pb2\.py|generated\.|\.g\.dart)",
    re.IGNORECASE,
)

# Commit messages that are noise
BAD_MESSAGE_RE = re.compile(
    r"^(wip|temp|tmp|fixup|squash|merge (branch|pull|remote)|"
    r"update readme|initial commit|bump version|revert \")",
    re.IGNORECASE,
)

LANGUAGE_MAP = {
    ".c": "C", ".h": "C",
    ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
    ".py": "Python", ".lua": "Lua",
    ".swift": "Swift", ".ts": "TypeScript",
    ".js": "JavaScript", ".rs": "Rust",
    ".go": "Go", ".asm": "65816 ASM", ".s": "ASM",
    ".el": "Emacs Lisp",
}


def detect_language(files: list[str]) -> str:
    counts: Counter[str] = Counter()
    for f in files:
        ext = Path(f).suffix.lower()
        lang = LANGUAGE_MAP.get(ext)
        if lang:
            counts[lang] += 1
    return counts.most_common(1)[0][0] if counts else "unknown"


def is_merge_commit(sha: str, repo: Path) -> bool:
    r = subprocess.run(
        ["git", "log", "--format=%P", "-1", sha],
        cwd=repo, capture_output=True, text=True,
    )
    return len(r.stdout.strip().split()) > 1


def get_stat(sha: str, repo: Path) -> tuple[list[str], int, int] | None:
    """Return (changed_files, insertions, deletions) or None if error."""
    r = subprocess.run(
        ["git", "show", sha, "--stat", "--no-color", "--format="],
        cwd=repo, capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return None
    lines = r.stdout.strip().splitlines()
    # Last line: " N files changed, X insertions(+), Y deletions(-)"
    summary = lines[-1]
    files = [l.strip().split("|")[0].strip() for l in lines[:-1] if "|" in l]
    ins = int(re.search(r"(\d+) insertion", summary).group(1)) if "insertion" in summary else 0
    dels = int(re.search(r"(\d+) deletion", summary).group(1)) if "deletion" in summary else 0
    return files, ins, dels


def get_diff(sha: str, repo: Path) -> str | None:
    r = subprocess.run(
        ["git", "show", sha, "--unified=3", "--no-color", "--format="],
        cwd=repo, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    diff = r.stdout.strip()
    # Strip lines for skippable files
    filtered: list[str] = []
    skip_block = False
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            skip_block = bool(SKIP_PATTERNS.search(line))
        if not skip_block:
            filtered.append(line)
    return "\n".join(filtered).strip() or None


# ─── Pair builder ─────────────────────────────────────────────────────────────

NAYRU_SYSTEM = (
    "You are Nayru. You write minimal, idiomatic code. "
    "When asked to implement a change, you output only the unified diff — "
    "no explanation, no preamble. The diff must compile and be correct."
)

OCKHAM_MESSAGE_SYSTEM = (
    "You are a precise developer. Given a diff, write a single concise commit message "
    "that captures the intent. Imperative mood. No period. Under 72 characters."
)


def make_pairs(
    message: str,
    diff: str,
    project: str,
    sha: str,
    files: list[str],
    ins: int,
    dels: int,
) -> list[dict]:
    lang = detect_language(files)
    file_list = ", ".join(Path(f).name for f in files[:4])
    meta = {
        "source": "git_commit_diff",
        "project": project,
        "sha": sha,
        "language": lang,
        "files_changed": len(files),
        "insertions": ins,
        "deletions": dels,
    }

    pairs = []

    # Direction 1: message → diff (code synthesis)
    pairs.append({
        "messages": [
            {"role": "system", "content": NAYRU_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Implement the following change in `{project}` ({lang}):\n\n"
                    f"{message}\n\nAffected files: {file_list}"
                ),
            },
            {"role": "assistant", "content": f"```diff\n{diff}\n```"},
        ],
        "_meta": {**meta, "direction": "message_to_diff"},
    })

    # Direction 2: diff → message (code understanding)
    pairs.append({
        "messages": [
            {"role": "system", "content": OCKHAM_MESSAGE_SYSTEM},
            {
                "role": "user",
                "content": f"Write a commit message for this diff:\n\n```diff\n{diff}\n```",
            },
            {"role": "assistant", "content": message},
        ],
        "_meta": {**meta, "direction": "diff_to_message"},
    })

    return pairs


# ─── Subcommands ──────────────────────────────────────────────────────────────

def load_commits() -> list[dict]:
    return [
        json.loads(l)
        for l in COMMITS_FILE.read_text(errors="replace").splitlines()
        if l.strip()
    ]


def cmd_scan(args):
    repo_map = build_repo_map()
    commits = load_commits()
    filter_projects = set(args.projects.split(",")) if args.projects else None

    by_project: dict[str, list[dict]] = {}
    for c in commits:
        proj = c["project"]
        if filter_projects and proj not in filter_projects:
            continue
        if proj not in repo_map:
            continue
        by_project.setdefault(proj, []).append(c)

    total_eligible = 0
    print(f"\nRepo map: {len(repo_map)} repos found")
    print(f"Commits with resolvable repo: {sum(len(v) for v in by_project.values())}")
    print(f"\n{'PROJECT':30s}  {'COMMITS':>7}  {'ESTIMATED':>9}")
    print("─" * 55)

    sample_results: dict[str, int] = {}
    for proj, cs in sorted(by_project.items()):
        repo = repo_map[proj]
        # Sample first 5 to estimate yield
        good = 0
        sample = cs[:min(10, len(cs))]
        for c in sample:
            sha = c["context"].replace("sha:", "")
            msg = c["text"]
            if BAD_MESSAGE_RE.match(msg) or len(msg) < 15:
                continue
            if is_merge_commit(sha, repo):
                continue
            stat = get_stat(sha, repo)
            if not stat:
                continue
            files, ins, dels = stat
            total = ins + dels
            if MIN_LINES <= total <= MAX_LINES and len(files) <= MAX_FILES:
                good += 1
        rate = good / len(sample) if sample else 0
        est = int(rate * len(cs))
        total_eligible += est
        sample_results[proj] = est
        print(f"  {proj:28s}  {len(cs):7d}  ~{est:8d}")

    print("─" * 55)
    print(f"  {'TOTAL':28s}  {sum(len(v) for v in by_project.values()):7d}  ~{total_eligible:8d}")
    print(f"\nEstimated pairs (×2 directions): ~{total_eligible * 2}")


async def _generate(args):
    repo_map = build_repo_map()
    commits = load_commits()
    out_path = Path(args.output) if args.output else DEFAULT_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_commits = args.max
    filter_projects = set(args.projects.split(",")) if args.projects else None

    # Load already-done SHAs for resume support
    done_shas: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(errors="replace").splitlines():
            try:
                r = json.loads(line)
                sha = r.get("_meta", {}).get("sha")
                if sha:
                    done_shas.add(sha)
            except Exception:
                pass

    processed = 0
    written = 0
    skipped_no_repo = 0
    skipped_filter = 0
    skipped_done = 0

    with open(out_path, "a") as out:
        for c in commits:
            if max_commits and processed >= max_commits:
                break

            proj = c["project"]
            sha = c["context"].replace("sha:", "")
            msg = c["text"].strip()

            if filter_projects and proj not in filter_projects:
                skipped_filter += 1
                continue
            if proj not in repo_map:
                skipped_no_repo += 1
                continue
            if sha in done_shas:
                skipped_done += 1
                continue
            if BAD_MESSAGE_RE.match(msg) or len(msg) < 15:
                skipped_filter += 1
                continue

            repo = repo_map[proj]

            if is_merge_commit(sha, repo):
                skipped_filter += 1
                continue

            stat = get_stat(sha, repo)
            if not stat:
                skipped_no_repo += 1
                continue

            files, ins, dels = stat
            total_lines = ins + dels
            if not (MIN_LINES <= total_lines <= MAX_LINES and len(files) <= MAX_FILES):
                skipped_filter += 1
                continue

            diff = get_diff(sha, repo)
            if not diff or len(diff) < 50:
                skipped_filter += 1
                continue

            pairs = make_pairs(msg, diff, proj, sha, files, ins, dels)
            for p in pairs:
                out.write(json.dumps(p) + "\n")
            out.flush()
            written += len(pairs)
            done_shas.add(sha)
            processed += 1

            if processed % 25 == 0:
                print(f"  Progress: {processed} commits → {written} pairs written")

    print(f"\nDone.")
    print(f"  Commits processed: {processed}")
    print(f"  Pairs written:     {written}")
    print(f"  Skipped (no repo): {skipped_no_repo}")
    print(f"  Skipped (filter):  {skipped_filter}")
    print(f"  Skipped (done):    {skipped_done}")
    print(f"  Output: {out_path}")


def cmd_generate(args):
    import asyncio
    asyncio.run(_generate(args))


def cmd_stats(args):
    path = Path(args.input) if args.input else DEFAULT_OUTPUT
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    by_dir: Counter[str] = Counter()
    by_proj: Counter[str] = Counter()
    by_lang: Counter[str] = Counter()
    sizes: list[int] = []
    for r in records:
        m = r.get("_meta", {})
        by_dir[m.get("direction", "?")] += 1
        by_proj[m.get("project", "?")] += 1
        by_lang[m.get("language", "?")] += 1
        sizes.append(m.get("insertions", 0) + m.get("deletions", 0))
    print(f"File:    {path}")
    print(f"Records: {len(records)}")
    print(f"\nBy direction:")
    for k, v in by_dir.most_common():
        print(f"  {k:25s} {v}")
    print(f"\nBy project (top 10):")
    for k, v in by_proj.most_common(10):
        print(f"  {k:25s} {v}")
    print(f"\nBy language:")
    for k, v in by_lang.most_common():
        print(f"  {k:25s} {v}")
    if sizes:
        print(f"\nAvg lines changed: {sum(sizes)/len(sizes):.0f}")
        print(f"Max lines changed: {max(sizes)}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Commit-diff training dataset builder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Preview extractable commits")
    p_scan.add_argument("--projects", metavar="A,B,C", help="Comma-separated project filter")

    p_gen = sub.add_parser("generate", help="Build the dataset")
    p_gen.add_argument("--output", "-o", metavar="FILE")
    p_gen.add_argument("--max", type=int, metavar="N", help="Max commits to process")
    p_gen.add_argument("--projects", metavar="A,B,C", help="Comma-separated project filter")

    p_stats = sub.add_parser("stats", help="Dataset statistics")
    p_stats.add_argument("--input", "-i", metavar="FILE")

    args = parser.parse_args()
    {"scan": cmd_scan, "generate": cmd_generate, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    main()
