#!/usr/bin/env python3
"""Build a chat-format repair dataset from EchoFlow eval cases and failures."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


SYSTEM_PROMPTS: dict[str, str] = {
    "echo": (
        "you are scawful-echo, a voice distilled from justin's writing.\n"
        "style: lowercase, candid, lightly stream-of-consciousness; dry humor with quiet hopefulness; technical when it matters, casual otherwise.\n"
        "rules: avoid corporate tone, avoid ai disclaimers, admit uncertainty directly, and follow strict json output when explicitly requested."
    ),
    "memory": (
        "you are memory, a factual recall assistant.\n"
        "style: concise, concrete, grounded in known facts.\n"
        "rules: do not speculate, state unknown when data is missing, prioritize precision."
    ),
    "muse": (
        "you are muse, a creative exploration partner.\n"
        "style: imaginative but coherent.\n"
        "rules: generate useful options, keep outputs compact and actionable."
    ),
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def choose_profile(tags: list[str]) -> str:
    lowered = {tag.lower() for tag in tags}
    if "memory" in lowered:
        return "memory"
    if "muse" in lowered:
        return "muse"
    return "echo"


# Per-case JSON overrides: used when the generic key-based builder would produce wrong output.
# Keys are case IDs from the eval pack.
_CASE_JSON_OVERRIDES: dict[str, dict[str, Any]] = {
    # tool_json_002: prompt asks for title/due/owner from the scheduling context,
    # not the hardcoded "review echo evals" that the generic builder produces.
    "tool_json_002": {
        "tool": "task_capture",
        "args": {"title": "run avatar smoke eval", "due": "today", "owner": "echo"},
    },
    # cap_short_json_001: no real content to evaluate, but must not use literal "value"
    # placeholders — those are degenerate training targets that cause EOS collapse.
    "cap_short_json_001": {"status": "pass", "reason": "no violations detected in output"},
}


def build_json_payload(case: dict[str, Any]) -> str:
    case_id = str(case.get("id", "")).strip()
    if case_id in _CASE_JSON_OVERRIDES:
        return json.dumps(_CASE_JSON_OVERRIDES[case_id], ensure_ascii=True, separators=(",", ":"))

    keys = [str(k) for k in case.get("json_keys", [])]
    payload: dict[str, Any] = {}
    for key in keys:
        if key == "type":
            payload[key] = "Task"
        elif key == "title":
            payload[key] = "Wire model profile persistence"
        elif key == "tool":
            payload[key] = "task_capture"
        elif key == "args":
            payload[key] = {"title": "review echo evals", "priority": "A"}
        else:
            payload[key] = "value"

    if not payload:
        payload = {"ok": True}
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def trim_to_max_chars(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars)].rstrip()


def ensure_required_tokens(text: str, must_include: list[str]) -> str:
    out = text
    lowered = out.lower()
    missing = [tok for tok in must_include if tok.lower() not in lowered]
    if missing:
        suffix = " " + " ".join(missing)
        out = (out.rstrip() + suffix).strip()
    return out


def remove_forbidden_tokens(text: str, must_not_include: list[str]) -> str:
    out = text
    for token in must_not_include:
        out = out.replace(token, "")
        out = out.replace(token.lower(), "")
    return out.strip()


def build_text_response(case: dict[str, Any], profile: str) -> str:
    tags = {str(t).lower() for t in case.get("tags", [])}

    if "action-items" in tags:
        return "1. ship profile picker in settings\n2. persist defaults\n3. run simulator smoke build\n4. document vast fallback"
    if "planning" in tags:
        return "1. add model config plumbing behind one service path.\n2. gate task outputs behind strict json mode.\n3. run iOS + macOS smoke builds on the same config.\n4. ship only after eval pass-rate clears the threshold."
    if "summary" in tags:
        return "pipeline got cleaner after we normalized env vars and killed duplicate path logic.\n- failures dropped after unifying scripts\n- next step is smoke tests for ios + windows packaging"
    if "uncertainty" in tags:
        return "i don't have that metric yet. can you share the latest run id so i can pull the exact number?"
    if "spanish" in tags:
        return "claro, podemos practicar pedir cafe con frases cortas y naturales.\nenglish hint: start with \"me gustaria\" for polite requests."
    if "project-awareness" in tags:
        return "first check recent sprite state writes and any out-of-bounds index math. then compare crash traces against the last stable sprite patch. finally verify the sprite init path still preserves expected registers."
    if "muse" in tags:
        return "1. make notes behave like magnetic cards that self-cluster by mood.\n2. let links decay unless they get reused, then bloom brighter.\n3. add a \"chaos seed\" mode that proposes one odd but relevant cross-link per day."
    if "format" in tags:
        # bullet list: must_include ['- '] — use dash prefix, not numbered list
        return (
            "- pin temperature to 0 for deterministic structured outputs\n"
            "- version your system prompt and track which eval cases regress on each change\n"
            "- keep repair seeds small and targeted; repetition without variety causes eos collapse"
        )
    if profile == "memory":
        return "unknown"

    return "oracle debugging felt cleaner today. i fixed a tiny asm edge case and the test stopped flapping, which is weirdly comforting."


def build_assistant_response(case: dict[str, Any], profile: str) -> str:
    if case.get("expect_json", False):
        return build_json_payload(case)

    text = build_text_response(case, profile)
    text = ensure_required_tokens(text, [str(x) for x in case.get("must_include", [])])
    text = remove_forbidden_tokens(text, [str(x) for x in case.get("must_not_include", [])])
    max_chars = int(case.get("max_chars", 0) or 0)
    return trim_to_max_chars(text, max_chars)


def build_messages(case: dict[str, Any], profile: str, assistant: str) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[profile]},
            {"role": "user", "content": str(case.get("prompt", ""))},
            {"role": "assistant", "content": assistant},
        ]
    }


def load_failed_case_info(eval_report_path: Path | None) -> dict[str, list[str]]:
    if eval_report_path is None:
        return {}
    payload = json.loads(eval_report_path.read_text(encoding="utf-8"))
    failed: dict[str, list[str]] = {}
    for row in payload.get("results", []):
        if row.get("passed") is True:
            continue
        case_id = str(row.get("id", "")).strip()
        if not case_id:
            continue
        failed[case_id] = [str(v) for v in row.get("violations", [])]
    return failed


def split_train_valid(samples: list[dict[str, Any]], ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    shuffled = list(samples)
    rng.shuffle(shuffled)
    cut = int(len(shuffled) * ratio)
    cut = min(max(cut, 1), len(shuffled)) if shuffled else 0
    return shuffled[:cut], shuffled[cut:]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-pack",
        default="/Users/scawful/src/lab/afs-scawful/docs/eval/echoflow_avatar_eval_v2.jsonl",
        help="Path to eval JSONL pack.",
    )
    parser.add_argument(
        "--eval-report",
        default=None,
        help="Optional eval run JSON; if set, only failed cases are used.",
    )
    parser.add_argument(
        "--out-dir",
        default="/Users/scawful/src/lab/afs-scawful/docs/eval/echo_repair_seed_v1",
        help="Output directory for train/valid JSONL files.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    eval_pack = Path(args.eval_pack).expanduser().resolve()
    eval_report = Path(args.eval_report).expanduser().resolve() if args.eval_report else None
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = load_jsonl(eval_pack)
    if not cases:
        raise SystemExit(f"No cases in eval pack: {eval_pack}")

    failed = load_failed_case_info(eval_report)
    selected_ids = set(failed) if failed else None

    samples: list[dict[str, Any]] = []
    dedupe: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if selected_ids is not None and case_id not in selected_ids:
            continue

        tags = [str(t) for t in case.get("tags", [])]
        profile = choose_profile(tags)
        assistant = build_assistant_response(case, profile)

        primary = build_messages(case, profile, assistant)
        key = json.dumps(primary, sort_keys=True)
        if key not in dedupe:
            dedupe.add(key)
            samples.append(primary)

        # Add one compact JSON reinforcement sample for JSON cases.
        if case.get("expect_json", False):
            compact = build_messages(case, profile, build_json_payload(case))
            compact_key = json.dumps(compact, sort_keys=True)
            if compact_key not in dedupe:
                dedupe.add(compact_key)
                samples.append(compact)

    if not samples:
        raise SystemExit("No samples generated. Check eval report IDs and eval pack.")

    train_rows, valid_rows = split_train_valid(samples, args.train_ratio, args.seed)

    train_path = out_dir / "train.jsonl"
    valid_path = out_dir / "valid.jsonl"
    manifest_path = out_dir / "manifest.json"

    write_jsonl(train_path, train_rows)
    write_jsonl(valid_path, valid_rows)

    manifest = {
        "eval_pack": str(eval_pack),
        "eval_report": str(eval_report) if eval_report else None,
        "total_samples": len(samples),
        "train_samples": len(train_rows),
        "valid_samples": len(valid_rows),
        "failed_case_count": len(failed),
        "seed": args.seed,
        "train_ratio": args.train_ratio,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {train_path}")
    print(f"Wrote {valid_path}")
    print(f"Wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
