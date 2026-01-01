#!/usr/bin/env python3
"""
Test the trained 7b_asm_v3 model on 65816 assembly generation.
"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import argparse

def test_model(model_path: str, prompt: str, max_length: int = 512):
    """Load model and generate assembly code."""

    # Load base model and tokenizer
    print("Loading base model: Qwen/Qwen2.5-Coder-7B-Instruct...")
    base_model_name = "Qwen/Qwen2.5-Coder-7B-Instruct"

    tokenizer = AutoTokenizer.from_pretrained(base_model_name)

    # Load base model (CPU/MPS compatible for Mac)
    # Detect best device
    if torch.cuda.is_available():
        device = "cuda"
        dtype = torch.bfloat16
    elif torch.backends.mps.is_available():
        device = "mps"
        dtype = torch.float16  # MPS doesn't support bfloat16 well yet
    else:
        device = "cpu"
        dtype = torch.float32

    print(f"Using device: {device}")

    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        device_map=device if device == "cpu" else "auto",
        torch_dtype=dtype,
    )

    # Load LoRA adapters
    print(f"Loading LoRA adapters from {model_path}...")
    model = PeftModel.from_pretrained(model, model_path)
    model.eval()

    # Format prompt in ChatML style (same as training)
    system_msg = "You are an expert 65816 Assembly programmer for SNES."
    formatted_prompt = f"<|im_start|>system\n{system_msg}<|im_end|>\n"
    formatted_prompt += f"<|im_start|>user\n{prompt}<|im_end|>\n"
    formatted_prompt += "<|im_start|>assistant\n"

    # Tokenize
    inputs = tokenizer(formatted_prompt, return_tensors="pt").to(model.device)

    # Generate
    print("\nGenerating assembly code...")
    print("=" * 60)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_length,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )

    # Decode and print
    generated = tokenizer.decode(outputs[0], skip_special_tokens=False)

    # Extract just the assistant's response
    if "<|im_start|>assistant\n" in generated:
        response = generated.split("<|im_start|>assistant\n")[1]
        if "<|im_end|>" in response:
            response = response.split("<|im_end|>")[0]
        print(response.strip())
    else:
        print(generated)

    print("=" * 60)
    print("\nGeneration complete!")

def main():
    parser = argparse.ArgumentParser(description="Test 7B ASM v3 model")
    parser.add_argument(
        "--model-path",
        type=str,
        default="models/7b_asm_v3/lora_adapters",
        help="Path to LoRA adapters"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Write a routine to check if Link is holding the Master Sword",
        help="Prompt for code generation"
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=512,
        help="Maximum tokens to generate"
    )

    args = parser.parse_args()

    test_model(args.model_path, args.prompt, args.max_length)

if __name__ == "__main__":
    main()
