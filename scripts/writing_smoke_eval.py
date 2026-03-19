#!/usr/bin/env python3
import argparse
import datetime
import json
import subprocess
from pathlib import Path

ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_POET = "gguf/afs/poet_v2-q8_0.gguf"
DEFAULT_ESSAYIST = "gguf/afs/essayist_v2-q8_0.gguf"

POET_SYSTEM = "You are Poet. Write vivid, concrete poetry with controlled rhythm."
ESSAY_SYSTEM = "You are Essayist. Produce thesis-driven essays with clear structure."

POET_PROMPTS = [
    "Write a short poem about choosing one task and finally starting.",
    "Write a poem about rain on train windows after a long day of work.",
    "Turn this into a poem: I kept polishing details to avoid the hard decision.",
    "Write a compact poem about a quiet room and a glowing monitor.",
    "Write a poem about deleting code and feeling relief.",
    "Write a short poem that ends with one concrete action for tomorrow.",
    "Write a poem about context switching and mental noise.",
    "Write a poem about a tiny win that broke a long freeze.",
]

ESSAY_PROMPTS = [
    "Write a concise essay on why irreversible first actions reduce procrastination.",
    "Write an essay on balancing maintenance work and strategic work.",
    "Write an essay arguing for explicit done criteria in task systems.",
    "Write an essay on context-switching costs in solo engineering.",
    "Write an essay about why documenting decisions improves execution quality.",
    "Write an essay on converting rough notes into coherent long-form arguments.",
    "Write an essay on why planning comfort can become avoidance behavior.",
    "Write an essay on how checkpoints reduce cognitive load in complex projects.",
]

POET_IMAGERY_WORDS = {
    "rain", "window", "glass", "coffee", "night", "train", "light", "shadow",
    "desk", "screen", "hands", "room", "street", "paper", "keys", "breath",
}


def call_model(model: str, system: str, prompt: str, max_tokens: int, temperature: float) -> tuple[str | None, str | None]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
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
            "45",
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
    if not isinstance(content, str):
        content = str(content)
    return content, None


def eval_poet(text: str) -> tuple[bool, list[str]]:
    fails: list[str] = []
    stripped = text.strip()
    if len(stripped) < 80:
        fails.append("too_short")
    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if len(lines) < 4:
        fails.append("not_poetic_line_structure")
    low = stripped.lower()
    if not any(word in low for word in POET_IMAGERY_WORDS):
        fails.append("missing_concrete_imagery")
    if len(stripped) > 1400:
        fails.append("too_long")
    return (len(fails) == 0), fails


def eval_essay(text: str) -> tuple[bool, list[str]]:
    fails: list[str] = []
    stripped = text.strip()
    if len(stripped) < 700:
        fails.append("too_short")
    paragraphs = [p.strip() for p in stripped.split("\n\n") if p.strip()]
    if len(paragraphs) < 3:
        fails.append("insufficient_paragraphs")
    low = stripped.lower()
    if not any(k in low for k in ["thesis", "in conclusion", "conclusion", "therefore", "argument"]):
        fails.append("missing_argument_signals")
    if len(stripped) > 9000:
        fails.append("too_long")
    return (len(fails) == 0), fails


def run_suite(kind: str, model: str, prompts: list[str]) -> dict:
    results = []
    passed = 0
    for i, prompt in enumerate(prompts, start=1):
        print(f"[{kind}] case {i}/{len(prompts)}", flush=True)
        if kind == "poet":
            text, err = call_model(model, POET_SYSTEM, prompt, max_tokens=450, temperature=0.8)
            if err:
                ok = False
                fails = [err]
                out = ""
            else:
                out = text or ""
                ok, fails = eval_poet(out)
        else:
            text, err = call_model(model, ESSAY_SYSTEM, prompt, max_tokens=1200, temperature=0.45)
            if err:
                ok = False
                fails = [err]
                out = ""
            else:
                out = text or ""
                ok, fails = eval_essay(out)

        if ok:
            passed += 1
        results.append(
            {
                "prompt": prompt,
                "ok": ok,
                "fails": fails,
                "chars": len(out),
                "response": out,
            }
        )

    return {
        "model": model,
        "cases": len(prompts),
        "passed": passed,
        "pass_rate": round(passed / len(prompts), 4) if prompts else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke eval for poet/essayist writing models")
    parser.add_argument("--model-poet", default=DEFAULT_POET)
    parser.add_argument("--model-essayist", default=DEFAULT_ESSAYIST)
    parser.add_argument("--out", default="docs/eval/writing_smoke_eval_20260228.json")
    args = parser.parse_args()

    poet = run_suite("poet", args.model_poet, POET_PROMPTS)
    essay = run_suite("essayist", args.model_essayist, ESSAY_PROMPTS)
    report = {
        "meta": {
            "date_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            "endpoint": ENDPOINT,
        },
        "poet": poet,
        "essayist": essay,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"poet_pass={poet['passed']}/{poet['cases']}")
    print(f"essayist_pass={essay['passed']}/{essay['cases']}")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
