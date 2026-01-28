"""
Zelda Model Evaluation & Agentic Testing System.

Evaluates 7B expert models (Din, Nayru, Veran, Farore) on:
- ALTTP/65816/SNES knowledge benchmarks
- Real Oracle-of-Secrets bugs and TODOs
- Code generation and debugging tasks

Uses Gemini 3 Flash Preview as orchestrator with extended thinking,
git worktree sandboxes for testing, and ASAR/yaze for validation.
"""

__version__ = "0.1.0"
