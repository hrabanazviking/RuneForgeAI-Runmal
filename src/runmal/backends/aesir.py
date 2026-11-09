"""Aesir chat adapter (S701, repaired F-02): OpenAI surface -> events.

Project Aesir is Rúnmál's local sovereign inference heart. Per
BACKEND_CONTRACT section 12, the adapter speaks Aesir's OpenAI-compatible
external surface (``POST /chat/completions``, ``GET /models``) while
Rúnmál's internal contract stays its own normalized interface (INV-001/002).
No Aesir wire object (chunk, error payload, routing detail) crosses into
normalized events.

Binding truth (P-009 readiness check, repaired by the P-014 gate's
F-02 follow-on; Aesir's own v1 API matrix is the source):

- The default base URL is Aesir's native ``serve`` port, 18434
  (P-009 D4: the old :8000 default reached nothing). Profiles may
  still set ``base_url`` in their config (S306) — Aesir's
  ``--ollama`` mode at 11434 is the other named port.
- No ``stream_options`` is sent (P-009 D1: Aesir's chat route
  rejects the field outright). Usage is surfaced only when the
  server volunteers it; Aesir's matrix says its stream carries
  none, and none is requested.
- ``SAMPLERS`` declares exactly the sampler subset Aesir's
  OpenAI chat route serves — temperature, top_p, max_tokens,
  seed (P-009 D2). The full canonical set Rúnmál wants is
  served on Aesir's native ``/v1/generate`` route instead;
  rebinding to that route is a separate binding choice, not
  this repair. Controls outside the served subset are cleared
  with structured warnings — never sent, never pretended
  honoured (INV-005).
- A stream that ends with neither the ``[DONE]`` terminal
  marker nor a finish reason is incomplete (P-009 D6): it
  raises instead of yielding a fabricated ``Done``.
- HTTP 422 is Aesir's context/generation admission refusal
  and maps to ``ContextOverflow`` (P-009 D8).
- Resident-model readiness is Aesir's ``/health/ready`` truth
  at the server root (native mode), surfaced by
  :meth:`AesirChatBackend.readiness_check` — the narrowed
  VX-19 home from the P-014 gate. Rúnmál estimates no VRAM.
  ``health_check`` stays the ``/models`` reachability probe
  that works in both of Aesir's modes; a listed/catalog model
  is NOT readiness (P-009 D5).

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
from runmal.backends.events import Done, ReasoningDelta, TextDelta, UsageUpdate
from runmal.backends.models import Capabilities, HealthStatus, ModelInfo
from runmal.tokens import TokenQuality

#: Adapter default endpoint: Aesir's native serve port (P-009 D4,
#: repaired F-02). Profile-configurable via ``config.base_url``.
DEFAULT_BASE_URL = "http://127.0.0.1:18434/v1"
#: Placeholder model name used only when a profile names no model; a real
#: deployment selects from ``list_models()``. Aesir serves local models, so
#: there is no provider-namespaced ID space to leak (contrast S303).
DEFAULT_MODEL = "local-model"

#: Canonical bag keys Aesir's OpenAI chat route actually serves
#: (P-009 D2, from Aesir's own v1 matrix). Exactly this subset is
#: declared honoured; everything else is declared unsupported.
SAMPLERS = frozenset(
    {
        "temperature",
        "top_p",
        "max_tokens",
        "seed",
    }
)
#: Canonical bag key -> Aesir wire name (identity on the served
#: subset: the OpenAI route spells them as the canonical bag
#: does). Public so the S310 negotiation layer can build the
#: S208 compatibility profile from the adapter's own mapping.
WIRE_NAMES = {key: key for key in sorted(SAMPLERS)}
#: Canonical controls the OpenAI chat route does NOT serve
#: (P-009 D2): top_k, min_p, repetition_penalty and stop are
#: rejected fields on that route (the full sampler set lives
#: on the native /v1/generate route); presence/frequency
#: penalties are cloud-API shaping controls the local surface
#: does not declare; requested context length is an engine
#: property, not a per-request control. Together with
#: ``SAMPLERS`` this set accounts for EVERY canonical control
#: — there is no third, silently ignored category (INV-005).
UNSUPPORTED_SAMPLERS = frozenset(
    {
        "top_k",
        "min_p",
        "repetition_penalty",
        "stop",
        # P-060: logit_bias joins the canonical vocabulary; the
        # OpenAI chat route does not serve it either (P-009 D2
        # shape: unserved controls are named, never silent).
        "logit_bias",
        "presence_penalty",
        "frequency_penalty",
        "context_length",
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


def map_params(params) -> tuple[dict, list[str]]:
    """Canonical SamplingParams -> (Aesir wire dict, warnings).

    The single mapping path ``chat_stream`` itself uses: served
    canonical controls pass under their wire names; unserved ones
    are omitted and named in a structured warning each — never
    sent, never pretended honored (INV-005). Driven by the
    declared sets (``WIRE_NAMES`` / ``UNSUPPORTED_SAMPLERS``),
    which together account for every canonical control.
    """
    bag = params.to_bag()
    wire: dict = {}
    warnings: list[str] = []
    for key in sorted(bag):
        if key in WIRE_NAMES:
            wire[WIRE_NAMES[key]] = bag[key]
        else:
            warnings.append(f"unsupported parameter dropped: {key}")
    return wire, warnings


def map_error(code: int, message: str = ""):
    lowered = (message or "").lower()
    if code in (401, 403):
        return AuthenticationFailed("aesir authentication failed")
    if code == 404 or "not found" in lowered:
        return ModelNotFound("aesir model not found")
    if code == 429:
        return RateLimited("aesir rate limited")
    if code == 422:
        # Aesir's context/generation admission refusal (P-009 D8).
        return ContextOverflow("aesir context overflow")
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

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        if structured is not None and structured.is_active():
            raise InvalidRequest(
                f"aesir does not serve structured mode {structured.mode!r}: "
                "the P-009 route matrix never recorded response_format"
            )
        if cancel.is_set():
            raise GenerationCancelled("generation cancelled")
        wire_params, _warnings = map_params(params)
        payload = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
        }
        payload.update(wire_params)
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
            raise BackendTimeout("aesir request timed out") from exc
        except httpx.ConnectError as exc:
            raise BackendUnavailable("aesir unreachable") from exc
        if not saw_terminal_marker and reason is None:
            # P-009 D6: a post-header failure can end Aesir's stream
            # with no terminal marker; that is an incomplete stream,
            # never a fabricated successful Done.
            raise ProviderError("aesir stream ended without a terminal marker")
        if usage is not None:
            yield usage
        yield Done(reason or "stop", usage)

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

    async def readiness_check(self) -> HealthStatus:
        """Resident-model readiness from Aesir's ``/health/ready``.

        The narrowed VX-19 home (P-014 gate, inside F-02): the
        catalog a ``/models`` listing shows is not readiness —
        only the resident model can generate (P-009 D5). Aesir's
        native serve exposes schema-v1 readiness at the server
        ROOT (not under ``/v1``), carrying the resident model's
        identity. This reports that truth and never estimates
        VRAM or any other quantity Aesir does not serve. In
        ``--ollama`` mode the native readiness route is not
        served, and this reports not-ready, honestly.
        """
        start = time.monotonic()
        base = str(self._client.base_url).rstrip("/")
        root = base[: -len("/v1")] if base.endswith("/v1") else base
        try:
            resp = await self._client.get(f"{root}/health/ready")
        except Exception as exc:  # readiness reports, never raises
            return HealthStatus(
                ok=False, detail=f"aesir readiness unreachable: {type(exc).__name__}"
            )
        latency = (time.monotonic() - start) * 1000
        if resp.status_code >= 400:
            return HealthStatus(
                ok=False,
                detail=f"aesir not ready (HTTP {resp.status_code})",
                latency_ms=latency,
            )
        detail = "aesir resident model ready"
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if isinstance(body, dict):
            resident = None
            for key in ("model", "model_id", "resident_model", "id"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    resident = value
                    break
            if resident is None and isinstance(body.get("resident"), dict):
                value = body["resident"].get("model") or body["resident"].get("id")
                if isinstance(value, str) and value:
                    resident = value
            if resident:
                detail = f"aesir resident model ready: {resident}"
        return HealthStatus(ok=True, detail=detail, latency_ms=latency)
