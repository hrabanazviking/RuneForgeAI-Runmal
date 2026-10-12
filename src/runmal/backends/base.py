"""ChatBackend abstract interface (S301).

Cancellation contract: failures inside ``chat_stream`` RAISE BackendError
subclasses (cancellation raises GenerationCancelled); ErrorEvent is only the
serializable form produced from them by the service/API layer.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import replace

from runmal.backends.events import Event
from runmal.backends.messages import ChatMessage
from runmal.backends.models import HealthStatus, ModelInfo
from runmal.backends.params import SamplingParams
from runmal.tokens import TokenCount, count_tokens


class ChatBackend(ABC):
    backend_key: str = "abstract"
    #: Subclasses set this so filter_params can apply capability truth.
    default_model: ModelInfo | None = None

    @abstractmethod
    def chat_stream(
        self,
        messages: list[ChatMessage],
        params: SamplingParams,
        cancel: asyncio.Event,
    ) -> AsyncIterator[Event]:
        """Yield normalized events; raise BackendError subclasses on failure."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return normalized model metadata."""

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Return normalized health status."""

    def count_tokens(self, messages: list[ChatMessage], model_id: str) -> TokenCount:
        """Default: shared runmal.tokens counter over concatenated content."""
        _ = model_id
        text = "\n".join(m.content for m in messages)
        return count_tokens(text)

    def filter_params(self, params: SamplingParams) -> tuple[SamplingParams, list[str]]:
        """Clear fields the default model does not declare (INV-005).

        Returns (filtered params, warnings). Driven by the model's declared
        ``supported_samplers`` (canonical bag key names); never pretends an
        unsupported parameter was honored.
        """
        model = self.default_model
        if model is None:
            return params, []
        supported = model.capabilities.supported_samplers
        bag = params.to_bag()
        clears: dict = {}
        warnings: list[str] = []
        field_for_key = {"max_tokens": "max_output_tokens"}
        for key in sorted(bag):
            if key not in supported:
                clears[field_for_key.get(key, key)] = None
                warnings.append(f"unsupported parameter dropped: {key}")
        if clears:
            params = replace(params, **clears)
        return params, warnings
