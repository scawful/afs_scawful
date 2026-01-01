#!/usr/bin/env python3
"""
Train afs_scawful model using PEFT + QLoRA.
Base model: Qwen2.5-Coder-1.5B-Instruct
Optimized for Qwen ChatML template.
"""
import os
import argparse
from datetime import datetime
from pathlib import Path
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
from datasets import load_dataset

os.environ["TOKENIZERS_PARALLELISM"] = "false"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4)
    parser.add_argument("--lr", type=float, default=3e-4, help="Increased for better convergence")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--data-dir", type=str, default="datasets")
    parser.add_argument("--model-name", type=str, default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    parser.add_argument("--resume_from_checkpoint", type=str, default=None, help="Path to checkpoint or 'True' to resume from output_dir")
    args = parser.parse_args()

    print(f"Initializing Training: {args.model_name} (ChatML) | LR: {args.lr}")

    # Quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    tokenizer.pad_token = tokenizer.eos_token # Qwen doesn't have a specific pad token usually, eos works

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    model = prepare_model_for_kbit_training(model)
    
    # Target modules for Qwen (all linear layers)
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

    # Load Data
    data_path = Path(args.data_dir)
    train_data = load_dataset("json", data_files=str(data_path / "train.jsonl"), split="train")
    # Optional validation
    if (data_path / "val.jsonl").exists():
        val_data = load_dataset("json", data_files=str(data_path / "val.jsonl"), split="train")
    else:
        val_data = None

    # ChatML Format
    def format_chatml(sample):
        system_msg = "You are an expert 65816 Assembly programmer for SNES."
        text = f"<|im_start|>system\n{system_msg}<|im_end|>\n"
        text += f"<|im_start|>user\n{sample['instruction']}\n"
        if sample.get("input"):
            text += f"Input:\n{sample['input']}\n"
        text += f"<|im_end|>\n<|im_start|>assistant\n{sample['output']}<|im_end|>"
        return text

    def tokenize_sample(sample):
        text = format_chatml(sample)
        tokens = tokenizer(
            text,
            truncation=True,
            max_length=2048,
            padding=False
        )
        tokens["labels"] = tokens["input_ids"].copy()
        return tokens

    train_tok = train_data.map(tokenize_sample, remove_columns=train_data.column_names)
    val_tok = val_data.map(tokenize_sample, remove_columns=val_data.column_names) if val_data else None

    # Output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path(f"models/afs_scawful_{timestamp}")
    
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        warmup_steps=20,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=50,
        save_total_limit=3,
        optim="adamw_torch",
        report_to="none", # disable wandb for CLI
        gradient_checkpointing=True,
    )

    trainer = Trainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_tok,
        eval_dataset=val_tok,
        args=training_args,
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, pad_to_multiple_of=8),
    )

    resume = args.resume_from_checkpoint
    if resume == "True":
        resume = True
    elif resume == "False":
        resume = False
        
    trainer.train(resume_from_checkpoint=resume)
    
    print("Saving model...")
    model.save_pretrained(output_dir / "lora_adapters")
    tokenizer.save_pretrained(output_dir / "lora_adapters")

if __name__ == "__main__":
    main()