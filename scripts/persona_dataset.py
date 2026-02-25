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
            "Maximum two sentences. Go."
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
        resp = await client.chat.completions.create(
            model=use(OPENAI_CODEX),
            messages=messages,
            temperature=temperature,
            max_tokens=1024,
        )
        return resp.choices[0].message.content or "", None
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
    prompts = [p for p in LANCER_PROMPTS if p[:80] not in done]
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
    if missing:
        print(
            f"[error] Missing API key for teacher '{args.teacher}'. "
            f"Set one of: {', '.join(vars_needed)}",
            file=sys.stderr,
        )
        sys.exit(1)

    generators = {
        "sibyl": lambda: generate_sibyl(args.teacher, args.limit, output_path),
        "lancer": lambda: generate_lancer(args.teacher, args.limit, output_path),
        "morpheus": lambda: generate_morpheus(args.teacher, args.limit, output_path),
        "anamnesis": lambda: generate_anamnesis(args.teacher, args.limit, output_path, MINE_DIR),
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
