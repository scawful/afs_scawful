---
name: zelda-model-manager
description: Manage Zelda/ALTTP/Oracle model training, datasets, evals, registry updates, and deployment artifacts. Use when planning or running training runs, curating ASM datasets, selecting base models, evaluating outputs, or converting/serving GGUF or MLX models.
---

# Zelda Model Manager

## Scope
- Manage Zelda and ASM model lifecycle: dataset inventory, training runs, evals, registry, and deployment artifacts.
- Treat model names and deployment state as volatile. Verify the registry and
  target run/evaluation artifacts before recommending a launch or promotion.

## Workflow
1. Confirm the target model role and naming.
   - Use `~/src/lab/afs-scawful/config/chat_registry.toml` for the live runtime
     contract and `~/src/training/docs/ORACLE_FAMILY_SLOT_PLAN_20260420.md` for
     promotion criteria.
   - Use `~/src/docs/NAMING_CONVENTIONS.md` and
     `~/src/lab/afs-scawful/docs/MODEL_PORTFOLIO.md` only as supporting context;
     both contain dated historical sections.
   - Keep hostnames as SSH aliases (medical-mechanica, halext-nj) instead of IPs.
2. Locate datasets and scripts before deciding on a run.
   - Read `~/src/training/INDEX.md` and `~/src/training/README.md` for dataset paths and scripts.
   - Read the target's `~/src/training/runs/<run>/README.md`, TOML under
     `~/src/training/configs/zelda/`, and latest matching result/readiness doc.
   - Use `~/src/training/docs/TRAINING_OVERVIEW.md` for architecture and
     `~/src/training/docs/HOME_GPU_LAB_HARDWARE_TOPOLOGY.md` for placement.
3. Choose base model and hardware based on tool-calling needs.
   - Choose from measured slot-specific evaluations; do not hard-code one base
     model family across every Oracle role.
4. Run QA before training.
   - Run the dataset builder's validation plus the target's held-out overlap,
     schema, and readiness gates before launch.
   - Use `afs training freshness-gate` and `afs training dataset ...` for the
     supported AFS lifecycle surface; do not use the removed
     `python -m afs_scawful datasets index` command.
5. Monitor training and evaluate.
   - Use `~/src/training/scripts/windows_zelda_ctl.py` for passive Windows/WSL
     status and machine modes; use Vast only as the documented fallback.
   - Use eval packs in `~/src/training/evals/`.
   - Track ASAR pass rate for ASM validity.
6. Register and deploy artifacts.
   - Use the AFS registry (`~/src/lab/afs-scawful/config/chat_registry.toml`) to define personas, ports, and parameters.
   - Use `~/src/tools/model-mgr/model-mgr` for GGUF/MLX conversion and Ollama imports.
   - Refresh artifacts with `model-mgr artifacts-index`, then verify the actual
     serving endpoint or Windows host status before claiming deployment.

## Commands to reuse
- `model-mgr list` and `model-mgr info <model>` for inventory.
- `model-mgr working-set-report` for the local footprint and active set.
- `model-mgr convert <model> --quantize q4km` for GGUF.
- `model-mgr mlx-convert <model> --hf-path <path>` for MLX exports.

## Knowledge References
Consult the global knowledge base at `~/.context/knowledge/models/` for background:
- Model portfolio & status: `models/portfolio.md`
- Training pipeline architecture: `models/training-pipeline.md`
- Dataset catalog: `models/datasets.md`
- GGUF conversion & deployment: `models/infrastructure.md`
- Step-by-step workflows: `models/workflows.md`
- Serving & routing: `models/serving.md`

## References
- Read `references/sources.md` for source paths and anchors.
