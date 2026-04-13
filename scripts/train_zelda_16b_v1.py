#!/usr/bin/env python3
"""Train the Zelda 16B v1 DeepSeek-Coder-V2-Lite adapter on a remote GPU node."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


MODEL_NAME = os.environ.get("TRAIN_MODEL_NAME", "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct")
DATA_DIR = Path(os.environ.get("TRAIN_DATA_DIR", "/opt/training/datasets/zelda_16b_mix_v1"))
OUTPUT_DIR = Path(os.environ.get("TRAIN_OUTPUT_DIR", "/opt/training/models/zelda-16b-v1"))
FINAL_DIR = OUTPUT_DIR / "final"
MAX_SEQ_LEN = int(os.environ.get("TRAIN_MAX_SEQ_LEN", "4096"))
ATTN_IMPLEMENTATION = os.environ.get("TRAIN_ATTN_IMPLEMENTATION", "eager")

NUM_EPOCHS = int(os.environ.get("TRAIN_NUM_EPOCHS", "1"))
MICRO_BATCH_SIZE = int(os.environ.get("TRAIN_MICRO_BATCH_SIZE", "1"))
EVAL_BATCH_SIZE = int(os.environ.get("TRAIN_EVAL_BATCH_SIZE", "1"))
GRADIENT_ACCUMULATION_STEPS = int(os.environ.get("TRAIN_GRAD_ACCUM", "8"))
LEARNING_RATE = float(os.environ.get("TRAIN_LEARNING_RATE", "1e-4"))
LORA_R = int(os.environ.get("TRAIN_LORA_R", "32"))
LORA_ALPHA = int(os.environ.get("TRAIN_LORA_ALPHA", "64"))
LORA_DROPOUT = float(os.environ.get("TRAIN_LORA_DROPOUT", "0.05"))


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("train_zelda_16b_v1")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    return logger


def pick_precision() -> tuple[torch.dtype, bool, bool]:
    if not torch.cuda.is_available():
        return torch.float16, False, True
    bf16_supported = False
    if hasattr(torch.cuda, "is_bf16_supported"):
        try:
            bf16_supported = torch.cuda.is_bf16_supported()
        except Exception:
            bf16_supported = False
    if bf16_supported:
        return torch.bfloat16, True, False
    return torch.float16, False, True


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "")).strip()
        if role not in {"system", "user", "assistant"}:
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        normalized.append({"role": role, "content": content.strip()})
    return normalized


def record_to_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    messages = record.get("messages")
    if isinstance(messages, list):
        normalized = normalize_messages(messages)
        if normalized:
            return normalized

    instruction = str(record.get("instruction", "")).strip()
    output = str(record.get("output", "")).strip()
    input_text = str(record.get("input", "")).strip()
    if not instruction or not output:
        return []
    user_content = instruction if not input_text else f"{instruction}\n\nContext:\n{input_text}"
    return [
        {
            "role": "system",
            "content": (
                "You are a Zelda ROM hacking assistant specialized in 65816 assembly, "
                "Oracle of Secrets, and ALTTP engine internals. Write precise code and "
                "explanations grounded in the actual prompt context."
            ),
        },
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": output},
    ]


def apply_chat_template(tokenizer, messages: list[dict[str, str]]) -> str:
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    chunks = []
    for message in messages:
        chunks.append(f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>")
    return "\n".join(chunks)


def main() -> None:
    logger = setup_logging()
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    logger.info("=== Zelda 16B v1 Vast Training ===")
    logger.info("Model: %s", MODEL_NAME)
    logger.info("Data dir: %s", DATA_DIR)
    logger.info("Output dir: %s", OUTPUT_DIR)

    if not torch.cuda.is_available():
        logger.error("CUDA is not available.")
        sys.exit(1)

    train_file = DATA_DIR / "train.jsonl"
    val_file = DATA_DIR / "val.jsonl"
    if not train_file.exists() or not val_file.exists():
        logger.error("Missing dataset files in %s", DATA_DIR)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    torch_dtype, use_bf16, use_fp16 = pick_precision()
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch_dtype,
        bnb_4bit_use_double_quant=True,
    )

    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    logger.info("Loading base model...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch_dtype,
        quantization_config=quant_config,
        attn_implementation=ATTN_IMPLEMENTATION,
    )
    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()

    peft_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    model.config.use_cache = False
    model.print_trainable_parameters()

    logger.info("Loading datasets...")
    dataset = load_dataset(
        "json",
        data_files={
            "train": str(train_file),
            "validation": str(val_file),
        },
    )

    def tokenize(record: dict[str, Any]) -> dict[str, Any]:
        messages = record_to_messages(record)
        if not messages:
            return {"input_ids": [], "attention_mask": []}
        prompt = apply_chat_template(tokenizer, messages)
        result = tokenizer(prompt, truncation=True, max_length=MAX_SEQ_LEN, padding=False)
        input_ids = result.get("input_ids")
        if not isinstance(input_ids, list) or (input_ids and isinstance(input_ids[0], list)):
            return {"input_ids": [], "attention_mask": []}
        return result

    tokenized_dataset = dataset.map(tokenize, remove_columns=dataset["train"].column_names)
    tokenized_dataset = tokenized_dataset.filter(lambda row: len(row["input_ids"]) > 0)
    logger.info(
        "Train samples: %d | Val samples: %d",
        len(tokenized_dataset["train"]),
        len(tokenized_dataset["validation"]),
    )

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=MICRO_BATCH_SIZE,
        per_device_eval_batch_size=EVAL_BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_ratio=0.03,
        weight_decay=0.01,
        logging_steps=10,
        save_steps=200,
        save_total_limit=3,
        eval_strategy="steps",
        eval_steps=200,
        bf16=use_bf16,
        fp16=use_fp16,
        tf32=True,
        gradient_checkpointing=True,
        lr_scheduler_type="cosine",
        report_to="none",
        dataloader_num_workers=2,
        max_grad_norm=0.3,
        optim="paged_adamw_8bit",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["validation"],
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    logger.info("Starting training...")
    trainer.train()

    logger.info("Saving final adapter...")
    trainer.save_model(str(FINAL_DIR))
    tokenizer.save_pretrained(str(FINAL_DIR))
    logger.info("Training complete. Final model saved to %s", FINAL_DIR)


if __name__ == "__main__":
    main()
