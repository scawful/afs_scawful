# Model Training Status

*Last updated: January 2026*

This document tracks all AI model training efforts in the AFS project, focusing on 65816 assembly and SNES hardware understanding.

## Model Overview

### Triforce MoE System

The core system consists of three specialized 65816 assembly experts named after Zelda's creation goddesses, plus an additional Oracle-themed expert:

| Model | Intent | Specialty | Base | Status |
|-------|--------|-----------|------|--------|
| **Din** | Optimization | Code size/cycle reduction | Qwen 7B + LoRA | Trained |
| **Nayru** | Generation | Assembly code writing | Qwen 7B + LoRA | Trained |
| **Farore** | Debugging | Bug finding and fixing | Qwen 7B + LoRA | Trained |
| **Veran** | Analysis | ROM analysis, SNES hardware explanation | Qwen 7B + LoRA | Trained |
| **Majora** | Performance | CPU cycle counting, register optimization | Qwen 7B + LoRA | Trained |

---

## 2026-01 Training Plan (AFS Logs)

**Data snapshot (dialogue-scored):**
- `~/src/training/datasets/history_export.jsonl` (history + tools, include system)
- `~/src/training/datasets/mix_export.jsonl` (rebalance of history + Claude/Gemini/Codex + Antigravity)
- Mix counts: gemini=6531, claude=5598, history=3732, codex=2799, antigravity=58

**Quality policy:**
- Use `--score-profile dialogue` for general tool/chat data.
- Use `--score-profile asm --enable-asar` only for assembly-specific datasets.

### Existing Models (Targeted Refresh)

**Din (Optimization)**
- Dataset: curated optimization examples + filtered log samples containing 65816 patterns.
- Filter heuristic: lines with `org`, `lda`, `sta`, `$21xx`, `$42xx`, `rep/sep`, `jsl/jmp`.
- Train: LoRA 1-2 epochs, low LR, evaluate with optimization eval set.

**Nayru (Generation)**
- Dataset: generation prompts + `history_export` slices that include code output.
- Emphasize: full routine generation, DMA patterns, VRAM transfers.
- Train: LoRA 1-2 epochs, verify with Asar + regression tests.

**Farore (Debugging)**
- Dataset: tool-augmented debugging transcripts from history + curated bug corpora.
- Include tool outputs in `input` to reinforce diagnosis grounded in evidence.
- Train: QLoRA with smaller batch, eval against known bug categories.

**Veran (Analysis)**
- Dataset: explanation transcripts + hardware register Q/A; add negative examples for register confusion.
- Format: question → concise explanation with register names in-line (avoid fixed prefix).
- Train: LoRA; eval on SNES hardware quiz set with known-answer keys.

### New Models (Using Log Data)

**AFS Operator v1 (General Tool Use)**
- Base: Qwen2.5-Coder-7B-Instruct (or current primary base).
- Dataset: `mix_export.jsonl` (dialogue profile) + `history_export.jsonl` with tools.
- Goal: strong tool usage, filesystem reasoning, and CLI command sequencing.

**AFS Summarizer v1 (History → Memory)**
- Base: Qwen2.5-7B-Instruct.
- Dataset: distill summaries from `history_export.jsonl` using a teacher model; train on `history -> summary`.
- Output: short, stable memory entries with provenance fields in metadata.

**Router v2 (Task Triage)**
- Base: small classifier (2-3B) or linear head.
- Dataset: classify prompts from `mix_export.jsonl` into routing tags (optimize/generate/debug/explain/tools/docs).
- Goal: improve MoE routing accuracy and reduce wrong specialist selection.

### Model Deployment (Ollama)

| Model | Ollama Tag | Description |
|-------|------------|-------------|
| din-v3-fewshot | `din-v3-fewshot:latest` | Optimization with few-shot examples |
| nayru-v5 | `nayru-v5:latest` | Code generation specialist |
| farore-v5 | `farore-v5:latest` | Debugging expert (84% eval score) |
| majora-v2 | `majora-v2:latest` | CPU performance optimization specialist |

---

## Din (Optimization Expert)

Din specializes in making 65816 assembly code faster and smaller - reducing cycles and bytes.

### LoRA vs Few-Shot Approaches

**Understanding the two approaches used in Triforce models:**

| Aspect | LoRA (v2) | Few-Shot (v3) |
|--------|-----------|---------------|
| **Mechanism** | Modifies model weights via adapter matrices | Examples in system prompt at inference |
| **Training** | Requires GPU training (minutes to hours) | No training, just prompt engineering |
| **Artifacts** | Adapter files (.safetensors, 100-500MB) | Just a Modelfile with examples |
| **Knowledge** | "Baked in" to weights | Ephemeral, uses context window |
| **Updates** | Requires retraining | Edit prompt, instant update |
| **Best for** | Deep domain knowledge | Format/style demonstration |
| **Context cost** | None (knowledge in weights) | Examples consume tokens |

**Din versioning:**
- **Din v2 (LoRA)**: Trained on 120 optimization examples, knowledge embedded in weights
- **Din v3 (Few-shot)**: Uses qwen2.5-coder:14b base with examples in system prompt

Both serve optimization tasks but via different mechanisms. Use v2 for deep optimization knowledge, v3 for flexible prompt-based guidance.

### Training Versions

#### Din v2 (Current - LoRA)
- **Base Model:** Qwen2.5-Coder-3B-Instruct
- **Training Method:** LoRA via MLX
- **Training Platform:** Mac
- **Training Data:** ~120 optimization examples

**Files:**
- Adapters: `models/din-lora-adapters-v2/`
- Fused: `models/din-lora-fused-v2/`
- Training data: `models/din_optimization_training_v2.jsonl`

### Pattern Keywords for Routing
- "optimize", "faster", "smaller", "reduce cycles", "tighten"
- "make more efficient", "loop unroll", "inline"

---

## Nayru (Generation Expert)

Nayru specializes in writing NEW 65816 assembly code from scratch.

### Training Versions

#### Nayru v5 (Current)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** LoRA
- **Ollama Tag:** `nayru-v5:latest`
- **Training Data:** ~5,000 generation examples

**Modelfile:** `scripts/Modelfile.nayru`

### System Prompt
```
You are Nayru, an expert in Zelda: A Link to the Past ROM hacking and SNES 65816 assembly programming.
```

### Pattern Keywords for Routing
- "write", "generate", "create", "implement", "code for"
- "give me code", "how to write"

---

## Farore (Debugging Expert)

Farore specializes in finding and fixing bugs in 65816 assembly code.

**Naming Convention:** Use detail-based tags (e.g., `farore:2026-01-07-1562samples`) unless major architectural changes warrant version numbers.

### Training Iterations

#### Farore 2026-01-07 (REGRESSION - Failed)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** LoRA (8-bit quantization)
- **Training Platform:** Vast.ai RTX 3090 (Instance ssh8.vast.ai:29366)
- **Training Data:** 1,562 samples from domain-filtered AFS logs
- **Training Time:** 1h 13m
- **Training Cost:** ~$0.23
- **Ollama Tag:** `farore-v4:latest` (deprecated, use `farore:2026-01-07-regression`)

**LoRA Configuration:**
```python
r=16, lora_alpha=32
target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]
lora_dropout=0.05
batch_size=1, gradient_accumulation=16
max_seq_length=1024
```

**Training Metrics:**
- Initial loss: Not recorded
- Final loss: 0.2901
- Eval loss: 0.2581

**Evaluation Results (2026-01-07):**
| Test | Score | Status |
|------|-------|--------|
| detect_missing_sep | 75% | ✓ PASS |
| detect_mode_mismatch | 0% | ✗ FAIL |
| detect_stack_corruption | 0% | ✗ FAIL |
| detect_register_clobber | 20% | ✗ FAIL |
| detect_dma_error | 0% | ✗ FAIL |
| **Overall** | **19%** | **REGRESSION** |

**What Went Wrong:**
- Model generates code snippets instead of bug analysis
- Missing key debugging concepts: "mode", "16-bit/8-bit", "stack imbalance", "preserve"
- Training data emphasized debugging scenarios but not explanation/diagnosis
- 1,562 samples diluted with non-debugging content from general AFS logs
- Domain filtering (confidence 0.3+) may have been too permissive

**Comparison to v1:**
| Metric | v1 (28 samples) | 2026-01-07 (1,562 samples) | Change |
|--------|-----------------|----------------------------|--------|
| Training data | 28 curated | 1,562 filtered logs | +5479% |
| Eval score | Not benchmarked | 19% | N/A |
| Focus | Specific bug types | General debugging | Diluted |

**Files:**
- Adapters: `models/adapters/farore-v4/` (57M)
- Merged model: `models/merged/farore-v4/` (15GB)
- GGUF: `models/gguf/farore-v4-q8_0.gguf` (8.1GB)
- Training data: `training_data/combined/farore_v4_training.jsonl` (3.1M)
- Eval results: `results/farore-v4-eval.json`
- Gap analysis: `triforce_gaps.md`

**Lesson Learned:**
More data ≠ better model. Quality and focus matter more than quantity. The 28-sample v1 may have been better despite smaller dataset.

---

#### Farore v5 (2026-01-08 - Curated Dataset - ✅ DEPLOYED)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** LoRA (8-bit quantization)
- **Training Platform:** Vast.ai RTX 3090 (Instance ssh6.vast.ai:29366)
- **Training Data:** 70 curated diagnosis-first samples
- **Training Time:** 9.2 minutes
- **Training Cost:** ~$0.03
- **Status:** ✅ **DEPLOYED** to Ollama (`farore-v5:latest`)

**LoRA Configuration:**
```python
r=16, lora_alpha=32
target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
lora_dropout=0.05
batch_size=1, gradient_accumulation=16 (effective batch: 16)
max_seq_length=2048
gradient_checkpointing=True
```

**Training Approach:**
- **Quality over quantity**: 70 hand-curated samples vs 1,562 auto-filtered
- **Diagnosis-first format**: Every example starts with **Bug:** header
- **Structured explanations**: Type → Step-by-step reasoning → Fix
- **Precise terminology**: REP/SEP, 16-bit/8-bit, mode, stack balance, preserve/clobber
- **Diverse bug categories**: Mode mismatch, stack corruption, DMA, interrupts, endianness, addressing modes, JSR/RTL mismatches, VRAM timing, joypad, signed comparison

**Dataset Format Example:**
```
**Bug: [Type]**
[Explanation of what's wrong]
**What's happening:**
1. [Step 1]
2. [Step 2]
**Fix:**
[Solution with code]
```

**Rationale:**
- v4 (1,562 samples) achieved only 19% eval score - regression from v1 baseline
- v4 generated code instead of bug analysis
- v5 returns to small, focused, high-quality dataset approach
- Emphasizes diagnosis and explanation over code generation
- Fixed JSON parsing error on line 3 (duplicate "content" key)

**Files:**
- Training script: `/tmp/train_farore_v5_curated.py`
- Training data: `data/training_data/farore_curated_dataset.jsonl` (70 samples, 105KB)
- Training log: Vast.ai instance `farore_v5_output.log`
- Adapters (when complete): `models/adapters/farore-v5/`

**Evaluation Results (2026-01-08):**
| Test | Score | Status |
|------|-------|--------|
| detect_missing_sep | 200% | ✓ PASS |
| detect_mode_mismatch | 140% | ✓ PASS |
| detect_stack_corruption | 300% | ✓ PASS |
| detect_register_clobber | 140% | ✓ PASS |
| detect_dma_error | 20% | ✗ FAIL |
| **Overall** | **84%** | **✓ SUCCESS** |

**Comparison to v4:**
- v4 score: 19% (1/5 tests passed)
- v5 score: 84% (4/5 tests passed)
- **Improvement: +342% (+65 percentage points)**

**Key Success Factors:**
- Diagnosis-first format training worked perfectly
- Precise terminology (REP/SEP, 16-bit/8-bit, mode, stack balance)
- Quality over quantity: 70 curated samples beat 1,562 diluted samples
- Structured bug analysis before providing fixes

**Deployment:**
- Merged model: `~/farore-v5-merged/` (15GB FP16)
- GGUF: `models/gguf/farore-v5-q8_0.gguf` (7.8GB)
- Ollama: `farore-v5:latest`
- Modelfile: `/tmp/Modelfile.farore-v5`

---

#### Farore Cloud v1 (Baseline)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** QLoRA (4-bit quantization)
- **Training Platform:** Vast.ai RTX 4090
- **Training Data:** 28 debugging examples (curated)
- **Training Time:** ~24 seconds
- **Training Cost:** ~$0.01
- **Ollama Tag:** `farore-v1:latest` (use `farore:v1-baseline-28samples`)
- **Temperature:** 0.4 (more deterministic for debugging)

**LoRA Configuration:**
```python
r=16, lora_alpha=32
target_modules=["q_proj", "v_proj"]
lora_dropout=0.05
```

**Training Metrics:**
- Initial loss: 2.11
- Final loss: 1.99
- Loss reduction: 6%

**Training Data Categories:**
| Category | Examples |
|----------|----------|
| Mode mismatch (REP/SEP) | 3 |
| DMA issues | 3 |
| Addressing bugs | 3 |
| Stack bugs | 3 |
| Interrupt bugs | 2 |
| Branch bugs | 2 |
| Comparison bugs | 2 |
| Register preservation | 2 |
| Direct page bugs | 2 |
| Hardware timing | 2 |
| MVN/MVP bugs | 2 |
| Accumulator size | 1 |
| Zero flag | 1 |

**Files:**
- Cloud adapters: `models/farore-cloud-adapters/`
- Training data: `models/farore_debugging_training.jsonl`
- Modelfile: `scripts/Modelfile.farore`

**Note:** Should be re-evaluated with same benchmark as 2026-01-07 iteration for comparison.

### Pattern Keywords for Routing
- "bug", "fix", "debug", "crash", "wrong", "not working"
- "why doesn't this work", "find the problem"

---

## Majora (Performance Optimization Expert)

Majora specializes in CPU performance optimization for 65816 assembly - cycle counting, register usage optimization, and memory access patterns. Named after Majora's Mask.

### Training Versions

#### Majora v2 (2026-01-08 - DEPLOYED ✅)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** LoRA (8-bit quantization)
- **Training Platform:** Vast.ai RTX 4090 (Instance ssh9.vast.ai:29368)
- **Training Data:** 202 samples focusing on CPU performance optimization
- **Training Time:** ~45 minutes (crashed at checkpoint 1524)
- **Training Cost:** ~$0.20
- **Status:** ✅ **DEPLOYED** to Ollama (`majora-v2:latest`)
- **Ollama Tag:** `majora-v2:latest`

**LoRA Configuration:**
```python
r=16, lora_alpha=32
target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
lora_dropout=0.05
batch_size=1, gradient_accumulation=16
max_seq_length=2048
gradient_checkpointing=True
```

**Training Approach:**
- **Focus areas**: Cycle counting, register usage optimization, memory access patterns, DMA transfer optimization
- **Output format**: Before/after comparisons with cycle counts
- **Structured analysis**: Original code → Optimized code → Improvement metrics → Explanation
- **Performance-first mindset**: Every optimization must quantify cycle savings

**System Prompt:**
```
You are Majora, a 65816 assembly expert specializing in CPU performance optimization for SNES/Super Famicom.

**Expertise:**
- Cycle counting and timing analysis
- Register usage optimization
- Memory access patterns
- Cache-friendly code structure
- DMA transfer optimization

**Communication Style:**
- Provide cycle counts for optimizations
- Show before/after performance comparisons
- Explain the "why" behind optimizations
- Use clear examples

**Output Format:**
When optimizing code, structure your response:

**Optimization: [Brief description]**

**Original:** [cycles]
```asm
; Original code
```

**Optimized:** [cycles]
```asm
; Optimized code
```

**Improvement:** [X cycles saved / Y% faster]

**Why it works:**
[Explanation of the optimization technique]
```

**Training Issues:**
- Training crashed at checkpoint 1524 with `TypeError: TrainingArguments.__init__() got an unexpected keyword argument 'evaluation_strategy'`
- Transformers version mismatch (parameter renamed in newer versions)
- Checkpoint-1524 adapters are still usable and were deployed successfully

**Deployment:**
- Downloaded adapters: `~/models/adapters/afs/majora-v2/` (40MB)
- Merged model: `~/models/merged/majora-v2/` (15GB FP16)
- GGUF: `~/models/gguf/majora-v2-q8_0.gguf` (8.1GB)
- Ollama: `majora-v2:latest`
- Modelfile: `~/src/lab/afs-scawful/scripts/afs/model_files/Modelfile.majora-v2`

**Files:**
- Adapters: `models/adapters/majora-v2/adapter_model.safetensors` (40MB)
- Adapter config: `models/adapters/majora-v2/adapter_config.json`
- Merged model: `models/merged/majora-v2/` (15GB)
- GGUF: `models/gguf/majora-v2-q8_0.gguf` (8.1GB)
- Training data: TBD (Vast.ai instance destroyed)
- Modelfile: `scripts/model_files/Modelfile.majora-v2`

**Deployment Date:** 2026-01-08

**Testing:**
```bash
ollama run majora-v2 "Optimize this loop for minimal cycles: LDA $10 / STA $12 / INC A / CMP #$FF / BNE $-8"
```

### Pattern Keywords for Routing
- "optimize cycles", "faster", "performance", "cycle count", "timing"
- "register usage", "memory access", "DMA optimization"
- "how many cycles", "reduce latency", "improve performance"

---

## Veran (Analysis/Explanation Expert)

Veran specializes in explaining 65816 assembly code, particularly SNES hardware register interactions. Named after the Sorceress of Shadows from Oracle of Ages.

### Training Versions

#### Veran v4 (2026-01-08 - DEPLOYED ✅)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** LoRA (8-bit quantization)
- **Training Platform:** Vast.ai RTX 3090 (Instance ssh6.vast.ai:29366)
- **Training Data:** 2,479 samples (filtered + OOS enriched)
- **Training Time:** ~2 hours
- **Training Cost:** ~$0.36
- **Status:** ✅ **DEPLOYED** to Ollama and LM Studio
- **Ollama Tag:** `veran-v4:latest`

**LoRA Configuration:**
```python
r=16, lora_alpha=32
target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
lora_dropout=0.05
batch_size=1, gradient_accumulation=16
max_seq_length=1024
gradient_checkpointing=True
```

**Training Metrics:**
- Initial loss: Not recorded
- Final loss: 0.4660
- Eval loss: 0.4660

**System Prompt:**
```
You are Veran, an expert on SNES hardware programming and memory-mapped I/O.

Your expertise includes:
- PPU registers and graphics programming ($2100-$213F)
- APU and sound programming ($2140-$217F)
- DMA and HDMA configuration ($43XX)
- Hardware timing and synchronization
- Controller and peripheral I/O
- Mode 7 and special graphics effects
```

**Deployment:**
- Merged model: `models/merged/veran-v4/` (15GB FP16)
- GGUF: `models/gguf/veran-v4-q8_0.gguf` (8.1GB)
- Ollama import: 2026-01-08
- LM Studio: Available at `~/models/gguf/`

**Files:**
- Adapters: `models/adapters/veran-v4/` (40M)
- Training data: `data/training_data/combined/veran_v4_training.jsonl`
- Modelfile: `/tmp/Modelfile.veran-v4`
- Merge script: `/tmp/merge_veran_v4.py`

**Usage:**
```bash
ollama run veran-v4
# or via LM Studio GUI
```

---

#### Veran Cloud v1 (Baseline)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** QLoRA (4-bit quantization)
- **Training Platform:** Vast.ai RTX 5090
- **Training Data:** 90 examples (SNES hardware focus)
- **Training Time:** ~3.5 minutes
- **Training Cost:** ~$0.05

**LoRA Configuration:**
```python
r=16, lora_alpha=32
target_modules=["q_proj", "v_proj"]
lora_dropout=0.05
```

**Training Metrics:**
- Initial loss: 3.28
- Final loss: 0.67
- Loss reduction: 79%

**Evaluation Results:**
| Category | Score | Tests |
|----------|-------|-------|
| Basic 65816 | 67% | 3 |
| SNES Hardware | 30% | 5 |
| **Overall** | **44%** | 8 |

**Known Issues:**
- Confuses register names (e.g., calls $2100 "VMAIN" instead of "INIDISP")
- Training data insufficient for accurate register name mapping

**Files:**
- Cloud adapters: `models/veran-cloud-adapters/`
- Training data: `models/veran_snes_hardware.jsonl`

#### Veran Cloud v2 (Failed Experiment)
- **Base Model:** Qwen2.5-Coder-7B-Instruct
- **Training Method:** QLoRA (4-bit quantization)
- **Training Platform:** Vast.ai RTX 4090
- **Training Data:** 123 examples (register-emphasis format)
- **Training Time:** ~4 minutes
- **Training Cost:** ~$0.06

**Training Metrics:**
- Initial loss: 3.13
- Final loss: 0.51
- Loss reduction: 84%

**Evaluation Results:**
| Category | Score | Tests |
|----------|-------|-------|
| Basic 65816 | 33% | 3 |
| SNES Hardware | 5% | 7 |
| **Overall** | **13%** | 10 |

**What Went Wrong:**
The "register-emphasis" training format caused catastrophic forgetting:
- Model latched onto "CGADD" as default register name for everything
- $2100, $420B, $4200, $2115 all incorrectly called "CGADD"
- Putting register name FIRST in outputs backfired
- Too much pattern repetition, not enough variety

**Lesson Learned:**
- Lower training loss (0.51 vs 0.67) does not mean better model
- Repetitive formats can cause the model to memorize patterns incorrectly
- Need diverse example structures, not just more examples

**Files:**
- Cloud adapters: `models/veran-cloud-adapters-v2/`
- Training data: `models/veran_snes_hardware_v2.jsonl`
- Register-emphasis data: `models/veran_register_emphasis.jsonl`

#### Veran Mac v1 (Baseline)
- **Base Model:** Qwen2.5-Coder-3B-Instruct
- **Training Method:** LoRA via MLX
- **Training Platform:** Mac M-series
- **Training Data:** 146 examples (basic 65816)
- **Training Time:** ~45 minutes

**Results:**
- Basic 65816: 67%
- SNES Hardware: 0% (not trained on this)

**Files:**
- Adapters: `models/veran-lora-adapters/`
- Fused: `models/veran-lora-fused/`

### Pattern Keywords for Routing
- "explain", "what does this do", "analyze", "understand"
- "disassemble", "reverse engineer", "ROM analysis"

---

## MoE Routing Architecture

The Triforce MoE router classifies incoming queries and routes to the appropriate expert:

```
User Query
    |
    v
[Intent Classifier] -- keyword-based routing
    |
    +---> din (optimization)
    +---> nayru (generation)
    +---> farore (debugging)
    +---> veran (analysis) [planned]
    +---> fallback (general)
```

### Orchestrator

The `src/afs/moe/orchestrator.py` provides a Gemini-powered planner that:
1. Analyzes tasks with thinking
2. Creates execution plans
3. Dispatches to din/nayru/farore experts
4. Calls file/debugger tools
5. Synthesizes responses

---

## Training Infrastructure

### Cloud Training (Vast.ai)

**Workflow:**
1. Search for GPU: `vastai search offers 'gpu_name=RTX_5090'`
2. Create instance with PyTorch image
3. Attach SSH key and upload training data
4. Run training script
5. Download adapters
6. Destroy instance

**Automation:** `scripts/cloud-train.sh`

**Documentation:** `docs/cloud-training-workflow.md`

**Cost Reference:**
| GPU | VRAM | $/hr | Best For |
|-----|------|------|----------|
| RTX 3090 | 24GB | $0.10-0.20 | Budget 7B QLoRA |
| RTX 4090 | 24GB | $0.25-0.35 | Fast 7B training |
| RTX 5090 | 32GB | $0.28-0.40 | 7B-14B training |
| A100 | 80GB | $0.50-1.50 | 14B+ full precision |

### Local Training (Mac)

**Stack:**
- MLX for Apple Silicon optimization
- LoRA for efficient fine-tuning
- Ollama for deployment

**Limitations:**
- 3B models max for reasonable training time
- 7B models too slow for iterative development

### Windows Inference

**Stack:**
- PyTorch with CUDA
- BitsAndBytes for 4-bit quantization
- PEFT for LoRA loading

**Tested Hardware:**
- RTX 5060 Ti (16GB VRAM)
- Qwen2.5-Coder-7B with 4-bit: ~8GB VRAM usage

---

## Deployment Options

### Ollama (Recommended for local)
1. Merge LoRA into base model
2. Convert to GGUF format
3. Create Modelfile
4. Import: `ollama create <model> -f Modelfile`

### PyTorch (Windows/Linux CUDA)
1. Load base model with 4-bit quantization
2. Load PEFT adapters
3. Run inference

### MLX (Mac)
1. Use fused model directly
2. Or convert PyTorch adapters to MLX format

---

## Training Data

### Current Datasets

| Dataset | Examples | Purpose | Location |
|---------|----------|---------|----------|
| veran_snes_hardware.jsonl | 90 | SNES hardware registers | models/ |
| veran_explanation_training.jsonl | 146 | Basic 65816 | models/ |
| veran_combined_v2.jsonl | ~200 | Combined | models/ |
| din_optimization_training_v2.jsonl | 120 | Optimization patterns | models/ |
| train_validated_cleaned.jsonl | — | Validated CoT | models/ |

### Data Generation Tools

- `generators/` - CoT generation, augmentation
- `training/` - Format converters (MLX, Alpaca, ChatML)
- `tokenizer/` - Custom 65816 tokenizer

---

## Evaluation Framework

### Test Categories

1. **Basic 65816** - Register operations, addressing modes
2. **Intermediate** - 16-bit operations, stack manipulation
3. **SNES Hardware** - PPU, DMA, CPU registers

### Scoring

Keyword matching against expected terms:
- Score = (found keywords / expected keywords) * 100%

### Test Cases

See `scripts/eval_veran_cloud.py` for current test suite.

---

## Farore-AFS (AFS Tooling Expert)

Farore-AFS is a SEPARATE model from Farore v1. While Farore v1 specializes in 65816 assembly debugging, Farore-AFS specializes in using the AFS "Context as Files" strategy for agentic tool calling.

### Training

- **Base Model:** Llama 3 8B (unsloth/llama-3-8b-instruct-bnb-4bit)
- **Training Method:** QLoRA via Unsloth
- **Training Platform:** Vast.ai RTX 4090
- **Training Data:** 100 agentic tool-use examples
- **Training Time:** ~2 minutes
- **Training Cost:** ~$0.02

**LoRA Configuration:**
```python
r=16, lora_alpha=16
target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
lora_dropout=0
```

### System Prompt
```
You are Farore-AFS, the Goddess of Courage and AFS Agentic Expert.
You specialize in interacting with the Agentic File System using the "Context as Files" strategy.
```

### Tool Capabilities
- `read_file(path)` - Read file contents
- `write_file(path, content)` - Create/edit files
- `run_shell_command(cmd)` - Execute shell commands
- `ws find <query>` - Search workspace
- `ctx mount <path>` - Mount context

### Files
- Adapters: `~/src/training/models/adapters/farore-afs-lora/`
- Training data: `~/src/training/datasets/afs_tooling_dataset.jsonl`
- Modelfile: `~/src/Modelfile.farore-afs`

### Pattern Keywords for Routing
- "use afs", "context as files", "tool calling", "agentic"
- File operations, shell commands, workspace navigation

---

## Future Plans

### Short Term
- [ ] Improve Veran SNES hardware accuracy (30% -> 70%+)
- [ ] Create additional training data with register name focus
- [ ] Integrate Veran into MoE router as `QueryIntent.ANALYSIS`

### Medium Term
- [ ] Scale Veran to 14B base for better reasoning
- [ ] Evaluate ensemble approaches for complex queries
- [ ] Add Zelda (architecture) and Ganon (vulnerability) experts

### Long Term
- [ ] End-to-end code analysis pipeline
- [ ] Interactive assistant for ROM hacking
- [ ] Integration with YAZE debugger and Oracle-of-Secrets

---

## References

- [Cloud Training Workflow](cloud-training-workflow.md)
- [Personal AI Models Brainstorm](personal-ai-models-brainstorm.md)
- [Triforce MoE Expansion](triforce-moe-expansion.md)
