"""Normalized backend events (S301, BACKEND_CONTRACT section 3).

Failures inside ``chat_stream`` RAISE BackendError subclasses; ErrorEvent is
the serializable form the API/service layer produces from them. Cancellation
raises GenerationCancelled. See docs/adr/0004-normalized-backend-events.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextDelta:
    text: str

    def to_dict(self) -> dict:
        return {"type": "text_delta", "text": self.text}


@dataclass(frozen=True)
class UsageUpdate:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict:
        return {
            "type": "usage",
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class Done:
    reason: str
    usage: UsageUpdate | None = None

    def to_dict(self) -> dict:
        return {
            "type": "done",
            "reason": self.reason,
            "usage": self.usage.to_dict() if self.usage else None,
        }


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    message: str
    retryable: bool
    provider_detail_ref: str | None = None

    def to_dict(self) -> dict:
        return {
            "type": "error",
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "provider_detail_ref": self.provider_detail_ref,
        }


Event = TextDelta | UsageUpdate | Done | ErrorEvent
