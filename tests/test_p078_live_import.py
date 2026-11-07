"""P-078 battery: chat import surgery -- imports become live chats.

Pins the P-078 contract from hidden_files/P078_DESIGN.md: a parsed
P-020 ImportedChat materialises into ordinary Chat/Message rows in
ONE transaction, after which the chat is indistinguishable from a
native chat on every road (list/get/append/edit/swipes/fork/
checkpoint/search/export/undo, provenance reads). Deck resolution
is deterministic with deck[active] == content; branches are never
fabricated (ST header branch-link keys ride as report data, the new
chat is kind=root); empty-content messages are refused, never given
invented text; every imported message carries a P-075 provenance
document with origin_kind="imported"; no message text ever appears
in the report or the import events.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from runmal.chats import branches, checkpoints, liveimport, search as search_mod
from runmal.chats import service as svc
from runmal.chats import undo as undo_mod
from runmal.chats.fileimport import parse_chat_file
from runmal.chats.filemodels import (
    ChatFileParseError,
    ImportedChat,
    ImportedMessage,
)
from runmal.chats.liveimport import plan_import
from runmal.chats.service import chat_to_dict, message_to_dict
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, User

UNKNOWN_ID = "12345678-1234-4234-9234-1234567890ab"


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    return tmp_path


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def jl(*records):
    return "\n".join(json.dumps(r) for r in records)


HEADER = {
    "character_name": "Old Bruni",
    "user_name": "Ferry Passenger",
    "create_date": "2026-10-01 @20h 00m 00s 000ms",
    "chat_metadata": {"integrity": "p078"},
}

ST_DOC = jl(
    HEADER,
    {
        "name": "Old Bruni", "is_user": False, "is_system": False,
        "mes": "Mind the gap. It minds you.",
        "send_date": "2026-10-01 @20h 00m 01s",
        "swipe_id": 0,
        "swipes": ["Mind the gap. It minds you.",
                   "Step careful. The planks remember rain."],
        "extra": {"api": "corpus", "model": "corpus-model"},
    },
    {
        "name": "Ferry Passenger", "is_user": True,
        "mes": "Is the letter heavy, Bruni?",
        "send_date": "2026-10-01 @20h 01m 00s",
        "swipe_id": 0, "swipes": ["Is the letter heavy, Bruni?"],
    },
    {
        "name": "Old Bruni", "is_user": False,
        "mes": "Letters are never heavy. News is.",
        "send_date": "2026-10-01 @20h 01m 30s",
        "swipe_id": 0, "swipes": ["Letters are never heavy. News is."],
    },
)


async def import_bytes(factory, user_id, data, **kw):
    async with factory() as session:
        return await liveimport.import_chat_file(session, user_id, data, **kw)


async def import_st(factory, user_id, **kw):
    chat, report = await import_bytes(factory, user_id, ST_DOC, **kw)
    return chat.id, report


async def history_dicts(factory, user_id, chat_id):
    async with factory() as session:
        history = await svc.get_history(session, user_id, chat_id)
        assert history is not None
        return [message_to_dict(m) for m in history]


async def history_rows(factory, user_id, chat_id):
    async with factory() as session:
        history = await svc.get_history(session, user_id, chat_id)
        assert history is not None
        return history


def msg(content, **kw):
    base = dict(role="assistant", content=content)
    base.update(kw)
    return ImportedMessage(**base)


def ichat(messages, **kw):
    base = dict(source_shape="st-jsonl-header", messages=messages)
    base.update(kw)
    return ImportedChat(**base)


# ---------------- A. an imported chat is a live chat ----------------


async def test_st_import_becomes_live_chat(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, report = await import_st(factory, user)
    assert report.source_shape == "st-jsonl-header"
    assert report.messages_imported == 3
    assert report.messages_with_swipes == 1
    assert report.swipe_alternates_preserved == 1
    assert report.messages_without_swipes == 2
    async with factory() as session:
        listed = await svc.list_chats(session, user)
        assert [c.id for c, _n in listed] == [chat_id]
        assert listed[0][1] == 3
        chat = await svc.get_chat(session, user, chat_id)
        assert chat is not None
        assert chat.character_id is None  # a name is never guessed into an id
        assert chat_to_dict(chat, 3)["branch"]["kind"] == "root"
        events = await svc.list_events(session, user, chat_id)
        kinds = [e.kind for e in events]
        assert kinds.count("chat.created") == 1
        assert kinds.count("chat.imported") == 1
    dicts = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in dicts] == [
        "Mind the gap. It minds you.",
        "Is the letter heavy, Bruni?",
        "Letters are never heavy. News is.",
    ]
    assert [d["position"] for d in dicts] == [0, 1, 2]
    assert dicts[0]["swipes"] == [
        "Mind the gap. It minds you.",
        "Step careful. The planks remember rain.",
    ]
    assert dicts[0]["swipe_id"] == 0
    assert dicts[0]["speaker_name"] == "Old Bruni"
    assert dicts[1]["role"] == "user"


async def test_imported_chat_append_and_edit_like_native(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        added = await svc.append_message(
            session, user, chat_id, "user", "One more thing.")
        assert added.position == 3
        edited = await svc.edit_message(
            session, user, chat_id, added.id, "One more thing, edited.")
        assert edited is not None and edited.content == "One more thing, edited."
    dicts = await history_dicts(factory, user, chat_id)
    assert len(dicts) == 4
    assert dicts[-1]["content"] == "One more thing, edited."


async def test_imported_chat_swipe_roads(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    rows = await history_rows(factory, user, chat_id)
    first_id = rows[0].id
    async with factory() as session:
        selected = await svc.select_swipe(session, user, chat_id, first_id, index=1)
        assert selected is not None
        assert selected.content == "Step careful. The planks remember rain."
        added = await svc.add_swipe(
            session, user, chat_id, first_id, "Third way of saying it.")
        assert added is not None and len(json.loads(added.swipes_json)) == 3
        removed = await svc.delete_swipe(session, user, chat_id, first_id, 2)
        assert removed is not None and len(json.loads(removed.swipes_json)) == 2
    dicts = await history_dicts(factory, user, chat_id)
    assert dicts[0]["content"] == "Step careful. The planks remember rain."
    assert dicts[0]["swipe_id"] == 1


async def test_imported_chat_fork_preserves_decks(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        branch = await branches.fork_chat(session, user, chat_id)
        assert branch is not None
        assert branch.branch_kind == "fork"
        assert branch.branch_parent_id == chat_id
        family = await branches.list_branch_family(session, user, chat_id)
        assert family is not None
    dicts = await history_dicts(factory, user, branch.id)
    assert dicts[0]["swipes"] == [
        "Mind the gap. It minds you.",
        "Step careful. The planks remember rain.",
    ]
    assert [d["content"] for d in dicts] == [
        "Mind the gap. It minds you.",
        "Is the letter heavy, Bruni?",
        "Letters are never heavy. News is.",
    ]


async def test_imported_chat_checkpoint(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        made = await checkpoints.create_checkpoint(
            session, user, chat_id, "after-import")
        assert made is not None and made["message_count"] == 3
        listed = await checkpoints.list_checkpoints(session, user, chat_id)
        assert listed is not None and len(listed) == 1


async def test_imported_chat_searchable(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        doc = await search_mod.search_chats(session, user, "Letters")
        assert doc is not None and doc["total"] >= 1
        assert any(r["chat_id"] == chat_id for r in doc["results"])


async def test_imported_chat_undo_of_later_append(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        await svc.append_message(session, user, chat_id, "user", "Ephemeral.")
    dicts = await history_dicts(factory, user, chat_id)
    assert len(dicts) == 4
    async with factory() as session:
        result = await undo_mod.undo_last(session, user, chat_id)
        assert result is not None
    dicts = await history_dicts(factory, user, chat_id)
    assert len(dicts) == 3


async def test_imported_chat_owner_isolation(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "someone-else")
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        assert await svc.get_history(session, other, chat_id) is None
        assert await svc.list_chats(session, other) == []
        assert await svc.get_chat(session, other, chat_id) is None


async def test_native_reimport_preserves_decks(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        exported = await svc.export_chat(session, user, chat_id)
        assert exported is not None
    parsed = parse_chat_file(json.dumps(exported))
    assert parsed.chat.source_shape == "runmal-native"
    assert parsed.chat.messages[0].has_explicit_swipes is True
    assert parsed.chat.messages[0].swipes == [
        "Mind the gap. It minds you.",
        "Step careful. The planks remember rain.",
    ]
    async with factory() as session:
        chat2, report2 = await liveimport.materialise_import(
            session, user, parsed)
    assert report2.messages_with_swipes == 1
    dicts = await history_dicts(factory, user, chat2.id)
    assert dicts[0]["swipes"] == [
        "Mind the gap. It minds you.",
        "Step careful. The planks remember rain.",
    ]


# ---------------- B. deck resolution ----------------


def test_plan_no_swipes_carried():
    report = plan_import(ichat([msg("Solo line.")]))
    assert report.messages_without_swipes == 1
    assert report.messages_with_swipes == 0
    plan = report.plans[0]
    assert plan.deck == ["Solo line."] and plan.swipe_id == 0


def test_plan_explicit_deck_active_matches():
    report = plan_import(ichat([msg(
        "Second.", swipes=["First.", "Second."], swipe_id=1,
        has_explicit_swipes=True)]))
    plan = report.plans[0]
    assert plan.deck == ["First.", "Second."] and plan.swipe_id == 1
    assert report.mes_mismatch_repaired == []
    assert report.swipe_alternates_preserved == 1
    assert report.messages_with_swipes == 1


def test_plan_empty_alternates_dropped_per_alternate():
    report = plan_import(ichat([msg(
        "Kept.", swipes=["Kept.", "", ""], swipe_id=0,
        has_explicit_swipes=True)]))
    plan = report.plans[0]
    assert plan.deck == ["Kept."]
    # One entry per dropped alternate, naming its source
    # message: two drops from message 0 report [0, 0], so the
    # dropped-alternate COUNT stays recoverable from the report.
    assert report.empty_alternates_dropped == [0, 0]


def test_plan_mes_mismatch_displaced_alternate():
    report = plan_import(ichat([msg(
        "Mes wins.", swipes=["Old active.", "Other."], swipe_id=0,
        has_explicit_swipes=True)]))
    plan = report.plans[0]
    assert plan.deck == ["Mes wins.", "Other."]
    assert plan.deck[plan.swipe_id] == "Mes wins."
    assert report.mes_mismatch_repaired == [0]
    assert report.swipe_alternates_preserved == 1


def test_plan_mes_mismatch_moves_active_nothing_lost():
    report = plan_import(ichat([msg(
        "Second.", swipes=["First.", "Second."], swipe_id=0,
        has_explicit_swipes=True)]))
    plan = report.plans[0]
    assert plan.deck == ["First.", "Second."] and plan.swipe_id == 1
    assert report.mes_mismatch_repaired == [0]
    assert report.swipe_alternates_preserved == 1


async def test_empty_content_message_refused_not_invented(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat = ichat([msg("Before."), msg(""), msg("After.")])
    async with factory() as session:
        _chat, report = await liveimport.materialise_import(session, user, chat)
    assert report.empty_content_refused == [1]
    assert report.messages_imported == 2
    dicts = await history_dicts(factory, user, _chat.id)
    assert [d["content"] for d in dicts] == ["Before.", "After."]
    assert [d["position"] for d in dicts] == [0, 1]


def test_plan_swipe_info_and_extra_reported_by_key_only():
    secret = "swordfish-value-12345"
    report = plan_import(ichat([msg(
        "A perfectly ordinary line.",
        swipes=["A perfectly ordinary line."], swipe_id=0,
        has_explicit_swipes=True,
        swipe_info=[{"gen_id": 7}], has_swipe_info=True,
        extra={"api": secret, "model": "m"})]))
    assert report.swipe_info_unmappable == 1
    assert report.extra_keys_unmappable == {0: ["api", "model"]}
    blob = json.dumps(report.to_dict())
    assert secret not in blob
    assert "A perfectly ordinary line." not in blob


def test_plan_send_date_unmappable_counted():
    report = plan_import(ichat([msg(
        "Dated badly.", raw={"send_date": "not a date"},
        send_date_parsed=None)]))
    assert report.send_date_unmappable == 1
    assert report.plans[0].created_at is None


async def test_report_and_events_carry_no_message_text(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, report = await import_st(factory, user)
    blob = json.dumps(report.to_dict())
    assert "Mind the gap" not in blob and "planks remember" not in blob
    async with factory() as session:
        events = await svc.list_events(session, user, chat_id)
        imported = [e for e in events if e.kind == "chat.imported"]
        assert len(imported) == 1
        data = json.loads(imported[0].data)
        assert data["messages_imported"] == 3
        assert "Mind the gap" not in imported[0].data


# ---------------- C. branch honesty ----------------


async def test_branch_link_keys_preserved_as_data_never_lineage(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    header = dict(HEADER)
    header["chat_metadata"] = {
        "integrity": "p078",
        "branch_of": "source-chat-99",
        "parent_chat": "source-chat-98",
        "branch_point": 2,
    }
    doc = jl(header, {
        "name": "Ferry Passenger", "is_user": True,
        "mes": "Branch child line.", "swipe_id": 0,
        "swipes": ["Branch child line."],
    })
    chat, report = await import_bytes(factory, user, doc)
    assert report.declared_branch_link == {
        "branch_of": "source-chat-99",
        "parent_chat": "source-chat-98",
        "branch_point": 2,
    }
    assert report.branch_link_mapped_to_lineage is False
    assert chat.branch_kind == "root"
    assert chat.branch_parent_id is None
    async with factory() as session:
        events = await svc.list_events(session, user, chat.id)
        imported = [e for e in events if e.kind == "chat.imported"][0]
        data = json.loads(imported.data)
        assert data["branch_link_keys"] == [
            "branch_of", "branch_point", "parent_chat"]


async def test_no_branch_link_reports_absent(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    _chat_id, report = await import_st(factory, user)
    assert report.declared_branch_link == {}
    assert report.branch_link_mapped_to_lineage is False


# ---------------- D. provenance ----------------


async def test_provenance_document_per_message(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    rows = await history_rows(factory, user, chat_id)
    async with factory() as session:
        for row in rows:
            view = await svc.get_message_provenance(
                session, user, chat_id, row.id)
            assert view is not None and view["recorded"] is True
            deck = json.loads(row.swipes_json)
            assert sorted(view["swipes"], key=int) == [
                str(i) for i in range(len(deck))]
            for record in view["swipes"].values():
                assert record["origin"]["kind"] == "imported"
                assert record["origin"]["source_shape"] == "st-jsonl-header"
        first = await svc.get_message_provenance(
            session, user, chat_id, rows[0].id)
        assert first["swipes"]["0"]["model"]["status"] == "unknown"
        assert first["swipes"]["0"]["preset"]["status"] == "unknown"
        user_msg = await svc.get_message_provenance(
            session, user, chat_id, rows[1].id)
        assert user_msg["swipes"]["0"]["model"]["status"] == "not_applicable"
        listing = await svc.list_chat_provenance(session, user, chat_id)
        assert listing is not None and len(listing["messages"]) == 3


# ---------------- E. character, title, dates, errors ----------------


async def test_character_linked_only_when_caller_supplies_id(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        character = Character(user_id=user, name="Old Bruni")
        session.add(character)
        await session.commit()
        character_id = character.id
    chat, report = await import_bytes(
        factory, user, ST_DOC, character_id=character_id)
    assert chat.character_id == character_id
    assert report.character_linked is True
    assert report.character_name_carried == "Old Bruni"
    async with factory() as session:
        with pytest.raises(KeyError):
            await liveimport.import_chat_file(
                session, user, ST_DOC, character_id=UNKNOWN_ID)


async def test_title_from_native_document(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    async with factory() as session:
        await svc.rename_chat(session, user, chat_id, "The Ferry Crossing")
        exported = await svc.export_chat(session, user, chat_id)
    async with factory() as session:
        chat2, _r = await liveimport.import_chat_file(
            session, user, json.dumps(exported))
    assert chat2.title == "The Ferry Crossing"
    chat3, _r3 = await import_bytes(factory, user, ST_DOC)
    assert chat3.title == ""


async def test_created_at_from_send_dates_stored_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _report = await import_st(factory, user)
    rows = await history_rows(factory, user, chat_id)
    first = rows[0].created_at
    if first.tzinfo is None:
        first = first.replace(tzinfo=UTC)
    assert first == datetime(2026, 10, 1, 20, 0, 1, tzinfo=UTC)
    # Two messages sharing one send_date keep that date VERBATIM
    # (never rewritten); position carries the display order.
    doc = jl(
        HEADER,
        {"name": "Ferry Passenger", "is_user": True, "mes": "Same time one.",
         "send_date": "2026-10-01 @20h 05m 00s", "swipe_id": 0,
         "swipes": ["Same time one."]},
        {"name": "Old Bruni", "is_user": False, "mes": "Same time two.",
         "send_date": "2026-10-01 @20h 05m 00s", "swipe_id": 0,
         "swipes": ["Same time two."]},
    )
    chat2, _r = await import_bytes(factory, user, doc)
    rows2 = await history_rows(factory, user, chat2.id)
    assert rows2[0].created_at == rows2[1].created_at
    dicts2 = await history_dicts(factory, user, chat2.id)
    assert [d["content"] for d in dicts2] == ["Same time one.", "Same time two."]
    assert [d["position"] for d in dicts2] == [0, 1]


async def test_import_chat_file_parse_error_propagates(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        with pytest.raises(ChatFileParseError):
            await liveimport.import_chat_file(session, user, b"42")


def test_report_shape_keys():
    report = plan_import(ichat([msg("Shape.")]))
    assert set(report.to_dict()) == {
        "source_shape", "messages_imported", "messages_with_swipes",
        "swipe_alternates_preserved", "messages_without_swipes",
        "empty_content_refused", "empty_alternates_dropped",
        "mes_mismatch_repaired", "displaced_alternates",
        "branch_link_absent", "swipe_info_unmappable",
        "extra_keys_unmappable", "send_date_unmappable",
        "declared_branch_link", "branch_link_mapped_to_lineage",
        "character_name_carried", "character_linked",
        "parse_refused_lines", "parse_repaired_lines",
    }


def test_migration_head_stays_0040(tmp_path):
    assert MIGRATIONS[-1][0] == "0040"
    revisions = [r[0] for r in MIGRATIONS]
    assert revisions.count("0040") == 1
    assert MIGRATIONS[-1][2].__name__.endswith("m0040_message_provenance")
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0040"


# ---------------- F. review fixes (post-review adjudication) ----------------


def test_plan_refused_message_metadata_still_counted():
    # A refused (empty) message's unmappable metadata is still
    # reported: refusal drops the message, not the accounting.
    report = plan_import(ichat([
        msg("Kept."),
        msg("", swipe_info=[{"gen_id": 1}], has_swipe_info=True,
            extra={"api": "x"}, raw={"send_date": "junk"},
            send_date_parsed=None),
    ]))
    assert report.empty_content_refused == [1]
    assert report.swipe_info_unmappable == 1
    assert report.extra_keys_unmappable == {1: ["api"]}
    assert report.send_date_unmappable == 1


def test_plan_native_unparsed_date_counted():
    # The native shape carries the date as created_at in raw;
    # an unparsed carried date is reported, never faked.
    report = plan_import(ichat([msg(
        "Native line.", raw={"created_at": "not a date"},
        send_date_parsed=None)]))
    assert report.send_date_unmappable == 1


def test_plan_mismatch_with_dropped_empty_active_reported():
    report = plan_import(ichat([msg(
        "Y", swipes=["X", "", "Y"], swipe_id=1,
        has_explicit_swipes=True)]))
    plan = report.plans[0]
    assert plan.deck == ["X", "Y"] and plan.swipe_id == 1
    assert report.empty_alternates_dropped == [0]
    assert report.mes_mismatch_repaired == [0]


def test_plan_displaced_alternate_reported_by_index():
    report = plan_import(ichat([msg(
        "Mes wins.", swipes=["Old active.", "Other."], swipe_id=0,
        has_explicit_swipes=True)]))
    assert report.displaced_alternates == {0: 0}
    moved = plan_import(ichat([msg(
        "Second.", swipes=["First.", "Second."], swipe_id=0,
        has_explicit_swipes=True)]))
    assert moved.displaced_alternates == {}


def test_plan_non_string_deck_entries_dropped():
    report = plan_import(ichat([msg(
        "A", swipes=["A", None, 5], swipe_id=0,
        has_explicit_swipes=True)]))
    plan = report.plans[0]
    assert plan.deck == ["A"]
    assert report.empty_alternates_dropped == [0, 0]


async def test_materialised_report_carries_no_message_text(tmp_path):
    import dataclasses

    factory = make_factory(tmp_path)
    user = await make_user(factory)
    _chat_id, report = await import_st(factory, user)
    assert report.plans == []
    blob = json.dumps(dataclasses.asdict(report))
    assert "Mind the gap" not in blob and "planks remember" not in blob


def test_native_parse_empty_content_recovers_deck_text():
    doc = {
        "format": "runmal-chat-export", "version": 1,
        "chat": {"title": "T"},
        "messages": [
            {"role": "assistant", "content": "",
             "swipes": ["Real text."], "swipe_id": 0},
        ],
    }
    parsed = parse_chat_file(json.dumps(doc))
    assert parsed.chat.messages[0].content == "Real text."
    assert parsed.chat.messages[0].swipes == ["Real text."]


async def test_fork_of_mixed_dated_undated_import_keeps_order(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat = ichat([
        msg("Undated first."),
        msg("Dated second.", send_date_parsed=datetime(2024, 1, 1, 10, 0, 0)),
        msg("Undated third."),
    ], create_date_parsed=None)
    async with factory() as session:
        imported, _report = await liveimport.materialise_import(
            session, user, chat)
        branch = await branches.fork_chat(session, user, imported.id)
        assert branch is not None
    dicts = await history_dicts(factory, user, branch.id)
    assert [d["content"] for d in dicts] == [
        "Undated first.", "Dated second.", "Undated third."]
    assert [d["position"] for d in dicts] == [0, 1, 2]
