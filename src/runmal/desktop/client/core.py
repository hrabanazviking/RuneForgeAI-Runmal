"""``RunmalClient`` — typed engine clients for the desktop shell (R-04).

One synchronous httpx client per route group the skeleton needs now:
health/engine status, backend profiles (R-02), chats, characters.
Synchronous by design: callers run these off the GUI thread through
``runmal.desktop.workers`` (Qt) — this module itself stays Qt-free
and unit-testable against ``httpx.MockTransport`` or a live local
engine.

``trust_env=False`` is deliberate: the engine is loopback-only, and a
host proxy environment (including unparseable ``no_proxy`` forms some
hosts export) must never route — or break — loopback traffic.
"""

from __future__ import annotations

from typing import Any

import httpx

from runmal.desktop.client.errors import (
    ApiError,
    AuthError,
    NotFoundError,
    TransportError,
)
from runmal.desktop.client.models import (
    BackendProfile,
    CharacterSummary,
    ChatSummary,
    EngineSnapshot,
    FirstRunState,
    HealthStatus,
    detect_first_run,
)
from runmal.desktop.client.session import DesktopSession

DEFAULT_TIMEOUT = 10.0


def _detail_of(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
    return ""


class RunmalClient:
    """Typed client over one engine base URL + one session."""

    def __init__(
        self,
        session: DesktopSession,
        *,
        http: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self.base_url = session.base_url
        self._owns_http = http is None
        self._http = http or httpx.Client(
            base_url=self.base_url, timeout=timeout, trust_env=False
        )
        session.apply(self._http)

    def __repr__(self) -> str:
        return f"RunmalClient({self._session!r})"

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> RunmalClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------ plumbing

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise TransportError(
                f"engine unreachable: {exc.__class__.__name__}"
            ) from exc
        if response.status_code in (401, 403):
            raise AuthError(response.status_code, _detail_of(response))
        if response.status_code == 404:
            raise NotFoundError(404, _detail_of(response) or "not found")
        if response.status_code >= 400:
            raise ApiError(response.status_code, _detail_of(response))
        if not response.content:
            return None
        return response.json()

    # ------------------------------------------------------- health/status

    def health(self) -> HealthStatus:
        """Real ``/healthz`` state (public route; no auth needed)."""
        return HealthStatus.from_dict(self._request("GET", "/healthz"))

    def api_status(self) -> dict[str, Any]:
        """Authenticated ``/api/v1/status`` — proves the session works,
        not just that the port answers."""
        payload = self._request("GET", "/api/v1/status")
        return payload if isinstance(payload, dict) else {}

    # --------------------------------------------------- backend profiles

    def list_backend_profiles(self) -> list[BackendProfile]:
        payload = self._request("GET", "/api/v1/backend-profiles")
        rows = payload if isinstance(payload, list) else []
        return [BackendProfile.from_dict(r) for r in rows if isinstance(r, dict)]

    def get_backend_profile(self, profile_id: str) -> BackendProfile:
        payload = self._request("GET", f"/api/v1/backend-profiles/{profile_id}")
        return BackendProfile.from_dict(payload if isinstance(payload, dict) else {})

    def profile_health(self, profile_id: str) -> dict[str, Any]:
        """The R-02 health probe for one profile (failures are data)."""
        payload = self._request(
            "GET", f"/api/v1/backend-profiles/{profile_id}/health"
        )
        return payload if isinstance(payload, dict) else {}

    def profile_models(self, profile_id: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET", f"/api/v1/backend-profiles/{profile_id}/models"
        )
        if isinstance(payload, dict):
            models = payload.get("models")
            if isinstance(models, list):
                return [m for m in models if isinstance(m, dict)]
        return []

    # ---------------------------------------------------------------- chats

    def list_chats(self) -> list[ChatSummary]:
        payload = self._request("GET", "/api/v1/chats")
        rows = payload if isinstance(payload, list) else []
        return [ChatSummary.from_dict(r) for r in rows if isinstance(r, dict)]

    # ------------------------------------------------------------ characters

    def list_characters(self) -> list[CharacterSummary]:
        payload = self._request("GET", "/api/v1/characters")
        rows = payload if isinstance(payload, list) else []
        return [
            CharacterSummary.from_dict(r) for r in rows if isinstance(r, dict)
        ]

    # ------------------------------------------------------------ first run

    def first_run_state(self) -> FirstRunState:
        """First-run detection via the client layer (plan §2.3): first
        run iff no backend profile and no character exist."""
        return detect_first_run(
            self.list_backend_profiles(), self.list_characters()
        )


def fetch_snapshot(client: RunmalClient) -> EngineSnapshot:
    """Fetch everything the shell skeleton displays, as one unit.

    Health is read first and for real; the authenticated lists follow.
    Any failure propagates as a typed client error — the caller (a Qt
    worker) turns it into status-bar words, never a frozen window.
    """
    health = client.health()
    profiles = client.list_backend_profiles()
    chats = client.list_chats()
    characters = client.list_characters()
    return EngineSnapshot(
        health=health,
        profiles=profiles,
        chats=chats,
        characters=characters,
        first_run=detect_first_run(profiles, characters),
    )
