"""Model / capability / health metadata (S301, BACKEND_CONTRACT section 5)."""

from __future__ import annotations

from dataclasses import dataclass, field

from runmal.tokens import TokenQuality


@dataclass(frozen=True)
class Capabilities:
    chat: bool = False
    embeddings: bool = False
    vision: bool = False
    tools: bool = False
    streaming: bool = False
    structured_output: bool = False
    context_length: int | None = None
    max_output_tokens: int | None = None
    token_count_quality: TokenQuality = TokenQuality.ESTIMATED
    supported_samplers: frozenset[str] = frozenset()

    def to_dict(self) -> dict:
        return {
            "chat": self.chat,
            "embeddings": self.embeddings,
            "vision": self.vision,
            "tools": self.tools,
            "streaming": self.streaming,
            "structured_output": self.structured_output,
            "context_length": self.context_length,
            "max_output_tokens": self.max_output_tokens,
            "token_count_quality": self.token_count_quality.value,
            "supported_samplers": sorted(self.supported_samplers),
        }


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    display_name: str
    backend_key: str
    capabilities: Capabilities = field(default_factory=Capabilities)

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "display_name": self.display_name,
            "backend_key": self.backend_key,
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass
class HealthStatus:
    ok: bool
    detail: str
    latency_ms: float | None = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "detail": self.detail, "latency_ms": self.latency_ms}
