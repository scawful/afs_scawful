"""Integrations module for AFS external services."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .google_genai_client import GoogleAIStudioClient, VertexAIClient
    from .ollama_client import OllamaClient, ModelResponse
    from .openai_client import OpenAIClient
    from .anthropic_client import AnthropicClient

__all__ = [
    "ModelResponse",
    "OllamaClient",
    "GoogleAIStudioClient",
    "VertexAIClient",
    "OpenAIClient",
    "AnthropicClient",
]


def __getattr__(name: str):
    if name == "ModelResponse":
        from .ollama_client import ModelResponse
        return ModelResponse
    if name == "OllamaClient":
        from .ollama_client import OllamaClient
        return OllamaClient
    if name == "GoogleAIStudioClient":
        from .google_genai_client import GoogleAIStudioClient
        return GoogleAIStudioClient
    if name == "VertexAIClient":
        from .google_genai_client import VertexAIClient
        return VertexAIClient
    if name == "OpenAIClient":
        from .openai_client import OpenAIClient
        return OpenAIClient
    if name == "AnthropicClient":
        from .anthropic_client import AnthropicClient
        return AnthropicClient
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
