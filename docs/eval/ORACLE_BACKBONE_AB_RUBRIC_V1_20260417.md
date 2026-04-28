# Oracle Backbone A/B Rubric v1

Last updated: 2026-04-17
Status: active comparison rubric for shared Oracle backbone decisions

## Purpose

This rubric makes the post-corrective Oracle A/B less subjective.

Primary comparison:

- corrected shared Qwen3 model: `qwen3-oracle-8b-v1-corrective2`
- shared Qwen3.5 challenger: `qwen35-oracle-9b-v1`

Optional later comparison:

- shared Qwen3 scale-up: `qwen3-oracle-14b-v1`

## Eval Inputs

Always run all three:

1. `training/evals/qwen3_rebase_eval_v1.jsonl`
2. `training/evals/qwen35_oracle_core_acceptance_v1.jsonl`
3. `docs/eval/oracle_boundary_effort_matrix_v1.jsonl`

The first two give hard evidence on tool/chain/core behavior. The boundary matrix
keeps the domain and effort contract honest.

## Hard Gates

Do not award the A/B win to a candidate that fails these gates, even if the
medium-verifiability rubric feels better.

### Gate 1 — Tool format

- no parser-breaking regressions
- no meaningful drop in exact tool-call formatting

### Gate 2 — Boundary discipline

- no critical failures on:
  - `alttp-trace`
  - `xref`
  - `wrong-convention-suppression`

### Gate 3 — Chain floor

- cannot stop after the first correct lookup when the prompt clearly requires a
  next action or second tool step

### Gate 4 — Latency sanity

- cannot be so timeout-prone that the apparent quality win is unusable in LM Studio

## Medium-Verifiability Overlay Rubric

Score each category `0`, `1`, or `2`.

- `0` = miss / weak behavior
- `1` = partly useful but inconsistent
- `2` = clearly correct and useful

Judge only on prompts where the category is actually relevant.

### 1) Project-Specific Posture

Question: does the model follow the right project work posture for the prompt?

Examples:

- debug prompt should investigate before patching
- trace prompt should explain flow before proposing changes
- author prompt should respect hook/ABI/bank-safety concerns

Scoring:

- `0`: jumps to patching or opinion with little evidence
- `1`: mentions the right posture but mixes it with premature action
- `2`: clearly sequences evidence first, then action, with the right project conventions

### 2) Explanation Sharpness

Question: is the answer specific and grounded, or generic and padded?

Scoring:

- `0`: generic coaching language, vague claims, filler explanation
- `1`: partly grounded but still padded or imprecise
- `2`: names the subsystem, constraint, or trace path directly and stays concise

### 3) High-Effort Reasoning Usefulness

Question: when `effort=high`, does the extra reasoning improve the answer?

Scoring:

- `0`: longer but not more useful; generic narration or repetition
- `1`: some useful assumptions/risk framing, but incomplete next-step reasoning
- `2`: explicit assumptions, evidence framing, and risk handling that materially improve the answer

### 4) Stop/Continue Chain Judgment

Question: does the model know when to continue the chain versus stop?

Scoring:

- `0`: stops too early or keeps going without evidence need
- `1`: mixed judgment; sometimes continues correctly, sometimes stops early
- `2`: stops only when enough evidence exists and continues when the prompt clearly requires another step

## Evidence Capture Rule

For every medium-verifiability score below `2`, record:

- prompt id
- candidate model
- score
- one quoted response fragment
- one sentence on why it scored that way

Do not score by vibe alone.

## Decision Policy

Qwen3.5 wins the backbone pivot only if:

1. it passes the hard gates
2. it beats corrected Qwen3 on the medium-verifiability overlay by a meaningful margin
3. the win shows up across more than one prompt family, not one cherry-picked example

If Qwen3.5 only wins on medium-verifiability overlay while tying or regressing on
hard gates, keep the current Qwen3 path.

If Qwen3.5 wins the hard gates but misses project-specific posture, allow exactly
one small corrective follow-up using reserved Qwen3.5 repair data before making a
final catalog decision.

## Result Template

Use this shape in the comparison note:

| Category | Qwen3 corrected | Qwen3.5 pilot | Winner | Notes |
| --- | ---: | ---: | --- | --- |
| Tool format hard gate | pass/fail | pass/fail |  |  |
| Boundary hard gate | pass/fail | pass/fail |  |  |
| Chain hard gate | pass/fail | pass/fail |  |  |
| Latency hard gate | pass/fail | pass/fail |  |  |
| Project-specific posture | 0-2 avg | 0-2 avg |  |  |
| Explanation sharpness | 0-2 avg | 0-2 avg |  |  |
| High-effort usefulness | 0-2 avg | 0-2 avg |  |  |
| Stop/continue judgment | 0-2 avg | 0-2 avg |  |  |

## Related Docs

- `docs/eval/ORACLE_EVAL_MATRIX_V1_20260415.md`
- `training/docs/ORACLE_VERIFIABILITY_AND_DATA_SCALING_20260417.md`
- `training/runs/qwen35_oracle_9b_v1/README.md`
