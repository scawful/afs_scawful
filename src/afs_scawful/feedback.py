"""Feedback logger for chat inference — shared by chat_harness and gateway.

Writes preference feedback in a format directly consumable by
build_preference_data.py for KTO/DPO alignment training.

Output format (JSONL):
    {"id": "fb_<hex>", "timestamp": "...", "prompt": "...", "response": "...",
     "model": "...", "feedback_score": 1/-1, "feedback_text": "...",
     "metadata": {...}}
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Default feedback log directory. Override with FEEDBACK_LOG_DIR for a project-local
# or private training-data location.
_DEFAULT_FEEDBACK_DIR = Path.home() / ".local" / "state" / "afs" / "chat-feedback"


def _feedback_dir() -> Path:
    return Path(os.environ.get("FEEDBACK_LOG_DIR", str(_DEFAULT_FEEDBACK_DIR)))


def _today_file() -> Path:
    d = _feedback_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"feedback_{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def log_feedback(
    prompt: str,
    response: str,
    score: int,
    model: str = "",
    text: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log a single feedback entry.

    Args:
        prompt: The user message that produced the response.
        response: The assistant response being rated.
        score: 1 (good), -1 (bad), 0 (neutral).
        model: Model name/id that produced the response.
        text: Optional freeform note about why.
        metadata: Optional extra metadata.

    Returns:
        The feedback record that was written.
    """
    if score not in (-1, 0, 1):
        raise ValueError("score must be -1, 0, or 1")

    record = {
        "id": f"fb_{uuid.uuid4().hex[:12]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "response": response,
        "model": model,
        "feedback_score": score,
        "feedback_text": text,
        "metadata": metadata or {},
    }

    path = _today_file()
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def recent_feedback(days: int = 7) -> list[dict[str, Any]]:
    """Read recent feedback entries for review."""
    d = _feedback_dir()
    if not d.exists():
        return []

    rows = []
    for f in sorted(d.glob("feedback_*.jsonl"), reverse=True)[:days]:
        for line in f.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def feedback_stats(days: int = 30) -> dict[str, Any]:
    """Summary stats across recent feedback."""
    rows = recent_feedback(days)
    pos = sum(1 for r in rows if r.get("feedback_score", 0) > 0)
    neg = sum(1 for r in rows if r.get("feedback_score", 0) < 0)
    neu = len(rows) - pos - neg

    by_model: dict[str, dict[str, int]] = {}
    for r in rows:
        m = r.get("model", "unknown")
        if m not in by_model:
            by_model[m] = {"positive": 0, "negative": 0, "neutral": 0}
        if r.get("feedback_score", 0) > 0:
            by_model[m]["positive"] += 1
        elif r.get("feedback_score", 0) < 0:
            by_model[m]["negative"] += 1
        else:
            by_model[m]["neutral"] += 1

    return {
        "total": len(rows),
        "positive": pos,
        "negative": neg,
        "neutral": neu,
        "by_model": by_model,
        "days_covered": days,
    }
