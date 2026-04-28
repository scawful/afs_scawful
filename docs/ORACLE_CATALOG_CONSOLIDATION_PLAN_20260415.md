# Oracle Catalog Consolidation Plan

Last updated: 2026-04-15
Status: proposed migration plan

## Decision Summary

- Public Oracle catalog contracts consolidate to `oracle`, `oracle-fast`, and a future `oracle-pro` only if a larger model clearly earns it.
- `plan` and `act` stop being public model identities. They become effort presets on the same model.
- The public name stays Oracle-branded even when the model must handle both Oracle of Secrets and vanilla ALTTP work.
- The ALTTP vs OOS distinction stays internal through routing, prompt overlays, skills, evals, and dataset tags.
- The serious shared Oracle models should move toward `Qwen3.5`, with smaller `Qwen3` / `Qwen3.5` models used as fast-path or proving-ground candidates.
- Target tiering is `oracle-fast` = `8-9B`, `oracle` = `14B`, `oracle-pro` = `27B`, subject to eval gates.
- Smaller models remain internal until a candidate clearly earns the `oracle-fast` contract.

## Why Change

The current public shape is more complicated than the real system:

- `oracle-main-plan` and `oracle-main-act` point to the same model artifact and mainly differ by prompt and token budget.
- `switchhook-plan` and `switchhook-act` are compatibility aliases, not distinct capabilities.
- The public catalog leaks rollout history instead of exposing a stable user-facing contract.
- The real useful axis is reasoning depth, not a fake split into separate planning and acting models.

The existing harness already supports reasoning effort through `thinking_tier`, so the public contract should align with that rather than multiply names.

## Target Public Shape

### Public names

- `oracle`
- `oracle-fast` (only after a smaller model clears eval gates)
- `oracle-pro` (only after a larger model proves a real quality jump worth the cost)

### Intended size tiers

- `oracle-fast`: `8-9B` fast/cheap model
- `oracle`: `14B` default public mainline
- `oracle-pro`: `27B` premium model, only if it earns the latency/cost tradeoff

The public names should stay stable and should not expose parameter counts directly. Parameter counts belong in docs, eval notes, and internal planning, not in the public contract.

### Public effort presets

- `low`: terse, tool-first, execution-oriented
- `medium`: balanced default
- `high`: evidence-first, longer diagnosis and design

### Public names to retire into compatibility aliases

- `oracle-main-plan`
- `oracle-main-act`
- `switchhook-plan`
- `switchhook-act`
- `oracle-tools`

## Internal Routing Shape

The public catalog should stay small, but the internal routing contract should stay explicit.

### Domain

- `oos`: Oracle hacked codebase, hooks, new code, project-specific systems
- `alttp-vanilla`: vanilla ALTTP disassembly reading and trace work
- `xref`: compare vanilla and hacked paths without collapsing the two

### Mode

- `trace`: explain, read, inspect, cross-reference, do not jump to patching
- `debug`: gather evidence, state capture, breakpoints, failure isolation
- `author`: patch design, new code, edits, refactors, hook writing

### Effort

- `low`
- `medium`
- `high`

### Skills as boundary enforcers

When the route is ambiguous, the system should prefer skill overlays over new public model entries:

- `alttp-disasm-labels`
- `oos-vanilla-xref`
- `oos-hook-author`
- `mesen2-oos-debugging`

These are a better fit for "vanilla trace vs Oracle authoring" than exposing extra public model names.

## Naming Decision

### Chosen direction

- mainline: `oracle`
- optional smaller sibling: `oracle-fast`
- optional larger sibling: `oracle-pro`

### Alternatives considered

- `oracle-main` / `oracle-fast`: acceptable but less clean than `oracle`
- `oracle-core` / `oracle-fast`: acceptable but heavier than needed
- `hyrule-*`, `sage-*`, `triforce-*`: more thematic, but less direct and more likely to blur roles

### Rejected direction

- public `plan` / `act` names
- public `switchhook-*` names
- public model names that expose base model details like `qwen35-*`
- a public ALTTP-only mainline before evals prove the unified Oracle model cannot hold the boundary

## Key Risk and Mitigation

### Risk

If the shared Oracle model is trained on mixed OOS and ALTTP data without explicit boundaries, it may:

- inject OOS conventions into vanilla disassembly reading
- answer trace-only prompts with patch-authoring behavior
- treat cross-reference work like single-domain work

### Mitigation

Do not solve this by making more public names.

Solve it with:

- explicit `domain` and `mode` routing
- stronger system-prompt overlays
- skill selection
- boundary evals
- boundary-tagged training data

## Phased Migration Plan

### Phase 1: Freeze the new contract

Goal: define the stable public surface before changing implementation.

Deliverables:

- `oracle` becomes the intended canonical public mainline name
- `oracle-fast` is reserved but not promoted until a smaller model earns it
- `oracle-pro` is reserved for a future larger model and should not be exposed until a premium model clearly justifies the extra cost and latency
- old `plan` / `act` names are officially downgraded to compatibility aliases

Acceptance:

- docs describe `oracle` as the future public mainline
- no new code or docs introduce additional public Oracle names

### Phase 2: Registry and prompt-layer cleanup

Goal: make the registry reflect one model with effort presets instead of two fake model identities.

Primary files:

- `config/chat_registry.toml`
- `src/afs_scawful/chat_harness.py`
- `src/afs_scawful/integrations/openai_client.py`

Changes:

- add canonical `oracle` entry pointing at the current mainline artifact
- keep `oracle-main-plan` and `oracle-main-act` as aliases to the same artifact
- map legacy `plan` preset to `thinking_tier = high`
- map legacy `act` preset to `thinking_tier = low`
- keep concise vs expanded response style in prompt/options, but stop presenting them as different models

Acceptance:

- one canonical mainline name resolves cleanly
- old names still work without breaking scripts or habits
- `--thinking-tier` overrides remain authoritative

### Phase 3: Add internal domain and mode profiles

Goal: preserve ALTTP/OOS distinctions without public catalog sprawl.

Primary files:

- `src/afs_scawful/chat_harness.py`
- router config in `config/chat_registry.toml`
- any Oracle preset helpers used by the harness

Changes:

- add internal profile fields for `domain` and `mode`
- resolve requests in this order:
  1. domain
  2. mode
  3. effort
- merge prompt overlays so the model is told whether it should:
  - read vanilla disassembly
  - debug Oracle hacked code
  - author new code

Acceptance:

- the same `oracle` model can be routed into vanilla trace mode or Oracle author mode without changing public name

### Phase 4: Make evals match the real routing contract

Goal: stop judging the model with one blended score only.

New eval matrix:

- `oos-author`
- `oos-debug`
- `alttp-trace`
- `xref`
- `wrong-convention suppression`
- `low` / `medium` / `high` effort behavior

Concrete v1 artifacts:

- design doc: `docs/eval/ORACLE_EVAL_MATRIX_V1_20260415.md`
- prompt pack: `docs/eval/oracle_boundary_effort_matrix_v1.jsonl`

Important boundary cases:

- vanilla prompt where writing new OOS code is wrong
- OOS patch prompt where vanilla-only tracing is insufficient
- cross-reference prompt where the model must keep hacked and vanilla flows separate

Acceptance:

- promotion decisions can show whether a model failed because of reasoning depth, domain confusion, or author/trace confusion

### Phase 5: Rebuild training data around shared repair buckets

Goal: consolidate learning before consolidating weights.

Shared repair buckets:

- `thinking`
- `tool_format`
- `chain`
- `domain_boundary`

Dataset policy:

- every Oracle sample should be taggable by `domain`, `mode`, and optionally `effort`
- the same task can have `low`, `medium`, and `high` effort variants
- specialists should consume shared repair buckets first, private data second
- strong specialists may also act as narrow internal teachers for shared models, but only on the routed surfaces where they clearly beat the mainline

Specialist distillation policy:

- distill specialist traits by disagreement, not by volume
- only lift the surfaces where the specialist passes and the shared model underperforms
- keep specialist distillation buckets narrow, e.g. `farore_domain_distill`, `farore_chain_distill`
- do not distill a specialist's failed shared-core behavior into `oracle` or `oracle-fast`

Acceptance:

- the shared mainline Oracle model gets the best reasoning and tool-call repairs first
- specialists are no longer improving in isolated silos for generic failures

### Phase 6: Prune the specialist bench by evidence

Goal: reduce internal catalog bloat after the current training wave settles.

Rule:

- keep a specialist only if it wins on a durable routed surface that the mainline and `oracle-fast` do not already cover

Expected candidates to keep if they earn it:

- `din` for optimization
- `nayru` for explanation
- `farore` for debugging, quick repair planning, room inspection, and evidence-first diagnostics

Expected candidates to fold back into shared data if they do not earn it:

- `majora`
- `hylia`
- `veran`
- `agahnim`
- `sahasrahla`

Current interpretation after the first specialist eval wave:

- active AFS training-track surfaces consolidate to `din`, `nayru`, and `farore`
- `farore` is not the FIM/autocomplete identity; that role belongs to `navi`
- `veran`, `majora`, `hylia`, `agahnim`, and `sahasrahla` should be treated as archive/sunset candidates unless a later eval wave proves a unique routed surface that beats the shared Oracle model
- if retired specialist knowledge is retained, keep it as small grounded data slices rather than active routed specialists

Acceptance:

- every surviving specialist has a documented reason to exist
- redundant specialists are retired or reduced to internal eval tracks

## Immediate Implementation Order

1. Add the new canonical `oracle` registry entry and keep the old names as aliases.
2. Refactor the current `plan` / `act` prompts into effort presets.
3. Add internal `domain` and `mode` routing overlays.
4. Extend eval packs with boundary cases and effort variants.
5. Feed Claude-generated thinking/tool-call repairs into the shared Oracle data pipeline.
6. Finish the current specialist wave and score redundancy before promoting `oracle-fast` or pruning internal specialists.

## `oracle-fast` Promotion Criteria

`oracle-fast` is a reserved public contract, not an automatic destination for the next smaller model.

Promotion requires all of the following:

- clear operational value: materially lower latency, VRAM, or cost than `oracle`
- no critical boundary failures on:
  - `alttp-trace`
  - `xref`
  - wrong-convention suppression
- competitive low-effort performance on the shared Oracle eval surface
- strong tool formatting and chain completion at small-model settings
- no unacceptable regression in evidence-first debugging behavior

Recommended gate shape:

- within 10% of `oracle` on the shared eval matrix overall
- pass the dedicated low-effort tool-format pack
- pass the domain-boundary pack without critical OOS/ALTTP confusion
- show a clear runtime win large enough to justify a second public contract

Until those gates are met, smaller candidates stay internal or experimental.

## `oracle-pro` Promotion Criteria

`oracle-pro` is not just "a bigger checkpoint". It should exist only if it gives a real quality jump over the default `oracle` model.

Promotion requires all of the following:

- clear quality win over `oracle` on the shared eval matrix
- stronger high-effort reasoning, chain completion, or cross-reference quality that users will actually feel
- acceptable latency/cost for an explicitly premium tier
- no major regression in tool formatting or domain-boundary discipline

Recommended interpretation:

- a `14B` model should be the likely default `oracle`
- a `27B` model should only become `oracle-pro` if it beats that `14B` model by enough to justify a separate public tier

## Post-Wave Oracle Router Decision Gate

The public router should default to `oracle`, but internal specialist routing may remain temporarily while the current wave is still proving itself.

### Temporary state during the current wave

- public contract: `oracle`
- internal overrides may still route a narrow prompt surface to surviving specialists
- those overrides are provisional and should be treated as a measurement phase, not a permanent public contract

### Decision after the current specialist wave finishes

Collapse the public router fully to `oracle` unless a specialist demonstrates a durable win on a routed surface.

Retention criteria for an internal override:

- it beats `oracle` on its intended routed eval slice by a meaningful margin
- it does not introduce domain-boundary confusion relative to `oracle`
- the routed surface is common enough to justify the complexity
- the improvement survives at least one follow-up corrective iteration

Recommended interpretation:

- keep `din` only if optimization prompts clearly improve with it
- keep `nayru` only if explanation or teaching prompts clearly improve with it
- keep `farore` only if debugging and quick repair prompts clearly improve with it
- fold `veran`, `majora`, `hylia`, `agahnim`, and `sahasrahla` back into shared data unless they later earn a distinct routed surface

If no specialist clears those bars, the Oracle router should collapse to `oracle` by default with domain/mode/effort profiles doing the differentiation instead of model switching.

## What Not To Do

- do not create a public ALTTP-only mainline yet
- do not merge adapters blindly just to reduce catalog count
- do not expose base model family names in the public contract
- do not keep `plan` / `act` alive as first-class public names after the migration begins

## Current Default Recommendation

- Public smaller sibling: `oracle-fast` for the `8-9B` fast model once a candidate earns it
- Public mainline: `oracle` for the likely `14B` default model
- Public larger sibling: reserve `oracle-pro` for a `27B` premium model only if it clearly earns the extra cost/latency
- Internal routing: `domain` + `mode` + `effort`
- Skills: use skills to enforce boundaries instead of adding more public model names
