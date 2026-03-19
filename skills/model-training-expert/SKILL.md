---
name: model-training-expert
description: Expert guidance for LLM model training, synthetic data generation (SDE), Hierarchical MoE (H-MoE) management, and agentic evaluation. Use when setting up training runs (Vast.ai), generating datasets, or performing technical research PDF analysis for ROM hacking and general AI development.
---

# Model Training Expert

## 2026 Training Workflows

### 1. Hierarchical MoE (H-MoE) Setup
- **Backbone Selection:** Default to Qwen 2.5 Coder 14B/32B or Gemma 2 9B/27B.
- **Adapter Strategy:** Use LoRA with `r=64-128` for domain-specific experts.
- **Hot-Swapping:** Use `ollama` or `vLLM` to switch adapters dynamically without reloading the base model.

### 2. Synthetic Data Evolution (SDE)
- **Generation:** Use `scripts/generate_synthetic_data.py` to create initial drafts.
- **Verification:** Pipe generated code through assemblers (`asar`) or compilers to filter for correctness.
- **Correction:** Use a "Teacher" model (Gemini 2.0 Pro) to explain failures and generate "Correction Pairs" for training.

### 3. Agentic Evaluation (AgE)
- **Benchmarks:** Use the `Agahnim` suite for assembly and the `HAFS` suite for tool-usage.
- **Environment Loops:** Run evaluations in sandboxed emulators (Mesen2) or PTY environments.
- **Metrics:** Prioritize functional correctness (passes tests) over perplexity.

## Research PDF Ingestion
- **Vision-Augmented Parsing:** For complex tables/diagrams, use Gemini's vision capability to describe the image before converting to markdown.
- **Local Cataloging:** Use `afs_scawful research catalog` to maintain the index in `~/.context/index/research_catalog.json`.
- **Metadata Extraction:** See `references/pdf_parsing_guide.md` for schema details.

## Bundled Tools
- `scripts/vast_setup.py`: Provision and configure training instances on Vast.ai.
- `scripts/evaluate_model.py`: Run standardized benchmarks against local or remote models.
- `afs/model_router.py`: Intelligent H-MoE orchestration for adapter hot-swapping.
- `scripts/vision_ingest.py`: Vision-augmented parsing for PDFs and emulator screenshots.
- `scripts/verify_rom.py`: Agentic evaluation via Mesen2 Socket API.
- `scripts/agentic_preflight.sh`: Multi-stage validator chaining Z3DK diagnostics with boot checks.

## Knowledge References
Consult the global knowledge base at `~/.context/knowledge/models/` for background:
- Model portfolio & current status: `models/portfolio.md`
- Training pipeline (stages, scoring, augmentation): `models/training-pipeline.md`
- Dataset catalog (48+ datasets): `models/datasets.md`
- Infrastructure & Vast.ai ops: `models/infrastructure.md`
- Step-by-step workflows: `models/workflows.md`
- Serving & MoE routing: `models/serving.md`