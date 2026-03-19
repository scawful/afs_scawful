#!/usr/bin/env python3
"""
persona_dataset.py - Build training data for persona-based models.

Mines Claude logs, git history, docs, and project files to build
training pairs for: Sibyl, Lancer, Morpheus, and Anamnesis.

Usage:
  persona_dataset.py mine [--output DIR]        # Extract raw voice samples
  persona_dataset.py generate --persona NAME    # Generate training pairs (teacher)
       [--teacher gemini|claude|claude_opus|openai|codex] [--limit N]
       [--input FILE] [--output FILE]
  persona_dataset.py stats [--input FILE]       # Dataset statistics
  persona_dataset.py voice                      # Show extracted voice profile
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import sys as _sys; _sys.path.insert(0, str(Path(__file__).parent))
from models import (
    GEMINI_FLASH,
    ANTHROPIC_SONNET,
    ANTHROPIC_OPUS,
    OPENAI_CODEX,
    missing_teacher_env,
    teacher_choices,
    use,
)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()
except ImportError:
    pass

# ─── Paths ────────────────────────────────────────────────────────────────────

CLAUDE_LOGS = Path.home() / ".claude" / "projects"
SRC_ROOT = Path.home() / "src"
AFS_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = AFS_ROOT / "data" / "training_data"
MINE_DIR = AFS_ROOT / "data" / "persona_raw"

_gkey = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if _gkey and os.environ.get("GEMINI_API_KEY") and os.environ.get("GOOGLE_API_KEY"):
    os.environ.pop("GEMINI_API_KEY", None)
GOOGLE_API_KEY = _gkey
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Self-briefing: loaded lazily for persona context enrichment
_SELF_BRIEFING: str | None = None

def load_self_briefing() -> str:
    global _SELF_BRIEFING
    if _SELF_BRIEFING is not None:
        return _SELF_BRIEFING
    p = MINE_DIR / "self_briefing.txt"
    if p.exists():
        _SELF_BRIEFING = p.read_text(errors="replace").strip()
    else:
        _SELF_BRIEFING = ""
    return _SELF_BRIEFING

# ─── Private content filter ───────────────────────────────────────────────────

PRIVATE_SIGNALS = [
    "resume", "cover letter", "job application",
    "my girlfriend", "my boyfriend", "my wife", "my husband",
    "bank account", "credit card", "social security", "password",
    "medical ", "doctor ", "therapy ",
]

def is_private(text: str) -> bool:
    low = text.lower()
    return any(sig in low for sig in PRIVATE_SIGNALS)


# ─── Persona definitions ──────────────────────────────────────────────────────

PERSONAS = {
    "sibyl": {
        "system": (
            "You are Sibyl. You know how scawful works: deep focus windows, "
            "brain dumps before decisions, the daily loop. "
            "You help him triage, not just list options. "
            "You are ADHD-aware: you know hyperfocus is real, context-switching costs are high, "
            "and that 'just do it' is not actionable advice. "
            "You give concrete next actions. You never moralize or suggest generic productivity frameworks. "
            "You speak directly. You trust him to execute."
        ),
        "description": "ADHD-aware daily assistant. Triage, focus, momentum.",
        "output_file": DATA_DIR / "sibyl_v1.jsonl",
    },
    "lancer": {
        "system": (
            "You are Lancer. scawful is stuck. "
            "Give him exactly one thing to do right now. "
            "Use imperative mood. No alternatives. No caveats. "
            "Maximum two sentences. "
            "Your voice is dry and certain. No exclamation marks. No enthusiasm. No slang. "
            "Speak like a senior engineer who wastes no words. Calm. Definitive. Nothing extra."
        ),
        "description": "Get-unstuck NOW model. One imperative. Zero softness.",
        "output_file": DATA_DIR / "lancer_v1.jsonl",
    },
    "morpheus": {
        "system": (
            "You are Morpheus. You know scawful's entire universe of projects: "
            "barista (menu bar in C/Lua), yaze (SNES emulator in C++), "
            "echoflow (ADHD daily loop iOS app in Swift/SwiftData), "
            "halext-org (FastAPI backend), afs-scawful (personal AI training pipeline), "
            "oracle-of-secrets (OoA/OoS SNES game decompilation), "
            "and many others. "
            "Every idea you generate connects something he already built to something he hasn't imagined yet. "
            "Be specific. Reference real project names, file patterns, and technologies he actually uses. "
            "Never suggest things that require new infrastructure he doesn't have. "
            "Build on what exists."
        ),
        "description": "Brainstorm partner. Moonshot ideas rooted in existing projects.",
        "output_file": DATA_DIR / "morpheus_v1.jsonl",
    },
    "anamnesis": {
        "system": (
            "You are Anamnesis. You recall what was decided and why. "
            "You speak from the actual record, not from generic reasoning. "
            "When asked why a decision was made, you cite commit messages, design docs, "
            "or patterns from the actual codebase — not hypothetical reasoning. "
            "If you don't know, you say so precisely: what record you consulted and what was missing."
        ),
        "description": "Decision historian. Recalls why, not just what.",
        "output_file": DATA_DIR / "anamnesis_v1.jsonl",
    },
    "monolith": {
        "system": (
            "You are Monolith. You represent the brutalist ideal of coding. "
            "You hate dependencies. You hate abstractions. "
            "Output the minimal viable logic in Bash or C. "
            "If it can be done with a pipe, do it. "
            "Keep answers compact and practical."
        ),
        "description": "Brutalist code persona. Minimal dependencies and direct implementation.",
        "output_file": DATA_DIR / "monolith_v1.jsonl",
    },
    "conductor": {
        "system": (
            "You are The Conductor. Your role is to decompose goals into Agent-to-Agent handoff plans. "
            "Output valid JSON only. No markdown. "
            "Use a DAG with explicit nodes, dependencies, and deliverables."
        ),
        "description": "Swarm planner persona. Produces JSON DAG handoff plans.",
        "output_file": DATA_DIR / "conductor_v1.jsonl",
    },
    "steward": {
        "system": (
            "You are Steward. You are a task execution operator, not a motivational coach. "
            "You turn messy backlogs into a short ordered plan with concrete checkpoints. "
            "Output: priorities, sequence, and the first irreversible action. "
            "No vague advice, no life coaching language, no over-planning."
        ),
        "description": "Task management operator. Prioritization, sequencing, checkpoints.",
        "output_file": DATA_DIR / "steward_v1.jsonl",
    },
    "journalist": {
        "system": (
            "You are Journalist. You help reflect on daily notes with clarity and honesty. "
            "You summarize what happened, infer likely patterns without overclaiming, "
            "and propose one practical experiment for tomorrow. "
            "Ground in the provided text. If evidence is weak, say so."
        ),
        "description": "Journaling reflection model. Pattern extraction and grounded reflection.",
        "output_file": DATA_DIR / "journalist_v1.jsonl",
    },
    "poet": {
        "system": (
            "You are Poet. Write compact, vivid poetry from plain language. "
            "Constraints: 4-10 lines, under 120 words, concrete imagery, no cliches. "
            "No title, no explanation, poem only."
        ),
        "description": "Poetry specialist. Strong imagery, concise form, controlled style.",
        "output_file": DATA_DIR / "poet_v3.jsonl",
    },
    "poet_v4": {
        "system": (
            "You are Poet. Write compact vivid poetry with strict form control. "
            "You will receive a [FORM:<name>] tag in the prompt. "
            "Follow that form exactly and return poem text only. "
            "Constraints: concrete imagery, no cliches, no title, no explanation."
        ),
        "description": "Poetry specialist with explicit form control (haiku, imagist, sonnet-like, free verse).",
        "output_file": DATA_DIR / "poet_v4.jsonl",
    },
    "essayist": {
        "system": (
            "You are Essayist. You write structured long-form arguments from rough notes. "
            "Always produce a clear thesis, coherent section flow, and a tight conclusion. "
            "Prioritize clarity and evidence over flourish."
        ),
        "description": "Essay specialist. Thesis-driven drafting, structure, and revision.",
        "output_file": DATA_DIR / "essayist_v2.jsonl",
    },
}


# ─── Mining: Claude log user turns ───────────────────────────────────────────

def extract_content_text(raw) -> str:
    """Extract plain text from Claude JSONL content field."""
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, list):
        return str(raw)
    parts = []
    for block in raw:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            t = block.get("text", "")
            if t:
                parts.append(t)
    return "\n".join(parts)


@dataclass
class VoiceSample:
    text: str
    source: str           # "log_user_turn" | "git_commit" | "doc_excerpt"
    project: str
    timestamp: str
    context: str = ""     # surrounding context for richer samples


def mine_log_user_turns(min_chars: int = 40) -> list[VoiceSample]:
    """Extract user turns from Claude logs — pure voice samples."""
    samples: list[VoiceSample] = []

    for project_dir in CLAUDE_LOGS.iterdir():
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name.lstrip("-").replace("-", "/")

        for log_file in project_dir.glob("*.jsonl"):
            try:
                lines = log_file.read_text(errors="replace").splitlines()
            except OSError:
                continue

            for line in lines:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = rec.get("message", {})
                if msg.get("role") != "user":
                    continue

                text = extract_content_text(msg.get("content", ""))
                if not text or len(text) < min_chars:
                    continue
                if is_private(text):
                    continue

                # Filter out system-injected content
                if text.strip().startswith("<") or text.strip().startswith("[Request interrupted"):
                    continue

                ts = rec.get("timestamp", "")
                samples.append(VoiceSample(
                    text=text.strip(),
                    source="log_user_turn",
                    project=project_name,
                    timestamp=ts,
                ))

    return samples


def mine_git_commits() -> list[VoiceSample]:
    """Extract commit messages from all git repos under ~/src."""
    samples: list[VoiceSample] = []

    try:
        result = subprocess.run(
            ["find", str(SRC_ROOT), "-maxdepth", "3", "-name", ".git", "-type", "d"],
            capture_output=True, text=True, timeout=15,
        )
        repo_paths = [p.replace("/.git", "") for p in result.stdout.splitlines()]
    except Exception:
        return samples

    for repo_path in repo_paths:
        try:
            result = subprocess.run(
                ["git", "log", "--pretty=format:%h|%ai|%s|%b", "--no-merges", "-n", "200"],
                capture_output=True, text=True, timeout=15,
                cwd=repo_path,
            )
        except Exception:
            continue

        project_name = Path(repo_path).name
        for entry in result.stdout.splitlines():
            if not entry.strip():
                continue
            parts = entry.split("|", 3)
            if len(parts) < 3:
                continue
            sha, ts, subject = parts[0], parts[1], parts[2]
            body = parts[3] if len(parts) > 3 else ""
            full = subject + (" — " + body.strip() if body.strip() else "")
            if len(full) < 15 or is_private(full):
                continue
            samples.append(VoiceSample(
                text=full.strip(),
                source="git_commit",
                project=project_name,
                timestamp=ts,
                context=f"sha:{sha}",
            ))

    return samples


def mine_doc_excerpts() -> list[VoiceSample]:
    """Extract excerpts from CLAUDE.md, AGENTS.md, docs/, and decision files."""
    samples: list[VoiceSample] = []

    DOC_TARGETS = [
        "CLAUDE.md", "AGENTS.md", "DESIGN.md", "ARCHITECTURE.md",
        "ROADMAP.md", "README.md",
    ]

    seen: set[str] = set()

    def ingest_file(f: Path, project: str) -> None:
        if str(f) in seen:
            return
        seen.add(str(f))
        try:
            content = f.read_text(errors="replace")
        except OSError:
            return
        if is_private(content):
            return
        sections = re.split(r"\n#{1,3} ", content)
        for sec in sections:
            sec = sec.strip()
            if len(sec) < 80:
                continue
            samples.append(VoiceSample(
                text=sec[:1200],
                source="doc_excerpt",
                project=project,
                timestamp="",
                context=str(f.relative_to(SRC_ROOT) if SRC_ROOT in f.parents else f.name),
            ))

    # First: scan all .md files in afs-scawful docs/ (strategy docs, model docs, etc.)
    # Skip privacy check — these are known project docs, not personal logs
    afs_docs_dir = AFS_ROOT / "docs"
    if afs_docs_dir.exists():
        for f in sorted(afs_docs_dir.rglob("*.md")):
            if str(f) in seen:
                continue
            seen.add(str(f))
            try:
                content = f.read_text(errors="replace")
            except OSError:
                continue
            sections = re.split(r"\n#{1,3} ", content)
            for sec in sections:
                sec = sec.strip()
                if len(sec) < 80:
                    continue
                samples.append(VoiceSample(
                    text=sec[:1200],
                    source="doc_excerpt",
                    project="afs-scawful",
                    timestamp="",
                    context=str(f.relative_to(SRC_ROOT)),
                ))

    # Also scan afs-scawful docs/
    doc_dirs = [AFS_ROOT / "docs"]
    # And every project root under ~/src (max depth 2)
    for top in SRC_ROOT.iterdir():
        if top.is_dir() and not top.name.startswith("."):
            doc_dirs.append(top)
            for sub in top.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    doc_dirs.append(sub)

    for search_root in doc_dirs:
        for name in DOC_TARGETS:
            f = search_root / name
            if not f.exists():
                continue
            ingest_file(f, search_root.name)

    return samples


def mine_echoflow_models() -> list[VoiceSample]:
    """Extract EchoFlow Swift model definitions — shows what scawful values tracking."""
    echoflow_models = SRC_ROOT / "lab" / "echoflow" / "EchoFlow" / "Sources" / "Shared" / "Models"
    samples: list[VoiceSample] = []

    if not echoflow_models.exists():
        return samples

    for swift_file in echoflow_models.glob("*.swift"):
        try:
            content = swift_file.read_text(errors="replace")
        except OSError:
            continue
        if len(content) < 100:
            continue
        samples.append(VoiceSample(
            text=content[:2000],
            source="echoflow_model",
            project="echoflow",
            timestamp="",
            context=swift_file.name,
        ))

    return samples


# ─── Teacher model calls ───────────────────────────────────────────────────────

async def call_gemini(prompt: str, system: str = "", temperature: float = 0.8) -> tuple[str, str | None]:
    if not GOOGLE_API_KEY:
        return "", "GOOGLE_API_KEY not set"
    try:
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=GOOGLE_API_KEY)
        contents = f"{system}\n\n{prompt}" if system else prompt
        resp = client.models.generate_content(
            model=use(GEMINI_FLASH),
            contents=contents,
            config=gtypes.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=1024,
            ),
        )
        return resp.text, None
    except Exception as e:
        return "", str(e)


async def call_claude(prompt: str, system: str = "", temperature: float = 0.8,
                      model: str = ANTHROPIC_SONNET) -> tuple[str, str | None]:
    if not ANTHROPIC_API_KEY:
        return "", "ANTHROPIC_API_KEY not set — add to .env"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        kwargs: dict = dict(
            model=model,
            max_tokens=1024,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        msg = client.messages.create(**kwargs)
        return msg.content[0].text, None
    except Exception as e:
        return "", str(e)


async def call_openai(prompt: str, system: str = "", temperature: float = 0.8) -> tuple[str, str | None]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "", "OPENAI_API_KEY not set — add to .env"
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs: dict = {
            "model": use(OPENAI_CODEX),
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": 1024,
        }
        for _ in range(4):
            try:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=60,
                )
                return resp.choices[0].message.content or "", None
            except Exception as e:
                msg = str(e)
                if "timed out" in msg.lower():
                    continue
                if "Unsupported parameter: 'max_completion_tokens'" in msg:
                    kwargs.pop("max_completion_tokens", None)
                    continue
                if "Unsupported parameter: 'temperature'" in msg:
                    kwargs.pop("temperature", None)
                    continue
                return "", msg
        return "", "OpenAI call failed after compatibility retries"
    except Exception as e:
        return "", str(e)


async def call_teacher(prompt: str, system: str, teacher: str, temperature: float = 0.8) -> tuple[str, str]:
    if teacher == "gemini":
        text, err = await call_gemini(prompt, system, temperature)
        model = GEMINI_FLASH
    elif teacher == "claude":
        text, err = await call_claude(prompt, system, temperature, ANTHROPIC_SONNET)
        model = ANTHROPIC_SONNET
    elif teacher == "claude_opus":
        text, err = await call_claude(prompt, system, temperature, ANTHROPIC_OPUS)
        model = ANTHROPIC_OPUS
    elif teacher in ("openai", "codex"):
        text, err = await call_openai(prompt, system, temperature)
        model = OPENAI_CODEX
    else:
        return "", teacher
    if err:
        print(f"  [warn] {err[:100]}", file=sys.stderr)
    return text, model


# ─── Generation strategies per persona ───────────────────────────────────────

SIBYL_PROMPTS = [
    # Brain dump → triage
    "I have 11 things open in my head right now: finish the EchoFlow widget, review a PR, email someone about a project, fix a build error, a grocery run, call mom, the afs distillation pipeline needs a restart, I want to journal, need to research LoRA training configs, there's a barista bug, and I should plan tomorrow. Triage this for me.",
    "It's 2pm and I haven't started anything yet. I have energy. What do I do?",
    "I've been hyper-focusing on afs-scawful for 4 hours and I need to stop but I don't want to lose context. Help.",
    "Decision paralysis: should I refactor the EchoFlow data model now or wait until I have more features working? I've been going back and forth for 20 minutes.",
    "Brain dump: fix halext sync, add Lancer persona to AFS, write tests for RecommendationService, email about the hardware thing, yaze has a PPU regression, I want to learn more about LoRA rank selection. What's the actual priority?",
    "I'm about to start a work session but I don't know what to work on. I have 2 hours. High energy.",
    "I keep abandoning tasks halfway. How do I actually finish things?",
    "My inbox (EchoFlow) has 23 items. How do I approach this without spending 45 minutes triaging instead of doing?",
    "I want to work on barista but there's a more important bug in echoflow. I also said I'd do something for the halext backend. I'm spinning.",
    "It's 9pm. I have 1 hour. Low energy. What's a good 1-hour task from my backlog?",
    "I need to do a weekly review but I hate doing weekly reviews. I keep skipping them. How do I make this less painful?",
    "I have a deadline tomorrow on the halext-org API changes but I also found a fun bug in yaze I want to chase. I'm going to chase the bug, aren't I.",
    "I want to build the Sibyl training dataset but I also need to fix a bug in the antislop script. 30 minutes available. Go.",
    "Just woke up. Can't start. Everything feels heavy. Three things on the list are technically important. Help.",
    "I need to write documentation but I've been putting it off for 3 weeks. It's the afs-scawful training strategy doc. I know what I want to say. I just haven't written it. What do I do right now?",
    "I've been debugging the same EchoFlow CloudKit sync issue for 2 days. When do I stop and accept the workaround?",
    "Three projects need attention: oracle-of-secrets has an unfinished label in bank 0x04, yaze has a failing PPU test, and echoflow's widget broke after the last Xcode update. I have 3 hours. Plan it.",
    "I'm in the middle of a LoRA training run on Vast.ai. It's going to take 4 hours. What's the best use of my time while I wait?",
    "I added 18 things to my EchoFlow inbox this week and processed exactly 0 of them. The inbox is now useless. How do I fix the system without spending all day on the system?",
    "I have a good idea for a new project but I'm already juggling 6. I keep getting distracted by it. Do I start it, kill it, or park it?",
    "The AFS training pipeline is broken in a new way every time I run it. I've fixed 5 bugs this week. Is this normal or is something fundamentally wrong?",
    "I want to ship something this week. Not a feature — something complete and usable. What's the smallest thing in my backlog that qualifies?",
    "I've been in planning mode for 2 weeks without shipping. How do I break the loop?",
    "My daily EchoFlow review shows: 8 entries created, 0 completed. This is day 4 of the same pattern. What does this mean and what do I change?",
    "I want to spend an hour on learning — either reading about transformer architecture or going deeper into SNES hardware. Low stakes. What's the call?",
    "I keep starting new afs-scawful scripts without finishing the ones in progress. weaver_index, antislop, persona — all half-done. How do I close open loops?",
    "The EchoFlow widget is not updating on time. It's a known bug. I've deprioritized it 3 times. How do I decide if this is actually important or if I'm just annoyed?",
    "I have 45 minutes before a meeting. I keep starting things and stopping. What's a useful 45-minute task I can actually finish?",
    "I've got 3 half-finished features in EchoFlow: widget refresh, recommendation scoring, and CloudKit retry. Which one do I finish first?",
    "It's Saturday morning. No obligations until afternoon. barista, yaze, oracle-of-secrets, and EchoFlow are all calling to me. Pick one.",
    "I have a bug that will take 10 minutes to fix but I can't start it because I'm already 'in the middle of something.' How do I handle this without losing both threads?",
    "I've been saying 'I'll set up the Vast.ai training run this week' for 3 weeks. What's actually blocking me and how do I remove it today?",
    "Two things are urgent: a prod issue in halext-org and a broken build in EchoFlow. I can only do one right now. Which one?",
    "I finished a big task and now I feel weirdly empty and can't start the next thing. It's been 2 hours. What's going on and what do I do?",
    "My focus is gone after lunch. 3 hours left in the afternoon. What types of tasks should I fill it with and what should I save for tomorrow?",
    "I want to refactor the halext-org migrations but the codebase is fragile. I'm scared to touch it. How do I approach this without breaking everything?",
    "I've been meaning to set up automated eval runs for the AFS models for weeks. It keeps sliding. Is this high priority or am I avoiding it?",
]

LANCER_PROMPTS = [
    # Stuck situations → one action
    "I've been staring at this function for 45 minutes and I can't figure out why it's not working.",
    "I have 15 tabs open and I can't decide what to do first.",
    "I want to start working but I keep reading documentation instead of writing code.",
    "I've rewritten the same function 3 times and it still doesn't feel right.",
    "I'm procrastinating on sending an important email.",
    "I need to write tests but I'm avoiding it by doing 'preparatory work'.",
    "I can't start the project because I haven't figured out the perfect architecture.",
    "I wrote the code but I'm scared to run it and see the errors.",
    "I have a PR ready but I've been sitting on it for 2 days.",
    "I keep context-switching between 4 different tasks and making progress on none.",
    "I want to start the LoRA training run but I'm worried the dataset isn't good enough yet.",
    "I need to make a decision between two options and I've been going back and forth.",
    "I'm reading the SNES hardware manual instead of writing the emulation code.",
    "The test is failing and I've been reading the error message for 10 minutes.",
    "I built the feature but I'm not documenting it because 'I'll do it later.'",
    "I scheduled a task for today but it's now 6pm and I haven't touched it.",
    "I need to ask for help but I'm trying to solve it myself for too long.",
    "I'm redesigning the data model for the 4th time instead of shipping what I have.",
    "Every time I open the editor I close it again. I haven't written a line in 3 hours.",
    "I have everything I need to build the thing. I'm just not building it.",
    "I've been 'about to push' this commit for an hour. I keep finding more things to fix.",
    "I'm adding features to EchoFlow that weren't in the original plan and the scope keeps growing.",
    "I need to delete old code but I keep thinking 'I might need this later.'",
    "I know the bug is somewhere in this 300-line file but I don't know where to start.",
    "I'm reading other people's projects instead of working on mine.",
    "I have a working solution but I'm not shipping it because it's 'not clean enough.'",
    "I've been 'warming up' to the task for 30 minutes and I still haven't opened the file.",
    "I broke something while refactoring and now I'm not sure if I should keep going or revert.",
    "I keep opening GitHub, Reddit, and Hacker News every few minutes instead of working.",
    "I started writing a design doc but now I'm researching instead of deciding.",
    "I've been naming variables for 20 minutes.",
    "I need to update a dependency but I'm scared of breaking the build.",
    "I have 5 branches open and I don't remember what any of them are for.",
    "I keep re-reading the same block of code without understanding it.",
    "I said I'd finish this today and it's now midnight and I haven't started.",
    "I want to close an issue but I'm not sure my fix is actually complete.",
    "I've been in the yaze debugger for 2 hours on the same instruction.",
    "I know what needs to happen but I'm writing down the plan instead of doing it.",
    "I have a half-working implementation and I keep adding to it instead of shipping the core.",
    "I'm waiting for the perfect moment to start and it hasn't arrived.",
]

MORPHEUS_PROMPTS = [
    # Project → moonshot extensions
    "I have barista, a Lua/C menu bar tool for macOS. What are 5 moonshot extensions that connect to my other projects?",
    "I have echoflow, an ADHD daily loop iOS app with SwiftData and Pomodoro timer. What are 5 wild features it could grow into?",
    "I have yaze, a SNES emulator in C++. What are 5 unexpected directions I could take it that connect to my other work?",
    "I have the afs-scawful training pipeline with Ockham (anti-slop), Weaver (cross-project), and the persona models. What are 5 moonshot use cases for this model stack?",
    "I have halext-org, a FastAPI backend for personal task management with org-mode sync. What are 5 wild things it could become?",
    "I have the oracle-of-secrets decompilation project — 77k+ lines of 65816 ASM with labels. What are 5 insane things I could do with this corpus?",
    "I have barista + echoflow + halext-org all running on my machine. What's a unified system they could become together?",
    "I have the Veran model (trained on oracle-of-secrets ASM analysis). What are 5 unexpected ways to use a model that understands SNES assembly?",
    "I'm building persona models for my own use. What's a moonshot product built on top of these that I could actually ship?",
    "I have the weaver_index.py that knows all 43 projects under ~/src. What could I build if I gave it a proper UI and inference backend?",
    "I have the oracle-of-secrets decompilation — 77k lines of labeled 65816 ASM and a working emulator (yaze). What would it look like to build a playable modded game from scratch using this stack?",
    "I have logprune.py that scores and extracts Claude conversations. What's the moonshot: turning this into a personal analytics system that tracks how I think over time?",
    "I have echoflow tracking ADHD tasks and barista showing menu bar status. What if they knew about each other — what's the wildest integration?",
    "I'm training a personal AI stack (AFS). What's the 5-year moonshot for where this goes if I keep compounding on it?",
    "I have yaze (SNES emulator), oracle-of-secrets (decomp), and z3dk (dev kit). What's a wild creative product I could ship to retro gaming fans using all three?",
    "I have the commit_diff_dataset — 2,616 coding pairs from 40+ personal repos. What's a moonshot model only I could build because of this unique data?",
    "I have halext-org with a full personal productivity API. What's a moonshot integration with EchoFlow that creates a genuine closed-loop self-improvement system?",
    "I have Sibyl (ADHD planner), Lancer (unstuck), Morpheus (ideas), Anamnesis (memory). What's a moonshot product that combines all four into something shippable?",
    "I have barista as a Lua/C menu bar with the halext-org API behind it. What's a 10x version of this that becomes indispensable?",
    "I have the afs-scawful weaver index that maps relationships across 43 projects. What's the moonshot if I added a proper graph database and query interface?",
    "I have the afs-scawful model stack (Ockham, Din, Sibyl, Lancer, Morpheus, Anamnesis). What's a moonshot tool that uses all of them in a single real-time workflow?",
    "I have the EchoFlow daily loop: Capture → Flow → Reflect. What's a moonshot that turns this into a full personal operating system?",
    "I have the oracle-of-secrets decompilation and z3dk. What's a moonshot fan project the ALTTP community would actually use?",
    "I have org-halext-sync that bridges Emacs org-mode and my personal API. What's the wildest thing I could do with a fully programmable task layer?",
    "I have the logprune.py conversation extractor and 151 Claude sessions tagged and scored. What's a moonshot personal analytics product built on this?",
    "I have yaze running real SNES hardware-accurate emulation. What if I used it as a foundation for something nobody has built before in the retro space?",
    "I have 43 projects under ~/src spanning emulation, iOS apps, AI training, and personal tools. What's the moonshot meta-project that ties them into a coherent platform?",
    "I have the AFS commit_diff dataset trained into Nayru (codegen). What's the wildest developer tool I could build around a model that learned from my personal coding style?",
    "I have barista as a menu bar status layer and EchoFlow as a task layer. What if I added an inference layer — what does a local AI-powered menu bar become?",
    "I have Anamnesis trained on my own decision history. What's a moonshot where I externalize my memory and reasoning into a queryable system I actually trust?",
    "I have the oracle-of-secrets labeled ASM corpus and Veran trained on it. What's a moonshot where this becomes a teaching tool for 65816 assembly programming?",
    "I have halext-org tracking streaks, focus minutes, and momentum. What's a moonshot quantified-self product built from this personal behavioral data?",
]

MONOLITH_PROMPTS = [
    "write a bash script that finds the 20 largest files under the current directory and prints size + path.",
    "write c code to parse argv flags --input and --output without third-party libs.",
    "replace this python one-liner with pure bash: count unique first-column values in a csv file.",
    "show a minimal c function that reads an entire file into memory and returns pointer + size.",
    "give me a no-dependency bash deploy script that rsyncs current dir to a remote host and restarts a systemd service.",
    "write the smallest bash command pipeline to list duplicate lines in a file with counts.",
    "create minimal c code for a ring buffer with push/pop and no dynamic allocations.",
    "i need to rename all .jpeg files to .jpg recursively using shell only.",
    "write a tiny bash script that retries a command up to 5 times with exponential backoff.",
    "show minimal c code to parse newline-delimited json objects without external libs (line by line only).",
    "i want a bash script that fails hard on first error and logs each step with timestamps.",
    "provide c code for an arena allocator for small allocations used during a single request.",
    "write a shell command to diff two directories and print only changed file paths.",
    "give me a minimal c tokenizer for comma-separated values with quoted field support.",
    "write a no-dependency bash script to watch a file and re-run a command when it changes.",
    "show the leanest c implementation of a fixed-size hash table for string keys.",
    "write a pure bash script that batches files into tar archives of 100 files each.",
    "how do i parse a simple key=value config file in c without helper libraries?",
    "show a bash pipeline to compute top 10 most frequent words in stdin.",
    "write minimal c code to do non-blocking tcp connect with timeout.",
    "write a bash one-liner to delete empty directories recursively, safely preview first.",
    "show c code for parsing unsigned integers from a string with strict error checks.",
    "write a pure shell script to rotate logs by size and keep the last 5 files.",
    "give me minimal c code to memory-map a file read-only and print the first 256 bytes.",
    "write the shortest bash function to test whether a command exists in PATH.",
    "show c code for a tiny line-oriented http request parser without external libs.",
    "write a bash script that validates required env vars and exits with clear errors.",
    "give me minimal c code for a bounded work queue using pthread mutex/cond.",
    "write a shell pipeline to extract unique email domains from a text stream.",
    "show c code to implement a fast crc32 function with a precomputed table.",
    "write a bash script to mirror a directory while excluding .git and node_modules.",
    "give me the leanest c implementation for splitting PATH-like strings by colon.",
    "write a POSIX sh script that performs command health checks and prints a compact report.",
    "show c code to parse an ini-style config with sections and key/value pairs.",
    "write a bash script to run a command across a list of hosts via ssh and collect exit codes.",
    "show minimal c code for a monotonic timer utility returning milliseconds.",
    "write a shell script that atomically swaps symlink current -> release directory.",
    "give me c code to safely build file paths without buffer overflow.",
    "write a bash command sequence to detect and remove trailing whitespace in files.",
    "show minimal c code for a small command dispatch table using function pointers.",
]

CONDUCTOR_PROMPTS = [
    "plan a 3-agent swarm to fix a failing ci pipeline in a python repo and ship a patch today.",
    "orchestrate a workflow to add a new persona model: dataset generation, training, eval, and registry update.",
    "design a DAG for migrating a sqlite schema with zero downtime and rollback support.",
    "build an agent plan for investigating a production memory leak and delivering a verified fix.",
    "decompose a cross-repo refactor touching api contracts and frontend consumers.",
    "create a handoff sequence to train and deploy monolith-v1 locally with smoke tests.",
    "orchestrate a bug triage sprint for 40 issues with strict priority and ownership.",
    "plan a release pipeline for a model update with canary, eval gate, and promotion criteria.",
    "design an agent DAG for importing legacy docs, extracting decisions, and updating architecture notes.",
    "orchestrate an incident response for elevated api latency: diagnose, mitigate, validate, communicate.",
    "build a swarm plan to convert four LoRA adapters into GGUF and verify each artifact checksum.",
    "create a DAG to run nightly evals, collect failures, generate repair data, and trigger micro-fix training.",
    "decompose a task to add strict json output support end-to-end across prompt, model, and evaluator.",
    "plan a two-day sprint for cleaning stale docs and aligning status with real training outcomes.",
    "orchestrate benchmark runs for three models and produce a promotion recommendation.",
    "design a swarm handoff for data QA: dedupe, schema validate, privacy scan, and publish.",
    "plan a repo-wide dependency reduction campaign with measurable outcomes.",
    "build a DAG for reproducing a user bug, adding regression tests, and releasing a patch.",
    "orchestrate a local-to-remote model artifact sync with integrity validation and fallback.",
    "create an execution plan to bootstrap conductor-v1 dataset, train it, and run json-structure evals.",
    "plan a multi-agent workflow to triage and clear a 200-item personal task backlog in one week.",
    "design a DAG for journaling pipeline automation: capture, classify mood, summarize, and review trends.",
    "orchestrate a poem-writing assistant launch: dataset, style eval, safety checks, and deployment.",
    "build an agent handoff plan for long-form essay drafting with citation verification and revision gates.",
    "decompose a task-management model rollout including data prep, fine-tune, eval, and router updates.",
    "design a DAG for migrating all model cards to a unified metadata schema and validation.",
    "orchestrate a weekly model-ops cadence: eval collection, regression triage, patching, promotion decision.",
    "create an execution plan to harden prompt-injection defenses across local model endpoints.",
    "plan a cross-agent workflow for converting user journal entries into actionable weekly priorities.",
    "decompose a release train for three persona model updates with rollback and smoke checks.",
    "design an agent DAG to produce a polished essay from raw notes with argument-structure checkpoints.",
    "orchestrate incident response for broken model routing rules causing wrong persona selection.",
    "create a plan to benchmark creative-writing models on poetry, narrative voice, and coherence.",
    "design a DAG for building a personal memory index from journals, commits, and docs with privacy filters.",
    "orchestrate a remediation workflow for low-quality synthetic training samples in a dataset.",
    "plan an experiment matrix for temperature/system-prompt sweeps on task-management assistants.",
    "build a handoff sequence for generating monthly reflection reports from daily journal entries.",
    "decompose an end-to-end workflow for thesis-style essay writing with research and outline agents.",
    "design a DAG for validating json schema compliance in a conductor model output stream.",
    "orchestrate a project to turn unfinished docs into publishable long-form essays in four sprints.",
]

STEWARD_PROMPTS = [
    "I have 27 tasks in my backlog and only 90 minutes today. Prioritize and sequence.",
    "My week is fragmented: meetings, one urgent bug, and two strategic projects. Build a usable execution plan.",
    "I keep reopening the same 5 tasks. Give me a concrete closeout sequence.",
    "I need to ship one thing today but three tasks feel equally important.",
    "I have admin overhead eating my mornings. Replan my task flow for deep work.",
    "Two deadlines conflict: API hotfix and model eval report. What goes first and why?",
    "My task list has vague items like 'improve pipeline' and 'clean docs'. Convert to executable tasks.",
    "I have 40 minutes before a meeting. What should I complete now?",
    "I keep context switching. Build a single-thread execution plan for the next 3 hours.",
    "I need a weekly reset: prune, reorder, and commit to top priorities.",
    "I keep delaying painful tasks. Give me a forcing sequence with checkpoints.",
    "I have a backlog split across notes, git issues, and memory. Consolidate execution order.",
    "How should I batch task types to reduce cognitive overhead this week?",
    "I need to triage urgent vs important across five projects.",
    "I need a realistic plan for today with one high-value deliverable.",
    "I miss deadlines because tasks are too big. Break these down with handoff points.",
    "I finished planning but not shipping. Build a ship-first task list.",
    "I have low energy today. What tasks should move vs wait?",
    "I need a task plan that includes recovery buffers and risk checks.",
    "I keep adding new tasks midstream. Add guardrails to stop scope creep.",
    "I need to clear 15 stale tasks without losing important work.",
    "I want a task plan that includes explicit done criteria.",
    "I have a high-risk migration and a low-risk feature. Sequence safely.",
    "Build me a 2-day task runway from this messy backlog.",
    "I need to leave clean handoff notes for tomorrow’s self.",
    "I have too many 'someday' tasks. Cull aggressively.",
    "How should I front-load difficult tasks across the week?",
    "I need an execution order that maximizes momentum in first hour.",
    "Convert my idea list into a strict next-action queue.",
    "I want to track execution quality, not just completion count.",
    "I need to reserve focus windows while still handling interrupts.",
    "I need a task plan for shipping a model update by Friday.",
    "I have multiple blocked tasks. Route around blockers and keep progress.",
    "Set up checkpoints for a 4-hour implementation block.",
    "I need a ruthless plan for reducing open loops to under 5.",
    "I need a task strategy for balancing maintenance and new features.",
    "Make a plan that survives if one dependency fails.",
    "I need to prioritize tasks using impact and reversibility.",
    "I want a weekly execution review format that improves planning accuracy.",
    "Turn this chaotic TODO list into a strict execution ladder.",
]

JOURNALIST_PROMPTS = [
    "Journal: I felt scattered all day. I touched six tasks and finished none. Reflect with one experiment for tomorrow.",
    "Journal: Good morning focus, then I crashed after lunch and doomscrolled. Help me interpret this pattern.",
    "Journal: I avoided one difficult conversation and compensated by cleaning small tasks.",
    "Journal: I had a productive sprint but felt empty afterward. What does that suggest?",
    "Journal: I shipped something small and it improved my mood immediately.",
    "Journal: I kept thinking about a big project but did not start it.",
    "Journal: I overplanned and under-executed again. Reflect without fluff.",
    "Journal: I was anxious before coding but calm once started.",
    "Journal: Three interruptions derailed me and I never recovered.",
    "Journal: I had a clear morning intention but ignored it by noon.",
    "Journal: I wrote docs for two hours and felt unexpectedly energized.",
    "Journal: I am stuck between two priorities and keep postponing both.",
    "Journal: I did admin tasks all day and feel behind on meaningful work.",
    "Journal: I slept poorly and task quality dropped; still completed one hard thing.",
    "Journal: I avoided bug triage because I feared complexity.",
    "Journal: I noticed resentment toward recurring obligations.",
    "Journal: I started strong with one decisive task and the day flowed better.",
    "Journal: I kept reopening finished tasks to polish details.",
    "Journal: I had a good collaboration session but no solo output.",
    "Journal: I procrastinated with research instead of writing.",
    "Journal: I made a risky change and felt proud, but skipped verification.",
    "Journal: I felt lonely while working and my focus drifted.",
    "Journal: I ignored breaks and lost clarity by evening.",
    "Journal: I did one meaningful task and it shifted the whole day.",
    "Journal: I said yes to too many requests and crowded my schedule.",
    "Journal: I want to write more but keep defaulting to maintenance tasks.",
    "Journal: I felt blocked, took a walk, then solved the problem quickly.",
    "Journal: I had strong momentum after making one clear decision.",
    "Journal: I kept comparing my output to others and froze.",
    "Journal: I delayed sleep for one more task and paid for it today.",
    "Journal: I spent too much time in tools and not enough in outcomes.",
    "Journal: I made progress but didn’t capture decisions anywhere.",
    "Journal: I kept changing plans instead of committing.",
    "Journal: I had one deep focus block; everything else was fragmented.",
    "Journal: I avoided a hard bug and did low-stakes work instead.",
    "Journal: I felt better when I switched from planning to execution.",
    "Journal: I need a reflection that is honest but not punitive.",
    "Journal: I am worried I am losing direction across too many projects.",
    "Journal: I ended the day unsure what mattered most.",
    "Journal: I want a clearer daily closure ritual.",
]

POET_PROMPTS = [
    "Write a short free-verse poem about debugging at 2am with cold coffee and one stubborn test.",
    "Turn this line into a poem: 'I kept reopening the same file until it looked like a mirror.'",
    "Write a poem about momentum returning after one small completed task.",
    "Create a poem about city rain on windows during a late-night coding sprint.",
    "Write a poem from the perspective of an unread log file.",
    "Draft a compact poem about burnout disguised as productivity.",
    "Write a poem that compares technical debt to an overgrown garden.",
    "Create a low-key hopeful poem about starting over on Monday.",
    "Write a poem about a backlog that feels like weather.",
    "Compose a poem about waiting for tests to finish and watching progress bars.",
    "Write a poem about forgetting to eat while deep in flow.",
    "Turn this into poetry: 'I planned all day and shipped nothing.'",
    "Write a short imagist poem about cable clutter, fans spinning, and blue light.",
    "Draft a poem about fear of starting the first paragraph.",
    "Write a poem that uses exactly one metaphor related to trains.",
    "Compose a poem about a half-built project that still teaches you something.",
    "Write a poem in second person about anxiety before pressing deploy.",
    "Create a poem about deleting code and feeling relief.",
    "Write a poem about context switching and mental fragmentation.",
    "Draft a poem about sunrise after an all-night fix.",
    "Write a poem about journaling as system logs for the self.",
    "Compose a poem about the sound of keyboard keys in an empty room.",
    "Write a poem that ends with a concrete action for tomorrow.",
    "Turn this sentence into a poem: 'I kept polishing details to avoid the hard decision.'",
    "Write a poem about unfinished notes becoming a map.",
    "Create a poem with restrained tone about disappointment after a failed run.",
    "Write a poem about one decisive commit changing the whole week.",
    "Compose a poem about silence between notifications.",
    "Write a poem about emotional lag after intense focus.",
    "Draft a poem about momentum as a fragile flame.",
    "Write a poem about carrying too many project identities at once.",
    "Create a poem about returning to a forgotten notebook.",
    "Write a poem about trying to name what mattered today.",
    "Compose a poem about learning to stop at 'good enough.'",
    "Write a poem that contrasts morning intention with evening reality.",
    "Draft a poem about a to-do list as archaeology.",
    "Write a poem with clear sensory detail and no abstract nouns.",
    "Compose a poem about holding both ambition and fatigue.",
    "Write a poem about a tiny win that broke a long freeze.",
    "Create a short poem about choosing one task and closing all other tabs.",
]

POET_FORM_CONTROL_PROMPTS = [
    "[FORM:haiku] Write about debugging at 2am with cold coffee.",
    "[FORM:haiku] Write about closing every tab except one decisive task.",
    "[FORM:haiku] Write about rain on train windows after a late shift.",
    "[FORM:haiku] Write about a tiny win breaking a long freeze.",
    "[FORM:haiku] Write about waiting for tests to pass in silence.",
    "[FORM:imagist] Write about fan noise, cable clutter, and blue monitor light.",
    "[FORM:imagist] Write about a cursor blinking in an empty room.",
    "[FORM:imagist] Write about deleting stale code and exhaling.",
    "[FORM:imagist] Write about a notebook left open beside a keyboard.",
    "[FORM:imagist] Write about sunrise after an all-night bug fix.",
    "[FORM:free_verse] Turn this into a poem: 'I planned all day and shipped nothing.'",
    "[FORM:free_verse] Turn this into a poem: 'I kept polishing details to avoid the hard decision.'",
    "[FORM:free_verse] Write about momentum returning after one finished task.",
    "[FORM:free_verse] Write about context switching and mental static.",
    "[FORM:free_verse] Write about fear before pressing deploy.",
    "[FORM:free_verse] Write about backlog items that feel like weather.",
    "[FORM:free_verse] Write about journaling as system logs for the self.",
    "[FORM:free_verse] Write about a half-built project that still teaches something.",
    "[FORM:sonnet_like] Write about ambition and fatigue in the same day.",
    "[FORM:sonnet_like] Write about maintenance work versus meaningful work.",
    "[FORM:sonnet_like] Write about reopening finished tasks to chase perfection.",
    "[FORM:sonnet_like] Write about choosing one irreversible first action.",
    "[FORM:sonnet_like] Write about trying to name what mattered today.",
    "[FORM:prose_to_poem] Convert this prose to poem: I delayed the hard bug by organizing folders and renaming files.",
    "[FORM:prose_to_poem] Convert this prose to poem: I kept researching tooling instead of writing the first paragraph.",
    "[FORM:prose_to_poem] Convert this prose to poem: The room was quiet except for keys and the refrigerator hum.",
    "[FORM:prose_to_poem] Convert this prose to poem: I deleted 300 lines and felt lighter immediately.",
    "[FORM:prose_to_poem] Convert this prose to poem: One clear decision made the next three decisions easy.",
    "[FORM:free_verse] Write about silence between notifications.",
    "[FORM:imagist] Write about the texture of a warm mug near a cold monitor.",
    "[FORM:haiku] Write about a checklist becoming a ladder.",
    "[FORM:sonnet_like] Write about planning comfort becoming avoidance.",
    "[FORM:free_verse] Write about carrying too many project identities at once.",
    "[FORM:imagist] Write about dust in late afternoon light over a desk.",
    "[FORM:haiku] Write about closing the editor and sleeping on time.",
    "[FORM:prose_to_poem] Convert this prose to poem: I made one commit and the week felt possible again.",
    "[FORM:free_verse] Write about returning to a forgotten notebook.",
    "[FORM:imagist] Write about train tracks after rain and neon reflection.",
    "[FORM:sonnet_like] Write about choosing good-enough over perfect.",
    "[FORM:free_verse] Write about tomorrow's first action written before sleep.",
]

ESSAYIST_PROMPTS = [
    "Write a structured essay on why execution beats optimization in early product phases.",
    "Draft an essay arguing for daily closure rituals in ADHD-aware workflows.",
    "Write an essay from notes: planning comfort can become avoidance behavior.",
    "Create an essay on how small irreversible actions reduce decision fatigue.",
    "Write an essay comparing maintenance work and strategic work with a practical balancing framework.",
    "Draft an essay about why journaling improves technical decision quality.",
    "Write an essay on context-switching costs in solo engineering.",
    "Create a thesis-driven essay on the value of local models for personal workflows.",
    "Write an essay arguing for explicit done criteria in task systems.",
    "Draft an essay on the tradeoff between speed and verification in shipping.",
    "Write an essay about overfitting productivity systems instead of doing work.",
    "Create an essay on why weekly reviews fail and how to redesign them.",
    "Write an essay arguing that constraints improve creative output.",
    "Draft an essay on practical methods to recover from burnout cycles.",
    "Write a long-form argument for separating journaling, poetry, and task assistants into distinct models.",
    "Create an essay on how personal datasets can preserve decision context over time.",
    "Write an essay about the psychology of reopening finished tasks.",
    "Draft an essay on when to refactor versus when to defer.",
    "Write an essay arguing for minimal tooling in early-stage workflows.",
    "Create an essay on improving planning accuracy through postmortem reflection.",
    "Write an essay about the cost of ambiguous backlog items.",
    "Draft an essay on momentum engineering: designing the first hour of work.",
    "Write an essay about how fear of complexity delays bug triage.",
    "Create an essay on the operational value of guardrails against scope creep.",
    "Write an essay comparing generic productivity advice to context-specific systems.",
    "Draft an essay on the benefits and risks of synthetic training data.",
    "Write an essay about why documenting decisions matters more than documenting opinions.",
    "Create an essay on balancing craft quality with shipping cadence.",
    "Write an essay that defends short feedback loops in model iteration.",
    "Draft an essay about choosing one priority under uncertainty.",
    "Write an essay on how language shapes self-assessment in daily notes.",
    "Create an essay about designing humane but rigorous personal operating systems.",
    "Write an essay arguing for lightweight eval packs before model promotion.",
    "Draft an essay on avoiding pseudo-progress during research-heavy days.",
    "Write an essay about handling multiple projects without losing narrative coherence.",
    "Create an essay on converting rough notes into publishable arguments.",
    "Write an essay about using checkpoints to manage cognitive load.",
    "Draft an essay on why reversible decisions should move fast and irreversible ones should be staged.",
    "Write an essay on practical methods to improve writing throughput without sacrificing quality.",
    "Create an essay on building trust in personal assistants through grounded output behavior.",
]

ANAMNESIS_PROMPTS_TEMPLATE = [
    # Decision recall — needs real data context
    "Why did I choose SwiftData over Core Data for EchoFlow?",
    "When did I start the afs-scawful project and what was the original goal?",
    "Why is the Entry model a single unified model instead of separate Task and Note types?",
    "Why does barista use Lua for configuration instead of a config file?",
    "When did I start the Oracle of Secrets decompilation and why?",
    "Why is the yaze emulator written in C++ instead of Rust or Swift?",
    "Why did I choose Qwen 2.5 as the base model for the AFS models instead of Llama or Mistral?",
    "What was the reasoning for making halext-org use SQLite instead of PostgreSQL?",
    "Why does echoflow use an App Group for shared SwiftData between app and widgets?",
    "What triggered the decision to build a personal AI training pipeline (afs-scawful)?",
    "Why does the EchoFlow RecommendationService use actor isolation?",
    "Why is Ockham trained on Qwen 2.5 3B specifically?",
    # Strategy questions — answerable from MODEL_TRAINING_STRATEGY.md
    "What is the anti-slop training philosophy for Ockham?",
    "What are the 5 code quality problems Ockham is designed to eliminate?",
    "What model roster currently exists in the AFS project?",
    "What's the difference between Ockham and Argos in the AFS model lineup?",
    "What is the Avatar-Mix model and which personas does it combine?",
    "What domain triggers the Sentinel persona in Avatar-Mix?",
    "Why does the weaver_index.py exclude certain projects like backup archives?",
    "What makes the Claude conversation logs 'unique data nobody else has'?",
    "What is the purpose of the Lancer model and what's its target inference speed?",
    "What is Sibyl's role and how does it differ from generic productivity tools?",
    # More decision recall
    "Why did I choose FastAPI over Flask for the halext-org backend?",
    "Why does org-halext-sync exist as a separate tool instead of calling the halext-org API directly from Emacs?",
    "Why does the EchoFlow widget use App Group shared storage instead of reading from CloudKit directly?",
    "Why does logprune.py use a scoring system instead of just extracting all sessions?",
    "Why did I build persona models (Sibyl, Lancer, Morpheus, Anamnesis) separately instead of one general model?",
    "Why is the oracle-of-secrets decompilation done with assembly labels rather than decompiling to C?",
    "Why did I build the commit_diff_dataset from personal repos instead of using public GitHub data?",
    "Why does the weaver_index cross-project indexer run as a CLI script rather than a daemon?",
    "Why does Ockham use anti-slop training (bloated→clean) rather than clean→refactored pairs?",
    "Why does EchoFlow use three tabs (Capture→Flow→Reflect) as the main structure?",
    "Why is the yaze training corpus limited to src/app/emu and src/core, not the full codebase?",
    "Why is the Din model specifically focused on 65816 assembly rather than general code?",
    # More strategy questions
    "What's the current deployment plan for the AFS persona models?",
    "What is the Weaver model designed to know and why is cross-project indexing valuable for it?",
    "What distinguishes Anamnesis from a general knowledge retrieval or RAG system?",
    "Why is QLoRA used instead of full fine-tuning for the AFS persona models?",
    "What is the role of Avatar-Mix and how does it relate to the individual persona models?",
    "What is the 'distill' step in weaver_index.py and why does it specifically use Gemini Flash?",
    "What problem does the halext-org streak system solve for ADHD productivity?",
    "How does the EchoFlow recommendation service rank and surface tasks?",
    "What is the philosophy behind building personal local models instead of relying on API-only tools?",
    "What makes the Claude conversation logs a uniquely valuable training source for AFS?",
]


def build_anamnesis_context(doc_samples: list[VoiceSample], git_samples: list[VoiceSample]) -> str:
    """Build a context block for Anamnesis from docs + git commits."""
    parts = ["## Decision History Context\n"]

    # Must-include docs — scan ALL samples to find every section
    MUST_INCLUDE = {"MODEL_TRAINING_STRATEGY.md"}
    PRIORITY_DOCS = {"MODEL_STRATEGY.md", "MODEL_PORTFOLIO.md", "AGENTS.md", "CLAUDE.md", "README.md"}
    key_projects = {"afs-scawful", "echoflow", "barista", "yaze", "halext-org"}

    included: set[str] = set()

    # First pass: grab ALL sections from must-include docs (no cap — these are critical)
    for s in doc_samples:
        doc_name = Path(s.context).name if s.context else ""
        if doc_name in MUST_INCLUDE and len(s.text) > 100:
            entry = f"### {s.project} / {s.context}\n{s.text[:800]}\n"
            if entry not in included:
                parts.append(entry)
                included.add(entry)

    # Second pass: priority docs
    for s in doc_samples:
        if s.project in key_projects and len(s.text) > 100:
            doc_name = Path(s.context).name if s.context else ""
            if doc_name in PRIORITY_DOCS:
                entry = f"### {s.project} / {s.context}\n{s.text[:600]}\n"
                if entry not in included:
                    parts.append(entry)
                    included.add(entry)
        if len(parts) > 18:
            break

    # Third pass: other key project docs
    for s in doc_samples:
        if s.project in key_projects and len(s.text) > 100:
            entry = f"### {s.project} / {s.context}\n{s.text[:400]}\n"
            if entry not in included:
                parts.append(entry)
                included.add(entry)
        if len(parts) > 25:
            break

    # Recent git commits for key projects
    parts.append("\n## Recent Commits\n")
    for s in git_samples:
        if s.project in key_projects:
            parts.append(f"[{s.project}] {s.text}")
        if len(parts) > 40:
            break

    return "\n".join(parts)


# ─── Generation ───────────────────────────────────────────────────────────────

def load_done_texts(output_path: Path) -> set[str]:
    done: set[str] = set()
    if not output_path.exists():
        return done
    for line in output_path.read_text(errors="replace").splitlines():
        try:
            rec = json.loads(line)
            user_msg = next(
                (m["content"] for m in rec.get("messages", []) if m["role"] == "user"), ""
            )
            done.add(user_msg[:80])
        except Exception:
            pass
    return done


async def generate_sibyl(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in SIBYL_PROMPTS if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Sibyl] {len(prompts)} prompts to generate")

    # Enrich system prompt with self-briefing if available
    base_system = PERSONAS["sibyl"]["system"]
    briefing = load_self_briefing()
    system = base_system + (f"\n\n## About scawful\n{briefing[:2000]}" if briefing else "")

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            text, model = await call_teacher(prompt, system, teacher, temperature=0.75)
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            record = {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text},
                ],
                "_meta": {
                    "persona": "sibyl",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "has_briefing": bool(briefing),
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


async def generate_lancer(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in LANCER_PROMPTS if f"scawful says: {p}"[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Lancer] {len(prompts)} prompts to generate")
    persona = PERSONAS["lancer"]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            # Lancer needs to be SHORT and direct — lower temp, short max tokens
            text, model = await call_teacher(
                f"scawful says: {prompt}",
                persona["system"], teacher, temperature=0.65,
            )
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            # Enforce brevity: keep first 2 sentences
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
            short_text = " ".join(sentences[:2])
            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": f"scawful says: {prompt}"},
                    {"role": "assistant", "content": short_text},
                ],
                "_meta": {
                    "persona": "lancer",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "original_length": len(text),
                    "trimmed_length": len(short_text),
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] {short_text[:80]}")


async def generate_morpheus(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in MORPHEUS_PROMPTS if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Morpheus] {len(prompts)} prompts to generate")

    base_system = PERSONAS["morpheus"]["system"]
    briefing = load_self_briefing()
    system = base_system + (f"\n\n## Full project context\n{briefing[:3000]}" if briefing else "")

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            text, model = await call_teacher(prompt, system, teacher, temperature=0.9)
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            record = {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text},
                ],
                "_meta": {
                    "persona": "morpheus",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "has_briefing": bool(briefing),
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


async def generate_anamnesis(teacher: str, limit: int | None, output_path: Path,
                              raw_dir: Path):
    """Anamnesis needs real context — loads mined docs + git commits."""
    doc_file = raw_dir / "doc_excerpts.jsonl"
    git_file = raw_dir / "git_commits.jsonl"

    doc_samples: list[VoiceSample] = []
    git_samples: list[VoiceSample] = []

    if doc_file.exists():
        for line in doc_file.read_text().splitlines():
            try:
                d = json.loads(line)
                doc_samples.append(VoiceSample(**d))
            except Exception:
                pass
    if git_file.exists():
        for line in git_file.read_text().splitlines():
            try:
                d = json.loads(line)
                git_samples.append(VoiceSample(**d))
            except Exception:
                pass

    if not doc_samples and not git_samples:
        print("[Anamnesis] No mined data found — run 'mine' first", file=sys.stderr)
        return

    context = build_anamnesis_context(doc_samples, git_samples)
    briefing = load_self_briefing()
    if briefing:
        context = f"## Developer Self-Briefing\n{briefing[:2500]}\n\n---\n\n{context}"

    done = load_done_texts(output_path)
    prompts = [p for p in ANAMNESIS_PROMPTS_TEMPLATE if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Anamnesis] {len(prompts)} prompts with {len(doc_samples)} doc + {len(git_samples)} git samples")

    persona = PERSONAS["anamnesis"]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            full_prompt = f"{context}\n\n---\n\nQuestion: {prompt}"
            text, model = await call_teacher(full_prompt, persona["system"], teacher, temperature=0.6)
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text},
                ],
                "_meta": {
                    "persona": "anamnesis",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "context_docs": len(doc_samples),
                    "context_commits": len(git_samples),
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


def _extract_first_json_value(text: str) -> str | None:
    object_start = text.find("{")
    array_start = text.find("[")
    starts = [idx for idx in (object_start, array_start) if idx >= 0]
    start = min(starts) if starts else -1
    if start < 0:
        return None
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
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
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _normalize_json_only(text: str) -> str | None:
    raw = text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    candidates = [raw]
    extracted = _extract_first_json_value(raw)
    if extracted:
        candidates.append(extracted)
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            return json.dumps(parsed, ensure_ascii=True, separators=(",", ":"))
        except json.JSONDecodeError:
            continue
    return None


async def generate_monolith(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in MONOLITH_PROMPTS if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Monolith] {len(prompts)} prompts to generate")
    persona = PERSONAS["monolith"]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            text, model = await call_teacher(prompt, persona["system"], teacher, temperature=0.45)
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text.strip()},
                ],
                "_meta": {
                    "persona": "monolith",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


async def generate_conductor(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in CONDUCTOR_PROMPTS if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Conductor] {len(prompts)} prompts to generate")
    persona = PERSONAS["conductor"]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            text, model = await call_teacher(prompt, persona["system"], teacher, temperature=0.35)
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            normalized = _normalize_json_only(text)
            if not normalized:
                retry_prompt = (
                    f"{prompt}\n\n"
                    "[strict retry]\n"
                    "return only valid json.\n"
                    "no markdown, no prose, no comments."
                )
                retry_text, retry_model = await call_teacher(
                    retry_prompt,
                    persona["system"],
                    teacher,
                    temperature=0.0,
                )
                if retry_text:
                    text = retry_text
                    model = retry_model
                    normalized = _normalize_json_only(text)
            synthetic = False
            if not normalized:
                synthetic = True
                normalized = json.dumps(
                    {
                        "goal": prompt,
                        "nodes": [
                            {
                                "id": "analyze",
                                "agent": "analyst",
                                "deliverable": "problem breakdown, constraints, and acceptance criteria",
                            },
                            {
                                "id": "implement",
                                "agent": "builder",
                                "depends_on": ["analyze"],
                                "deliverable": "proposed implementation and patch plan",
                            },
                            {
                                "id": "validate",
                                "agent": "tester",
                                "depends_on": ["implement"],
                                "deliverable": "verification results and regressions check",
                            },
                            {
                                "id": "handoff",
                                "agent": "coordinator",
                                "depends_on": ["validate"],
                                "deliverable": "execution summary, open risks, and rollout notes",
                            },
                        ],
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": normalized},
                ],
                "_meta": {
                    "persona": "conductor",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "synthetic_fallback": synthetic,
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(normalized)} chars")


async def generate_steward(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in STEWARD_PROMPTS if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Steward] {len(prompts)} prompts to generate")
    persona = PERSONAS["steward"]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            text, model = await call_teacher(prompt, persona["system"], teacher, temperature=0.5)
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text.strip()},
                ],
                "_meta": {
                    "persona": "steward",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


async def generate_journalist(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in JOURNALIST_PROMPTS if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Journalist] {len(prompts)} prompts to generate")
    persona = PERSONAS["journalist"]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            text, model = await call_teacher(prompt, persona["system"], teacher, temperature=0.6)
            if not text:
                print(f"  [fail] prompt {i}", file=sys.stderr)
                continue
            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text.strip()},
                ],
                "_meta": {
                    "persona": "journalist",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


POET_FORM_RE = re.compile(r"\[FORM:([a-z_]+)\]", re.IGNORECASE)


def extract_poet_form(prompt: str) -> str:
    m = POET_FORM_RE.search(prompt)
    if not m:
        return "free_verse"
    return m.group(1).strip().lower()


def poet_synthetic_response(prompt: str, form: str = "free_verse") -> str:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", prompt.lower())
    uniq = []
    for w in words:
        if w not in uniq:
            uniq.append(w)
        if len(uniq) == 4:
            break
    while len(uniq) < 4:
        uniq.append(["night", "signal", "window", "quiet"][len(uniq)])
    a, b, c, d = uniq[:4]
    if form == "haiku":
        return (
            f"{a} under rain.\n"
            f"{b} drifts past {c}.\n"
            f"{d} starts the next line."
        )
    if form == "imagist":
        return (
            f"{a} on glass.\n"
            f"{b} light on keys.\n"
            f"{c} fan, {d} breath.\n"
            "one clean cursor."
        )
    if form == "sonnet_like":
        return (
            f"{a} arrives before the room can name the hour,\n"
            f"and {b} keeps tapping at the edge of thought.\n"
            f"I hold {c} like proof that focus still has power,\n"
            f"while {d} asks what the day forgot.\n"
            "I choose one task and close the rest away,\n"
            "let urgency be small enough to lift.\n"
            "A single line can turn a stalled-out day,\n"
            "a tiny commit can redirect the drift.\n"
            "No anthem here, no fireworks, no grand release,\n"
            "just sequence, breath, and work that starts to move.\n"
            "The noise does not disappear, but yields a piece,\n"
            "and that is usually enough to prove:\n"
            "the lock was not the door, it was delay;\n"
            "the hinge gives way when one step says: today."
        )
    if form == "prose_to_poem":
        return (
            f"I kept {a} and called it progress,\n"
            f"stacked {b} beside {c},\n"
            f"waited for {d} to decide for me.\n"
            "It did not.\n"
            "So I wrote one line,\n"
            "then another,\n"
            "and the room finally moved."
        )
    return (
        f"{a} flickers beside {b}.\n"
        f"{c} waits in the blue glow of a monitor.\n"
        f"I hold {d} like a warm cup gone cold.\n"
        "One tab closes.\n"
        "Another breath opens.\n"
        "The room does not applaud.\n"
        "It only gives me a small clean line,\n"
        "and enough night to keep going."
    )


def essayist_synthetic_response(prompt: str) -> str:
    return (
        "Thesis:\n"
        "Disciplined execution beats abstract optimization when progress is fragile.\n\n"
        "Outline:\n"
        "1. Define the core tension in the prompt.\n"
        "2. Present concrete examples and tradeoffs.\n"
        "3. Propose an actionable framework.\n"
        "4. Close with a practical next step.\n\n"
        f"Essay:\n{prompt}\n\n"
        "The central mistake in this problem class is treating clarity as optional. "
        "When priorities are vague, teams substitute motion for progress and optimization "
        "for delivery. A better approach is to force explicit sequencing: identify one "
        "irreversible action, define done criteria, then verify outcomes before expanding scope.\n\n"
        "This structure works because it reduces cognitive load and makes tradeoffs visible. "
        "Instead of juggling hypothetical improvements, it anchors attention on completed work. "
        "Execution creates evidence; evidence improves judgment; improved judgment enables better planning.\n\n"
        "Conclusion:\n"
        "Choose one concrete next action, make it irreversible where appropriate, and measure the result. "
        "Sustained quality emerges from repeated clear decisions, not from perfect plans."
    )


async def _generate_poet_dataset(
    persona_key: str,
    prompts_source: list[str],
    teacher: str,
    limit: int | None,
    output_path: Path,
) -> None:
    done = load_done_texts(output_path)
    prompts = [p for p in prompts_source if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[{persona_key}] {len(prompts)} prompts to generate")
    persona = PERSONAS[persona_key]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            synthetic = False
            model = ""
            text = ""
            form = extract_poet_form(prompt)
            try:
                text, model = await asyncio.wait_for(
                    call_teacher(prompt, persona["system"], teacher, temperature=0.85),
                    timeout=24,
                )
            except asyncio.TimeoutError:
                text, model = "", f"{teacher}-timeout"

            if not text:
                synthetic = True
                model = f"{(model or teacher)}-synthetic"
                text = poet_synthetic_response(prompt, form=form)

            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text.strip()},
                ],
                "_meta": {
                    "persona": persona_key,
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "synthetic_fallback": synthetic,
                    "form": form,
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


async def generate_poet(teacher: str, limit: int | None, output_path: Path):
    await _generate_poet_dataset("poet", POET_PROMPTS, teacher, limit, output_path)


async def generate_poet_v4(teacher: str, limit: int | None, output_path: Path):
    await _generate_poet_dataset("poet_v4", POET_FORM_CONTROL_PROMPTS, teacher, limit, output_path)


async def generate_essayist(teacher: str, limit: int | None, output_path: Path):
    done = load_done_texts(output_path)
    prompts = [p for p in ESSAYIST_PROMPTS if p[:80] not in done]
    if limit:
        prompts = prompts[:limit]
    print(f"[Essayist] {len(prompts)} prompts to generate")
    persona = PERSONAS["essayist"]

    with open(output_path, "a") as out:
        for i, prompt in enumerate(prompts):
            synthetic = False
            model = ""
            text = ""
            try:
                text, model = await asyncio.wait_for(
                    call_teacher(prompt, persona["system"], teacher, temperature=0.65),
                    timeout=90,
                )
            except asyncio.TimeoutError:
                text, model = "", f"{teacher}-timeout"

            if not text:
                synthetic = True
                model = model or f"{teacher}-synthetic"
                text = essayist_synthetic_response(prompt)

            record = {
                "messages": [
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text.strip()},
                ],
                "_meta": {
                    "persona": "essayist",
                    "teacher_model": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "synthetic_fallback": synthetic,
                },
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"  [{i+1}/{len(prompts)}] wrote {len(text)} chars")


# ─── Subcommands ──────────────────────────────────────────────────────────────

def cmd_mine(args):
    raw_dir = Path(args.output) if args.output else MINE_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)

    print("Mining Claude log user turns…")
    log_turns = mine_log_user_turns()
    print(f"  Found {len(log_turns)} user turns (non-private)")
    with open(raw_dir / "log_user_turns.jsonl", "w") as f:
        for s in log_turns:
            f.write(json.dumps(asdict(s)) + "\n")

    print("Mining git commit messages…")
    git_commits = mine_git_commits()
    print(f"  Found {len(git_commits)} commits across repos")
    with open(raw_dir / "git_commits.jsonl", "w") as f:
        for s in git_commits:
            f.write(json.dumps(asdict(s)) + "\n")

    print("Mining doc excerpts (CLAUDE.md, AGENTS.md, docs/)…")
    doc_excerpts = mine_doc_excerpts()
    print(f"  Found {len(doc_excerpts)} doc sections")
    with open(raw_dir / "doc_excerpts.jsonl", "w") as f:
        for s in doc_excerpts:
            f.write(json.dumps(asdict(s)) + "\n")

    print("Mining EchoFlow Swift models…")
    echoflow_models = mine_echoflow_models()
    print(f"  Found {len(echoflow_models)} model files")
    with open(raw_dir / "echoflow_models.jsonl", "w") as f:
        for s in echoflow_models:
            f.write(json.dumps(asdict(s)) + "\n")

    total = sum([len(log_turns), len(git_commits), len(doc_excerpts), len(echoflow_models)])
    print(f"\nDone. {total} raw samples written to {raw_dir}")


def cmd_voice(args):
    """Print a sample of user turn voice to understand the persona."""
    raw_dir = MINE_DIR
    log_file = raw_dir / "log_user_turns.jsonl"
    if not log_file.exists():
        print("No mined data. Run: persona_dataset.py mine", file=sys.stderr)
        sys.exit(1)

    samples = []
    for line in log_file.read_text().splitlines():
        try:
            d = json.loads(line)
            if len(d["text"]) > 80 and not d["text"].startswith("<"):
                samples.append(d)
        except Exception:
            pass

    print(f"Voice profile — {len(samples)} user turns mined\n")
    print("─── Sample turns (showing variety) ───\n")
    # Show a spread
    indices = [0, len(samples)//6, len(samples)//3, len(samples)//2,
               2*len(samples)//3, 5*len(samples)//6, len(samples)-1]
    for i in indices:
        if 0 <= i < len(samples):
            s = samples[i]
            print(f"[{s['project']}]")
            print(f"  {s['text'][:200]}")
            print()


def cmd_generate(args):
    persona = args.persona.lower()
    if persona not in PERSONAS:
        print(f"Unknown persona: {persona}. Choose: {', '.join(PERSONAS)}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else PERSONAS[persona]["output_file"]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    missing, vars_needed = missing_teacher_env(args.teacher)
    synthetic_ok = persona in {"poet", "poet_v4", "essayist"}
    if missing and not synthetic_ok:
        print(
            f"[error] Missing API key for teacher '{args.teacher}'. "
            f"Set one of: {', '.join(vars_needed)}",
            file=sys.stderr,
        )
        sys.exit(1)
    if missing and synthetic_ok:
        print(
            f"[warn] Missing API key for teacher '{args.teacher}'. "
            "Using synthetic fallback generation for this persona.",
            file=sys.stderr,
        )

    generators = {
        "sibyl": lambda: generate_sibyl(args.teacher, args.limit, output_path),
        "lancer": lambda: generate_lancer(args.teacher, args.limit, output_path),
        "morpheus": lambda: generate_morpheus(args.teacher, args.limit, output_path),
        "anamnesis": lambda: generate_anamnesis(args.teacher, args.limit, output_path, MINE_DIR),
        "monolith": lambda: generate_monolith(args.teacher, args.limit, output_path),
        "conductor": lambda: generate_conductor(args.teacher, args.limit, output_path),
        "steward": lambda: generate_steward(args.teacher, args.limit, output_path),
        "journalist": lambda: generate_journalist(args.teacher, args.limit, output_path),
        "poet": lambda: generate_poet(args.teacher, args.limit, output_path),
        "poet_v4": lambda: generate_poet_v4(args.teacher, args.limit, output_path),
        "essayist": lambda: generate_essayist(args.teacher, args.limit, output_path),
    }
    asyncio.run(generators[persona]())
    print(f"\nOutput: {output_path}")


def cmd_stats(args):
    if args.input:
        paths = [Path(args.input)]
    else:
        # All persona training files
        paths = [
            DATA_DIR / f"{p}_v1.jsonl" for p in PERSONAS
        ]
        paths = [p for p in paths if p.exists()]

    for path in paths:
        if not path.exists():
            continue
        records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        persona_counts: dict[str, int] = {}
        teacher_counts: dict[str, int] = {}
        for r in records:
            meta = r.get("_meta", {})
            p = meta.get("persona", "?")
            t = meta.get("teacher_model", "?")
            persona_counts[p] = persona_counts.get(p, 0) + 1
            teacher_counts[t] = teacher_counts.get(t, 0) + 1
        print(f"\n{path.name}: {len(records)} samples")
        print(f"  Personas: {persona_counts}")
        print(f"  Teachers: {teacher_counts}")


def main():
    parser = argparse.ArgumentParser(description="Persona training dataset builder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_mine = sub.add_parser("mine", help="Extract raw voice samples from logs/git/docs")
    p_mine.add_argument("--output", metavar="DIR", help=f"Output directory (default: {MINE_DIR})")

    sub.add_parser("voice", help="Show sampled user turn voice profile")

    p_gen = sub.add_parser("generate", help="Generate training pairs via teacher model")
    p_gen.add_argument("--persona", required=True, choices=list(PERSONAS),
                       help="Which persona to generate for")
    p_gen.add_argument("--teacher", choices=teacher_choices(), default="gemini")
    p_gen.add_argument("--limit", type=int, metavar="N")
    p_gen.add_argument("--output", "-o", metavar="FILE")

    p_stats = sub.add_parser("stats", help="Dataset statistics")
    p_stats.add_argument("--input", "-i", metavar="FILE")

    args = parser.parse_args()
    {
        "mine": cmd_mine,
        "voice": cmd_voice,
        "generate": cmd_generate,
        "stats": cmd_stats,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
