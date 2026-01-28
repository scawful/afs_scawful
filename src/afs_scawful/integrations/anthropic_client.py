"""Anthropic API client for chat completions."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

from .ollama_client import ModelResponse

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
_DEFAULT_VERSION = "2023-06-01"
_THINKING_BUDGETS = {
    "low": 1024,
    "medium": 4096,
    "high": 8192,
    "max": 16384,
}


def _normalize_thinking_tier(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"none", "off", "false", "0"}:
        return None
    if normalized in _THINKING_BUDGETS:
        return normalized
    return None


def _extract_text(payload: dict[str, Any]) -> str:
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    texts = []
    for part in content or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            texts.append(part.get("text", "") or "")
    return "".join(texts)


class AnthropicClient:
    """Async client for the Anthropic messages API."""

    supports_model_listing = True

    def __init__(
        self,
        api_key: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str | None = None,
        timeout: int = 60,
        api_version: str | None = None,
    ):
        self.api_key_env = api_key_env
        self.api_key = api_key or os.environ.get(api_key_env)
        self.base_url = (base_url or os.environ.get("ANTHROPIC_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.api_version = api_version or os.environ.get("ANTHROPIC_VERSION") or _DEFAULT_VERSION

    def _headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "x-api-key": str(self.api_key),
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        if extra_headers:
            headers.update({k: str(v) for k, v in extra_headers.items()})
        return headers

    def _build_messages(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> tuple[list[dict[str, str]], str]:
        payload_messages: list[dict[str, str]] = []
        system_text = system or ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "system":
                system_text = f"{system_text}\n{content}".strip() if system_text else content
                continue
            payload_messages.append({"role": role, "content": content})
        return payload_messages, system_text

    def _apply_options(
        self,
        payload: dict[str, Any],
        options: dict[str, object] | None,
        reserved: set[str],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        if not options:
            return payload, {}
        extra_headers = {}
        for key, value in options.items():
            if key == "headers" and isinstance(value, dict):
                extra_headers = {str(k): str(v) for k, v in value.items()}
                continue
            if key in reserved:
                continue
            payload[key] = value
        return payload, extra_headers

    async def list_models(self) -> list[str]:
        if not self.api_key:
            logger.warning("Anthropic API key missing (%s).", self.api_key_env)
            return []
        url = f"{self.base_url}/models"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=self._headers()) as resp:
                    if resp.status != 200:
                        logger.error("Anthropic list_models failed: HTTP %s", resp.status)
                        return []
                    data = await resp.json()
                    return [
                        m.get("id", "") or m.get("name", "")
                        for m in data.get("data", [])
                        if m.get("id") or m.get("name")
                    ]
        except Exception as exc:
            logger.error("Anthropic list_models error: %s", exc)
            return []

    async def model_exists(self, model: str) -> bool:
        models = await self.list_models()
        if not models:
            return True
        return model in models

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.8,
        max_tokens: int = 512,
        system: str = "",
        thinking_tier: str | None = None,
        options: dict[str, object] | None = None,
    ) -> ModelResponse:
        start_time = time.perf_counter()
        prompt = str(messages)

        if not self.api_key:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=0.0,
                error=f"{self.api_key_env} not set",
            )

        payload_messages, system_text = self._build_messages(messages, system)
        payload: dict[str, Any] = {
            "model": model,
            "messages": payload_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if system_text:
            payload["system"] = system_text

        thinking = _normalize_thinking_tier(thinking_tier)
        if thinking:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": _THINKING_BUDGETS[thinking],
            }

        payload, extra_headers = self._apply_options(payload, options, {"model", "messages"})
        url = f"{self.base_url}/messages"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=self._headers(extra_headers), json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return ModelResponse(
                            text="",
                            model=model,
                            prompt=prompt,
                            latency_ms=(time.perf_counter() - start_time) * 1000,
                            error=f"HTTP {resp.status}: {error_text}",
                        )

                    data = await resp.json()
                    latency = (time.perf_counter() - start_time) * 1000
                    text = _extract_text(data)
                    usage = data.get("usage", {})
                    tokens = int(usage.get("output_tokens", 0) or 0)
                    tps = tokens / (latency / 1000) if tokens and latency > 0 else 0.0
                    return ModelResponse(
                        text=text,
                        model=model,
                        prompt=prompt,
                        latency_ms=latency,
                        tokens_generated=tokens,
                        tokens_per_second=tps,
                        done=True,
                    )
        except asyncio.TimeoutError:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="Request timed out",
            )
        except Exception as exc:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(exc),
            )
