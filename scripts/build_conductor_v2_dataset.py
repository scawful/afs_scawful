#!/usr/bin/env python3
"""Build a strict-schema Conductor v2 dataset.

Outputs JSONL chat records with deterministic DAG schema so Conductor learns
stable JSON structure.
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path("data/training_data/conductor_v2.jsonl")

SYSTEM = (
    "You are The Conductor. Decompose goals into Agent-to-Agent handoff plans. "
    "Output valid JSON only. Use a DAG with explicit nodes, dependencies, and deliverables."
)

PROMPTS = [
    "plan a 3-agent swarm to fix a failing ci pipeline in a python repo and ship a patch today.",
    "orchestrate a workflow to add a new persona model: dataset generation, training, eval, and registry update.",
    "design a DAG for migrating a sqlite schema with zero downtime and rollback support.",
    "build an agent plan for investigating a production memory leak and delivering a verified fix.",
    "decompose a cross-repo refactor touching api contracts and frontend consumers.",
    "create a handoff sequence to train and deploy monolith-v1 locally with smoke tests.",
    "orchestrate a bug triage sprint for 40 issues with strict priority and ownership.",
    "plan a release pipeline for a model update with canary, eval gate, and promotion criteria.",
    "design an agent DAG for importing legacy docs, extracting decisions, and updating architecture notes.",
    "orchestrate an incident response for elevated api latency: diagnose, mitigate, validate, communicate.",
    "build a swarm plan to convert four LoRA adapters into GGUF and verify each artifact checksum.",
    "create a DAG to run nightly evals, collect failures, generate repair data, and trigger micro-fix training.",
    "decompose a task to add strict json output support end-to-end across prompt, model, and evaluator.",
    "plan a two-day sprint for cleaning stale docs and aligning status with real training outcomes.",
    "orchestrate benchmark runs for three models and produce a promotion recommendation.",
    "design a swarm handoff for data QA: dedupe, schema validate, privacy scan, and publish.",
    "plan a repo-wide dependency reduction campaign with measurable outcomes.",
    "build a DAG for reproducing a user bug, adding regression tests, and releasing a patch.",
    "orchestrate a local-to-remote model artifact sync with integrity validation and fallback.",
    "create an execution plan to bootstrap conductor-v1 dataset, train it, and run json-structure evals.",
    "plan a multi-agent workflow to triage and clear a 200-item personal task backlog in one week.",
    "design a DAG for journaling pipeline automation: capture, classify mood, summarize, and review trends.",
    "orchestrate a poem-writing assistant launch: dataset, style eval, safety checks, and deployment.",
    "build an agent handoff plan for long-form essay drafting with citation verification and revision gates.",
    "decompose a task-management model rollout including data prep, fine-tune, eval, and router updates.",
    "design a DAG for migrating all model cards to a unified metadata schema and validation.",
    "orchestrate a weekly model-ops cadence: eval collection, regression triage, patching, promotion decision.",
    "create an execution plan to harden prompt-injection defenses across local model endpoints.",
    "plan a cross-agent workflow for converting user journal entries into actionable weekly priorities.",
    "decompose a release train for three persona model updates with rollback and smoke checks.",
    "design an agent DAG to produce a polished essay from raw notes with argument-structure checkpoints.",
    "orchestrate incident response for broken model routing rules causing wrong persona selection.",
    "create a plan to benchmark creative-writing models on poetry, narrative voice, and coherence.",
    "design a DAG for building a personal memory index from journals, commits, and docs with privacy filters.",
    "orchestrate a remediation workflow for low-quality synthetic training samples in a dataset.",
    "plan an experiment matrix for temperature/system-prompt sweeps on task-management assistants.",
    "build a handoff sequence for generating monthly reflection reports from daily journal entries.",
    "decompose an end-to-end workflow for thesis-style essay writing with research and outline agents.",
    "design a DAG for validating json schema compliance in a conductor model output stream.",
    "orchestrate a project to turn unfinished docs into publishable long-form essays in four sprints.",
]


def make_record(prompt: str, idx: int) -> dict:
    payload = {
        "goal": prompt,
        "dag": {
            "nodes": [
                {
                    "id": "analyze",
                    "agent": "analyst",
                    "depends_on": [],
                    "deliverable": "constraints, scope, and acceptance criteria",
                },
                {
                    "id": "plan",
                    "agent": "planner",
                    "depends_on": ["analyze"],
                    "deliverable": "ordered execution plan with checkpoints",
                },
                {
                    "id": "implement",
                    "agent": "builder",
                    "depends_on": ["plan"],
                    "deliverable": "working implementation artifacts",
                },
                {
                    "id": "validate",
                    "agent": "tester",
                    "depends_on": ["implement"],
                    "deliverable": "verification report and regressions summary",
                },
                {
                    "id": "handoff",
                    "agent": "coordinator",
                    "depends_on": ["validate"],
                    "deliverable": "final summary, open risks, and next actions",
                },
            ]
        },
        "version": "v2",
    }
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": json.dumps(payload, ensure_ascii=True, separators=(",", ":"))},
        ],
        "_meta": {
            "persona": "conductor",
            "dataset": "conductor_v2",
            "sample_id": idx,
            "source": "schema_template",
        },
    }


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    records = [make_record(prompt, i + 1) for i, prompt in enumerate(PROMPTS)]
    with OUTPUT.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")
    print(f"wrote {len(records)} records -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
