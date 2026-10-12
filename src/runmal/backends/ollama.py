"""Ollama chat adapter (S302): native /api/chat NDJSON -> normalized events.

Provider wire shapes stay inside this module (INV-001/002). The httpx client
(or transport) is injectable so recorded-fixture contract tests need no live
server. Errors map onto the S301 taxonomy (BACKEND_CONTRACT section 6).
The native embedding endpoint (S304) is POST /api/embed.
"""

from __future__ import annotations

import json

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
from runmal.backends.params import SamplingParams
from runmal.tokens import TokenQuality

SAMPLERS = frozenset({
    "temperature", "top_p", "top_k", "min_p", "seed", "stop",
    "max_tokens", "repetition_penalty", "context_length",
})
_OPTION_NAMES = {
    "temperature": "temperature", "top_p": "top_p", "top_k": "top_k",
    "min_p": "min_p", "seed": "seed", "stop": "stop",
    "max_tokens": "num_predict", "repetition_penalty": "repeat_penalty",
    "context_length": "num_ctx",
}


def map_status_error(status: int, text: str = ""):
    lowered = text.lower()
    if status in (401, 403):
        return AuthenticationFailed("ollama authentication failed")
    if status == 404 or "not found" in lowered:
        return ModelNotFound("ollama model not found")
    if status == 429:
        return RateLimited("ollama rate limited")
    if "context" in lowered and ("length" in lowered or "exceed" in lowered):
        return ContextOverflow("ollama context overflow")
    if status == 400:
        return InvalidRequest("ollama invalid request")
    if status >= 500:
        return BackendUnavailable(f"ollama unavailable (HTTP {status})")
    return ProviderError(f"ollama provider error (HTTP {status})")


def map_text_error(text: str):
    lowered = text.lower()
    if "not found" in lowered:
        return ModelNotFound("ollama model not found")
    if "context" in lowered:
        return ContextOverflow("ollama context overflow")
    return ProviderError("ollama provider error")


class OllamaChatBackend(ChatBackend):
    backend_key = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 model: str = "llama3.1", client: httpx.AsyncClient | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 api_key: str | None = None, timeout_s: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key  # unused by Ollama; never emitted (INV-023)
        self._timeout_s = timeout_s
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout_s, transport=transport)
        self._owns_client = client is None
        self.default_model = self._model_info(model)

    @staticmethod
    def _model_info(name: str, context_length: int | None = None) -> ModelInfo:
        return ModelInfo(
            model_id=name, display_name=name, backend_key="ollama",
            capabilities=Capabilities(
                chat=True, streaming=True, context_length=context_length,
                token_count_quality=TokenQuality.ESTIMATED,
                supported_samplers=SAMPLERS))

    def _options(self, params: SamplingParams) -> dict:
        filtered, _warnings = self.filter_params(params)
        return {_OPTION_NAMES[k]: v for k, v in filtered.to_bag().items()
                if k in _OPTION_NAMES}

    async def chat_stream(self, messages, params, cancel):
        if cancel.is_set():
            raise GenerationCancelled("generation cancelled")
        payload = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": self._options(params),
        }
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise map_status_error(resp.status_code, body)
                async for line in resp.aiter_lines():
                    if cancel.is_set():
                        raise GenerationCancelled("generation cancelled")
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get("error"):
                        raise map_text_error(str(obj["error"]))
                    content = (obj.get("message") or {}).get("content")
                    if content:
                        yield TextDelta(content)
                    if obj.get("done"):
                        usage = None
                        prompt = obj.get("prompt_eval_count")
                        completion = obj.get("eval_count")
                        if prompt is not None or completion is not None:
                            usage = UsageUpdate(
                                prompt_tokens=prompt, completion_tokens=completion,
                                total_tokens=(prompt or 0) + (completion or 0))
                            yield usage
                        yield Done(obj.get("done_reason") or "stop", usage)
                        return
        except httpx.TimeoutException as exc:
            raise BackendTimeout("ollama request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("ollama unreachable") from exc

    async def list_models(self) -> list[ModelInfo]:
        try:
            resp = await self._client.get("/api/tags")
        except httpx.TimeoutException as exc:
            raise BackendTimeout("ollama request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("ollama unreachable") from exc
        if resp.status_code >= 400:
            raise map_status_error(resp.status_code, resp.text)
        out = []
        for entry in resp.json().get("models", []):
            details = entry.get("details") or {}
            out.append(self._model_info(
                entry["name"], context_length=details.get("context_length")))
        return out

    async def health_check(self) -> HealthStatus:
        import time

        start = time.monotonic()
        try:
            resp = await self._client.get("/api/tags")
        except Exception as exc:  # health reports, never raises
            return HealthStatus(ok=False, detail=f"ollama unreachable: {type(exc).__name__}")
        latency = (time.monotonic() - start) * 1000
        if resp.status_code >= 400:
            return HealthStatus(ok=False, detail=f"ollama HTTP {resp.status_code}",
                                latency_ms=latency)
        return HealthStatus(ok=True, detail="ollama reachable", latency_ms=latency)
