#!/usr/bin/env python3
"""Strict actionability eval for Steward task-management models."""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path

ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODELS = ["gguf/afs/steward_v1-q8_0.gguf"]

SYSTEM = (
    "You are Steward. Turn messy backlogs into a short ordered execution plan. "
    "Output format: one line for 'First irreversible action', then a numbered list "
    "with concrete checkpoints. Be direct and non-destructive."
)

PROMPTS = [
    "I have 12 unfinished tasks: taxes, 3 PR reviews, dentist appointment, inbox cleanup, blog draft, grocery run, refactor auth tests, update docs, call mom, workout, and backup laptop. Give me an ordered plan for tomorrow.",
    "I keep context switching and ending with nothing done. Build a 3-hour single-thread plan with checkpoints.",
    "I have 90 minutes and low energy. Pick a realistic sequence from a backlog of 20 mixed admin and coding tasks.",
    "Two deadlines collide: API hotfix and monthly report. Sequence what I should do first and why.",
    "My backlog has vague items like 'improve pipeline' and 'clean docs'. Convert them into executable steps.",
    "I need a plan that survives one dependency failure and still ships one useful output today.",
    "I reopen the same five tasks every day. Give me a closeout sequence with done criteria.",
    "I need a one-day plan to reduce a 40-item backlog without losing important work.",
    "I have only 40 minutes before a meeting. Give me a compact sequence with one irreversible action.",
    "I keep overplanning. Give me a ship-first plan with minimal overhead for today.",
]

DESTRUCTIVE_PATTERNS = [
    r"\bdelete all\b",
    r"\bdelete (the )?pending tasks\b",
    r"\barchive all\b",
    r"\bwipe (the )?backlog\b",
    r"\bdiscard (all|everything)\b",
    r"\bclear (all|everything)\b",
    r"\bremove every task\b",
]

ACTION_VERBS = {
    "schedule",
    "ship",
    "review",
    "triage",
    "draft",
    "commit",
    "run",
    "fix",
    "verify",
    "call",
    "book",
    "pay",
    "block",
    "merge",
    "write",
}


def call_model(model: str, prompt: str, temperature: float, max_tokens: int) -> tuple[str | None, str | None]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            "60",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(payload),
            ENDPOINT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None, f"curl_error:{proc.stderr.strip()}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, "api_non_json"
    if "error" in data:
        return None, f"api_error:{data['error']}"
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return str(content), None


def strip_wrappers(text: str) -> str:
    out = text.strip()
    out = re.sub(r"^```(?:text|markdown)?\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*```$", "", out)
    return out.strip()


def evaluate(text: str) -> tuple[bool, list[str], dict[str, int]]:
    fails: list[str] = []
    cleaned = strip_wrappers(text)
    lower = cleaned.lower()
    lines = [ln.rstrip() for ln in cleaned.splitlines() if ln.strip()]

    if not cleaned:
        fails.append("empty")

    if len(cleaned) < 120:
        fails.append("too_short")
    if len(cleaned) > 2200:
        fails.append("too_long")

    has_irreversible = "first irreversible action" in lower or "irreversible action" in lower
    if not has_irreversible:
        fails.append("missing_irreversible_action")

    numbered_lines = [ln for ln in lines if re.match(r"^\s*\d+\.\s+\S+", ln)]
    if len(numbered_lines) < 4:
        fails.append("missing_numbered_sequence")

    has_checkpoint = any("checkpoint" in ln.lower() or "done criteria" in ln.lower() for ln in lines)
    if not has_checkpoint:
        fails.append("missing_checkpoint")

    if re.search(r"\[[^\]]+\]\([^)]+\)", cleaned) or "http://" in lower or "https://" in lower:
        fails.append("external_links_or_markdown_links")

    if "[insert" in lower or "tbd" in lower:
        fails.append("placeholder_content")

    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, lower):
            fails.append("destructive_instruction")
            break

    irreversible_line = ""
    for ln in lines:
        if "irreversible action" in ln.lower():
            irreversible_line = ln.lower()
            break
    if irreversible_line:
        for pattern in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, irreversible_line):
                fails.append("irreversible_action_destructive")
                break

    verb_hits = {v for v in ACTION_VERBS if re.search(rf"\b{re.escape(v)}\b", lower)}
    if len(verb_hits) < 3:
        fails.append("insufficient_action_verbs")

    metrics = {
        "chars": len(cleaned),
        "lines": len(lines),
        "numbered_steps": len(numbered_lines),
        "action_verbs": len(verb_hits),
    }
    return len(fails) == 0, fails, metrics


def run_model(model: str, temperature: float, max_tokens: int) -> dict:
    results = []
    passed = 0
    for idx, prompt in enumerate(PROMPTS, start=1):
        print(f"[{model}] case {idx}/{len(PROMPTS)}", flush=True)
        response, err = call_model(model, prompt, temperature, max_tokens)
        if err:
            ok = False
            fails = [err]
            metrics = {}
            output = ""
        else:
            output = strip_wrappers(response or "")
            ok, fails, metrics = evaluate(output)
        if ok:
            passed += 1
        results.append(
            {
                "prompt": prompt,
                "ok": ok,
                "fails": fails,
                "metrics": metrics,
                "response": output,
            }
        )
    return {
        "model": model,
        "cases": len(PROMPTS),
        "passed": passed,
        "pass_rate": round(passed / len(PROMPTS), 4),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict Steward actionability eval")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--temperature", type=float, default=0.35)
    parser.add_argument("--max-tokens", type=int, default=460)
    parser.add_argument("--out", default="docs/eval/steward_eval_20260228.json")
    args = parser.parse_args()

    models_report = {}
    for model in args.models:
        models_report[model] = run_model(model, args.temperature, args.max_tokens)

    report = {
        "meta": {
            "date_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            "endpoint": ENDPOINT,
            "cases_total": len(PROMPTS),
            "eval_type": "steward_actionability_strict_v1",
        },
        "models": models_report,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for model, row in models_report.items():
        print(f"{model} pass={row['passed']}/{row['cases']} ({row['pass_rate']})")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
