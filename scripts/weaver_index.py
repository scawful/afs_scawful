#!/usr/bin/env python3
"""
weaver_index.py - Index the ~/src universe for cross-project intelligence.

Builds a "Problem-Solution" knowledge graph across all projects, then generates
training pairs for the Weaver/Synapse model: a model that knows how patterns from
one project apply to another.

Usage:
  weaver_index.py scan [--src DIR]              # Discover projects and extract patterns
  weaver_index.py build [--output FILE]         # Build the full cross-project index
  weaver_index.py generate [--teacher gemini]   # Generate Q&A training pairs
  weaver_index.py stats [--index FILE]          # Show index statistics
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SRC_ROOT = Path.home() / "src"
DEFAULT_INDEX = Path.home() / "src" / "lab" / "afs-scawful" / "data" / "weaver_index.jsonl"
DEFAULT_DATASET = Path.home() / "src" / "lab" / "afs-scawful" / "data" / "training_data" / "weaver_v1.jsonl"

# Files that describe a project's architecture and purpose
SIGNAL_FILES = [
    "README.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md",
    "ARCHITECTURE.md", "DESIGN.md", "PROJECT.toml",
    "CHANGELOG.md", "ROADMAP.md",
]

# Source code patterns worth indexing per language
CODE_PATTERNS = {
    ".c":    ["typedef struct", "pthread_", "mmap(", "shm_open", "ioctl", "epoll"],
    ".cc":   ["class ", "std::unique_ptr", "template<", "virtual ", "override"],
    ".cpp":  ["class ", "std::unique_ptr", "template<", "virtual ", "override"],
    ".py":   ["async def", "@dataclass", "asyncio", "subprocess", "click"],
    ".lua":  ["function ", "require", "pcall", "coroutine"],
    ".swift": ["@Observable", "SwiftData", "NavigationSplitView", "actor "],
}

# Problem categories for cross-project synthesis
PROBLEM_TAGS = {
    "ipc":         ["shm_open", "mmap(", "socketpair", "pipe(", "semaphore_open"],
    "concurrency": ["pthread_", "async def", "asyncio", "Semaphore", "actor "],
    "state_mgmt":  ["state_manager", "@Observable", "Redux", "SwiftData", "StateStore"],
    "rendering":   ["sketchybar", "imgui", "OpenGL", "Metal", "CoreGraphics"],
    "networking":  ["epoll", "URLSession", "httpx", "FastAPI", "websocket", "aiohttp"],
    "storage":     ["SwiftData", "SQLAlchemy", "sqlite3", "ftruncate", "ModelContainer"],
    "emulation":   ["65816", "PPU", "DMA", "SPC700", "VRAM", "OAM", "WRAM"],
    "ml_training": ["LoRA", "PEFT", "tokenizer", "distill", "train_peft", "unsloth"],
}


@dataclass
class ProjectEntry:
    name: str
    path: str
    description: str
    language: str
    problem_tags: list[str]
    key_patterns: list[str]
    doc_snippets: list[str]


def detect_language(root: Path) -> str:
    exts: dict[str, int] = {}
    for p in root.rglob("*"):
        if p.suffix and not any(part.startswith(".") for part in p.parts[len(root.parts):]):
            exts[p.suffix] = exts.get(p.suffix, 0) + 1
    if not exts:
        return "unknown"
    dominant = max(exts, key=lambda e: exts[e])
    return {".py": "Python", ".c": "C", ".cpp": "C++", ".cc": "C++",
            ".swift": "Swift", ".lua": "Lua", ".ts": "TypeScript",
            ".rs": "Rust", ".go": "Go"}.get(dominant, dominant[1:].upper())


def extract_description(root: Path) -> str:
    for name in SIGNAL_FILES:
        f = root / name
        if f.exists():
            try:
                lines = f.read_text(errors="replace").splitlines()
                # Find first non-empty, non-heading line
                for line in lines[:30]:
                    line = line.strip().lstrip("#").strip()
                    if line and len(line) > 10:
                        return line[:200]
            except OSError:
                pass
    return ""


def extract_doc_snippets(root: Path, max_snippets: int = 5) -> list[str]:
    snippets = []
    for name in SIGNAL_FILES:
        f = root / name
        if f.exists() and len(snippets) < max_snippets:
            try:
                content = f.read_text(errors="replace")[:3000]
                snippets.append(f"## {name}\n{content}")
            except OSError:
                pass
    return snippets


def detect_patterns(root: Path) -> tuple[list[str], list[str]]:
    """Return (problem_tags, key_code_patterns) found in source files."""
    found_tags: set[str] = set()
    found_patterns: set[str] = set()

    for p in root.rglob("*"):
        if p.suffix not in CODE_PATTERNS:
            continue
        if any(part in {".git", "build", "__pycache__", ".venv"} for part in p.parts):
            continue
        try:
            text = p.read_text(errors="replace", encoding="utf-8")
        except OSError:
            continue

        for tag, signals in PROBLEM_TAGS.items():
            if any(sig in text for sig in signals):
                found_tags.add(tag)

        for pattern in CODE_PATTERNS.get(p.suffix, []):
            if pattern in text:
                found_patterns.add(f"{p.suffix[1:]}:{pattern.strip()}")

    return sorted(found_tags), sorted(found_patterns)


def is_project(path: Path) -> bool:
    """Check if a directory looks like a real project."""
    indicators = [
        "README.md", "CMakeLists.txt", "pyproject.toml", "package.json",
        "Cargo.toml", "go.mod", "*.xcodeproj", "AGENTS.md", "CLAUDE.md",
        "PROJECT.toml",
    ]
    for ind in indicators:
        if list(path.glob(ind)):
            return True
    return False


def scan_projects(src_root: Path) -> list[Path]:
    projects = []
    skip = {".git", "__pycache__", "build", "node_modules", ".venv", "venv"}
    for child in sorted(src_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in skip:
            continue
        if is_project(child):
            projects.append(child)
        else:
            # Check one level deeper
            for sub in sorted(child.iterdir()):
                if sub.is_dir() and is_project(sub) and sub.name not in skip:
                    projects.append(sub)
    return projects


# ─── Subcommands ───────────────────────────────────────────────────────────────

def cmd_scan(args):
    root = Path(args.src) if args.src else SRC_ROOT
    projects = scan_projects(root)
    print(f"Found {len(projects)} projects in {root}\n")
    for p in projects:
        lang = detect_language(p)
        desc = extract_description(p)
        tags, patterns = detect_patterns(p)
        print(f"  {p.name:30s}  [{lang:8s}]  {', '.join(tags[:4]) or '—'}")
        if desc:
            print(f"    {desc[:80]}")


def cmd_build(args):
    root = SRC_ROOT
    out_path = Path(args.output) if args.output else DEFAULT_INDEX
    out_path.parent.mkdir(parents=True, exist_ok=True)

    projects = scan_projects(root)
    print(f"Indexing {len(projects)} projects…")

    with open(out_path, "w") as out:
        for p in projects:
            try:
                lang = detect_language(p)
                desc = extract_description(p)
                tags, patterns = detect_patterns(p)
                snippets = extract_doc_snippets(p)
                entry = ProjectEntry(
                    name=p.name,
                    path=str(p),
                    description=desc,
                    language=lang,
                    problem_tags=tags,
                    key_patterns=patterns,
                    doc_snippets=snippets,
                )
                out.write(json.dumps(asdict(entry)) + "\n")
                print(f"  ✓ {p.name}")
            except Exception as e:
                print(f"  ✗ {p.name}: {e}", file=sys.stderr)

    print(f"\nIndex written to {out_path}")


WEAVER_SYSTEM = """\
You are Weaver. You know how every project in this developer's ~/src universe connects.
When asked how to solve a problem in one project, you draw on the patterns already solved
in other projects. You never suggest patterns the developer hasn't already used.
You reason from the index of their actual code, not from generic best practices."""


SKIP_NAMES = {
    # Backup/archive/external projects that don't represent active work
    "hafs-backup-20251219", "sketchybar.pre-restore", "mesen2-ARCHIVED",
    "boost_1_82_0", "opencv", "unsloth", "llama.cpp", "implot",
    "asar-repo", "untrunc", "JUCE", "acmlmboard",
}

# Core projects to prioritise in cross-project linking
CORE_PROJECTS = {
    "barista", "echoflow", "yaze", "halext-org", "afs-scawful",
    "oracle-of-secrets", "mesen2-oos", "mesen-s", "cortex",
    "afs", "afs_suite", "dotfiles", "tools", "training",
    "llama-harness", "nerv-xfer", "assembly", "65816-SNES-Assembly",
}


async def generate_qa_pairs(entries: list[dict], teacher: str, n_pairs: int = 3) -> list[dict]:
    """Generate cross-project Q&A pairs from the index."""
    # Filter to relevant projects — prefer core projects
    def entry_score(e: dict) -> int:
        name = e.get("name", "")
        if name in SKIP_NAMES:
            return -1
        if name in CORE_PROJECTS:
            return 2
        if e.get("description"):
            return 1
        return 0

    filtered = [e for e in entries if entry_score(e) >= 0]
    # Sort: core projects first
    filtered.sort(key=lambda e: -entry_score(e))

    seen_pairs: set[tuple[str, str]] = set()

    # Build candidate list per tag — max 3 pairs per tag, best core projects first
    by_tag: dict[str, list[dict]] = {}
    for e in filtered:
        for tag in e.get("problem_tags", []):
            by_tag.setdefault(tag, []).append(e)

    # Round-robin: one pair per tag until n_pairs reached
    tag_candidates: dict[str, list[tuple[dict, dict]]] = {}
    for tag, projs in by_tag.items():
        if len(projs) < 2:
            continue
        cands = []
        for i, a in enumerate(projs):
            for b in projs[i+1:]:
                if a["name"] != b["name"] and (a["name"], b["name"]) not in seen_pairs:
                    cands.append((a, b))
        if cands:
            tag_candidates[tag] = cands

    pairs: list[dict] = []
    # Alternate across tags to get diverse coverage
    tag_iters = {tag: iter(cands) for tag, cands in tag_candidates.items()}
    while len(pairs) < n_pairs and tag_iters:
        exhausted = []
        for tag, it in tag_iters.items():
            if len(pairs) >= n_pairs:
                break
            try:
                a, b = next(it)
                pair_key = (a["name"], b["name"])
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                question = (
                    f"I need to add {tag} to the `{b['name']}` project. "
                    f"How does `{a['name']}` handle this, and what should I reuse or adapt?"
                )
                context = (
                    f"## {a['name']} ({a['language']})\n{a['description']}\n\n"
                    f"Key patterns: {', '.join(a['key_patterns'][:5])}\n\n"
                    f"## {b['name']} ({b['language']})\n{b['description']}"
                )
                pairs.append({
                    "messages": [
                        {"role": "system", "content": WEAVER_SYSTEM},
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": f"[context]\n{context}\n\n[answer pending distillation]"},
                    ],
                    "_meta": {
                        "source": "weaver_index",
                        "tag": tag,
                        "project_a": a["name"],
                        "project_b": b["name"],
                        "needs_distillation": True,
                    }
                })
            except StopIteration:
                exhausted.append(tag)
        for tag in exhausted:
            del tag_iters[tag]

    return pairs


async def _run_generate(args):
    index_path = Path(args.index) if hasattr(args, "index") and args.index else DEFAULT_INDEX
    out_path = Path(args.output) if args.output else DEFAULT_DATASET
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not index_path.exists():
        print(f"Index not found: {index_path} — run 'build' first", file=sys.stderr)
        sys.exit(1)

    entries = []
    for line in index_path.read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except Exception:
            pass

    print(f"Loaded {len(entries)} project entries")
    pairs = await generate_qa_pairs(entries, args.teacher, n_pairs=50)
    with open(out_path, "w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")
    print(f"Wrote {len(pairs)} pairs to {out_path}")
    print("Note: pairs marked 'needs_distillation=True' need teacher model completion — run distill_cloud.py")


def cmd_generate(args):
    asyncio.run(_run_generate(args))


async def _distill_weaver(args):
    """Fill in [answer pending distillation] placeholders in weaver_v1.jsonl."""
    import os
    from google import genai
    from google.genai import types as gtypes

    data_path = Path(args.data) if hasattr(args, "data") and args.data else DEFAULT_DATASET
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[error] GOOGLE_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    records = [json.loads(l) for l in data_path.read_text().splitlines() if l.strip()]
    pending = [r for r in records if "[answer pending distillation]" in
               next((m["content"] for m in r.get("messages", []) if m["role"] == "assistant"), "")]
    done = len(records) - len(pending)
    print(f"Weaver distillation: {len(records)} records, {done} complete, {len(pending)} pending")

    if not pending:
        print("Nothing to distill.")
        return

    client = genai.Client(api_key=api_key)
    updated = 0

    for i, rec in enumerate(pending):
        msgs = rec["messages"]
        system_msg = next((m["content"] for m in msgs if m["role"] == "system"), "")
        user_msg = next((m["content"] for m in msgs if m["role"] == "user"), "")
        asst_msg = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
        # Extract the context block (everything before [answer pending distillation])
        context_block = asst_msg.split("[answer pending distillation]")[0].strip()

        full_prompt = (
            f"{system_msg}\n\n"
            f"User question: {user_msg}\n\n"
            f"Available context about the projects:\n{context_block}\n\n"
            f"Answer the user's question as Weaver, drawing on the context above. "
            f"Be specific: reference actual patterns from the context, not generic advice. "
            f"3-5 sentences maximum. Start with the answer, not preamble."
        )
        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=full_prompt,
                config=gtypes.GenerateContentConfig(temperature=0.7, max_output_tokens=512),
            )
            answer = resp.text.strip() if resp.text else ""
        except Exception as e:
            print(f"  [{i+1}/{len(pending)}] error: {e}", file=sys.stderr)
            continue

        if not answer:
            print(f"  [{i+1}/{len(pending)}] empty response, skipping")
            continue

        # Update in-place in the records list
        for rec_in_list in records:
            if rec_in_list is rec:
                for m in rec_in_list["messages"]:
                    if m["role"] == "assistant":
                        m["content"] = f"{context_block}\n\n{answer}"
                rec_in_list["_meta"]["needs_distillation"] = False
                break
        updated += 1
        print(f"  [{i+1}/{len(pending)}] filled {len(answer)} chars")

    # Rewrite the file
    data_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    print(f"\nDone. Filled {updated}/{len(pending)} pending answers in {data_path}")


def cmd_distill(args):
    asyncio.run(_distill_weaver(args))


def cmd_stats(args):
    index_path = Path(args.index) if args.index else DEFAULT_INDEX
    if not index_path.exists():
        print(f"Index not found: {index_path}", file=sys.stderr)
        sys.exit(1)
    entries = [json.loads(l) for l in index_path.read_text().splitlines() if l.strip()]
    tag_counts: dict[str, int] = {}
    lang_counts: dict[str, int] = {}
    for e in entries:
        lang_counts[e.get("language", "?")] = lang_counts.get(e.get("language", "?"), 0) + 1
        for t in e.get("problem_tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    print(f"Projects indexed: {len(entries)}")
    print("\nLanguages:")
    for k, v in sorted(lang_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:15s} {v}")
    print("\nProblem tags (cross-linking opportunities):")
    for k, v in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v} projects")


def main():
    parser = argparse.ArgumentParser(description="Weaver cross-project intelligence indexer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Discover projects")
    p_scan.add_argument("--src", metavar="DIR")

    p_build = sub.add_parser("build", help="Build full index")
    p_build.add_argument("--output", "-o", metavar="FILE")

    p_gen = sub.add_parser("generate", help="Generate training Q&A pairs")
    p_gen.add_argument("--teacher", choices=["gemini", "claude"], default="gemini")
    p_gen.add_argument("--index", metavar="FILE")
    p_gen.add_argument("--output", "-o", metavar="FILE")

    p_stats = sub.add_parser("stats", help="Index statistics")
    p_stats.add_argument("--index", metavar="FILE")

    p_distill = sub.add_parser("distill", help="Fill in placeholder answers with Gemini")
    p_distill.add_argument("--data", metavar="FILE", help="weaver_v1.jsonl path")

    args = parser.parse_args()
    {"scan": cmd_scan, "build": cmd_build,
     "generate": cmd_generate, "stats": cmd_stats,
     "distill": cmd_distill}[args.cmd](args)


if __name__ == "__main__":
    main()
