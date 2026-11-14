"""Chat Stage logic (R-06, R-07) — Qt-free view-model layer.

The Chat Stage *widgets* live in ``runmal.desktop.window``; every
decision they render lives here, so the whole stage is unit-testable
on hosts with no PySide6 (the R-04/R-05 pattern). This module talks
to the engine ONLY through ``RunmalClient`` — no engine imports, no
SQL, no prompt logic.

The composed turn, end to end (the bridge's landing discipline,
applied to the local ``/generate`` road):

1. The user's line is persisted FIRST (``append_message``), so the
   R-03 server-side composition includes it in the prompt.
2. ``POST /generate`` streams the reply for the chat (composed
   mode); token events accumulate into a :class:`StreamDraft` the
   window renders live.
3. The reply is persisted ONLY after a clean finish (a ``done``
   event whose reason is not ``cancelled``/``error``) with text —
   a stopped or errored stream stores nothing, exactly like the
   bridge (``bridge.conversation.stream_generation``). The partial
   text of a stopped stream stays visible in the window, clearly
   labelled as not saved; it never enters the stored history.

The Session dock view (:class:`SessionView`) is resolved from real
API data only — the chat row, the R-03 persona road, the R-02
profile list, the preset list — in words, never colour alone, and
never fabricated: an unpinned chat says so and names the engine
default it will actually use, a dangling preset id says the preset
no longer exists.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from typing import Any

from runmal.desktop.client import RunmalClient
from runmal.desktop.client.errors import ClientError, NotFoundError
from runmal.desktop.client.models import (
    AuthorsNoteView,
    BackendProfile,
    CharacterSummary,
    ChatSummary,
    CheckpointView,
    MessageView,
    PersonaView,
    PresetSummary,
    SearchHitView,
    StreamEvent,
    UndoEntryView,
)

#: Speaker labels for roles with no recorded speaker name.
ROLE_LABELS = {"user": "You", "assistant": "Assistant", "system": "System"}


# ------------------------------------------------------------ session view


@dataclass(frozen=True)
class SessionView:
    """The Session dock's at-a-glance truth for one open chat.

    Every field is display words resolved from real API data; the
    ``*_label`` fields are complete sentences/fragments the dock
    shows verbatim after its field name."""

    chat_title: str
    character_label: str
    persona_label: str
    profile_label: str
    model_label: str
    preset_label: str


def resolve_session(
    chat: ChatSummary,
    *,
    persona: PersonaView | None,
    profiles: list[BackendProfile],
    characters: list[CharacterSummary],
    presets: list[PresetSummary],
) -> SessionView:
    """Resolve one chat's Session view from already-fetched data
    (pure; the flow below fetches, this function decides)."""
    character_names = {c.id: c.name for c in characters}
    if chat.character_id:
        name = character_names.get(chat.character_id)
        character_label = name or f"Character {chat.character_id} (not in the roster)"
    else:
        character_label = "No character — this chat is unbound"

    if persona is not None and persona.present:
        persona_label = persona.name or character_names.get(
            persona.character_id or "", ""
        ) or f"Character {persona.character_id}"
    elif persona is not None:
        persona_label = "No persona — the chat has no character"
    else:
        persona_label = "Unknown — the persona could not be read"

    profile_by_id = {p.id: p for p in profiles}
    if chat.backend_profile_id:
        profile = profile_by_id.get(chat.backend_profile_id)
        if profile is not None:
            profile_label = profile.label
            model_label = profile.chat_model or "— (profile names no model)"
        else:
            profile_label = (
                f"Profile {chat.backend_profile_id} (no longer exists)"
            )
            model_label = "—"
    else:
        profile_label = "No profile pinned — the engine default answers"
        model_label = "Engine default (fake backend, Demo replies)"

    preset_by_id = {p.id: p for p in presets}
    if chat.preset_id:
        preset = preset_by_id.get(chat.preset_id)
        preset_label = (
            preset.name
            if preset is not None
            else f"Preset {chat.preset_id} (no longer exists)"
        )
    else:
        preset_label = "No preset applied"

    return SessionView(
        chat_title=chat.title or "(untitled chat)",
        character_label=character_label,
        persona_label=persona_label,
        profile_label=profile_label,
        model_label=model_label,
        preset_label=preset_label,
    )


# ------------------------------------------------------------ open chat


@dataclass(frozen=True)
class OpenChat:
    """One chat opened in the stage: its row, its stored history,
    and its resolved Session view."""

    chat: ChatSummary
    messages: list[MessageView] = field(default_factory=list)
    session: SessionView | None = None


# ------------------------------------------------------------ streaming


@dataclass
class StreamDraft:
    """The in-flight reply, reduced from stream events.

    ``text`` is what the window shows growing; ``reasoning_text``
    is collected for honesty in the result (the R-06 stage does
    not render reasoning live — stored-reasoning display is the
    Inspector's road, R-12). ``finish`` stays empty until the
    terminal event; ``error`` carries a stream error's message."""

    text: str = ""
    reasoning_text: str = ""
    backend_key: str = ""
    mode: str = ""
    finish: str = ""
    error: str = ""

    def apply(self, event: StreamEvent) -> None:
        if event.kind == "started":
            self.backend_key = event.backend_key
            self.mode = event.mode
        elif event.kind == "token":
            self.text += event.text
        elif event.kind == "reasoning":
            self.reasoning_text += event.text
        elif event.kind == "error":
            self.error = event.message
        elif event.kind == "done":
            self.finish = event.finish_reason

    @property
    def completed_cleanly(self) -> bool:
        """True only when the stream finished on its own terms:
        a done event, no error, not a cancellation, with text."""
        return (
            bool(self.finish)
            and self.finish not in ("cancelled", "error")
            and not self.error
            and bool(self.text)
        )

    @property
    def stopped(self) -> bool:
        return self.finish == "cancelled" and not self.error


@dataclass(frozen=True)
class TurnResult:
    """The outcome of one composed turn (see :meth:`ChatFlow.send_turn`)."""

    draft: StreamDraft
    user_message: MessageView
    assistant_message: MessageView | None = None

    @property
    def landed(self) -> bool:
        """Whether the reply was persisted into the chat."""
        return self.assistant_message is not None

    @property
    def status_words(self) -> str:
        """The turn's verdict in plain words, for the status bar."""
        draft = self.draft
        if draft.error:
            return f"Generation failed: {draft.error} — nothing was saved."
        if draft.stopped:
            return (
                "Stopped — the partial reply was not saved "
                f"({len(draft.text)} characters shown only here)."
            )
        if self.landed:
            who = draft.backend_key or "the backend"
            return f"Reply received from {who} and saved to the chat."
        if draft.finish:
            return "The reply finished empty — nothing was saved."
        return "The stream ended without finishing — nothing was saved."


# ------------------------------------------------------------ transcript


def speaker_label(
    message: MessageView,
    *,
    character_name: str = "",
    user_name: str = "",
) -> str:
    """Who said one message, in words: the recorded speaker name
    wins; otherwise the character for assistant lines, the user's
    name for user lines, the role word last."""
    if message.speaker_name:
        return message.speaker_name
    if message.role == "assistant" and character_name:
        return character_name
    if message.role == "user" and user_name:
        return user_name
    return ROLE_LABELS.get(message.role, message.role or "Message")


def transcript_html(
    messages: list[MessageView],
    *,
    character_name: str = "",
    user_name: str = "",
    draft: StreamDraft | None = None,
    draft_speaker: str = "",
) -> str:
    """Render a chat's history (+ an optional in-flight draft) as
    the stage's HTML: one block per message, speaker in bold words
    above the (escaped) text. A draft block is marked as still
    writing, or as stopped-and-unsaved once it stops."""
    blocks: list[str] = []
    for message in messages:
        who = html.escape(
            speaker_label(
                message, character_name=character_name, user_name=user_name
            )
        )
        # R-07 state words: pin + swipe position are shown as
        # words beside the speaker, never as colour or icon alone.
        marks: list[str] = []
        if message.pinned:
            marks.append("pinned")
        if message.swipe_count > 1:
            marks.append(
                f"swipe {message.swipe_id + 1} of {message.swipe_count}"
            )
        if marks:
            who += " · " + html.escape(", ".join(marks))
        body = html.escape(message.content).replace("\n", "<br/>")
        blocks.append(f"<p><b>{who}</b><br/>{body}</p>")
    if draft is not None and (draft.text or draft.finish or draft.error):
        who = html.escape(draft_speaker or character_name or "Assistant")
        if draft.error:
            state = " — failed, not saved"
        elif draft.stopped:
            state = " — stopped, not saved"
        elif draft.finish:
            state = ""
        else:
            state = " — writing…"
        body = html.escape(draft.text).replace("\n", "<br/>")
        blocks.append(f"<p><b>{who}{state}</b><br/>{body}</p>")
    if not blocks:
        return "<p><i>No messages yet — say the first word below.</i></p>"
    return "\n".join(blocks)


def export_filename(chat: ChatSummary) -> str:
    """A filesystem-friendly export filename for one chat."""
    slug = "".join(
        ch if ch.isalnum() or ch in "-_" else "-" for ch in (chat.title or "")
    ).strip("-")
    return f"runmal-chat-{slug or chat.id}.json"


# ------------------------------------------------- R-07 outcomes


@dataclass(frozen=True)
class ContinueOutcome:
    """The landing of one Continue (P-069): the engine generated
    AND landed it — ``extend`` grew the last assistant message in
    place, ``next`` appended a new one."""

    mode: str
    content: str
    message: MessageView | None = None
    backend_key: str = ""

    @property
    def status_words(self) -> str:
        if self.mode == "extend":
            return "Continued — the last reply was extended in place and saved."
        return "Continued — a new reply was added and saved."


@dataclass(frozen=True)
class ImpersonateDraft:
    """One impersonate draft (P-069): a DRAFT only. It is never a
    stored message until the user accepts a final text."""

    draft_id: str
    content: str
    backend_key: str = ""


@dataclass(frozen=True)
class RegenResult:
    """The outcome of one Regenerate (see
    :meth:`ChatFlow.regenerate` for the discipline)."""

    draft: StreamDraft
    message: MessageView | None = None
    restored: bool = False

    @property
    def landed(self) -> bool:
        return self.message is not None

    @property
    def status_words(self) -> str:
        draft = self.draft
        if self.landed:
            who = draft.backend_key or "the backend"
            return f"Regenerated — the new reply from {who} was saved."
        if self.restored:
            if draft.error:
                return (
                    f"Regeneration failed: {draft.error} — the "
                    "previous reply was restored unchanged."
                )
            return (
                "Regeneration stopped — the previous reply was "
                "restored unchanged; the partial was not saved."
            )
        return "Regeneration did not finish — reload the chat to see its state."


@dataclass(frozen=True)
class SearchOutcome:
    """One chat search (P-072): typed hits + the engine's honesty
    words (mode actually used, fallback reason, scan counts)."""

    hits: list[SearchHitView]
    query: str
    mode_used: str = ""
    fallback_reason: str = ""
    total: int = 0

    @property
    def status_words(self) -> str:
        if not self.hits:
            return f"No matches for “{self.query}”."
        words = f"{self.total} match(es) for “{self.query}”"
        if self.mode_used:
            words += f" · mode: {self.mode_used}"
        if self.fallback_reason:
            words += f" · {self.fallback_reason}"
        return words + "."


def message_list_label(
    message: MessageView,
    *,
    character_name: str = "",
    user_name: str = "",
) -> str:
    """One line for the stage's message list (R-07): speaker,
    state words (pinned / swipe position), and a short excerpt —
    enough to pick the message an action should land on."""
    who = speaker_label(
        message, character_name=character_name, user_name=user_name
    )
    marks: list[str] = []
    if message.pinned:
        marks.append("pinned")
    if message.swipe_count > 1:
        marks.append(f"swipe {message.swipe_id + 1}/{message.swipe_count}")
    excerpt = " ".join(message.content.split())
    if len(excerpt) > 60:
        excerpt = excerpt[:57] + "…"
    label = who
    if marks:
        label += " · " + ", ".join(marks)
    return f"{label} — {excerpt}" if excerpt else label


# ------------------------------------------------------------ the flow


class ChatFlow:
    """Stateful driver for the Chat Stage, over one client.

    Holds only the active generation's request id (so the Stop
    control can cancel exactly that stream from another thread) —
    never message text beyond the draft a turn returns.
    """

    def __init__(self, client: RunmalClient) -> None:
        self._client = client
        self.active_request_id: str | None = None

    # ------------------------------------------------------------ reads

    def open_chat(self, chat_id: str) -> OpenChat:
        """Fetch one chat's history + its Session view inputs."""
        chat = self._client.get_chat(chat_id)
        messages = self._client.list_chat_messages(chat_id)
        session = self.session_view(chat)
        return OpenChat(chat=chat, messages=messages, session=session)

    def session_view(self, chat: ChatSummary) -> SessionView:
        """Resolve the Session view for a chat from live API data.
        A persona read that 404s (the chat vanished mid-refresh)
        degrades to the honest Unknown label, never a crash."""
        try:
            persona = self._client.get_chat_persona(chat.id)
        except NotFoundError:
            persona = None
        return resolve_session(
            chat,
            persona=persona,
            profiles=self._client.list_backend_profiles(),
            characters=self._client.list_characters(),
            presets=self._client.list_presets(),
        )

    # ------------------------------------------------------- chats dock

    def create_chat(
        self, *, character_id: str | None = None, title: str = ""
    ) -> OpenChat:
        """Create a chat (the engine seeds the character's greeting
        when one is picked) and open it."""
        chat = self._client.create_chat(title=title, character_id=character_id)
        return self.open_chat(chat.id)

    def rename_chat(self, chat_id: str, title: str) -> ChatSummary:
        cleaned = (title or "").strip()
        if not cleaned:
            raise ClientError("the chat needs a title")
        return self._client.rename_chat(chat_id, cleaned)

    def delete_chat(self, chat_id: str) -> bool:
        return self._client.delete_chat(chat_id)

    def export_chat(self, chat_id: str) -> dict[str, Any]:
        return self._client.export_chat(chat_id)

    def export_text(self, chat_id: str) -> str:
        """The export document as the exact JSON text a file gets."""
        return json.dumps(self.export_chat(chat_id), indent=2, ensure_ascii=False)

    # ------------------------------------------------------------- turns

    def send_turn(
        self,
        chat_id: str,
        text: str,
        *,
        on_event=None,
        request_id: str | None = None,
    ) -> TurnResult:
        """One composed turn (see the module docstring for the
        landing discipline). ``on_event`` (optional) is called with
        each :class:`StreamEvent` as it arrives, on THIS thread —
        the window's worker forwards them to the GUI thread.

        Raises the typed client errors for pre-stream failures
        (unknown chat, unreachable engine); a stream-level error
        event is reported in the result instead, with nothing
        landed."""
        cleaned = (text or "").strip()
        if not cleaned:
            raise ClientError("write a message first")
        # The request id is registered BEFORE the user line lands,
        # so the Stop control can name this exact turn from the
        # moment sending starts (a caller-supplied id lets the
        # window hold the same value the flow will stream under).
        request_id = request_id or self._client.new_request_id()
        self.active_request_id = request_id
        draft = StreamDraft()
        try:
            user_message = self._client.append_message(chat_id, "user", cleaned)
            for event in self._client.stream_composed(
                chat_id, request_id=request_id
            ):
                draft.apply(event)
                if on_event is not None:
                    on_event(event)
        finally:
            self.active_request_id = None
        assistant_message = None
        if draft.completed_cleanly:
            assistant_message = self._client.append_message(
                chat_id, "assistant", draft.text
            )
        return TurnResult(
            draft=draft,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    def cancel_active(self) -> bool:
        """Cancel the in-flight turn, if any (the Stop control).
        Returns the engine's verdict; False when nothing is live."""
        request_id = self.active_request_id
        if not request_id:
            return False
        return self._client.cancel_generate(request_id)

    # ------------------------------------------- message actions (R-07)

    def edit_message(
        self, chat_id: str, message_id: str, content: str
    ) -> MessageView:
        """Edit one message's text. Empty text is refused here
        (the engine's 422 says the same, later and uglier)."""
        cleaned = (content or "").strip()
        if not cleaned:
            raise ClientError("a message cannot be emptied by editing")
        return self._client.edit_message(chat_id, message_id, cleaned)

    def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Delete one message. The engine journals the delete
        (P-076), so the Undo surface can bring it back."""
        return self._client.delete_message(chat_id, message_id)

    def add_swipe(
        self, chat_id: str, message_id: str, content: str
    ) -> MessageView:
        cleaned = (content or "").strip()
        if not cleaned:
            raise ClientError("a swipe alternate cannot be empty")
        return self._client.add_swipe(chat_id, message_id, cleaned)

    def swipe_next(self, chat_id: str, message_id: str) -> MessageView:
        return self._client.select_swipe(chat_id, message_id, action="next")

    def swipe_prev(self, chat_id: str, message_id: str) -> MessageView:
        return self._client.select_swipe(chat_id, message_id, action="prev")

    def select_swipe(
        self, chat_id: str, message_id: str, index: int
    ) -> MessageView:
        return self._client.select_swipe(chat_id, message_id, index=index)

    def delete_swipe(
        self, chat_id: str, message_id: str, index: int
    ) -> MessageView:
        return self._client.delete_swipe(chat_id, message_id, index)

    def set_pinned(
        self, chat_id: str, message: MessageView, pinned: bool
    ) -> bool:
        """Pin or unpin one message; returns the NEW pin state as
        the engine reports it afterwards (a re-read, never an
        assumption)."""
        if pinned:
            self._client.pin_message(chat_id, message.id)
        else:
            self._client.unpin_message(chat_id, message.id)
        pinned_now = {
            m.id for m in self._client.list_pinned_messages(chat_id)
        }
        return message.id in pinned_now

    def pinned_messages(self, chat_id: str) -> list[MessageView]:
        return self._client.list_pinned_messages(chat_id)

    def branch_from(
        self,
        chat_id: str,
        *,
        message_id: str | None = None,
        name: str = "",
    ) -> ChatSummary:
        """Fork the chat at a message (or whole) into a NEW chat;
        the source is never mutated (P-066)."""
        return self._client.branch_chat(
            chat_id, message_id=message_id, name=name or None
        )

    def branch_family(self, chat_id: str) -> dict[str, Any]:
        return self._client.list_branches(chat_id)

    # ------------------------------------------ author's note (R-07)

    def authors_note(self, chat_id: str) -> AuthorsNoteView:
        return self._client.get_authors_note(chat_id)

    def save_authors_note(
        self,
        chat_id: str,
        *,
        text: str,
        depth: int = 4,
        frequency: int = 1,
        enabled: bool = True,
        role: str = "system",
    ) -> AuthorsNoteView:
        """Save the note, then read it back — the returned view is
        what the engine actually stored."""
        self._client.set_authors_note(
            chat_id,
            text=text,
            depth=depth,
            frequency=frequency,
            enabled=enabled,
            role=role,
        )
        return self._client.get_authors_note(chat_id)

    # -------------------------------------- continue / impersonate

    def continue_turn(
        self, chat_id: str, *, mode: str = "auto", instruction: str = ""
    ) -> ContinueOutcome:
        """Continue the chat (P-069): the engine generates and
        LANDS the continuation itself — this flow only reports
        where it landed."""
        document = self._client.continue_chat(
            chat_id, mode=mode, instruction=instruction or None
        )
        raw_message = document.get("message")
        return ContinueOutcome(
            mode=str(document.get("mode", "")),
            content=str(document.get("content", "")),
            message=(
                MessageView.from_dict(raw_message)
                if isinstance(raw_message, dict)
                else None
            ),
            backend_key=str(document.get("backend", "")),
        )

    def impersonate(self, chat_id: str, *, instruction: str = "") -> ImpersonateDraft:
        """Draft the next user line (P-069). Nothing is stored."""
        document = self._client.impersonate_draft(
            chat_id, instruction=instruction or None
        )
        return ImpersonateDraft(
            draft_id=str(document.get("id", "")),
            content=str(document.get("content", "")),
            backend_key=str(document.get("backend", "")),
        )

    def accept_impersonate(
        self, chat_id: str, draft: ImpersonateDraft, content: str
    ) -> MessageView:
        """Land an impersonate draft's final text (the draft
        verbatim or the user's edit of it) as a real user message."""
        cleaned = (content or "").strip()
        if not cleaned:
            raise ClientError("an accepted impersonation cannot be empty")
        return self._client.accept_impersonate(
            chat_id, cleaned, draft_id=draft.draft_id or None
        )

    def discard_impersonate(self, chat_id: str, draft: ImpersonateDraft) -> bool:
        return self._client.discard_impersonate(
            chat_id, draft_id=draft.draft_id or None
        )

    # ------------------------------------------------- regenerate

    def regenerate(
        self,
        chat_id: str,
        *,
        on_event=None,
        request_id: str | None = None,
    ) -> RegenResult:
        """Regenerate the chat's last reply.

        There is no engine regenerate route; this composes the
        roads that exist, with the R-06 landing discipline:

        1. The last message must be an assistant reply. It is
           deleted FIRST — the delete is journaled (P-076) and
           the composed prompt then ends at the user line it
           answers, exactly the prompt the original reply saw.
        2. A fresh composed turn streams (no new user line).
        3. On a clean finish the new reply lands as a fresh
           assistant message. On ANY other ending the old reply
           is restored — via the undo journal first (exact
           before-image, original id), falling back to
           re-appending its text — and the result says so.
        """
        history = self._client.list_chat_messages(chat_id)
        if not history:
            raise ClientError("there is nothing to regenerate yet")
        last = history[-1]
        if last.role != "assistant":
            raise ClientError(
                "only a chat whose last message is the assistant's "
                "reply can be regenerated"
            )
        request_id = request_id or self._client.new_request_id()
        self.active_request_id = request_id
        draft = StreamDraft()
        deleted = False
        try:
            deleted = self._client.delete_message(chat_id, last.id)
            if not deleted:
                raise ClientError("the last reply could not be set aside")
            for event in self._client.stream_composed(
                chat_id, request_id=request_id
            ):
                draft.apply(event)
                if on_event is not None:
                    on_event(event)
        finally:
            self.active_request_id = None
        if draft.completed_cleanly:
            message = self._client.append_message(
                chat_id, "assistant", draft.text
            )
            return RegenResult(draft=draft, message=message)
        # Restore the old reply: undo the journaled delete when
        # possible (exact restore), else re-append its text.
        restored = False
        if deleted:
            try:
                self._client.undo_last(chat_id)
                restored = any(
                    m.id == last.id
                    for m in self._client.list_chat_messages(chat_id)
                )
            except ClientError:
                restored = False
            if not restored:
                try:
                    self._client.append_message(chat_id, "assistant", last.content)
                    restored = True
                except ClientError:
                    restored = False
        return RegenResult(draft=draft, restored=restored)

    # ----------------------------------------------------- search

    def search(
        self, query: str, *, chat_id: str | None = None, limit: int = 20
    ) -> SearchOutcome:
        cleaned = (query or "").strip()
        if not cleaned:
            raise ClientError("write something to search for first")
        hits, document = self._client.search_chats(
            cleaned, chat_id=chat_id, limit=limit
        )
        total = document.get("total", len(hits))
        return SearchOutcome(
            hits=hits,
            query=cleaned,
            mode_used=str(document.get("mode_used", "")),
            fallback_reason=str(document.get("fallback_reason") or ""),
            total=total if isinstance(total, int) else len(hits),
        )

    # ------------------------------------ checkpoints / undo (R-07)

    def checkpoints(self, chat_id: str) -> list[CheckpointView]:
        return self._client.list_checkpoints(chat_id)

    def create_checkpoint(
        self, chat_id: str, *, name: str = ""
    ) -> CheckpointView:
        return self._client.create_checkpoint(chat_id, name=name or None)

    def restore_checkpoint(
        self, chat_id: str, checkpoint_id: str, *, name: str = ""
    ) -> ChatSummary:
        """Restore a checkpoint as a NEW chat (the source and
        everything after the checkpoint are never discarded)."""
        return self._client.restore_checkpoint(
            chat_id, checkpoint_id, name=name or None
        )

    def delete_checkpoint(self, chat_id: str, checkpoint_id: str) -> bool:
        return self._client.delete_checkpoint(chat_id, checkpoint_id)

    def undo_journal(self, chat_id: str) -> list[UndoEntryView]:
        return self._client.list_undo(chat_id)

    def undo_last(self, chat_id: str) -> dict[str, Any]:
        """Undo the chat's most recent journaled operation."""
        return self._client.undo_last(chat_id)


__all__ = [
    "ROLE_LABELS",
    "ChatFlow",
    "ContinueOutcome",
    "ImpersonateDraft",
    "OpenChat",
    "RegenResult",
    "SearchOutcome",
    "SessionView",
    "StreamDraft",
    "TurnResult",
    "export_filename",
    "message_list_label",
    "resolve_session",
    "speaker_label",
    "transcript_html",
]
