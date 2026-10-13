"""Aesir chat adapter (S701): OpenAI-compatible surface -> normalized events.

Project Aesir is Rúnmál's local sovereign inference heart. Per
BACKEND_CONTRACT section 12, the adapter speaks Aesir's OpenAI-compatible
external surface (``POST /chat/completions``, ``GET /models``) while
Rúnmál's internal contract stays its own normalized interface (INV-001/002).
No Aesir wire object (chunk, error payload, routing detail) crosses into
normalized events.

The base URL is configuration, never a domain assumption: profiles may set
``base_url`` in their config (S306); the default below is the adapter's
documented local default. Nothing in this module reaches the Aesir host
machine — it is an HTTP client for the Aesir *server surface* only.

Sampler truth (S702, INV-005): ``SAMPLERS`` declares exactly the canonical
controls this adapter maps onto the wire (``_WIRE_NAMES``). Canonical
controls outside that set — presence/frequency penalty and requested
context length — are NOT sent; ``ChatBackend.filter_params`` clears them
with structured warnings driven by the declared set, never by provider-name
conditionals in domain code.

An optional bearer key (from a profile secret reference, resolved
server-side) is sent only as an Authorization header and never serialized
(INV-023). Token counting is the conservative estimator
(TokenQuality.ESTIMATED); server-reported usage surfaces as UsageUpdate
events, never as a silent quality upgrade.
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

#: Adapter default endpoint for a locally served Aesir (profile-configurable).
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
#: Placeholder model name used only when a profile names no model; a real
#: deployment selects from ``list_models()``. Aesir serves local models, so
#: there is no provider-namespaced ID space to leak (contrast S303).
DEFAULT_MODEL = "local-model"

#: Canonical bag keys this adapter honors (S702 mapping, BACKEND_CONTRACT §4).
SAMPLERS = frozenset(
    {
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "repetition_penalty",
        "max_tokens",
        "stop",
        "seed",
    }
)
#: Canonical bag key -> Aesir wire name. ``repetition_penalty`` is the one
#: rename: the OpenAI-compatible local-engine surface spells it
#: ``repeat_penalty``.
_WIRE_NAMES = {
    "temperature": "temperature",
    "top_p": "top_p",
    "top_k": "top_k",
    "min_p": "min_p",
    "repetition_penalty": "repeat_penalty",
    "max_tokens": "max_tokens",
    "stop": "stop",
    "seed": "seed",
}


def map_error(code: int, message: str = ""):
    lowered = (message or "").lower()
    if code in (401, 403):
        return AuthenticationFailed("aesir authentication failed")
    if code == 404 or "not found" in lowered:
        return ModelNotFound("aesir model not found")
    if code == 429:
        return RateLimited("aesir rate limited")
    if "context" in lowered and ("length" in lowered or "maximum" in lowered):
        return ContextOverflow("aesir context overflow")
    if code == 400:
        return InvalidRequest("aesir invalid request")
    if code >= 500:
        return BackendUnavailable(f"aesir unavailable (HTTP {code})")
    return ProviderError(f"aesir provider error (HTTP {code})")


class AesirChatBackend(ChatBackend):
    backend_key = "aesir"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 60.0,
    ):
        self._api_key = api_key  # header only; never emitted (INV-023)
        self._model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport, headers=headers
        )
        self.default_model = self._model_info(model, model)

    @staticmethod
    def _model_info(model_id: str, name: str, context_length=None, max_output=None) -> ModelInfo:
        return ModelInfo(
            model_id=model_id,
            display_name=name,
            backend_key="aesir",
            capabilities=Capabilities(
                chat=True,
                streaming=True,
                context_length=context_length,
                max_output_tokens=max_output,
                token_count_quality=TokenQuality.ESTIMATED,
                supported_samplers=SAMPLERS,
            ),
        )

    async def chat_stream(self, messages, params, cancel):
        if cancel.is_set():
            raise GenerationCancelled("generation cancelled")
        filtered, _w = self.filter_params(params)
        payload = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        for key, value in filtered.to_bag().items():
            if key in _WIRE_NAMES:
                payload[_WIRE_NAMES[key]] = value
        usage: UsageUpdate | None = None
        reason = "stop"
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
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
                        raise map_error(int(err.get("code") or 500), str(err.get("message") or ""))
                    raw_usage = obj.get("usage")
                    if raw_usage:
                        usage = UsageUpdate(
                            prompt_tokens=raw_usage.get("prompt_tokens"),
                            completion_tokens=raw_usage.get("completion_tokens"),
                            total_tokens=raw_usage.get("total_tokens"),
                        )
                    choices = obj.get("choices") or []
                    if choices:
                        choice = choices[0]
                        content = (choice.get("delta") or {}).get("content")
                        if content:
                            yield TextDelta(content)
                        if choice.get("finish_reason"):
                            reason = choice["finish_reason"]
        except httpx.TimeoutException as exc:
            raise BackendTimeout("aesir request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("aesir unreachable") from exc
        if usage is not None:
            yield usage
        yield Done(reason, usage)

    async def list_models(self) -> list[ModelInfo]:
        try:
            resp = await self._client.get("/models")
        except httpx.TimeoutException as exc:
            raise BackendTimeout("aesir request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("aesir unreachable") from exc
        if resp.status_code >= 400:
            raise map_error(resp.status_code, resp.text)
        out = []
        for entry in resp.json().get("data", []):
            out.append(
                self._model_info(
                    entry["id"],
                    entry.get("name") or entry["id"],
                    context_length=entry.get("context_length"),
                    max_output=entry.get("max_output_tokens"),
                )
            )
        return out

    async def health_check(self) -> HealthStatus:
        start = time.monotonic()
        try:
            resp = await self._client.get("/models")
        except Exception as exc:  # health reports, never raises
            return HealthStatus(ok=False, detail=f"aesir unreachable: {type(exc).__name__}")
        latency = (time.monotonic() - start) * 1000
        if resp.status_code >= 400:
            return HealthStatus(
                ok=False, detail=f"aesir HTTP {resp.status_code}", latency_ms=latency
            )
        return HealthStatus(ok=True, detail="aesir reachable", latency_ms=latency)
