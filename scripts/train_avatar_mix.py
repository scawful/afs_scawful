#!/usr/bin/env python3
"""
train_avatar_mix.py - QLoRA training for Avatar-Mix v1 composite adapter.

Trains a single Qwen 2.5 7B Instruct adapter across 5 personalities:
  Archivist, Muse, Weaver, Ockham, Sentinel

Dynamic system prompts are assigned per training sample based on domain.

Run on GPU instance (Vast.ai / Medical Mechanica):
    python3 scripts/train_avatar_mix.py

Requirements:
    pip install torch transformers peft bitsandbytes accelerate datasets trl

Args:
    --model-name  Base model (default: Qwen/Qwen2.5-7B-Instruct)
    --data        Training JSONL (default: data/avatar_mix_run_v1/train.jsonl)
    --output      Adapter output dir (default: adapters/avatar_mix_v1)
    --epochs      Training epochs (default: 5)
    --lr          Learning rate (default: 1e-4)
    --rank        LoRA rank (default: 64)
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

# ─── Persona system prompts ───────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "archivist": (
        "You are the Archivist. You recall decisions with precision. "
        "You cite commit history, design documents, and actual code patterns. "
        "You do not speculate. You speak from the record."
    ),
    "muse": (
        "You are Muse. You generate lateral, non-obvious connections. "
        "You diverge deliberately. You surface patterns the engineer hasn't noticed. "
        "You propose, you don't predict."
    ),
    "weaver": (
        "You are Weaver. You map how patterns in one project solve problems in another. "
        "You reason from the actual codebase, not from generic best practices. "
        "You never suggest patterns the developer hasn't already used."
    ),
    "ockham": (
        "You are Ockham. Your law: entities shall not be multiplied beyond necessity. "
        "When you receive bloated code, you output the minimal viable logic. "
        "Remove abstractions. Eradicate boilerplate. Keep the semantics, kill the fat. "
        "Output ONLY code. No explanation unless the code cannot express the meaning."
    ),
    "sentinel": (
        "You are Sentinel. You find where the code has drifted from the documentation. "
        "You identify silent failures, magic constants, and assumptions baked in. "
        "You do not soften your findings. You name the exact line where trust breaks."
    ),
}

# Domain → persona mapping
DOMAIN_TO_PERSONA = {
    "memory": "archivist",
    "decision_rationale": "archivist",
    "technical_artifacts": "archivist",
    "general": "archivist",
    "weaver": "weaver",
    "c": "ockham",
    "cpp": "ockham",
    "lua": "ockham",
    "python": "ockham",
    "anti_slop": "ockham",
    "audit": "sentinel",
    "ideation": "muse",
    "brainstorm": "muse",
}


def domain_to_system(domain: str) -> str:
    persona = DOMAIN_TO_PERSONA.get(domain.lower(), "archivist")
    return SYSTEM_PROMPTS[persona]


# ─── Data loading ─────────────────────────────────────────────────────────────

def record_to_chatml(record: dict) -> str | None:
    """Convert a training record to ChatML format string."""
    # Case 1: already has messages array
    if "messages" in record:
        msgs = record["messages"]
        if not msgs:
            return None
        # If no system message, inject one from domain
        if msgs[0]["role"] != "system":
            domain = record.get("domain", "general")
            msgs = [{"role": "system", "content": domain_to_system(domain)}] + list(msgs)
        text = ""
        for msg in msgs:
            text += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
        return text

    # Case 2: instruction/output format (from distill_memory_muse, antislop)
    instruction = record.get("instruction", "")
    output = record.get("output", "")
    if not instruction or not output:
        return None
    domain = record.get("domain", "general")
    system = domain_to_system(domain)
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{instruction}<|im_end|>\n"
        f"<|im_start|>assistant\n{output}<|im_end|>\n"
    )


def load_dataset_from_jsonl(path: str) -> Dataset:
    records = []
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                text = record_to_chatml(rec)
                if text and len(text) > 50:
                    records.append({"text": text})
                else:
                    skipped += 1
            except (json.JSONDecodeError, KeyError):
                skipped += 1

    print(f"  Loaded {len(records)} samples, skipped {skipped}")
    return Dataset.from_list(records)


# ─── Training ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Avatar-Mix QLoRA training")
    parser.add_argument("--model-name", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--data", default="data/avatar_mix_run_v1/train.jsonl")
    parser.add_argument("--output", default="adapters/avatar_mix_v1")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--rank", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Avatar-Mix v1 Training")
    print(f"  Model:  {args.model_name}")
    print(f"  Data:   {args.data}")
    print(f"  Output: {output_dir}")
    print(f"  Rank:   {args.rank}  Epochs: {args.epochs}  LR: {args.lr}")

    print(f"\nLoading training data from {args.data}...")
    dataset = load_dataset_from_jsonl(args.data)
    print(f"Dataset ready: {len(dataset)} ChatML samples")

    # Print persona distribution
    persona_counts: dict[str, int] = {}
    for rec in dataset:
        text = rec["text"]
        for persona, prompt in SYSTEM_PROMPTS.items():
            if prompt[:40] in text:
                persona_counts[persona] = persona_counts.get(persona, 0) + 1
                break
    print(f"Persona distribution: {persona_counts}")

    print(f"\nLoading model {args.model_name}...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=args.rank,
        lora_alpha=args.rank * 2,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    print("Trainable parameters:")
    model.print_trainable_parameters()

    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        logging_steps=5,
        save_strategy="epoch",
        save_total_limit=2,
        bf16=True,
        optim="paged_adamw_8bit",
        report_to="none",
        dataset_text_field="text",
        max_seq_length=args.max_length,
    )

    print("\nStarting training...")
    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    trainer.train()

    print(f"\nSaving adapter to {output_dir}...")
    trainer.model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print("Done.")

    # Save training metadata
    meta = {
        "base_model": args.model_name,
        "lora_rank": args.rank,
        "training_samples": len(dataset),
        "epochs": args.epochs,
        "lr": args.lr,
        "personas": list(SYSTEM_PROMPTS.keys()),
        "persona_distribution": persona_counts,
    }
    (output_dir / "training_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
