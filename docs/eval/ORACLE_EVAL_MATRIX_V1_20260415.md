# Oracle Eval Matrix v1

Last updated: 2026-04-15
Status: active design for Phase 4 of `docs/ORACLE_CATALOG_CONSOLIDATION_PLAN_20260415.md`

## Purpose

This matrix replaces single blended Oracle scoring with routed boundary scoring.

Primary eval surfaces:

- `oos-author`
- `oos-debug`
- `alttp-trace`
- `xref`
- `wrong-convention-suppression`

Each surface is evaluated at `low`, `medium`, and `high` effort so promotion decisions can isolate:

- reasoning depth failures
- domain confusion failures
- mode confusion failures

## Source Pack

`docs/eval/oracle_boundary_effort_matrix_v1.jsonl`

Each JSONL record includes:

- `id`: stable case ID
- `surface`: one of the five matrix surfaces
- `domain`: `oos`, `alttp-vanilla`, or `xref`
- `mode`: `author`, `debug`, or `trace`
- `effort`: `low`, `medium`, or `high`
- `effort_group`: case family used to compare behavior across effort tiers
- `instruction`, `input`, `category`, `expected_keywords`
- optional `forbidden_keywords` and `effort_expectation`

## Scoring Intent

- `oos-author`: patch quality, project-convention correctness, and safe hook structure.
- `oos-debug`: evidence-first debugging behavior and failure isolation discipline.
- `alttp-trace`: vanilla trace fidelity, no unrequested authoring, no Oracle convention bleed.
- `xref`: explicit separation of vanilla vs Oracle flows and accurate mapping between them.
- `wrong-convention-suppression`: avoid injecting Oracle-specific assumptions into vanilla-only prompts.

## Effort Behavior Expectations

- `low`: terse, execution-first, minimal-but-correct output.
- `medium`: balanced diagnosis and implementation detail.
- `high`: explicit assumptions, evidence framing, and stronger risk handling.

## Promotion Gates (Oracle-Fast Alignment)

For a smaller candidate to qualify for the reserved `oracle-fast` contract:

- No critical failures on `alttp-trace`, `xref`, and `wrong-convention-suppression`.
- Competitive `low` effort behavior against `oracle` on shared matrix slices.
- No unacceptable regression in evidence-first `oos-debug`.
- Clear runtime/latency win that justifies a second public contract.

These gates mirror the policy in `docs/ORACLE_CATALOG_CONSOLIDATION_PLAN_20260415.md`.

## Medium-Verifiability Overlay

For backbone A/B decisions, pair this matrix with:

- `docs/eval/ORACLE_BACKBONE_AB_RUBRIC_V1_20260417.md`

That rubric covers the less binary but still important surfaces such as:

- project-specific posture
- explanation sharpness
- high-effort reasoning usefulness
- stop/continue chain judgment
