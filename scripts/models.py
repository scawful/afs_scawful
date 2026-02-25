"""
models.py — Canonical model registry for afs-scawful.

All scripts MUST import model names from here. Never hardcode model strings.
Update GEMINI_PRO / GEMINI_FLASH here when new models release.

Usage:
    from models import GEMINI_PRO, GEMINI_FLASH, ANTHROPIC_DEFAULT
"""

import os
import re

# ── Current models ────────────────────────────────────────────────────────────

GEMINI_PRO     = "gemini-3.1-pro-preview"   # Deep reasoning / thinking
GEMINI_FLASH   = "gemini-3-flash-preview"   # Fast generation / variation

OPENAI_CODEX   = "codex-5.3"               # Code generation / synthesis

ANTHROPIC_SONNET  = "claude-sonnet-4-6"
ANTHROPIC_OPUS    = "claude-opus-4-6"
ANTHROPIC_DEFAULT = ANTHROPIC_SONNET        # Alias

# ── Teacher alias registry (single source of truth) ─────────────────────────
# Add new cloud teachers here, then scripts can consume aliases automatically.
TEACHER_ALIASES: dict[str, dict[str, object]] = {
    "gemini": {
        "model": GEMINI_FLASH,
        "env": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    },
    "gemini_flash": {
        "model": GEMINI_FLASH,
        "env": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    },
    "gemini_pro": {
        "model": GEMINI_PRO,
        "env": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    },
    "claude": {
        "model": ANTHROPIC_SONNET,
        "env": ("ANTHROPIC_API_KEY",),
    },
    "claude_opus": {
        "model": ANTHROPIC_OPUS,
        "env": ("ANTHROPIC_API_KEY",),
    },
    "openai": {
        "model": OPENAI_CODEX,
        "env": ("OPENAI_API_KEY",),
    },
    "codex": {
        "model": OPENAI_CODEX,
        "env": ("OPENAI_API_KEY",),
    },
}

# ── Enforcement ───────────────────────────────────────────────────────────────

# Minimum Gemini generation. Anything below this raises immediately.
_GEMINI_MIN_GENERATION = 3

_DEPRECATED: dict[str, str] = {
    "code-davinci-002":   "use OPENAI_CODEX",
    "code-cushman-001":   "use OPENAI_CODEX",
    "gpt-4":              "use OPENAI_CODEX or ANTHROPIC_DEFAULT",
    "gpt-4o":             "use OPENAI_CODEX or ANTHROPIC_DEFAULT",
    "gpt-4o-mini":        "use OPENAI_CODEX or ANTHROPIC_DEFAULT",
    "gemini-1.0-pro":        "use GEMINI_PRO",
    "gemini-1.5-pro":        "use GEMINI_PRO",
    "gemini-1.5-flash":      "use GEMINI_FLASH",
    "gemini-2.0-flash":      "use GEMINI_FLASH",
    "gemini-2.0-flash-exp":  "use GEMINI_FLASH",
    "gemini-2.0-flash-lite": "use GEMINI_FLASH",
    "gemini-2.5-pro":        "use GEMINI_PRO",
    "gemini-2.5-flash":      "use GEMINI_FLASH",
    "gemini-2.5-flash-lite": "use GEMINI_FLASH",
}


def use(model: str) -> str:
    """Validate and return a model name. Raises ValueError for deprecated/old models.

    Call this everywhere a model string is passed to an API client:
        client.models.generate_content(model=use(GEMINI_PRO), ...)
    """
    if model in _DEPRECATED:
        raise ValueError(
            f"\n\n  ✗ Deprecated model: {model!r}\n"
            f"  → {_DEPRECATED[model]}\n"
            f"  Import from scripts/models.py and never hardcode model strings.\n"
        )
    m = re.match(r"gemini-(\d+)", model)
    if m and int(m.group(1)) < _GEMINI_MIN_GENERATION:
        raise ValueError(
            f"\n\n  ✗ Model {model!r} is below minimum generation "
            f"(gemini-{_GEMINI_MIN_GENERATION}+)\n"
            f"  Use GEMINI_PRO or GEMINI_FLASH from scripts/models.py\n"
        )
    return model


def teacher_choices(*, include_internal: bool = False) -> list[str]:
    """Return valid teacher aliases for argparse.

    include_internal=True includes aliases like gemini_pro/gemini_flash.
    """
    keys = list(TEACHER_ALIASES.keys())
    if include_internal:
        return sorted(keys)
    return sorted(k for k in keys if not k.startswith("gemini_"))


def resolve_teacher_model(teacher: str) -> str:
    """Resolve a teacher alias to concrete model id and enforce deprecations."""
    if teacher not in TEACHER_ALIASES:
        raise ValueError(f"Unknown teacher alias: {teacher}")
    model = str(TEACHER_ALIASES[teacher]["model"])
    return use(model)


def missing_teacher_env(teacher: str) -> tuple[bool, tuple[str, ...]]:
    """Return (missing, candidate_env_vars) for a teacher alias."""
    if teacher not in TEACHER_ALIASES:
        raise ValueError(f"Unknown teacher alias: {teacher}")
    env_vars = tuple(str(v) for v in TEACHER_ALIASES[teacher]["env"])
    has_any = any(bool(os.environ.get(var)) for var in env_vars)
    return (not has_any), env_vars
