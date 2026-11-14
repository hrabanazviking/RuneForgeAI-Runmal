"""Client-layer error taxonomy (R-04).

Engine HTTP failures are mapped to typed errors so widgets can react
without parsing status codes or response bodies themselves. Error
messages carry the engine's ``detail`` string and the status code —
never headers, never credentials (INV-023).
"""

from __future__ import annotations


class ClientError(Exception):
    """Base class for every client-layer failure."""


class TransportError(ClientError):
    """The engine could not be reached at all (connection/timeout)."""


class ApiError(ClientError):
    """The engine answered with a non-success status."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        message = f"engine answered {status_code}"
        if detail:
            message += f": {detail}"
        super().__init__(message)


class AuthError(ApiError):
    """401/403 — the local credential or session was refused."""


class NotFoundError(ApiError):
    """404 — the named resource does not exist (or is not the owner's)."""
