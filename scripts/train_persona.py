#!/usr/bin/env python3
"""
train_persona.py - QLoRA training for single-persona models.

Trains Sibyl, Lancer, Morpheus, Anamnesis, Monolith, Conductor, Steward,
Journalist, Poet, Poet_v4, or Essayist on Qwen 2.5 3B Instruct.
Smaller rank and batch size tuned for 3B vs Avatar-Mix's 7B.

Run on GPU instance (Vast.ai / Medical Mechanica):
    python3 scripts/train_persona.py --persona sibyl
    python3 scripts/train_persona.py --persona lancer --epochs 8
    python3 scripts/train_persona.py --data data/training_data/morpheus_v1.jsonl --name morpheus-v1

Requirements:
    pip install torch transformers peft bitsandbytes accelerate datasets trl

Args:
    --persona   Persona name: sibyl, lancer, morpheus, anamnesis, monolith,
                conductor, conductor_v3, steward, journalist, poet, poet_v4, essayist
                (sets data + system prompt)
    --data      Override training JSONL path
    --name      Override output adapter name
    --model     Base model (default: Qwen/Qwen2.5-3B-Instruct)
    --epochs    Training epochs (default: 6)
    --lr        Learning rate (default: 2e-4)
    --rank      LoRA rank (default: 32)
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

# ─── Persona registry ─────────────────────────────────────────────────────────

PERSONAS = {
    "sibyl": {
        "data": "data/training_data/sibyl_v1.jsonl",
        "output": "adapters/sibyl_v1",
        "system": (
            "You are Sibyl. You know how scawful works: deep focus windows, brain dumps before "
            "decisions, the daily Capture → Flow → Reflect loop. You help him triage, not just "
            "list options. Direct, concrete, low-overhead. No vague suggestions."
        ),
    },
    "lancer": {
        "data": "data/training_data/lancer_v1.jsonl",
        "output": "adapters/lancer_v1",
        "system": (
            "You are Lancer. scawful is stuck. Give him exactly one thing to do right now. "
            "Use imperative mood. No alternatives. No caveats. "
            "Your voice is dry and certain. No exclamation marks. No enthusiasm. No slang. "
            "Speak like a senior engineer who wastes no words. Calm. Definitive. Nothing extra."
        ),
    },
    "morpheus": {
        "data": "data/training_data/morpheus_v1.jsonl",
        "output": "adapters/morpheus_v1",
        "system": (
            "You are Morpheus. You know scawful's entire universe of projects. Every idea you "
            "generate connects something he already built to something he hasn't imagined yet. "
            "Be specific. Reference real files and patterns he has."
        ),
    },
    "anamnesis": {
        "data": "data/training_data/anamnesis_v1.jsonl",
        "output": "adapters/anamnesis_v1",
        "system": (
            "You are Anamnesis. You recall what was decided and why. You speak from the actual "
            "record — commit messages, design docs, code patterns — not from generic reasoning. "
            "If you don't know, you say so precisely: what record you consulted and what was missing."
        ),
    },
    "monolith": {
        "data": "data/training_data/monolith_v1.jsonl",
        "output": "adapters/monolith_v1",
        "system": (
            "You are Monolith. You represent the brutalist ideal of coding. "
            "Output minimal viable logic in Bash or C. "
            "Prefer no dependencies and no ceremony. "
            "Keep output compact, direct, and practical."
        ),
    },
    "conductor": {
        "data": "data/training_data/conductor_v1.jsonl",
        "output": "adapters/conductor_v1",
        "system": (
            "You are The Conductor. Decompose goals into Agent-to-Agent handoff plans. "
            "Output valid JSON only. "
            "Use a DAG with explicit nodes, dependencies, and deliverables."
        ),
    },
    "conductor_v3": {
        "data": "data/training_data/conductor_v3.jsonl",
        "output": "adapters/conductor_v3",
        "system": (
            "You are The Conductor. Output valid JSON only. "
            "Generate schema-consistent DAG handoff plans with nodes, edges, checkpoints, risks, and ownership."
        ),
    },
    "steward": {
        "data": "data/training_data/steward_v1.jsonl",
        "output": "adapters/steward_v1",
        "system": (
            "You are Steward. You are a task execution operator, not a motivational coach. "
            "Turn messy backlogs into a short ordered plan with concrete checkpoints. "
            "Always include the first irreversible action."
        ),
    },
    "journalist": {
        "data": "data/training_data/journalist_v1.jsonl",
        "output": "adapters/journalist_v1",
        "system": (
            "You are Journalist. Reflect on daily notes with clarity and honesty. "
            "Summarize what happened, identify likely patterns without overclaiming, "
            "and propose one practical experiment for tomorrow."
        ),
    },
    "poet": {
        "data": "data/training_data/poet_v3.jsonl",
        "output": "adapters/poet_v3",
        "system": (
            "You are Poet. Write compact vivid poems from plain language. "
            "Use 4-10 lines, under 120 words, and concrete imagery. "
            "No title and no explanatory prose."
        ),
    },
    "poet_v4": {
        "data": "data/training_data/poet_v4.jsonl",
        "output": "adapters/poet_v4",
        "system": (
            "You are Poet. You receive [FORM:<name>] in the user prompt. "
            "Follow that form exactly and return poem text only. "
            "Keep concrete imagery and avoid cliches."
        ),
    },
    "essayist": {
        "data": "data/training_data/essayist_v2.jsonl",
        "output": "adapters/essayist_v2",
        "system": (
            "You are Essayist. Write thesis-driven structured essays from rough prompts. "
            "Provide clear argument flow, practical examples, and tight conclusions."
        ),
    },
}


def record_to_chatml(record: dict, default_system: str) -> str | None:
    """Convert a training record to ChatML format string."""
    if "messages" in record:
        msgs = record["messages"]
        if not msgs:
            return None
        if msgs[0]["role"] != "system":
            msgs = [{"role": "system", "content": default_system}] + list(msgs)
        text = ""
        for msg in msgs:
            text += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
        return text

    instruction = record.get("instruction", "")
    output = record.get("output", "")
    if not instruction or not output:
        return None
    return (
        f"<|im_start|>system\n{default_system}<|im_end|>\n"
        f"<|im_start|>user\n{instruction}<|im_end|>\n"
        f"<|im_start|>assistant\n{output}<|im_end|>\n"
    )


def load_dataset_from_jsonl(path: str, system_prompt: str) -> Dataset:
    records = []
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                text = record_to_chatml(rec, system_prompt)
                if text and len(text) > 50:
                    records.append({"text": text})
                else:
                    skipped += 1
            except (json.JSONDecodeError, KeyError):
                skipped += 1
    print(f"  Loaded {len(records)} samples, skipped {skipped}")
    return Dataset.from_list(records)


def main():
    parser = argparse.ArgumentParser(description="Persona QLoRA training (3B)")
    parser.add_argument("--persona", choices=list(PERSONAS), help="Persona name")
    parser.add_argument("--data", help="Override JSONL path")
    parser.add_argument("--name", help="Override output adapter name")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()

    if not args.persona and not args.data:
        parser.error("Provide --persona or --data")

    cfg = PERSONAS.get(args.persona, {}) if args.persona else {}
    data_path = args.data or cfg.get("data")
    output_name = args.name or cfg.get("output") or f"adapters/{args.persona or 'persona'}_v1"
    system_prompt = cfg.get("system", "You are a helpful assistant.")

    if not data_path:
        parser.error("Could not determine data path — provide --persona or --data")

    output_dir = Path(output_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Persona Training: {args.persona or 'custom'}")
    print(f"  Model:  {args.model}")
    print(f"  Data:   {data_path}")
    print(f"  Output: {output_dir}")
    print(f"  Rank:   {args.rank}  Epochs: {args.epochs}  LR: {args.lr}")

    print(f"\nLoading training data...")
    dataset = load_dataset_from_jsonl(data_path, system_prompt)
    print(f"Dataset ready: {len(dataset)} ChatML samples")

    print(f"\nLoading model {args.model}...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
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

    meta = {
        "persona": args.persona or "custom",
        "base_model": args.model,
        "lora_rank": args.rank,
        "training_samples": len(dataset),
        "epochs": args.epochs,
        "lr": args.lr,
        "system_prompt": system_prompt[:100] + "...",
    }
    (output_dir / "training_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print("Done.")


if __name__ == "__main__":
    main()
