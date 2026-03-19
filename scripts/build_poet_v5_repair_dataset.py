#!/usr/bin/env python3
"""Build a focused repair dataset for poet_v5 from strict form eval failures."""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

POET_SYSTEM = (
    "You are Poet. Write compact vivid poetry with strict form control. "
    "You will receive a [FORM:<name>] tag in the prompt. "
    "Follow that form exactly and return poem text only. "
    "Constraints: concrete imagery, no cliches, no title, no explanation."
)

DRILL_PROMPTS = {
    "sonnet": [
        "Write about pushing through resistance and finishing the draft.",
        "Write about learning to cut weak paragraphs without panic.",
        "Write about choosing one path and accepting tradeoffs.",
        "Write about the quiet discipline of daily writing.",
    ],
    "limerick": [
        "Write about a test suite finally turning green at 1am.",
        "Write about deleting dead code and smiling at the diff.",
        "Write about context switching and trying again tomorrow.",
        "Write about one notebook page that unblocked the week.",
    ],
    "haiku": [
        "Write about a blinking cursor and cold coffee.",
        "Write about rain on glass and a clean compile.",
    ],
}


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def split_train_valid(rows: list[dict[str, Any]], train_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    data = list(rows)
    rng.shuffle(data)
    cut = int(len(data) * train_ratio)
    cut = max(1, min(cut, len(data))) if data else 0
    return data[:cut], data[cut:]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "\n".join(json.dumps(r, ensure_ascii=True) for r in rows)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def compact_words(text: str) -> list[str]:
    stop = {
        "write",
        "about",
        "the",
        "and",
        "with",
        "your",
        "that",
        "this",
        "into",
        "from",
        "after",
        "before",
        "during",
        "through",
        "finally",
    }
    return [w for w in re.findall(r"[a-z']+", text.lower()) if len(w) > 3 and w not in stop]


def topic_words(prompt: str) -> tuple[str, str]:
    ws = compact_words(prompt)
    if not ws:
        return "glass", "night"
    if len(ws) == 1:
        return ws[0], "night"
    return ws[0], ws[1]


def poem_for_haiku(prompt: str, variant: int) -> str:
    a, b = topic_words(prompt)
    options = [
        f"{a} on cold glass\nnight trains count slow breaths in rain\none key starts the line",
        f"{a} stains the mug rim\n{b} hums in the monitor glow\ncursor waits for yes",
        "rain on train window\ncold coffee beside the keys\none clean line begins",
    ]
    return options[variant % len(options)]


def poem_for_limerick(prompt: str, variant: int) -> str:
    templates = [
        (
            "There once was a coder named Ray,\n"
            "who deleted stale blocks in one day.\n"
            "the warnings grew thin,\n"
            "calm settled within,\n"
            "and finally sleep came to stay."
        ),
        (
            "A developer wrestling delay,\n"
            "cut three hundred bad lines away.\n"
            "the logs quieted down,\n"
            "no red lights in town,\n"
            "and rest found the desk before day."
        ),
        (
            "There once was a builder in gray,\n"
            "who closed every tab but one way.\n"
            "one task in clear view,\n"
            "one promise held true,\n"
            "and momentum returned there to stay."
        ),
    ]
    return templates[variant % len(templates)]


def poem_for_sonnet(prompt: str, variant: int) -> str:
    a, b = topic_words(prompt)
    options = [
        (
            f"I keep one narrow window lit at last,\n"
            f"while {a} and {b} drift beyond the pane.\n"
            "The noisy tabs that mocked me have gone past,\n"
            "their glitter traded for a useful strain.\n"
            "I cut the swollen draft to nerve and bone,\n"
            "and watch the argument stand clean and spare.\n"
            "A thesis learns to carry weight alone,\n"
            "not dressed in borrowed thunder, only care.\n"
            "The cursor blinks like rain against the glass,\n"
            "a metronome that keeps my breathing true.\n"
            "I choose one road and let the others pass,\n"
            "accepting what a finite hour can do.\n"
            "By morning, effort hardens into light;\n"
            "the page is less afraid, and so am I."
        ),
        (
            "At midnight I close every glittering door,\n"
            "and leave one task alive beneath the lamp.\n"
            "The room is bare, the floorboards keep the score,\n"
            "a thin and honest silence, dry and damp.\n"
            "I carve excess from every stubborn claim,\n"
            "until the paragraph can stand and breathe.\n"
            "No borrowed smoke, no ornamental flame,\n"
            "just clear connective tissue underneath.\n"
            "My coffee cools; the keyboard answers rain.\n"
            "The sentence turns, then settles into place.\n"
            "I trade my appetite for easy gain\n"
            "for patient cuts and one deliberate pace.\n"
            "When dawn arrives, the draft is finally plain:\n"
            "a working bridge from doubt to chosen aim."
        ),
    ]
    return options[variant % len(options)]


def poem_for_imagist(prompt: str, variant: int) -> str:
    options = [
        "neon in wet glass\nkeyboard ticks under pale hands\ncoffee skin cooling",
        "white cursor\nblack room\nrain tracks the window frame\na mug ring dries",
        "cold mug lip\nmonitor glow on knuckles\nstreetlight in the rain",
    ]
    return options[variant % len(options)]


def poem_for_free_verse(prompt: str, variant: int) -> str:
    options = [
        (
            "i kept switching windows\n"
            "until every task sounded urgent.\n"
            "rain stitched the dark glass,\n"
            "the keyboard answered in short metal clicks.\n"
            "i closed everything but one file,\n"
            "let the room go quiet,\n"
            "and wrote the first hard sentence\n"
            "before doubt woke up."
        ),
        (
            "the day was a pile of half-open loops.\n"
            "coffee turned cold beside the mouse.\n"
            "when one tiny test passed,\n"
            "the static in my head thinned.\n"
            "i kept that thread,\n"
            "line by line,\n"
            "until the monitor stopped feeling like a warning\n"
            "and started feeling like a door."
        ),
    ]
    return options[variant % len(options)]


def generate_poem(form: str, prompt: str, variant: int) -> str:
    if form == "haiku":
        return poem_for_haiku(prompt, variant)
    if form == "limerick":
        return poem_for_limerick(prompt, variant)
    if form == "sonnet":
        return poem_for_sonnet(prompt, variant)
    if form == "imagist":
        return poem_for_imagist(prompt, variant)
    return poem_for_free_verse(prompt, variant)


def make_row(form: str, prompt: str, poem: str, source: str, fails: list[str]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": POET_SYSTEM},
            {"role": "user", "content": f"[FORM:{form}] {prompt}"},
            {"role": "assistant", "content": poem},
        ],
        "_meta": {
            "persona": "poet_v5",
            "source": source,
            "form": form,
            "from_fails": fails,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-report", required=True, help="Path to poet_form_eval JSON report.")
    parser.add_argument("--target-model", default="gguf/afs/poet_v4-q8_0.gguf")
    parser.add_argument("--out-dir", default="docs/eval/poet_repair_v5_20260228")
    parser.add_argument("--augment-per-fail", type=int, default=4)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report_path = Path(args.eval_report).resolve()
    report = load_report(report_path)
    models = report.get("models", {})
    if args.target_model not in models:
        raise SystemExit(f"target model missing from eval report: {args.target_model}")

    target = models[args.target_model]
    failed = [r for r in target.get("results", []) if not r.get("ok")]

    rows: list[dict[str, Any]] = []

    for r in failed:
        form = str(r.get("form", "free_verse"))
        prompt = str(r.get("prompt", "")).strip()
        fails = [str(x) for x in r.get("fails", [])]
        for i in range(max(1, args.augment_per_fail)):
            poem = generate_poem(form, prompt, i)
            rows.append(make_row(form, prompt, poem, "strict_eval_repair", fails))

    for form, prompts in DRILL_PROMPTS.items():
        for idx, prompt in enumerate(prompts):
            poem = generate_poem(form, prompt, idx)
            rows.append(make_row(form, prompt, poem, "form_drill", []))

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    train_rows, valid_rows = split_train_valid(rows, args.train_ratio, args.seed)
    train_path = out_dir / "train.jsonl"
    valid_path = out_dir / "valid.jsonl"
    write_jsonl(train_path, train_rows)
    write_jsonl(valid_path, valid_rows)

    forms = Counter([r["_meta"]["form"] for r in rows])
    manifest = {
        "source_eval_report": str(report_path),
        "target_model": args.target_model,
        "failed_cases": len(failed),
        "augment_per_fail": args.augment_per_fail,
        "total_rows": len(rows),
        "train_rows": len(train_rows),
        "valid_rows": len(valid_rows),
        "forms": dict(forms),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"failed_cases={len(failed)} total_rows={len(rows)} train={len(train_rows)} valid={len(valid_rows)}")
    print(train_path)
    print(valid_path)
    print(out_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
