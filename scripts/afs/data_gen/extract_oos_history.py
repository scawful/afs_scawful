#!/usr/bin/env python3
"""Extract Oracle of Secrets git history for training data.

Creates training samples from:
1. Bug fix commits (for Farore - debugging)
2. Feature implementations (for OoS specialists)
3. Refactoring patterns (for best practices)
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
import re

OOS_REPO = Path.home() / "src/hobby/oracle-of-secrets"
OUTPUT_DIR = Path.home() / ".context/training_pools"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_git(args: list[str], cwd: Path = OOS_REPO) -> str:
    """Run git command and return output."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def get_commits(since: str = "2023-01-01", grep: str | None = None) -> list[dict]:
    """Get commits with metadata."""
    args = ["log", f"--since={since}", "--format=%H|%ai|%s"]
    if grep:
        args.extend(["--grep", grep])

    output = run_git(args)
    commits = []
    for line in output.split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0],
                "date": parts[1],
                "message": parts[2]
            })
    return commits

def get_commit_diff(commit_hash: str, name_only: bool = False) -> str:
    """Get diff for a commit."""
    args = ["show", commit_hash]
    if name_only:
        args.extend(["--name-only", "--format="])
    else:
        args.extend(["--format=", "-p"])
    return run_git(args)

def categorize_commit(message: str) -> str:
    """Categorize commit by type."""
    msg_lower = message.lower()
    if any(word in msg_lower for word in ["fix", "bug", "crash", "issue", "regression"]):
        return "bugfix"
    elif any(word in msg_lower for word in ["add", "implement", "feat", "new"]):
        return "feature"
    elif any(word in msg_lower for word in ["refactor", "clean", "optimize"]):
        return "refactor"
    elif any(word in msg_lower for word in ["doc", "update", "readme"]):
        return "docs"
    else:
        return "other"

def extract_asm_files_changed(diff_output: str) -> list[str]:
    """Extract .asm files from diff."""
    files = []
    for line in diff_output.split("\n"):
        if line.endswith(".asm"):
            files.append(line.strip())
    return files

def create_bugfix_sample(commit: dict, diff: str) -> dict | None:
    """Create training sample for Farore (debugging)."""
    # Extract what was fixed
    asm_files = extract_asm_files_changed(get_commit_diff(commit["hash"], name_only=True))
    if not asm_files:
        return None

    # Get the actual code changes
    code_diff = get_commit_diff(commit["hash"])

    # Truncate if too long
    if len(code_diff) > 8000:
        code_diff = code_diff[:8000] + "\n... [truncated]"

    return {
        "input": f"Debug this issue in Oracle of Secrets: {commit['message']}\n\nFiles affected: {', '.join(asm_files)}",
        "output": f"This bug was fixed with the following changes:\n\n{code_diff}",
        "domain": "oracle_of_secrets",
        "category": "bugfix",
        "source": "git_history",
        "timestamp": commit["date"],
        "metadata": {
            "commit_hash": commit["hash"],
            "files_changed": asm_files,
            "expert": "farore",
            "tags": ["debugging", "bugfix", "oracle-of-secrets"],
        }
    }

def create_feature_sample(commit: dict, diff: str) -> dict | None:
    """Create training sample for OoS specialist."""
    asm_files = extract_asm_files_changed(get_commit_diff(commit["hash"], name_only=True))
    if not asm_files:
        return None

    code_diff = get_commit_diff(commit["hash"])
    if len(code_diff) > 8000:
        code_diff = code_diff[:8000] + "\n... [truncated]"

    return {
        "input": f"Implement this feature for Oracle of Secrets ROM hack: {commit['message']}",
        "output": f"Here's how this feature was implemented:\n\n{code_diff}",
        "domain": "oracle_of_secrets",
        "category": "feature",
        "source": "git_history",
        "timestamp": commit["date"],
        "metadata": {
            "commit_hash": commit["hash"],
            "files_changed": asm_files,
            "expert": "oracle_specialist",
            "tags": ["feature", "implementation", "oracle-of-secrets"],
        }
    }

def main():
    print("Extracting Oracle of Secrets git history...")

    # Get bug fix commits
    bugfix_commits = get_commits(grep="Fix")
    print(f"Found {len(bugfix_commits)} bug fix commits")

    # Get feature commits
    feature_commits = get_commits(grep="Add\\|Implement\\|feat")
    print(f"Found {len(feature_commits)} feature commits")

    # Create samples
    bugfix_samples = []
    feature_samples = []

    for commit in bugfix_commits[:50]:  # Limit to 50 most recent
        sample = create_bugfix_sample(commit, "")
        if sample:
            bugfix_samples.append(sample)

    for commit in feature_commits[:50]:
        sample = create_feature_sample(commit, "")
        if sample:
            feature_samples.append(sample)

    print(f"Created {len(bugfix_samples)} bugfix samples")
    print(f"Created {len(feature_samples)} feature samples")

    # Save outputs
    bugfix_path = OUTPUT_DIR / "oos_bugfix_samples.jsonl"
    feature_path = OUTPUT_DIR / "oos_feature_samples.jsonl"

    with open(bugfix_path, "w") as f:
        for sample in bugfix_samples:
            f.write(json.dumps(sample) + "\n")

    with open(feature_path, "w") as f:
        for sample in feature_samples:
            f.write(json.dumps(sample) + "\n")

    print(f"\nSaved to:")
    print(f"  {bugfix_path}")
    print(f"  {feature_path}")

    # Create timeline summary
    timeline = {
        "project": "Oracle of Secrets",
        "total_commits": len(get_commits(since="2022-01-01")),
        "bugfix_commits": len(bugfix_commits),
        "feature_commits": len(feature_commits),
        "extracted_at": datetime.now().isoformat(),
        "categories": {
            "bugfix": len(bugfix_samples),
            "feature": len(feature_samples),
        }
    }

    timeline_path = OUTPUT_DIR / "oos_timeline.json"
    with open(timeline_path, "w") as f:
        json.dump(timeline, f, indent=2)
    print(f"  {timeline_path}")

if __name__ == "__main__":
    main()
