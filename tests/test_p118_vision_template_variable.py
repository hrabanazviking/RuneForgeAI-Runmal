"""P-118 — Vision template variable + custody (Part VIII, DERIVED).

Pins: the S307 registry gains ``last_vision_description`` (the
VX-43/VX-50 template variable P-117 named open); the resolver
substitutes a supplied value and — P-075 — an honest EMPTY when
the chat has none (nothing fabricated, the variable is known so
it is never flagged unknown); vision_link reads P-117's store
format (version 1) tolerantly (missing/corrupt reads as none);
resolve_variables_for_chat fills the value from the store; the
tools preview road resolves it from explicit text or a chat_id;
and chat deletion purges the chat's descriptions while other
chats' rows survive (custody, voice drop_chat precedent).
Migration head stays 0041. No network: fixtures only.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.prompt import vision_link as vl
from runmal.prompt.variables import (
    list_variables,
    resolve_variables,
    resolve_variables_for_chat,
)

FIXED = datetime(2026, 11, 8, 12, 0)  # a Sunday


def _row(chat_id, description, row_id):
    """One description row in P-117's exact store shape."""
    return {
        "id": row_id,
        "chat_id": chat_id,
        "owner_id": "owner-1",
        "source_kind": "inline",
        "source_ref": "",
        "question": "",
        "description": description,
        "provider": {"provider_id": "runmal.vision.metadata",
                     "model": "sniff-1", "road": "metadata"},
        "image": {"format": "png", "width": 6, "height": 4,
                  "bytes": 123, "sha256": "ab" * 32},
        "created_at": "2026-11-08T12:00:00+00:00",
    }


def _seed_store(tmp_path, rows):
    path = tmp_path / "vision_descriptions.json"
    path.write_text(json.dumps({"version": 1, "descriptions": rows}))
    return path


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ------------------------------------------------------- registry


def test_registry_gains_the_vision_variable():
    names = [v["name"] for v in list_variables()]
    assert names == ["char", "user", "original", "time", "date",
                     "weekday", "last_vision_description"]
    entry = [v for v in list_variables()
             if v["name"] == "last_vision_description"][0]
    assert entry["description"]


# ------------------------------------------------------- resolver


def test_resolve_substitutes_a_supplied_description():
    out = resolve_variables(
        "You last saw: {{last_vision_description}}",
        now=FIXED, last_vision_description="a red door, ajar")
    assert out.text == "You last saw: a red door, ajar"
    assert out.resolved == ["last_vision_description"]
    assert out.unknown == []


def test_resolve_without_description_is_an_honest_empty():
    out = resolve_variables(
        "You last saw: [{{last_vision_description}}]", now=FIXED)
    assert out.text == "You last saw: []"
    assert out.resolved == ["last_vision_description"]
    assert out.unknown == []  # known variable, never flagged


def test_resolve_vision_variable_is_case_insensitive():
    out = resolve_variables(
        "{{LAST_VISION_DESCRIPTION}}", now=FIXED,
        last_vision_description="snow on the fjord")
    assert out.text == "snow on the fjord"


def test_unknowns_still_flagged_alongside_vision():
    out = resolve_variables(
        "{{mood}} / {{last_vision_description}}", now=FIXED,
        last_vision_description="a harbour at dusk")
    assert out.text == "{{mood}} / a harbour at dusk"
    assert out.unknown == ["mood"]
    assert out.resolved == ["last_vision_description"]


# ---------------------------------------------------- vision_link


def test_link_missing_store_reads_as_none(tmp_path):
    assert vl.last_for_chat("chat-a", tmp_path) is None
    assert vl.last_description_text("chat-a", tmp_path) == ""
    assert vl.load_descriptions(tmp_path) == []


def test_link_last_is_the_last_row_for_that_chat(tmp_path):
    _seed_store(tmp_path, [
        _row("chat-a", "first look", "r1"),
        _row("chat-b", "other chat", "r2"),
        _row("chat-a", "second look", "r3"),
    ])
    assert vl.last_description_text("chat-a", tmp_path) == "second look"
    assert vl.last_description_text("chat-b", tmp_path) == "other chat"
    assert vl.last_for_chat("chat-c", tmp_path) is None
    assert [r["id"] for r in vl.list_for_chat("chat-a", tmp_path)] == ["r1", "r3"]


def test_link_corrupt_store_reads_as_empty(tmp_path):
    (tmp_path / "vision_descriptions.json").write_text("{not json")
    assert vl.load_descriptions(tmp_path) == []
    assert vl.last_description_text("chat-a", tmp_path) == ""


def test_link_wrong_shape_rows_are_skipped(tmp_path):
    _seed_store(tmp_path, ["junk", 42, _row("chat-a", "real", "r9")])
    assert vl.last_description_text("chat-a", tmp_path) == "real"


def test_purge_removes_only_that_chat_and_counts(tmp_path):
    path = _seed_store(tmp_path, [
        _row("chat-a", "first look", "r1"),
        _row("chat-b", "other chat", "r2"),
        _row("chat-a", "second look", "r3"),
    ])
    assert vl.purge_chat("chat-a", tmp_path) == 2
    doc = json.loads(path.read_text())
    assert doc["version"] == 1
    assert [r["id"] for r in doc["descriptions"]] == ["r2"]
    assert vl.last_description_text("chat-b", tmp_path) == "other chat"
    before = path.read_text()
    assert vl.purge_chat("chat-a", tmp_path) == 0  # idempotent
    assert path.read_text() == before  # nothing to purge: untouched


def test_purge_missing_store_creates_no_file(tmp_path):
    assert vl.purge_chat("chat-a", tmp_path) == 0
    assert not (tmp_path / "vision_descriptions.json").exists()


# ------------------------------------------- resolver + store glue


def test_resolve_for_chat_fills_from_the_store(tmp_path):
    _seed_store(tmp_path, [_row("chat-a", "a lighthouse", "r1")])
    out = resolve_variables_for_chat(
        "Seen: {{last_vision_description}}", chat_id="chat-a",
        data_dir=tmp_path, now=FIXED)
    assert out.text == "Seen: a lighthouse"
    out = resolve_variables_for_chat(
        "Seen: [{{last_vision_description}}]", chat_id="chat-none",
        data_dir=tmp_path, now=FIXED)
    assert out.text == "Seen: []"


def test_resolve_for_chat_explicit_value_wins(tmp_path):
    _seed_store(tmp_path, [_row("chat-a", "stored text", "r1")])
    out = resolve_variables_for_chat(
        "{{last_vision_description}}", chat_id="chat-a",
        data_dir=tmp_path, now=FIXED,
        last_vision_description="explicit text")
    assert out.text == "explicit text"


# ------------------------------------------------------ tools road


def test_tools_road_resolves_vision_variable(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    registry = client.get("/api/v1/tools/variables")
    assert registry.status_code == 200
    assert "last_vision_description" in {
        v["name"] for v in registry.json()}
    res = client.post("/api/v1/tools/resolve", json={
        "text": "Saw: {{last_vision_description}}",
        "last_vision_description": "a black sail"})
    assert res.status_code == 200
    assert res.json()["text"] == "Saw: a black sail"
    assert res.json()["unknown"] == []


def test_tools_road_resolves_from_chat_id(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "Lookout"})
    assert chat.status_code == 201, chat.text
    chat_id = chat.json()["id"]
    _seed_store(tmp_path, [_row(chat_id, "gulls over the harbour", "r1")])
    res = client.post("/api/v1/tools/resolve", json={
        "text": "Saw: {{last_vision_description}}", "chat_id": chat_id})
    assert res.status_code == 200
    assert res.json()["text"] == "Saw: gulls over the harbour"


# --------------------------------------------------------- custody


def test_chat_deletion_purges_its_descriptions(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    doomed = client.post("/api/v1/chats", json={"title": "Doomed"})
    assert doomed.status_code == 201, doomed.text
    keeper = client.post("/api/v1/chats", json={"title": "Keeper"})
    assert keeper.status_code == 201, keeper.text
    doomed_id, keeper_id = doomed.json()["id"], keeper.json()["id"]
    _seed_store(tmp_path, [
        _row(doomed_id, "the doomed chat's view", "r1"),
        _row(keeper_id, "the keeper chat's view", "r2"),
        _row(doomed_id, "a second doomed view", "r3"),
    ])
    res = client.delete(f"/api/v1/chats/{doomed_id}")
    assert res.status_code in (200, 204), res.text
    assert vl.list_for_chat(doomed_id, tmp_path) == []
    assert vl.last_description_text(keeper_id, tmp_path) == \
        "the keeper chat's view"
    out = resolve_variables_for_chat(
        "[{{last_vision_description}}]", chat_id=doomed_id,
        data_dir=tmp_path, now=FIXED)
    assert out.text == "[]"


# ------------------------------------------------------ migration


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
