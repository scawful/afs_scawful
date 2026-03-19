#!/usr/bin/env python3
"""Micro-fix trainer that resumes from an existing Echo LoRA adapter."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import torch
from datasets import load_dataset
from peft import PeftModel, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter-dir", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=1536)
    parser.add_argument("--quant", choices=["4bit", "none"], default="none")
    parser.add_argument("--device-map", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--offload-dir", default="/tmp/echo_offload")
    return parser.parse_args()


def render_messages(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    cleaned = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if not role or content is None:
            continue
        cleaned.append({"role": role, "content": str(content)})

    if tokenizer.chat_template:
        return tokenizer.apply_chat_template(
            cleaned,
            tokenize=False,
            add_generation_prompt=False,
        )

    parts = []
    for msg in cleaned:
        parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
    return "\n".join(parts)


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    offload_dir = Path(args.offload_dir).resolve()
    offload_dir.mkdir(parents=True, exist_ok=True)

    print(f"base model: {args.base_model}")
    print(f"resume adapter: {args.adapter_dir}")
    print(f"data dir: {data_dir}")
    print(f"output: {out_dir}")
    print(f"offload dir: {offload_dir}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if args.quant == "4bit":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model,
            quantization_config=bnb_config,
            device_map=args.device_map if args.device_map != "cuda" else {"": 0},
            trust_remote_code=True,
        )
        model = prepare_model_for_kbit_training(model)
    else:
        dtype = torch.bfloat16 if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else torch.float16
        if args.device_map == "cuda":
            device_map: Any = {"": 0}
        elif args.device_map == "cpu":
            device_map = "cpu"
        else:
            device_map = "auto"
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model,
            torch_dtype=dtype,
            device_map=device_map,
            trust_remote_code=True,
        )
    lora_kwargs: dict[str, Any] = {"is_trainable": True}
    if args.device_map == "auto":
        lora_kwargs["offload_folder"] = str(offload_dir)

    model = PeftModel.from_pretrained(model, args.adapter_dir, **lora_kwargs)
    model.config.use_cache = False
    if hasattr(model, "generation_config") and model.generation_config:
        model.generation_config.use_cache = False

    valid_path = data_dir / "valid.jsonl"
    has_valid = valid_path.exists() and valid_path.stat().st_size > 2
    data_files: dict[str, str] = {"train": str(data_dir / "train.jsonl")}
    if has_valid:
        data_files["validation"] = str(valid_path)
    dataset = load_dataset("json", data_files=data_files)

    def tokenize_row(batch: dict[str, Any]) -> dict[str, list[list[int]]]:
        encoded_ids = []
        encoded_masks = []
        labels = []
        for messages in batch["messages"]:
            text = render_messages(tokenizer, messages)
            encoded = tokenizer(
                text,
                truncation=True,
                max_length=args.max_length,
                padding="max_length",
            )
            input_ids = encoded["input_ids"]
            mask = encoded["attention_mask"]
            encoded_ids.append(input_ids)
            encoded_masks.append(mask)
            labels.append(input_ids.copy())

        return {
            "input_ids": encoded_ids,
            "attention_mask": encoded_masks,
            "labels": labels,
        }

    tokenized = dataset.map(
        tokenize_row,
        batched=True,
        remove_columns=dataset["train"].column_names,
    )

    eval_dataset = tokenized["validation"] if has_valid else None
    training_args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        logging_steps=1,
        save_steps=10,
        eval_steps=5 if has_valid else None,
        eval_strategy="steps" if has_valid else "no",
        save_total_limit=2,
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        report_to="none",
        optim="paged_adamw_8bit" if args.quant == "4bit" else "adamw_torch",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=eval_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )

    print("starting micro-fix training")
    trainer.train()
    print("saving adapter")
    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
