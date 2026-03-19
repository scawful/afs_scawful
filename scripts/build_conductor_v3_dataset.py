#!/usr/bin/env python3
"""Build Conductor v3 dataset with richer DAG schema and JSON-repair samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

OUTPUT_DEFAULT = Path("data/training_data/conductor_v3.jsonl")

SYSTEM = (
    "You are The Conductor. Decompose goals into Agent-to-Agent handoff plans. "
    "Output valid JSON only. No markdown, no prose."
)

SCENARIOS = [
    "orchestrate a 4-agent workflow to fix a failing CI pipeline and ship a verified patch today.",
    "design a DAG for a zero-downtime sqlite schema migration with rollback checkpoints.",
    "plan a swarm to triage and close 40 production bugs in one week without regressions.",
    "create a handoff sequence to train, convert, and smoke-test a new local persona model.",
    "design an execution DAG for nightly evals, failure clustering, repair data generation, and retraining.",
    "orchestrate a release pipeline with canary, promotion gate, rollback trigger, and owner handoff.",
    "build an agent plan to investigate memory leaks, validate fixes, and publish postmortem notes.",
    "design a workflow to migrate docs to a unified schema and catch stale references automatically.",
    "orchestrate a task backlog reduction sprint with strict priority and reversible/irreversible decision tags.",
    "create a DAG for preparing a long-form essay from rough notes, structure checks, and revision passes.",
    "design a handoff plan to convert chat logs into distilled training prompts with quality filters.",
    "orchestrate multi-repo dependency cleanup with staged validation and change windows.",
    "build a workflow for detecting prompt-injection regressions and patching routing rules.",
    "design a swarm plan for JSON-schema hardening across prompt, model output, and evaluator.",
    "orchestrate migration of model cards to a canonical registry format with strict validation.",
    "create a plan to recover from a broken production deploy with diagnostics, mitigation, and verification.",
    "design an execution DAG for importing essays, cleaning text, and producing training-ready chunks.",
    "orchestrate tool-calling evals across three models with scoring and promotion recommendation.",
    "build a workflow to run weekly reflection extraction and turn it into next-week priorities.",
    "design a handoff sequence for local artifact sync with checksum verification and fallback mirrors.",
]

AGENTS = [
    "analyst",
    "planner",
    "builder",
    "tester",
    "coordinator",
    "scribe",
]

CHECKPOINTS = [
    "scope accepted",
    "implementation draft reviewed",
    "validation passed",
    "handoff completed",
]

RISKS = [
    "hidden dependency on stale docs",
    "schema mismatch between agents",
    "insufficient rollback rehearsal",
    "unowned validation failures",
]


def _expand_prompts(total: int) -> list[str]:
    prompts: list[str] = []
    for i in range(total):
        base = SCENARIOS[i % len(SCENARIOS)]
        cycle = i // len(SCENARIOS) + 1
        if cycle > 1:
            prompts.append(f"{base} Variant {cycle}: tighten risk controls and ownership.")
        else:
            prompts.append(base)
    return prompts


def _make_payload(goal: str) -> dict:
    nodes = [
        {
            "id": "n1_analyze",
            "agent": AGENTS[0],
            "depends_on": [],
            "inputs": ["goal", "constraints"],
            "deliverable": "scope, constraints, and acceptance criteria",
            "acceptance_checks": ["scope is bounded", "owners named"],
        },
        {
            "id": "n2_plan",
            "agent": AGENTS[1],
            "depends_on": ["n1_analyze"],
            "inputs": ["analysis packet"],
            "deliverable": "ordered execution plan with checkpoints",
            "acceptance_checks": ["sequence is valid", "first irreversible action exists"],
        },
        {
            "id": "n3_implement",
            "agent": AGENTS[2],
            "depends_on": ["n2_plan"],
            "inputs": ["plan packet"],
            "deliverable": "implementation artifacts",
            "acceptance_checks": ["changes are scoped", "artifact list complete"],
        },
        {
            "id": "n4_validate",
            "agent": AGENTS[3],
            "depends_on": ["n3_implement"],
            "inputs": ["artifacts", "test plan"],
            "deliverable": "verification report and open issues",
            "acceptance_checks": ["tests pass", "regressions listed"],
        },
        {
            "id": "n5_handoff",
            "agent": AGENTS[4],
            "depends_on": ["n4_validate"],
            "inputs": ["validation report"],
            "deliverable": "release summary, risks, and next actions",
            "acceptance_checks": ["rollback path documented", "next owner assigned"],
        },
    ]
    edges = []
    for node in nodes:
        for dep in node["depends_on"]:
            edges.append({"from": dep, "to": node["id"]})
    return {
        "schema_version": "conductor.v3",
        "goal": goal,
        "agents": AGENTS,
        "nodes": nodes,
        "edges": edges,
        "checkpoints": CHECKPOINTS,
        "risks": RISKS,
        "handoff": {
            "primary_owner": "coordinator",
            "fallback_owner": "planner",
            "status_format": "short bullet summary with blockers and next action",
        },
    }


def _corrupt_json(valid_json: str) -> str:
    if '"schema_version"' in valid_json:
        return valid_json.replace('"schema_version"', "schema_version", 1)
    return valid_json[:-1] + ",}"


def _record(prompt: str, assistant_json: str, idx: int, kind: str, user_prompt: str | None = None) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt or prompt},
            {"role": "assistant", "content": assistant_json},
        ],
        "_meta": {
            "persona": "conductor",
            "dataset": "conductor_v3",
            "sample_id": idx,
            "sample_kind": kind,
            "source": "schema_template",
        },
    }


def build_records(plan_count: int, repair_count: int) -> list[dict]:
    records: list[dict] = []
    plan_prompts = _expand_prompts(plan_count)
    repair_prompts = _expand_prompts(repair_count)

    idx = 1
    for prompt in plan_prompts:
        payload = _make_payload(prompt)
        assistant_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        records.append(_record(prompt, assistant_json, idx, "plan"))
        idx += 1

    for prompt in repair_prompts:
        payload = _make_payload(prompt)
        valid = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        broken = _corrupt_json(valid)
        user = (
            "repair this conductor json so it is valid and schema-consistent. "
            "return json only.\n\n"
            f"{broken}"
        )
        records.append(_record(prompt, valid, idx, "repair", user_prompt=user))
        idx += 1

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Conductor v3 training dataset")
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--plan-count", type=int, default=80)
    parser.add_argument("--repair-count", type=int, default=40)
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    records = build_records(plan_count=args.plan_count, repair_count=args.repair_count)
    with output.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    print(f"wrote {len(records)} records -> {output}")
    print(f"  plan: {args.plan_count}")
    print(f"  repair: {args.repair_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
