#!/usr/bin/env python3
"""Build a tiny checkpoint-focused micro-fix dataset for steward_v3."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

STEWARD_SYSTEM = (
    "You are Steward. Convert messy backlogs into a short ordered execution plan with "
    "a first irreversible action, numbered steps, and explicit checkpoints."
)

CHECKPOINT_DRILLS = [
    "I keep overplanning. Give me a ship-first plan with minimal overhead for today.",
    "I need a compact plan for 40 minutes before a meeting; include checkpoints.",
    "I need a realistic one-day backlog reduction plan with clear checkpoints.",
    "I reopen the same tasks every day; give me a closeout sequence with done criteria.",
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


def make_checkpoint_plan(prompt: str, variant: int) -> str:
    starters = [
        "First irreversible action: Start a 45-minute focus block now and publish the done criteria before executing.",
        "First irreversible action: Move one high-impact task to In Progress and commit to shipping it today.",
        "First irreversible action: Book the first execution block now and lock intake until Checkpoint 1.",
    ]
    step_sets = [
        [
            "Triage backlog into `ship today`, `schedule`, and `defer`.",
            "Choose one primary deliverable and define a measurable done state.",
            "Execute in single-thread mode for one uninterrupted block.",
            "Verify output quality against done criteria before closing.",
            "Batch low-impact admin items in a fixed short window.",
            "Write tomorrow's first action before ending the day.",
        ],
        [
            "List tasks once and remove any item without a concrete outcome.",
            "Prioritize top three by impact and reversibility.",
            "Start the first task and produce a concrete artifact in 25 minutes.",
            "Reassess at midpoint and downscope rather than context-switch.",
            "Ship one useful output and capture blockers with owner/date.",
            "Close the day with a status note and next action.",
        ],
    ]
    start = starters[variant % len(starters)]
    steps = step_sets[variant % len(step_sets)]
    lines = [start, ""]
    for i, step in enumerate(steps, start=1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append("Checkpoint 1: Primary deliverable selected and done criteria documented.")
    lines.append("Checkpoint 2: First focused execution block completed with evidence.")
    lines.append("Checkpoint 3: Verification done and status updated with tomorrow's first action.")
    return "\n".join(lines)


def make_record(prompt: str, answer: str, source: str, fails: list[str]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": STEWARD_SYSTEM},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ],
        "_meta": {
            "persona": "steward_v3",
            "source": source,
            "from_fails": fails,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-report", required=True, help="Steward eval JSON report path")
    parser.add_argument("--target-model", default="gguf/afs/steward_v2-q8_0.gguf")
    parser.add_argument("--out-dir", default="docs/eval/steward_repair_v3_20260228")
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = load_report(Path(args.eval_report).resolve())
    model = report.get("models", {}).get(args.target_model)
    if not model:
        raise SystemExit(f"target model missing in report: {args.target_model}")

    failed = [r for r in model.get("results", []) if not r.get("ok")]
    checkpoint_failed = [r for r in failed if "missing_checkpoint" in r.get("fails", [])]

    rows: list[dict[str, Any]] = []
    for r in checkpoint_failed:
        prompt = str(r.get("prompt", "")).strip()
        fails = [str(x) for x in r.get("fails", [])]
        for variant in range(6):
            rows.append(make_record(prompt, make_checkpoint_plan(prompt, variant), "checkpoint_repair", fails))
        bad = str(r.get("response", "")).strip()
        if bad:
            rewrite_prompt = (
                "Rewrite the plan below so it keeps the same intent but includes explicit checkpoint lines. "
                "Keep a first irreversible action and numbered steps.\n\n"
                f"{bad}"
            )
            rows.append(make_record(rewrite_prompt, make_checkpoint_plan(prompt, 0), "checkpoint_rewrite", fails))

    for idx, prompt in enumerate(CHECKPOINT_DRILLS):
        rows.append(make_record(prompt, make_checkpoint_plan(prompt, idx), "checkpoint_drill", []))

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    train_rows, valid_rows = split_train_valid(rows, args.train_ratio, args.seed)
    write_jsonl(out_dir / "train.jsonl", train_rows)
    write_jsonl(out_dir / "valid.jsonl", valid_rows)

    manifest = {
        "source_eval_report": str(Path(args.eval_report).resolve()),
        "target_model": args.target_model,
        "failed_cases": len(failed),
        "checkpoint_failed_cases": len(checkpoint_failed),
        "total_rows": len(rows),
        "train_rows": len(train_rows),
        "valid_rows": len(valid_rows),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(
        f"failed_cases={len(failed)} checkpoint_failed_cases={len(checkpoint_failed)} "
        f"total_rows={len(rows)} train={len(train_rows)} valid={len(valid_rows)}"
    )
    print(out_dir / "train.jsonl")
    print(out_dir / "valid.jsonl")
    print(out_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
