#!/usr/bin/env python3
"""Run EchoFlow avatar eval pack against an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    cmd = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "-H",
        "Content-Type: application/json",
        "-d",
        json.dumps(payload),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or f"curl exited {proc.returncode}"
        raise RuntimeError(stderr)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        snippet = proc.stdout[:240].replace("\n", " ")
        raise RuntimeError(f"invalid_json_response: {snippet}") from exc


def call_openai(
    endpoint: str,
    model: str,
    prompt: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    strict_json: bool,
) -> str:
    base = endpoint.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if strict_json:
        payload["response_format"] = {"type": "json_object"}

    data = post_json(f"{base}/chat/completions", payload, timeout)
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


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
    parser.add_argument("--endpoint", default="http://medical-mechanica:1234")
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", choices=["echo", "memory", "muse", "neutral"], default="echo")
    parser.add_argument(
        "--eval-pack",
        default="/Users/scawful/src/lab/echoflow/evals/echoflow_avatar_eval_v1.jsonl",
    )
    parser.add_argument(
        "--out",
        default=(
            "/Users/scawful/src/lab/afs-scawful/docs/eval/"
            f"echoflow_avatar_eval_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        ),
    )
    parser.add_argument("--temperature", type=float, default=0.25)
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--strict-json-response-format", action="store_true")
    args = parser.parse_args()

    pack_path = Path(args.eval_pack).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cases = load_cases(pack_path, args.limit)
    if not cases:
        raise RuntimeError(f"No eval cases loaded from {pack_path}")

    results: list[dict[str, Any]] = []
    violation_counts: Counter[str] = Counter()

    for idx, case in enumerate(cases, start=1):
        tags = [str(tag) for tag in case.get("tags", [])]
        profile_used = choose_profile(args.profile, tags)
        system_prompt = SYSTEM_PROMPTS[profile_used]
        prompt = str(case.get("prompt", ""))

        try:
            response = call_openai(
                endpoint=args.endpoint,
                model=args.model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                strict_json=bool(case.get("expect_json")) and args.strict_json_response_format,
            )
        except Exception as exc:  # noqa: BLE001
            lower = str(exc).lower()
            if "timed out" in lower:
                response = "[timeout]"
            else:
                response = f"[error] {exc}"

        violations, details = evaluate_case(case, response, profile_used)
        violation_counts.update(violations)
        passed = len(violations) == 0

        results.append(
            {
                "id": case.get("id"),
                "tags": tags,
                "profile_used": profile_used,
                "prompt": prompt,
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
            "endpoint": args.endpoint,
            "model": args.model,
            "default_profile": args.profile,
            "eval_pack": str(pack_path),
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "timeout": args.timeout,
            "strict_json_response_format": args.strict_json_response_format,
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
