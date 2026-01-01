#!/usr/bin/env python3
"""
Convert trained model to GGUF format for local inference.

Usage:
    python convert_to_gguf.py <model_dir> [--quant Q4_K_M]

Example:
    python convert_to_gguf.py D:/afs_training/models/afs_scawful_20251231_203028
"""
import argparse
import subprocess
import sys
from pathlib import Path

QUANT_TYPES = {
    "Q4_K_M": "Best balance of speed/quality (recommended)",
    "Q5_K_M": "Better quality, slightly larger",
    "Q8_0": "Near-lossless, slowest",
    "Q4_0": "Fastest, lower quality",
    "F16": "Full precision, for evaluation",
}

def main():
    parser = argparse.ArgumentParser(description="Convert to GGUF for Ollama/llama.cpp")
    parser.add_argument("model_dir", type=Path, help="Path to merged_model directory")
    parser.add_argument("--quant", default="Q4_K_M", choices=QUANT_TYPES.keys(),
                        help="Quantization type (default: Q4_K_M)")
    parser.add_argument("--output", type=Path, help="Output directory (default: model_dir/gguf/)")
    args = parser.parse_args()

    model_dir = args.model_dir
    if not model_dir.exists():
        print(f"Error: {model_dir} not found")
        sys.exit(1)

    # Find merged_model subdir if needed
    if (model_dir / "merged_model").exists():
        model_dir = model_dir / "merged_model"

    output_dir = args.output or model_dir.parent / "gguf"
    output_dir.mkdir(parents=True, exist_ok=True)

    model_name = model_dir.parent.name
    f16_path = output_dir / f"{model_name}_f16.gguf"
    quant_path = output_dir / f"{model_name}_{args.quant.lower()}.gguf"

    print("=" * 60)
    print("GGUF Conversion Pipeline")
    print("=" * 60)
    print(f"Source: {model_dir}")
    print(f"Quant:  {args.quant} - {QUANT_TYPES[args.quant]}")
    print(f"Output: {quant_path}")
    print()

    # Step 1: Convert to F16 GGUF
    print("Step 1: Converting to F16 GGUF...")
    try:
        subprocess.run([
            sys.executable, "-m", "llama_cpp.convert",
            str(model_dir),
            "--outtype", "f16",
            "--outfile", str(f16_path),
        ], check=True)
        print(f"  Created: {f16_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")
        print("\nTry installing: pip install llama-cpp-python")
        sys.exit(1)

    # Step 2: Quantize
    if args.quant != "F16":
        print(f"\nStep 2: Quantizing to {args.quant}...")
        try:
            subprocess.run([
                "llama-quantize",
                str(f16_path),
                str(quant_path),
                args.quant,
            ], check=True)
            print(f"  Created: {quant_path}")

            # Clean up F16 if quantized
            f16_path.unlink()
            print(f"  Removed: {f16_path}")
        except FileNotFoundError:
            print("Warning: llama-quantize not found, keeping F16")
            print("Install llama.cpp to quantize: brew install llama.cpp")
            quant_path = f16_path

    print()
    print("=" * 60)
    print("Conversion Complete!")
    print("=" * 60)
    print()
    print("To use with Ollama:")
    print(f"  1. Create Modelfile:")
    print(f"     FROM {quant_path}")
    print(f"     PARAMETER temperature 0.7")
    print(f"     SYSTEM \"You are an expert in 65816 assembly and ALTTP ROM hacking.\"")
    print()
    print(f"  2. Import: ollama create afs_scawful -f Modelfile")
    print(f"  3. Run:    ollama run afs_scawful")
    print()
    print("To use with llama.cpp:")
    print(f"  ./main -m {quant_path} -p \"### Instruction:\\n...\"")

if __name__ == "__main__":
    main()
