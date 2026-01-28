---
name: echo-persona
description: Train, evaluate, and maintain the scawful-echo persona and related avatar models (Echo/Memory/Muse). Use when working on persona voice, dataset prep, A/B testing, deployment, or tool-calling constraints for avatar models.
---

# Echo Persona

## Scope
- Maintain scawful-echo voice, datasets, training runs, and evals for avatar models.

## Voice guardrails
- Write in lowercase, candid, lightly stream-of-consciousness style.
- Use dry humor with quiet hopefulness.
- Stay technical when it matters, casual otherwise.
- Avoid marketing tone or corporate polish.
- Keep responses conversational and grounded in known facts.

## Workflow
1. Confirm which avatar track is in scope (echo, memory, muse).
   - Use `~/src/lab/afs-scawful/docs/afs/avatar-models-comparison.md` for role intent.
2. Locate the dataset pipeline.
   - Use `~/src/training/docs/SCAWFUL_ECHO_V2.md` for the build script and mix.
   - Default output: `~/src/training/datasets/scribe-corpus/mlx_data_scawful_echo_v2/`.
3. Apply data prep rules and labels.
   - Follow `~/src/training/docs/avatar_data_prep.md` for schema and labeling.
4. Choose base model with tool-calling constraints in mind.
   - Prefer Qwen 2.5 when tool calling is required.
   - Treat Gemma 2 as tool-calling limited (see `~/src/training/docs/SCAWFUL_ECHO_AB_PLAN.md`).
5. Run training and monitoring.
   - Use `~/src/training/docs/avatar_training_ops.md` for watchers, alerts, and backups.
6. Evaluate with a fixed rubric.
   - Use persona fidelity, factual consistency, chat naturalness, and hallucination rate.
   - Use `~/src/training/evals/avatar_text_prompt_pack.jsonl` for quick checks.
7. Package and deploy.
   - Convert with `~/src/tools/model-mgr/model-mgr` (GGUF/MLX).
   - Deploy to LM Studio (preferred) or Ollama.

## References
- Read `references/sources.md` for source paths and anchors.