"""P-122 - Vision description history, search & custody (Part VIII, DERIVED).

Pins: the VisionStore history surface (get / list_for_owner /
search - owner-scoped FIRST so foreign rows are never matched
or counted, literal case-insensitive substring over the
description text and the question only, exact chat / source /
provider filters, unknown source_kind refused plainly, paging
with the full total), the custody verbs (remove deletes
exactly one record; purge_source removes only the rows derived
from one named source and an empty ref purges nothing), the
owner-scoped HTTP roads (GET /vision/history, GET + DELETE
/vision/descriptions/{id}, 404 + 422 shapes, foreign rows
invisible even to counts), source custody end to end (deleting
an attachment - directly or through message deletion - purges
its derived descriptions, and the last-description surface
follows), and the migration head staying 0041 (NO migration).
Search here is literal text matching, never semantic. No
network: fixtures only.
"""

from __future__ import annotations

import base64
import hashlib
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.prompt import vision_link
from runmal.vision import selection as sel
from runmal.vision import service as vis

NOW = "2026-11-08T14:00:00+00:00"
LATER = "2026-11-08T14:05:00+00:00"


def make_png_bytes(width=6, height=4, color=(30, 200, 30)) -> bytes:
    def chunk(ctype, data):
        raw = ctype + data
        return struct.pack(">I", len(data)) + raw + struct.pack(
            ">I", zlib.crc32(raw) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(color) * width
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


PNG = make_png_bytes()
PNG2 = make_png_bytes(2, 2)
PNG_SHA = hashlib.sha256(PNG).hexdigest()
PNG_B64 = base64.b64encode(PNG).decode()


def _store(tmp_path):
    return vis.VisionStore(tmp_path / "vision_descriptions.json")


def _describe(store, chat_id="c1", owner_id="u1", data=PNG,
              provider=None, question="", source_kind="inline",
              source_ref="", now=NOW):
    return vis.describe_image(
        store, chat_id=chat_id, owner_id=owner_id, image_bytes=data,
        provider=provider or vis.MetadataVisionProvider(),
        question=question, source_kind=source_kind,
        source_ref=source_ref, now=now)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory, db_path


def _chat(client, **kw):
    return client.post("/api/v1/chats", json=kw).json()["id"]


def _message(client, chat_id, content="look at this"):
    res = client.post(f"/api/v1/chats/{chat_id}/messages",
                      json={"role": "user", "content": content})
    assert res.status_code == 201
    return res.json()["id"]


# --------------------------------------------------- store: reads


def test_store_get_and_list_for_owner(tmp_path):
    store = _store(tmp_path)
    a = _describe(store, chat_id="c1")
    b = _describe(store, chat_id="c2", now=LATER)
    _describe(store, chat_id="c1", owner_id="other")
    fresh = _store(tmp_path)
    assert fresh.get(a.id).id == a.id
    assert fresh.get("nope") is None
    assert [r.id for r in fresh.list_for_owner("u1")] == [a.id, b.id]
    assert len(fresh.list_for_owner("other")) == 1
    assert fresh.list_for_owner("nobody") == []


def test_search_literal_matches_text_and_question(tmp_path):
    store = _store(tmp_path)
    a = _describe(store, question="Is this a SUNSET?")
    b = _describe(store, data=PNG2, question="portrait?", now=LATER)
    rows, total = store.search("u1", "sunset")
    assert total == 1 and [r.id for r in rows] == [a.id]
    rows, total = store.search("u1", "METADATA")
    assert total == 2
    rows, total = store.search("u1", PNG_SHA[:12])
    assert total == 1 and rows[0].id == a.id
    rows, total = store.search("u1", "no-such-text")
    assert total == 0 and rows == []
    rows, total = store.search("u1", "")
    assert total == 2 and [r.id for r in rows] == [a.id, b.id]


def test_search_owner_isolation_counts(tmp_path):
    store = _store(tmp_path)
    _describe(store, owner_id="other", question="sunset")
    _describe(store, owner_id="other", chat_id="c9")
    rows, total = store.search("u1", "")
    assert total == 0 and rows == []
    rows, total = store.search("u1", "sunset")
    assert total == 0


def test_search_filters(tmp_path):
    store = _store(tmp_path)
    a = _describe(store, chat_id="c1")
    b = _describe(store, chat_id="c2", now=LATER,
                  provider=sel.DeterministicTestVisionProvider())
    c = _describe(store, chat_id="c2", now=LATER,
                  source_kind="attachment", source_ref="att-1")
    rows, total = store.search("u1", "", chat_id="c2")
    assert total == 2 and [r.id for r in rows] == [b.id, c.id]
    rows, total = store.search("u1", "", source_kind="attachment")
    assert total == 1 and rows[0].id == c.id
    rows, total = store.search("u1", "", provider_road="metadata")
    assert total == 2 and a.id in [r.id for r in rows]
    rows, total = store.search(
        "u1", "", provider_road="deterministic_test")
    assert total == 1 and rows[0].id == b.id


def test_search_unknown_source_kind_refused(tmp_path):
    store = _store(tmp_path)
    _describe(store)
    with pytest.raises(vis.VisionError):
        store.search("u1", "", source_kind="bogus")


def test_search_paging_and_total(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        _describe(store, question=f"q{i}", now=NOW)
    rows, total = store.search("u1", "", limit=2, offset=0)
    assert total == 5 and len(rows) == 2
    rows, total = store.search("u1", "", limit=2, offset=4)
    assert total == 5 and len(rows) == 1
    rows, total = store.search("u1", "", limit=0, offset=-3)
    assert total == 5 and len(rows) == 1
    rows, total = store.search("u1", "", limit=9999)
    assert total == 5 and len(rows) == 5


def test_search_tolerant_corrupt_store(tmp_path):
    path = tmp_path / "vision_descriptions.json"
    path.write_text("{ not json")
    rows, total = vis.VisionStore(path).search("u1", "x")
    assert rows == [] and total == 0


# ------------------------------------------------- store: custody


def test_remove_deletes_exactly_one_and_last_follows(tmp_path):
    store = _store(tmp_path)
    a = _describe(store)
    b = _describe(store, data=PNG2, now=LATER)
    removed = store.remove(b.id)
    assert removed is not None and removed.id == b.id
    fresh = _store(tmp_path)
    assert [r.id for r in fresh.list_for_chat("c1")] == [a.id]
    assert fresh.last_for_chat("c1").id == a.id
    assert store.remove(b.id) is None
    assert store.remove("nope") is None


def test_purge_source_is_scoped(tmp_path):
    store = _store(tmp_path)
    keep_inline = _describe(store)
    gone1 = _describe(store, source_kind="attachment",
                      source_ref="att-1", now=LATER)
    gone2 = _describe(store, chat_id="c2", source_kind="attachment",
                      source_ref="att-1", now=LATER)
    keep_asset = _describe(store, source_kind="asset",
                           source_ref="att-1", now=LATER)
    keep_other_att = _describe(store, source_kind="attachment",
                               source_ref="att-2", now=LATER)
    assert store.purge_source("attachment", "att-1") == 2
    fresh = _store(tmp_path)
    ids = [r.id for r in fresh.list_for_owner("u1")]
    assert gone1.id not in ids and gone2.id not in ids
    assert keep_inline.id in ids
    assert keep_asset.id in ids
    assert keep_other_att.id in ids
    assert store.purge_source("attachment", "att-1") == 0
    assert store.purge_source("attachment", "") == 0
    assert len(_store(tmp_path).list_for_owner("u1")) == 3


# ------------------------------------------------------------ HTTP


def test_http_history_lists_across_chats(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    c2 = _chat(client, title="two")
    client.post("/api/v1/vision/describe", json={
        "chat_id": c1, "image_b64": PNG_B64, "question": "first"})
    client.post("/api/v1/vision/describe", json={
        "chat_id": c2, "image_b64": PNG_B64, "question": "second"})
    res = client.get("/api/v1/vision/history")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2 and body["returned"] == 2
    assert {d["chat_id"] for d in body["descriptions"]} == {c1, c2}
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/vision/history" in paths
    assert "/api/v1/vision/descriptions/{description_id}" in paths


def test_http_history_query_filters_and_paging(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    c2 = _chat(client, title="two")
    client.post("/api/v1/vision/describe", json={
        "chat_id": c1, "image_b64": PNG_B64, "question": "sunset?"})
    client.post("/api/v1/vision/describe", json={
        "chat_id": c2, "image_b64": PNG_B64, "question": "portrait?",
        "provider": "deterministic_test"})
    by_q = client.get("/api/v1/vision/history", params={"q": "SUNSET"})
    assert by_q.json()["total"] == 1
    by_chat = client.get("/api/v1/vision/history",
                         params={"chat_id": c2})
    assert by_chat.json()["total"] == 1
    assert by_chat.json()["descriptions"][0]["chat_id"] == c2
    by_kind = client.get("/api/v1/vision/history",
                         params={"source_kind": "inline"})
    assert by_kind.json()["total"] == 2
    by_road = client.get(
        "/api/v1/vision/history",
        params={"provider_road": "deterministic_test"})
    assert by_road.json()["total"] == 1
    page = client.get("/api/v1/vision/history",
                      params={"limit": 1, "offset": 1})
    body = page.json()
    assert body["total"] == 2 and body["returned"] == 1
    assert body["limit"] == 1 and body["offset"] == 1


def test_http_history_404_and_422_shapes(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    missing = client.get("/api/v1/vision/history",
                         params={"chat_id": "no-such-chat"})
    assert missing.status_code == 404
    bad_kind = client.get("/api/v1/vision/history",
                          params={"source_kind": "bogus"})
    assert bad_kind.status_code == 422
    bad_road = client.get("/api/v1/vision/history",
                          params={"provider_road": "bogus"})
    assert bad_road.status_code == 422
    assert "metadata" in bad_road.json()["detail"]


def test_http_history_owner_isolation(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    foreign = _describe(_store(tmp_path), chat_id="c-foreign",
                        owner_id="someone-else", question="sunset")
    body = client.get("/api/v1/vision/history").json()
    assert body["total"] == 0 and body["descriptions"] == []
    searched = client.get("/api/v1/vision/history",
                          params={"q": "sunset"}).json()
    assert searched["total"] == 0
    got = client.get(f"/api/v1/vision/descriptions/{foreign.id}")
    assert got.status_code == 404
    deleted = client.delete(f"/api/v1/vision/descriptions/{foreign.id}")
    assert deleted.status_code == 404
    assert _store(tmp_path).get(foreign.id) is not None


def test_http_get_and_delete_single_description(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    first = client.post("/api/v1/vision/describe", json={
        "chat_id": c1, "image_b64": PNG_B64,
        "question": "first"}).json()
    second = client.post("/api/v1/vision/describe", json={
        "chat_id": c1, "image_b64": PNG_B64,
        "question": "second"}).json()
    got = client.get(f"/api/v1/vision/descriptions/{second['id']}")
    assert got.status_code == 200
    assert got.json()["question"] == "second"
    deleted = client.delete(
        f"/api/v1/vision/descriptions/{second['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": second["id"]}
    assert client.get(
        f"/api/v1/vision/descriptions/{second['id']}").status_code == 404
    last = client.get("/api/v1/vision/last", params={"chat_id": c1})
    assert last.status_code == 200
    assert last.json()["id"] == first["id"]
    assert vision_link.last_description_text(c1, data_dir=tmp_path) == first["description"]
    again = client.delete(f"/api/v1/vision/descriptions/{second['id']}")
    assert again.status_code == 404
    missing = client.get("/api/v1/vision/descriptions/nope")
    assert missing.status_code == 404


# --------------------------------------------- HTTP source custody


def test_http_attachment_delete_purges_derived(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="pics")
    att_id = client.post("/api/v1/vision/attachments", json={
        "chat_id": c1, "image_b64": PNG_B64}).json()["id"]
    derived = client.post("/api/v1/vision/describe", json={
        "chat_id": c1, "attachment_id": att_id,
        "question": "attached?"})
    assert derived.status_code == 200
    inline = client.post("/api/v1/vision/describe", json={
        "chat_id": c1, "image_b64": PNG_B64, "question": "inline?"})
    assert inline.status_code == 200
    deleted = client.delete(f"/api/v1/vision/attachments/{att_id}")
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["deleted"] is True
    assert body["descriptions_purged"] == 1
    history = client.get("/api/v1/vision/history").json()
    assert history["total"] == 1
    assert history["descriptions"][0]["source_kind"] == "inline"
    last = client.get("/api/v1/vision/last", params={"chat_id": c1})
    assert last.json()["id"] == inline.json()["id"]


def test_http_message_delete_purges_derived(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="pics")
    msg_id = _message(client, c1)
    att_id = client.post("/api/v1/vision/attachments", json={
        "chat_id": c1, "message_id": msg_id,
        "image_b64": PNG_B64}).json()["id"]
    described = client.post("/api/v1/vision/describe", json={
        "chat_id": c1, "attachment_id": att_id})
    assert described.status_code == 200
    assert client.get("/api/v1/vision/history").json()["total"] == 1
    deleted = client.delete(f"/api/v1/chats/{c1}/messages/{msg_id}")
    assert deleted.status_code in (200, 204)
    assert client.get("/api/v1/vision/history").json()["total"] == 0
    assert _store(tmp_path).list_for_owner(
        described.json()["owner_id"]) == []
    last = client.get("/api/v1/vision/last", params={"chat_id": c1})
    assert last.status_code == 404


# ------------------------------------------------------------ pins


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"
