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

import json
from typing import Any

import httpx

from runmal.desktop.client.errors import (
    ApiError,
    AuthError,
    ClientError,
    NotFoundError,
    TransportError,
)
from runmal.desktop.client.models import (
    BackendProfile,
    CharacterSummary,
    ChatSummary,
    EngineSnapshot,
    FirstRunState,
    GeneratedReply,
    HealthStatus,
    ImportOutcome,
    MessageView,
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

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise AuthError(response.status_code, _detail_of(response))
        if response.status_code == 404:
            raise NotFoundError(404, _detail_of(response) or "not found")
        if response.status_code >= 400:
            raise ApiError(response.status_code, _detail_of(response))

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise TransportError(
                f"engine unreachable: {exc.__class__.__name__}"
            ) from exc
        self._raise_for_status(response)
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

    def create_backend_profile(
        self,
        name: str,
        chat_backend: str,
        *,
        chat_model: str = "",
        config: dict[str, Any] | None = None,
    ) -> BackendProfile:
        """Create one R-02 profile. Secrets are NEVER sent inline
        here — set them afterwards via :meth:`set_chat_secret`, the
        dedicated write-only route (INV-023)."""
        body: dict[str, Any] = {
            "name": name,
            "chat_backend": chat_backend,
            "chat_model": chat_model,
        }
        if config:
            body["config"] = config
        payload = self._request("POST", "/api/v1/backend-profiles", json=body)
        return BackendProfile.from_dict(payload if isinstance(payload, dict) else {})

    def update_backend_profile(
        self, profile_id: str, **fields: Any
    ) -> BackendProfile:
        """Partial update (R-02 PATCH). Only the named fields are
        sent; secret fields are refused by construction — they are
        not part of the PATCH shape and never pass through here."""
        body = {k: v for k, v in fields.items() if v is not None}
        payload = self._request(
            "PATCH", f"/api/v1/backend-profiles/{profile_id}", json=body
        )
        return BackendProfile.from_dict(payload if isinstance(payload, dict) else {})

    def delete_backend_profile(self, profile_id: str) -> bool:
        payload = self._request(
            "DELETE", f"/api/v1/backend-profiles/{profile_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("ok"))

    def set_chat_secret(self, profile_id: str, value: str) -> BackendProfile:
        """Store an API key via the R-02 write-only secret route.

        The value travels once, in this request body, to the engine's
        secret store; the response is the profile shape (references +
        booleans only). The value is never logged, never put in an
        error, and never retained by this client (INV-023)."""
        payload = self._request(
            "PUT",
            f"/api/v1/backend-profiles/{profile_id}/chat-secret",
            json={"value": value},
        )
        return BackendProfile.from_dict(payload if isinstance(payload, dict) else {})

    # ---------------------------------------------------------------- chats

    def list_chats(self) -> list[ChatSummary]:
        payload = self._request("GET", "/api/v1/chats")
        rows = payload if isinstance(payload, list) else []
        return [ChatSummary.from_dict(r) for r in rows if isinstance(r, dict)]

    def create_chat(
        self, *, title: str = "", character_id: str | None = None
    ) -> ChatSummary:
        """Create a chat; with a character, the engine seeds the
        character's greeting as the first message (chats service,
        greeting mode "first")."""
        body: dict[str, Any] = {"title": title}
        if character_id:
            body["character_id"] = character_id
        payload = self._request("POST", "/api/v1/chats", json=body)
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    def set_chat_backend_profile(
        self, chat_id: str, profile_id: str | None
    ) -> ChatSummary:
        """Pin (or clear, with None) a chat's backend profile."""
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/backend-profile",
            json={"profile_id": profile_id},
        )
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    def list_chat_messages(self, chat_id: str) -> list[MessageView]:
        payload = self._request("GET", f"/api/v1/chats/{chat_id}/messages")
        rows = payload if isinstance(payload, list) else []
        return [MessageView.from_dict(r) for r in rows if isinstance(r, dict)]

    # ------------------------------------------------------------ characters

    def list_characters(self) -> list[CharacterSummary]:
        payload = self._request("GET", "/api/v1/characters")
        rows = payload if isinstance(payload, list) else []
        return [
            CharacterSummary.from_dict(r) for r in rows if isinstance(r, dict)
        ]

    def create_character(
        self, card: dict[str, Any], *, name: str | None = None
    ) -> CharacterSummary:
        """Create a character from a card dict (``POST /characters``)."""
        body: dict[str, Any] = {"card": card}
        if name:
            body["name"] = name
        payload = self._request("POST", "/api/v1/characters", json=body)
        return CharacterSummary.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def import_character_file(self, filename: str, data: bytes) -> ImportOutcome:
        """Import one card file (JSON/PNG) via the bulk library road
        (``POST /api/v1/library/imports``) and collapse its report to
        the wizard's verdict. Refusals are data, not errors."""
        payload = self._request(
            "POST",
            "/api/v1/library/imports",
            files=[("files", (filename, data))],
            data={"dry_run": "false"},
        )
        return ImportOutcome.from_report(
            payload if isinstance(payload, dict) else {}
        )

    # ------------------------------------------------------------- user name

    def get_user_name(self) -> dict[str, Any]:
        """The persisted ``{{user}}`` name (R-03): ``user_name`` is the
        effective name (default "User"); ``is_set`` says whether one
        was ever stored."""
        payload = self._request("GET", "/api/v1/user-name")
        return payload if isinstance(payload, dict) else {}

    def set_user_name(self, name: str) -> dict[str, Any]:
        """Persist the ``{{user}}`` name (R-03 PUT road). An empty
        name clears the setting back to the default."""
        payload = self._request(
            "PUT", "/api/v1/user-name", json={"user_name": name}
        )
        return payload if isinstance(payload, dict) else {}

    # ------------------------------------------------------------- generation

    def generate_composed(
        self,
        chat_id: str,
        *,
        profile_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> GeneratedReply:
        """One composed turn (R-03): the engine composes the prompt
        from the chat server-side and streams SSE; this collects the
        token events into the reply text. An ``error`` event in the
        stream raises :class:`ClientError` with its plain message —
        provider payloads never cross (INV-001/023)."""
        body: dict[str, Any] = {"chat_id": chat_id}
        if profile_id:
            body["profile_id"] = profile_id
        if params:
            body["params"] = params
        try:
            with self._http.stream(
                "POST", "/api/v1/generate", json=body
            ) as response:
                self._raise_for_status(response)
                backend_key = response.headers.get("X-Backend-Key", "")
                mode = response.headers.get("X-Generation-Mode", "")
                chunks: list[str] = []
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[len("data:"):].strip())
                    except ValueError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") == "token":
                        text = event.get("text")
                        if isinstance(text, str):
                            chunks.append(text)
                    elif event.get("type") == "error":
                        message = event.get("message")
                        raise ClientError(
                            str(message) if message
                            else "generation failed in the engine"
                        )
        except httpx.HTTPError as exc:
            raise TransportError(
                f"engine unreachable: {exc.__class__.__name__}"
            ) from exc
        return GeneratedReply(
            text="".join(chunks), backend_key=backend_key, mode=mode
        )

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
