# Model Strategy (Base Models + Quantization)

This is a living note for choosing base models and quantization settings.
Keep it practical and tied to available hardware.

## Base Model Shortlist (Text)

**Chat / persona (3B-8B):**
- Qwen2.5-3B-Instruct (fast, cheap, good for MLX)
- Qwen2.5-7B-Instruct (strong chat, fits 4090 with LoRA)
- Llama 3.1/3.2 8B Instruct (good general chat, larger footprint)

**Code / tooling:**
- Qwen2.5-Coder-7B-Instruct (code + tool style)
- DeepSeek-Coder-V2-Lite-Instruct (bigger, cloud GPU)

**Small routing / utilities (1B-2B):**
- Qwen2.5-1.5B-Instruct
- Gemma 2 2B IT

## Multimodal (Separate Track)

Gemma 3 models are Image-Text-to-Text (multimodal). They require a separate
pipeline from text-only LoRA training. Keep these as a future track.

## Quantization Guidance

**Training (cloud GPU)**
- Prefer QLoRA 4-bit (NF4) on 24GB cards.
- If bitsandbytes breaks, fall back to bfloat16 with LoRA (slower, bigger).

**Inference (local)**
- GGUF: `q4_k_m` baseline, `q5_k_m` when quality matters.
- MLX: 4-bit or 8-bit depending on latency vs quality.
- For evaluation, use higher precision when possible to avoid quant artifacts.

## Deployment Notes

- Keep base models on Windows (D:).
- Store adapters separately; merge only for export.
- Export targets:
  - GGUF for Ollama / llama.cpp
  - MLX for Mac

## Selection Checklist

- Does the base model fit the target GPU with LoRA?
- Does it support your chat template correctly?
- Do you need text-only or multimodal?
- Is the license/usage gate accessible?
