#!/usr/bin/env python3
"""
antislop_dataset.py - Build anti-slop training pairs from gold-standard codebases.

Scans barista (C/Lua) and yaze (C++) for clean, idiomatic code, then generates
"bloated enterprise" versions as the training INPUT and uses the original as OUTPUT.

This trains Ockham: a model that receives sloppy code and returns minimal, direct code.

Usage:
  antislop_dataset.py scan [--source barista|yaze|all]
  antislop_dataset.py generate [--source barista] [--teacher gemini|claude]
                                [--max-files 20] [--output FILE]
  antislop_dataset.py stats [--input FILE]
"""

import argparse
import asyncio
import json
import os
import sys
import hashlib
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()
except ImportError:
    pass

_provider_key_notice_emitted = False


def resolve_gemini_api_key() -> Optional[str]:
    """Resolve Gemini provider key deterministically and normalize env vars.

    Priority:
      1) GOOGLE_API_KEY
      2) GEMINI_API_KEY

    We also unset the non-selected key to avoid duplicate-key warnings from SDKs
    that inspect both environment variables.
    """
    global _provider_key_notice_emitted

    google_key = os.environ.get("GOOGLE_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    selected_name = None
    selected_key = None

    if google_key:
        selected_name = "GOOGLE_API_KEY"
        selected_key = google_key
    elif gemini_key:
        selected_name = "GEMINI_API_KEY"
        selected_key = gemini_key

    if selected_name == "GOOGLE_API_KEY":
        os.environ.pop("GEMINI_API_KEY", None)
    elif selected_name == "GEMINI_API_KEY":
        os.environ.pop("GOOGLE_API_KEY", None)

    if selected_key and not _provider_key_notice_emitted:
        print(f"[info] Gemini provider key selected: {selected_name}", file=sys.stderr)
        _provider_key_notice_emitted = True

    return selected_key


# Normalize provider key once at import-time to prevent SDK startup warnings.
resolve_gemini_api_key()

# ─── Gold-standard source paths ───────────────────────────────────────────────

SOURCES = {
    "barista": {
        "path": Path.home() / "src" / "lab" / "barista",
        "extensions": [".c", ".lua"],
        "exclude_dirs": {"build", ".git", "themes"},
        "description": "Memory-mapped C/Lua menu bar — tight resource management, no dynamic allocation",
    },
    "yaze": {
        "path": Path.home() / "src" / "hobby" / "yaze",
        "extensions": [".cc", ".h"],
        "exclude_dirs": {"build", "build-ios", "build-wasm", "ext", ".git", "venv"},
        # Only use emulation and core code — avoid GUI/editor layers
        "include_dirs": {"src/app/emu", "src/core"},
        "description": "SNES emulator in C++ — data-driven state machines, hardware-fidelity design",
    },
    "zelda3": {
        "path": Path.home() / "src" / "hobby" / "zelda3",
        "extensions": [".cpp", ".h", ".c"],
        "exclude_dirs": {"build", ".git"},
        "description": "Zelda3 decompilation — lookup tables, handler dispatch, cycle-accurate emulation",
    },
    "afs_distill": {
        "path": Path.home() / "src" / "lab" / "afs-scawful" / "scripts",
        "extensions": [".py"],
        "exclude_dirs": {"__pycache__", ".venv", "venv"},
        "description": "afs-scawful distillation scripts — async concurrency, dataclass-typed, provider-abstract",
    },
}

DEFAULT_OUTPUT = (
    Path.home() / "src" / "lab" / "afs-scawful" / "data" / "training_data" / "anti_slop_v1.jsonl"
)

# ─── File collection ───────────────────────────────────────────────────────────

MIN_LINES = 20
MAX_LINES = 400  # Skip files that are too large to fit in a single training sample


def collect_files(source_key: str) -> list[Path]:
    cfg = SOURCES[source_key]
    root = cfg["path"]
    exts = set(cfg["extensions"])
    skip = cfg["exclude_dirs"]
    include_dirs = cfg.get("include_dirs")  # optional whitelist of subdirs
    results = []

    if not root.exists():
        print(f"[warn] Source path not found: {root}", file=sys.stderr)
        return []

    for p in root.rglob("*"):
        if p.suffix not in exts:
            continue
        if any(part in skip for part in p.parts):
            continue
        # If include_dirs is set, file must be under one of those subdirs
        if include_dirs:
            rel = p.relative_to(root)
            if not any(str(rel).startswith(d) for d in include_dirs):
                continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            if MIN_LINES <= len(lines) <= MAX_LINES:
                results.append(p)
        except OSError:
            continue

    return results


def extract_snippet(path: Path, max_lines: int = MAX_LINES) -> Optional[str]:
    """Read and return file content, truncated to max_lines."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n// ... ({len(lines)} lines total, truncated)"
        return text
    except OSError:
        return None


# ─── Teacher model integration ─────────────────────────────────────────────────

SLOPIFY_SYSTEM = """\
You are a code transformation tool. Your task is to take clean, minimal, \
idiomatic code and rewrite it as bloated "enterprise" code:

- Add unnecessary abstraction layers (factories, managers, adapters)
- Add verbose comments that restate the obvious
- Split simple functions into multiple classes with one method each
- Add unused flexibility: config objects, strategy patterns, registries
- Use long variable names that add no meaning
- Add redundant error-wrapping without fixing root causes
- Prefer 10 lines over 1 line wherever possible

Output ONLY the rewritten code. No explanation."""

OCKHAM_SYSTEM = """\
You are Ockham. Your law: entities shall not be multiplied beyond necessity.
When you receive bloated, over-abstracted code, you output the minimal viable logic.
Remove unnecessary abstractions. Eradicate boilerplate. Keep the semantics, kill the fat.
Output ONLY code. No explanation. No comments unless they convey meaning that the code cannot."""


async def slopify_with_gemini(code: str, filename: str) -> Optional[str]:
    """Generate a bloated 'enterprise' version of clean code using Gemini."""
    try:
        from google import genai
        from google.genai import types as gtypes
        api_key = resolve_gemini_api_key()
        if not api_key:
            print("[warn] No GOOGLE_API_KEY or GEMINI_API_KEY found", file=sys.stderr)
            return None
        client = genai.Client(api_key=api_key)
        prompt = f"File: {filename}\n\n```\n{code}\n```"
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=f"{SLOPIFY_SYSTEM}\n\n{prompt}",
            config=gtypes.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8192,  # thinking model needs larger budget
            ),
        )
        return response.text
    except Exception as e:
        print(f"[error] Gemini slopify failed: {e}", file=sys.stderr)
        return None


async def slopify_with_claude(code: str, filename: str) -> Optional[str]:
    """Generate a bloated version using Claude (Anthropic API)."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SLOPIFY_SYSTEM,
            messages=[{"role": "user", "content": f"File: {filename}\n\n```\n{code}\n```"}],
        )
        return msg.content[0].text
    except Exception as e:
        print(f"[error] Claude slopify failed: {e}", file=sys.stderr)
        return None


async def slopify(code: str, filename: str, teacher: str) -> Optional[str]:
    if teacher == "gemini":
        return await slopify_with_gemini(code, filename)
    elif teacher == "claude":
        return await slopify_with_claude(code, filename)
    else:
        raise ValueError(f"Unknown teacher: {teacher}")


# ─── Dataset record builder ────────────────────────────────────────────────────

def make_record(
    pristine: str,
    sloppy: str,
    source_path: Path,
    source_key: str,
    teacher: str,
) -> dict:
    return {
        "messages": [
            {"role": "system", "content": OCKHAM_SYSTEM},
            {"role": "user", "content": f"# Refactor this bloated code\n\n```\n{sloppy}\n```"},
            {"role": "assistant", "content": f"```\n{pristine}\n```"},
        ],
        "_meta": {
            "source_file": str(source_path.name),
            "source_repo": source_key,
            "teacher_model": teacher,
            "pristine_lines": len(pristine.splitlines()),
            "sloppy_lines": len(sloppy.splitlines()),
            "content_hash": hashlib.md5(pristine.encode()).hexdigest()[:8],
        }
    }


# ─── Subcommands ───────────────────────────────────────────────────────────────

def cmd_scan(args):
    sources = args.source.split(",") if args.source != "all" else list(SOURCES.keys())
    for key in sources:
        if key not in SOURCES:
            print(f"Unknown source: {key}", file=sys.stderr)
            continue
        cfg = SOURCES[key]
        files = collect_files(key)
        print(f"\n{key}  ({cfg['description']})")
        print(f"  Path:  {cfg['path']}")
        print(f"  Files: {len(files)} eligible")
        for p in files[:10]:
            lines = len(p.read_text(errors="replace").splitlines())
            print(f"    {p.relative_to(cfg['path'])}  ({lines} lines)")
        if len(files) > 10:
            print(f"    ... and {len(files) - 10} more")


async def _run_generate(args):
    sources = args.source.split(",") if args.source != "all" else list(SOURCES.keys())
    teacher = args.teacher
    max_files = args.max_files
    out_path = Path(args.output) if args.output else DEFAULT_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing content hashes to avoid duplicates
    existing_hashes: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                rec = json.loads(line)
                h = rec.get("_meta", {}).get("content_hash")
                if h:
                    existing_hashes.add(h)
            except Exception:
                pass

    total_new = 0
    with open(out_path, "a") as out:
        for key in sources:
            files = collect_files(key)[:max_files]
            print(f"\n[{key}] Processing {len(files)} files with teacher={teacher}…")
            for fp in files:
                code = extract_snippet(fp)
                if not code:
                    continue
                # Skip if already processed
                h = hashlib.md5(code.encode()).hexdigest()[:8]
                if h in existing_hashes:
                    print(f"  skip (dup): {fp.name}")
                    continue

                print(f"  slopify: {fp.name}")
                sloppy = await slopify(code, fp.name, teacher)
                if not sloppy:
                    print(f"  [fail]: {fp.name}")
                    continue

                rec = make_record(code, sloppy, fp, key, teacher)
                out.write(json.dumps(rec) + "\n")
                out.flush()
                existing_hashes.add(h)
                total_new += 1

    print(f"\nDone — {total_new} new samples written to {out_path}")


def cmd_generate(args):
    asyncio.run(_run_generate(args))


def cmd_stats(args):
    path = Path(args.input) if args.input else DEFAULT_OUTPUT
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    records = []
    for line in path.read_text().splitlines():
        try:
            records.append(json.loads(line))
        except Exception:
            pass

    by_repo: dict[str, int] = {}
    by_teacher: dict[str, int] = {}
    pristine_lens, sloppy_lens = [], []

    for rec in records:
        meta = rec.get("_meta", {})
        repo = meta.get("source_repo", "unknown")
        teacher = meta.get("teacher_model", "unknown")
        by_repo[repo] = by_repo.get(repo, 0) + 1
        by_teacher[teacher] = by_teacher.get(teacher, 0) + 1
        pristine_lens.append(meta.get("pristine_lines", 0))
        sloppy_lens.append(meta.get("sloppy_lines", 0))

    print(f"File:    {path}")
    print(f"Samples: {len(records)}")
    print(f"\nBy source repo:")
    for k, v in sorted(by_repo.items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v}")
    print(f"\nBy teacher model:")
    for k, v in sorted(by_teacher.items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v}")
    if pristine_lens:
        print(f"\nAvg pristine lines: {sum(pristine_lens)/len(pristine_lens):.0f}")
        print(f"Avg sloppy lines:   {sum(sloppy_lens)/len(sloppy_lens):.0f}")
        bloat = sum(s/p for p, s in zip(pristine_lens, sloppy_lens) if p > 0) / len(pristine_lens)
        print(f"Avg bloat factor:   {bloat:.1f}x")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Anti-slop training dataset builder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="List eligible source files")
    p_scan.add_argument("--source", default="all",
                        help="Comma-separated: barista,yaze,zelda3,afs_distill")

    p_gen = sub.add_parser("generate", help="Generate sloppy/clean pairs")
    p_gen.add_argument("--source", default="barista",
                       help="Comma-separated source keys")
    p_gen.add_argument("--teacher", choices=["gemini", "claude"], default="gemini")
    p_gen.add_argument("--max-files", type=int, default=20)
    p_gen.add_argument("--output", "-o", metavar="FILE")

    p_stats = sub.add_parser("stats", help="Dataset statistics")
    p_stats.add_argument("--input", "-i", metavar="FILE")

    args = parser.parse_args()
    {"scan": cmd_scan, "generate": cmd_generate, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    main()
