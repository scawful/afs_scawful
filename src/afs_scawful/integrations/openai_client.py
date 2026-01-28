"""OpenAI API client for chat completions and responses."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

from .ollama_client import ModelResponse

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_MODE_CHAT = "chat"
_MODE_RESPONSES = "responses"
_THINKING_EFFORT = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "max": "high",
}


def _normalize_mode(value: str | None) -> str:
    if not value:
        return _MODE_CHAT
    normalized = value.strip().lower()
    if normalized in {_MODE_CHAT, _MODE_RESPONSES}:
        return normalized
    return _MODE_CHAT


def _normalize_thinking_tier(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"none", "off", "false", "0"}:
        return None
    if normalized in _THINKING_EFFORT:
        return normalized
    return None


def _extract_text_from_chat(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def _extract_text_from_responses(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text
    for item in payload.get("output", []) or []:
        for part in item.get("content", []) or []:
            if not isinstance(part, dict):
                continue
            part_type = part.get("type")
            if part_type in {"output_text", "text"}:
                return part.get("text", "") or ""
    return ""


class OpenAIClient:
    """Async client for the OpenAI API."""

    supports_model_listing = True

    def __init__(
        self,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        timeout: int = 60,
        api_mode: str | None = None,
        organization: str | None = None,
    ):
        self.api_key_env = api_key_env
        self.api_key = api_key or os.environ.get(api_key_env)
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.api_mode = _normalize_mode(api_mode or os.environ.get("OPENAI_API_MODE"))
        if os.environ.get("OPENAI_USE_RESPONSES"):
            self.api_mode = _MODE_RESPONSES
        self.organization = (
            organization
            or os.environ.get("OPENAI_ORG_ID")
            or os.environ.get("OPENAI_ORGANIZATION")
        )

    def _headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        if extra_headers:
            headers.update({k: str(v) for k, v in extra_headers.items()})
        return headers

    def _with_system(self, messages: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        if not system:
            return list(messages)
        if messages and messages[0].get("role") == "system":
            return list(messages)
        return [{"role": "system", "content": system}] + list(messages)

    def _resolve_mode(self, options: dict[str, object] | None) -> str:
        option_mode = None
        if options and isinstance(options.get("api_mode"), str):
            option_mode = str(options.get("api_mode"))
        return _normalize_mode(option_mode or self.api_mode)

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
            logger.warning("OpenAI API key missing (%s).", self.api_key_env)
            return []
        url = f"{self.base_url}/models"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=self._headers()) as resp:
                    if resp.status != 200:
                        logger.error("OpenAI list_models failed: HTTP %s", resp.status)
                        return []
                    data = await resp.json()
                    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        except Exception as exc:
            logger.error("OpenAI list_models error: %s", exc)
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

        mode = self._resolve_mode(options)
        payload_messages = self._with_system(messages, system)
        thinking = _normalize_thinking_tier(thinking_tier)

        if mode == _MODE_RESPONSES:
            payload: dict[str, Any] = {
                "model": model,
                "input": payload_messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_output_tokens": max_tokens,
            }
            if thinking:
                payload.setdefault("reasoning", {"effort": _THINKING_EFFORT[thinking]})
            payload, extra_headers = self._apply_options(payload, options, {"model", "input"})
            url = f"{self.base_url}/responses"
        else:
            payload = {
                "model": model,
                "messages": payload_messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
            }
            if thinking:
                payload.setdefault("reasoning_effort", _THINKING_EFFORT[thinking])
            payload, extra_headers = self._apply_options(payload, options, {"model", "messages"})
            url = f"{self.base_url}/chat/completions"

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
                    if mode == _MODE_RESPONSES:
                        text = _extract_text_from_responses(data)
                        usage = data.get("usage", {})
                        tokens = int(usage.get("output_tokens", 0) or 0)
                    else:
                        text = _extract_text_from_chat(data)
                        usage = data.get("usage", {})
                        tokens = int(usage.get("completion_tokens", 0) or 0)
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
