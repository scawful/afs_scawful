# STATUS

Stage: Prototype → **Alpha**

## Models

| Model | Status | Quality |
|-------|--------|---------|
| **nayru-7b-v1** | Production | Excellent 65816 ASM generation |
| farore-1.5b-v1 | Testing | FIM autocomplete (Windows) |
| veran-14b-v1-lora | Available | Needs 4-bit quantization |
| muse-v2 | Completed | Needs broader eval |
| scawful-echo | Training (Vast) | Unknown / needs verification |
| zelda-16b-v1 | Benchmark (Vast) | Stopped |
| twitter-avatar-qwen25-3b | Training (Windows GPU) | Unknown / needs verification |
| twitter-avatar-qwen25-7b | Training (Vast) | Unknown / needs verification |

See `MODEL_NAMING.md` for naming convention.
Runtime alias mapping lives in `config/chat_registry.toml` (aliases are stable; model IDs may change).

## Infrastructure

- Windows GPU (mm-d): Online via LAN SSH
- Vultr GPU: Default plan `vcg-a100-3c-30g-20vram` (see `infra/VULTR_GPU_PLANS.md`)
- halext-nj: Backup server
- Vast GPU: muse-v2 on RTX 4090 (instance 29465486)
- Vast GPU: scawful-echo on RTX 4090 (instance 29472137)
- Vast GPU: zelda-16b benchmark on H100 NVL (instance 29451377, destroyed after exit; see `docs/VAST_SETUP.md`)
- Vast GPU: twitter-avatar-qwen25-7b on RTX 4090 48GB (instance 29482871)

## Training Status

Latest check: 2026-01-04

- muse-v2 (instance 29465486): training completed; model saved to `/opt/training/models/muse-v2` and synced locally
- muse-v2 quick eval produces coherent output; Ollama model `muse-v2:latest` created
- scawful-echo (instance 29472137): training in progress (~79% epoch 3.16) with eval loss ~0.365
- scawful-echo: Hugging Face token installed and Gemma config download verified; re-check logs for new 401 warnings
- zelda-16b (instance 29451377) exited and was destroyed to stop billing
- twitter-avatar-qwen25-7b (instance 29482871): training started; logs at `/opt/training/logs/twitter-avatar-qwen25-7b.log`
- twitter-avatar-qwen25-3b (Windows GPU): training started (Windows Python 3.12, no-quant); logs at `D:\src\training\logs\twitter-avatar-qwen25-3b.log`

## Current Focus

- [x] Training infrastructure improvements (cost protection, alerts)
- [x] Model naming convention (Oracle series)
- [x] First production model (nayru-7b-v1)
- [x] GGUF conversion for Ollama (nayru-7b-v1-q4km, 4.7GB)
- [ ] Eval framework with ASAR validation
- [ ] DeepSeek-Coder-V2 exploration
- [ ] Zelda-16B benchmark (Vast H100 NVL)

## Data

Local inventory lives in `docs/TRAINING_DATA_INVENTORY.md` (source: `~/src/training/datasets`).
Windows datasets under `D:\afs_training\datasets` are not verified here.

| Dataset | Samples | Purpose |
|---------|---------|---------|
| `vultr_train_full.jsonl` | 28,707 | Main ASM training (local inventory) |
| `vultr_gold_full.jsonl` | 11,044 | Gold set (local inventory) |
| `oos_enriched_v1_normalized_notodo.jsonl` | 19,303 | Oracle of Secrets enriched (local inventory) |
| `nerv_watcher_v1.jsonl` | 211 | Nerv watcher (local inventory) |
| `expert_router_v1.jsonl` | 53 | Expert router (local inventory) |
| `lsp_fim_train.jsonl` | Unknown / needs verification | FIM autocomplete (Windows dataset) |
| `lsp_train.jsonl` | Unknown / needs verification | LSP autocomplete (Windows dataset) |
| `twitter-2026-01-04-text-only` | 11,480 (standalone) | Twitter avatar text-only dataset |

## Issues

- Windows training depends on mm-d availability (now via LAN)
- 14B model requires cloud GPU for merge (>20GB VRAM)
- (Optional) Re-run training script quick test end-to-end if needed

## Next Steps

1. Test farore-1.5b-v1 autocomplete model
2. Plan zelda-16b-v1 (DeepSeek-Coder-V2-Lite, 128K context)
3. Build ASAR eval framework
4. Train din-7b-v1 (optimization focus)
