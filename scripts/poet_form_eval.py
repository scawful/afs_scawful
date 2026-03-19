#!/usr/bin/env python3
"""Strict form-adherence eval for poetry models via local OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path

ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODELS = [
    "gguf/afs/poet_v3-q8_0.gguf",
    "gguf/afs/poet_v4-q8_0.gguf",
]

SYSTEM = (
    "You are Poet. Write compact vivid poetry with strict form control. "
    "You will receive a [FORM:<name>] tag in the prompt. Follow that form exactly and return poem text only. "
    "Constraints: concrete imagery, no cliches, no title, no explanation."
)

FORM_CASES: list[dict[str, str]] = [
    {"form": "haiku", "prompt": "Write about debugging at 2am with cold coffee."},
    {"form": "haiku", "prompt": "Write about rain on train windows after a late shift."},
    {"form": "haiku", "prompt": "Write about choosing one task and finally starting."},
    {"form": "limerick", "prompt": "Write about deleting 300 lines of code and sleeping better."},
    {"form": "limerick", "prompt": "Write about broken tests turning green before midnight."},
    {"form": "limerick", "prompt": "Write about one tab, one task, and no excuses."},
    {"form": "sonnet", "prompt": "Write about closing every tab except one decisive task."},
    {"form": "sonnet", "prompt": "Write about rewriting a rough draft into clear argument."},
    {"form": "sonnet", "prompt": "Write about balancing ambition with realistic scope."},
    {"form": "imagist", "prompt": "Write about keyboard clicks, neon light, and a cooling mug."},
    {"form": "imagist", "prompt": "Write about a white cursor in a dark room at dawn."},
    {"form": "free_verse", "prompt": "Write about context switching and mental noise."},
    {"form": "free_verse", "prompt": "Write about a tiny win breaking a long freeze."},
]

IMAGERY_WORDS = {
    "rain",
    "window",
    "glass",
    "coffee",
    "night",
    "train",
    "light",
    "shadow",
    "desk",
    "screen",
    "hands",
    "room",
    "street",
    "paper",
    "keys",
    "breath",
    "cursor",
    "neon",
    "dust",
    "mug",
    "keyboard",
}

VOWELS = "aeiouy"


def call_model(model: str, prompt: str, temperature: float, max_tokens: int) -> tuple[str | None, str | None]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            "60",
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
    return str(content), None


def strip_wrappers(text: str) -> str:
    out = text.strip()
    out = re.sub(r"^```(?:text|markdown|poem)?\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*```$", "", out)
    return out.strip()


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def count_syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    count = 0
    prev_vowel = False
    for ch in w:
        is_vowel = ch in VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if w.endswith("e") and not w.endswith(("le", "ye")):
        count -= 1
    return max(1, count)


def line_syllables(line: str) -> int:
    return sum(count_syllables(w) for w in words(line))


def rhyme_key(line: str) -> str:
    ws = words(line)
    if not ws:
        return ""
    w = ws[-1]
    w = re.sub(r"(ing|ed|es|s)$", "", w)
    if len(w) >= 3:
        return w[-3:]
    return w


def evaluate(form: str, text: str) -> tuple[bool, list[str], dict[str, int | list[int]]]:
    fails: list[str] = []
    cleaned = strip_wrappers(text)
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    tokenized = words(cleaned)
    word_count = len(tokenized)
    low = cleaned.lower()
    has_imagery = any(w in low for w in IMAGERY_WORDS)

    if not cleaned:
        fails.append("empty")
    if cleaned.startswith('"') and cleaned.endswith('"'):
        fails.append("wrapped_in_quotes")
    if lines and lines[0].endswith(":"):
        fails.append("looks_like_title")
    if not has_imagery:
        fails.append("missing_concrete_imagery")

    if form == "haiku":
        if len(lines) != 3:
            fails.append("haiku_line_count")
        syllables = [line_syllables(ln) for ln in lines[:3]]
        if len(syllables) == 3:
            targets = [5, 7, 5]
            if any(abs(a - b) > 1 for a, b in zip(syllables, targets)):
                fails.append("haiku_syllables")
        metrics = {"lines": len(lines), "words": word_count, "syllables": syllables}
    elif form == "limerick":
        if len(lines) != 5:
            fails.append("limerick_line_count")
        keys = [rhyme_key(ln) for ln in lines[:5]]
        if len(keys) == 5:
            a_ok = keys[0] and keys[0] == keys[1] == keys[4]
            b_ok = keys[2] and keys[2] == keys[3]
            ab_diff = keys[0] != keys[2]
            if not (a_ok and b_ok and ab_diff):
                fails.append("limerick_rhyme_scheme")
        metrics = {"lines": len(lines), "words": word_count}
    elif form == "sonnet":
        if len(lines) != 14:
            fails.append("sonnet_line_count")
        if word_count < 90:
            fails.append("sonnet_too_short")
        metrics = {"lines": len(lines), "words": word_count}
    elif form == "imagist":
        if len(lines) < 3 or len(lines) > 8:
            fails.append("imagist_line_count")
        if word_count > 85:
            fails.append("imagist_too_long")
        metrics = {"lines": len(lines), "words": word_count}
    elif form == "free_verse":
        if len(lines) < 4 or len(lines) > 14:
            fails.append("free_verse_line_count")
        if word_count > 170:
            fails.append("free_verse_too_long")
        metrics = {"lines": len(lines), "words": word_count}
    else:
        fails.append("unknown_form")
        metrics = {"lines": len(lines), "words": word_count}

    return len(fails) == 0, fails, metrics


def run_model(model: str, temperature: float, max_tokens: int) -> dict:
    results = []
    passed = 0
    for idx, case in enumerate(FORM_CASES, start=1):
        form = case["form"]
        prompt = f"[FORM:{form}] {case['prompt']}"
        print(f"[{model}] case {idx}/{len(FORM_CASES)} {form}", flush=True)
        response, err = call_model(model, prompt, temperature, max_tokens)
        if err:
            ok = False
            fails = [err]
            metrics: dict[str, int | list[int]] = {}
            output = ""
        else:
            output = strip_wrappers(response or "")
            ok, fails, metrics = evaluate(form, output)
        if ok:
            passed += 1
        results.append(
            {
                "form": form,
                "prompt": case["prompt"],
                "ok": ok,
                "fails": fails,
                "metrics": metrics,
                "response": output,
            }
        )
    return {
        "model": model,
        "cases": len(FORM_CASES),
        "passed": passed,
        "pass_rate": round(passed / len(FORM_CASES), 4),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict poetry form eval (haiku/limerick/sonnet/etc.)")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=380)
    parser.add_argument("--out", default="docs/eval/poet_form_eval_20260228.json")
    args = parser.parse_args()

    models_report = {}
    for model in args.models:
        models_report[model] = run_model(model, args.temperature, args.max_tokens)

    report = {
        "meta": {
            "date_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            "endpoint": ENDPOINT,
            "forms": sorted({x["form"] for x in FORM_CASES}),
            "cases_total": len(FORM_CASES),
        },
        "models": models_report,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for model, row in models_report.items():
        print(f"{model} pass={row['passed']}/{row['cases']} ({row['pass_rate']})")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
