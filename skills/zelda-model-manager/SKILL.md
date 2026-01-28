---
name: zelda-model-manager
description: Manage Zelda/ALTTP/Oracle model training, datasets, evals, registry updates, and deployment artifacts (Nayru/Din/Farore/Veran/Sahasrahla/IQuest). Use when planning or running training runs, curating ASM datasets, selecting base models, evaluating outputs, or converting/serving GGUF or MLX models.
---

# Zelda Model Manager

## Scope
- Manage Zelda and ASM model lifecycle: dataset inventory, training runs, evals, registry, and deployment artifacts.

## Workflow
1. Confirm the target model role and naming.
   - Use `~/src/docs/NAMING_CONVENTIONS.md` and `~/src/lab/afs-scawful/docs/MODEL_PORTFOLIO.md`.
   - Keep hostnames as SSH aliases (medical-mechanica, halext-nj) instead of IPs.
2. Locate datasets and scripts before deciding on a run.
   - Read `~/src/training/INDEX.md` and `~/src/training/README.md` for dataset paths and scripts.
   - For large runs, consult `~/src/training/docs/IQUEST_40B.md`.
   - For smaller Zelda plans, consult `~/src/lab/afs-scawful/docs/ZELDA_16B_TRAINING_PLAN.md`.
3. Choose base model and hardware based on tool-calling needs.
   - Prefer Qwen 2.5 Coder for tool calling and ASM workflows.
   - Follow `~/src/training/docs/MODEL_SELECTION_AND_PRACTICES.md`.
4. Run QA before training.
   - Use dataset QA and registry updates described in `~/src/lab/afs-scawful/docs/ZELDA_16B_TRAINING_PLAN.md`.
   - Ensure AFS dataset index is current (`python -m afs_scawful datasets index`).
5. Monitor training and evaluate.
   - Use eval packs in `~/src/training/evals/`.
   - Track ASAR pass rate for ASM validity.
6. Register and deploy artifacts.
   - Use the AFS registry (`~/src/lab/afs-scawful/config/chat_registry.toml`) to define personas, ports, and parameters.
   - Use `~/src/tools/model-mgr/model-mgr` for GGUF/MLX conversion and Ollama imports.
   - Test deployments using `python3 ~/src/lab/afs/lmstudio_client.py` (checks health and ports).

## Commands to reuse
- `model-mgr list` and `model-mgr info <model>` for inventory.
- `model-mgr convert <model> --quantize q4km` for GGUF.
- `model-mgr mlx-convert <model> --hf-path <path>` for MLX exports.

## References
- Read `references/sources.md` for source paths and anchors.