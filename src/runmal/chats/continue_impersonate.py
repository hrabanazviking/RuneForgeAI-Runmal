"""Chat continue & impersonate (P-069): nudge-generation and
user-turn drafting by the model, the mirrors' pair.

The pair, in Runmal's own terms:

- **Continue** asks the model to move the conversation forward
  from the current chat state. Two modes, one pair of hands:
  ``extend`` continues the last assistant message seamlessly
  (the generated text is a fragment, appended onto that message
  in place), and ``next`` writes the next assistant turn as a
  new message (the nudge). ``auto`` picks ``extend`` when the
  last message is the assistant's, ``next`` otherwise. Continue
  LANDS: a cleanly finished generation is stored, a failed,
  cancelled or empty one stores nothing -- the bridge
  generation contract (bridge/conversation.py).
- **Impersonate** asks the model to draft the next USER turn,
  in the voice the user's own history evidences. The result is
  a DRAFT and never lands: it is returned as a draft document
  (``status: "draft"``, ``message_id: None``), history is left
  untouched, and the text becomes a real user message only
  when the user accepts it -- verbatim or edited -- through
  :func:`accept_impersonate`. A draft the user drops is
  discarded with :func:`discard_impersonate`; nothing is ever
  stored for a draft, accepted or not.

Generation road: the prompt is the persona system prompt from
the chat character's card slots (the ``runmal.persona`` road
the bridge uses) plus the stored history in order, plus ONE
trailing system instruction that says which of the pair is
being asked for. Generation itself runs through
``generation.service.generate_events`` with the chat's backend
resolution (the chat's pinned backend profile, else the
offline fake default). HONEST BOUNDARY (Part IV gate finding
F2, carried): live generation in this tree does not route
through the prompt composer/inspector, so this slice composes
through the bridge road and claims nothing about composer
assembly. With no profile pinned the backend is the
deterministic fake and the generated text is the stub text.

Draft storage: NONE, by design, and no migration is taken.
The draft is a ``generation.modes`` IMPERSONATE candidate
before commit -- candidate state lives with the caller, the
same place GenerationSession candidates live -- and the final
text rides back on the accept call. The chat event log records
both halves of the pair as METADATA ONLY (mode, character
counts, backend, prompt fingerprint): generated text is never
written to the event log (the P-056/P-065 precedent).

Cross-user isolation: every entry resolves the chat through
the owned-chat check; a foreign or missing chat returns None
(or False for discard) and no generation runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.messages import ChatMessage
from runmal.characters.service import get_character
from runmal.chats import provenance as prov_mod
from runmal.chats.service import (
    _deck,
    _get_owned_chat,
    _preset_snapshot,
    _profile_snapshot,
    _record_event,
    _store_deck,
    append_message,
    get_history,
    message_to_dict,
)
from runmal.db.models import Chat, Message
from runmal.generation.modes import GenerationSession, Mode

EVENT_MESSAGE_CONTINUED = "message.continued"
EVENT_IMPERSONATE_DRAFTED = "impersonate.drafted"
EVENT_IMPERSONATE_ACCEPTED = "impersonate.accepted"
EVENT_IMPERSONATE_DISCARDED = "impersonate.discarded"

KIND_CONTINUE = "continue"
KIND_IMPERSONATE = "impersonate"

MODE_AUTO = "auto"
MODE_EXTEND = "extend"
MODE_NEXT = "next"
CONTINUE_MODES = frozenset({MODE_AUTO, MODE_EXTEND, MODE_NEXT})

EXTEND_INSTRUCTION = (
    "Continue the last assistant message exactly where it stops. "
    "Write only the continuation of that message: do not repeat any "
    "of its existing text, do not restart it, and do not add a new "
    "speaker, a preamble, or quotation marks."
)
NEXT_INSTRUCTION = (
    "Write the next assistant turn in this conversation. Move the "
    "conversation forward naturally -- answer, react, or raise the "
    "next beat -- staying in character. Write only the turn itself."
)
IMPERSONATE_INSTRUCTION = (
    "Write the next user turn in this conversation, as the user. "
    "Use the voice, wording habits, and concerns the user shows in "
    "their earlier messages, in the first person. Write only the "
    "user's turn itself: no quotation marks around it, no "
    "explanation, and no assistant reply."
)


class GenerationFailedError(Exception):
    """A generation that errored, was cancelled, or produced no
    text. Nothing is stored when this is raised."""


def _now() -> datetime:
    return datetime.now(UTC)


def _clean_instruction(instruction: str | None) -> str | None:
    if instruction is None:
        return None
    if not isinstance(instruction, str):
        raise ValueError("instruction must be a string")
    cleaned = instruction.strip()
    return cleaned or None


def _instruction_text(base: str, instruction: str | None) -> str:
    cleaned = _clean_instruction(instruction)
    if cleaned is None:
        return base
    return f"{base}\nAdditional instruction: {cleaned}"


def resolve_continue_mode(history: list[dict], mode: str = MODE_AUTO) -> str:
    """Resolve ``auto`` and validate an explicit continue mode.

    ``history`` is a list of ``{"role", "content"}`` dicts in
    order. An empty history raises ValueError (there is nothing
    to continue); ``extend`` requires the last message to be an
    assistant message; an unknown mode raises ValueError.
    """
    if mode not in CONTINUE_MODES:
        raise ValueError(f"unknown continue mode: {mode!r}")
    if not history:
        raise ValueError("nothing to continue: the chat has no messages")
    if mode != MODE_AUTO:
        resolved = mode
    elif history[-1].get("role") == "assistant":
        resolved = MODE_EXTEND
    else:
        resolved = MODE_NEXT
    if resolved == MODE_EXTEND and history[-1].get("role") != "assistant":
        raise ValueError(
            "extend mode continues the last assistant message, "
            "but the last message is not an assistant message"
        )
    return resolved


def _base_messages(
    history: list[dict], system_prompt: str
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    if system_prompt:
        messages.append(ChatMessage(role="system", content=system_prompt))
    messages.extend(
        ChatMessage(role=m["role"], content=m["content"]) for m in history
    )
    return messages


def build_continue_messages(
    history: list[dict],
    system_prompt: str = "",
    mode: str = MODE_AUTO,
    instruction: str | None = None,
) -> tuple[list[ChatMessage], str]:
    """The generation prompt for a continue, and its resolved mode.

    Persona system prompt first (when any), then the stored
    history in order, then exactly one trailing system
    instruction -- the extend or the next text, plus the
    caller's own instruction when one was given.
    """
    resolved = resolve_continue_mode(history, mode)
    base = EXTEND_INSTRUCTION if resolved == MODE_EXTEND else NEXT_INSTRUCTION
    messages = _base_messages(history, system_prompt)
    messages.append(
        ChatMessage(role="system", content=_instruction_text(base, instruction))
    )
    return messages, resolved


def build_impersonate_messages(
    history: list[dict],
    system_prompt: str = "",
    instruction: str | None = None,
) -> list[ChatMessage]:
    """The generation prompt for an impersonate draft.

    Same road as continue -- persona prompt, history, one
    trailing system instruction -- with the impersonate
    instruction: write the next USER turn, as the user. An
    empty history raises ValueError: there is no history to
    draft from.
    """
    if not history:
        raise ValueError("nothing to impersonate from: the chat has no messages")
    messages = _base_messages(history, system_prompt)
    messages.append(
        ChatMessage(
            role="system",
            content=_instruction_text(IMPERSONATE_INSTRUCTION, instruction),
        )
    )
    return messages


def _persona_system_prompt(character) -> str:
    """The persona's system prompt from its card slots (S110
    manifest) -- the same road bridge/conversation.py walks."""
    from runmal.cards import CardParseError, parse_json_card
    from runmal.persona import build_slot_manifest, render_system_prompt

    try:
        card = parse_json_card(character.card_json.encode("utf-8"))
    except CardParseError:
        return ""
    return render_system_prompt(build_slot_manifest(card))


async def _chat_system_prompt(
    session: AsyncSession, user_id: str, chat: Chat
) -> str:
    if not chat.character_id:
        return ""
    character = await get_character(session, user_id, chat.character_id)
    if character is None:
        return ""
    return _persona_system_prompt(character)


async def _character_snapshot(
    session: AsyncSession, user_id: str, chat: Chat
) -> tuple[str | None, str | None]:
    if not chat.character_id:
        return None, None
    character = await get_character(session, user_id, chat.character_id)
    if character is None:
        return None, None
    return character.id, character.name


async def _generation_record(session, user_id, chat, backend, *,
                             origin_kind, origin=None, generation=None,
                             lore=None, speaker=None):
    """A P-075 record for a continue/impersonate landing: the
    model facts come from the backend object that actually
    generated, the preset/profile are chat snapshots, and lore
    is not_run — this road composes persona + history only and
    never runs lore activation (the P-069 boundary)."""
    backend_key, model_id = prov_mod.backend_model_fields(backend)
    profile_id, profile_name = await _profile_snapshot(session, user_id, chat)
    return prov_mod.build_record(
        origin_kind=origin_kind, origin=origin,
        model=prov_mod.model_section(
            backend_key=backend_key, model_id=model_id,
            backend_profile_id=profile_id,
            backend_profile_name=profile_name),
        preset=await _preset_snapshot(session, user_id, chat),
        lore=lore if lore is not None else prov_mod.lore_section(
            status="not_run",
            reason="continue/impersonate composes persona + history "
                   "only; lore activation is not run on this road"),
        generation=generation, speaker=speaker)


async def resolve_backend(session: AsyncSession, user_id: str, chat: Chat):
    """Same resolution as the local /generate route and the
    bridge: the chat's pinned backend profile when set and
    resolvable, else the offline fake default."""
    from runmal.backends import profiles as backend_profiles
    from runmal.generation import service as generation_service

    if chat.backend_profile_id:
        profile = await backend_profiles.get_profile(
            session, user_id, chat.backend_profile_id
        )
        if profile is not None:
            return await backend_profiles.build_chat_backend(session, profile)
    return generation_service.default_backend()


async def _generate_text(backend, messages: list[ChatMessage]) -> str:
    """Collect one generation's text through the generation
    service. Error, cancellation, or empty output raises
    GenerationFailedError -- the caller stores nothing."""
    from runmal.generation import service as generation_service

    parts: list[str] = []
    finish: str | None = None
    error_code: str | None = None
    async for event in generation_service.generate_events(
        generation_service.new_request_id(), messages=messages, backend=backend
    ):
        kind = event.get("type")
        if kind == "token":
            parts.append(event["text"])
        elif kind == "error":
            error_code = event.get("code") or "backend_error"
        elif kind == "done":
            finish = event.get("finish_reason")
    text = "".join(parts)
    if error_code is not None:
        raise GenerationFailedError(f"generation failed: {error_code}")
    if finish in (None, "cancelled", "error"):
        raise GenerationFailedError(f"generation did not finish cleanly: {finish}")
    if not text or not text.strip():
        raise GenerationFailedError("generation produced no text")
    return text


def _run_session(mode: Mode, messages: list[ChatMessage], text: str) -> GenerationSession:
    """Walk a GenerationSession to CANDIDATE_READY over the
    composed prompt: the modes.py lifecycle both halves of the
    pair are expressed in."""
    gen = GenerationSession(mode=mode)
    gen.compose([m.to_dict() for m in messages])
    gen.begin()
    gen.complete(text)
    return gen


async def continue_chat(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    mode: str = MODE_AUTO,
    instruction: str | None = None,
    backend=None,
) -> dict | None:
    """Continue a chat (P-069) and LAND the result.

    ``extend`` appends the generated fragment onto the last
    assistant message in place (swipe-deck aware: the active
    alternate grows, so ``content == swipes[swipe_id]`` keeps
    holding); ``next`` appends the generated text as a NEW
    assistant message carrying the chat character's speaker
    snapshot. Returns the landing document, or None when the
    chat is missing or foreign. Invalid mode/instruction and
    an empty chat raise ValueError; a failed generation raises
    GenerationFailedError and stores nothing.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    history = await get_history(session, user_id, chat_id) or []
    hist = [{"role": m.role, "content": m.content} for m in history]
    system_prompt = await _chat_system_prompt(session, user_id, chat)
    messages, resolved = build_continue_messages(hist, system_prompt, mode, instruction)
    backend = backend or await resolve_backend(session, user_id, chat)
    text = await _generate_text(backend, messages)
    gen = _run_session(Mode.NORMAL, messages, text)
    role, committed_text = gen.commit()
    assert role == "assistant" and committed_text == text
    if resolved == MODE_EXTEND:
        message = history[-1]
        deck, idx = _deck(message)
        new_deck = list(deck)
        new_deck[idx] = deck[idx] + text
        _store_deck(message, new_deck, idx)
        backend_key, model_id = prov_mod.backend_model_fields(backend)
        message.provenance_json = prov_mod.dump_document(
            prov_mod.with_amendment(
                getattr(message, "provenance_json", None), idx,
                {"kind": "continuation", "mode": resolved,
                 "backend_key": backend_key, "model_id": model_id,
                 "fingerprint": gen.fingerprint}))
        message.updated_at = _now()
        await _record_event(
            session,
            chat_id,
            EVENT_MESSAGE_CONTINUED,
            message_id=message.id,
            data={"mode": resolved, "chars": len(text), "backend": backend.backend_key},
        )
        await session.commit()
        continuation_of = message.id
    else:
        speaker_id, speaker_name = await _character_snapshot(session, user_id, chat)
        record = await _generation_record(
            session, user_id, chat, backend,
            origin_kind="continue", origin={"mode": resolved},
            generation={"fingerprint": gen.fingerprint, "mode": resolved},
            speaker={"speaker_id": speaker_id, "speaker_name": speaker_name})
        message = await append_message(
            session,
            user_id,
            chat_id,
            "assistant",
            text,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            event_data={"source": KIND_CONTINUE, "mode": resolved},
            provenance=record,
        )
        await _record_event(
            session,
            chat_id,
            EVENT_MESSAGE_CONTINUED,
            message_id=message.id,
            data={"mode": resolved, "chars": len(text), "backend": backend.backend_key},
        )
        await session.commit()
        continuation_of = None
    return {
        "chat_id": chat_id,
        "kind": KIND_CONTINUE,
        "mode": resolved,
        "content": text,
        "backend": backend.backend_key,
        "fingerprint": gen.fingerprint,
        "generation_state": gen.state.value,
        "continuation_of": continuation_of,
        "message": message_to_dict(message),
    }


async def impersonate_draft(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    instruction: str | None = None,
    backend=None,
) -> dict | None:
    """Draft the next user turn (P-069). NEVER lands.

    Returns the draft document -- visibly a draft: ``status``
    is ``"draft"``, ``draft`` is True, ``message_id`` is None --
    or None when the chat is missing or foreign. History is
    not mutated; the only trace is the metadata-only
    ``impersonate.drafted`` event. An empty chat raises
    ValueError; a failed generation raises
    GenerationFailedError and records nothing.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    history = await get_history(session, user_id, chat_id) or []
    hist = [{"role": m.role, "content": m.content} for m in history]
    system_prompt = await _chat_system_prompt(session, user_id, chat)
    messages = build_impersonate_messages(hist, system_prompt, instruction)
    backend = backend or await resolve_backend(session, user_id, chat)
    text = await _generate_text(backend, messages)
    gen = _run_session(Mode.IMPERSONATE, messages, text)
    await _record_event(
        session,
        chat_id,
        EVENT_IMPERSONATE_DRAFTED,
        data={
            "chars": len(text),
            "backend": backend.backend_key,
            "fingerprint": gen.fingerprint,
        },
    )
    await session.commit()
    return {
        "id": uuid.uuid4().hex,
        "chat_id": chat_id,
        "kind": KIND_IMPERSONATE,
        "status": "draft",
        "draft": True,
        "role": "user",
        "content": text,
        "message_id": None,
        "based_on_message_id": history[-1].id,
        "backend": backend.backend_key,
        "fingerprint": gen.fingerprint,
        "generation_state": gen.state.value,
    }


async def accept_impersonate(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    content: str,
    *,
    draft_id: str | None = None,
) -> Message | None:
    """Accept an impersonate draft: append its final text --
    verbatim or user-edited -- as a real user message.

    This is the ONLY road by which impersonated text becomes a
    message, and the user always supplies the text that lands.
    Returns the stored message, or None when the chat is
    missing or foreign. Empty content raises ValueError.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if not content or not content.strip():
        raise ValueError("message content must not be empty")
    record = prov_mod.build_record(
        origin_kind="impersonate_accepted",
        origin={"draft_id": draft_id},
        model=prov_mod.model_section(status="unknown"),
        preset=await _preset_snapshot(session, user_id, chat),
        lore=prov_mod.lore_section(status="not_applicable"))
    message = await append_message(
        session,
        user_id,
        chat_id,
        "user",
        content,
        event_data={"source": KIND_IMPERSONATE},
        provenance=record,
    )
    data = {"draft_id": draft_id} if draft_id else {}
    await _record_event(
        session,
        chat_id,
        EVENT_IMPERSONATE_ACCEPTED,
        message_id=message.id,
        data=data,
    )
    await session.commit()
    return message


async def discard_impersonate(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    draft_id: str | None = None,
) -> bool:
    """Discard an impersonate draft: records the metadata-only
    ``impersonate.discarded`` event and stores nothing -- there
    is nothing to delete, because a draft was never stored.
    Returns False when the chat is missing or foreign."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return False
    data = {"draft_id": draft_id} if draft_id else {}
    await _record_event(session, chat_id, EVENT_IMPERSONATE_DISCARDED, data=data)
    await session.commit()
    return True
