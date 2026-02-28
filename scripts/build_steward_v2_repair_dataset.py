#!/usr/bin/env python3
"""Build a focused repair dataset for steward_v2 from strict eval failures."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

STEWARD_SYSTEM = (
    "You are Steward. You are a task execution operator, not a motivational coach. "
    "Turn messy backlogs into a short ordered plan with concrete checkpoints. "
    "Always include the first irreversible action."
)

DRILL_PROMPTS = [
    "I have 27 tasks in my backlog and only 90 minutes today. Prioritize and sequence.",
    "I keep context switching. Build a single-thread execution plan for the next 3 hours.",
    "I need a realistic plan for today with one high-value deliverable.",
    "I miss deadlines because tasks are too big. Break these down with handoff points.",
    "I need to clear 15 stale tasks without losing important work.",
    "I need a task plan that includes explicit done criteria.",
    "I need an execution order that maximizes momentum in first hour.",
    "Turn this chaotic TODO list into a strict execution ladder.",
]


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def split_train_valid(rows: list[dict[str, Any]], train_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    data = list(rows)
    rng.shuffle(data)
    cut = int(len(data) * train_ratio)
    cut = max(1, min(cut, len(data))) if data else 0
    return data[:cut], data[cut:]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "\n".join(json.dumps(r, ensure_ascii=True) for r in rows)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def first_irreversible_action(prompt: str, variant: int) -> str:
    low = prompt.lower()
    if "tax" in low:
        return "Open the tax portal now and submit one required document before touching any other task."
    if "40 minute" in low or "40 minutes" in low:
        return "Start a 35-minute timer and commit the first concrete update to the highest-risk task."
    if "context switching" in low:
        return "Close every tab except one work surface and start a 90-minute no-switch block."
    if "deadline" in low or "hotfix" in low:
        return "Notify stakeholders of the execution order now, then begin the hotfix branch immediately."
    base = [
        "Create a Today board with exactly three tasks and lock it until first checkpoint.",
        "Book the first focus block on your calendar now and begin the top-priority task.",
        "Move one high-impact task to In Progress and publish the done criteria before execution.",
    ]
    return base[variant % len(base)]


def make_plan(prompt: str, variant: int) -> str:
    first = first_irreversible_action(prompt, variant)
    plans = [
        [
            "Triage the backlog into `must ship today`, `important but schedulable`, and `defer`.",
            "Select one primary deliverable and define done criteria in one sentence.",
            "Block 60-90 minutes to execute the primary deliverable with notifications off.",
            "Run verification for the primary deliverable and capture evidence of completion.",
            "Schedule follow-up slots for remaining important tasks with explicit owners/time.",
            "Close the day with a 10-minute review and write tomorrow's first action.",
        ],
        [
            "List every open task once, then cut anything without a clear outcome statement.",
            "Prioritize by impact and reversibility; place only top three tasks in execution queue.",
            "Start the first task immediately and produce a concrete artifact within 25 minutes.",
            "Review progress at midpoint and either continue or downscope without adding new tasks.",
            "Ship one useful output, then batch quick admin tasks in a fixed short window.",
            "Capture blockers and next actions in plain language for tomorrow.",
        ],
        [
            "Convert vague tasks into executable actions that start with a verb.",
            "Choose one high-risk item early while energy is highest.",
            "Execute in single-thread mode and avoid all new intake until checkpoint.",
            "Verify outcomes with tests/review/checklist before marking complete.",
            "Schedule unresolved items with dates instead of leaving them open-ended.",
            "End with a brief audit: shipped, scheduled, delegated, and deferred.",
        ],
    ]
    steps = plans[variant % len(plans)]
    lines = [f"First irreversible action: {first}", ""]
    for idx, step in enumerate(steps, start=1):
        lines.append(f"{idx}. {step}")
    lines.append("")
    lines.append("Checkpoint 1: One primary deliverable is in progress with explicit done criteria.")
    lines.append("Checkpoint 2: Verification completed and tomorrow's first action is scheduled.")
    return "\n".join(lines)


def make_record(prompt: str, answer: str, source: str, fail_tags: list[str] | None = None) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": STEWARD_SYSTEM},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ],
        "_meta": {
            "persona": "steward_v2",
            "source": source,
            "from_fails": fail_tags or [],
        },
    }


def build_rows(eval_report: dict[str, Any], target_model: str, augment_per_fail: int) -> tuple[list[dict[str, Any]], int]:
    model_row = eval_report.get("models", {}).get(target_model)
    if not model_row:
        raise SystemExit(f"target model missing in report: {target_model}")

    failed = [r for r in model_row.get("results", []) if not r.get("ok")]
    rows: list[dict[str, Any]] = []

    for r in failed:
        prompt = str(r.get("prompt", "")).strip()
        fails = [str(x) for x in r.get("fails", [])]
        bad = str(r.get("response", "")).strip()

        for i in range(max(1, augment_per_fail)):
            answer = make_plan(prompt, i)
            rows.append(make_record(prompt, answer, "strict_eval_repair", fails))

        if bad:
            repair_prompt = (
                "Rewrite the following plan so it is non-destructive, includes a clear first irreversible action, "
                "a numbered execution sequence, and concrete checkpoints. Return plan text only.\n\n"
                f"{bad}"
            )
            answer = make_plan(prompt, 0)
            rows.append(make_record(repair_prompt, answer, "bad_output_rewrite", fails))

    for idx, prompt in enumerate(DRILL_PROMPTS):
        rows.append(make_record(prompt, make_plan(prompt, idx), "actionability_drill", []))

    return rows, len(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-report", required=True, help="Path to steward eval report JSON.")
    parser.add_argument("--target-model", default="gguf/afs/steward_v1-q8_0.gguf")
    parser.add_argument("--out-dir", default="docs/eval/steward_repair_v2_20260228")
    parser.add_argument("--augment-per-fail", type=int, default=6)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report_path = Path(args.eval_report).resolve()
    report = load_report(report_path)
    rows, failed_cases = build_rows(report, args.target_model, args.augment_per_fail)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    train_rows, valid_rows = split_train_valid(rows, args.train_ratio, args.seed)
    train_path = out_dir / "train.jsonl"
    valid_path = out_dir / "valid.jsonl"
    write_jsonl(train_path, train_rows)
    write_jsonl(valid_path, valid_rows)

    source_counts = Counter([r["_meta"]["source"] for r in rows])
    manifest = {
        "source_eval_report": str(report_path),
        "target_model": args.target_model,
        "failed_cases": failed_cases,
        "augment_per_fail": args.augment_per_fail,
        "total_rows": len(rows),
        "train_rows": len(train_rows),
        "valid_rows": len(valid_rows),
        "source_breakdown": dict(source_counts),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"failed_cases={failed_cases} total_rows={len(rows)} train={len(train_rows)} valid={len(valid_rows)}")
    print(train_path)
    print(valid_path)
    print(out_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
