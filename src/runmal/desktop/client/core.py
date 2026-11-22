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
    BackupView,
    BindingView,
    BridgeCredentialView,
    BundleView,
    CharacterCardView,
    CharacterSummary,
    ChatSummary,
    CheckpointView,
    EngineSnapshot,
    ExpressionSetView,
    FirstRunState,
    GeneratedReply,
    GroupMemberView,
    GroupMessageView,
    GroupView,
    HealthStatus,
    ImportOutcome,
    LayerScopeSummary,
    LibraryCardView,
    LibraryHitView,
    LorebookSummary,
    LorebookView,
    LoreEntryView,
    LoreScopeView,
    MemoryView,
    MessageView,
    OrganisationView,
    OverrideView,
    PersonaView,
    PluginFailureReportView,
    PluginView,
    PresetDetail,
    PresetSummary,
    PreviewRow,
    QuickReplyView,
    ScenarioView,
    SearchHitView,
    StreamEvent,
    TagCountView,
    UndoEntryView,
    VersionHistoryView,
    VisionAttachmentView,
    VisionAttachOutcome,
    VisionDescriptionView,
    VisionProviderView,
    VoiceBackendView,
    VoiceDeviceView,
    VoiceSessionView,
    WatchFolderView,
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

    def clear_chat_secret(self, profile_id: str) -> BackendProfile:
        """Remove the stored chat API key (R-02 DELETE road)."""
        payload = self._request(
            "DELETE", f"/api/v1/backend-profiles/{profile_id}/chat-secret"
        )
        return BackendProfile.from_dict(payload if isinstance(payload, dict) else {})

    def set_embedding_secret(self, profile_id: str, value: str) -> BackendProfile:
        """Store an embedding API key via the write-only secret
        route — same INV-023 discipline as :meth:`set_chat_secret`:
        the value travels once and is never retained or echoed."""
        payload = self._request(
            "PUT",
            f"/api/v1/backend-profiles/{profile_id}/embedding-secret",
            json={"value": value},
        )
        return BackendProfile.from_dict(payload if isinstance(payload, dict) else {})

    def clear_embedding_secret(self, profile_id: str) -> BackendProfile:
        """Remove the stored embedding API key (R-02 DELETE road)."""
        payload = self._request(
            "DELETE", f"/api/v1/backend-profiles/{profile_id}/embedding-secret"
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

    def set_chat_persona(
        self, chat_id: str, character_id: str | None
    ) -> PersonaView:
        """Switch a chat's active persona (``POST
        /chats/{id}/persona``, R-03 road; R-10 panel). ``None``
        clears. Affects future turns only."""
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/persona",
            json={"character_id": character_id},
        )
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

    # ------------------------------------------- lorebooks, full (R-10)

    def list_lorebook_views(self) -> list[LorebookView]:
        """All lorebooks, full shape (``GET /api/v1/lorebooks``)."""
        payload = self._request("GET", "/api/v1/lorebooks")
        rows = payload if isinstance(payload, list) else []
        return [LorebookView.from_dict(r) for r in rows if isinstance(r, dict)]

    def get_lorebook(self, book_id: str) -> LorebookView:
        payload = self._request("GET", f"/api/v1/lorebooks/{book_id}")
        return LorebookView.from_dict(payload if isinstance(payload, dict) else {})

    def create_lorebook(self, fields: dict[str, Any]) -> LorebookView:
        """Create a lorebook (``POST /api/v1/lorebooks``)."""
        payload = self._request("POST", "/api/v1/lorebooks", json=fields)
        return LorebookView.from_dict(payload if isinstance(payload, dict) else {})

    def update_lorebook(
        self, book_id: str, fields: dict[str, Any]
    ) -> LorebookView:
        """Patch a lorebook (``PATCH /api/v1/lorebooks/{id}``); only
        the named fields are sent."""
        payload = self._request(
            "PATCH", f"/api/v1/lorebooks/{book_id}", json=fields
        )
        return LorebookView.from_dict(payload if isinstance(payload, dict) else {})

    def delete_lorebook(self, book_id: str) -> bool:
        payload = self._request("DELETE", f"/api/v1/lorebooks/{book_id}")
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def import_lorebook(self, document: dict[str, Any]) -> LorebookView:
        """Import a lorebook document (``POST /lorebooks/import``)."""
        payload = self._request("POST", "/api/v1/lorebooks/import", json=document)
        return LorebookView.from_dict(payload if isinstance(payload, dict) else {})

    def export_lorebook(self, book_id: str) -> dict[str, Any]:
        """Export a lorebook document (``GET
        /lorebooks/{id}/export``) as a plain dict."""
        payload = self._request("GET", f"/api/v1/lorebooks/{book_id}/export")
        return payload if isinstance(payload, dict) else {}

    def lorebook_editor_schema(self) -> dict[str, Any]:
        """The P-042 editor census (``GET /lorebooks/editor-schema``)
        the R-10 forms are generated from."""
        payload = self._request("GET", "/api/v1/lorebooks/editor-schema")
        return payload if isinstance(payload, dict) else {}

    def list_lore_entries(self, book_id: str) -> list[LoreEntryView]:
        payload = self._request("GET", f"/api/v1/lorebooks/{book_id}/entries")
        rows = payload if isinstance(payload, list) else []
        return [LoreEntryView.from_dict(r) for r in rows if isinstance(r, dict)]

    def create_lore_entry(
        self, book_id: str, fields: dict[str, Any]
    ) -> LoreEntryView:
        """Create an entry (``POST /lorebooks/{id}/entries``)."""
        payload = self._request(
            "POST", f"/api/v1/lorebooks/{book_id}/entries", json=fields
        )
        return LoreEntryView.from_dict(payload if isinstance(payload, dict) else {})

    def update_lore_entry(
        self, book_id: str, entry_id: str, fields: dict[str, Any]
    ) -> LoreEntryView:
        """Patch an entry (``PATCH /lorebooks/{id}/entries/{eid}``);
        only the named fields are sent."""
        payload = self._request(
            "PATCH",
            f"/api/v1/lorebooks/{book_id}/entries/{entry_id}",
            json=fields,
        )
        return LoreEntryView.from_dict(payload if isinstance(payload, dict) else {})

    def delete_lore_entry(self, book_id: str, entry_id: str) -> bool:
        payload = self._request(
            "DELETE", f"/api/v1/lorebooks/{book_id}/entries/{entry_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def list_book_scopes(self, book_id: str) -> list[LoreScopeView]:
        """A book's scope assignments (``GET
        /lorebooks/{id}/scopes``)."""
        payload = self._request("GET", f"/api/v1/lorebooks/{book_id}/scopes")
        rows = (
            payload.get("scopes")
            if isinstance(payload, dict)
            else None
        )
        return [
            LoreScopeView.from_dict(r)
            for r in (rows or [])
            if isinstance(r, dict)
        ]

    def assign_book_scope(
        self,
        book_id: str,
        scope_kind: str,
        owner_id: str | None,
        *,
        token_budget: int | None = None,
        position: int = 0,
    ) -> LoreScopeView:
        """Assign a book to a scope (``PUT /lorebooks/{id}/scope``)."""
        body: dict[str, Any] = {
            "scope_kind": scope_kind,
            "owner_id": owner_id,
            "position": position,
        }
        if token_budget is not None:
            body["token_budget"] = token_budget
        payload = self._request(
            "PUT", f"/api/v1/lorebooks/{book_id}/scope", json=body
        )
        return LoreScopeView.from_dict(payload if isinstance(payload, dict) else {})

    def unassign_book_scope(
        self, book_id: str, scope_kind: str, owner_id: str | None
    ) -> bool:
        """Remove a scope assignment (``DELETE
        /lorebooks/{id}/scope`` with query params)."""
        params: dict[str, Any] = {"scope_kind": scope_kind}
        if owner_id is not None:
            params["owner_id"] = owner_id
        payload = self._request(
            "DELETE", f"/api/v1/lorebooks/{book_id}/scope", params=params
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def preview_lorebook(
        self, book_id: str, messages: list[str]
    ) -> list[PreviewRow]:
        """Activation preview for one book (``POST
        /lorebooks/{id}/preview``) — per-entry verdict rows."""
        payload = self._request(
            "POST",
            f"/api/v1/lorebooks/{book_id}/preview",
            json={"messages": list(messages)},
        )
        rows = payload.get("entries") if isinstance(payload, dict) else None
        return [
            PreviewRow.from_dict(r) for r in (rows or []) if isinstance(r, dict)
        ]

    def preview_chat_lore(
        self, chat_id: str, messages: list[str]
    ) -> tuple[list[PreviewRow], list[LayerScopeSummary], list[str]]:
        """Layered lore preview for a chat (``POST
        /chats/{id}/lore-preview``): every layer's verdict rows,
        the per-layer scope summaries, and shadowed-book words."""
        payload = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}/lore-preview",
            json={"messages": list(messages)},
        )
        if not isinstance(payload, dict):
            return [], [], []
        rows: list[PreviewRow] = []
        layers = payload.get("layers")
        if isinstance(layers, dict):
            for layer in layers.values():
                if not isinstance(layer, dict):
                    continue
                for row in layer.get("entries") or []:
                    if isinstance(row, dict):
                        rows.append(PreviewRow.from_dict(row))
        summaries = [
            LayerScopeSummary.from_dict(s)
            for s in (payload.get("scopes") or [])
            if isinstance(s, dict)
        ]
        shadowed = [
            str(s.get("name") or s.get("lorebook_id") or s)
            if isinstance(s, dict)
            else str(s)
            for s in (payload.get("shadowed") or [])
        ]
        return rows, summaries, shadowed

    # ---------------------------------------------------------------- groups

    def list_groups(self) -> list[GroupView]:
        """All persistent group rooms (``GET /api/v1/groups``)."""
        payload = self._request("GET", "/api/v1/groups")
        return [
            GroupView.from_dict(g)
            for g in (payload or [])
            if isinstance(g, dict)
        ]

    def get_group(self, group_id: str) -> GroupView:
        payload = self._request("GET", f"/api/v1/groups/{group_id}")
        return GroupView.from_dict(payload if isinstance(payload, dict) else {})

    def create_group(
        self, name: str, member_character_ids: list[str]
    ) -> GroupView:
        """Create a room (``POST /api/v1/groups``, 201)."""
        payload = self._request(
            "POST",
            "/api/v1/groups",
            json={
                "name": name,
                "member_character_ids": list(member_character_ids),
            },
        )
        return GroupView.from_dict(payload if isinstance(payload, dict) else {})

    def update_group(
        self,
        group_id: str,
        *,
        name: str | None = None,
        speaker_policy: str | None = None,
        speaker_config: dict[str, Any] | None = None,
    ) -> GroupView:
        """Rename / re-strategise a room (``PATCH /api/v1/groups/{id}``).
        Only the fields given are sent."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if speaker_policy is not None:
            body["speaker_policy"] = speaker_policy
        if speaker_config is not None:
            body["speaker_config"] = speaker_config
        payload = self._request(
            "PATCH", f"/api/v1/groups/{group_id}", json=body
        )
        return GroupView.from_dict(payload if isinstance(payload, dict) else {})

    def delete_group(self, group_id: str) -> None:
        self._request("DELETE", f"/api/v1/groups/{group_id}")

    def add_group_member(
        self, group_id: str, character_id: str
    ) -> GroupMemberView:
        payload = self._request(
            "POST",
            f"/api/v1/groups/{group_id}/members",
            json={"character_id": character_id},
        )
        return GroupMemberView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def remove_group_member(self, group_id: str, character_id: str) -> None:
        self._request(
            "DELETE", f"/api/v1/groups/{group_id}/members/{character_id}"
        )

    def update_group_member(
        self,
        group_id: str,
        character_id: str,
        *,
        talkativeness: float | None = None,
        muted: bool | None = None,
    ) -> GroupMemberView:
        """Per-member settings (``PATCH …/members/{cid}``)."""
        body: dict[str, Any] = {}
        if talkativeness is not None:
            body["talkativeness"] = talkativeness
        if muted is not None:
            body["muted"] = muted
        payload = self._request(
            "PATCH",
            f"/api/v1/groups/{group_id}/members/{character_id}",
            json=body,
        )
        return GroupMemberView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def list_group_messages(self, group_id: str) -> list[GroupMessageView]:
        payload = self._request("GET", f"/api/v1/groups/{group_id}/messages")
        return [
            GroupMessageView.from_dict(m)
            for m in (payload or [])
            if isinstance(m, dict)
        ]

    def post_group_message(
        self, group_id: str, speaker: str, content: str
    ) -> GroupMessageView:
        """Append a transcript line (``POST …/messages``); speaker
        is ``"user"`` or a member character id."""
        payload = self._request(
            "POST",
            f"/api/v1/groups/{group_id}/messages",
            json={"speaker": speaker, "content": content},
        )
        return GroupMessageView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def get_group_deepening(self, group_id: str) -> dict[str, Any]:
        """The room's deepening document (``GET …/deepening``)."""
        payload = self._request("GET", f"/api/v1/groups/{group_id}/deepening")
        return dict(payload) if isinstance(payload, dict) else {}

    def put_group_deepening(
        self, group_id: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        """Replace the deepening document (``PUT …/deepening``);
        the shell composes over the stored document so engine
        state and unknown keys survive."""
        payload = self._request(
            "PUT", f"/api/v1/groups/{group_id}/deepening", json=document
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def patch_group_member_override(
        self, group_id: str, character_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Patch one member's override (``PATCH …/override``)."""
        payload = self._request(
            "PATCH",
            f"/api/v1/groups/{group_id}/members/{character_id}/override",
            json=patch,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def peek_group_member(
        self, group_id: str, character_id: str
    ) -> dict[str, Any]:
        """In-group card peek (``GET …/peek``): member + override +
        persona source + effective persona. Read-only."""
        payload = self._request(
            "GET", f"/api/v1/groups/{group_id}/members/{character_id}/peek"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def leave_group_member(self, group_id: str, character_id: str) -> dict:
        payload = self._request(
            "POST",
            f"/api/v1/groups/{group_id}/members/{character_id}/leave",
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def return_group_member(
        self, group_id: str, character_id: str
    ) -> dict[str, Any]:
        """Mark a member returned (``POST …/return``); the engine
        answers with the digest of what they missed."""
        payload = self._request(
            "POST",
            f"/api/v1/groups/{group_id}/members/{character_id}/return",
            json={},
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def group_member_digest(
        self, group_id: str, character_id: str
    ) -> dict[str, Any]:
        payload = self._request(
            "GET", f"/api/v1/groups/{group_id}/members/{character_id}/digest"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def group_presence(self, group_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/v1/groups/{group_id}/presence")
        return [dict(r) for r in (payload or []) if isinstance(r, dict)]

    def group_next(
        self,
        group_id: str,
        *,
        user_text: str | None = None,
        manual_speaker_id: str | None = None,
        generate: bool = False,
    ) -> dict[str, Any]:
        """One activation tick (``POST …/next``): the strategy's
        pick + reason; with ``generate`` the reply lands in the
        transcript."""
        body: dict[str, Any] = {"generate": generate}
        if user_text:
            body["user_text"] = user_text
        if manual_speaker_id:
            body["manual_speaker_id"] = manual_speaker_id
        payload = self._request(
            "POST", f"/api/v1/groups/{group_id}/next", json=body
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def group_run(
        self, group_id: str, *, turns: int = 1, generate: bool = False
    ) -> dict[str, Any]:
        """Several ticks at once (``POST …/run``)."""
        payload = self._request(
            "POST",
            f"/api/v1/groups/{group_id}/run",
            json={"turns": turns, "generate": generate},
        )
        return dict(payload) if isinstance(payload, dict) else {}

    # ------------------------------------------------- memory (R-12)

    def list_memories(
        self,
        *,
        q: str = "",
        state: str | None = None,
        kind: str | None = None,
    ) -> list[MemoryView]:
        """The memory browser list (``GET /api/v1/memories``,
        S410): provenance-carrying rows, server-filtered."""
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        if state:
            params["state"] = state
        if kind:
            params["kind"] = kind
        payload = self._request("GET", "/api/v1/memories", params=params)
        rows = payload.get("memories") if isinstance(payload, dict) else None
        return [
            MemoryView.from_dict(m)
            for m in (rows or [])
            if isinstance(m, dict)
        ]

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        """One memory with sources + provenance graph
        (``GET /api/v1/memories/{id}``)."""
        payload = self._request("GET", f"/api/v1/memories/{memory_id}")
        return dict(payload) if isinstance(payload, dict) else {}

    # ------------------------------------------------- scenarios (R-12)

    def list_scenarios(
        self, *, q: str = "", favourites_only: bool = False
    ) -> list[ScenarioView]:
        """The scenario library (``GET /api/v1/scenarios``,
        enriched summaries)."""
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        if favourites_only:
            params["favourites_only"] = "true"
        payload = self._request("GET", "/api/v1/scenarios", params=params)
        rows = payload.get("scenarios") if isinstance(payload, dict) else None
        return [
            ScenarioView.from_dict(s)
            for s in (rows or [])
            if isinstance(s, dict)
        ]

    def get_scenario(self, definition_id: str) -> ScenarioView:
        payload = self._request("GET", f"/api/v1/scenarios/{definition_id}")
        return ScenarioView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def create_scenario(self, definition: dict[str, Any]) -> ScenarioView:
        """Store a scenario file as a definition (``POST
        /api/v1/scenarios``, 201)."""
        payload = self._request("POST", "/api/v1/scenarios", json=definition)
        return ScenarioView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def update_scenario(
        self, definition_id: str, definition: dict[str, Any]
    ) -> ScenarioView:
        """Replace a definition (``PUT /api/v1/scenarios/{id}``)."""
        payload = self._request(
            "PUT", f"/api/v1/scenarios/{definition_id}", json=definition
        )
        return ScenarioView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def delete_scenario(self, definition_id: str) -> None:
        self._request("DELETE", f"/api/v1/scenarios/{definition_id}")

    def duplicate_scenario(self, definition_id: str) -> ScenarioView:
        payload = self._request(
            "POST", f"/api/v1/scenarios/{definition_id}/duplicate"
        )
        return ScenarioView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def set_scenario_favourite(
        self, definition_id: str, is_favourite: bool
    ) -> None:
        self._request(
            "PUT",
            f"/api/v1/scenarios/{definition_id}/favourite",
            json={"is_favourite": is_favourite},
        )

    def set_scenario_tags(
        self, definition_id: str, tags: list[str]
    ) -> None:
        self._request(
            "PUT",
            f"/api/v1/scenarios/{definition_id}/tags",
            json={"tags": list(tags)},
        )

    def list_scenario_tags(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/scenarios/library/tags")
        rows = payload.get("tags") if isinstance(payload, dict) else payload
        return [dict(t) for t in (rows or []) if isinstance(t, dict)]

    def bind_scenario(
        self, definition_id: str, chat_id: str
    ) -> dict[str, Any]:
        """Bind a definition to an owned EMPTY chat (``POST
        /scenarios/{id}/bind``): bootstrap lines seed the chat."""
        payload = self._request(
            "POST",
            f"/api/v1/scenarios/{definition_id}/bind",
            json={"chat_id": chat_id},
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def unbind_scenario(self, chat_id: str) -> None:
        self._request("DELETE", f"/api/v1/scenarios/bindings/{chat_id}")

    def get_chat_binding(self, chat_id: str) -> dict[str, Any]:
        payload = self._request(
            "GET", f"/api/v1/scenarios/bindings/{chat_id}"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def list_scenario_bindings(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/scenarios/bindings")
        rows = payload.get("bindings") if isinstance(payload, dict) else None
        return [dict(b) for b in (rows or []) if isinstance(b, dict)]

    def import_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Import a scenario file (``POST /api/v1/scenarios/import``)."""
        result = self._request(
            "POST", "/api/v1/scenarios/import", json=payload
        )
        return dict(result) if isinstance(result, dict) else {}

    def export_scenario(
        self, definition: dict[str, Any], *, fmt: str = "native"
    ) -> dict[str, Any]:
        """Re-export a scenario file (``POST /api/v1/scenarios/export``
        ?format=native|voxta)."""
        result = self._request(
            "POST",
            "/api/v1/scenarios/export",
            params={"format": fmt},
            json=definition,
        )
        return dict(result) if isinstance(result, dict) else {}

    # ------------------------------------------------- inspector (R-12)

    def inspector_overview(self, chat_id: str) -> dict[str, Any]:
        """The chat's Inspector overview (P-203)."""
        payload = self._request("GET", f"/api/v1/inspector/chats/{chat_id}")
        return dict(payload) if isinstance(payload, dict) else {}

    def inspector_events(self, chat_id: str) -> dict[str, Any]:
        """The chat's Inspector events census (P-204)."""
        payload = self._request(
            "GET", f"/api/v1/inspector/chats/{chat_id}/events"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def inspector_reasoning(self, chat_id: str) -> dict[str, Any]:
        """The chat's Inspector reasoning census (P-210)."""
        payload = self._request(
            "GET", f"/api/v1/inspector/chats/{chat_id}/reasoning"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def prompt_inspect(
        self,
        *,
        chat_id: str,
        character_id: str | None = None,
        messages: list[str] | None = None,
    ) -> dict[str, Any]:
        """The prompt trace for a chat (``POST
        /api/v1/debug/prompt-inspect``): ledger + slots with
        statuses and reasons, lore activation inspection on."""
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "include_activation_inspection": True,
            "messages": list(messages or []),
        }
        if character_id:
            body["character_id"] = character_id
        payload = self._request(
            "POST", "/api/v1/debug/prompt-inspect", json=body
        )
        return dict(payload) if isinstance(payload, dict) else {}

    # ------------------------------------------------- tools (R-12)

    def list_macros(self) -> list[dict[str, Any]]:
        """The macro registry (P-055): name/kind/description/
        syntax/example per macro."""
        payload = self._request("GET", "/api/v1/tools/macros")
        rows = payload if isinstance(payload, list) else []
        return [dict(m) for m in rows if isinstance(m, dict)]

    def expand_macros(
        self, text: str, *, char: str = "", user: str = "User"
    ) -> dict[str, Any]:
        """Expand macros in a text (``POST /tools/macros/expand``)."""
        payload = self._request(
            "POST",
            "/api/v1/tools/macros/expand",
            json={"text": text, "char": char, "user": user},
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def compose_preview(
        self,
        *,
        system: str = "",
        persona: str = "",
        history: list[str] | None = None,
        authors_note: str = "",
        note_depth: int = 0,
        context_limit: int = 4096,
        reserve_response: int = 512,
    ) -> dict[str, Any]:
        """The compose preview (``POST /api/v1/tools/compose``)."""
        payload = self._request(
            "POST",
            "/api/v1/tools/compose",
            json={
                "system": system,
                "persona": persona,
                "history": list(history or []),
                "authors_note": authors_note,
                "note_depth": note_depth,
                "context_limit": context_limit,
                "reserve_response": reserve_response,
            },
        )
        return dict(payload) if isinstance(payload, dict) else {}

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

    # -------------------------------------------- presets, full (R-09)

    def get_preset_detail(self, preset_id: str) -> PresetDetail:
        """The full preset row for the R-09 editor (bag included)."""
        payload = self._request("GET", f"/api/v1/presets/{preset_id}")
        return PresetDetail.from_dict(payload if isinstance(payload, dict) else {})

    def create_preset(
        self,
        name: str,
        params: dict[str, Any] | None = None,
        template_ref: str = "",
    ) -> PresetDetail:
        body: dict[str, Any] = {"name": name, "template_ref": template_ref}
        if params is not None:
            body["params"] = params
        payload = self._request("POST", "/api/v1/presets", json=body)
        return PresetDetail.from_dict(payload if isinstance(payload, dict) else {})

    def update_preset(
        self,
        preset_id: str,
        *,
        name: str | None = None,
        params: dict[str, Any] | None = None,
        template_ref: str | None = None,
    ) -> PresetDetail:
        """Partial preset update (S207 PATCH). Only the named
        fields are sent; ``params={}`` is a real value (it clears
        the bag) and is distinct from leaving params untouched."""
        body = {
            k: v
            for k, v in (
                ("name", name),
                ("params", params),
                ("template_ref", template_ref),
            )
            if v is not None
        }
        payload = self._request(
            "PATCH", f"/api/v1/presets/{preset_id}", json=body
        )
        return PresetDetail.from_dict(payload if isinstance(payload, dict) else {})

    def delete_preset(self, preset_id: str) -> bool:
        payload = self._request("DELETE", f"/api/v1/presets/{preset_id}")
        return bool(isinstance(payload, dict) and payload.get("ok"))

    def import_preset(
        self, payload_in: dict[str, Any], name: str | None = None
    ) -> PresetDetail:
        """Import a preset file object (P-021 interop road)."""
        params = {"name": name} if name else None
        payload = self._request(
            "POST", "/api/v1/presets/import", json=payload_in, params=params
        )
        return PresetDetail.from_dict(payload if isinstance(payload, dict) else {})

    def export_preset(
        self, preset_id: str, format: str | None = None
    ) -> dict[str, Any]:
        """Export a preset as a file object (native / st-text /
        st-chat); the payload is the file's JSON content."""
        params = {"format": format} if format else None
        payload = self._request(
            "GET", f"/api/v1/presets/{preset_id}/export", params=params
        )
        return payload if isinstance(payload, dict) else {}

    # ------------------------------------- preset bundles (P-054, R-09)

    def list_bundles(self) -> list[BundleView]:
        payload = self._request("GET", "/api/v1/presets/bundles")
        rows = payload if isinstance(payload, list) else []
        return [BundleView.from_dict(r) for r in rows if isinstance(r, dict)]

    def get_bundle(self, bundle_id: str) -> BundleView:
        payload = self._request("GET", f"/api/v1/presets/bundles/{bundle_id}")
        return BundleView.from_dict(payload if isinstance(payload, dict) else {})

    def create_bundle(self, bundle: dict[str, Any]) -> BundleView:
        payload = self._request(
            "POST", "/api/v1/presets/bundles", json={"bundle": bundle}
        )
        return BundleView.from_dict(payload if isinstance(payload, dict) else {})

    def update_bundle(
        self, bundle_id: str, bundle: dict[str, Any]
    ) -> BundleView:
        payload = self._request(
            "PATCH",
            f"/api/v1/presets/bundles/{bundle_id}",
            json={"bundle": bundle},
        )
        return BundleView.from_dict(payload if isinstance(payload, dict) else {})

    def delete_bundle(self, bundle_id: str) -> bool:
        payload = self._request(
            "DELETE", f"/api/v1/presets/bundles/{bundle_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("ok"))

    def share_bundle(self, bundle_id: str) -> dict[str, Any]:
        """The P-054 share envelope for one bundle (file form)."""
        payload = self._request(
            "GET", f"/api/v1/presets/bundles/{bundle_id}/share"
        )
        return payload if isinstance(payload, dict) else {}

    def import_bundle(
        self, payload_in: dict[str, Any], name: str | None = None
    ) -> BundleView:
        """Import a bundle (bare document or share envelope)."""
        params = {"name": name} if name else None
        payload = self._request(
            "POST", "/api/v1/presets/bundles/import",
            json=payload_in, params=params,
        )
        return BundleView.from_dict(payload if isinstance(payload, dict) else {})

    # ----------------------------------- preset overrides (P-054, R-09)

    def list_overrides(self) -> list[OverrideView]:
        payload = self._request("GET", "/api/v1/presets/overrides")
        rows = payload if isinstance(payload, list) else []
        return [OverrideView.from_dict(r) for r in rows if isinstance(r, dict)]

    def set_override(
        self,
        scope_kind: str,
        owner_id: str,
        bundle_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> OverrideView:
        body: dict[str, Any] = {"bundle_id": bundle_id}
        if overrides is not None:
            body["overrides"] = overrides
        payload = self._request(
            "PUT",
            f"/api/v1/presets/overrides/{scope_kind}/{owner_id}",
            json=body,
        )
        return OverrideView.from_dict(payload if isinstance(payload, dict) else {})

    def delete_override(self, scope_kind: str, owner_id: str) -> bool:
        payload = self._request(
            "DELETE", f"/api/v1/presets/overrides/{scope_kind}/{owner_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("ok"))

    # ---------------------------------------- preset packs (P-054, R-09)

    def inspect_pack(self, payload_in: dict[str, Any]) -> dict[str, Any]:
        payload = self._request(
            "POST", "/api/v1/presets/packs/inspect", json=payload_in
        )
        return payload if isinstance(payload, dict) else {}

    def import_pack(
        self, payload_in: dict[str, Any], on_conflict: str = "create_new"
    ) -> dict[str, Any]:
        payload = self._request(
            "POST", "/api/v1/presets/packs/import",
            json=payload_in, params={"on_conflict": on_conflict},
        )
        return payload if isinstance(payload, dict) else {}

    def export_pack(
        self,
        name: str,
        bundle_ids: list[str] | None = None,
        preset_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if bundle_ids is not None:
            body["bundle_ids"] = bundle_ids
        if preset_ids is not None:
            body["preset_ids"] = preset_ids
        payload = self._request(
            "POST", "/api/v1/presets/packs/export", json=body
        )
        return payload if isinstance(payload, dict) else {}

    def resolve_presets(
        self,
        chat_id: str | None = None,
        character_id: str | None = None,
    ) -> dict[str, Any] | None:
        """The effective-bundle view for a chat and/or character
        (``GET /presets/resolve``); None when no assignment
        applies. The view carries per-field sources — provenance
        is data, never silent (P-054)."""
        params: dict[str, Any] = {}
        if chat_id:
            params["chat_id"] = chat_id
        if character_id:
            params["character_id"] = character_id
        payload = self._request("GET", "/api/v1/presets/resolve", params=params)
        if isinstance(payload, dict):
            effective = payload.get("effective")
            if isinstance(effective, dict):
                return effective
        return None

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

    # ------------------------------------------------------- voice (R-13)

    def voice_status(self) -> dict[str, Any]:
        """Live voice state + metrics report (``GET
        /api/v1/voice/status``), raw — the logic layer renders it."""
        payload = self._request("GET", "/api/v1/voice/status")
        return dict(payload) if isinstance(payload, dict) else {}

    def _voice_devices_payload(self) -> dict[str, Any]:
        payload = self._request("GET", "/api/v1/voice/devices")
        return dict(payload) if isinstance(payload, dict) else {}

    def voice_devices(self) -> list[VoiceDeviceView]:
        """Enumerated audio endpoints (``GET /api/v1/voice/devices``)."""
        rows = self._voice_devices_payload().get("devices")
        return [
            VoiceDeviceView.from_dict(d)
            for d in (rows or [])
            if isinstance(d, dict)
        ]

    def voice_device_provider(self) -> str:
        """The device provider key behind the enumeration (the
        same ``GET /api/v1/voice/devices`` payload)."""
        return str(self._voice_devices_payload().get("provider", "") or "")

    def voice_roles(self) -> dict[str, Any]:
        """Saved role assignments + their live resolution
        (``GET /api/v1/voice/roles``), raw."""
        payload = self._request("GET", "/api/v1/voice/roles")
        return dict(payload) if isinstance(payload, dict) else {}

    def set_voice_role(self, role: str, device_id: str) -> dict[str, Any]:
        """Assign one role to one present device (``PUT
        /api/v1/voice/roles/{role}``)."""
        payload = self._request(
            "PUT",
            f"/api/v1/voice/roles/{role}",
            json={"device_id": device_id},
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def voice_backends(self) -> dict[str, Any]:
        """Every registered TTS/STT backend's status (``GET
        /api/v1/voice/backends``): rows parsed to views, the
        ``defaults`` dict kept raw."""
        payload = self._request("GET", "/api/v1/voice/backends")
        payload = payload if isinstance(payload, dict) else {}
        out: dict[str, Any] = {}
        for kind in ("tts", "stt"):
            rows = payload.get(kind)
            out[kind] = [
                VoiceBackendView.from_dict(b)
                for b in (rows or [])
                if isinstance(b, dict)
            ]
        defaults = payload.get("defaults")
        out["defaults"] = dict(defaults) if isinstance(defaults, dict) else {}
        return out

    def install_voice_backend(self, kind: str, key: str) -> dict[str, Any]:
        """The one-button install (``POST
        /api/v1/voice/backends/{kind}/{key}/install``) — an
        explicit user action; the engine refuses unverified plans."""
        payload = self._request(
            "POST", f"/api/v1/voice/backends/{kind}/{key}/install"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def voice_defaults(self) -> dict[str, Any]:
        """The default TTS/STT backend keys (``GET
        /api/v1/voice/settings/defaults``)."""
        payload = self._request("GET", "/api/v1/voice/settings/defaults")
        return dict(payload) if isinstance(payload, dict) else {}

    def set_voice_defaults(
        self,
        tts_backend: str | None = None,
        stt_backend: str | None = None,
    ) -> dict[str, Any]:
        """Set the default backends (``PUT
        /api/v1/voice/settings/defaults``); only the keys named
        are sent."""
        body: dict[str, Any] = {}
        if tts_backend is not None:
            body["tts_backend"] = tts_backend
        if stt_backend is not None:
            body["stt_backend"] = stt_backend
        payload = self._request(
            "PUT", "/api/v1/voice/settings/defaults", json=body
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def list_voice_sessions(self, chat_id: str = "") -> dict[str, Any]:
        """Voice sessions (``GET /api/v1/voice/sessions``):
        summaries parsed to views + the active session id."""
        params: dict[str, Any] = {}
        if chat_id:
            params["chat_id"] = chat_id
        payload = self._request(
            "GET", "/api/v1/voice/sessions", params=params
        )
        payload = payload if isinstance(payload, dict) else {}
        rows = payload.get("sessions")
        return {
            "sessions": [
                VoiceSessionView.from_dict(s)
                for s in (rows or [])
                if isinstance(s, dict)
            ],
            "active_session_id": payload.get("active_session_id") or None,
        }

    def start_voice_session(
        self, chat_id: str, auto_project: bool = False
    ) -> VoiceSessionView:
        """Start a voice session on a chat (``POST
        /api/v1/voice/sessions``, 201; the full session shape
        parses into the summary view)."""
        payload = self._request(
            "POST",
            "/api/v1/voice/sessions",
            json={"chat_id": chat_id, "auto_project": auto_project},
        )
        return VoiceSessionView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def get_voice_session(self, session_id: str) -> dict[str, Any]:
        """One voice session, full shape with its turns (``GET
        /api/v1/voice/sessions/{id}``), raw."""
        payload = self._request("GET", f"/api/v1/voice/sessions/{session_id}")
        return dict(payload) if isinstance(payload, dict) else {}

    def stop_voice_session(
        self, session_id: str, note: str = ""
    ) -> VoiceSessionView:
        """Stop a voice session (``POST
        /api/v1/voice/sessions/{id}/stop``)."""
        payload = self._request(
            "POST",
            f"/api/v1/voice/sessions/{session_id}/stop",
            json={"note": note},
        )
        return VoiceSessionView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def voice_session_latency(self, session_id: str) -> dict[str, Any]:
        """Per-turn latency evidence + aggregate (``GET
        /api/v1/voice/sessions/{id}/latency``), raw."""
        payload = self._request(
            "GET", f"/api/v1/voice/sessions/{session_id}/latency"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def voice_live(self, session_id: str) -> dict[str, Any]:
        """The session's live-orchestrator state (``GET
        /api/v1/voice/sessions/{id}/live``), raw."""
        payload = self._request(
            "GET", f"/api/v1/voice/sessions/{session_id}/live"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    # ------------------------------------------------------ vision (R-13)

    def vision_providers(self) -> dict[str, Any]:
        """The vision provider truth surface (``GET
        /api/v1/vision/providers``): ``providers`` parsed to
        views, every other key kept raw."""
        payload = self._request("GET", "/api/v1/vision/providers")
        payload = payload if isinstance(payload, dict) else {}
        out = dict(payload)
        rows = payload.get("providers")
        out["providers"] = [
            VisionProviderView.from_dict(p)
            for p in (rows or [])
            if isinstance(p, dict)
        ]
        return out

    def describe_image(
        self,
        chat_id: str,
        *,
        image_b64: str | None = None,
        attachment_id: str | None = None,
        asset_id: str | None = None,
        question: str = "",
        provider: str | None = None,
        require_semantic: bool = False,
    ) -> VisionDescriptionView:
        """Describe one image for a chat (``POST
        /api/v1/vision/describe``). Exactly one source should be
        named; source keys and ``provider`` travel only when set."""
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "question": question,
            "require_semantic": require_semantic,
        }
        if image_b64 is not None:
            body["image_b64"] = image_b64
        if attachment_id is not None:
            body["attachment_id"] = attachment_id
        if asset_id is not None:
            body["asset_id"] = asset_id
        if provider is not None:
            body["provider"] = provider
        payload = self._request("POST", "/api/v1/vision/describe", json=body)
        return VisionDescriptionView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def list_chat_descriptions(
        self, chat_id: str
    ) -> list[VisionDescriptionView]:
        """A chat's descriptions (``GET
        /api/v1/vision/descriptions?chat_id=``)."""
        payload = self._request(
            "GET", "/api/v1/vision/descriptions", params={"chat_id": chat_id}
        )
        rows = payload.get("descriptions") if isinstance(payload, dict) else None
        return [
            VisionDescriptionView.from_dict(d)
            for d in (rows or [])
            if isinstance(d, dict)
        ]

    def vision_history(
        self,
        q: str = "",
        *,
        chat_id: str | None = None,
        source_kind: str | None = None,
        provider_road: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Owner-scoped description history (``GET
        /api/v1/vision/history``): ``descriptions`` parsed to
        views, ``total`` and the rest kept raw."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        if chat_id is not None:
            params["chat_id"] = chat_id
        if source_kind is not None:
            params["source_kind"] = source_kind
        if provider_road is not None:
            params["provider_road"] = provider_road
        payload = self._request(
            "GET", "/api/v1/vision/history", params=params
        )
        payload = payload if isinstance(payload, dict) else {}
        out = dict(payload)
        rows = payload.get("descriptions")
        out["descriptions"] = [
            VisionDescriptionView.from_dict(d)
            for d in (rows or [])
            if isinstance(d, dict)
        ]
        return out

    def delete_description(self, description_id: str) -> bool:
        """Delete one description (``DELETE
        /api/v1/vision/descriptions/{id}``); True when the engine
        reports the deletion."""
        payload = self._request(
            "DELETE", f"/api/v1/vision/descriptions/{description_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def attach_image(
        self,
        chat_id: str,
        filename: str,
        image_b64: str,
        *,
        message_id: str | None = None,
        describe: bool = False,
        describe_question: str = "",
        describe_provider: str | None = None,
        require_semantic: bool = False,
    ) -> VisionAttachOutcome:
        """Attach image bytes to a chat (``POST
        /api/v1/vision/attachments``, 201), optionally describing
        them in the same act."""
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "filename": filename,
            "image_b64": image_b64,
            "describe": describe,
            "describe_question": describe_question,
            "require_semantic": require_semantic,
        }
        if message_id is not None:
            body["message_id"] = message_id
        if describe_provider is not None:
            body["describe_provider"] = describe_provider
        payload = self._request(
            "POST", "/api/v1/vision/attachments", json=body
        )
        payload = payload if isinstance(payload, dict) else {}
        description = payload.get("description")
        return VisionAttachOutcome(
            attachment=VisionAttachmentView.from_dict(payload),
            description=(
                VisionDescriptionView.from_dict(description)
                if isinstance(description, dict)
                else None
            ),
        )

    def list_attachments(self, chat_id: str) -> list[VisionAttachmentView]:
        """A chat's attachments (``GET
        /api/v1/vision/attachments?chat_id=``)."""
        payload = self._request(
            "GET", "/api/v1/vision/attachments", params={"chat_id": chat_id}
        )
        rows = payload.get("attachments") if isinstance(payload, dict) else None
        return [
            VisionAttachmentView.from_dict(a)
            for a in (rows or [])
            if isinstance(a, dict)
        ]

    def attachment_thumbnail(
        self, attachment_id: str, max_dim: int | None = None
    ) -> bytes:
        """One attachment's PNG thumbnail (``GET
        /api/v1/vision/attachments/{id}/thumbnail``)."""
        params: dict[str, Any] = {}
        if max_dim is not None:
            params["max_dim"] = max_dim
        content, _media = self._request_bytes(
            "GET",
            f"/api/v1/vision/attachments/{attachment_id}/thumbnail",
            params=params,
        )
        return content

    def delete_attachment(self, attachment_id: str) -> dict[str, Any]:
        """Delete one attachment (``DELETE
        /api/v1/vision/attachments/{id}``) — the engine purges
        its derived descriptions and reports the counts."""
        payload = self._request(
            "DELETE", f"/api/v1/vision/attachments/{attachment_id}"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def list_watch_folders(self, chat_id: str) -> list[WatchFolderView]:
        """A chat's watch folders (``GET
        /api/v1/vision/watch-folders?chat_id=``)."""
        payload = self._request(
            "GET", "/api/v1/vision/watch-folders", params={"chat_id": chat_id}
        )
        rows = payload.get("watch_folders") if isinstance(payload, dict) else None
        return [
            WatchFolderView.from_dict(w)
            for w in (rows or [])
            if isinstance(w, dict)
        ]

    def create_watch_folder(
        self, chat_id: str, path: str, recursive: bool = False
    ) -> WatchFolderView:
        """Register a watch folder for a chat (``POST
        /api/v1/vision/watch-folders``, 201)."""
        payload = self._request(
            "POST",
            "/api/v1/vision/watch-folders",
            json={"chat_id": chat_id, "path": path, "recursive": recursive},
        )
        return WatchFolderView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def update_watch_folder(
        self,
        watch_id: str,
        *,
        enabled: bool | None = None,
        recursive: bool | None = None,
    ) -> WatchFolderView:
        """Patch a watch folder's flags (``PATCH
        /api/v1/vision/watch-folders/{id}``); only the flags
        named are sent."""
        body: dict[str, Any] = {}
        if enabled is not None:
            body["enabled"] = enabled
        if recursive is not None:
            body["recursive"] = recursive
        payload = self._request(
            "PATCH", f"/api/v1/vision/watch-folders/{watch_id}", json=body
        )
        return WatchFolderView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def delete_watch_folder(self, watch_id: str) -> dict[str, Any]:
        """Delete a watch folder (``DELETE
        /api/v1/vision/watch-folders/{id}``); the engine reports
        how many ingested records died with it."""
        payload = self._request(
            "DELETE", f"/api/v1/vision/watch-folders/{watch_id}"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def scan_watch_folder(
        self,
        watch_id: str,
        *,
        describe: bool = False,
        describe_question: str = "",
        describe_provider: str | None = None,
        require_semantic: bool = False,
    ) -> dict[str, Any]:
        """Scan a watch folder once (``POST
        /api/v1/vision/watch-folders/{id}/scan``) — the scan
        report, raw."""
        body: dict[str, Any] = {
            "describe": describe,
            "describe_question": describe_question,
            "require_semantic": require_semantic,
        }
        if describe_provider is not None:
            body["describe_provider"] = describe_provider
        payload = self._request(
            "POST", f"/api/v1/vision/watch-folders/{watch_id}/scan", json=body
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def list_watch_ingested(self, watch_id: str) -> list[dict[str, Any]]:
        """A watch folder's ingested records (``GET
        /api/v1/vision/watch-folders/{id}/ingested``), raw rows."""
        payload = self._request(
            "GET", f"/api/v1/vision/watch-folders/{watch_id}/ingested"
        )
        rows = payload.get("ingested") if isinstance(payload, dict) else None
        return [dict(r) for r in (rows or []) if isinstance(r, dict)]

    # ----------------------------------------------------- backups (R-14)

    def list_backups(self) -> list[BackupView]:
        """Database backups present on disk (``GET
        /api/v1/backups``, S114): the filesystem listing shape
        — name, size, modified time. The engine's listing law
        matches only ``runmal-backup-*.db``; full bundles are
        NOT listed here and are staged by the name their
        create road returned."""
        payload = self._request("GET", "/api/v1/backups")
        rows = payload if isinstance(payload, list) else []
        return [BackupView.from_dict(r) for r in rows if isinstance(r, dict)]

    def create_backup(self) -> BackupView:
        """Take an online database backup (``POST
        /api/v1/backups``, 201): the verified info document.
        Secrets are never in a backup (``secrets_included`` is
        always False, S114)."""
        payload = self._request("POST", "/api/v1/backups")
        return BackupView.from_dict(payload if isinstance(payload, dict) else {})

    def create_full_backup(self) -> BackupView:
        """Take a full backup bundle — database + assets, one
        sealed ZIP (``POST /api/v1/backups/full``, 201, S802)."""
        payload = self._request("POST", "/api/v1/backups/full")
        return BackupView.from_dict(payload if isinstance(payload, dict) else {})

    def stage_backup(self, filename: str) -> dict[str, Any]:
        """Stage-restore a database backup (``POST
        /api/v1/backups/{filename}/stage``): the staged copy's
        verified info document, raw. The live database is never
        touched by staging."""
        payload = self._request(
            "POST", f"/api/v1/backups/{filename}/stage"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def stage_full_backup(self, filename: str) -> dict[str, Any]:
        """Stage a full backup bundle (``POST
        /api/v1/backups/full/{filename}/stage``): the restore
        report document (checks, counts, warnings), raw. The
        live installation is never touched by staging."""
        payload = self._request(
            "POST", f"/api/v1/backups/full/{filename}/stage"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def import_archive(self, path: str) -> dict[str, Any]:
        """Import a portable ``.runmal`` archive into a fresh
        staging directory (``POST /api/v1/archive/import``):
        the import report document, raw."""
        payload = self._request(
            "POST", "/api/v1/archive/import", json={"path": path}
        )
        return dict(payload) if isinstance(payload, dict) else {}

    # ----------------------------------------------------- plugins (R-14)

    def plugin_manager(self) -> dict[str, Any]:
        """The plugin manager ledger view (``GET
        /api/v1/plugins/manager``, P-083): ``installed`` rows +
        ``rehydration_problems``, raw — the ledger row shape is
        the manager's own document."""
        payload = self._request("GET", "/api/v1/plugins/manager")
        return dict(payload) if isinstance(payload, dict) else {}

    def list_plugins(self) -> list[PluginView]:
        """Every registered plugin (``GET /api/v1/plugins``,
        P-081 list-row shape)."""
        payload = self._request("GET", "/api/v1/plugins")
        rows = payload if isinstance(payload, list) else []
        return [PluginView.from_dict(r) for r in rows if isinstance(r, dict)]

    def plugin_detail(self, plugin_id: str) -> dict[str, Any]:
        """One plugin's detail document (``GET
        /api/v1/plugins/{id}``): the list row + manifest
        verbatim + failure log + UI contributions, raw."""
        payload = self._request("GET", f"/api/v1/plugins/{plugin_id}")
        return dict(payload) if isinstance(payload, dict) else {}

    def plugin_permission_card(self, plugin_id: str) -> dict[str, Any]:
        """The permission card for an installed or in-tree
        plugin (``GET /api/v1/plugins/{id}/permission-card``,
        P-083), raw — the logic layer renders its words."""
        payload = self._request(
            "GET", f"/api/v1/plugins/{plugin_id}/permission-card"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def plugin_failure_reports(self) -> list[PluginFailureReportView]:
        """Every plugin's failure report (``GET
        /api/v1/plugins/failure-reports``, P-099), in
        registration order."""
        payload = self._request("GET", "/api/v1/plugins/failure-reports")
        rows = payload if isinstance(payload, list) else []
        return [
            PluginFailureReportView.from_dict(r)
            for r in rows
            if isinstance(r, dict)
        ]

    def plugin_failure_report(
        self, plugin_id: str
    ) -> PluginFailureReportView:
        """One plugin's failure report (``GET
        /api/v1/plugins/{id}/failure-report``, P-099)."""
        payload = self._request(
            "GET", f"/api/v1/plugins/{plugin_id}/failure-report"
        )
        return PluginFailureReportView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def plugin_install_preview(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """The permission-card verdict for a pack, writing
        nothing (``POST /api/v1/plugins/install/preview``).
        The body carries the pack under ``pack``."""
        result = self._request(
            "POST", "/api/v1/plugins/install/preview", json=payload
        )
        return dict(result) if isinstance(result, dict) else {}

    def install_plugin(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Install a local pack (``POST /api/v1/plugins/install``,
        201; 200 for an exact duplicate): the outcome document
        (outcome + plugin detail + manager row + card), raw.
        The body carries ``pack`` + ``granted_permissions``."""
        result = self._request(
            "POST", "/api/v1/plugins/install", json=payload
        )
        return dict(result) if isinstance(result, dict) else {}

    def update_plugin(
        self, plugin_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """The versioned swap for one plugin (``POST
        /api/v1/plugins/{id}/update``): the outcome document,
        raw. The body carries ``pack`` + ``granted_permissions``."""
        result = self._request(
            "POST", f"/api/v1/plugins/{plugin_id}/update", json=payload
        )
        return dict(result) if isinstance(result, dict) else {}

    def uninstall_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Remove a pack-managed plugin (``POST
        /api/v1/plugins/{id}/uninstall``): outcome + plugin id
        + the card that was in force, raw."""
        result = self._request(
            "POST", f"/api/v1/plugins/{plugin_id}/uninstall"
        )
        return dict(result) if isinstance(result, dict) else {}

    def enable_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Enable one plugin (``POST /api/v1/plugins/{id}/enable``):
        the detail document after the transition, raw. An
        ``on_enable`` failure answers 200 with the ERRORED
        record — the record IS the report (PLG-01)."""
        result = self._request(
            "POST", f"/api/v1/plugins/{plugin_id}/enable"
        )
        return dict(result) if isinstance(result, dict) else {}

    def disable_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Disable one plugin (``POST
        /api/v1/plugins/{id}/disable``): the detail document
        after the transition, raw."""
        result = self._request(
            "POST", f"/api/v1/plugins/{plugin_id}/disable"
        )
        return dict(result) if isinstance(result, dict) else {}

    def acknowledge_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Acknowledge an errored plugin (``POST
        /api/v1/plugins/{id}/acknowledge``): the detail
        document after the transition, raw."""
        result = self._request(
            "POST", f"/api/v1/plugins/{plugin_id}/acknowledge"
        )
        return dict(result) if isinstance(result, dict) else {}

    # ---------------------------------------------- quick replies (R-14)

    def list_quick_replies(
        self, chat_id: str | None = None
    ) -> list[QuickReplyView]:
        """Quick-reply definitions (``GET /api/v1/quick-replies``,
        P-089), optionally narrowed to one chat's scope."""
        params: dict[str, Any] = {}
        if chat_id:
            params["chat_id"] = chat_id
        payload = self._request(
            "GET", "/api/v1/quick-replies", params=params
        )
        rows = payload if isinstance(payload, list) else []
        return [
            QuickReplyView.from_dict(r) for r in rows if isinstance(r, dict)
        ]

    def create_quick_reply(
        self, payload: dict[str, Any]
    ) -> QuickReplyView:
        """Create a quick reply (``POST /api/v1/quick-replies``,
        201). The body is the engine's reply document (``name``
        + ``text`` or ``steps``, scope, optional ``chat_id``)."""
        result = self._request(
            "POST", "/api/v1/quick-replies", json=payload
        )
        return QuickReplyView.from_dict(
            result if isinstance(result, dict) else {}
        )

    def get_quick_reply(self, reply_id: str) -> QuickReplyView:
        """One quick reply (``GET /api/v1/quick-replies/{id}``)."""
        payload = self._request("GET", f"/api/v1/quick-replies/{reply_id}")
        return QuickReplyView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def update_quick_reply(
        self, reply_id: str, payload: dict[str, Any]
    ) -> QuickReplyView:
        """Replace a quick reply (``PUT
        /api/v1/quick-replies/{id}``)."""
        result = self._request(
            "PUT", f"/api/v1/quick-replies/{reply_id}", json=payload
        )
        return QuickReplyView.from_dict(
            result if isinstance(result, dict) else {}
        )

    def delete_quick_reply(self, reply_id: str) -> bool:
        """Delete a quick reply (``DELETE
        /api/v1/quick-replies/{id}``)."""
        payload = self._request(
            "DELETE", f"/api/v1/quick-replies/{reply_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def execute_quick_reply(
        self, reply_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a quick reply into a chat (``POST
        /api/v1/quick-replies/{id}/execute``): the execution
        record, raw. The body must carry ``chat_id``."""
        result = self._request(
            "POST",
            f"/api/v1/quick-replies/{reply_id}/execute",
            json=payload or {},
        )
        return dict(result) if isinstance(result, dict) else {}

    def quick_reply_executions(self) -> list[dict[str, Any]]:
        """Past quick-reply execution records (``GET
        /api/v1/quick-replies/executions``), raw rows."""
        payload = self._request("GET", "/api/v1/quick-replies/executions")
        rows = payload if isinstance(payload, list) else []
        return [dict(r) for r in rows if isinstance(r, dict)]

    # ----------------------------------------------- expressions (R-14)

    def list_expression_sets(self) -> list[ExpressionSetView]:
        """All declared expression sets (``GET
        /api/v1/expressions/sets``, P-092)."""
        payload = self._request("GET", "/api/v1/expressions/sets")
        rows = payload if isinstance(payload, list) else []
        return [
            ExpressionSetView.from_dict(r)
            for r in rows
            if isinstance(r, dict)
        ]

    def get_expression_set(self, character_id: str) -> ExpressionSetView:
        """One character's expression set (``GET
        /api/v1/expressions/sets/{character_id}``)."""
        payload = self._request(
            "GET", f"/api/v1/expressions/sets/{character_id}"
        )
        return ExpressionSetView.from_dict(
            payload if isinstance(payload, dict) else {}
        )

    def create_expression_set(
        self, payload: dict[str, Any]
    ) -> ExpressionSetView:
        """Declare a character's expression set (``POST
        /api/v1/expressions/sets``, 201). Refused by the engine
        when a set for that character already exists — replace
        via :meth:`update_expression_set`."""
        result = self._request(
            "POST", "/api/v1/expressions/sets", json=payload
        )
        return ExpressionSetView.from_dict(
            result if isinstance(result, dict) else {}
        )

    def update_expression_set(
        self, character_id: str, payload: dict[str, Any]
    ) -> ExpressionSetView:
        """Replace a character's expression set (``PUT
        /api/v1/expressions/sets/{character_id}``); the body
        must name the same character."""
        result = self._request(
            "PUT",
            f"/api/v1/expressions/sets/{character_id}",
            json=payload,
        )
        return ExpressionSetView.from_dict(
            result if isinstance(result, dict) else {}
        )

    def delete_expression_set(self, character_id: str) -> bool:
        """Delete a character's expression set (``DELETE
        /api/v1/expressions/sets/{character_id}``)."""
        payload = self._request(
            "DELETE", f"/api/v1/expressions/sets/{character_id}"
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def expression_bindings(self, character_id: str) -> dict[str, Any]:
        """A set's asset-binding report (``GET
        /api/v1/expressions/sets/{character_id}/bindings``),
        raw."""
        payload = self._request(
            "GET", f"/api/v1/expressions/sets/{character_id}/bindings"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def derive_expression_set(self, character_id: str) -> dict[str, Any]:
        """Derive a draft set from a character's assets (``POST
        /api/v1/expressions/sets/{character_id}/derive``): the
        draft document, raw — nothing is saved by deriving."""
        payload = self._request(
            "POST", f"/api/v1/expressions/sets/{character_id}/derive"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def expressions_current(self, chat_id: str) -> dict[str, Any]:
        """A chat's current expression selection (``GET
        /api/v1/expressions/current?chat_id=...``): the
        selection document with its provenance, raw. The
        engine 404s when nothing is selected — that absence is
        the honest answer, surfaced as :class:`NotFoundError`."""
        payload = self._request(
            "GET", "/api/v1/expressions/current", params={"chat_id": chat_id}
        )
        return dict(payload) if isinstance(payload, dict) else {}

    # --------------------------------------------- chat variables (R-14)

    def chat_variables(self, chat_id: str) -> dict[str, Any]:
        """A chat's shared variables/flags snapshot (``GET
        /api/v1/chat-variables?chat_id=...``, P-093), raw."""
        payload = self._request(
            "GET", "/api/v1/chat-variables", params={"chat_id": chat_id}
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def set_chat_variable(
        self,
        chat_id: str,
        key: str,
        *,
        value: Any = None,
        flag: bool | None = None,
    ) -> dict[str, Any]:
        """Set one chat variable (or, with ``flag``, one chat
        flag) (``POST /api/v1/chat-variables/set``, P-093).
        Exactly one of ``value`` / ``flag`` is sent."""
        body: dict[str, Any] = {"chat_id": chat_id, "key": key}
        if flag is not None:
            body["flag"] = flag
        else:
            body["value"] = value
        payload = self._request(
            "POST", "/api/v1/chat-variables/set", json=body
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def unset_chat_variable(self, chat_id: str, key: str) -> bool:
        """Remove one chat variable (``POST
        /api/v1/chat-variables/unset``, P-093)."""
        payload = self._request(
            "POST",
            "/api/v1/chat-variables/unset",
            json={"chat_id": chat_id, "key": key},
        )
        return bool(isinstance(payload, dict) and payload.get("deleted"))

    def clear_chat_variables(self, chat_id: str) -> dict[str, Any]:
        """Clear all of a chat's variables (``POST
        /api/v1/chat-variables/clear``, P-093): the verdict
        document with the removed count, raw."""
        payload = self._request(
            "POST",
            "/api/v1/chat-variables/clear",
            json={"chat_id": chat_id},
        )
        return dict(payload) if isinstance(payload, dict) else {}

    # -------------------------------------------- library search (R-14)

    def search_hub(
        self, query: str, *, kind: str | None = None
    ) -> tuple[list[LibraryHitView], dict[str, Any]]:
        """Search the hub (``GET /api/v1/hub/unified-search``,
        P-192): one query over entry metadata AND verified pack
        contents, merged by entry. Returns the typed hits plus
        the raw document (totals, coverage, skips) for display
        words. An empty query is refused by the engine (422) —
        never treated as match-everything."""
        params: dict[str, Any] = {"q": query}
        if kind:
            params["kind"] = kind
        payload = self._request(
            "GET", "/api/v1/hub/unified-search", params=params
        )
        document = payload if isinstance(payload, dict) else {}
        rows = document.get("matches")
        hits = (
            [LibraryHitView.from_hub(r) for r in rows if isinstance(r, dict)]
            if isinstance(rows, list)
            else []
        )
        return hits, document

    def search_workspaces(
        self, query: str, chat_id: str, *, subpath: str = ""
    ) -> tuple[list[LibraryHitView], dict[str, Any]]:
        """Search one chat's bound workspace folder (``GET
        /api/v1/workspaces/unified-search``, P-182): entry
        names AND file contents over the bound tree, merged by
        path. Workspace search is chat-scoped by the engine's
        own law — there is no owner-wide workspace search.
        Returns the typed hits plus the raw document."""
        params: dict[str, Any] = {"chat_id": chat_id, "q": query}
        if subpath:
            params["subpath"] = subpath
        payload = self._request(
            "GET", "/api/v1/workspaces/unified-search", params=params
        )
        document = payload if isinstance(payload, dict) else {}
        rows = document.get("matches")
        hits = (
            [
                LibraryHitView.from_workspace(r)
                for r in rows
                if isinstance(r, dict)
            ]
            if isinstance(rows, list)
            else []
        )
        return hits, document

    def search_library(
        self, query: str, *, chat_id: str | None = None
    ) -> dict[str, list[LibraryHitView]]:
        """The R-14 fan-out: one query over every source that
        HAS a real search route. ``hub`` is always searched;
        ``workspaces`` joins only when ``chat_id`` names the
        chat whose bound folder is meant (its route is
        chat-scoped). Faces has NO search route in the engine
        (its routers are presentation/roster/census only), so
        no ``faces`` key is ever fabricated."""
        results: dict[str, list[LibraryHitView]] = {}
        hits, _document = self.search_hub(query)
        results["hub"] = hits
        if chat_id:
            ws_hits, _ws_document = self.search_workspaces(query, chat_id)
            results["workspaces"] = ws_hits
        return results

    # ------------------------------------------------ bridge admin (R-14)

    def list_bridge_credentials(self) -> list[BridgeCredentialView]:
        """Bridge credentials (``GET /api/v1/bridge/credentials``,
        S601 admin road): id/name/scopes/state only — the list
        payload never carries a token or its hash (INV-023)."""
        payload = self._request("GET", "/api/v1/bridge/credentials")
        rows = payload if isinstance(payload, list) else []
        return [
            BridgeCredentialView.from_dict(r)
            for r in rows
            if isinstance(r, dict)
        ]

    def create_bridge_credential(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a bridge credential (``POST
        /api/v1/bridge/credentials``, 201). The body carries
        ``name`` + ``scopes``.

        INV-023: the response is the ONE place the token
        plaintext ever appears. It is returned raw to the
        caller — the window shows it once — and is never
        parsed into a view, never logged, and never retained
        by this client."""
        result = self._request(
            "POST", "/api/v1/bridge/credentials", json=payload
        )
        return dict(result) if isinstance(result, dict) else {}

    def revoke_bridge_credential(
        self, credential_id: str
    ) -> BridgeCredentialView:
        """Revoke a bridge credential (``POST
        /api/v1/bridge/credentials/{id}/revoke``): the
        credential view with its revoked stamp. Idempotent in
        the engine — re-revoking keeps the first stamp."""
        payload = self._request(
            "POST", f"/api/v1/bridge/credentials/{credential_id}/revoke"
        )
        return BridgeCredentialView.from_dict(
            payload if isinstance(payload, dict) else {}
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
