#!/usr/bin/env python3
import argparse
import datetime
import json
import subprocess
from pathlib import Path

ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODEL = "gguf/afs/conductor_v1-q8_0.gguf"
SYSTEM = "You are The Conductor. Output only valid JSON defining a DAG handoff plan with nodes and dependencies."
PROMPTS = [
    "plan a 3-agent swarm to fix a failing ci pipeline in a python repo and ship a patch today.",
    "design a DAG for migrating a sqlite schema with zero downtime and rollback support.",
    "build an agent plan for investigating a production memory leak and delivering a verified fix.",
    "create a DAG to run nightly evals, collect failures, generate repair data, and trigger micro-fix training.",
    "orchestrate benchmark runs for three models and produce a promotion recommendation.",
    "design a swarm handoff for data QA: dedupe, schema validate, privacy scan, and publish.",
    "decompose an end-to-end workflow for thesis-style essay writing with research and outline agents.",
    "plan a multi-agent workflow to triage and clear a 200-item personal task backlog in one week.",
]


def call(model: str, prompt: str, temperature: float = 0.0) -> tuple[str | None, str | None]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 500,
    }
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(payload),
            ENDPOINT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None, f"curl_error:{proc.stderr.strip()}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, "api_non_json"
    if "error" in data:
        return None, f"api_error:{data['error']}"
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content, None


def extract_json(text: str):
    cleaned = text.strip()
    cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(cleaned)):
            ch = cleaned[idx]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : idx + 1])
                    except json.JSONDecodeError:
                        return None
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Conductor JSON smoke eval")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--out",
        default="docs/eval/conductor_json_smoke_freeform_20260226.json",
        help="Output report path",
    )
    args = parser.parse_args()

    passed = 0
    results = []
    for prompt in PROMPTS:
        response, err = call(args.model, prompt, temperature=0.0)
        ok = False
        reason = ""
        parsed = None
        if err:
            reason = err
        else:
            parsed = extract_json(response or "")
            if parsed is None:
                reason = "json_parse_error"
            elif isinstance(parsed, dict):
                keys = set(parsed.keys())
                ok = bool({"nodes", "agents", "dag", "steps"} & keys)
                if not ok:
                    reason = "json_missing_plan_keys"
            elif isinstance(parsed, list):
                ok = len(parsed) > 0
                if not ok:
                    reason = "json_empty_list"
            else:
                reason = "json_invalid_top_level"
        if ok:
            passed += 1
        results.append(
            {
                "prompt": prompt,
                "ok": ok,
                "reason": reason,
                "response": response,
                "parsed_type": type(parsed).__name__ if parsed is not None else None,
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "meta": {
                    "date_utc": datetime.datetime.now(datetime.UTC).isoformat(),
                    "model": args.model,
                    "cases": len(PROMPTS),
                    "passed": passed,
                    "pass_rate": round(passed / len(PROMPTS), 4),
                },
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"pass={passed}/{len(PROMPTS)}")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
