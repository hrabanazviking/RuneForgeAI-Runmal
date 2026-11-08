"""Live materialisation of imported chats (P-078).

P-020's file layer parses ST-shaped JSONL and Runmal native
exports into the typed ImportedChat contract -- as DATA. This
module is the surgery that makes those imports LIVE: it writes
an ImportedChat into ordinary Chat/Message rows in one
transaction, preserving swipe decks where the source format
carried them, and reports honestly -- per chat -- what was
preserved, what was absent, and what was unmappable. It never
invents swipes, branches, speakers, or dates the file did not
carry, and no message text ever appears in the report or in
events (counts and source indices only).

Branch honesty: the ST shape carries branch structure only as
header chat_metadata link keys (filemodels.BRANCH_LINK_KEYS)
naming ids of the SOURCE system. Those are not Runmal chat ids
and no mapping exists, so live lineage columns are never
fabricated: the imported chat is a root chat, the declared
linkage is preserved verbatim in the report as data, and the
chat can fork/merge/checkpoint natively from then on.

Clean-room basis: Runmal's own P-020 contract, P-065 decks,
P-066 lineage, P-075 provenance. No mirror source was read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import provenance as prov_mod
from runmal.chats.filemodels import ImportedChat, ImportResult
from runmal.db.models import Chat, Message

EVENT_CHAT_IMPORTED = "chat.imported"

__all__ = [
    "EVENT_CHAT_IMPORTED",
    "LiveImportReport",
    "MessagePlan",
    "import_chat_file",
    "materialise_import",
    "plan_import",
]


@dataclass
class MessagePlan:
    source_index: int
    role: str
    content: str
    speaker_name: str
    deck: list[str]
    swipe_id: int
    has_explicit_swipes: bool
    created_at: datetime | None


@dataclass
class LiveImportReport:
    """Honest per-chat account of a live materialisation.

    Counts and source indices only -- never message text.
    """

    source_shape: str = ""
    messages_imported: int = 0
    messages_with_swipes: int = 0
    swipe_alternates_preserved: int = 0
    messages_without_swipes: int = 0
    empty_content_refused: list[int] = field(default_factory=list)
    empty_alternates_dropped: list[int] = field(default_factory=list)
    mes_mismatch_repaired: list[int] = field(default_factory=list)
    displaced_alternates: dict[int, int] = field(default_factory=dict)
    swipe_info_unmappable: int = 0
    extra_keys_unmappable: dict[int, list[str]] = field(default_factory=dict)
    send_date_unmappable: int = 0
    declared_branch_link: dict = field(default_factory=dict)
    branch_link_mapped_to_lineage: bool = False
    character_name_carried: str = ""
    character_linked: bool = False
    parse_refused_lines: int = 0
    parse_repaired_lines: int = 0
    plans: list[MessagePlan] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "source_shape": self.source_shape,
            "messages_imported": self.messages_imported,
            "messages_with_swipes": self.messages_with_swipes,
            "swipe_alternates_preserved": self.swipe_alternates_preserved,
            "messages_without_swipes": self.messages_without_swipes,
            "empty_content_refused": list(self.empty_content_refused),
            "empty_alternates_dropped": list(self.empty_alternates_dropped),
            "mes_mismatch_repaired": list(self.mes_mismatch_repaired),
            "displaced_alternates": {
                str(k): v for k, v in self.displaced_alternates.items()
            },
            "branch_link_absent": not self.declared_branch_link,
            "swipe_info_unmappable": self.swipe_info_unmappable,
            "extra_keys_unmappable": {
                str(k): list(v) for k, v in self.extra_keys_unmappable.items()
            },
            "send_date_unmappable": self.send_date_unmappable,
            "declared_branch_link": dict(self.declared_branch_link),
            "branch_link_mapped_to_lineage": self.branch_link_mapped_to_lineage,
            "character_name_carried": self.character_name_carried,
            "character_linked": self.character_linked,
            "parse_refused_lines": self.parse_refused_lines,
            "parse_repaired_lines": self.parse_repaired_lines,
        }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def plan_import(chat: ImportedChat) -> LiveImportReport:
    """Resolve an ImportedChat into live message plans (pure).

    Deck law (P-065): every stored alternate is a non-empty
    string and content == deck[swipe_id]. `mes` is authoritative
    (filebridge law) when it disagrees with the active swipe.
    """
    report = LiveImportReport(source_shape=chat.source_shape)
    report.declared_branch_link = chat.branch_link
    report.character_name_carried = chat.character_name
    for index, message in enumerate(chat.messages):
        # Unmappable-metadata accounting runs for EVERY message,
        # refused ones included: a refused message's swipe_info,
        # extra keys and unparsed date are still facts about the
        # source file the report must not silently drop.
        if message.has_swipe_info and message.swipe_info:
            report.swipe_info_unmappable += 1
        if message.extra:
            report.extra_keys_unmappable[index] = sorted(
                str(k) for k in message.extra)
        if message.send_date_parsed is None and (
            message.send_date_raw is not None
            or "send_date" in message.raw
            or "created_at" in message.raw
        ):
            # The native shape carries the date as `created_at`;
            # an unparsed carried date is reported, never faked.
            report.send_date_unmappable += 1
        if not message.content:
            # The live append road refuses empty content; a live
            # message cannot be empty. Never invent text.
            report.empty_content_refused.append(index)
            continue
        if not message.has_explicit_swipes:
            deck, swipe_id = [message.content], 0
            report.messages_without_swipes += 1
        else:
            raw_deck = list(message.swipes) or [message.content]
            kept = [(i, s) for i, s in enumerate(raw_deck)
                    if isinstance(s, str) and s != ""]
            dropped = [i for i, s in enumerate(raw_deck)
                       if not (isinstance(s, str) and s != "")]
            if dropped:
                # One entry per DROPPED ALTERNATE, naming its
                # source message -- the multiset keeps the count
                # of dropped alternates recoverable from the
                # report (a per-message collapse would lose it).
                report.empty_alternates_dropped.extend(
                    index for _ in dropped)
            deck = [s for _i, s in kept]
            old2new = {old: new for new, (old, _s) in enumerate(kept)}
            active = message.swipe_id
            if message.content in deck:
                if active in old2new and deck[old2new[active]] == message.content:
                    swipe_id = old2new[active]
                else:
                    swipe_id = deck.index(message.content)
                    # mes disagreed with the active swipe (or the
                    # active alternate was a dropped empty): mes
                    # wins by selection, nothing is lost.
                    report.mes_mismatch_repaired.append(index)
            elif active in old2new:
                swipe_id = old2new[active]
                deck[swipe_id] = message.content
                report.displaced_alternates[index] = active
                report.mes_mismatch_repaired.append(index)
            else:
                deck.append(message.content)
                swipe_id = len(deck) - 1
                report.mes_mismatch_repaired.append(index)
            if len(deck) > 1:
                report.messages_with_swipes += 1
                report.swipe_alternates_preserved += len(deck) - 1
            else:
                report.messages_without_swipes += 1
        # Parsed dates are stored VERBATIM: display order is
        # guaranteed by position (service._ordered_messages
        # sorts position first), so no timestamp is ever
        # rewritten to manufacture an ordering.
        created = _aware(message.send_date_parsed)
        report.plans.append(MessagePlan(
            source_index=index, role=message.role,
            content=message.content, speaker_name=message.speaker_name,
            deck=deck, swipe_id=swipe_id,
            has_explicit_swipes=message.has_explicit_swipes,
            created_at=created))
    report.messages_imported = len(report.plans)
    return report


def _provenance_json(plan: MessagePlan, source_shape: str) -> str:
    """One P-075 document: a record per swipe, origin imported.

    The file does not say which model produced the text, so the
    model section is an honest gap (unknown for assistant lines,
    not_applicable otherwise); no lore scan ran at import.
    """
    document = None
    for position in range(len(plan.deck)):
        record = prov_mod.build_record(
            origin_kind="imported",
            origin={"source_shape": source_shape,
                    "has_explicit_swipes": plan.has_explicit_swipes},
            model=prov_mod.model_section(
                status="unknown" if plan.role == "assistant"
                else "not_applicable"),
            preset=prov_mod.preset_section(status="unknown"),
            lore=prov_mod.lore_section(status="unknown"),
            speaker={"speaker_id": None,
                     "speaker_name": plan.speaker_name or None})
        if document is None:
            document = prov_mod.build_document(record, swipe_index=position)
        else:
            document = prov_mod.with_record_for_swipe(
                document, position, record)
    return prov_mod.dump_document(document)


async def materialise_import(
    session: AsyncSession,
    user_id: str,
    imported: ImportedChat | ImportResult,
    *,
    character_id: str | None = None,
    title: str | None = None,
) -> tuple[Chat, LiveImportReport]:
    """Write an imported chat into live rows; ONE commit.

    Accepts an ImportedChat or a P-020 ImportResult (whose parse
    report's refused/repaired counts ride into the live report).
    `character_id`, when given, must name a character the caller
    owns (KeyError otherwise, mirroring create_chat); a character
    NAME carried by the file is never guessed into an id.
    """
    from runmal.chats.service import EVENT_CHAT_CREATED, _record_event
    from runmal.characters.service import get_character as get_char

    parse_report = None
    chat_data = imported
    if isinstance(imported, ImportResult):
        chat_data = imported.chat
        parse_report = imported.report
    if character_id is not None and await get_char(
            session, user_id, character_id) is None:
        raise KeyError(character_id)
    report = plan_import(chat_data)
    plans = report.plans
    if parse_report is not None:
        report.parse_refused_lines = parse_report.refused_lines
        report.parse_repaired_lines = parse_report.repaired_lines
    report.character_linked = character_id is not None
    if title is None:
        title = ""
        if chat_data.source_shape == "runmal-native":
            raw_chat = chat_data.header_raw.get("chat")
            if isinstance(raw_chat, dict) and isinstance(
                    raw_chat.get("title"), str):
                title = raw_chat["title"]
    chat = Chat(user_id=user_id, title=title, character_id=character_id)
    created = _aware(chat_data.create_date_parsed)
    if created is not None:
        chat.created_at = created
    session.add(chat)
    await session.flush()
    for position, plan in enumerate(plans):
        message = Message(
            chat_id=chat.id, role=plan.role, content=plan.content,
            speaker_name=plan.speaker_name or None,
            swipes_json=json.dumps(plan.deck), swipe_id=plan.swipe_id,
            position=position,
            provenance_json=_provenance_json(plan, chat_data.source_shape))
        if plan.created_at is not None:
            message.created_at = plan.created_at
        session.add(message)
    await session.flush()
    await _record_event(session, chat.id, EVENT_CHAT_CREATED, data={
        "title": title, "character_id": character_id, "source": "import"})
    await _record_event(session, chat.id, EVENT_CHAT_IMPORTED, data={
        "source_shape": report.source_shape,
        "messages_imported": report.messages_imported,
        "messages_with_swipes": report.messages_with_swipes,
        "alternates_preserved": report.swipe_alternates_preserved,
        "empty_content_refused": len(report.empty_content_refused),
        "branch_link_keys": sorted(report.declared_branch_link),
    })
    await session.commit()
    # The report is an honesty surface (counts and indices
    # only): the working plans carry message text, so they
    # never ride out inside the returned report.
    report.plans = []
    return chat, report


async def import_chat_file(
    session: AsyncSession,
    user_id: str,
    data: bytes | str,
    **kwargs,
) -> tuple[Chat, LiveImportReport]:
    """Parse a chat file (P-020) and materialise it live (P-078)."""
    from runmal.chats.fileimport import parse_chat_file

    return await materialise_import(
        session, user_id, parse_chat_file(data), **kwargs)
