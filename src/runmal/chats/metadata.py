"""Chat metadata (P-073): titles, tags, summaries — auto-generated
and editable — plus the chat library view at scale.

Auto-generation is DETERMINISTIC and EXTRACTIVE (generator id
``extractive-v1``): titles, summaries and tags are derived from
the chat's own messages with plain string work. No model is
called, no backend is consulted, and the stored provenance says
exactly that. A field the owner edits by hand is marked
``manual`` and regeneration never overwrites it unless the
caller explicitly forces that field.

Storage (PROVISIONAL 0039): the summary and the provenance
document live on the chat row (``chats.summary`` /
``chats.metadata_json``); tags are normalised rows in
``chat_tags`` and the favourite flag a row in
``chat_organisation`` — the P-024 character-library pattern,
because a library view must filter and count tags in SQL.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import (
    Character,
    Chat,
    ChatEvent,
    ChatOrganisation,
    ChatTag,
    Message,
)
from runmal.library.organise import normalise_tag

__all__ = [
    "GENERATOR_ID",
    "MAX_SUMMARY_LEN",
    "MAX_TAGS_PER_CHAT",
    "MAX_TITLE_LEN",
    "SOURCE_AUTO",
    "SOURCE_MANUAL",
    "SOURCE_UNSET",
    "generate_summary",
    "generate_tags",
    "generate_title",
    "get_metadata",
    "list_chat_library",
    "list_chat_tags",
    "metadata_to_dict",
    "normalise_chat_tags",
    "provenance_from_chat",
    "regenerate_metadata",
    "set_favourite",
    "update_metadata",
]

GENERATOR_ID = "extractive-v1"
SOURCE_MANUAL = "manual"
SOURCE_AUTO = "auto"
SOURCE_UNSET = "unset"

MAX_TITLE_LEN = 200
MAX_SUMMARY_LEN = 2000
MAX_TAGS_PER_CHAT = 50
TITLE_AUTO_MAX = 60
SUMMARY_AUTO_MAX = 280
MAX_AUTO_TAGS = 5
MIN_TAG_TOKEN_LEN = 4

EVENT_METADATA_UPDATED = "chat.metadata_updated"
EVENT_METADATA_GENERATED = "chat.metadata_generated"
EVENT_FAVOURITE_CHANGED = "chat.favourite_changed"
EVENT_CHAT_RENAMED = "chat.renamed"

_FIELDS = ("title", "summary", "tags")

_STOPWORDS = frozenset(
    """
    about above after again against being below between could every
    first found going great have having hello just know like little
    long look made make many more most much must never night now
    once only other over really right said say see she should some
    still such take tell than thank that the their them then there
    these they thing think this those through time today together
    under until upon very want way well went were what when where
    which while who will with would you your yours and are but for
    from had has her him his its not our out own per she the too was
    """.split()
)

_SENTENCE_RE = re.compile(r"[^.!?…]+(?:[.!?…]+|$)")


def _now() -> datetime:
    return datetime.now(UTC)


def _collapse(text) -> str:
    return " ".join(str(text or "").split())


def _trim_words(text: str, max_chars: int) -> str:
    """Collapse whitespace; if over max_chars, cut at a word
    boundary and mark the cut with an ellipsis."""
    text = _collapse(text)
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (cut or text[: max_chars - 1].rstrip()) + "…"


def _tokens(text: str) -> list[str]:
    folded = str(text or "").casefold()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in folded)
    return cleaned.split()


def _sentences(text: str) -> list[str]:
    out = []
    for match in _SENTENCE_RE.findall(str(text or "")):
        sentence = _collapse(match)
        if sentence:
            out.append(sentence)
    return out


def _message_texts(messages) -> list[tuple[str, str]]:
    """(role, collapsed content) pairs, blanks dropped."""
    out = []
    for message in messages or []:
        if isinstance(message, dict):
            role, content = message.get("role", ""), message.get("content", "")
        else:
            role = getattr(message, "role", "")
            content = getattr(message, "content", "")
        text = _collapse(content)
        if text:
            out.append((str(role or ""), text))
    return out


# -- Pure generation (no I/O, deterministic) ---------------------------


def generate_title(messages, character_name: str | None = None) -> str:
    """An extractive title: the first user message, trimmed.

    Falls back to the first assistant message, then to the
    character's name, then to a plain placeholder. Never invents
    words that are not in the chat (the character name and the
    placeholder are labels, not generated prose).
    """
    texts = _message_texts(messages)
    for wanted in ("user", "assistant"):
        for role, text in texts:
            if role == wanted:
                return _trim_words(text, TITLE_AUTO_MAX)
    for _role, text in texts:
        return _trim_words(text, TITLE_AUTO_MAX)
    name = _collapse(character_name or "")
    if name:
        return f"Chat with {name}"[:MAX_TITLE_LEN]
    return "Untitled chat"


def generate_summary(messages, max_chars: int = SUMMARY_AUTO_MAX) -> str:
    """An extractive summary: the opening sentence plus the
    highest-scoring later sentence, capped at max_chars.

    Sentences are scored by the summed frequency of their content
    tokens across the whole chat (ties keep the earlier sentence),
    so the pick is deterministic. An empty chat summarises to "".
    """
    texts = _message_texts(messages)
    sentences: list[str] = []
    for _role, text in texts:
        sentences.extend(_sentences(text))
    if not sentences:
        return ""
    if len(sentences) == 1:
        return _trim_words(sentences[0], max_chars)
    freq: dict[str, int] = {}
    for _role, text in texts:
        for token in _tokens(text):
            if len(token) >= 3 and token not in _STOPWORDS:
                freq[token] = freq.get(token, 0) + 1

    def score(sentence: str) -> int:
        return sum(
            freq.get(token, 0)
            for token in set(_tokens(sentence))
            if len(token) >= 3 and token not in _STOPWORDS
        )

    best_index, best_score = 0, -1
    for index in range(1, len(sentences)):
        value = score(sentences[index])
        if value > best_score:
            best_index, best_score = index, value
    picked = [sentences[0]]
    if best_index != 0:
        picked.append(sentences[best_index])
    return _trim_words(" ".join(picked), max_chars)


def generate_tags(messages, limit: int = MAX_AUTO_TAGS) -> list[str]:
    """Frequency-ranked content tokens as tags.

    Tokens are casefolded words of at least MIN_TAG_TOKEN_LEN
    characters, stopwords removed, ranked by frequency then
    alphabetically. Fewer than two distinct candidates yields []
    — one repeated word is not a tag set.
    """
    freq: dict[str, int] = {}
    for _role, text in _message_texts(messages):
        for token in _tokens(text):
            if len(token) < MIN_TAG_TOKEN_LEN or token in _STOPWORDS:
                continue
            if token.isdigit():
                continue
            freq[token] = freq.get(token, 0) + 1
    ranked = sorted(freq.items(), key=lambda item: (-item[1], item[0]))
    if len(ranked) < 2:
        return []
    tags = []
    for token, _count in ranked[: max(0, limit)]:
        try:
            display, _key = normalise_tag(token)
        except ValueError:
            continue
        tags.append(display)
    return tags


# -- Validation ----------------------------------------------------------


def validate_title(raw) -> str:
    if not isinstance(raw, str):
        raise ValueError("title must be a string")
    title = _collapse(raw)
    if not title:
        raise ValueError("title must not be empty")
    if len(title) > MAX_TITLE_LEN:
        raise ValueError(f"title exceeds {MAX_TITLE_LEN} characters")
    if any(unicodedata.category(ch) == "Cc" for ch in title):
        raise ValueError("title contains control characters")
    return title


def validate_summary(raw) -> str:
    if not isinstance(raw, str):
        raise ValueError("summary must be a string")
    summary = str(raw).strip()
    if len(summary) > MAX_SUMMARY_LEN:
        raise ValueError(f"summary exceeds {MAX_SUMMARY_LEN} characters")
    return summary


def normalise_chat_tags(raw_list) -> list[tuple[str, str]]:
    """(display, key) pairs via the P-024 tag normaliser, deduped
    by key (first display wins), capped for chats."""
    if not isinstance(raw_list, list):
        raise ValueError("tags must be a list of strings")
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw_list:
        display, key = normalise_tag(item)
        if key in seen:
            continue
        seen.add(key)
        pairs.append((display, key))
    if len(pairs) > MAX_TAGS_PER_CHAT:
        raise ValueError(f"at most {MAX_TAGS_PER_CHAT} tags per chat")
    return pairs


# -- Provenance ----------------------------------------------------------


def _empty_provenance() -> dict:
    return {
        "title_source": SOURCE_UNSET,
        "summary_source": SOURCE_UNSET,
        "tags_source": SOURCE_UNSET,
        "generator": None,
        "generated_at": None,
        "generated_from": None,
    }


def provenance_from_chat(chat: Chat) -> dict:
    """The chat's provenance document, normalised.

    Corrupt or missing JSON reads as the empty provenance (the
    house pattern for per-chat JSON documents).
    """
    prov = _empty_provenance()
    try:
        raw = getattr(chat, "metadata_json", None)
        parsed = json.loads(raw) if raw else None
    except (json.JSONDecodeError, TypeError, AttributeError):
        parsed = None
    if isinstance(parsed, dict):
        for field in _FIELDS:
            value = parsed.get(f"{field}_source")
            if value in (SOURCE_MANUAL, SOURCE_AUTO, SOURCE_UNSET):
                prov[f"{field}_source"] = value
        if isinstance(parsed.get("generator"), str):
            prov["generator"] = parsed["generator"]
        if isinstance(parsed.get("generated_at"), str):
            prov["generated_at"] = parsed["generated_at"]
        if isinstance(parsed.get("generated_from"), int):
            prov["generated_from"] = parsed["generated_from"]
    # A pre-existing title/summary with no recorded source predates
    # this slice; report it honestly as unset rather than guessing.
    return prov


def _store_provenance(chat: Chat, prov: dict) -> None:
    chat.metadata_json = json.dumps(prov)


def metadata_to_dict(
    chat: Chat,
    tags: list[str] | None = None,
    is_favourite: bool = False,
    message_count: int = 0,
) -> dict:
    return {
        "chat_id": chat.id,
        "title": chat.title,
        "summary": getattr(chat, "summary", "") or "",
        "tags": list(tags or []),
        "is_favourite": bool(is_favourite),
        "message_count": int(message_count),
        "character_id": chat.character_id,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "metadata": provenance_from_chat(chat),
    }


# -- Service helpers ------------------------------------------------------


async def _record_event(
    session: AsyncSession,
    chat_id: str,
    kind: str,
    data: dict | None = None,
) -> None:
    session.add(
        ChatEvent(chat_id=chat_id, kind=kind, data=json.dumps(data or {}))
    )
    await session.flush()


async def _get_owned_chat(
    session: AsyncSession, user_id: str, chat_id: str
) -> Chat | None:
    result = await session.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _tags_for(session: AsyncSession, chat_id: str) -> list[str]:
    result = await session.execute(
        select(ChatTag.tag)
        .where(ChatTag.chat_id == chat_id)
        .order_by(ChatTag.tag_key)
    )
    return list(result.scalars().all())


async def _org_for(session: AsyncSession, chat_id: str) -> ChatOrganisation | None:
    result = await session.execute(
        select(ChatOrganisation).where(ChatOrganisation.chat_id == chat_id)
    )
    return result.scalar_one_or_none()


async def _is_favourite(session: AsyncSession, chat_id: str) -> bool:
    org = await _org_for(session, chat_id)
    return bool(org.is_favourite) if org is not None else False


async def _message_count(session: AsyncSession, chat_id: str) -> int:
    result = await session.execute(
        select(func.count(Message.id)).where(Message.chat_id == chat_id)
    )
    return int(result.scalar_one())


async def _ordered_messages(session: AsyncSession, chat_id: str) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(
            Message.position.is_(None),
            Message.position,
            Message.created_at,
            Message.id,
        )
    )
    return list(result.scalars().all())


async def _replace_tags(
    session: AsyncSession, chat: Chat, pairs: list[tuple[str, str]]
) -> None:
    await session.execute(delete(ChatTag).where(ChatTag.chat_id == chat.id))
    for display, key in pairs:
        session.add(
            ChatTag(chat_id=chat.id, user_id=chat.user_id, tag=display, tag_key=key)
        )
    await session.flush()


async def _full_dict(session: AsyncSession, chat: Chat) -> dict:
    return metadata_to_dict(
        chat,
        tags=await _tags_for(session, chat.id),
        is_favourite=await _is_favourite(session, chat.id),
        message_count=await _message_count(session, chat.id),
    )


# -- Service ---------------------------------------------------------------


async def get_metadata(
    session: AsyncSession, user_id: str, chat_id: str
) -> dict | None:
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    return await _full_dict(session, chat)


async def update_metadata(
    session: AsyncSession, user_id: str, chat_id: str, updates: dict
) -> dict | None:
    """Apply a partial manual edit. Keys present in ``updates``
    (title / summary / tags) are edited and marked manual;
    absent keys are untouched. Raises ValueError on bad input."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if not isinstance(updates, dict):
        raise ValueError("metadata update must be an object")
    unknown = sorted(set(updates) - set(_FIELDS))
    if unknown:
        raise ValueError(f"unknown metadata fields: {', '.join(unknown)}")
    prov = provenance_from_chat(chat)
    changed: list[str] = []
    if "title" in updates:
        title = validate_title(updates["title"])
        if title != chat.title:
            chat.title = title
            await _record_event(session, chat.id, EVENT_CHAT_RENAMED, data={"title": title})
        prov["title_source"] = SOURCE_MANUAL
        changed.append("title")
    if "summary" in updates:
        chat.summary = validate_summary(updates["summary"])
        prov["summary_source"] = SOURCE_MANUAL
        changed.append("summary")
    if "tags" in updates:
        pairs = normalise_chat_tags(updates["tags"])
        await _replace_tags(session, chat, pairs)
        prov["tags_source"] = SOURCE_MANUAL
        changed.append("tags")
    if changed:
        _store_provenance(chat, prov)
        await _record_event(
            session, chat.id, EVENT_METADATA_UPDATED, data={"fields": changed}
        )
        await session.commit()
    return await _full_dict(session, chat)


async def regenerate_metadata(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    fields: list[str] | None = None,
    force: bool = False,
) -> dict | None:
    """(Re)generate the requested fields extractively.

    A field whose source is manual is skipped unless ``force``.
    The result dict gains ``generated`` and ``skipped`` lists so
    the caller can see exactly what happened.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    wanted = list(fields) if fields else list(_FIELDS)
    unknown = sorted(set(wanted) - set(_FIELDS))
    if unknown:
        raise ValueError(f"unknown metadata fields: {', '.join(unknown)}")
    messages = await _ordered_messages(session, chat_id)
    character_name = None
    if chat.character_id:
        result = await session.execute(
            select(Character).where(Character.id == chat.character_id)
        )
        character = result.scalar_one_or_none()
        if character is not None:
            character_name = character.name
    prov = provenance_from_chat(chat)
    generated: list[str] = []
    skipped: list[str] = []
    for field in wanted:
        if prov[f"{field}_source"] == SOURCE_MANUAL and not force:
            skipped.append(field)
            continue
        if field == "title":
            chat.title = generate_title(messages, character_name)
        elif field == "summary":
            chat.summary = generate_summary(messages)
        elif field == "tags":
            pairs = normalise_chat_tags(generate_tags(messages))
            await _replace_tags(session, chat, pairs)
        prov[f"{field}_source"] = SOURCE_AUTO
        generated.append(field)
    if generated:
        prov["generator"] = GENERATOR_ID
        prov["generated_at"] = _now().isoformat()
        prov["generated_from"] = len(messages)
        _store_provenance(chat, prov)
        await _record_event(
            session,
            chat.id,
            EVENT_METADATA_GENERATED,
            data={
                "fields": generated,
                "skipped": skipped,
                "generator": GENERATOR_ID,
                "message_count": len(messages),
            },
        )
        await session.commit()
    out = await _full_dict(session, chat)
    out["generated"] = generated
    out["skipped"] = skipped
    return out


async def set_favourite(
    session: AsyncSession, user_id: str, chat_id: str, is_favourite: bool
) -> dict | None:
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    org = await _org_for(session, chat_id)
    if org is None:
        org = ChatOrganisation(
            chat_id=chat.id, user_id=user_id, is_favourite=False
        )
        session.add(org)
    org.is_favourite = bool(is_favourite)
    org.updated_at = _now()
    await session.flush()
    await _record_event(
        session,
        chat.id,
        EVENT_FAVOURITE_CHANGED,
        data={"is_favourite": bool(is_favourite)},
    )
    await session.commit()
    return await _full_dict(session, chat)


# -- The library view at scale --------------------------------------------


def _like_pattern(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


async def list_chat_library(
    session: AsyncSession,
    user_id: str,
    *,
    q=None,
    tags=None,
    tag_mode: str = "any",
    favourites_only: bool = False,
    character_id: str | None = None,
    sort: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """A filtered, sorted, paginated page of the user's chats.

    Returns ``{"total": int, "items": [...]}`` where total counts
    every chat matching the filters, not just the page. ``q``
    matches title, summary, and tag text. Sorts: recent (last
    message activity, falling back to creation), newest, oldest,
    title, title_desc, favourites_first. Unknown sorts fall back
    to recent.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(200, limit))
    offset = max(0, offset)

    conditions = [Chat.user_id == user_id]
    if character_id:
        conditions.append(Chat.character_id == character_id)
    if favourites_only:
        conditions.append(ChatOrganisation.is_favourite == True)  # noqa: E712
    if tags:
        keys: list[str] = []
        seen_keys: set[str] = set()
        for raw in tags:
            _display, key = normalise_tag(raw)
            if key not in seen_keys:
                seen_keys.add(key)
                keys.append(key)
        if keys:
            if tag_mode == "all":
                tag_subquery = (
                    select(ChatTag.chat_id)
                    .where(ChatTag.user_id == user_id, ChatTag.tag_key.in_(keys))
                    .group_by(ChatTag.chat_id)
                    .having(func.count(func.distinct(ChatTag.tag_key)) == len(keys))
                )
            else:
                tag_subquery = select(ChatTag.chat_id).where(
                    ChatTag.user_id == user_id, ChatTag.tag_key.in_(keys)
                )
            conditions.append(Chat.id.in_(tag_subquery))
    if q is not None and str(q).strip():
        pattern = _like_pattern(str(q).strip().casefold())
        tag_q_subquery = select(ChatTag.chat_id).where(
            ChatTag.user_id == user_id,
            or_(
                func.lower(ChatTag.tag).like(pattern, escape="\\"),
                ChatTag.tag_key.like(pattern, escape="\\"),
            ),
        )
        conditions.append(
            or_(
                func.lower(Chat.title).like(pattern, escape="\\"),
                func.lower(Chat.summary).like(pattern, escape="\\"),
                Chat.id.in_(tag_q_subquery),
            )
        )

    count_result = await session.execute(
        select(func.count(Chat.id))
        .select_from(Chat)
        .outerjoin(ChatOrganisation, ChatOrganisation.chat_id == Chat.id)
        .where(*conditions)
    )
    total = int(count_result.scalar_one())

    last_activity = (
        select(func.max(Message.created_at))
        .where(Message.chat_id == Chat.id)
        .correlate(Chat)
        .scalar_subquery()
    )
    message_count = (
        select(func.count(Message.id))
        .where(Message.chat_id == Chat.id)
        .correlate(Chat)
        .scalar_subquery()
    )
    activity = func.coalesce(last_activity, Chat.created_at)
    if sort == "newest":
        order_by = [Chat.created_at.desc(), Chat.id]
    elif sort == "oldest":
        order_by = [Chat.created_at, Chat.id]
    elif sort == "title":
        order_by = [func.lower(Chat.title), Chat.created_at.desc()]
    elif sort == "title_desc":
        order_by = [func.lower(Chat.title).desc(), Chat.created_at.desc()]
    elif sort == "favourites_first":
        order_by = [
            func.coalesce(ChatOrganisation.is_favourite, False).desc(),
            activity.desc(),
            Chat.id,
        ]
    else:  # "recent" and any unknown value
        order_by = [activity.desc(), Chat.id]

    result = await session.execute(
        select(Chat, ChatOrganisation, message_count, last_activity)
        .outerjoin(ChatOrganisation, ChatOrganisation.chat_id == Chat.id)
        .where(*conditions)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()

    tags_by_id: dict[str, list[str]] = {chat.id: [] for chat, _o, _c, _a in rows}
    if tags_by_id:
        tag_result = await session.execute(
            select(ChatTag.chat_id, ChatTag.tag)
            .where(ChatTag.chat_id.in_(list(tags_by_id)))
            .order_by(ChatTag.tag_key)
        )
        for chat_id, tag in tag_result.all():
            tags_by_id.setdefault(chat_id, []).append(tag)

    items = []
    for chat, org, count, last in rows:
        item = metadata_to_dict(
            chat,
            tags=tags_by_id.get(chat.id, []),
            is_favourite=bool(org.is_favourite) if org is not None else False,
            message_count=int(count or 0),
        )
        item["last_activity"] = (
            last.isoformat() if hasattr(last, "isoformat") else (str(last) if last else None)
        ) or item["created_at"]
        items.append(item)
    return {"total": total, "items": items}


async def list_chat_tags(session: AsyncSession, user_id: str) -> list[dict]:
    """Every tag on the user's chats with its chat count.

    Display form is the minimum stored tag per key (deterministic);
    sorted by count descending, then key ascending.
    """
    result = await session.execute(
        select(ChatTag.tag_key, func.min(ChatTag.tag), func.count())
        .where(ChatTag.user_id == user_id)
        .group_by(ChatTag.tag_key)
        .order_by(func.count().desc(), ChatTag.tag_key)
    )
    return [
        {"tag": tag, "tag_key": tag_key, "count": int(count)}
        for tag_key, tag, count in result.all()
    ]
