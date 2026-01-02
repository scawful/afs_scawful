"""Integrations module for AFS external services."""

from .ollama_client import OllamaClient, ModelResponse

__all__ = [
    "ModelResponse",
    "OllamaClient",
]
