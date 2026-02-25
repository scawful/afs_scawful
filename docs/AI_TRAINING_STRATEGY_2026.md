# AI Training Strategy 2026: The Agentic Evolution

## 1. Architectural Shift: Hierarchical MoE (H-MoE)
Moving away from separate standalone models to a shared backbone architecture.

- **Shared Backbone:** Qwen 2.5 Coder 14B or 32B (Q4_K_M).
- **Hot-Swappable Adapters:** Use PEFT/LoRA adapters (~100MB-500MB) for specific experts (Din, Nayru, Veran).
- **Dynamic Loading:** Implement a "Just-In-Time" adapter loader based on the orchestrator's intent classification.
- **Ensemble Reasoning:** For complex tasks, run multiple experts in parallel and use a "Zelda" (Architecture) expert to synthesize the final output.

## 2. Synthetic Data Evolution (SDE)
Leveraging "Model-in-the-Loop" data generation.

- **Self-Correction Loops:** Generate assembly code, run it through `asar` (assembler), and feed errors back to the model to generate "Negative Samples" and "Correction Pairs".
- **Distillation:** Use larger models (e.g., Gemini 2.0 Pro) to generate high-quality reasoning traces for complex ROM hacking tasks, then distill into the local 7B/14B experts.
- **Diversity Injection:** Use `chaos-monkey` style augmentation to vary code style, register usage, and optimization levels in synthetic datasets.

## 3. Agentic Evaluation (AgE)
Shifting from static benchmarks to interactive environment testing.

- **Sandbox Evals:** Test models by having them perform actual ROM edits in a sandboxed Mesen2 environment.
- **Success Metrics:** Code size, cycle count, memory safety, and "Bootability" (does the game still run?).
- **Human-AI Synergy Score:** Measure how well the model follows user constraints and handles feedback loops.

## 4. Vision-Augmented PDF & Data Ingestion
- **Multimodal Parsing:** Use Gemini 2.0 Vision to parse complex tables, diagrams, and memory maps in research PDFs that `pypdf` struggles with.
- **Screenshot-to-Dataset:** Automate the capture of emulator state (Mesen2) and convert visual bugs/glitches into structured training examples for the `Farore` (Debugging) expert.

## 5. Implementation Roadmap (2026)
- **Q1:** Implement H-MoE adapter switching in the AFS orchestrator.
- **Q2:** Launch the "Veran" Analysis expert using SDE-generated disassembly data.
- **Q3:** Integrate Vision-Augmented ingestion for the Research Catalog.
- **Q4:** Full "Agentic Eval" suite for ROM hacking tasks.
