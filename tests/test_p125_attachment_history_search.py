"""P-125 - Attachment owner-wide history & literal search (Part VIII, DERIVED).

Pins: the AttachmentStore history surface (list_for_owner /
search - owner-scoped FIRST so foreign rows are never matched
or counted, literal case-insensitive substring over the
filename and the image sha256 ONLY, exact chat / message /
format filters, unknown format refused plainly, paging with
the full total), the literal-scope honesty pin (the format
is a filter, never search text - a query naming a format
does not match rows whose filename/sha lack it), the
owner-scoped HTTP road (GET /vision/attachments/history,
404 + 422 shapes, foreign rows invisible even to counts),
the route-order pin (the history road is declared before
{attachment_id} and BOTH roads stay live), the per-chat list
road unchanged, and the migration head staying 0041 (NO
migration). Search here is literal text matching, never
semantic. No network: fixtures only.
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
from runmal.vision import attachments as att

NOW = "2026-11-08T15:00:00+00:00"
LATER = "2026-11-08T15:05:00+00:00"


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


def make_gif_bytes(width=3, height=2) -> bytes:
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00"


PNG = make_png_bytes()
PNG2 = make_png_bytes(2, 2, (9, 9, 9))
GIF = make_gif_bytes()
PNG_SHA = hashlib.sha256(PNG).hexdigest()
PNG_B64 = base64.b64encode(PNG).decode()
GIF_B64 = base64.b64encode(GIF).decode()


def _store(tmp_path):
    return att.AttachmentStore(tmp_path)


def _attach(store, chat_id="c1", owner_id="u1", data=PNG,
            message_id=None, filename="", now=NOW):
    return att.attach_image(
        store, chat_id=chat_id, owner_id=owner_id, data=data,
        message_id=message_id, filename=filename, now=now)


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


def _post_attachment(client, chat_id, b64=PNG_B64, filename="",
                     message_id=None):
    body = {"chat_id": chat_id, "image_b64": b64, "filename": filename}
    if message_id:
        body["message_id"] = message_id
    res = client.post("/api/v1/vision/attachments", json=body)
    assert res.status_code == 201
    return res.json()


# --------------------------------------------------- store: reads


def test_list_for_owner_append_order_and_isolation(tmp_path):
    store = _store(tmp_path)
    a = _attach(store, chat_id="c1", filename="first.png")
    b = _attach(store, chat_id="c2", filename="second.png", now=LATER)
    _attach(store, chat_id="c1", owner_id="other", filename="foreign.png")
    fresh = _store(tmp_path)
    assert [r.id for r in fresh.list_for_owner("u1")] == [a.id, b.id]
    assert len(fresh.list_for_owner("other")) == 1
    assert fresh.list_for_owner("nobody") == []


def test_search_literal_filename_case_insensitive(tmp_path):
    store = _store(tmp_path)
    a = _attach(store, filename="Sunset Over Fjord.png")
    _attach(store, filename="portrait.png", now=LATER)
    rows, total = store.search("u1", "sunset")
    assert total == 1 and [r.id for r in rows] == [a.id]
    rows, total = store.search("u1", "FJORD")
    assert total == 1 and rows[0].id == a.id
    rows, total = store.search("u1", "no-such-name")
    assert total == 0 and rows == []


def test_search_matches_sha256_substring(tmp_path):
    store = _store(tmp_path)
    a = _attach(store, filename="plain-name")
    _attach(store, data=PNG2, filename="other-name", now=LATER)
    rows, total = store.search("u1", PNG_SHA[:12])
    assert total == 1 and rows[0].id == a.id
    rows, total = store.search("u1", PNG_SHA[:12].upper())
    assert total == 1 and rows[0].id == a.id


def test_search_empty_query_is_owner_history_across_chats(tmp_path):
    store = _store(tmp_path)
    a = _attach(store, chat_id="c1")
    b = _attach(store, chat_id="c2", now=LATER)
    c = _attach(store, chat_id="c3", data=GIF, now=LATER)
    rows, total = store.search("u1", "")
    assert total == 3 and [r.id for r in rows] == [a.id, b.id, c.id]


def test_search_owner_isolation_counts(tmp_path):
    store = _store(tmp_path)
    _attach(store, owner_id="other", filename="sunset.png")
    _attach(store, owner_id="other", chat_id="c9")
    rows, total = store.search("u1", "")
    assert total == 0 and rows == []
    rows, total = store.search("u1", "sunset")
    assert total == 0


def test_search_format_is_filter_not_search_text(tmp_path):
    # Honesty pin: the literal search reads the filename and
    # the sha256 ONLY. A PNG whose filename and digest lack
    # the text "png" must NOT match the query "png" - the
    # format is an exact filter, never search text, and no
    # content claim is ever searched.
    store = _store(tmp_path)
    _attach(store, filename="portrait")
    rows, total = store.search("u1", "png")
    assert total == 0 and rows == []
    rows, total = store.search("u1", "", image_format="png")
    assert total == 1


def test_search_filters_chat_message_format(tmp_path):
    store = _store(tmp_path)
    a = _attach(store, chat_id="c1", message_id="m1", filename="a")
    b = _attach(store, chat_id="c2", filename="b", now=LATER)
    c = _attach(store, chat_id="c2", data=GIF, filename="c", now=LATER)
    rows, total = store.search("u1", "", chat_id="c2")
    assert total == 2 and [r.id for r in rows] == [b.id, c.id]
    rows, total = store.search("u1", "", message_id="m1")
    assert total == 1 and rows[0].id == a.id
    rows, total = store.search("u1", "", message_id="no-such")
    assert total == 0 and rows == []
    rows, total = store.search("u1", "", image_format="gif")
    assert total == 1 and rows[0].id == c.id
    rows, total = store.search("u1", "", chat_id="c2",
                               image_format="png")
    assert total == 1 and rows[0].id == b.id


def test_search_unknown_format_refused(tmp_path):
    store = _store(tmp_path)
    _attach(store)
    with pytest.raises(att.AttachmentError):
        store.search("u1", "", image_format="bmp")
    with pytest.raises(att.AttachmentError):
        store.search("u1", "", image_format="PNG")


def test_search_paging_and_total(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        _attach(store, filename=f"shot-{i}", now=NOW)
    rows, total = store.search("u1", "shot", limit=2, offset=0)
    assert total == 5 and len(rows) == 2
    rows, total = store.search("u1", "shot", limit=2, offset=4)
    assert total == 5 and len(rows) == 1
    rows, total = store.search("u1", "shot", limit=0, offset=-3)
    assert total == 5 and len(rows) == 1
    rows, total = store.search("u1", "shot", limit=9999)
    assert total == 5 and len(rows) == 5


def test_search_tolerant_corrupt_store(tmp_path):
    (tmp_path / "vision_attachments.json").write_text("{ not json")
    rows, total = _store(tmp_path).search("u1", "x")
    assert rows == [] and total == 0


# ------------------------------------------------------------ HTTP


def test_http_history_lists_across_chats(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    c2 = _chat(client, title="two")
    _post_attachment(client, c1, filename="first.png")
    _post_attachment(client, c2, filename="second.png")
    res = client.get("/api/v1/vision/attachments/history")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2 and body["returned"] == 2
    assert {a["chat_id"] for a in body["attachments"]} == {c1, c2}
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/vision/attachments/history" in paths


def test_http_history_query_filters_and_paging(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    c2 = _chat(client, title="two")
    m1 = _message(client, c1)
    _post_attachment(client, c1, filename="Sunset.png",
                     message_id=m1)
    _post_attachment(client, c2, filename="portrait.png")
    _post_attachment(client, c2, b64=GIF_B64, filename="clip.gif")
    by_q = client.get("/api/v1/vision/attachments/history",
                      params={"q": "SUNSET"})
    assert by_q.json()["total"] == 1
    by_sha = client.get("/api/v1/vision/attachments/history",
                        params={"q": PNG_SHA[:10]})
    assert by_sha.json()["total"] == 2
    by_chat = client.get("/api/v1/vision/attachments/history",
                         params={"chat_id": c2})
    assert by_chat.json()["total"] == 2
    by_msg = client.get("/api/v1/vision/attachments/history",
                        params={"message_id": m1})
    assert by_msg.json()["total"] == 1
    assert by_msg.json()["attachments"][0]["message_id"] == m1
    by_fmt = client.get("/api/v1/vision/attachments/history",
                        params={"image_format": "gif"})
    assert by_fmt.json()["total"] == 1
    page = client.get("/api/v1/vision/attachments/history",
                      params={"limit": 1, "offset": 1})
    body = page.json()
    assert body["total"] == 3 and body["returned"] == 1
    assert body["limit"] == 1 and body["offset"] == 1
    assert body["q"] == "" and body["image_format"] is None


def test_http_history_404_and_422_shapes(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    missing = client.get("/api/v1/vision/attachments/history",
                         params={"chat_id": "no-such-chat"})
    assert missing.status_code == 404
    bad_fmt = client.get("/api/v1/vision/attachments/history",
                         params={"image_format": "bmp"})
    assert bad_fmt.status_code == 422
    assert "png" in bad_fmt.json()["detail"]


def test_http_history_owner_isolation(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    foreign = _attach(_store(tmp_path), chat_id="c-foreign",
                      owner_id="someone-else", filename="sunset.png")
    body = client.get("/api/v1/vision/attachments/history").json()
    assert body["total"] == 0 and body["attachments"] == []
    searched = client.get("/api/v1/vision/attachments/history",
                          params={"q": "sunset"}).json()
    assert searched["total"] == 0
    got = client.get(f"/api/v1/vision/attachments/{foreign.id}")
    assert got.status_code == 404


def test_http_route_order_history_and_single_get(tmp_path, monkeypatch):
    # The history road is declared before {attachment_id}:
    # the literal segment must reach the history handler,
    # and the single-record road must stay live beside it.
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    posted = _post_attachment(client, c1, filename="kept.png")
    hist = client.get("/api/v1/vision/attachments/history")
    assert hist.status_code == 200
    assert hist.json()["total"] == 1
    single = client.get(f"/api/v1/vision/attachments/{posted['id']}")
    assert single.status_code == 200
    assert single.json()["id"] == posted["id"]
    assert single.json()["filename"] == "kept.png"


def test_http_per_chat_list_unchanged(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    c2 = _chat(client, title="two")
    _post_attachment(client, c1, filename="in-one.png")
    _post_attachment(client, c2, filename="in-two.png")
    body = client.get("/api/v1/vision/attachments",
                      params={"chat_id": c1}).json()
    assert body["chat_id"] == c1
    assert len(body["attachments"]) == 1
    assert body["attachments"][0]["filename"] == "in-one.png"


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"
