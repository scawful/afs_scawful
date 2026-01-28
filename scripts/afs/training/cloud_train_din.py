#!/usr/bin/env python3
"""
Cloud training script for Din (optimization expert).

Run on Vast.ai or similar GPU cloud with:
    python cloud_train_din.py

Requirements:
    pip install torch transformers peft bitsandbytes accelerate datasets trl
"""

import json
import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

# Configuration
MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"
OUTPUT_DIR = "./din-optimize-adapters"
TRAINING_DATA = "./din_optimize_filtered.jsonl"

# LoRA configuration
LORA_CONFIG = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

# Training configuration using SFTConfig
SFT_CONFIG = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    warmup_ratio=0.1,
    logging_steps=5,
    save_strategy="epoch",
    bf16=True,
    optim="paged_adamw_8bit",
    report_to="none",
    dataset_text_field="text",
)


def load_training_data(path: str) -> Dataset:
    """Load JSONL training data."""
    examples = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            messages = data.get("messages", [])
            text = ""
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                text += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            if text:
                examples.append({"text": text})
    return Dataset.from_list(examples)


def main() -> None:
    print(f"Loading training data from {TRAINING_DATA}...")
    dataset = load_training_data(TRAINING_DATA)
    print(f"Loaded {len(dataset)} examples")

    print(f"Loading model {MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    # 4-bit quantization for memory efficiency
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # Prepare for training
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LORA_CONFIG)

    print("Trainable parameters:")
    model.print_trainable_parameters()

    # Train
    print("Starting training...")
    trainer = SFTTrainer(
        model=model,
        args=SFT_CONFIG,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    trainer.train()

    # Save adapters
    print(f"Saving adapters to {OUTPUT_DIR}...")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print("Training complete!")
    print(f"Adapters saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
