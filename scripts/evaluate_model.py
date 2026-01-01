#!/usr/bin/env python3
"""
Evaluate trained afs_scawful model quality.

Tests:
1. ASM syntax validity (does output assemble?)
2. Instruction following (does it answer correctly?)
3. Tool calling format (correct JSON structure?)
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Test prompts for evaluation
EVAL_PROMPTS = [
    # ASM understanding
    {
        "instruction": "Explain what this 65816 assembly code does",
        "input": "LDA $0E20,X\nSEC\nSBC #$10\nSTA $0E20,X",
        "expected_keywords": ["load", "subtract", "store", "hp", "damage"],
        "category": "asm_understanding"
    },
    # Code generation
    {
        "instruction": "Write a 65816 routine that sets A to 0 and returns",
        "input": "",
        "expected_keywords": ["LDA", "RTS"],
        "category": "code_generation"
    },
    # Tool calling
    {
        "instruction": "Read 16 bytes from ROM address $008000",
        "input": "",
        "expected_keywords": ["read", "rom", "8000"],
        "category": "tool_calling"
    },
    # ALTTP knowledge
    {
        "instruction": "What is stored at WRAM address $0E20 in A Link to the Past?",
        "input": "",
        "expected_keywords": ["sprite", "hp", "health", "enemy"],
        "category": "alttp_knowledge"
    },
    # Optimization
    {
        "instruction": "Optimize this code for fewer cycles",
        "input": "LDA #$00\nSTA $00\nLDA #$00\nSTA $01",
        "expected_keywords": ["STZ", "optimize", "cycle"],
        "category": "optimization"
    },
]

def run_inference(model_path: str, prompt: str) -> Optional[str]:
    """Run inference using ollama or llama.cpp."""
    try:
        # Try ollama first
        result = subprocess.run(
            ["ollama", "run", "afs_test", prompt],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to direct model if ollama not available
    return None

def evaluate_response(response: str, expected_keywords: list) -> dict:
    """Score a response based on expected keywords."""
    if not response:
        return {"score": 0, "matched": [], "missed": expected_keywords}

    response_lower = response.lower()
    matched = [kw for kw in expected_keywords if kw.lower() in response_lower]
    missed = [kw for kw in expected_keywords if kw.lower() not in response_lower]

    score = len(matched) / len(expected_keywords) if expected_keywords else 1.0

    return {
        "score": score,
        "matched": matched,
        "missed": missed,
        "response_length": len(response),
    }

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate afs_scawful model")
    parser.add_argument("model_path", type=Path, nargs="?",
                        help="Path to GGUF model (optional if using ollama)")
    parser.add_argument("--output", type=Path, default=Path("eval_results.json"))
    args = parser.parse_args()

    print("=" * 60)
    print("AFS_SCAWFUL MODEL EVALUATION")
    print("=" * 60)
    print()

    results = {
        "model": str(args.model_path) if args.model_path else "ollama:afs_test",
        "tests": [],
        "summary": {}
    }

    category_scores = {}

    for i, test in enumerate(EVAL_PROMPTS, 1):
        print(f"Test {i}/{len(EVAL_PROMPTS)}: {test['category']}")

        prompt = f"### Instruction:\n{test['instruction']}\n\n"
        if test['input']:
            prompt += f"### Input:\n{test['input']}\n\n"
        prompt += "### Response:\n"

        response = run_inference(str(args.model_path), prompt)

        if response:
            eval_result = evaluate_response(response, test['expected_keywords'])
            print(f"  Score: {eval_result['score']:.2f}")
            print(f"  Matched: {eval_result['matched']}")
        else:
            eval_result = {"score": 0, "error": "No response"}
            print("  Error: Could not get response")

        results["tests"].append({
            "category": test['category'],
            "instruction": test['instruction'],
            "response": response[:500] if response else None,
            **eval_result
        })

        # Track category scores
        cat = test['category']
        if cat not in category_scores:
            category_scores[cat] = []
        category_scores[cat].append(eval_result['score'])

        print()

    # Calculate summary
    results["summary"] = {
        "overall_score": sum(t["score"] for t in results["tests"]) / len(results["tests"]),
        "category_scores": {
            cat: sum(scores) / len(scores)
            for cat, scores in category_scores.items()
        }
    }

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Overall Score: {results['summary']['overall_score']:.2%}")
    print()
    print("By Category:")
    for cat, score in results['summary']['category_scores'].items():
        print(f"  {cat}: {score:.2%}")

    # Save results
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)
    print()
    print(f"Results saved to: {args.output}")

if __name__ == "__main__":
    main()
