# Advanced ASM Model Training Strategy

## Current State
- Local dataset inventory updated (see `docs/TRAINING_DATA_INVENTORY.md`).
- 1.5B training sample counts: Unknown / needs verification.
- RTX 5060 Ti (17GB) for local training.
- Vultr GPU plans available via API; A100 ranges 4–640 GB GPU VRAM (GPU count unknown / needs verification). See `infra/VULTR_GPU_PLANS.md`.

## Phase 1: Improve Data Quality (Before Scaling)

### A. Structured ASM Examples
Instead of raw code, create structured training pairs:

```json
{
  "instruction": "Explain this ALTTP routine and suggest an optimization",
  "input": "```asm\nLDA $0E20,X   ; Load enemy HP\nSEC\nSBC #$10      ; Subtract 16\nSTA $0E20,X   ; Store result\nBPL .alive\nSTZ $0DD0,X   ; Kill enemy\n.alive:\nRTS\n```",
  "output": "This routine damages an enemy by 16 HP.\n\n**Analysis:**\n- $0E20,X = Enemy HP table\n- $0DD0,X = Enemy alive flag (0 = dead)\n\n**Optimization:**\n```asm\nLDA $0E20,X\nSBC #$10      ; Carry already set from positive HP\nBCC .kill     ; Branch if HP went negative\nSTA $0E20,X\nRTS\n.kill:\nSTZ $0DD0,X\nRTS\n```\nSaves 1 cycle by using BCC instead of BPL and avoiding redundant store when killing."
}
```

### B. Chain-of-Thought for Complex Tasks
```json
{
  "instruction": "Trace execution through this sprite handler",
  "input": "<code>",
  "output": "<step-by-step analysis with register states>"
}
```

### C. Self-Correction Training
Include examples where model catches errors:
```json
{
  "instruction": "Review this code for bugs",
  "input": "```asm\nLDA #$00\nXBA\nLDA #$10\nTAX\n```",
  "output": "Bug: XBA swaps A high/low bytes but doesn't affect X transfer.\n\n**Issue:** After XBA, A = $0000 (8-bit mode shows $00).\nThen LDA #$10 makes A = $10, so TAX sets X = $10.\n\n**If intent was X = $1000:**\n```asm\nLDA #$00\nXBA\nLDA #$10  ; A = $1000\nREP #$10  ; 16-bit index\nTAX       ; X = $1000\n```"
}
```

## Phase 2: Scaling Path

### Model Size Progression
| Model | VRAM (QLoRA) | Local? | Est. Quality |
|-------|--------------|--------|--------------|
| 1.5B  | 8GB          | Yes    | Tool calling, simple tasks |
| 3B    | 12GB         | Yes    | Good ASM analysis |
| 7B    | 16GB         | Tight  | Complex reasoning |
| 14B   | 24GB         | Cloud  | Expert-level |

### Recommended Progression
1. **Now**: 1.5B with current data → baseline
2. **Next**: 3B with improved data → compare vs 1.5B
3. **If 3B wins**: Scale data, not model
4. **If ceiling hit**: Move to 7B with a Vultr A100 plan sized from `infra/VULTR_GPU_PLANS.md`

### Base Models to Consider
| Model | Strengths | Notes |
|-------|-----------|-------|
| Qwen2.5-Coder | Code understanding | Current choice |
| DeepSeek-Coder | Strong at code | Open weights |
| DeepSeek-Coder-V2-Lite (16B) | 128K context, MoE | Target for zelda-16b-v1 |
| CodeLlama | ASM instruction knowledge | Meta's offering |
| Yi-Coder | Efficient architecture | Longer context |

## Phase 3: Quantization for Inference

### GGUF Conversion Pipeline
```bash
# After training, convert merged model to GGUF
pip install llama-cpp-python

# Convert to F16 (intermediate)
python -m llama_cpp.convert \
  D:\afs_training\models\afs_scawful_TIMESTAMP\merged_model \
  --outtype f16 \
  --outfile afs_scawful_f16.gguf

# Quantize to various sizes
llama-quantize afs_scawful_f16.gguf afs_scawful_q4_k_m.gguf Q4_K_M
llama-quantize afs_scawful_f16.gguf afs_scawful_q5_k_m.gguf Q5_K_M
llama-quantize afs_scawful_f16.gguf afs_scawful_q8_0.gguf Q8_0
```

### Quantization Levels
| Quant | Size (1.5B) | Quality | Speed | Use Case |
|-------|-------------|---------|-------|----------|
| Q4_K_M | ~1GB | Good | Fastest | Mac M1 inference |
| Q5_K_M | ~1.2GB | Better | Fast | Balance |
| Q8_0 | ~1.6GB | Best | Slower | When quality matters |
| F16 | ~3GB | Perfect | Slowest | Evaluation only |

### Local Inference Setup
```bash
# Mac (ollama)
ollama create afs_scawful -f Modelfile
ollama run afs_scawful "Explain: LDA $0E20,X"

# Windows (llama.cpp)
./main -m afs_scawful_q4_k_m.gguf -p "### Instruction:\nExplain this routine..."
```

## Phase 4: Evaluation Framework

### ASM-Specific Benchmarks
Create eval set of tasks:
1. **Syntax validity**: Does output assemble?
2. **Semantic accuracy**: Does it run correctly?
3. **Optimization quality**: Cycle count, memory usage
4. **Explanation clarity**: Human eval

### Automated Testing
```python
def eval_asm_output(model_output: str) -> dict:
    """Evaluate ASM generation quality."""
    # 1. Extract code blocks
    code = extract_asm_code(model_output)

    # 2. Assemble with ASAR
    success, errors = asar_assemble(code)

    # 3. Compare cycles if reference exists
    cycle_diff = compare_cycles(code, reference)

    return {
        "assembles": success,
        "errors": errors,
        "cycle_diff": cycle_diff,
    }
```

## Immediate Next Steps

1. [ ] Create 500+ high-quality chain-of-thought ASM examples
2. [ ] Build automated ASAR validation into training pipeline
3. [ ] Set up eval framework before 7B training
4. [ ] Create GGUF conversion script
5. [ ] Test inference on Mac M1 Pro
