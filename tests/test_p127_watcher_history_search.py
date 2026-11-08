"""P-127 - Watcher owner-wide history & literal search (Part VIII, DERIVED).

Pins: the WatchStore history surface (search - owner-scoped
FIRST so foreign registrations are never matched or counted,
literal case-insensitive substring over the folder path ONLY,
exact chat / enabled / recursive filters, paging with the
full total, limit clamped / offset floored), the ingested
surface (list_ingested_for_owner resolving ownership through
the watch registrations; search_ingested - owner scoping via
watch ownership FIRST, literal substring over source_path
and sha256 ONLY, exact watch / chat filters, paging), the
literal-scope honesty pins (filters are never search text: a
query naming a chat id, an attachment id or a watch id does
not match through them), reads-write-nothing, the owner-
scoped HTTP roads (GET /vision/watch-folders/history and
GET /vision/watch-folders/ingested/history - cross-chat
listing, filters, paging, 404 filter shapes, foreign rows
invisible even to counts), the route-order pins (both
history roads declared before {watch_id} and the single-
watch + per-watch ingested roads stay live), the per-chat
list road unchanged, and the migration head staying 0041
(NO migration). Search here is literal text matching, never
semantic. No network, no daemon: fixtures only.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.vision import watcher as w

NOW = "2026-11-08T16:00:00+00:00"
SHA_A = "aa" * 32
SHA_B = "bb" * 32
SHA_C = "cc" * 32


def make_png_bytes(width=6, height=4, color=(200, 30, 30)) -> bytes:
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
PNG_SHA = hashlib.sha256(PNG).hexdigest()


def _store(tmp_path):
    return w.WatchStore(tmp_path / "data")


def _register(store, path, chat_id="c1", owner="u1", **kw):
    return w.register_watch(
        store, owner_id=owner, chat_id=chat_id,
        path=path, now=NOW, **kw)


def _ingested(store, watch_id, attachment_id, path="/inbox/a.png",
              sha=SHA_A):
    return store.record_ingested(w.IngestedRecord(
        watch_id=watch_id, source_path=path, sha256=sha,
        size=len(PNG), attachment_id=attachment_id,
        ingested_at=NOW))


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


def _post_watch(client, chat_id, path, recursive=False):
    res = client.post("/api/v1/vision/watch-folders",
                      json={"chat_id": chat_id, "path": path,
                            "recursive": recursive})
    assert res.status_code == 201
    return res.json()


# ------------------------------------------- store: watch search


def test_search_empty_query_is_owner_history_across_chats(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/photos", chat_id="c1")
    b = _register(store, "/media/videos", chat_id="c2")
    _register(store, "/media/photos", chat_id="c9", owner="other")
    rows, total = store.search("u1", "")
    assert total == 2
    assert [r.id for r in rows] == [a.id, b.id]
    rows, total = store.search("nobody", "")
    assert rows == [] and total == 0


def test_search_literal_path_case_insensitive(tmp_path):
    store = _store(tmp_path)
    _register(store, "/Media/HolidayPhotos", chat_id="c1")
    _register(store, "/media/backups", chat_id="c1")
    rows, total = store.search("u1", "holidayphotos")
    assert total == 1 and rows[0].path == "/Media/HolidayPhotos"
    rows, total = store.search("u1", "MEDIA")
    assert total == 2
    rows, total = store.search("u1", "no-such-folder")
    assert rows == [] and total == 0


def test_search_literal_scope_pin_filters_are_not_search_text(tmp_path):
    store = _store(tmp_path)
    _register(store, "/media/photos", chat_id="chat-alpha")
    # the chat id is a filter, never search text
    rows, total = store.search("u1", "chat-alpha")
    assert rows == [] and total == 0
    # neither is the enabled flag's name
    rows, total = store.search("u1", "true")
    assert rows == [] and total == 0


def test_search_filters_chat_enabled_recursive(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/a", chat_id="c1", recursive=True)
    b = _register(store, "/media/b", chat_id="c2")
    store.set_enabled(b.id, False)
    rows, total = store.search("u1", "", chat_id="c1")
    assert total == 1 and rows[0].id == a.id
    rows, total = store.search("u1", "", enabled=False)
    assert total == 1 and rows[0].id == b.id
    rows, total = store.search("u1", "", enabled=True)
    assert total == 1 and rows[0].id == a.id
    rows, total = store.search("u1", "", recursive=True)
    assert total == 1 and rows[0].id == a.id
    rows, total = store.search("u1", "media", chat_id="c2",
                               enabled=False, recursive=False)
    assert total == 1 and rows[0].id == b.id
    rows, total = store.search("u1", "", chat_id="c-unknown")
    assert rows == [] and total == 0


def test_search_paging_total_and_clamps(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        _register(store, f"/media/f{i}", chat_id="c1")
    rows, total = store.search("u1", "media", limit=2, offset=0)
    assert total == 5 and len(rows) == 2
    rows, total = store.search("u1", "media", limit=2, offset=4)
    assert total == 5 and len(rows) == 1
    rows, _ = store.search("u1", "media", limit=0)
    assert len(rows) == 1  # limit clamped up to 1
    rows, _ = store.search("u1", "media", limit=9999)
    assert len(rows) == 5  # limit clamped down to 200, all fit
    rows, _ = store.search("u1", "media", offset=-3)
    assert len(rows) == 5  # offset floored at 0


# ---------------------------------------- store: ingested search


def test_list_ingested_for_owner_resolves_through_watches(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/a", chat_id="c1")
    b = _register(store, "/media/b", chat_id="c2")
    foreign = _register(store, "/media/x", chat_id="c9", owner="other")
    _ingested(store, a.id, "att-1")
    _ingested(store, b.id, "att-2", path="/media/b/c.png", sha=SHA_B)
    _ingested(store, foreign.id, "att-3", path="/media/x/d.png",
              sha=SHA_C)
    rows = store.list_ingested_for_owner("u1")
    assert [r.attachment_id for r in rows] == ["att-1", "att-2"]
    assert [r.attachment_id for r in
            store.list_ingested_for_owner("other")] == ["att-3"]
    assert store.list_ingested_for_owner("nobody") == []


def test_search_ingested_literal_path_and_sha(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/a", chat_id="c1")
    _ingested(store, a.id, "att-1", path="/media/a/Sunset.png",
              sha=SHA_A)
    _ingested(store, a.id, "att-2", path="/media/a/portrait.png",
              sha=SHA_B)
    rows, total = store.search_ingested("u1", "sunset")
    assert total == 1 and rows[0].attachment_id == "att-1"
    rows, total = store.search_ingested("u1", SHA_B[:12])
    assert total == 1 and rows[0].attachment_id == "att-2"
    rows, total = store.search_ingested("u1", "")
    assert total == 2


def test_search_ingested_scope_pin_ids_are_not_search_text(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/a", chat_id="c1")
    _ingested(store, a.id, "att-secret-1", path="/media/a/pic.png",
              sha=SHA_A)
    # the attachment id and the watch id are filters, never text
    rows, total = store.search_ingested("u1", "att-secret-1")
    assert rows == [] and total == 0
    rows, total = store.search_ingested("u1", a.id)
    assert rows == [] and total == 0


def test_search_ingested_filters_watch_chat_and_foreign(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/a", chat_id="c1")
    b = _register(store, "/media/b", chat_id="c2")
    foreign = _register(store, "/media/x", chat_id="c9", owner="other")
    _ingested(store, a.id, "att-1", path="/media/a/one.png", sha=SHA_A)
    _ingested(store, b.id, "att-2", path="/media/b/two.png", sha=SHA_B)
    _ingested(store, foreign.id, "att-3", path="/media/x/one.png",
              sha=SHA_C)
    rows, total = store.search_ingested("u1", "", watch_id=a.id)
    assert total == 1 and rows[0].attachment_id == "att-1"
    rows, total = store.search_ingested("u1", "", chat_id="c2")
    assert total == 1 and rows[0].attachment_id == "att-2"
    # a foreign watch named as a filter matches nothing, and the
    # foreign record is invisible even unfiltered / to counts
    rows, total = store.search_ingested("u1", "", watch_id=foreign.id)
    assert rows == [] and total == 0
    rows, total = store.search_ingested("u1", "one.png")
    assert total == 1 and rows[0].attachment_id == "att-1"
    rows, total = store.search_ingested("u1", "", chat_id="c9")
    assert rows == [] and total == 0


def test_search_ingested_paging(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/a", chat_id="c1")
    for i in range(4):
        _ingested(store, a.id, f"att-{i}", path=f"/media/a/f{i}.png",
                  sha=f"{i:02x}" * 32)
    rows, total = store.search_ingested("u1", "media", limit=3)
    assert total == 4 and len(rows) == 3
    rows, total = store.search_ingested("u1", "media", limit=3,
                                        offset=3)
    assert total == 4 and len(rows) == 1


def test_history_reads_write_nothing(tmp_path):
    store = _store(tmp_path)
    a = _register(store, "/media/a", chat_id="c1")
    _ingested(store, a.id, "att-1")
    before = store.index_path.read_bytes()
    store.search("u1", "media")
    store.search_ingested("u1", "media")
    store.list_ingested_for_owner("u1")
    store.list_for_owner("u1")
    assert store.index_path.read_bytes() == before


# ------------------------------------------------------------ HTTP


def test_http_watch_history_across_chats(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    c2 = _chat(client, title="two")
    _post_watch(client, c1, "/media/photos")
    _post_watch(client, c2, "/media/videos", recursive=True)
    body = client.get("/api/v1/vision/watch-folders/history").json()
    assert body["total"] == 2 and body["returned"] == 2
    assert [r["path"] for r in body["watch_folders"]] == [
        "/media/photos", "/media/videos"]
    # the per-chat list road is unchanged
    one = client.get("/api/v1/vision/watch-folders",
                     params={"chat_id": c1}).json()
    assert len(one["watch_folders"]) == 1
    assert one["watch_folders"][0]["path"] == "/media/photos"


def test_http_watch_history_query_filters_paging(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    c2 = _chat(client, title="two")
    _post_watch(client, c1, "/media/photos")
    second = _post_watch(client, c2, "/media/photos-backup")
    _post_watch(client, c2, "/other/stuff")
    body = client.get("/api/v1/vision/watch-folders/history",
                      params={"q": "PHOTOS"}).json()
    assert body["total"] == 2
    body = client.get("/api/v1/vision/watch-folders/history",
                      params={"chat_id": c2}).json()
    assert body["total"] == 2
    assert all(r["chat_id"] == c2 for r in body["watch_folders"])
    client.patch(f"/api/v1/vision/watch-folders/{second['id']}",
                 json={"enabled": False})
    body = client.get("/api/v1/vision/watch-folders/history",
                      params={"enabled": False}).json()
    assert body["total"] == 1
    assert body["watch_folders"][0]["id"] == second["id"]
    body = client.get("/api/v1/vision/watch-folders/history",
                      params={"limit": 1, "offset": 1}).json()
    assert body["total"] == 3 and body["returned"] == 1
    assert body["limit"] == 1 and body["offset"] == 1


def test_http_history_404_filter_shapes(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/vision/watch-folders/history",
                     params={"chat_id": "no-such-chat"})
    assert res.status_code == 404
    res = client.get("/api/v1/vision/watch-folders/ingested/history",
                     params={"watch_id": "no-such-watch"})
    assert res.status_code == 404
    res = client.get("/api/v1/vision/watch-folders/ingested/history",
                     params={"chat_id": "no-such-chat"})
    assert res.status_code == 404


def test_http_ingested_history_end_to_end(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "sunset.png").write_bytes(PNG)
    c1 = _chat(client, title="one")
    watch = _post_watch(client, c1, str(folder))
    scan = client.post(
        f"/api/v1/vision/watch-folders/{watch['id']}/scan")
    assert scan.status_code == 200
    assert len(scan.json()["ingested"]) == 1
    body = client.get(
        "/api/v1/vision/watch-folders/ingested/history").json()
    assert body["total"] == 1
    assert body["ingested"][0]["source_path"].endswith("sunset.png")
    assert body["ingested"][0]["sha256"] == PNG_SHA
    by_name = client.get(
        "/api/v1/vision/watch-folders/ingested/history",
        params={"q": "SUNSET"}).json()
    assert by_name["total"] == 1
    by_sha = client.get(
        "/api/v1/vision/watch-folders/ingested/history",
        params={"q": PNG_SHA[:16]}).json()
    assert by_sha["total"] == 1
    by_watch = client.get(
        "/api/v1/vision/watch-folders/ingested/history",
        params={"watch_id": watch["id"]}).json()
    assert by_watch["total"] == 1
    by_chat = client.get(
        "/api/v1/vision/watch-folders/ingested/history",
        params={"chat_id": c1}).json()
    assert by_chat["total"] == 1
    # the per-watch ingested road stays live beside it
    per = client.get(
        f"/api/v1/vision/watch-folders/{watch['id']}/ingested").json()
    assert len(per["ingested"]) == 1


def test_http_history_owner_isolation(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    store = w.WatchStore(tmp_path)
    foreign = _register(store, "/media/foreign", chat_id="c-foreign",
                        owner="someone-else")
    _ingested(store, foreign.id, "att-foreign",
              path="/media/foreign/secret.png", sha=SHA_C)
    body = client.get("/api/v1/vision/watch-folders/history").json()
    assert body["total"] == 0 and body["watch_folders"] == []
    body = client.get("/api/v1/vision/watch-folders/history",
                      params={"q": "foreign"}).json()
    assert body["total"] == 0
    body = client.get(
        "/api/v1/vision/watch-folders/ingested/history").json()
    assert body["total"] == 0 and body["ingested"] == []
    body = client.get(
        "/api/v1/vision/watch-folders/ingested/history",
        params={"q": "secret"}).json()
    assert body["total"] == 0


def test_http_route_order_history_and_single_get(tmp_path, monkeypatch):
    # Both history roads are declared before {watch_id}: the
    # literal segments reach the history handlers, and the
    # single-watch road stays live beside them.
    client, _f, _db = make_client(tmp_path, monkeypatch)
    c1 = _chat(client, title="one")
    posted = _post_watch(client, c1, "/media/kept")
    hist = client.get("/api/v1/vision/watch-folders/history")
    assert hist.status_code == 200
    assert hist.json()["total"] == 1
    ing = client.get("/api/v1/vision/watch-folders/ingested/history")
    assert ing.status_code == 200
    assert ing.json()["total"] == 0
    single = client.get(
        f"/api/v1/vision/watch-folders/{posted['id']}")
    assert single.status_code == 200
    assert single.json()["id"] == posted["id"]
    assert single.json()["path"] == "/media/kept"


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _client, _f, db_path = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0041"
    assert current_revision(db_path) == "0041"
