# TRAINING ROADMAP

Scope: AFS Scawful training data pipelines and monitoring. Research-only.

## Committed (exists now)
- Dataset registry indexing (local)
- Resource indexing (local)
- Plugin config loader for training paths/resources
- Validator base + initial validators (ASM/C++/KG/ASAR)

## Planned (near-term)
- Generator base + one small generator
- Training monitor schema validation and config docs

## Planned (mid-term)
- Generator runner that produces dataset manifests
- QA summary reports (counts, sizes, validation results)
- Repeatable dataset build scripts (local-only)

## Ideas (later)
- Training campaign runner (batching + resume)
- Per-generator metrics export (JSON)
- Optional remote sync hooks (explicit opt-in, no auto-network)

## Unknown / needs verification
- Which generators can be safely generalized outside local workflows
- Which validation checks are still useful vs legacy noise
