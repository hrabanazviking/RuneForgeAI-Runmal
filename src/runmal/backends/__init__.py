"""Backend seams (Campaign III): normalized chat/embedding interfaces."""

from runmal.backends.base import ChatBackend
from runmal.backends.errors import (
    AuthenticationFailed,
    BackendError,
    BackendTimeout,
    BackendUnavailable,
    ContextOverflow,
    GenerationCancelled,
    InvalidRequest,
    ModelNotFound,
    ProviderError,
    RateLimited,
)
from runmal.backends.events import Done, ErrorEvent, Event, TextDelta, UsageUpdate
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.models import Capabilities, HealthStatus, ModelInfo
from runmal.backends.params import SamplingParams
from runmal.backends.retry import AttemptRecord, RetryPolicy, stream_with_retry

__all__ = [
    "AttemptRecord",
    "AuthenticationFailed",
    "BackendError",
    "BackendTimeout",
    "BackendUnavailable",
    "Capabilities",
    "ChatBackend",
    "ChatMessage",
    "ContextOverflow",
    "Done",
    "ErrorEvent",
    "Event",
    "FakeChatBackend",
    "GenerationCancelled",
    "HealthStatus",
    "InvalidRequest",
    "ModelInfo",
    "ModelNotFound",
    "ProviderError",
    "RateLimited",
    "RetryPolicy",
    "SamplingParams",
    "TextDelta",
    "UsageUpdate",
    "stream_with_retry",
]
