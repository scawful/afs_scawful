#!/usr/bin/env python3
"""
Evaluate Veran PEFT adapters using mixed eval suites.

Supported item kinds in eval JSONL:
- reference: compares generated text to expected text via normalized exact + token F1
- keywords: checks keyword recall in generated text
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9$#:_\-\.\s]", "", text)
    return text.strip()


def token_f1(pred: str, ref: str) -> float:
    p = normalize_text(pred).split()
    r = normalize_text(ref).split()
    if not p or not r:
        return 0.0
    p_counts: dict[str, int] = {}
    r_counts: dict[str, int] = {}
    for t in p:
        p_counts[t] = p_counts.get(t, 0) + 1
    for t in r:
        r_counts[t] = r_counts.get(t, 0) + 1
    overlap = 0
    for t, c in p_counts.items():
        overlap += min(c, r_counts.get(t, 0))
    precision = overlap / len(p)
    recall = overlap / len(r)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


@dataclass
class EvalSummary:
    total_cases: int = 0
    reference_cases: int = 0
    keyword_cases: int = 0
    exact_match_count: int = 0
    contains_match_count: int = 0
    keyword_full_match_count: int = 0
    token_f1_sum: float = 0.0
    keyword_recall_sum: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        ref_den = self.reference_cases if self.reference_cases else 1
        key_den = self.keyword_cases if self.keyword_cases else 1
        return {
            "total_cases": self.total_cases,
            "reference_cases": self.reference_cases,
            "keyword_cases": self.keyword_cases,
            "reference_exact_match_rate": self.exact_match_count / ref_den,
            "reference_contains_rate": self.contains_match_count / ref_den,
            "reference_avg_token_f1": self.token_f1_sum / ref_den,
            "keyword_full_match_rate": self.keyword_full_match_count / key_den,
            "keyword_avg_recall": self.keyword_recall_sum / key_den,
        }


def load_eval_cases(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
            if limit and len(cases) >= limit:
                break
    return cases


def build_prompt(tokenizer, system_msg: str, instruction: str) -> str:
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": instruction},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def generate_response(model, tokenizer, prompt: str, max_new_tokens: int) -> str:
    inputs = tokenizer(prompt, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.cuda() for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    new_tokens = outputs[0][inputs["input_ids"].shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Veran PEFT adapters.")
    parser.add_argument("--model-name", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--adapter-path", required=True, help="Path to LoRA adapter directory.")
    parser.add_argument("--eval-file", required=True, help="JSONL eval suite.")
    parser.add_argument("--output", required=True, help="Output JSON report path.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=220)
    parser.add_argument("--system-default", default="You are Veran, a 65816 assembly code explanation expert for SNES hardware.")
    args = parser.parse_args()

    eval_file = Path(args.eval_file)
    adapter_path = Path(args.adapter_path)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not eval_file.exists():
        raise SystemExit(f"Eval file not found: {eval_file}")
    if not adapter_path.exists():
        raise SystemExit(f"Adapter path not found: {adapter_path}")

    print(f"Loading tokenizer/model: {args.model_name}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if torch.cuda.is_available():
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        base = AutoModelForCausalLM.from_pretrained(
            args.model_name,
            quantization_config=bnb,
            device_map="auto",
            trust_remote_code=True,
        )
    else:
        base = AutoModelForCausalLM.from_pretrained(
            args.model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )

    model = PeftModel.from_pretrained(base, str(adapter_path))
    model.eval()

    cases = load_eval_cases(eval_file, limit=args.limit)
    print(f"Loaded {len(cases)} eval cases from {eval_file}", flush=True)

    summary = EvalSummary(total_cases=len(cases))
    results: list[dict[str, Any]] = []

    for idx, case in enumerate(cases, start=1):
        kind = case.get("kind", "reference")
        case_id = case.get("id", f"case_{idx:03d}")
        instruction = case.get("instruction", "")
        system_msg = case.get("input") or args.system_default

        prompt = build_prompt(tokenizer, system_msg, instruction)
        response = generate_response(model, tokenizer, prompt, max_new_tokens=args.max_new_tokens)

        record: dict[str, Any] = {
            "id": case_id,
            "kind": kind,
            "instruction": instruction,
            "response": response,
        }

        if kind == "keywords":
            summary.keyword_cases += 1
            keywords = [str(k) for k in case.get("keywords", [])]
            response_norm = normalize_text(response)
            found = [k for k in keywords if normalize_text(k) in response_norm]
            recall = (len(found) / len(keywords)) if keywords else 0.0
            summary.keyword_recall_sum += recall
            if keywords and len(found) == len(keywords):
                summary.keyword_full_match_count += 1
            record.update(
                {
                    "keywords": keywords,
                    "keywords_found": found,
                    "keywords_missing": [k for k in keywords if k not in found],
                    "keyword_recall": recall,
                }
            )
        else:
            summary.reference_cases += 1
            expected = case.get("expected", "")
            response_norm = normalize_text(response)
            expected_norm = normalize_text(expected)
            em = int(response_norm == expected_norm and expected_norm != "")
            contains = int(expected_norm in response_norm or response_norm in expected_norm)
            f1 = token_f1(response, expected)
            summary.exact_match_count += em
            summary.contains_match_count += contains
            summary.token_f1_sum += f1
            record.update(
                {
                    "expected": expected,
                    "exact_match": bool(em),
                    "contains_match": bool(contains),
                    "token_f1": f1,
                }
            )

        results.append(record)
        print(f"[{idx}/{len(cases)}] {case_id} ({kind})", flush=True)

    report = {
        "model_name": args.model_name,
        "adapter_path": str(adapter_path),
        "eval_file": str(eval_file),
        "summary": summary.to_dict(),
        "results": results,
    }

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved report: {output_path}", flush=True)
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
