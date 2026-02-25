#!/usr/bin/env python3
"""
logprune - Extract high-quality training pairs from Claude Code conversation logs.

Usage:
  logprune stats                          # Summarize all sessions
  logprune extract [--min-score FLOAT]    # Extract training pairs (default: 0.5)
  logprune extract --format chatml        # ChatML format (messages array)
  logprune extract --filter coding        # Only agentic/coding sessions
  logprune extract --output out.jsonl     # Write to file (default: stdout)
  logprune inspect SESSION_ID             # Show full session transcript
  logprune prune --output dir/            # Copy logs with private content removed
"""

import argparse
import json
import sys
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Generator, Optional
from datetime import datetime

CLAUDE_LOGS = Path.home() / ".claude" / "projects"

# --- Scoring signals ---

CODING_SIGNALS = [
    # Language keywords
    "def ", "class ", "import ", "return ", "void ", "struct ", "enum ",
    "func ", "async ", "await ", "trait ", "interface ", "typedef ",
    # File indicators
    ".py", ".c", ".cpp", ".cc", ".swift", ".ts", ".js", ".rs", ".go",
    ".h", ".hpp", ".lua", ".sh", ".yaml", ".toml",
    # Agentic tool names (strong signals)
    "read_file", "write_file", "bash", "edit_file", "glob", "grep",
    "xcodebuild", "cargo ", "cmake ", "make ", "git ",
    # Concepts
    "error:", "bug ", "refactor", "implement", "debug", "test", "compile",
    "function", "```",
]

# Signals that must appear as unambiguous personal-context phrases.
# Keep these specific — avoid short words that appear in technical contexts
# (e.g. "resume" fires on "resume agent/training/session").
PRIVATE_SIGNALS = [
    "my resume", "my cv", "cover letter", "job application",
    "my girlfriend", "my boyfriend", "my wife", "my husband",
    "my partner", "we are dating", "our relationship",
    "bank account", "credit card", "social security",
    "my password", "my medical", "medical record", "medical history",
    "my doctor", "seeing a therapist", "in therapy",
]

TOOL_NAMES = {
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "Task", "WebFetch", "WebSearch",
    "mcp__", "computer_", "browser_",
}


# --- Data structures ---

@dataclass
class Turn:
    role: str           # "user" | "assistant"
    content: str
    uuid: str
    parent_uuid: Optional[str]
    timestamp: str
    model: Optional[str] = None
    tool_calls: list[str] = field(default_factory=list)
    has_tool_result: bool = False
    token_count: int = 0


@dataclass
class Session:
    session_id: str
    project_path: str
    source_file: str
    turns: list[Turn] = field(default_factory=list)
    quality_score: float = 0.0
    tags: list[str] = field(default_factory=list)
    is_coding: bool = False
    is_private: bool = False


# --- JSONL / content parsing ---

def iter_jsonl(path: Path) -> Generator[dict, None, None]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return


def extract_content(raw) -> tuple[str, list[str], bool]:
    """Parse message content into (text, tool_call_names, has_tool_result)."""
    if isinstance(raw, str):
        return raw, [], False
    if not isinstance(raw, list):
        return str(raw), [], False

    parts, tools, has_result = [], [], False
    for block in raw:
        if not isinstance(block, dict):
            continue
        t = block.get("type", "")
        if t == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
        elif t == "thinking":
            pass  # Omit internal reasoning from training data
        elif t == "tool_use":
            name = block.get("name", "unknown")
            tools.append(name)
            inp = block.get("input", {})
            # Summarise tool call compactly
            if name in ("Read", "Write", "Edit"):
                fp = inp.get("file_path", inp.get("path", ""))
                parts.append(f"[{name}: {fp}]")
            elif name == "Bash":
                cmd = inp.get("command", "")[:120]
                parts.append(f"[Bash: {cmd}]")
            else:
                parts.append(f"[{name}]")
        elif t == "tool_result":
            has_result = True
            inner = block.get("content", "")
            if isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and item.get("type") == "text":
                        snippet = item.get("text", "")[:400]
                        parts.append(f"→ {snippet}")
            elif isinstance(inner, str):
                parts.append(f"→ {inner[:400]}")

    return "\n".join(parts), tools, has_result


def extract_model(msg: dict) -> Optional[str]:
    return msg.get("model") or msg.get("message", {}).get("model")


def extract_tokens(msg: dict) -> int:
    usage = msg.get("message", {}).get("usage", {})
    return (usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0)


# --- Session reconstruction ---

def load_sessions_from_file(path: Path) -> list[Session]:
    """Read one JSONL file and reconstruct sessions by session_id."""
    by_session: dict[str, list[dict]] = {}
    for rec in iter_jsonl(path):
        sid = rec.get("sessionId")
        t = rec.get("type", "")
        if not sid or t not in ("user", "assistant"):
            continue
        by_session.setdefault(sid, []).append(rec)

    sessions = []
    project_path = str(path.parent.name)

    for sid, records in by_session.items():
        records.sort(key=lambda r: r.get("timestamp", ""))
        turns = []
        for rec in records:
            msg = rec.get("message", {})
            raw_content = msg.get("content", "")
            text, tools, has_result = extract_content(raw_content)
            if not text.strip():
                continue
            turn = Turn(
                role=msg.get("role", rec.get("type", "user")),
                content=text,
                uuid=rec.get("uuid", ""),
                parent_uuid=rec.get("parentUuid"),
                timestamp=rec.get("timestamp", ""),
                model=extract_model(rec),
                tool_calls=tools,
                has_tool_result=has_result,
                token_count=extract_tokens(rec),
            )
            turns.append(turn)

        if len(turns) >= 2:
            s = Session(
                session_id=sid,
                project_path=project_path,
                source_file=str(path),
                turns=turns,
            )
            sessions.append(s)

    return sessions


def load_all_sessions(logs_dir: Path = CLAUDE_LOGS) -> list[Session]:
    sessions = []
    for jsonl_path in logs_dir.glob("**/*.jsonl"):
        if "subagents" in str(jsonl_path):
            continue  # Subagent logs are shorter; include main session logs only
        sessions.extend(load_sessions_from_file(jsonl_path))
    return sessions


# --- Quality scoring ---

def score_session(s: Session) -> None:
    combined = " ".join(t.content.lower() for t in s.turns)

    # Detect private content
    if any(sig in combined for sig in PRIVATE_SIGNALS):
        s.is_private = True
        s.quality_score = 0.0
        return

    score = 0.0

    # Tool use signals (strongest indicator of agentic work)
    all_tools = [tc for t in s.turns for tc in t.tool_calls]
    tool_turns = sum(1 for t in s.turns if t.tool_calls)
    score += min(tool_turns * 0.08, 0.25)

    # Named tool types boost
    named_tools = {tc for tc in all_tools if any(tn in tc for tn in TOOL_NAMES)}
    score += min(len(named_tools) * 0.03, 0.15)

    # Coding content
    coding_hits = sum(1 for sig in CODING_SIGNALS if sig in combined)
    score += min(coding_hits * 0.015, 0.20)
    s.is_coding = coding_hits > 3 or tool_turns > 0

    # Multi-turn depth
    score += min(len(s.turns) * 0.015, 0.15)

    # Substantive assistant responses
    asst = [t for t in s.turns if t.role == "assistant"]
    if asst:
        avg_len = sum(len(t.content) for t in asst) / len(asst)
        if avg_len > 800:
            score += 0.08
        if avg_len > 2500:
            score += 0.07

    # Tags
    if tool_turns > 0:
        s.tags.append("tool_use")
    if s.is_coding:
        s.tags.append("coding")
    if any("xcodebuild" in t.content or "swift" in t.content.lower() for t in s.turns):
        s.tags.append("ios_macos")
    if any("asm" in t.content.lower() or "65816" in t.content for t in s.turns):
        s.tags.append("assembly")
    if ("yaze" in s.project_path or "zelda" in s.project_path.lower()
            or any(".cc" in t.content or ".cpp" in t.content
                   or "std::" in t.content or "template<" in t.content
                   for t in s.turns)):
        s.tags.append("cpp")

    s.quality_score = min(score, 1.0)


# --- Output formatters ---

def to_chatml(s: Session, system: str = "") -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    for t in s.turns:
        messages.append({"role": t.role, "content": t.content})
    return {
        "messages": messages,
        "_meta": {
            "source": "claude_logs",
            "session_id": s.session_id,
            "project": s.project_path,
            "quality_score": round(s.quality_score, 3),
            "tags": s.tags,
            "turns": len(s.turns),
        }
    }


def to_instruction_pairs(s: Session) -> list[dict]:
    """Extract consecutive user→assistant pairs as instruction/output samples."""
    pairs = []
    turns = s.turns
    for i in range(len(turns) - 1):
        if turns[i].role == "user" and turns[i+1].role == "assistant":
            pairs.append({
                "instruction": turns[i].content,
                "output": turns[i+1].content,
                "_meta": {
                    "source": "claude_logs",
                    "session_id": s.session_id,
                    "project": s.project_path,
                    "quality_score": round(s.quality_score, 3),
                    "turn_count": len(s.turns),
                    "tags": s.tags,
                    "model": turns[i+1].model,
                }
            })
    return pairs


# --- Subcommands ---

def cmd_stats(args):
    sessions = load_all_sessions()
    for s in sessions:
        score_session(s)

    coding = [s for s in sessions if s.is_coding]
    private = [s for s in sessions if s.is_private]
    high_q = [s for s in sessions if s.quality_score >= 0.6]
    tool_use = [s for s in sessions if "tool_use" in s.tags]

    print(f"Total sessions:     {len(sessions)}")
    print(f"Coding sessions:    {len(coding)}")
    print(f"With tool use:      {len(tool_use)}")
    print(f"High quality (≥0.6):{len(high_q)}")
    print(f"Private (filtered): {len(private)}")

    tag_counts: dict[str, int] = {}
    for s in sessions:
        for tag in s.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    print("\nTag distribution:")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag:25s} {count}")

    total_turns = sum(len(s.turns) for s in sessions)
    print(f"\nTotal turns:        {total_turns}")
    if sessions:
        avg_score = sum(s.quality_score for s in sessions) / len(sessions)
        print(f"Avg quality score:  {avg_score:.3f}")


def cmd_extract(args):
    min_score = args.min_score
    fmt = args.format
    filter_tag = args.filter
    filter_project = args.project
    out_path = Path(args.output) if args.output else None

    sessions = load_all_sessions()
    for s in sessions:
        score_session(s)

    candidates = [
        s for s in sessions
        if s.quality_score >= min_score and not s.is_private
    ]
    if filter_tag:
        candidates = [s for s in candidates if filter_tag in s.tags]
    if filter_project:
        candidates = [s for s in candidates if filter_project in s.project_path]

    # Sort best first
    candidates.sort(key=lambda s: -s.quality_score)

    records = []
    if fmt == "chatml":
        records = [to_chatml(s) for s in candidates]
    else:
        for s in candidates:
            records.extend(to_instruction_pairs(s))

    out = open(out_path, "w") if out_path else sys.stdout
    try:
        for rec in records:
            out.write(json.dumps(rec) + "\n")
    finally:
        if out_path:
            out.close()

    total = len(records)
    msg = f"# Extracted {total} records from {len(candidates)} sessions"
    if out_path:
        print(msg, file=sys.stderr)
    else:
        print(msg, file=sys.stderr)


def cmd_inspect(args):
    sid = args.session_id
    sessions = load_all_sessions()
    for s in sessions:
        if sid in s.session_id:
            score_session(s)
            print(f"Session: {s.session_id}")
            print(f"Project: {s.project_path}")
            print(f"Score:   {s.quality_score:.3f}")
            print(f"Tags:    {', '.join(s.tags)}")
            print(f"Turns:   {len(s.turns)}")
            print("─" * 60)
            for i, t in enumerate(s.turns):
                prefix = "USER" if t.role == "user" else "ASST"
                tools = f" [{', '.join(t.tool_calls)}]" if t.tool_calls else ""
                print(f"\n[{i+1}] {prefix}{tools} ({t.timestamp[:19]})")
                print(t.content[:600])
                if len(t.content) > 600:
                    print(f"  ... ({len(t.content)} chars total)")
            return
    print(f"Session {sid!r} not found.", file=sys.stderr)
    sys.exit(1)


def cmd_prune(args):
    """Copy logs to output dir with private sessions removed."""
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    kept = 0
    for jsonl_path in CLAUDE_LOGS.glob("**/*.jsonl"):
        if "subagents" in str(jsonl_path):
            continue
        rel = jsonl_path.relative_to(CLAUDE_LOGS)
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        kept_lines, removed_lines = [], 0
        for rec in iter_jsonl(jsonl_path):
            msg = rec.get("message", {})
            raw = msg.get("content", "")
            text, _, _ = extract_content(raw)
            if any(sig in text.lower() for sig in PRIVATE_SIGNALS):
                removed_lines += 1
            else:
                kept_lines.append(json.dumps(rec))
        removed += removed_lines
        kept += len(kept_lines)
        with open(dest, "w") as f:
            f.write("\n".join(kept_lines) + "\n")
    print(f"Kept {kept} records, removed {removed} private records → {out_dir}")


# --- CLI entrypoint ---

def main():
    parser = argparse.ArgumentParser(description="Claude log pruner and training extractor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # stats
    sub.add_parser("stats", help="Show session statistics")

    # extract
    p_ext = sub.add_parser("extract", help="Extract training pairs")
    p_ext.add_argument("--min-score", type=float, default=0.5, metavar="FLOAT")
    p_ext.add_argument("--format", choices=["chatml", "pairs"], default="pairs")
    p_ext.add_argument("--filter", metavar="TAG", help="Only sessions with this tag")
    p_ext.add_argument("--project", metavar="SUBSTR", help="Only sessions whose project path contains SUBSTR")
    p_ext.add_argument("--output", "-o", metavar="FILE")

    # inspect
    p_ins = sub.add_parser("inspect", help="Show a single session")
    p_ins.add_argument("session_id")

    # prune
    p_prn = sub.add_parser("prune", help="Copy logs with private content removed")
    p_prn.add_argument("--output", "-o", required=True, metavar="DIR")

    args = parser.parse_args()
    {"stats": cmd_stats, "extract": cmd_extract,
     "inspect": cmd_inspect, "prune": cmd_prune}[args.cmd](args)


if __name__ == "__main__":
    main()
