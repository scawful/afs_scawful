#!/bin/bash
# 00_instance_setup.sh
# Run this on each Vast.ai instance after creation

set -e

echo "========================================"
echo "  Vast.ai Instance Setup"
echo "========================================"

# Install dependencies
echo "[1/4] Installing Python dependencies..."
pip install -q transformers peft accelerate bitsandbytes datasets wandb sentencepiece torch torchvision torchaudio

# Clone training repo (using public llama.cpp for GGUF conversion)
echo "[2/4] Cloning required repositories..."
cd /workspace
if [ ! -d "llama.cpp" ]; then
    git clone https://github.com/ggerganov/llama.cpp
    cd llama.cpp && cmake -B build && cmake --build build --config Release
fi

# Create directory structure
echo "[3/4] Creating directory structure..."
mkdir -p /workspace/data
mkdir -p /workspace/adapters
mkdir -p /workspace/merged
mkdir -p /workspace/gguf
mkdir -p /workspace/logs

# Create training script
echo "[4/4] Creating training script..."
cat > /workspace/train_model.sh << 'TRAIN_EOF'
#!/bin/bash
# train_model.sh <model_name> <data_file> <epochs>

MODEL_NAME=$1
DATA_FILE=$2
EPOCHS=${3:-3}

echo "========================================"
echo "  Training: $MODEL_NAME"
echo "  Data: $DATA_FILE"
echo "  Epochs: $EPOCHS"
echo "========================================"

python3 << 'PYTHON_EOF'
import sys
import os
import json
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
)
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# Config from command line
MODEL_NAME = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MODEL_NAME", "model")
DATA_FILE = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DATA_FILE", "data.jsonl")
EPOCHS = int(sys.argv[3]) if len(sys.argv) > 3 else int(os.environ.get("EPOCHS", "3"))

print(f"Model: {MODEL_NAME}")
print(f"Data: {DATA_FILE}")
print(f"Epochs: {EPOCHS}")

# Load base model
print("\n[1/5] Loading base model...")
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True,
)

tokenizer = AutoTokenizer.from_pretrained(
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    trust_remote_code=True
)
tokenizer.pad_token = tokenizer.eos_token

# LoRA config
print("\n[2/5] Configuring LoRA...")
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# Load dataset
print("\n[3/5] Loading dataset...")
dataset = load_dataset("json", data_files=f"/workspace/data/{DATA_FILE}", split="train")

# Split train/eval (95/5)
dataset = dataset.train_test_split(test_size=0.05, seed=42)

def tokenize_function(examples):
    # ChatML format already in dataset
    conversations = []
    for messages in examples["messages"]:
        conversation = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                conversation += f"<|im_start|>system\n{content}<|im_end|>\n"
            elif role == "user":
                conversation += f"<|im_start|>user\n{content}<|im_end|>\n"
            elif role == "assistant":
                conversation += f"<|im_start|>assistant\n{content}<|im_end|>\n"
        conversations.append(conversation)

    return tokenizer(conversations, truncation=True, max_length=2048, padding="max_length")

tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=dataset["train"].column_names)

# Training arguments
print("\n[4/5] Configuring training...")
training_args = TrainingArguments(
    output_dir=f"/workspace/adapters/{MODEL_NAME}",
    num_train_epochs=EPOCHS,
    per_device_train_batch_size=4,
    per_device_eval_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=3e-4,
    lr_scheduler_type="cosine",
    warmup_steps=100,
    logging_steps=10,
    save_steps=500,
    eval_steps=250,
    evaluation_strategy="steps",
    save_strategy="steps",
    load_best_model_at_end=True,
    fp16=True,
    optim="adamw_torch",
    weight_decay=0.01,
    max_grad_norm=1.0,
    report_to="none",  # Disable wandb for now
)

# Train
print("\n[5/5] Starting training...")
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset["train"],
    eval_dataset=tokenized_dataset["test"],
)

trainer.train()

# Save final model
print("\nSaving final model...")
trainer.save_model(f"/workspace/adapters/{MODEL_NAME}")
tokenizer.save_pretrained(f"/workspace/adapters/{MODEL_NAME}")

print("\n" + "="*50)
print("✓ Training complete!")
print(f"Adapters saved to: /workspace/adapters/{MODEL_NAME}")
print("="*50)
PYTHON_EOF

python3 -c "pass" "$MODEL_NAME" "$DATA_FILE" "$EPOCHS"
TRAIN_EOF

chmod +x /workspace/train_model.sh

echo ""
echo "========================================"
echo "  ✓ Setup Complete"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Upload training data: scp -P <PORT> data.jsonl root@ssh1.vast.ai:/workspace/data/"
echo "  2. Start training: bash /workspace/train_model.sh <name> <file> <epochs>"
echo ""
