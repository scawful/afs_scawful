# AFS Model Naming Convention

## Oracle Series

Models are named after characters from *The Legend of Zelda: Oracle of Ages/Seasons*, reflecting their role as "oracles" of code understanding and generation.

### The Goddess Trio (Core Models)

| Name | Deity | Domain | Model Role |
|------|-------|--------|------------|
| **Nayru** | Goddess of Wisdom | Knowledge, understanding | Explanation, analysis, documentation |
| **Din** | Goddess of Power | Strength, transformation | Generation, optimization, refactoring |
| **Farore** | Goddess of Courage | Exploration, discovery | Autocomplete, FIM, quick inference |

### Extended Oracle Characters

| Name | Character | Model Role |
|------|-----------|------------|
| **Veran** | Sorceress of Shadows (Ages) | Complex analysis, large context |
| **Onox** | General of Darkness (Seasons) | Aggressive optimization |
| **Ralph** | Nayru's protector | Validation, error checking |
| **Maple** | Witch's apprentice | Fast helper, small tasks |
| **Impa** | Sage, Zelda's guardian | Security review, best practices |

### Ensemble/MoE Names

| Name | Reference | Use |
|------|-----------|-----|
| **Linked Game** | Oracle game mechanic | Combined Nayru + Din models |
| **Twinrova** | Twin witches (merged) | MoE ensemble |
| **Essence** | Collected essences | Distilled/quantized models |

---

## Naming Format

```
{character}-{size}-v{version}[-{variant}]
```

### Examples
- `nayru-7b-v1` - First 7B wisdom model
- `din-7b-v1-opt` - 7B power model, optimization variant
- `farore-1.5b-v1-fim` - 1.5B courage model, FIM variant
- `veran-14b-v1` - 14B large context model
- `linked-moe-v1` - MoE ensemble

---

## Current Model Registry

### Production Models

| Oracle Name | Technical Name | Base | Size | Status |
|-------------|----------------|------|------|--------|
| `nayru-7b-v1` | qwen-7b-asm-v4-merged | Qwen2.5-Coder-7B | 15GB | **Production** |
| `farore-1.5b-v1` | autocomplete-fim | Qwen2.5-Coder-1.5B | ~3GB | Testing |

### LoRA Adapters (Unmerged)

| Oracle Name | Technical Name | Base | Size | Status |
|-------------|----------------|------|------|--------|
| `nayru-7b-v1-lora` | 7b_asm_v4_lora | Qwen2.5-Coder-7B | 154MB | Archived |
| `veran-14b-v1-lora` | 14b_asm_v3_lora | Qwen2.5-Coder-14B | 263MB | Available |

### Planned Models

| Oracle Name | Base | Purpose | Priority |
|-------------|------|---------|----------|
| `nayru-16b-v1` | DeepSeek-Coder-V2-Lite | 128K context, MoE | High |
| `din-7b-v1` | Qwen2.5-Coder-7B | Optimization focus | Medium |
| `linked-moe-v1` | DeepSeek-Coder-V2-Lite | Nayru + Din ensemble | Future |

---

## Base Model Strategy

### Current: Qwen2.5-Coder

| Variant | Params | Active | Context | VRAM (QLoRA) |
|---------|--------|--------|---------|--------------|
| 0.5B | 0.5B | 0.5B | 32K | 4GB |
| 1.5B | 1.5B | 1.5B | 32K | 6GB |
| 3B | 3B | 3B | 32K | 8GB |
| 7B | 7B | 7B | 32K | 16GB |
| 14B | 14B | 14B | 32K | 24GB |
| 32B | 32B | 32B | 32K | 48GB |

### Future: DeepSeek-Coder-V2 (MoE)

| Variant | Total Params | Active Params | Context | VRAM (BF16) |
|---------|--------------|---------------|---------|-------------|
| Lite (16B) | 16B | 2.4B | 128K | 40GB |
| Full (236B) | 236B | 21B | 128K | 8x80GB |

**Why DeepSeek-Coder-V2:**
- Native MoE architecture (efficient inference)
- 128K context (4x Qwen)
- 338 programming languages
- Multi-head Latent Attention (MLA)
- Only 2.4B active params in Lite = fast inference

---

## Quantization Naming

Append quantization level to model name:

| Suffix | Format | Size Reduction | Quality |
|--------|--------|----------------|---------|
| `-f16` | Float16 | 1x | Perfect |
| `-q8` | INT8 | 0.5x | Excellent |
| `-q5km` | Q5_K_M | 0.35x | Great |
| `-q4km` | Q4_K_M | 0.25x | Good |
| `-q4ks` | Q4_K_S | 0.22x | Acceptable |

**Examples:**
- `nayru-7b-v1-q4km.gguf` - Quantized for Ollama
- `farore-1.5b-v1-q8.gguf` - High quality small model

---

## Training Data Domains

Models are trained on domain-specific data:

| Suffix | Domain | Data Source |
|--------|--------|-------------|
| `-asm` | 65816 Assembly | ALTTP disassembly, SNES docs |
| `-cpp` | C++ | Emulator code, game engines |
| `-lsp` | LSP/Autocomplete | Code completion pairs |
| `-fim` | Fill-in-Middle | Infilling training |

**Examples:**
- `nayru-7b-v1-asm` - ASM specialist (current)
- `din-7b-v1-cpp` - C++ optimization specialist

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-01-01 | Initial Oracle naming scheme |
