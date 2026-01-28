#!/usr/bin/env python3
"""
Train an LSP-style autocomplete model using PEFT + QLoRA.
Supports prefix-only and FIM (fill-in-the-middle) modes.
"""
from __future__ import annotations

import argparse
import inspect
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

os.environ["TOKENIZERS_PARALLELISM"] = "false"
sys.stdout = os.fdopen(sys.stdout.fileno(), "w", buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), "w", buffering=1)

FIM_TOKENS = ["<|fim_prefix|>", "<|fim_suffix|>", "<|fim_middle|>"]


def resolve_data_files(data_dir: Path, train_file: Path | None, val_file: Path | None) -> tuple[Path, Path | None]:
    train_path = train_file if train_file else data_dir / "train.jsonl"
    val_path = val_file if val_file else data_dir / "val.jsonl"
    if not train_path.exists():
        raise SystemExit(f"Train file not found: {train_path}")
    if not val_path.exists():
        val_path = None
    return train_path, val_path


def build_prefix_example(
    prefix: str,
    completion: str,
    tokenizer,
    max_length: int,
    add_eos: bool,
) -> dict:
    prefix_ids = tokenizer(prefix, add_special_tokens=False).input_ids
    completion_ids = tokenizer(completion, add_special_tokens=False).input_ids
    if add_eos and tokenizer.eos_token_id is not None:
        completion_ids = completion_ids + [tokenizer.eos_token_id]

    input_ids = prefix_ids + completion_ids
    if len(input_ids) > max_length:
        overflow = len(input_ids) - max_length
        if overflow < len(prefix_ids):
            prefix_ids = prefix_ids[overflow:]
        else:
            prefix_ids = []
            completion_ids = completion_ids[:max_length]
        input_ids = prefix_ids + completion_ids

    labels = [-100] * len(prefix_ids) + completion_ids
    attention_mask = [1] * len(input_ids)
    return {"input_ids": input_ids, "labels": labels, "attention_mask": attention_mask}


def trim_fim_context(prefix_ids: list[int], suffix_ids: list[int], max_context: int) -> tuple[list[int], list[int]]:
    context_len = 3 + len(prefix_ids) + len(suffix_ids)
    if context_len <= max_context:
        return prefix_ids, suffix_ids

    overflow = context_len - max_context
    if overflow <= len(prefix_ids):
        prefix_ids = prefix_ids[overflow:]
        return prefix_ids, suffix_ids

    overflow -= len(prefix_ids)
    prefix_ids = []
    if overflow >= len(suffix_ids):
        return prefix_ids, []
    suffix_ids = suffix_ids[: len(suffix_ids) - overflow]
    return prefix_ids, suffix_ids


def build_fim_example(
    prefix: str,
    suffix: str,
    completion: str,
    tokenizer,
    max_length: int,
    add_eos: bool,
) -> dict:
    prefix_ids = tokenizer(prefix, add_special_tokens=False).input_ids
    suffix_ids = tokenizer(suffix, add_special_tokens=False).input_ids
    completion_ids = tokenizer(completion, add_special_tokens=False).input_ids
    if add_eos and tokenizer.eos_token_id is not None:
        completion_ids = completion_ids + [tokenizer.eos_token_id]

    max_completion = max_length - 3
    if max_completion <= 0:
        raise ValueError("max_length too small for FIM tokens")
    if len(completion_ids) > max_completion:
        completion_ids = completion_ids[:max_completion]

    max_context = max_length - len(completion_ids)
    prefix_ids, suffix_ids = trim_fim_context(prefix_ids, suffix_ids, max_context)

    fim_prefix_id = tokenizer.convert_tokens_to_ids(FIM_TOKENS[0])
    fim_suffix_id = tokenizer.convert_tokens_to_ids(FIM_TOKENS[1])
    fim_middle_id = tokenizer.convert_tokens_to_ids(FIM_TOKENS[2])
    context_ids = [fim_prefix_id] + prefix_ids + [fim_suffix_id] + suffix_ids + [fim_middle_id]
    input_ids = context_ids + completion_ids
    labels = [-100] * len(context_ids) + completion_ids
    attention_mask = [1] * len(input_ids)
    return {"input_ids": input_ids, "labels": labels, "attention_mask": attention_mask}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LSP autocomplete model.")
    parser.add_argument("--model-name", type=str, default="Qwen/Qwen2.5-Coder-0.5B")
    parser.add_argument("--data-dir", type=Path, default=Path("datasets"))
    parser.add_argument("--train-file", type=Path, default=None)
    parser.add_argument("--val-file", type=Path, default=None)
    parser.add_argument("--mode", choices=["auto", "prefix", "fim"], default="auto")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--save-steps", type=int, default=200)
    parser.add_argument("--eval-steps", type=int, default=200)
    parser.add_argument("--save-total-limit", type=int, default=2)
    parser.add_argument(
        "--save-only-model",
        dest="save_only_model",
        action="store_true",
        help="Save model weights only (skip optimizer/scheduler state).",
    )
    parser.add_argument(
        "--save-full-checkpoint",
        dest="save_only_model",
        action="store_false",
        help="Save full checkpoints including optimizer/scheduler state.",
    )
    parser.add_argument("--warmup-steps", type=int, default=20)
    parser.add_argument("--no-gradient-checkpointing", action="store_true")
    parser.add_argument("--no-eos", action="store_true")
    parser.set_defaults(save_only_model=True)
    args = parser.parse_args()

    random.seed(args.seed)

    train_file, val_file = resolve_data_files(args.data_dir, args.train_file, args.val_file)

    print("=" * 60, flush=True)
    print("AFS_SCAWFUL AUTOCOMPLETE TRAINING", flush=True)
    print("=" * 60, flush=True)
    print(f"Start time: {datetime.now()}", flush=True)
    print(f"Model: {args.model_name}", flush=True)
    print(f"Train: {train_file}", flush=True)
    print(f"Val: {val_file if val_file else 'None'}", flush=True)
    print(f"Mode: {args.mode}", flush=True)
    print(f"Max length: {args.max_length}", flush=True)
    print(flush=True)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    tokenizer.add_special_tokens({"additional_special_tokens": FIM_TOKENS})

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.resize_token_embeddings(len(tokenizer))
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    train_data = load_dataset("json", data_files=str(train_file), split="train")
    if val_file:
        val_data = load_dataset("json", data_files=str(val_file), split="train")
    else:
        val_data = None

    def extract_fields(sample: dict) -> tuple[str, str, str]:
        prefix = sample.get("prefix") or sample.get("prompt") or sample.get("instruction") or ""
        input_text = sample.get("input") or ""
        if input_text:
            prefix = f"{prefix}\n{input_text}" if prefix else str(input_text)

        completion = (
            sample.get("completion")
            or sample.get("output")
            or sample.get("response")
            or sample.get("answer")
            or ""
        )
        suffix = sample.get("suffix") or ""
        return str(prefix), str(completion), str(suffix)

    def has_completion(sample: dict) -> bool:
        _, completion, _ = extract_fields(sample)
        return bool(completion.strip())

    train_data = train_data.filter(has_completion)
    if val_data:
        val_data = val_data.filter(has_completion)

    def resolve_mode(sample: dict) -> str:
        if args.mode != "auto":
            return args.mode
        mode = str(sample.get("mode", "prefix")).lower()
        return mode if mode in {"prefix", "fim"} else "prefix"

    def tokenize_sample(sample: dict) -> dict:
        prefix, completion, suffix = extract_fields(sample)
        mode = resolve_mode(sample)
        add_eos = not args.no_eos

        if mode == "fim" and suffix.strip():
            return build_fim_example(prefix, suffix, completion, tokenizer, args.max_length, add_eos)
        return build_prefix_example(prefix, completion, tokenizer, args.max_length, add_eos)

    train_tok = train_data.map(tokenize_sample, remove_columns=train_data.column_names)
    if val_data:
        val_tok = val_data.map(tokenize_sample, remove_columns=val_data.column_names)
    else:
        val_tok = None

    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    use_fp16 = torch.cuda.is_available() and not use_bf16

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path(f"models/autocomplete_{timestamp}")

    eval_strategy = "steps" if val_tok else "no"
    training_kwargs = dict(
        output_dir=str(output_dir),
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        warmup_steps=args.warmup_steps,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        logging_steps=args.logging_steps,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=args.save_total_limit,
        eval_steps=args.eval_steps,
        bf16=use_bf16,
        fp16=use_fp16,
        optim="adamw_torch",
        report_to="none",
        gradient_checkpointing=not args.no_gradient_checkpointing,
        seed=args.seed,
        remove_unused_columns=False,
    )
    training_params = inspect.signature(TrainingArguments.__init__).parameters
    eval_arg = "eval_strategy" if "eval_strategy" in training_params else "evaluation_strategy"
    if args.save_only_model and "save_only_model" in training_params:
        training_kwargs["save_only_model"] = True
    if "save_safetensors" in training_params:
        training_kwargs["save_safetensors"] = True
    training_kwargs[eval_arg] = eval_strategy
    training_args = TrainingArguments(**training_kwargs)

    data_collator = DataCollatorForSeq2Seq(
        tokenizer,
        padding=True,
        pad_to_multiple_of=8,
        label_pad_token_id=-100,
    )

    trainer = Trainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_tok,
        eval_dataset=val_tok,
        args=training_args,
        data_collator=data_collator,
    )
    if args.save_only_model and "save_only_model" not in training_params:
        trainer._save_optimizer_and_scheduler = lambda *_, **__: None

    print("=" * 60, flush=True)
    print("STARTING TRAINING", flush=True)
    print("=" * 60, flush=True)
    print(flush=True)

    trainer.train()

    print(flush=True)
    print("=" * 60, flush=True)
    print("TRAINING COMPLETE", flush=True)
    print("=" * 60, flush=True)
    print(f"Saving model to {output_dir / 'lora_adapters'}...", flush=True)
    model.save_pretrained(output_dir / "lora_adapters")
    tokenizer.save_pretrained(output_dir / "lora_adapters")
    print("Model saved successfully!", flush=True)
    print(f"Finished at: {datetime.now()}", flush=True)


if __name__ == "__main__":
    main()
