"""Generic OpenAI-compatible chat adapter (F-01, Part I follow-on).

One adapter for every endpoint that speaks the common OpenAI-shaped
surface (``POST /chat/completions`` SSE, ``GET /models``): OpenAI
itself, Mistral, DeepSeek, llama.cpp servers, TabbyAPI, KoboldCpp,
Text Generation WebUI, and any other compatible local or cloud
endpoint (P-008 ledger: 14 WANTED-GENERIC rows, one build). The
profile supplies ``base_url`` + model + an optional secret reference;
no per-brand code exists and no provider wire object crosses into
normalized events (INV-001/002). The connection layer's long-promised
``openai`` kind (S211) is this adapter's ``backend_key``.

Sampler truth: ``SAMPLERS`` is exactly the S208 ``openai`` wire
profile's key set. Canonical controls outside it (top_k, min_p,
repetition_penalty, context_length, and the P-052 sampler
families no OpenAI-shaped wire carries) are cleared by
``ChatBackend.filter_params`` with structured warnings — never sent,
never pretended honoured (INV-005). A future endpoint that serves
more declares it through its own adapter, not through this one
silently growing fields.

Wire discipline (lessons carried from P-009's Aesir findings, applied
generically): the request carries no ``stream_options`` and no
provider-specific usage toggle — some compatible servers reject
unknown fields outright — while usage is surfaced whenever the
server volunteers it. A stream that ends with neither the ``[DONE]``
terminal marker nor a finish reason is an incomplete stream: it
raises instead of yielding a fabricated ``Done``.

The API key is sent only as an Authorization header and never
serialized (INV-023). Token counting is the conservative estimator
(TokenQuality.ESTIMATED); server-reported usage surfaces as
UsageUpdate events.
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
from runmal.backends.events import Done, ReasoningDelta, TextDelta, UsageUpdate
from runmal.backends.models import Capabilities, HealthStatus, ModelInfo
from runmal.backends.structured import wire_payload
from runmal.tokens import TokenQuality

#: Default endpoint: OpenAI's own API. Any compatible endpoint is a
#: profile ``base_url`` away; the default names no assumption the
#: profile does not already make by choosing this backend.
DEFAULT_BASE_URL = "https://api.openai.com/v1"
#: Placeholder default model; real deployments select from
#: ``list_models()`` for their endpoint.
DEFAULT_MODEL = "gpt-4o-mini"

#: Canonical bag keys this adapter honours — exactly the S208
#: ``openai`` compatibility profile's wire names.
SAMPLERS = frozenset(
    {
        "temperature",
        "top_p",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "seed",
        # P-060: the OpenAI-shaped wire carries logit_bias as a
        # {token-id-string: bias} object; the adapter forwards the
        # canonical bag form unchanged.
        "logit_bias",
    }
)
#: Canonical bag key -> wire name (identity: the common shape spells
#: them as the canonical bag does). Public so tests and the
#: negotiation layer can pin the mapping to S208's profile.
WIRE_NAMES = {key: key for key in sorted(SAMPLERS)}
#: Canonical controls this adapter deliberately does NOT map, with
#: SAMPLERS accounting for every canonical control (INV-005).
UNSUPPORTED_SAMPLERS = frozenset(
    {"top_k", "min_p", "repetition_penalty", "context_length",
     "typical_p",
     "top_a",
     "tfs_z",
     "epsilon_cutoff",
     "eta_cutoff",
     "dry_multiplier",
     "dry_base",
     "dry_allowed_length",
     "dry_penalty_last_n",
     "dry_sequence_breakers",
     "xtc_probability",
     "xtc_threshold",
     "mirostat_mode",
     "mirostat_tau",
     "mirostat_eta",
     "dynamic_temperature_range",
     "dynamic_temperature_exponent",
    }
)


def map_error(code: int, message: str = ""):
    lowered = (message or "").lower()
    if code in (401, 403):
        return AuthenticationFailed("openai-compatible authentication failed")
    if code == 404 or "not found" in lowered:
        return ModelNotFound("openai-compatible model not found")
    if code == 429:
        return RateLimited("openai-compatible rate limited")
    if "context" in lowered and ("length" in lowered or "maximum" in lowered):
        return ContextOverflow("openai-compatible context overflow")
    if code in (400, 422):
        return InvalidRequest("openai-compatible invalid request")
    if code >= 500:
        return BackendUnavailable(f"openai-compatible unavailable (HTTP {code})")
    return ProviderError(f"openai-compatible provider error (HTTP {code})")


class OpenAICompatibleChatBackend(ChatBackend):
    backend_key = "openai"

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
            backend_key="openai",
            capabilities=Capabilities(
                chat=True,
                streaming=True,
                structured_output=True,
                context_length=context_length,
                max_output_tokens=max_output,
                token_count_quality=TokenQuality.ESTIMATED,
                supported_samplers=SAMPLERS,
            ),
        )

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        if cancel.is_set():
            raise GenerationCancelled("generation cancelled")
        filtered, _warnings = self.filter_params(params)
        payload = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
        }
        for key, value in filtered.to_bag().items():
            if key in WIRE_NAMES:
                payload[WIRE_NAMES[key]] = value
        if structured is not None and structured.is_active():
            payload.update(wire_payload(self.backend_key, structured))
        usage: UsageUpdate | None = None
        reason: str | None = None
        saw_terminal_marker = False
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
                        saw_terminal_marker = True
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
                        delta = choice.get("delta") or {}
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                        if reasoning:
                            yield ReasoningDelta(reasoning)
                        content = delta.get("content")
                        if content:
                            yield TextDelta(content)
                        if choice.get("finish_reason"):
                            reason = choice["finish_reason"]
        except httpx.TimeoutException as exc:
            raise BackendTimeout("openai-compatible request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("openai-compatible unreachable") from exc
        if not saw_terminal_marker and reason is None:
            raise ProviderError(
                "openai-compatible stream ended without a terminal marker"
            )
        if usage is not None:
            yield usage
        yield Done(reason or "stop", usage)

    async def list_models(self) -> list[ModelInfo]:
        try:
            resp = await self._client.get("/models")
        except httpx.TimeoutException as exc:
            raise BackendTimeout("openai-compatible request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("openai-compatible unreachable") from exc
        if resp.status_code >= 400:
            raise map_error(resp.status_code, resp.text)
        out = []
        for entry in resp.json().get("data", []):
            top = entry.get("top_provider") or {}
            out.append(
                self._model_info(
                    entry["id"],
                    entry.get("name") or entry["id"],
                    context_length=entry.get("context_length") or entry.get("context_window"),
                    max_output=entry.get("max_output_tokens")
                    or entry.get("max_completion_tokens")
                    or top.get("max_completion_tokens"),
                )
            )
        return out

    async def health_check(self) -> HealthStatus:
        start = time.monotonic()
        try:
            resp = await self._client.get("/models")
        except Exception as exc:  # health reports, never raises
            return HealthStatus(
                ok=False, detail=f"openai-compatible unreachable: {type(exc).__name__}"
            )
        latency = (time.monotonic() - start) * 1000
        if resp.status_code >= 400:
            return HealthStatus(
                ok=False, detail=f"openai-compatible HTTP {resp.status_code}", latency_ms=latency
            )
        return HealthStatus(ok=True, detail="openai-compatible reachable", latency_ms=latency)
