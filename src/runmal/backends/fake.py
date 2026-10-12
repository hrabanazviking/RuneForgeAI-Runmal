"""FakeChatBackend (S301): emits NORMALIZED events directly.

Deterministic, scriptable, with optional failure injection for contract
tests. Unlike generation/fake_backend.py (S108, untouched), nothing here is
provider-shaped. The api_key argument exists only so the secret-leak
contract check can prove it never appears in any output.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from runmal.backends.base import ChatBackend
from runmal.backends.errors import BackendError, GenerationCancelled
from runmal.backends.events import Done, Event, TextDelta, UsageUpdate
from runmal.backends.messages import ChatMessage
from runmal.backends.models import Capabilities, HealthStatus, ModelInfo
from runmal.backends.params import SamplingParams
from runmal.tokens import TokenQuality

FAKE_MODEL_ID = "fake-1"
SUPPORTED = frozenset({"temperature", "top_p", "max_tokens", "stop", "seed"})


class FakeChatBackend(ChatBackend):
    backend_key = "fake"

    def __init__(
        self,
        chunks: tuple[str, ...] = ("Rúnmál ", "hears ", "you."),
        usage: UsageUpdate | None = None,
        fail_with: BackendError | None = None,
        fail_after: int | None = None,
        api_key: str | None = None,
        model_id: str = FAKE_MODEL_ID,
    ):
        self._chunks = tuple(chunks)
        self._usage = usage
        self._fail_with = fail_with
        self._fail_after = fail_after
        self._api_key = api_key  # never serialized anywhere (INV-023)
        self._model_id = model_id
        self.default_model = ModelInfo(
            model_id=model_id,
            display_name="Fake Model",
            backend_key=self.backend_key,
            capabilities=Capabilities(
                chat=True,
                streaming=True,
                context_length=8192,
                max_output_tokens=1024,
                token_count_quality=TokenQuality.ESTIMATED,
                supported_samplers=SUPPORTED,
            ),
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        params: SamplingParams,
        cancel: asyncio.Event,
    ) -> AsyncIterator[Event]:
        _ = (messages, params)
        if self._fail_with is not None and self._fail_after is None:
            raise self._fail_with
        emitted = 0
        for chunk in self._chunks:
            if cancel.is_set():
                raise GenerationCancelled("generation cancelled")
            if self._fail_with is not None and emitted >= (self._fail_after or 0):
                raise self._fail_with
            yield TextDelta(chunk)
            emitted += 1
            await asyncio.sleep(0)
        if self._fail_with is not None and emitted >= (self._fail_after or 0):
            raise self._fail_with
        if cancel.is_set():
            raise GenerationCancelled("generation cancelled")
        if self._usage is not None:
            yield self._usage
        yield Done("stop", self._usage)

    async def list_models(self) -> list[ModelInfo]:
        return [self.default_model]

    async def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="fake backend healthy", latency_ms=0.0)
