#!/usr/bin/env python3
import json
import subprocess
import random
import argparse
import re
from pathlib import Path

# Paths
OOS_REPO = Path.home() / "src/hobby/oracle-of-secrets"
GUIDELINES_DIR = OOS_REPO / ".context/knowledge"
OUTPUT_DIR = Path.home() / "src/lab/afs/training_data/synthetic/oos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load Guidelines
def load_guidelines():
    guidelines = {}
    for file in GUIDELINES_DIR.glob("*.md"):
        with open(file, 'r') as f:
            guidelines[file.stem] = f.read()
    return guidelines

# Git Context Functions
def get_recent_commits(limit=100):
    cmd = ["git", "log", f"-n {limit}", "--format=%H|%s|%ai"]
    result = subprocess.run(cmd, cwd=OOS_REPO, capture_output=True, text=True)
    commits = []
    for line in result.stdout.strip().split("\n"):
        if "|" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                commits.append({"hash": parts[0], "subject": parts[1], "date": parts[2]})
    return commits

def get_commit_diff(commit_hash):
    cmd = ["git", "show", commit_hash, "--format=", "-p"]
    result = subprocess.run(cmd, cwd=OOS_REPO, capture_output=True, text=True)
    return result.stdout

# Pattern Generator for high-quality synthetic ASM
def synthesize_sample(commit, guidelines):
    subject = commit['subject'].lower()
    
    # Identify Expert
    expert = "farore" if any(x in subject for x in ["fix", "bug", "crash", "issue", "regress"]) else "oos_specialist"
    
    # Contextual Logic based on Subject
    if "mask" in subject:
        system = "Masks"
        instruction = f"Implement a system-level modification for the {system} following the pattern in commit {commit['hash'][:8]}: {commit['subject']}"
    elif "zsow" in subject or "overworld" in subject:
        system = "ZSOW_v3"
        instruction = f"Modify the ZSOW v3 overworld mapping for map transformations as seen in {commit['hash'][:8]}: {commit['subject']}"
    elif "menu" in subject or "hud" in subject:
        system = "Menu"
        instruction = f"Update the custom Oracle {system} logic based on the refactor: {commit['subject']}"
    else:
        system = "Core"
        instruction = f"Apply a technical patch to the Oracle {system} as described in: {commit['subject']}"

    # Extract relevant ASM patterns from diff if possible
    diff = get_commit_diff(commit['hash'])
    asm_blocks = re.findall(r'^\+([ \t]*[^+\- ].*)$', diff, re.MULTILINE)
    context_asm = "\n".join(asm_blocks[:10]) if asm_blocks else "; No new ASM lines found in diff."

    return {
        "instruction": instruction,
        "input": f"Targeting {system} system. Reference Commit: {commit['subject']}",
        "output": f"; Oracle of Secrets ASM Implementation\nnamespace Oracle {{\n{context_asm}\n}}",
        "expert": expert,
        "metadata": {
            "source_commit": commit['hash'],
            "system": system,
            "synthetic": True,
            "date": commit['date']
        }
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="Number of samples to generate")
    args = parser.parse_args()

    # In a real scenario, this script would handle 1000s of commits
    commits = get_recent_commits(args.limit)
    guidelines = load_guidelines()
    
    samples = []
    print(f"Synthesizing {len(commits)} high-fidelity samples...")
    for commit in commits:
        sample = synthesize_sample(commit, guidelines)
        samples.append(sample)

    output_file = OUTPUT_DIR / "oos_synthetic_scaled_v2.jsonl"
    with open(output_file, "w") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")
    
    print(f"Success! Generated {len(samples)} samples to {output_file}")

if __name__ == "__main__":
    main()
