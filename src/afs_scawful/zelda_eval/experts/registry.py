"""
Expert model registry for the Triforce MoE system.

Din (Power)    - Assembly optimization, code generation
Nayru (Wisdom) - Code analysis, explanation
Farore (Courage) - Debugging, problem solving
Veran (Villain) - Deep analysis, edge cases

Supports remote Ollama via OLLAMA_HOST env var or --ollama-host CLI option.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import os
import httpx

# Default Ollama host - can be overridden by env var or CLI option
# Supports remote Vast.ai instances: export OLLAMA_HOST=http://<vast_host>:11434
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def get_ollama_host() -> str:
    """Get the Ollama host from environment or default.

    Ensures the URL has a scheme (http://) if not provided.
    """
    host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
    if host and not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host


class ExpertType(Enum):
    """Types of expert models."""

    DIN = "din"  # Power - optimization, low-level
    NAYRU = "nayru"  # Wisdom - generation, patterns
    FARORE = "farore"  # Courage - debugging, fixing
    VERAN = "veran"  # Analysis, explanation


@dataclass
class ModelRecord:
    """Record of an expert model."""

    name: str
    display_name: str
    model_id: str  # Ollama model ID (e.g., "din-v2:latest")
    expert_type: ExpertType
    specialty: str
    description: str

    # Routing keywords
    keywords: list[str] = field(default_factory=list)

    # Fallback model if primary not available
    fallback_model_id: str = "deepseek-coder:6.7b"

    # Model settings
    temperature: float = 0.7
    top_p: float = 0.9
    context_length: int = 4096

    # Ollama endpoint (default uses env var OLLAMA_HOST)
    host: str = field(default_factory=get_ollama_host)

    # Status
    enabled: bool = True
    available: bool = False  # Set after health check
    using_fallback: bool = False  # True if using fallback model

    def ollama_url(self, endpoint: str = "generate") -> str:
        """Get the Ollama API URL for this model."""
        return f"{self.host}/api/{endpoint}"

    def effective_model_id(self) -> str:
        """Get the model ID to use (primary or fallback)."""
        return self.fallback_model_id if self.using_fallback else self.model_id


class ExpertRegistry:
    """Registry of available expert models."""

    DEFAULT_EXPERTS = {
        "din": ModelRecord(
            name="din",
            display_name="Din (Power)",
            model_id="din-v4:latest",
            expert_type=ExpertType.DIN,
            specialty="Assembly optimization and code generation",
            description="Specializes in 65816 assembly optimization, efficient routines, and low-level code generation.",
            keywords=[
                "optimize",
                "faster",
                "smaller",
                "efficient",
                "mvn",
                "dma",
                "loop",
                "unroll",
                "inline",
                "cycles",
            ],
            temperature=0.5,  # Lower for more deterministic code
        ),
        "nayru": ModelRecord(
            name="nayru",
            display_name="Nayru (Wisdom)",
            model_id="nayru-v7:latest",
            expert_type=ExpertType.NAYRU,
            specialty="Code generation and pattern implementation",
            description="Specializes in generating new assembly routines, implementing patterns, and creating features.",
            keywords=[
                "write",
                "create",
                "implement",
                "generate",
                "new",
                "routine",
                "function",
                "subroutine",
                "feature",
            ],
            temperature=0.7,
        ),
        "farore": ModelRecord(
            name="farore",
            display_name="Farore (Courage)",
            model_id="farore-v3:latest",
            expert_type=ExpertType.FARORE,
            specialty="Debugging and problem solving",
            description="Specializes in finding bugs, fixing crashes, and diagnosing issues in assembly code.",
            keywords=[
                "debug",
                "fix",
                "bug",
                "crash",
                "error",
                "wrong",
                "broken",
                "issue",
                "problem",
                "why",
            ],
            temperature=0.4,  # Lower for careful analysis
        ),
        "veran": ModelRecord(
            name="veran",
            display_name="Veran (Analysis)",
            model_id="veran-v3:latest",
            expert_type=ExpertType.VERAN,
            specialty="Code analysis and explanation",
            description="Specializes in explaining assembly code, documenting routines, and deep analysis.",
            keywords=[
                "explain",
                "analyze",
                "what",
                "how",
                "describe",
                "document",
                "understand",
                "means",
                "does",
            ],
            temperature=0.6,
        ),
    }

    def __init__(self, host: str | None = None):
        """
        Initialize expert registry.

        Args:
            host: Ollama host URL. If not provided, uses OLLAMA_HOST env var
                  or defaults to http://localhost:11434.
                  For Vast.ai: export OLLAMA_HOST=http://<vast_host>:11434
        """
        # Normalize host to ensure it has http:// scheme
        if host:
            if not host.startswith(("http://", "https://")):
                host = f"http://{host}"
            self.host = host
        else:
            self.host = get_ollama_host()
        self._experts: dict[str, ModelRecord] = {}

        # Load defaults with configured host
        for name, record in self.DEFAULT_EXPERTS.items():
            record.host = self.host
            self._experts[name] = record

    def get(self, name: str) -> ModelRecord | None:
        """Get an expert by name."""
        return self._experts.get(name)

    def list_experts(self) -> list[ModelRecord]:
        """List all registered experts."""
        return list(self._experts.values())

    def list_available(self) -> list[ModelRecord]:
        """List only available (healthy) experts."""
        return [e for e in self._experts.values() if e.available]

    async def check_availability(self) -> dict[str, bool]:
        """Check which experts are available via Ollama.

        Checks primary model first, then fallback if primary unavailable.
        """
        results = {}

        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, expert in self._experts.items():
                try:
                    # Check if primary model exists
                    response = await client.post(
                        expert.ollama_url("show"),
                        json={"name": expert.model_id},
                    )
                    if response.status_code == 200:
                        expert.available = True
                        expert.using_fallback = False
                    else:
                        # Try fallback model
                        response = await client.post(
                            expert.ollama_url("show"),
                            json={"name": expert.fallback_model_id},
                        )
                        if response.status_code == 200:
                            expert.available = True
                            expert.using_fallback = True
                        else:
                            expert.available = False
                except Exception:
                    expert.available = False

                results[name] = expert.available

        return results

    def route_query(self, query: str) -> tuple[str, float]:
        """
        Route a query to the best expert based on keywords.

        Returns (expert_name, confidence_score).
        """
        query_lower = query.lower()
        scores: dict[str, float] = {}

        for name, expert in self._experts.items():
            if not expert.enabled:
                continue

            # Count keyword matches
            matches = sum(1 for kw in expert.keywords if kw in query_lower)
            if matches > 0:
                # Normalize by number of keywords
                scores[name] = matches / len(expert.keywords)

        if not scores:
            # Default to veran for general queries
            return ("veran", 0.3)

        best = max(scores, key=lambda k: scores[k])
        return (best, scores[best])

    async def generate(
        self,
        expert_name: str,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a response using an expert model.

        Automatically falls back to fallback model if primary returns 404.
        """
        expert = self.get(expert_name)
        if not expert:
            raise ValueError(f"Unknown expert: {expert_name}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Try primary model first (unless we already know to use fallback)
            models_to_try = (
                [expert.fallback_model_id]
                if expert.using_fallback
                else [expert.model_id, expert.fallback_model_id]
            )

            for model_id in models_to_try:
                payload = {
                    "model": model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": kwargs.get("temperature", expert.temperature),
                        "top_p": kwargs.get("top_p", expert.top_p),
                        "num_ctx": kwargs.get("context_length", expert.context_length),
                    },
                }

                if system:
                    payload["system"] = system

                response = await client.post(
                    expert.ollama_url("generate"),
                    json=payload,
                )

                if response.status_code == 404:
                    # Model not found, try fallback
                    expert.using_fallback = True
                    continue

                response.raise_for_status()
                data = response.json()
                return data.get("response", "")

            # If we get here, both models failed
            raise ValueError(f"No available model for expert {expert_name}")
