"""Ollama API client for model inference."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    """Response from model inference."""
    text: str
    model: str
    prompt: str
    latency_ms: float
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    done: bool = True
    context: list[int] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "prompt": self.prompt,
            "latency_ms": self.latency_ms,
            "tokens_generated": self.tokens_generated,
            "tokens_per_second": self.tokens_per_second,
            "done": self.done,
            "error": self.error,
        }


@dataclass
class Prompt:
    """A prompt for model inference."""
    instruction: str
    input: str = ""
    category: str = ""
    expected_keywords: list[str] = field(default_factory=list)

    @property
    def full_prompt(self) -> str:
        """Build full prompt text."""
        if self.input:
            return f"{self.instruction}\n\n{self.input}"
        return self.instruction


class OllamaClient:
    """Async client for Ollama API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def health_check(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.base_url}/api/tags") as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning("Ollama health check failed: %s", e)
            return False

    async def list_models(self) -> list[str]:
        """List available models."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/api/tags") as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    async def model_exists(self, model: str) -> bool:
        """Check if a specific model exists."""
        models = await self.list_models()
        return model in models or model.split(":")[0] in [m.split(":")[0] for m in models]

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        top_p: float = 0.8,
        max_tokens: int = 512,
        stream: bool = False,
    ) -> ModelResponse:
        """Generate a response from the model."""
        start_time = time.perf_counter()

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return ModelResponse(
                            text="",
                            model=model,
                            prompt=prompt,
                            latency_ms=(time.perf_counter() - start_time) * 1000,
                            error=f"HTTP {resp.status}: {error_text}",
                        )

                    if stream:
                        # Handle streaming response
                        full_text = ""
                        async for line in resp.content:
                            try:
                                data = json.loads(line.decode())
                                full_text += data.get("response", "")
                                if data.get("done"):
                                    break
                            except json.JSONDecodeError:
                                continue

                        latency = (time.perf_counter() - start_time) * 1000
                        return ModelResponse(
                            text=full_text,
                            model=model,
                            prompt=prompt,
                            latency_ms=latency,
                        )
                    else:
                        data = await resp.json()
                        latency = (time.perf_counter() - start_time) * 1000

                        # Extract timing info if available
                        tokens = data.get("eval_count", 0)
                        eval_duration = data.get("eval_duration", 0) / 1e9  # Convert ns to s
                        tps = tokens / eval_duration if eval_duration > 0 else 0

                        return ModelResponse(
                            text=data.get("response", ""),
                            model=model,
                            prompt=prompt,
                            latency_ms=latency,
                            tokens_generated=tokens,
                            tokens_per_second=tps,
                            done=data.get("done", True),
                            context=data.get("context", []),
                        )

        except asyncio.TimeoutError:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="Request timed out",
            )
        except Exception as e:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.8,
        max_tokens: int = 512,
    ) -> ModelResponse:
        """Send a chat completion request."""
        start_time = time.perf_counter()

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            },
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return ModelResponse(
                            text="",
                            model=model,
                            prompt=str(messages),
                            latency_ms=(time.perf_counter() - start_time) * 1000,
                            error=f"HTTP {resp.status}: {error_text}",
                        )

                    data = await resp.json()
                    latency = (time.perf_counter() - start_time) * 1000

                    message = data.get("message", {})
                    tokens = data.get("eval_count", 0)
                    eval_duration = data.get("eval_duration", 0) / 1e9
                    tps = tokens / eval_duration if eval_duration > 0 else 0

                    return ModelResponse(
                        text=message.get("content", ""),
                        model=model,
                        prompt=str(messages),
                        latency_ms=latency,
                        tokens_generated=tokens,
                        tokens_per_second=tps,
                        done=data.get("done", True),
                    )

        except asyncio.TimeoutError:
            return ModelResponse(
                text="",
                model=model,
                prompt=str(messages),
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="Request timed out",
            )
        except Exception as e:
            return ModelResponse(
                text="",
                model=model,
                prompt=str(messages),
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    async def generate_batch(
        self,
        model: str,
        prompts: list[Prompt],
        system: str = "",
        temperature: float = 0.7,
        top_p: float = 0.8,
        max_tokens: int = 512,
        concurrency: int = 5,
    ) -> list[ModelResponse]:
        """Generate responses for multiple prompts with controlled concurrency."""
        semaphore = asyncio.Semaphore(concurrency)

        async def limited_generate(prompt: Prompt) -> ModelResponse:
            async with semaphore:
                return await self.generate(
                    model=model,
                    prompt=prompt.full_prompt,
                    system=system,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                )

        tasks = [limited_generate(p) for p in prompts]
        return await asyncio.gather(*tasks)
