"""Backend service layer (S305): aggregated models, health, token counting.

Aggregates ``list_models``/``health_check`` across configured chat backends
and surfaces token-count *quality* (exact / provider / estimated, from
runmal.tokens.TokenQuality) alongside every count, so the UI/service layer
can always distinguish an estimate from an exact or provider-reported count.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.backends.base import ChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.models import HealthStatus, ModelInfo
from runmal.tokens import TokenCount, TokenQuality, count_from_provider_usage


@dataclass(frozen=True)
class TokenCountReport:
    backend_key: str
    model_id: str
    count: TokenCount

    @property
    def quality(self) -> TokenQuality:
        return self.count.quality

    @property
    def is_estimate(self) -> bool:
        return self.count.quality is TokenQuality.ESTIMATED

    def to_dict(self) -> dict:
        return {
            "backend_key": self.backend_key,
            "model_id": self.model_id,
            "tokens": self.count.value,
            "quality": self.count.quality.value,
            "is_estimate": self.is_estimate,
        }


class BackendRegistry:
    """Named collection of chat backends with aggregated views."""

    def __init__(self):
        self._backends: dict[str, ChatBackend] = {}

    def register(self, backend: ChatBackend, name: str | None = None) -> str:
        key = name or backend.backend_key
        self._backends[key] = backend
        return key

    def get(self, key: str) -> ChatBackend:
        return self._backends[key]

    def keys(self) -> list[str]:
        return sorted(self._backends)

    async def list_all_models(self) -> list[ModelInfo]:
        out: list[ModelInfo] = []
        for key in self.keys():
            out.extend(await self._backends[key].list_models())
        return out

    async def list_models_for(self, key: str) -> list[ModelInfo]:
        return await self.get(key).list_models()

    async def health_all(self) -> dict[str, HealthStatus]:
        return {key: await self._backends[key].health_check()
                for key in self.keys()}

    async def health_for(self, key: str) -> HealthStatus:
        return await self.get(key).health_check()

    async def health_dicts(self) -> dict[str, dict]:
        return {key: status.to_dict()
                for key, status in (await self.health_all()).items()}

    def token_count(self, key: str, messages: list[ChatMessage],
                    model_id: str) -> TokenCountReport:
        backend = self.get(key)
        return TokenCountReport(
            backend_key=backend.backend_key, model_id=model_id,
            count=backend.count_tokens(messages, model_id))

    def token_count_from_usage(self, key: str,
                               usage: dict | None) -> TokenCountReport | None:
        """Provider-reported count from a usage payload, quality=PROVIDER."""
        count = count_from_provider_usage(usage)
        if count is None:
            return None
        return TokenCountReport(
            backend_key=self.get(key).backend_key, model_id="", count=count)
