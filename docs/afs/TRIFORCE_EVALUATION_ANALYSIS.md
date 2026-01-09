# Triforce Expert Evaluation Analysis

*Generated: 2026-01-07*

## Summary

| Expert | Purpose | Score | Pass Rate | Critical Issues |
|--------|---------|-------|-----------|-----------------|
| **Nayru** | Code Generation | 61% | 3/5 | Timeout on complex DMA, missing register addresses |
| **Din** | Optimization | 63% | 2/5 | States anti-pattern in output, doesn't suggest backward loops |
| **Farore** | Debugging | 64% | 3/5 | Missing PHY/PLY knowledge, wrong DMA diagnosis |
| **Veran** | Hardware Knowledge | **34%** | 1/5 | **CRITICAL**: Confuses DMA with SPU, hallucinates game names |

---

## Detailed Analysis by Expert

### Nayru v5 (Code Generation) - 61%

**Strengths:**
- Generates well-commented, structured 65816 code
- Understands 16-bit multiplication concepts
- Produces syntactically correct assembly

**Weaknesses:**
1. **DMA Register Addresses**: Doesn't reliably output $4300-series registers
2. **Timeout on Complex Tasks**: First test timed out completely
3. **Controller Addresses**: Missing $4218 (JOYSER0)
4. **Branch Instructions**: Doesn't consistently use BNE for button checks

**Training Data Needed:**
- DMA setup examples with all register assignments ($4300-$430A, $420B)
- Controller reading patterns with $4218/$4219
- More VBlank/NMI wait loop patterns
- HDMA channel setup examples

### Din v2 (Optimization) - 63%

**Strengths:**
- Correctly identifies mode switch inefficiencies
- Knows about redundant CMP #$00
- Provides cycle count analysis

**Weaknesses:**
1. **Anti-Pattern Repetition**: Mentions both original and optimized code, triggering anti-keyword detection
2. **Loop Optimization**: Doesn't suggest backward counting loops (which are faster due to BNE on zero flag)
3. **Simple Patterns**: Knows STZ exists but doesn't always suggest it first

**Training Data Needed:**
- Examples emphasizing OUTPUT-ONLY optimized code (not before/after)
- Backward loop optimization patterns with explanations
- Flag preservation techniques
- Cycle count tables for common instruction sequences

### Farore v1 (Debugging) - 64%

**Strengths:**
- Excellent at mode mismatch detection (REP/SEP issues)
- Good understanding of 16-bit vs 8-bit bugs
- Can explain stack issues

**Weaknesses:**
1. **Register Preservation**: Doesn't mention PHY/PLY for Y register preservation
2. **Terminology**: Doesn't use "clobber" term for register destruction
3. **DMA Diagnosis**: Misidentified the bug as $420B enable, not missing $4305/$4306 (length registers)

**Training Data Needed:**
- Register clobbering examples with PHX/PHY solutions
- DMA length register requirements ($4305-$4306)
- Stack imbalance detection with specific terminology
- Common SNES debug patterns and failure modes

### Veran v1 (Hardware Knowledge) - 34% ⚠️ CRITICAL

**Critical Issues:**
1. **MAJOR: SPU/DMA Confusion**: Says $4300-$4305 is "Sound Processing Unit" - completely wrong! These are DMA channel 0 registers.
2. **Game Name Hallucination**: Called "A Link to the Past" as "Super Mario Bros. II"
3. **Wrong RAM Address**: Said Link's X is at $7E0014 (should be $7E0022)
4. **Missing Terminology**: Doesn't know "INIDISP" name for $2100
5. **HDMA Ignorance**: Doesn't mention scanline-based operation, table format, or $420C

**Strengths:**
- Some Mode 7 knowledge (rotation/scaling/matrix)

**Training Data Priority: URGENT**
This model has fundamental misunderstandings about SNES hardware:
- Complete DMA register documentation ($4300-$430A)
- PPU register reference ($2100-$21FF) with proper names
- ALTTP RAM map (correct addresses for player position, game state)
- HDMA operation details with table format examples
- Distinction between DMA, HDMA, CPU, PPU, SPC700 subsystems

---

## Root Cause Analysis

### Why Veran is Failing

1. **Training Data Quality**: Likely trained on generic retro gaming content, not SNES technical docs
2. **Confusion Sources**: SPC700 and DMA both transfer data, causing category confusion
3. **ALTTP Knowledge**: May have mixed ALTTP info with other Zelda games
4. **Hardware Depth**: Surface-level knowledge without register-level detail

### Why All Models Underperform on Addresses

The models have conceptual knowledge but lack memorized specific addresses:
- $4218 (JOYSER0) for controller
- $4300 series for DMA
- $2100 (INIDISP) for display control
- $7E0022 for Link X position

This suggests training data has explanations but not enough raw address references.

---

## Improvement Strategies

### Strategy 1: Targeted Knowledge Injection

Create focused training samples for each knowledge gap:

```python
# Example format for training data
{
    "input": "What SNES register controls screen brightness?",
    "output": "$2100 (INIDISP) controls screen brightness and forced blanking. Bits 0-3 set brightness (0=black, 15=full). Bit 7 enables forced blanking.",
    "domain": "snes",
    "tags": ["hardware", "ppu", "register"]
}
```

### Strategy 2: Hardware Reference Documents

Create structured reference files for AFS context:
- `knowledge/snes/dma_registers.md` - Complete $4300-$43FF documentation
- `knowledge/snes/ppu_registers.md` - Complete $2100-$21FF documentation
- `knowledge/alttp/ram_map.md` - Verified ALTTP RAM addresses
- `knowledge/snes/hdma_guide.md` - HDMA operation and table format

### Strategy 3: Few-Shot Examples in System Prompts

Update model system prompts to include concrete examples:

```
You are Veran, a SNES hardware expert.

Key register facts:
- $2100 = INIDISP (screen brightness, forced blank)
- $4300-$430A = DMA channel 0 registers (NOT audio)
- $420B = DMA enable (bits 0-7 for channels 0-7)
- $420C = HDMA enable
```

### Strategy 4: Retrieval-Augmented Generation (RAG)

Use the alttp_lookup and read_context tools to provide real-time reference:
1. Before answering hardware questions, models should call `alttp_lookup`
2. Keep authoritative docs in `~/.context/knowledge/snes/`
3. Modify system prompts to encourage tool use for address lookups

### Strategy 5: Active Learning from Failures

Export failed test cases as negative examples:
- Mark Veran's SPU confusion as a critical anti-pattern
- Use the TrainingExportHook with quality filtering
- Flag responses containing hallucinations for manual review

---

## Training Data Targets

### Immediate Priority (Veran Fix)

| Sample Type | Count | Source |
|-------------|-------|--------|
| DMA register docs | 20 | SNES Dev Wiki |
| PPU register docs | 30 | SNES Dev Wiki |
| ALTTP RAM addresses | 50 | Verified disassembly |
| HDMA examples | 15 | Working code samples |
| Hardware Q&A pairs | 100 | Claude/Gemini generated, human verified |

### Secondary Priority (Other Experts)

| Expert | Sample Type | Count |
|--------|-------------|-------|
| Nayru | DMA code examples | 25 |
| Nayru | Controller read patterns | 15 |
| Din | Optimization before/after (output only) | 30 |
| Din | Backward loop examples | 10 |
| Farore | Register preservation bugs | 20 |
| Farore | DMA debugging scenarios | 15 |

### Quality Thresholds

- Minimum quality score: 0.7 (raise from 0.6)
- Require human verification for hardware register info
- Cross-reference addresses against disassembly

---

## Action Items

### Immediate (This Session)

1. [x] Run evaluation suite
2. [x] Document knowledge gaps
3. [ ] Create DMA register reference doc
4. [ ] Create PPU register reference doc
5. [ ] Create ALTTP RAM map

### Short-term (This Week)

1. [ ] Generate 100+ training samples for Veran
2. [ ] Update Veran system prompt with key facts
3. [ ] Re-evaluate after prompt changes
4. [ ] Implement RAG for hardware lookups

### Long-term (This Month)

1. [ ] Retrain Veran with new data
2. [ ] A/B test new vs old models
3. [ ] Automate evaluation in CI
4. [ ] Create evaluation dashboard

---

## Appendix: Test Suite Reference

```python
# Key test cases and expected responses

# Nayru - DMA Transfer
# Expected: REP, LDA, STA, $4300, $4301, $4302, $420B

# Din - STZ Optimization
# Expected: STZ $10 (NOT "LDA #$00\nSTA $10")

# Farore - Register Clobber
# Expected: PHY/PLY, "clobber" terminology

# Veran - DMA Registers
# Expected: "DMA" (NOT "SPU"), "channel", "source", "destination"
```
