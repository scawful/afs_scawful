#!/usr/bin/env python3
"""Build coding distillation prompts from local chat-log datasets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEFAULT_SOURCES = [
    Path("data/training_data/claude_log_pairs.jsonl"),
    Path("data/training_data/cpp_log_pairs.jsonl"),
    Path("data/training_data/commit_diff_v1.jsonl"),
]

DEFAULT_OUTPUT = Path("docs/eval/distill_prompts_logs_v1.jsonl")
HARD_MAX_PROMPT_CHARS = 420

INPUT_HINT = "Output practical code or stepwise technical guidance."

CATEGORY_KEYWORDS = {
    "tooling": ["tool", "workflow", "pipeline", "orchestrate", "automation", "agent"],
    "debugging": ["debug", "error", "bug", "failing", "regression", "trace"],
    "refactor": ["refactor", "cleanup", "rewrite", "simplify", "reduce"],
    "build": ["build", "compile", "ci", "release", "deploy", "test"],
    "codegen": ["implement", "write", "create", "generate", "function", "script"],
}

EXPECTED_KEYWORDS = {
    "tooling": ["plan", "steps", "validation"],
    "debugging": ["root cause", "repro", "fix"],
    "refactor": ["before", "after", "tradeoff"],
    "build": ["command", "verify", "result"],
    "codegen": ["code", "edge case", "test"],
}

CODE_HINTS = [
    ".py",
    ".ts",
    ".js",
    ".cpp",
    ".c",
    ".rs",
    "bash",
    "build",
    "test",
    "compile",
    "function",
    "script",
    "api",
    "json",
]

NON_CODING_HINTS = [
    "girlfriend",
    "boyfriend",
    "dating",
    "relationship",
    "therapy",
    "journal",
    "family",
    "my job at",
]

REJECT_HINTS = [
    "tool use was rejected",
    "stop what you are doing and wait for the user",
    "agentid:",
    "<usage>",
    "[task]",
    "request interrupted",
    "<local-command-caveat>",
    "do not respond to these messages",
]


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_prompt(row: dict) -> str:
    instruction = row.get("instruction")
    if isinstance(instruction, str) and instruction.strip():
        return instruction.strip()

    messages = row.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    return ""


def _is_coding_prompt(prompt: str, row: dict) -> bool:
    low = prompt.lower()
    has_code_hint = any(hint in low for hint in CODE_HINTS)
    has_domain_kw = any(kw in low for kws in CATEGORY_KEYWORDS.values() for kw in kws)
    has_non_coding_hint = any(hint in low for hint in NON_CODING_HINTS)

    if has_non_coding_hint:
        return False

    if has_code_hint:
        return True

    meta = row.get("_meta", {})
    tags = meta.get("tags", [])
    if isinstance(tags, list):
        tags_low = [str(tag).lower() for tag in tags]
        if ("coding" in tags_low or "tool_use" in tags_low or "cpp" in tags_low) and has_domain_kw:
            return True
    return False


def _category_for(prompt: str) -> str:
    low = prompt.lower()
    best = "codegen"
    best_hits = -1
    for category, kws in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in low)
        if hits > best_hits:
            best = category
            best_hits = hits
    return best


def _trim_prompt(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _collect_from_source(path: Path, per_source_max: int, max_chars: int) -> list[dict]:
    rows = _load_jsonl(path)
    out: list[dict] = []
    seen: set[str] = set()

    for row in rows:
        prompt = _extract_prompt(row)
        if not prompt:
            continue
        prompt = _normalize(prompt)
        if len(prompt) < 24:
            continue
        if any(hint in prompt.lower() for hint in REJECT_HINTS):
            continue
        if len(prompt) > HARD_MAX_PROMPT_CHARS:
            continue
        if not _is_coding_prompt(prompt, row):
            continue

        trimmed = _trim_prompt(prompt, max_chars=max_chars)
        key = trimmed.lower()
        if key in seen:
            continue
        seen.add(key)

        category = _category_for(trimmed)
        out.append(
            {
                "instruction": trimmed,
                "input": INPUT_HINT,
                "category": category,
                "expected_keywords": EXPECTED_KEYWORDS[category],
                "_meta": {
                    "source_file": str(path),
                    "quality_score": (row.get("_meta", {}) or {}).get("quality_score"),
                },
            }
        )
        if len(out) >= per_source_max:
            break

    return out


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        key = _normalize(str(row.get("instruction", "")).lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build coding distillation prompt pack from log datasets")
    parser.add_argument("--sources", nargs="+", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-source-max", type=int, default=100)
    parser.add_argument("--target-count", type=int, default=220)
    parser.add_argument("--max-chars", type=int, default=1100)
    args = parser.parse_args()

    merged: list[dict] = []
    for source in args.sources:
        source_path = source.expanduser().resolve()
        rows = _collect_from_source(
            path=source_path,
            per_source_max=args.per_source_max,
            max_chars=args.max_chars,
        )
        merged.extend(rows)
        print(f"{source_path}: collected {len(rows)} prompts")

    merged = _dedupe_rows(merged)
    if len(merged) > args.target_count:
        merged = merged[: args.target_count]

    output_path = args.output.expanduser().resolve()
    _write_jsonl(output_path, merged)

    print(f"wrote {len(merged)} prompts -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
