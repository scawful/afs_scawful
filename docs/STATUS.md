# STATUS

Stage: Prototype → **Alpha**

## Models

| Model | Status | Quality |
|-------|--------|---------|
| **nayru-7b-v1** | Production | Excellent 65816 ASM generation |
| farore-1.5b-v1 | Testing | FIM autocomplete (Windows) |
| veran-14b-v1-lora | Available | Needs 4-bit quantization |

See `MODEL_NAMING.md` for naming convention.

## Infrastructure

- Windows GPU (mm-d): Online via LAN SSH
- Vultr A100: On-demand ($1.29/hr)
- halext-nj: Backup server

## Current Focus

- [x] Training infrastructure improvements (cost protection, alerts)
- [x] Model naming convention (Oracle series)
- [x] First production model (nayru-7b-v1)
- [x] GGUF conversion for Ollama (nayru-7b-v1-q4km, 4.7GB)
- [ ] Eval framework with ASAR validation
- [ ] DeepSeek-Coder-V2 exploration

## Data

| Dataset | Samples | Purpose |
|---------|---------|---------|
| train.jsonl | 28,707 | Main ASM training |
| lsp_fim_train.jsonl | 3,497 | FIM autocomplete |
| lsp_train.jsonl | 3,706 | LSP autocomplete |

## Issues

- Windows training depends on mm-d availability (now via LAN)
- 14B model requires cloud GPU for merge (>20GB VRAM)

## Next Steps

1. Test farore-1.5b-v1 autocomplete model
2. Explore DeepSeek-Coder-V2-Lite for 128K context
3. Build ASAR eval framework
4. Train din-7b-v1 (optimization focus)
