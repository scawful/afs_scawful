"""Google AI Studio and Vertex AI clients for Gemini API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Sequence

import aiohttp

from .ollama_client import ModelResponse

logger = logging.getLogger(__name__)

_STUDIO_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _guess_image_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "image/png"


def _build_parts(prompt: str, image_paths: Sequence[str] | None) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = []
    if prompt:
        parts.append({"text": prompt})
    if image_paths:
        for image_path in image_paths:
            path = Path(image_path).expanduser()
            if not path.exists():
                logger.warning("Image not found: %s", path)
                continue
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            parts.append(
                {
                    "inline_data": {
                        "mime_type": _guess_image_mime_type(path),
                        "data": data,
                    }
                }
            )
    return parts


def _extract_text(response_payload: dict[str, object]) -> str:
    candidates = response_payload.get("candidates", [])
    if not candidates:
        return ""
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "".join(texts)


def _extract_usage(response_payload: dict[str, object]) -> dict[str, int]:
    usage = response_payload.get("usageMetadata", {})
    if not isinstance(usage, dict):
        return {"candidates": 0, "prompt": 0, "total": 0}
    return {
        "candidates": int(usage.get("candidatesTokenCount", 0) or 0),
        "prompt": int(usage.get("promptTokenCount", 0) or 0),
        "total": int(usage.get("totalTokenCount", 0) or 0),
    }


class GoogleAIStudioClient:
    """Async client for the Gemini API via Google AI Studio."""

    supports_model_listing = True

    def __init__(
        self,
        api_key: str | None = None,
        api_key_env: str = "GEMINI_API_KEY",
        base_url: str = _STUDIO_BASE_URL,
        timeout: int = 60,
    ):
        self.api_key_env = api_key_env
        self.api_key = api_key or os.environ.get(api_key_env) or os.environ.get("AISTUDIO_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    def _resolve_model(self, model: str) -> str:
        if model.startswith("models/"):
            return model
        if "/" in model:
            return model
        return f"models/{model}"

    async def list_models(self) -> list[str]:
        if not self.api_key:
            logger.warning("AI Studio API key missing (%s).", self.api_key_env)
            return []
        url = f"{self.base_url}/models?key={self.api_key}"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.error("AI Studio list_models failed: HTTP %s", resp.status)
                        return []
                    data = await resp.json()
                    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception as exc:
            logger.error("AI Studio list_models error: %s", exc)
            return []

    async def model_exists(self, model: str) -> bool:
        models = await self.list_models()
        if not models:
            return True
        normalized = self._resolve_model(model)
        raw = model
        stripped = normalized.split("/", 1)[1] if normalized.startswith("models/") else normalized
        return normalized in models or raw in models or stripped in models

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        top_p: float = 0.8,
        max_tokens: int = 512,
        stream: bool = False,
        image_paths: Sequence[str] | None = None,
    ) -> ModelResponse:
        start_time = time.perf_counter()
        if not self.api_key:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=0.0,
                error=f"{self.api_key_env} not set",
            )

        if stream:
            logger.warning("AI Studio streaming not implemented; continuing without stream.")

        payload: dict[str, object] = {
            "contents": [
                {
                    "role": "user",
                    "parts": _build_parts(prompt, image_paths),
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "topP": top_p,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = f"{self.base_url}/{self._resolve_model(model)}:generateContent?key={self.api_key}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=payload) as resp:
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
                    usage = _extract_usage(data)
                    tokens = usage["candidates"]
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
        prompt = json.dumps(messages)
        start_time = time.perf_counter()

        if not self.api_key:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=0.0,
                error=f"{self.api_key_env} not set",
            )

        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if not text:
                continue
            contents.append({"role": role, "parts": [{"text": text}]})

        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topP": top_p,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if options:
            gen_config = options.get("generationConfig")
            if isinstance(gen_config, dict):
                payload["generationConfig"].update(gen_config)
            for key, value in options.items():
                if key in {"generationConfig", "headers"}:
                    continue
                payload[key] = value

        url = f"{self.base_url}/{self._resolve_model(model)}:generateContent?key={self.api_key}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=payload) as resp:
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
                    usage = _extract_usage(data)
                    tokens = usage["candidates"]
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


class VertexAIClient:
    """Async client for Gemini via Vertex AI."""

    supports_model_listing = True

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        base_url: str | None = None,
        gcloud_path: str = "gcloud",
        timeout: int = 60,
    ):
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or "halext"
        self.location = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_LOCATION") or "us-east1"
        self.base_url = (base_url or f"https://{self.location}-aiplatform.googleapis.com/v1").rstrip("/")
        self.gcloud_path = gcloud_path
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._token: str | None = None
        self._token_cached_at = 0.0
        self._token_ttl_seconds = 3000

    def _resolve_model(self, model: str) -> str:
        if model.startswith("projects/"):
            return model
        if model.startswith("publishers/"):
            return f"projects/{self.project}/locations/{self.location}/{model}"
        if model.startswith("models/"):
            model = model.split("/", 1)[1]
        return (
            f"projects/{self.project}/locations/{self.location}/publishers/google/models/{model}"
        )

    def _access_token_sync(self) -> str | None:
        env_token = os.environ.get("VERTEX_ACCESS_TOKEN") or os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
        if env_token:
            return env_token

        try:
            result = subprocess.run(
                [self.gcloud_path, "auth", "print-access-token"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            logger.error("gcloud not found (%s).", self.gcloud_path)
            return None

        if result.returncode != 0:
            logger.error("gcloud auth failed: %s", result.stderr.strip())
            return None

        token = result.stdout.strip()
        return token or None

    async def _access_token(self) -> str | None:
        now = time.time()
        if self._token and (now - self._token_cached_at) < self._token_ttl_seconds:
            return self._token
        token = await asyncio.to_thread(self._access_token_sync)
        if token:
            self._token = token
            self._token_cached_at = now
        return token

    async def list_models(self) -> list[str]:
        token = await self._access_token()
        if not token:
            return []

        url = (
            f"{self.base_url}/projects/{self.project}/locations/{self.location}/publishers/google/models"
        )
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.error("Vertex list_models failed: HTTP %s", resp.status)
                        return []
                    data = await resp.json()
                    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception as exc:
            logger.error("Vertex list_models error: %s", exc)
            return []

    async def model_exists(self, model: str) -> bool:
        models = await self.list_models()
        if not models:
            return True
        resolved = self._resolve_model(model)
        short_name = resolved.split("/")[-1]
        return resolved in models or model in models or short_name in models

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        top_p: float = 0.8,
        max_tokens: int = 512,
        stream: bool = False,
        image_paths: Sequence[str] | None = None,
    ) -> ModelResponse:
        start_time = time.perf_counter()
        token = await self._access_token()
        if not token:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=0.0,
                error="Vertex access token unavailable (run gcloud auth login)",
            )

        if stream:
            logger.warning("Vertex streaming not implemented; continuing without stream.")

        payload: dict[str, object] = {
            "contents": [
                {
                    "role": "user",
                    "parts": _build_parts(prompt, image_paths),
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "topP": top_p,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = f"{self.base_url}/{self._resolve_model(model)}:generateContent"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
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
                    usage = _extract_usage(data)
                    tokens = usage["candidates"]
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
        prompt = json.dumps(messages)
        start_time = time.perf_counter()
        token = await self._access_token()
        if not token:
            return ModelResponse(
                text="",
                model=model,
                prompt=prompt,
                latency_ms=0.0,
                error="Vertex access token unavailable (run gcloud auth login)",
            )

        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if not text:
                continue
            contents.append({"role": role, "parts": [{"text": text}]})

        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topP": top_p,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if options:
            gen_config = options.get("generationConfig")
            if isinstance(gen_config, dict):
                payload["generationConfig"].update(gen_config)
            for key, value in options.items():
                if key in {"generationConfig", "headers"}:
                    continue
                payload[key] = value

        url = f"{self.base_url}/{self._resolve_model(model)}:generateContent"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
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
                    usage = _extract_usage(data)
                    tokens = usage["candidates"]
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
