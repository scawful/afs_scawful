# Nayru v5 Training Documentation

Generated: 2026-01-03

## Model Summary

| Property | Value |
|----------|-------|
| **Model Name** | nayru-v5 |
| **Base Model** | Qwen/Qwen2.5-Coder-7B-Instruct |
| **Architecture** | qwen2 |
| **Parameters** | 7.6B |
| **Context Length** | 32768 (configured: 4096) |
| **Quantization** | Q4_K_M |
| **Size** | 4.8 GB |
| **License** | Apache 2.0 (Alibaba Cloud) |

## Training Method

**Method:** LoRA (Low-Rank Adaptation) with QLoRA quantization

### LoRA Configuration

Based on `train_peft.py` and `train_peft_v2.py`:

```python
LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)
```

### Quantization Configuration

```python
BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)
```

## Training Platform

**Primary Training Environment:** Windows GPU (medical-mechanica / mm-d)

The merge script (`merge_nayru.py`) indicates:
- Windows paths: `D:/afs_training/checkpoints/7b_asm_v4/lora_adapters`
- Output: `D:/afs_training/models/nayru`
- Device: CUDA with bfloat16

**Note:** The Windows mount (`~/Mounts/mm-d/`) was not accessible during this documentation run. Training artifacts are stored on the Windows machine.

## Training Data

### Source Datasets (from local inventory)

The training data was compiled from ALTTP assembly sources:

| Dataset | Samples | Purpose |
|---------|---------|---------|
| `vultr_train_full.jsonl` | 28,707 | Main ASM training |
| `vultr_gold_full.jsonl` | 11,044 | Gold/validated set |
| `oos_enriched_v1_normalized_notodo.jsonl` | 19,303 | Oracle of Secrets enriched |
| `asm_augmented_20260101.jsonl` | 5,592 | Augmented ASM samples |
| `asm_comment_multi_20251231.jsonl` | 14,220 | Multi-line comment samples |
| `asm_comment_to_code_20251231.jsonl` | 14,219 | Comment-to-code samples |
| `train_validated_cleaned.jsonl` | 52 KB | ASAR-validated samples |

### Training Data Domain

- 65816 assembly language (SNES)
- ALTTP disassembly and ROM structure
- Nintendo development patterns
- SNES hardware registers ($2100-$21FF PPU, $4200-$43FF CPU)
- RAM usage ($7E:0000-$7F:FFFF)

## Model Configuration (Ollama)

From `ollama show nayru-v5`:

### System Prompt

```
You are Nayru, a 65816 assembly code generation specialist for SNES development.
Generate clean, well-commented 65816 assembly code with proper addressing modes,
correct lorom/hirom org addresses, and SNES-specific hardware register usage.
```

### Parameters

| Parameter | Value |
|-----------|-------|
| temperature | 0.5 |
| top_p | 0.85 |
| num_ctx | 4096 |

### Template Format

Uses Qwen2.5 ChatML template with `<|im_start|>` / `<|im_end|>` tokens.

## Adapter Details

From Ollama manifest, nayru-v5 includes:
- **Base Model Blob:** `sha256-60e05f21...` (4.68 GB)
- **LoRA Adapter Blob:** `sha256-b5376568...` (154 MB)

The adapter layer is loaded separately from the base GGUF, indicating this is a LoRA-merged model.

## Deployment

### Conversion Pipeline

1. Train LoRA adapters on Windows GPU
2. Merge adapters into base model (`merge_nayru.py`)
3. Convert to GGUF: `python llama.cpp/convert_hf_to_gguf.py nayru --outtype q4_k_m`
4. Create Ollama model: `ollama create nayru-v5 -f Modelfile.nayru`

### Ollama Registration

The model is registered locally:
- Manifest: `~/.ollama/models/manifests/registry.ollama.ai/library/nayru-v5/latest`
- Created: 2026-01-03 (3 hours ago at documentation time)

## Version History

| Version | Date | Notes |
|---------|------|-------|
| nayru-v2 | 2026-01-02 | Early iteration |
| nayru-v3 | 2026-01-02 | Improved training |
| nayru-v4 | 2026-01-02 | Eval score 0.39 (see eval_nayru-v4.json) |
| nayru-v5 | 2026-01-03 | Current production model |

## Evaluation (v4 Reference)

From `infra/eval_nayru-v4.json`:

| Category | Score |
|----------|-------|
| Optimization | 0.329 |
| Performance | 0.444 |
| Hardware | 0.375 |
| Size Reduction | 0.571 |
| **Total** | **0.392** |

**Note:** Nayru-v5 evaluation results not yet recorded.

## Known Gaps

The following training details could not be determined from local artifacts:

1. **Exact training dataset for v5** - Windows training directory not accessible
2. **Training duration and epochs** - Logs stored on Windows
3. **Validation metrics** - Not recorded locally
4. **Hyperparameters used** - Default scripts suggest:
   - Epochs: 3
   - Batch size: 1-4
   - Gradient accumulation: 4-8
   - Learning rate: 2e-4 to 3e-4
   - Max sequence length: 2048

## Recommendations for Future Training

To improve documentation for future training runs:

1. **Create training manifest** - JSON file with:
   - Base model name and version
   - Training dataset paths and sizes
   - Hyperparameters used
   - Training start/end timestamps
   - Final loss/eval metrics
   - Hardware used (GPU model, VRAM)

2. **Sync training logs** - Copy logs from Windows to Mac after training:
   ```bash
   scp starw@mm-d:D:/afs_training/logs/*.log ~/src/training/logs/
   ```

3. **Version checkpoint metadata** - Store with each adapter:
   ```json
   {
     "version": "v5",
     "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
     "training_date": "2026-01-03",
     "dataset": "zelda_16b_mix_v1",
     "epochs": 3,
     "final_loss": 0.xxx
   }
   ```

4. **Automate eval on new models** - Run eval suite immediately after Ollama registration

## Related Files

- `/Users/scawful/src/lab/afs/scripts/Modelfile.nayru` - Ollama Modelfile template
- `/Users/scawful/src/lab/afs/scripts/merge_nayru.py` - LoRA merge script
- `/Users/scawful/src/lab/afs-scawful/infra/scripts/train_peft.py` - Training script
- `/Users/scawful/src/lab/afs-scawful/infra/eval_nayru-v4.json` - v4 evaluation results
- `/Users/scawful/src/lab/afs-scawful/docs/MODEL_NAMING.md` - Oracle naming convention
