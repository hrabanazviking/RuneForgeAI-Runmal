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
import uuid
from collections.abc import Iterator
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
    AssetView,
    AuthorsNoteView,
    BackendProfile,
    BindingView,
    CharacterCardView,
    CharacterSummary,
    ChatSummary,
    CheckpointView,
    EngineSnapshot,
    FirstRunState,
    GeneratedReply,
    HealthStatus,
    ImportOutcome,
    LibraryCardView,
    LorebookSummary,
    MessageView,
    OrganisationView,
    PersonaView,
    PresetSummary,
    SearchHitView,
    StreamEvent,
    TagCountView,
    UndoEntryView,
    VersionHistoryView,
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

    def _request_bytes(
        self, method: str, path: str, **kwargs: Any
    ) -> tuple[bytes, str]:
        """One binary road (R-08: avatar / asset bytes). Returns
        ``(content, media_type)``; HTTP failures raise the same
        typed errors as :meth:`_request`."""
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise TransportError(
                f"engine unreachable: {exc.__class__.__name__}"
            ) from exc
        self._raise_for_status(response)
        return response.content, response.headers.get("content-type", "")

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

    def get_chat(self, chat_id: str) -> ChatSummary:
        """One chat's summary (``GET /chats/{id}``; the payload also
        embeds its messages — the shell reads those through
        :meth:`list_chat_messages`, so only the summary is parsed)."""
        payload = self._request("GET", f"/api/v1/chats/{chat_id}")
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    def rename_chat(self, chat_id: str, title: str) -> ChatSummary:
        """Rename a chat (``PATCH /chats/{id}``, R-06 chats dock)."""
        payload = self._request(
            "PATCH", f"/api/v1/chats/{chat_id}", json={"title": title}
        )
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    def delete_chat(self, chat_id: str) -> bool:
        """Delete a chat (``DELETE /chats/{id}``). Irreversible —
        callers confirm with the user first."""
        payload = self._request("DELETE", f"/api/v1/chats/{chat_id}")
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def export_chat(self, chat_id: str) -> dict[str, Any]:
        """The portable export document for a chat (``GET
        /chats/{id}/export``, S111): chat metadata + full history,
        no secrets (INV-023/025)."""
        payload = self._request("GET", f"/api/v1/chats/{chat_id}/export")
        return payload if isinstance(payload, dict) else {}

    def append_message(
        self, chat_id: str, role: str, content: str
    ) -> MessageView:
        """Persist one message in a chat (``POST /chats/{id}/messages``).

        This is the landing road for a composed turn (R-06): the
        caller appends the user's line BEFORE generating (so the
        server-side composition includes it) and the assistant's
        reply AFTER a cleanly finished stream — exactly the
        bridge's landing discipline (a cancelled or errored stream
        stores nothing)."""
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"role": role, "content": content},
        )
        return MessageView.from_dict(payload if isinstance(payload, dict) else {})

    def set_chat_preset(
        self, chat_id: str, preset_id: str | None
    ) -> ChatSummary:
        """Apply (or clear, with None) a chat's sampling preset."""
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/preset",
            json={"preset_id": preset_id},
        )
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    def get_chat_persona(self, chat_id: str) -> PersonaView:
        """The chat's active persona (R-03 local persona road)."""
        payload = self._request("GET", f"/api/v1/chats/{chat_id}/persona")
        return PersonaView.from_dict(payload if isinstance(payload, dict) else {})

    # ------------------------------------------- message actions (R-07)

    def edit_message(
        self, chat_id: str, message_id: str, content: str
    ) -> MessageView:
        """Edit one message's content (``PATCH
        /chats/{id}/messages/{mid}``, P-068)."""
        payload = self._request(
            "PATCH",
            f"/api/v1/chats/{chat_id}/messages/{message_id}",
            json={"content": content},
        )
        return MessageView.from_dict(payload if isinstance(payload, dict) else {})

    def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Delete one message (``DELETE
        /chats/{id}/messages/{mid}``, P-068). Journaled by the
        engine (P-076), so the Undo surface can restore it."""
        payload = self._request(
            "DELETE", f"/api/v1/chats/{chat_id}/messages/{message_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def add_swipe(
        self, chat_id: str, message_id: str, content: str
    ) -> MessageView:
        """Append an alternate to a message's swipe deck (``POST
        .../swipes``, P-065). Returns the message with its deck."""
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/messages/{message_id}/swipes",
            json={"content": content},
        )
        return MessageView.from_dict(payload if isinstance(payload, dict) else {})

    def select_swipe(
        self,
        chat_id: str,
        message_id: str,
        *,
        action: str | None = None,
        index: int | None = None,
    ) -> MessageView:
        """Select the active alternate in a swipe deck (``POST
        .../swipes/select``, P-065): a relative ``action``
        (next/prev/first/last) or an explicit ``index``."""
        body: dict[str, Any] = {}
        if action is not None:
            body["action"] = action
        if index is not None:
            body["index"] = index
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/messages/{message_id}/swipes/select",
            json=body,
        )
        return MessageView.from_dict(payload if isinstance(payload, dict) else {})

    def delete_swipe(
        self, chat_id: str, message_id: str, index: int
    ) -> MessageView:
        """Delete one alternate from a swipe deck (``DELETE
        .../swipes/{index}``, P-065)."""
        payload = self._request(
            "DELETE",
            f"/api/v1/chats/{chat_id}/messages/{message_id}/swipes/{index}",
        )
        return MessageView.from_dict(payload if isinstance(payload, dict) else {})

    def pin_message(self, chat_id: str, message_id: str) -> dict[str, Any]:
        """Pin a message to memory (``POST .../pin``, P-068): a
        real pinned Memory record; the memory document is returned
        raw (its shape is the memory domain's, R-12's concern)."""
        payload = self._request(
            "POST", f"/api/v1/chats/{chat_id}/messages/{message_id}/pin"
        )
        return payload if isinstance(payload, dict) else {}

    def unpin_message(self, chat_id: str, message_id: str) -> bool:
        """Unpin a message (``DELETE .../pin``, P-068)."""
        payload = self._request(
            "DELETE", f"/api/v1/chats/{chat_id}/messages/{message_id}/pin"
        )
        return bool(isinstance(payload, dict) and payload.get("unpinned"))

    def list_pinned_messages(self, chat_id: str) -> list[MessageView]:
        """A chat's pinned messages, in display order (``GET
        /chats/{id}/pinned-messages``, P-068)."""
        payload = self._request(
            "GET", f"/api/v1/chats/{chat_id}/pinned-messages"
        )
        rows = payload if isinstance(payload, list) else []
        return [MessageView.from_dict(r) for r in rows if isinstance(r, dict)]

    # --------------------------------------------- branches (R-07)

    def branch_chat(
        self,
        chat_id: str,
        *,
        message_id: str | None = None,
        name: str | None = None,
    ) -> ChatSummary:
        """Fork a chat at a message (``POST /chats/{id}/branches``,
        P-066). Never destructive: the source is copied, never
        mutated. No message_id forks the whole chat."""
        body: dict[str, Any] = {}
        if message_id:
            body["message_id"] = message_id
        if name:
            body["name"] = name
        payload = self._request(
            "POST", f"/api/v1/chats/{chat_id}/branches", json=body
        )
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    def list_branches(self, chat_id: str) -> dict[str, Any]:
        """A chat's branch family (``GET /chats/{id}/branches``,
        P-066), returned raw — the family document's shape is the
        branches domain's; the logic layer projects what it shows."""
        payload = self._request("GET", f"/api/v1/chats/{chat_id}/branches")
        return payload if isinstance(payload, dict) else {}

    # ------------------------------------------ author's note (R-07)

    def get_authors_note(self, chat_id: str) -> AuthorsNoteView:
        """A chat's author's note (``GET
        /chats/{id}/authors-note``, P-056)."""
        payload = self._request(
            "GET", f"/api/v1/chats/{chat_id}/authors-note"
        )
        return AuthorsNoteView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def set_authors_note(
        self,
        chat_id: str,
        *,
        text: str,
        depth: int = 4,
        frequency: int = 1,
        enabled: bool = True,
        role: str = "system",
    ) -> ChatSummary:
        """Set a chat's author's note (``POST
        /chats/{id}/authors-note``, P-056). The route answers with
        the chat row, like the other chat-setting roads."""
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/authors-note",
            json={
                "text": text,
                "depth": depth,
                "frequency": frequency,
                "enabled": enabled,
                "role": role,
            },
        )
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    # -------------------------------------- continue / impersonate

    def continue_chat(
        self, chat_id: str, *, mode: str = "auto", instruction: str | None = None
    ) -> dict[str, Any]:
        """Continue a chat (``POST /chats/{id}/continue``, P-069):
        the engine generates AND lands the result (extend grows
        the last assistant message; next appends a new one). The
        landing document is returned raw; the logic layer
        projects it."""
        body: dict[str, Any] = {"mode": mode}
        if instruction:
            body["instruction"] = instruction
        payload = self._request(
            "POST", f"/api/v1/chats/{chat_id}/continue", json=body
        )
        return payload if isinstance(payload, dict) else {}

    def impersonate_draft(
        self, chat_id: str, *, instruction: str | None = None
    ) -> dict[str, Any]:
        """Draft the next user turn (``POST
        /chats/{id}/impersonate``, P-069). A DRAFT document only —
        nothing is stored as a message until
        :meth:`accept_impersonate` lands a final text."""
        body: dict[str, Any] = {}
        if instruction:
            body["instruction"] = instruction
        payload = self._request(
            "POST", f"/api/v1/chats/{chat_id}/impersonate", json=body
        )
        return payload if isinstance(payload, dict) else {}

    def accept_impersonate(
        self, chat_id: str, content: str, *, draft_id: str | None = None
    ) -> MessageView:
        """Accept an impersonate draft (``POST
        /chats/{id}/impersonate/accept``, P-069): the final text
        (the draft verbatim or the user's edit of it) is appended
        as a real user message."""
        body: dict[str, Any] = {"content": content}
        if draft_id:
            body["draft_id"] = draft_id
        payload = self._request(
            "POST", f"/api/v1/chats/{chat_id}/impersonate/accept", json=body
        )
        return MessageView.from_dict(payload if isinstance(payload, dict) else {})

    def discard_impersonate(
        self, chat_id: str, *, draft_id: str | None = None
    ) -> bool:
        """Discard an impersonate draft (``POST
        /chats/{id}/impersonate/discard``, P-069): records the
        discard, stores nothing."""
        body: dict[str, Any] = {}
        if draft_id:
            body["draft_id"] = draft_id
        payload = self._request(
            "POST", f"/api/v1/chats/{chat_id}/impersonate/discard", json=body
        )
        return bool(isinstance(payload, dict) and payload.get("discarded"))

    # ------------------------------------------------ search (R-07)

    def search_chats(
        self, query: str, *, chat_id: str | None = None, limit: int = 20
    ) -> tuple[list[SearchHitView], dict[str, Any]]:
        """Search chats (``GET /api/v1/chats/search``, P-072):
        returns the typed hits plus the raw result document (mode
        used, fallback honesty, scan counts) for display words."""
        params: dict[str, Any] = {"q": query, "limit": limit}
        if chat_id:
            params["chat_id"] = chat_id
        payload = self._request("GET", "/api/v1/chats/search", params=params)
        document = payload if isinstance(payload, dict) else {}
        rows = document.get("results")
        hits = (
            [SearchHitView.from_dict(r) for r in rows if isinstance(r, dict)]
            if isinstance(rows, list)
            else []
        )
        return hits, document

    # ------------------------------------ checkpoints / undo (R-07)

    def list_checkpoints(self, chat_id: str) -> list[CheckpointView]:
        """A chat's checkpoints, oldest first (``GET
        /chats/{id}/checkpoints``, P-067)."""
        payload = self._request("GET", f"/api/v1/chats/{chat_id}/checkpoints")
        rows = payload if isinstance(payload, list) else []
        return [
            CheckpointView.from_dict(r) for r in rows if isinstance(r, dict)
        ]

    def create_checkpoint(
        self, chat_id: str, *, name: str | None = None
    ) -> CheckpointView:
        """Snapshot a chat as a named checkpoint (``POST
        /chats/{id}/checkpoints``, P-067). Never destructive."""
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        payload = self._request(
            "POST", f"/api/v1/chats/{chat_id}/checkpoints", json=body
        )
        return CheckpointView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def restore_checkpoint(
        self, chat_id: str, checkpoint_id: str, *, name: str | None = None
    ) -> ChatSummary:
        """Restore a checkpoint as a NEW chat (``POST
        /chats/{id}/checkpoints/{cid}/restore``, P-067); the
        source chat is never discarded."""
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/checkpoints/{checkpoint_id}/restore",
            json=body,
        )
        return ChatSummary.from_dict(payload if isinstance(payload, dict) else {})

    def delete_checkpoint(self, chat_id: str, checkpoint_id: str) -> bool:
        """Delete one checkpoint file (``DELETE
        /chats/{id}/checkpoints/{cid}``, P-067)."""
        payload = self._request(
            "DELETE", f"/api/v1/chats/{chat_id}/checkpoints/{checkpoint_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def list_undo(self, chat_id: str) -> list[UndoEntryView]:
        """A chat's undo journal, top of stack first (``GET
        /chats/{id}/undo``, P-076). Metadata only."""
        payload = self._request("GET", f"/api/v1/chats/{chat_id}/undo")
        document = payload if isinstance(payload, dict) else {}
        rows = document.get("entries")
        if not isinstance(rows, list):
            return []
        return [
            UndoEntryView.from_dict(r) for r in rows if isinstance(r, dict)
        ]

    def undo_last(self, chat_id: str) -> dict[str, Any]:
        """Undo the most recent journaled operation (``POST
        /chats/{id}/undo``, P-076): restores the operation's
        before-image in place and consumes the entry."""
        payload = self._request("POST", f"/api/v1/chats/{chat_id}/undo", json={})
        return payload if isinstance(payload, dict) else {}

    # ------------------------------------------------------------ characters

    def list_characters(self) -> list[CharacterSummary]:
        payload = self._request("GET", "/api/v1/characters")
        rows = payload if isinstance(payload, list) else []
        return [
            CharacterSummary.from_dict(r) for r in rows if isinstance(r, dict)
        ]

    def get_character(self, character_id: str) -> CharacterSummary:
        """One character's summary (``GET /characters/{id}``)."""
        payload = self._request("GET", f"/api/v1/characters/{character_id}")
        return CharacterSummary.from_dict(
            payload if isinstance(payload, dict) else {}
        )

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

    # ------------------------------------------- characters R-08 (full)

    def update_character(
        self, character_id: str, card: dict[str, Any], *, name: str | None = None
    ) -> CharacterSummary:
        """Replace a character's card (``PATCH /characters/{id}``).
        The card dict is the stored shape (unknown fields ride
        through the engine's importer/exporter, INV-009)."""
        body: dict[str, Any] = {"card": card}
        if name:
            body["name"] = name
        payload = self._request(
            "PATCH", f"/api/v1/characters/{character_id}", json=body
        )
        return CharacterSummary.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def delete_character(self, character_id: str) -> bool:
        """Soft-delete a character (``DELETE /characters/{id}``,
        S303): hidden, assets retained, undoable via
        :meth:`restore_character`."""
        payload = self._request(
            "DELETE", f"/api/v1/characters/{character_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def restore_character(self, character_id: str) -> CharacterSummary:
        """Undo a soft delete (``POST /characters/{id}/restore``)."""
        payload = self._request(
            "POST", f"/api/v1/characters/{character_id}/restore", json={}
        )
        return CharacterSummary.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def duplicate_character(self, character_id: str) -> CharacterSummary:
        """Copy a character under a fresh id (``POST
        /characters/{id}/duplicate``, S303)."""
        payload = self._request(
            "POST", f"/api/v1/characters/{character_id}/duplicate", json={}
        )
        return CharacterSummary.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def get_character_versions(
        self, character_id: str
    ) -> VersionHistoryView:
        """A character's version history (``GET
        /characters/{id}/versions``, P-025)."""
        payload = self._request(
            "GET", f"/api/v1/characters/{character_id}/versions"
        )
        return VersionHistoryView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def get_character_version_card(
        self, character_id: str, version_no: int
    ) -> dict[str, Any]:
        """One version's stored card dict (``GET
        /characters/{id}/versions/{n}`` carries ``card``)."""
        payload = self._request(
            "GET", f"/api/v1/characters/{character_id}/versions/{version_no}"
        )
        if isinstance(payload, dict):
            card = payload.get("card")
            if isinstance(card, dict):
                return card
        return {}

    def get_character_card(self, character_id: str) -> CharacterCardView:
        """The character's FULL card, composed from existing roads:
        the summary row + its current version's stored card (the
        version road is the only one that returns the whole card —
        there is no card-export route, and none is added)."""
        summary = self.get_character(character_id)
        card = self.get_character_version_card(character_id, summary.version_no)
        return CharacterCardView.from_parts(summary, card)

    def upload_avatar(
        self, character_id: str, filename: str, data: bytes
    ) -> str:
        """Upload/replace a character's avatar (``POST
        /characters/{id}/avatar``, multipart). Returns the stored
        filename the engine reports."""
        payload = self._request(
            "POST",
            f"/api/v1/characters/{character_id}/avatar",
            files=[("file", (filename, data))],
        )
        if isinstance(payload, dict):
            return str(payload.get("filename", ""))
        return ""

    def get_avatar_bytes(
        self, character_id: str
    ) -> tuple[bytes, str] | None:
        """The character's avatar bytes + media type (``GET
        /characters/{id}/avatar``); None when it has none."""
        try:
            return self._request_bytes(
                "GET", f"/api/v1/characters/{character_id}/avatar"
            )
        except NotFoundError:
            return None

    def get_character_book(self, character_id: str) -> dict[str, Any]:
        """The character's travelling character-book (``GET
        /characters/{id}/character-book``, P-039): the bound
        book serialised, or the card's embedded book, or
        ``{"entries": []}``."""
        payload = self._request(
            "GET", f"/api/v1/characters/{character_id}/character-book"
        )
        return payload if isinstance(payload, dict) else {}

    # ------------------------------------------------ library (R-08)

    def list_library_cards(
        self,
        *,
        q: str = "",
        tags: list[str] | None = None,
        tag_mode: str = "any",
        favourites_only: bool = False,
        sort: str = "name",
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[int, list[LibraryCardView]]:
        """One page of the character library (``GET
        /library/cards``, P-024): search text, tag filter,
        favourites, sort. Returns ``(total, items)``."""
        params: dict[str, Any] = {
            "tag_mode": tag_mode,
            "favourites_only": str(favourites_only).lower(),
            "sort": sort,
            "limit": limit,
            "offset": offset,
        }
        if q:
            params["q"] = q
        if tags:
            params["tag"] = tags
        payload = self._request("GET", "/api/v1/library/cards", params=params)
        document = payload if isinstance(payload, dict) else {}
        rows = document.get("items")
        total = document.get("total", 0)
        return (
            total if isinstance(total, int) else 0,
            [
                LibraryCardView.from_dict(r)
                for r in rows
                if isinstance(r, dict)
            ]
            if isinstance(rows, list)
            else [],
        )

    def list_library_tags(self) -> list[TagCountView]:
        """Every library tag with its character count (``GET
        /library/tags``, P-024)."""
        payload = self._request("GET", "/api/v1/library/tags")
        rows = payload.get("tags") if isinstance(payload, dict) else None
        return (
            [TagCountView.from_dict(r) for r in rows if isinstance(r, dict)]
            if isinstance(rows, list)
            else []
        )

    def get_organisation(self, character_id: str) -> OrganisationView:
        """A character's library organisation (tags + favourite)."""
        payload = self._request(
            "GET", f"/api/v1/library/cards/{character_id}/organisation"
        )
        return OrganisationView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def set_character_tags(
        self, character_id: str, tags: list[str]
    ) -> OrganisationView:
        """Replace a character's tags (``PUT
        /library/cards/{id}/tags``): the engine keeps the tag rows
        and the card's own tag list in step."""
        payload = self._request(
            "PUT",
            f"/api/v1/library/cards/{character_id}/tags",
            json={"tags": tags},
        )
        return OrganisationView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def set_character_favourite(
        self, character_id: str, is_favourite: bool
    ) -> OrganisationView:
        """Set/clear a character's favourite flag (``PUT
        /library/cards/{id}/favourite``)."""
        payload = self._request(
            "PUT",
            f"/api/v1/library/cards/{character_id}/favourite",
            json={"is_favourite": is_favourite},
        )
        return OrganisationView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def import_character_files(
        self, files: list[tuple[str, bytes]]
    ) -> dict[str, Any]:
        """Bulk-import card files (``POST /library/imports``,
        P-022): the full report dict — refusals are data in it,
        never errors."""
        payload = self._request(
            "POST",
            "/api/v1/library/imports",
            files=[("files", (name, data)) for name, data in files],
            data={"dry_run": "false"},
        )
        return payload if isinstance(payload, dict) else {}

    # ------------------------------------------------- assets (R-08)

    def list_assets(self, character_id: str) -> list[AssetView]:
        """A character's assets (``GET /characters/{id}/assets``,
        P-023), metadata only."""
        payload = self._request(
            "GET", f"/api/v1/characters/{character_id}/assets"
        )
        rows = payload if isinstance(payload, list) else []
        return [AssetView.from_dict(r) for r in rows if isinstance(r, dict)]

    def upload_asset(
        self,
        character_id: str,
        filename: str,
        data: bytes,
        *,
        kind: str = "embedded",
        name: str = "",
    ) -> AssetView:
        """Upload one asset file for a character (``POST
        /characters/{id}/assets``, multipart, P-023)."""
        payload = self._request(
            "POST",
            f"/api/v1/characters/{character_id}/assets",
            files=[("file", (filename, data))],
            data={"kind": kind, "name": name},
        )
        return AssetView.from_dict(payload if isinstance(payload, dict) else {})

    def get_asset_bytes(
        self, character_id: str, asset_id: str
    ) -> tuple[bytes, str]:
        """One asset's stored bytes + media type (``GET
        .../assets/{aid}/content``)."""
        return self._request_bytes(
            "GET",
            f"/api/v1/characters/{character_id}/assets/{asset_id}/content",
        )

    def get_asset_thumbnail(
        self, character_id: str, asset_id: str
    ) -> tuple[bytes, str] | None:
        """One asset's thumbnail bytes when the engine has one
        ready (``GET .../assets/{aid}/thumbnail``); None when no
        thumbnail exists — an honest absence, not an error."""
        try:
            return self._request_bytes(
                "GET",
                f"/api/v1/characters/{character_id}/assets/{asset_id}/thumbnail",
            )
        except NotFoundError:
            return None

    # ------------------------------------- lorebook binding (R-08)

    def list_lorebooks(self) -> list[LorebookSummary]:
        """All lorebooks (``GET /lorebooks``) — the binding
        picker's roster (the full editor is R-10)."""
        payload = self._request("GET", "/api/v1/lorebooks")
        rows = payload if isinstance(payload, list) else []
        return [
            LorebookSummary.from_dict(r) for r in rows if isinstance(r, dict)
        ]

    def get_lorebook_binding(self, character_id: str) -> BindingView:
        """A character's lorebook binding (``GET
        /characters/{id}/lorebook-binding``, P-039)."""
        payload = self._request(
            "GET", f"/api/v1/characters/{character_id}/lorebook-binding"
        )
        return BindingView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def bind_lorebook(
        self, character_id: str, lorebook_id: str, *, precedence: str | None = None
    ) -> BindingView:
        """Bind a lorebook to a character (``PUT
        /characters/{id}/lorebook-binding``, P-039)."""
        body: dict[str, Any] = {"lorebook_id": lorebook_id}
        if precedence:
            body["precedence"] = precedence
        payload = self._request(
            "PUT",
            f"/api/v1/characters/{character_id}/lorebook-binding",
            json=body,
        )
        return BindingView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def set_binding_precedence(
        self, character_id: str, precedence: str
    ) -> BindingView:
        """Change a binding's precedence (``PATCH
        /characters/{id}/lorebook-binding``)."""
        payload = self._request(
            "PATCH",
            f"/api/v1/characters/{character_id}/lorebook-binding",
            json={"precedence": precedence},
        )
        return BindingView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def unbind_lorebook(self, character_id: str) -> bool:
        """Remove a character's lorebook binding (``DELETE
        /characters/{id}/lorebook-binding``)."""
        payload = self._request(
            "DELETE", f"/api/v1/characters/{character_id}/lorebook-binding"
        )
        return bool(isinstance(payload, dict) and payload.get("unbound"))

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

    # --------------------------------------------------------------- presets

    def list_presets(self) -> list[PresetSummary]:
        """All sampling presets (identity fields only — the full
        preset editor is R-09; R-06 displays the applied name)."""
        payload = self._request("GET", "/api/v1/presets")
        rows = payload if isinstance(payload, list) else []
        return [PresetSummary.from_dict(r) for r in rows if isinstance(r, dict)]

    def get_preset(self, preset_id: str) -> PresetSummary:
        payload = self._request("GET", f"/api/v1/presets/{preset_id}")
        return PresetSummary.from_dict(payload if isinstance(payload, dict) else {})

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

    @staticmethod
    def new_request_id() -> str:
        """A fresh generation request id (the generation service's
        own shape: uuid4 hex). The caller keeps it so the Stop
        control can cancel exactly this stream."""
        return uuid.uuid4().hex

    def stream_composed(
        self,
        chat_id: str,
        *,
        request_id: str,
        profile_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Iterator[StreamEvent]:
        """Stream one composed turn (R-03 road, R-06 incremental).

        Yields :class:`StreamEvent` in wire order: a ``started``
        event carrying the response headers (which backend answered,
        composed vs raw), then ``token``/``reasoning`` events as
        they arrive, then a terminal ``done`` — or an ``error``
        event with a plain message (provider payloads never cross,
        INV-001/023). HTTP failures before the stream opens raise
        the typed client errors, like every other road. The stream
        runs on the CALLER's thread: the shell runs it on a worker
        thread and calls :meth:`cancel_generate` (from another
        thread; the httpx client is thread-safe) to stop it.
        """
        body: dict[str, Any] = {"chat_id": chat_id, "request_id": request_id}
        if profile_id:
            body["profile_id"] = profile_id
        if params:
            body["params"] = params
        try:
            with self._http.stream(
                "POST", "/api/v1/generate", json=body
            ) as response:
                self._raise_for_status(response)
                yield StreamEvent(
                    kind="started",
                    backend_key=response.headers.get("X-Backend-Key", ""),
                    mode=response.headers.get("X-Generation-Mode", ""),
                )
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[len("data:"):].strip())
                    except ValueError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    kind = event.get("type")
                    if kind == "token":
                        text = event.get("text")
                        if isinstance(text, str) and text:
                            yield StreamEvent(kind="token", text=text)
                    elif kind == "reasoning":
                        text = event.get("text")
                        if isinstance(text, str) and text:
                            yield StreamEvent(kind="reasoning", text=text)
                    elif kind == "error":
                        message = event.get("message")
                        yield StreamEvent(
                            kind="error",
                            message=str(message)
                            if message
                            else "generation failed in the engine",
                        )
                    elif kind == "done":
                        reason = event.get("finish_reason")
                        yield StreamEvent(
                            kind="done",
                            finish_reason=str(reason) if reason else "",
                        )
        except httpx.HTTPError as exc:
            raise TransportError(
                f"engine unreachable: {exc.__class__.__name__}"
            ) from exc

    def cancel_generate(self, request_id: str) -> bool:
        """Ask the engine to cancel one in-flight generation
        (``POST /api/v1/generate/cancel``, INV-003). Returns the
        engine's verdict: True when the request was live."""
        payload = self._request(
            "POST", "/api/v1/generate/cancel", json={"request_id": request_id}
        )
        return bool(isinstance(payload, dict) and payload.get("cancelled"))

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
