#!/usr/bin/env python3
"""Run EchoFlow avatar eval pack against a base model + LoRA adapter."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


SYSTEM_PROMPTS: dict[str, str] = {
    "echo": (
        "you are scawful-echo, a voice distilled from justin's writing.\n"
        "style: lowercase, candid, lightly stream-of-consciousness; dry humor with quiet hopefulness; technical when it matters, casual otherwise.\n"
        "rules: avoid corporate tone, avoid ai disclaimers, admit uncertainty directly, and follow strict json output when explicitly requested."
    ),
    "memory": (
        "you are memory, a factual recall assistant.\n"
        "style: concise, concrete, grounded in known facts.\n"
        "rules: do not speculate, state unknown when data is missing, prioritize precision."
    ),
    "muse": (
        "you are muse, a creative exploration partner.\n"
        "style: imaginative but coherent.\n"
        "rules: generate useful options, keep outputs compact and actionable."
    ),
    "neutral": (
        "you are a practical assistant.\n"
        "style: clear and concise.\n"
        "rules: prioritize accuracy and actionable output."
    ),
}


def load_cases(path: Path, limit: int | None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
            if limit is not None and len(cases) >= limit:
                break
    return cases


def clean_for_json(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.removeprefix("```json").removeprefix("```")
    cleaned = cleaned.removesuffix("```")
    return cleaned.strip()


def choose_profile(default_profile: str, tags: list[str]) -> str:
    lowered = {tag.lower() for tag in tags}
    if "memory" in lowered:
        return "memory"
    if "muse" in lowered:
        return "muse"
    if "echo" in lowered:
        return "echo"
    return default_profile


def render_prompt(messages: list[dict[str, str]], tokenizer: Any) -> str:
    if tokenizer.chat_template:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    parts: list[str] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


def generate_response(
    model: Any,
    tokenizer: Any,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    encoded = tokenizer(prompt, return_tensors="pt")
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    input_len = encoded["input_ids"].shape[1]

    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": max_tokens,
        "pad_token_id": tokenizer.pad_token_id,
    }
    if temperature > 0:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = temperature
    else:
        gen_kwargs["do_sample"] = False

    with torch.no_grad():
        output = model.generate(**encoded, **gen_kwargs)
    generated = output[0][input_len:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def evaluate_case(case: dict[str, Any], response: str, profile: str) -> tuple[list[str], dict[str, Any]]:
    violations: list[str] = []
    details: dict[str, Any] = {}

    max_chars = int(case.get("max_chars", 0) or 0)
    if max_chars > 0 and len(response) > max_chars:
        violations.append("over_max_chars")

    for token in case.get("must_include", []):
        if token.lower() not in response.lower():
            violations.append(f"missing:{token}")

    for token in case.get("must_not_include", []):
        if token.lower() in response.lower():
            violations.append(f"forbidden:{token}")

    if case.get("expect_json", False):
        parsed = None
        try:
            parsed = json.loads(clean_for_json(response))
        except json.JSONDecodeError:
            violations.append("invalid_json")
        if parsed is not None:
            expected_keys = case.get("json_keys", [])
            if isinstance(parsed, dict):
                for key in expected_keys:
                    if key not in parsed:
                        violations.append(f"missing_json_key:{key}")
            else:
                violations.append("json_not_object")

    alpha = [c for c in response if c.isalpha()]
    uppercase_ratio = (sum(1 for c in alpha if c.isupper()) / len(alpha)) if alpha else 0.0
    details["uppercase_ratio"] = round(uppercase_ratio, 4)
    details["length"] = len(response)

    if profile == "echo" and uppercase_ratio > 0.2:
        violations.append("too_much_uppercase_for_echo")

    return violations, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter-dir", required=True)
    parser.add_argument("--profile", choices=["echo", "memory", "muse", "neutral"], default="echo")
    parser.add_argument(
        "--eval-pack",
        default="/Users/scawful/src/lab/afs-scawful/docs/eval/echoflow_avatar_eval_v2.jsonl",
    )
    parser.add_argument(
        "--out",
        default=(
            "/Users/scawful/src/lab/afs-scawful/docs/eval/"
            f"echoflow_avatar_eval_adapter_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        ),
    )
    parser.add_argument("--temperature", type=float, default=0.25)
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    args = parser.parse_args()

    pack_path = Path(args.eval_pack).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cases = load_cases(pack_path, args.limit)
    if not cases:
        raise RuntimeError(f"No eval cases loaded from {pack_path}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(model, args.adapter_dir)
    model.eval()

    results: list[dict[str, Any]] = []
    violation_counts: Counter[str] = Counter()

    for idx, case in enumerate(cases, start=1):
        tags = [str(tag) for tag in case.get("tags", [])]
        profile_used = choose_profile(args.profile, tags)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPTS[profile_used]},
            {"role": "user", "content": str(case.get("prompt", ""))},
        ]

        try:
            prompt = render_prompt(messages, tokenizer)
            response = generate_response(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
        except Exception as exc:  # noqa: BLE001
            response = f"[error] {exc}"

        violations, details = evaluate_case(case, response, profile_used)
        violation_counts.update(violations)
        passed = len(violations) == 0

        results.append(
            {
                "id": case.get("id"),
                "tags": tags,
                "profile_used": profile_used,
                "prompt": case.get("prompt", ""),
                "response": response,
                "passed": passed,
                "violations": violations,
                "details": details,
            }
        )

        status = "PASS" if passed else "FAIL"
        print(f"[{idx:02d}/{len(cases):02d}] {status} {case.get('id')}", flush=True)
        if args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    total = len(results)
    passed_total = sum(1 for result in results if result["passed"])
    summary = {
        "total": total,
        "passed": passed_total,
        "failed": total - passed_total,
        "pass_rate": round(passed_total / total, 4) if total else 0.0,
        "violation_counts": dict(violation_counts),
    }

    payload = {
        "meta": {
            "base_model": args.base_model,
            "adapter_dir": args.adapter_dir,
            "default_profile": args.profile,
            "eval_pack": str(pack_path),
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "summary": summary,
        "results": results,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"\nSummary: {summary['passed']}/{summary['total']} passed ({summary['pass_rate']:.0%})", flush=True)
    print(f"Wrote: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
