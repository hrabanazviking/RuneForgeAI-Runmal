"""P-162 - Character face history (Part X, DERIVED).

Pins: the per-character board of that character's kept
face history across all of its chats - P-160's chat
enumeration (list_chats order, the chats service's title
and message count, other characters' and unbound chats
never appearing) composed with P-158's history document
verbatim per chat (events whole with provenance,
entry_state / problem_now / descriptor, the counts, the
kept window), events never merged across chats, the
board classified under the closed HISTORY_BOARD_STATES
law (no_chats / no_history / some_history / all_history),
the totals summed from P-158's own arithmetic, the
standing honesty notes, owner scoping (unknown/foreign/
deleted character -> None / 404), the pure-read law (the
P-092 store byte-identical after resolves), and the
neighbours (migration head stays 0041, no 0042). No
network.
"""

from __future__ import annotations

import struct
import uuid
import zlib

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets import service as assets_svc
from runmal.auth import get_or_create_credential
from runmal.characters import service as characters_svc
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.faces import character_history as board
from runmal.faces import history as hist
from runmal.plugins import expressions as ex
from runmal.plugins import service as plugin_service
from runmal.plugins.image_generation import render_deterministic_png

PNG_BYTES = render_deterministic_png("sprite seed", "", 1, 32)


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def card_dict(name="Asta"):
    return {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "description": "A keeper of the northern lighthouse.",
        "personality": "Steady.", "scenario": "A test hall.",
        "first_mes": "Hail!", "mes_example": "", "creator_notes": "",
        "system_prompt": "", "post_history_instructions": "",
        "alternate_greetings": [], "tags": [], "creator": "forge",
        "character_version": "1.0",
    }


async def seed_character(factory, uid, name="Asta"):
    async with factory() as session:
        character = await characters_svc.create_character(
            session, uid, card_dict(name))
        await session.commit()
        return character.id


async def seed_chat(factory, uid, character_id=None, title="The Lighthouse"):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title,
            character_id=character_id,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


async def _add_asset(factory, uid, cid, *, kind, name):
    async with factory() as session:
        asset = await assets_svc.add_asset(
            session, uid, cid, kind=kind, name=name,
            filename=f"{name.replace(' ', '_')}.png", data=PNG_BYTES)
        return asset.id


async def _world(factory, uid):
    """Character + set: neutral (no asset), amused (bound
    sprite), wrong (wrong-kind asset); default is amused.
    No chats yet - each test seeds the chats it judges."""
    cid = await seed_character(factory, uid)
    bound_id = await _add_asset(factory, uid, cid, kind="expression",
                                name="amused")
    bg_id = await _add_asset(factory, uid, cid, kind="background",
                             name="stairs")
    ex.create_set(uid, {
        "character_id": cid,
        "entries": [
            {"name": "neutral", "label": "Neutral"},
            {"name": "amused", "label": "Amused", "asset_id": bound_id},
            {"name": "wrong", "label": "Wrong", "asset_id": bg_id},
        ],
        "default": "amused",
    })
    return cid, bound_id, bg_id


# -- Scoping / empty boards ------------------------------------------------------


async def test_missing_and_foreign_character_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await board.resolve_character_face_history(
            session, uid, str(uuid.uuid4())) is None
        assert await board.resolve_character_face_history(
            session, other, cid) is None


async def test_deleted_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await characters_svc.delete_character(
            session, uid, cid) is True
        assert await board.resolve_character_face_history(
            session, uid, cid) is None


async def test_character_with_no_chats_is_an_empty_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert doc["schema"] == board.CHARACTER_HISTORY_SCHEMA
    assert doc["character_id"] == cid
    assert doc["character"]["id"] == cid
    assert doc["character"]["name"] == "Asta"
    assert doc["state"] == board.HISTORY_BOARD_STATE_NO_CHATS
    assert doc["chats"] == []
    assert doc["chat_count"] == 0
    assert doc["chats_with_history_count"] == 0
    assert doc["event_count"] == 0
    assert doc["selection_count"] == 0
    assert doc["cleared_count"] == 0
    assert doc["still_ready_count"] == 0
    assert doc["chats_at_kept_limit"] == 0
    assert doc["kept_limit"] == ex.MAX_HISTORY_KEPT


async def test_chats_without_events_are_a_no_history_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    await seed_chat(factory, uid, cid, title="First")
    await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert doc["state"] == board.HISTORY_BOARD_STATE_NO_HISTORY
    assert doc["chat_count"] == 2
    assert doc["chats_with_history_count"] == 0
    assert doc["event_count"] == 0
    for row in doc["chats"]:
        assert row["events"] == []
        assert row["event_count"] == 0
        assert row["at_kept_limit"] is False
        assert row["kept_limit"] == ex.MAX_HISTORY_KEPT


async def test_unbound_and_other_character_chats_never_appear(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    other_cid = await seed_character(factory, uid, name="Bera")
    ex.create_set(uid, {
        "character_id": other_cid,
        "entries": [{"name": "amused", "label": "Amused"}],
        "default": "amused",
    })
    mine = await seed_chat(factory, uid, cid, title="Mine")
    hers = await seed_chat(factory, uid, other_cid, title="Hers")
    await seed_chat(factory, uid, None, title="Unbound")
    async with factory() as session:
        await ex.select_for_chat(session, uid, mine, "amused")
        await ex.select_for_chat(session, uid, hers, "amused")
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert doc["chat_count"] == 1
    (row,) = doc["chats"]
    assert row["chat_id"] == mine
    assert row["event_count"] == 1


# -- Rows: order, chat facts, per-chat history truth ------------------------------


async def test_rows_ride_in_creation_order_with_chat_facts(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    third = await seed_chat(factory, uid, cid, title="Third")
    async with factory() as session:
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert [row["chat_id"] for row in doc["chats"]] == [first, second, third]
    assert [row["title"] for row in doc["chats"]] == [
        "First", "Second", "Third"]
    assert all(row["message_count"] == 0 for row in doc["chats"])
    assert doc["chat_count"] == 3


async def test_row_composes_p158_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, bound_id, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
        await ex.select_for_chat(session, uid, chat_id, "neutral",
                                 reason="the news turned grave")
        expected = await hist.resolve_face_history(session, uid, chat_id)
        doc = await board.resolve_character_face_history(session, uid, cid)
    (row,) = doc["chats"]
    for key in ("chat_id", "presentation_state", "current", "events",
                "event_count", "selection_count", "cleared_count",
                "still_ready_count", "kept_limit", "at_kept_limit"):
        assert row[key] == expected[key], key
    newest, oldest = row["events"]
    assert newest["expression"] == "neutral"
    assert newest["provenance"]["reason"] == "the news turned grave"
    assert newest["provenance"]["previous_expression"] == "amused"
    assert oldest["expression"] == "amused"
    assert doc["state"] == board.HISTORY_BOARD_STATE_ALL_HISTORY


async def test_still_ready_event_descriptor_rides_per_chat(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, bound_id, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        doc = await board.resolve_character_face_history(session, uid, cid)
    (row,) = doc["chats"]
    (event,) = row["events"]
    assert event["entry_state"] == hist.ENTRY_STATE_STILL_READY
    assert event["problem_now"] is None
    descriptor = event["descriptor"]
    assert descriptor["name"] == "amused"
    base = f"/api/v1/characters/{cid}/assets/{bound_id}"
    assert descriptor["content_url"] == f"{base}/content"
    assert descriptor["thumbnail_url"] == f"{base}/thumbnail"
    assert row["presentation_state"] == "ready"
    assert row["current"]["expression"] == "amused"
    assert doc["still_ready_count"] == 1


async def test_events_are_never_merged_across_chats(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "neutral")
        await ex.select_for_chat(session, uid, first, "neutral")
        doc = await board.resolve_character_face_history(session, uid, cid)
    by_title = {row["title"]: row for row in doc["chats"]}
    assert [e["expression"] for e in by_title["First"]["events"]] == [
        "neutral", "amused"]
    assert all(e["chat_id"] == first for e in by_title["First"]["events"])
    assert [e["expression"] for e in by_title["Second"]["events"]] == [
        "neutral"]
    assert all(e["chat_id"] == second for e in by_title["Second"]["events"])
    assert doc["event_count"] == 3


async def test_cleared_event_counts_as_history_not_selection(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    assert ex.clear_selection(uid, chat_id, reason="scene over") is True
    async with factory() as session:
        doc = await board.resolve_character_face_history(session, uid, cid)
    (row,) = doc["chats"]
    assert row["event_count"] == 2
    assert row["selection_count"] == 1 and row["cleared_count"] == 1
    newest = row["events"][0]
    assert newest["entry_state"] == hist.ENTRY_STATE_CLEARED
    assert newest["expression"] is None
    assert doc["event_count"] == 2
    assert doc["selection_count"] == 1 and doc["cleared_count"] == 1
    assert doc["state"] == board.HISTORY_BOARD_STATE_ALL_HISTORY
    assert doc["chats_with_history_count"] == 1


# -- The board law ------------------------------------------------------------------


async def test_some_history_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    busy = await seed_chat(factory, uid, cid, title="Busy")
    await seed_chat(factory, uid, cid, title="Quiet")
    async with factory() as session:
        await ex.select_for_chat(session, uid, busy, "amused")
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert doc["state"] == board.HISTORY_BOARD_STATE_SOME_HISTORY
    assert doc["chats_with_history_count"] == 1 and doc["chat_count"] == 2


async def test_all_history_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "neutral")
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert doc["state"] == board.HISTORY_BOARD_STATE_ALL_HISTORY
    assert doc["chats_with_history_count"] == 2


async def test_totals_sum_p158_arithmetic_on_a_mixed_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    await seed_chat(factory, uid, cid, title="Quiet")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, first, "wrong")
        await ex.select_for_chat(session, uid, second, "neutral")
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert doc["chat_count"] == 3
    assert doc["chats_with_history_count"] == 2
    assert doc["event_count"] == 3
    assert doc["selection_count"] == 3
    assert doc["cleared_count"] == 0
    assert doc["still_ready_count"] == 1
    assert doc["state"] == board.HISTORY_BOARD_STATE_SOME_HISTORY
    by_title = {row["title"]: row for row in doc["chats"]}
    wrong_event = by_title["First"]["events"][0]
    assert wrong_event["entry_state"] == hist.ENTRY_STATE_DECLARED_UNBOUND
    assert wrong_event["problem_now"] == "wrong_kind"
    neutral_event = by_title["Second"]["events"][0]
    assert neutral_event["entry_state"] == hist.ENTRY_STATE_DECLARED_UNBOUND
    assert neutral_event["problem_now"] == "no_asset"
    assert by_title["Quiet"]["events"] == []


async def test_no_set_character_rows_are_empty_and_honest(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    await seed_chat(factory, uid, cid)
    async with factory() as session:
        doc = await board.resolve_character_face_history(session, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "no_set"
    assert row["events"] == [] and row["current"] is None
    assert doc["state"] == board.HISTORY_BOARD_STATE_NO_HISTORY


# -- Pure-read law / notes ------------------------------------------------------------


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    store = ex.store_path(uid)
    before = store.read_bytes()
    async with factory() as session:
        await board.resolve_character_face_history(session, uid, cid)
        await board.resolve_character_face_history(session, uid, cid)
    assert store.read_bytes() == before
    assert ex.current_expression(uid, chat_id)["expression"] == "amused"
    assert len(ex.list_history(uid, chat_id=chat_id)) == 1


async def test_notes_and_closed_state_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    async with factory() as session:
        doc = await board.resolve_character_face_history(session, uid, cid)
    assert doc["notes"] == list(board.NOTES)
    assert len(doc["notes"]) == 5
    assert "renders nothing" in doc["notes"][0]
    assert "per chat" in doc["notes"][2]
    assert "no single face history stream" in doc["notes"][3]
    assert set(board.HISTORY_BOARD_STATES) == {
        "no_chats", "no_history", "some_history", "all_history"}


# -- HTTP surface ---------------------------------------------------------------------


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + ctype + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def make_png_bytes(width=16, height=16, color=(200, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(raw))
            + _png_chunk(b"IEND", b""))


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_http_character_history_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    empty = client.get("/api/v1/faces/character-history",
                       params={"character_id": cid})
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "no_chats"
    assert empty.json()["chats"] == []
    up = client.post(
        f"/api/v1/characters/{cid}/assets",
        data={"kind": "expression", "name": "amused"},
        files={"file": ("amused.png", make_png_bytes(), "image/png")})
    assert up.status_code == 201, up.text
    asset_id = up.json()["id"]
    made = client.post("/api/v1/expressions/sets", json={
        "character_id": cid,
        "entries": [{"name": "neutral"},
                    {"name": "amused", "asset_id": asset_id}],
        "default": "neutral"})
    assert made.status_code == 201, made.text
    chat = client.post("/api/v1/chats",
                       json={"title": "T", "character_id": cid})
    assert chat.status_code in (200, 201), chat.text
    chat_id = chat.json()["id"]
    before = client.get("/api/v1/faces/character-history",
                        params={"character_id": cid})
    assert before.status_code == 200, before.text
    assert before.json()["state"] == "no_history"
    assert before.json()["chats"][0]["events"] == []
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/character-history",
                       params={"character_id": cid})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p162-character-face-history-v1"
    assert doc["state"] == "all_history"
    assert doc["event_count"] == 1
    event = doc["chats"][0]["events"][0]
    assert event["expression"] == "amused"
    assert event["entry_state"] == "still_ready"
    assert event["descriptor"]["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    missing = client.get("/api/v1/faces/character-history",
                         params={"character_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/character-history" in paths


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
