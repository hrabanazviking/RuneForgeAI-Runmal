"""OpenRouter adapter (S303): OpenAI-compatible SSE -> normalized events.

Namespaced model IDs (e.g. ``openai/gpt-4o-mini``) live only inside this
adapter and in ModelInfo metadata; no provider wire object (chunk, routing
metadata, error payload) crosses into normalized events (INV-001/002).
The API key is sent only as an Authorization header and never serialized.
"""

from __future__ import annotations

import json
import time

import httpx

from runmal.backends.base import ChatBackend
from runmal.backends.errors import (
    AuthenticationFailed,
    BackendTimeout,
    BackendUnavailable,
    ContextOverflow,
    GenerationCancelled,
    InvalidRequest,
    ModelNotFound,
    ProviderError,
    RateLimited,
)
from runmal.backends.events import Done, TextDelta, UsageUpdate
from runmal.backends.models import Capabilities, HealthStatus, ModelInfo
from runmal.tokens import TokenQuality

SAMPLERS = frozenset({
    "temperature", "top_p", "max_tokens", "frequency_penalty",
    "presence_penalty", "stop", "seed",
})
_WIRE_NAMES = {
    "temperature": "temperature", "top_p": "top_p", "max_tokens": "max_tokens",
    "frequency_penalty": "frequency_penalty",
    "presence_penalty": "presence_penalty", "stop": "stop", "seed": "seed",
}


def map_error(code: int, message: str = ""):
    lowered = (message or "").lower()
    if code in (401, 403):
        return AuthenticationFailed("openrouter authentication failed")
    if code == 404 or "no endpoints" in lowered or "not found" in lowered:
        return ModelNotFound("openrouter model not found")
    if code == 429:
        return RateLimited("openrouter rate limited")
    if "context" in lowered and ("length" in lowered or "maximum" in lowered):
        return ContextOverflow("openrouter context overflow")
    if code == 400:
        return InvalidRequest("openrouter invalid request")
    if code >= 500:
        return BackendUnavailable(f"openrouter unavailable (HTTP {code})")
    return ProviderError(f"openrouter provider error (HTTP {code})")


class OpenRouterChatBackend(ChatBackend):
    backend_key = "openrouter"

    def __init__(self, api_key: str | None = None,
                 model: str = "openai/gpt-4o-mini",
                 base_url: str = "https://openrouter.ai/api/v1",
                 client: httpx.AsyncClient | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout_s: float = 60.0):
        self._api_key = api_key  # header only; never emitted (INV-023)
        self._model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_s,
            transport=transport, headers=headers)
        self.default_model = self._model_info(model, model)

    @staticmethod
    def _model_info(model_id: str, name: str, context_length=None,
                    max_output=None) -> ModelInfo:
        return ModelInfo(
            model_id=model_id, display_name=name, backend_key="openrouter",
            capabilities=Capabilities(
                chat=True, streaming=True, context_length=context_length,
                max_output_tokens=max_output,
                token_count_quality=TokenQuality.PROVIDER,
                supported_samplers=SAMPLERS))

    async def chat_stream(self, messages, params, cancel):
        if cancel.is_set():
            raise GenerationCancelled("generation cancelled")
        filtered, _w = self.filter_params(params)
        payload = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "usage": {"include": True},
        }
        for key, value in filtered.to_bag().items():
            if key in _WIRE_NAMES:
                payload[_WIRE_NAMES[key]] = value
        usage: UsageUpdate | None = None
        reason = "stop"
        try:
            async with self._client.stream(
                    "POST", "/chat/completions", json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise map_error(resp.status_code, body)
                async for line in resp.aiter_lines():
                    if cancel.is_set():
                        raise GenerationCancelled("generation cancelled")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    if not data:
                        continue
                    obj = json.loads(data)
                    if obj.get("error"):
                        err = obj["error"] or {}
                        raise map_error(int(err.get("code") or 500),
                                        str(err.get("message") or ""))
                    raw_usage = obj.get("usage")
                    if raw_usage:
                        usage = UsageUpdate(
                            prompt_tokens=raw_usage.get("prompt_tokens"),
                            completion_tokens=raw_usage.get("completion_tokens"),
                            total_tokens=raw_usage.get("total_tokens"))
                    choices = obj.get("choices") or []
                    if choices:
                        choice = choices[0]
                        content = (choice.get("delta") or {}).get("content")
                        if content:
                            yield TextDelta(content)
                        if choice.get("finish_reason"):
                            reason = choice["finish_reason"]
        except httpx.TimeoutException as exc:
            raise BackendTimeout("openrouter request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("openrouter unreachable") from exc
        if usage is not None:
            yield usage
        yield Done(reason, usage)

    async def list_models(self) -> list[ModelInfo]:
        try:
            resp = await self._client.get("/models")
        except httpx.TimeoutException as exc:
            raise BackendTimeout("openrouter request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("openrouter unreachable") from exc
        if resp.status_code >= 400:
            raise map_error(resp.status_code, resp.text)
        out = []
        for entry in resp.json().get("data", []):
            top = entry.get("top_provider") or {}
            out.append(self._model_info(
                entry["id"], entry.get("name") or entry["id"],
                context_length=entry.get("context_length"),
                max_output=top.get("max_completion_tokens")))
        return out

    async def health_check(self) -> HealthStatus:
        start = time.monotonic()
        try:
            resp = await self._client.get("/models")
        except Exception as exc:  # health reports, never raises
            return HealthStatus(
                ok=False, detail=f"openrouter unreachable: {type(exc).__name__}")
        latency = (time.monotonic() - start) * 1000
        if resp.status_code >= 400:
            return HealthStatus(ok=False, detail=f"openrouter HTTP {resp.status_code}",
                                latency_ms=latency)
        return HealthStatus(ok=True, detail="openrouter reachable", latency_ms=latency)
