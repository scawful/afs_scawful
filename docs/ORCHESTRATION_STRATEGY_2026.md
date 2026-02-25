# AI Orchestration & Sub-Agent Strategy (2026)

## 1. Multi-Model Tiering

| Tier | Model | Primary Role | Strength |
| :--- | :--- | :--- | :--- |
| **Architect** | **Gemini 3 Pro** | Multi-modal research, long-context planning, and AFS orchestration. | 2M+ Context, Vision-to-MD. |
| **Builder** | **Claude 4.6 Opus** | Complex refactoring, logic verification, and test generation. | Superior reasoning, code safety. |
| **Iteration** | **ChatGPT 5.3** | Rapid prototyping, documentation, and real-time troubleshooting. | Low latency, high throughput. |
| **Specialist** | **Triforce MoE** | 65816 Assembly optimization, ROM analysis (Local). | Domain-specific expertise. |

## 2. Sub-Agent Workflows

### The "A-B-V" Loop (Architect-Builder-Validator)
1.  **Architect (Gemini 3):** Analyzes the request, mounts relevant AFS context, and defines the high-level `PLAN.md`.
2.  **Builder (Claude 4.6):** Executes the plan, writing code and unit tests.
3.  **Validator (Local / GPT-5.3):** Runs build/lint/test commands and performs "Agentic Evaluation" in the sandbox.

## 3. Tool Discovery & Installation
- **MCP Servers:** Use the Model Context Protocol to bridge local tools (Mesen2, Asar) to cloud sub-agents.
- **Dynamic Skills:** Sub-agents can trigger `skill-creator` to generate new procedural skills on-the-fly when encountering unknown project patterns.

## 4. Hardware Allocation
- **Local Experts:** Run on M5 (Inference) and 5060 Ti (Training).
- **Cloud Experts:** Orchestrated via Gemini CLI for complex reasoning tasks that exceed local VRAM.
