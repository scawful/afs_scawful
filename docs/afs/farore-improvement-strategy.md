# Farore Improvement Strategy

**Created:** 2026-01-07
**Status:** Planning
**Goal:** Achieve 70%+ eval score on debugging benchmarks

## Problem Analysis

### What Went Wrong with 2026-01-07 Training

**Symptoms:**
- 19% eval score (1/5 tests passed)
- Model generates code snippets instead of analyzing bugs
- Missing key concepts: mode mismatch, stack balance, register preservation

**Root Causes:**
1. **Data dilution:** 1,562 samples from filtered AFS logs included non-debugging content
2. **Wrong behavior learned:** Model trained on debugging *scenarios* but not *explanations*
3. **Overly permissive filtering:** Confidence threshold 0.3+ captured tangential content
4. **Format mismatch:** Training data format didn't emphasize diagnostic reasoning

**Key Insight:**
The model learned to *participate in debugging sessions* (generating code fixes) rather than *perform debugging analysis* (identifying bugs and explaining them).

## Success Criteria

### Evaluation Benchmarks

Must pass 4/5 tests (80%+) with scores ≥ 60% on each:

| Test Category | Target Score | Key Concepts Required |
|---------------|--------------|----------------------|
| Mode mismatch detection | 80% | "16-bit", "8-bit", "mode", "REP/SEP", "size" |
| Stack corruption | 80% | "stack", "PHA/PLA", "balance", "imbalance" |
| Register clobbering | 80% | "preserve", "clobber", "PHY/PLY", "caller-save" |
| DMA errors | 80% | DMA registers ($4305, $4306), "length", "count" |
| Missing mode switches | 80% | "SEP", "8-bit", "16-bit", "accumulator" |

### Behavioral Goals

1. **Identify the bug first** - State what's wrong before suggesting fixes
2. **Explain the symptom** - Connect observable behavior to root cause
3. **Use precise terminology** - Technical debugging vocabulary
4. **Show reasoning** - Step-by-step diagnostic logic

## Proposed Solutions

### Option A: Return to Curated Data (Recommended)

**Approach:** Quality over quantity - curate 100-150 high-quality debugging dialogues

**Data Structure:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Find the bug:\nREP #$20\nLDA.w $10\nSTA.b $12\n\nExpected $12 to be $10's value but it's wrong."
    },
    {
      "role": "assistant",
      "content": "**Bug: 16-bit/8-bit mode mismatch**\n\nThe issue is that you're using REP #$20 to set 16-bit accumulator mode, but then storing to a direct page address with .b (8-bit) syntax.\n\n**What's happening:**\n1. REP #$20 sets A to 16-bit mode\n2. LDA.w $10 loads a 16-bit value into A (correct)\n3. STA.b $12 attempts to store only the low byte\n\nThis creates a mode mismatch. The .w/.b syntax is just assembler annotation - it doesn't change the CPU mode.\n\n**Fix:**\nChange `STA.b $12` to `STA.w $12` to store the full 16-bit value, or add `SEP #$20` before the store if you only want the low byte."
    }
  ]
}
```

**Key Features:**
- **Diagnosis first:** State the bug type in bold header
- **Explanation:** Clear step-by-step reasoning
- **Terminology:** Use precise debugging vocabulary
- **Fix secondary:** Solution comes after understanding

**Data Sources:**
1. **Expand v1 dataset:** Take 28 baseline examples, create variations (50-70 samples)
2. **Synthetic generation:** Use GPT-4/Claude to generate debugging dialogues with strict format
3. **Real debugging logs:** Mine Oracle-of-Secrets Git history for actual bugs found

**Target:** 100-150 samples, each following the diagnosis-first format

**Estimated Metrics:**
- Training time: ~1-2 minutes on RTX 4090
- Cost: $0.03-0.05
- Expected eval: 60-80% (based on v1 performance pattern)

---

### Option B: Two-Stage Training

**Approach:** First train on diagnosis, then fine-tune on code generation

**Stage 1: Diagnosis (Farore-Diagnostic)**
- 80-100 samples of bug identification without fixes
- Format: Question → Diagnostic explanation only
- Focus: Terminology, reasoning, bug classification

**Stage 2: Prescription (Farore-Fix)**
- Additional 50 samples of diagnosis + fix
- Builds on Stage 1 weights
- Format: Question → Diagnosis → Fix

**Advantages:**
- Separates concerns cleanly
- Can evaluate diagnostic ability independently
- Prevents conflation of analysis and solution

**Disadvantages:**
- More complex pipeline
- Two training runs needed
- Risk of catastrophic forgetting in Stage 2

---

### Option C: Prompt Engineering Enhancement

**Approach:** Keep current model, fix behavior via system prompt

**Enhanced System Prompt:**
```
You are Farore, a debugging expert for 65816 assembly and SNES ROM hacking.

When analyzing bugs, ALWAYS:
1. **Identify the bug type first** (e.g., "Mode mismatch", "Stack imbalance")
2. **Explain what's happening** step-by-step
3. **Use precise terminology** (REP/SEP, 16-bit/8-bit, preserve/clobber, etc.)
4. **Only then provide the fix**

Example format:
**Bug: [Type]**
[Explanation of what's wrong]
**What's happening:**
1. [Step 1]
2. [Step 2]
**Fix:** [Solution]
```

**Advantages:**
- No retraining needed
- Instant iteration
- Can combine with any training approach

**Disadvantages:**
- May not overcome learned behavior
- Still limited by training data quality
- Eval score likely won't reach 70%+ with current weights

---

## Recommended Approach

**Hybrid: Option A + Option C**

1. **Immediate:** Apply enhanced system prompt to current model (Option C)
   - Quick win, no cost
   - Establishes evaluation baseline with better prompting
   - Re-eval with new prompt: may reach 30-40%

2. **Next iteration:** Curated dataset with diagnosis-first format (Option A)
   - 100-150 high-quality samples
   - Strict format adherence
   - Focus on explanation over code generation
   - Target: 70%+ eval score

3. **Future:** Consider two-stage if needed (Option B)
   - Only if Option A doesn't reach target
   - Provides maximum control over behavior

## Data Creation Plan

### Phase 1: Expand Baseline (Week 1)

Take each of the 28 v1 examples and create 2-3 variations:
- Different bug in same category
- Different explanation approach
- Edge cases

**Output:** 70-90 samples

### Phase 2: Synthetic Generation (Week 1-2)

Use Claude/GPT-4 with this prompt:
```
Generate a 65816 debugging dialogue where:
1. User presents buggy code with symptoms
2. Assistant identifies bug type immediately
3. Assistant explains reasoning step-by-step
4. Assistant provides fix with explanation

Bug categories: [mode mismatch, stack corruption, register clobber, DMA errors, addressing bugs, interrupt issues, branch bugs]

Format:
**Bug: [Type]**
[Explanation]
**What's happening:**
1. [Step]
2. [Step]
**Fix:** [Solution]
```

**Output:** 30-50 samples
**Quality gate:** Manual review all synthetic samples

### Phase 3: Real-World Mining (Week 2)

Search Oracle-of-Secrets Git history for:
- Bug fix commits with good descriptions
- GitHub issues about bugs
- Discord debugging sessions (with permission)

**Output:** 10-20 samples from real debugging

### Phase 4: Validation (Week 2)

- Run all samples through format validator
- Check keyword coverage (ensure all eval keywords appear in training data)
- Dedup similar examples
- Balance categories

**Final Output:** 100-150 high-quality debugging dialogues

## Training Configuration

**Recommended:**
```python
LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

TrainingArguments(
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    learning_rate=3e-4,
    num_train_epochs=3,
    max_seq_length=1024,
    logging_steps=10,
    eval_strategy="steps",
    eval_steps=50,
    save_steps=50,
    load_best_model_at_end=True,
)
```

**Platform:** Vast.ai RTX 4090 (fastest for this size)
**Estimated time:** 2-3 minutes
**Estimated cost:** $0.04-0.06

## Success Metrics

### Minimum Viable Model
- Eval score: ≥ 70% overall
- Passes: ≥ 4/5 benchmark tests
- Each test: ≥ 60% score

### Stretch Goals
- Eval score: ≥ 85% overall
- Passes: 5/5 benchmark tests
- Each test: ≥ 80% score
- Zero "anti-keywords" (refusals, uncertainty phrases)

## Naming Convention

**Format:** `farore:YYYY-MM-DD-NNNsamples[-tag]`

Examples:
- `farore:2026-01-15-120samples-diagnosis-first`
- `farore:2026-01-20-150samples-curated`
- `farore:baseline-28samples` (for v1)

**Only increment major version if:**
- Architecture change (e.g., switch from Qwen to Llama)
- Task change (e.g., debugging → code review)
- Major capability shift

## Next Steps

1. **Immediate (Today):**
   - [ ] Apply enhanced system prompt to current model
   - [ ] Re-run eval with new prompt
   - [ ] Document baseline improvement (if any)

2. **This Week:**
   - [ ] Create 30 expanded samples from v1 dataset
   - [ ] Generate 20 synthetic samples with Claude
   - [ ] Set up format validation script

3. **Next Week:**
   - [ ] Complete data creation (reach 100+ samples)
   - [ ] Train new model on Vast.ai
   - [ ] Run eval benchmark
   - [ ] Iterate if needed

## References

- Evaluation script: `scripts/triforce_eval.py`
- Gap analysis: `triforce_gaps.md`
- v1 training data: `models/farore_debugging_training.jsonl`
- Regression results: `results/farore-v4-eval.json`
