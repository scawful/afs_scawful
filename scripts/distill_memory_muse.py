#!/usr/bin/env python3
"""
distill_memory_muse.py - Distill Memory and Muse training data using cloud teachers.

Teacher models: Gemini 3.1 Pro (deep rationale), Gemini 3 Flash (variations)
Fallback:       Claude Sonnet (if Gemini quota exhausted)

Usage:
  distill_memory_muse.py run [--prompts FILE] [--limit N] [--output FILE]
  distill_memory_muse.py stats [--input FILE]
  distill_memory_muse.py resume [--output FILE]   # Continue from where we left off
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

# ─── Environment ──────────────────────────────────────────────────────────────
# Load .env automatically if python-dotenv is installed.
# To install: pip install python-dotenv
# To configure: copy .env.example to .env and fill in your keys.

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()  # also check cwd
except ImportError:
    pass

# Prefer GOOGLE_API_KEY; fall back to GEMINI_API_KEY alias without emitting a warning.
_gkey = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if _gkey and os.environ.get("GEMINI_API_KEY") and os.environ.get("GOOGLE_API_KEY"):
    os.environ.pop("GEMINI_API_KEY", None)  # avoid duplicate-key warning from google-genai
GOOGLE_API_KEY = _gkey
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

PROMPTS_DEFAULT = (
    Path(__file__).resolve().parents[1]
    / "docs" / "eval" / "memory_muse_distill_prompts_v1.jsonl"
)
OUTPUT_DEFAULT = (
    Path(__file__).resolve().parents[1]
    / "data" / "training_data" / "memory_muse_distill_v1.jsonl"
)

CONCURRENCY = 3  # simultaneous teacher model calls


# ─── Prompt loading ────────────────────────────────────────────────────────────

def load_prompts(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def load_done_ids(output_path: Path) -> set[str]:
    """Return set of instruction fingerprints already written, for resume support.

    Keyed on first 100 chars of instruction text (prompts lack a stable sample_id).
    """
    done: set[str] = set()
    if not output_path.exists():
        return done
    for line in output_path.read_text(errors="replace").splitlines():
        try:
            rec = json.loads(line)
            # Primary key: instruction text fingerprint
            instr = rec.get("instruction", "")
            if instr:
                done.add(instr[:100])
            # Fallback: legacy sample_id / prompt_id
            sid = rec.get("sample_id") or rec.get("_metadata", {}).get("prompt_id")
            if sid:
                done.add(str(sid))
        except Exception:
            pass
    return done


# ─── Provider clients ──────────────────────────────────────────────────────────

async def query_gemini(prompt_text: str, model: str = "gemini-2.5-pro",
                       temperature: float = 0.7) -> tuple[str, str | None]:
    if not GOOGLE_API_KEY:
        return "", "GOOGLE_API_KEY not set — add it to .env or export it"
    try:
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=GOOGLE_API_KEY)
        # gemini-2.5-pro is a thinking model — needs larger token budget
        max_tokens = 8192 if "2.5" in model else 2048
        resp = client.models.generate_content(
            model=model,
            contents=prompt_text,
            config=gtypes.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return resp.text, None
    except Exception as e:
        return "", str(e)


async def query_claude(prompt_text: str, model: str = "claude-sonnet-4-6",
                       temperature: float = 0.7) -> tuple[str, str | None]:
    if not ANTHROPIC_API_KEY:
        return "", (
            "ANTHROPIC_API_KEY not set.\n"
            "Fix: add ANTHROPIC_API_KEY=sk-ant-... to .env in afs-scawful root, or:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return msg.content[0].text, None
    except Exception as e:
        return "", str(e)


async def query_teacher(prompt_text: str, teacher: str,
                        variation: bool = False) -> tuple[str, str, str | None]:
    """Returns (text, model_used, error)."""
    temp = 0.9 if variation else 0.7
    if teacher == "gemini_pro":
        text, err = await query_gemini(prompt_text, "gemini-2.5-pro", temp)
        return text, "gemini-2.5-pro", err
    elif teacher == "gemini_flash":
        text, err = await query_gemini(prompt_text, "gemini-2.0-flash", temp)
        return text, "gemini-2.0-flash", err
    elif teacher == "claude":
        text, err = await query_claude(prompt_text, temperature=temp)
        return text, "claude-sonnet-4-6", err
    else:
        return "", teacher, f"Unknown teacher: {teacher}"


# ─── Sample builder ────────────────────────────────────────────────────────────

@dataclass
class DistillSample:
    instruction: str
    output: str
    input: str
    domain: str
    source: str
    sample_id: str
    teacher_model: str
    timestamp: str
    _metadata: dict


async def distill_prompt(
    prompt_rec: dict,
    semaphore: asyncio.Semaphore,
    output_file,
    also_generate_variation: bool = True,
) -> int:
    """Distill one prompt record. Returns number of samples written."""
    instruction = prompt_rec.get("instruction", "")
    domain = prompt_rec.get("domain", "memory")
    category = prompt_rec.get("_metadata", {}).get("category", "general")
    context_source = prompt_rec.get("_metadata", {}).get("context_source", "")

    # Build full prompt
    prompt_text = instruction
    if context_source:
        prompt_text += f"\n\nContext source: {context_source}"

    written = 0
    async with semaphore:
        # Primary: Gemini Pro (deep, authoritative response)
        text, model_used, err = await query_teacher(prompt_text, "gemini_pro", variation=False)
        if err:
            print(f"  [warn] {err[:80]}", file=sys.stderr)
        if text:
            sample = DistillSample(
                instruction=instruction,
                output=text,
                input="",
                domain=domain,
                source="distillation",
                sample_id=str(uuid.uuid4()),
                teacher_model=model_used,
                timestamp=datetime.now(timezone.utc).isoformat(),
                _metadata={"category": category, "context_source": context_source},
            )
            output_file.write(json.dumps(asdict(sample)) + "\n")
            output_file.flush()
            written += 1

        # Variation: Gemini Flash (higher entropy, alternative recall pattern)
        if also_generate_variation:
            var_prompt = f"[variation] {prompt_text}"
            text2, model2, err2 = await query_teacher(var_prompt, "gemini_flash", variation=True)
            if text2:
                sample2 = DistillSample(
                    instruction=instruction,
                    output=text2,
                    input="",
                    domain=domain,
                    source="distillation",
                    sample_id=str(uuid.uuid4()),
                    teacher_model=model2,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    _metadata={
                        "category": category,
                        "context_source": context_source,
                        "variation": True,
                    },
                )
                output_file.write(json.dumps(asdict(sample2)) + "\n")
                output_file.flush()
                written += 1

    return written


# ─── Subcommands ───────────────────────────────────────────────────────────────

async def _run(args):
    prompts_path = Path(args.prompts) if args.prompts else PROMPTS_DEFAULT
    output_path = Path(args.output) if args.output else OUTPUT_DEFAULT
    limit = args.limit

    if not prompts_path.exists():
        print(f"Prompts file not found: {prompts_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompts = load_prompts(prompts_path)
    done_ids = load_done_ids(output_path)

    pending = [p for p in prompts
               if p.get("instruction", "")[:100] not in done_ids
               and str(p.get("sample_id", "")) not in done_ids]
    if limit:
        pending = pending[:limit]

    print(f"Prompts:  {len(prompts)} total, {len(done_ids)} done, {len(pending)} pending")
    print(f"Output:   {output_path}")
    if not GOOGLE_API_KEY:
        print("[warn] No GOOGLE_API_KEY — will try Claude fallback", file=sys.stderr)
    if not ANTHROPIC_API_KEY and not GOOGLE_API_KEY:
        print("[error] No API keys found. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY in .env", file=sys.stderr)
        sys.exit(1)

    semaphore = asyncio.Semaphore(CONCURRENCY)
    total_written = 0

    with open(output_path, "a") as out:
        tasks = [distill_prompt(p, semaphore, out) for p in pending]
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            n = await coro
            total_written += n
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i+1}/{len(pending)}, {total_written} samples written")

    print(f"\nDone. Wrote {total_written} new samples to {output_path}")


def cmd_run(args):
    asyncio.run(_run(args))


def cmd_stats(args):
    path = Path(args.input) if args.input else OUTPUT_DEFAULT
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    domains: dict[str, int] = {}
    teachers: dict[str, int] = {}
    categories: dict[str, int] = {}
    for r in records:
        d = r.get("domain", "?")
        t = r.get("teacher_model", "?")
        c = r.get("_metadata", {}).get("category", "?")
        domains[d] = domains.get(d, 0) + 1
        teachers[t] = teachers.get(t, 0) + 1
        categories[c] = categories.get(c, 0) + 1
    print(f"Total samples: {len(records)}")
    print(f"\nBy domain:    {domains}")
    print(f"By teacher:   {teachers}")
    print(f"By category:  {dict(list(sorted(categories.items(), key=lambda x: -x[1]))[:8])}")


def main():
    parser = argparse.ArgumentParser(description="Memory/Muse distillation pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run distillation")
    p_run.add_argument("--prompts", metavar="FILE")
    p_run.add_argument("--output", "-o", metavar="FILE")
    p_run.add_argument("--limit", type=int, metavar="N")

    p_stats = sub.add_parser("stats", help="Dataset statistics")
    p_stats.add_argument("--input", "-i", metavar="FILE")

    args = parser.parse_args()
    {"run": cmd_run, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    main()
