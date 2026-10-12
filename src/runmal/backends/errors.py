"""Backend error taxonomy (S301, BACKEND_CONTRACT section 6).

Errors NEVER carry secret values: no API keys, headers, or raw provider
payloads. ``provider_detail_ref`` is a safe opaque reference only.
"""

from __future__ import annotations


class BackendError(Exception):
    code = "backend_error"
    retryable = False

    def __init__(self, message: str = "", provider_detail_ref: str | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.provider_detail_ref = provider_detail_ref

    def to_event_dict(self) -> dict:
        from runmal.backends.events import ErrorEvent

        return ErrorEvent(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
            provider_detail_ref=self.provider_detail_ref,
        ).to_dict()


class BackendUnavailable(BackendError):  # noqa: N818
    code = "backend_unavailable"
    retryable = True


class AuthenticationFailed(BackendError):  # noqa: N818
    code = "authentication_failed"
    retryable = False


class RateLimited(BackendError):  # noqa: N818
    code = "rate_limited"
    retryable = True

    def __init__(self, message: str = "", retry_after_s: float | None = None,
                 provider_detail_ref: str | None = None):
        super().__init__(message, provider_detail_ref)
        self.retry_after_s = retry_after_s


class ContextOverflow(BackendError):  # noqa: N818
    code = "context_overflow"
    retryable = False


class ModelNotFound(BackendError):  # noqa: N818
    code = "model_not_found"
    retryable = False


class InvalidRequest(BackendError):  # noqa: N818
    code = "invalid_request"
    retryable = False


class BackendTimeout(BackendError):  # noqa: N818
    code = "timeout"
    retryable = True


class GenerationCancelled(BackendError):  # noqa: N818
    code = "generation_cancelled"
    retryable = False


class ProviderError(BackendError):  # noqa: N818
    code = "provider_error"
    retryable = False
