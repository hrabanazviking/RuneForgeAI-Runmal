"""P-128 - Describe-on-scan opt-in (Part VIII, DERIVED).

Pins: the scan_and_describe composition (each newly
ingested file lands attachment + description, in ingestion
order, on the report's described list), the P-121 bound
untouched (scan_watch itself - service and HTTP, plain or
describe=False - describes nothing and its report dict
stays byte-identical, with NO "described" key), per-file
atomicity (a failing or absent provider makes each file a
named refused skip with NO attachment, NO byte file, NO
description and NO ingested record, and a later plain scan
ingests the same file fresh), dedupe honesty (already-
ingested files are never re-described), the injected-
attacher wrap, missing-folder / disabled refusals
unchanged, the HTTP opt-in (selection BEFORE the scan, so
selection refusals ingest nothing; the question carried;
custody inherited end-to-end - deleting the attachment
purges the description and forgets the ingested record),
foreign watch 404 with a describe body, and the migration
head staying 0041. No network: fixtures/fakes only.
"""

from __future__ import annotations

import hashlib
import itertools
import struct
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets.imaging import sniff_image
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.vision import attachments as att
from runmal.vision import service as vsvc
from runmal.vision import watcher as w

NOW = "2026-11-08T16:00:00+00:00"


def make_png_bytes(width=6, height=4, color=(30, 30, 200)) -> bytes:
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
PNG2 = make_png_bytes(2, 2, (10, 200, 10))
PNG_SHA = hashlib.sha256(PNG).hexdigest()
NOT_IMAGE = b"definitely not an image"


def _watch_store(tmp_path):
    return w.WatchStore(tmp_path / "data")


def _vis_store(tmp_path):
    return vsvc.VisionStore(
        tmp_path / "data" / vsvc.DESCRIPTIONS_FILENAME)


def _att_store(tmp_path):
    return att.AttachmentStore(tmp_path / "data")


def _register(store, folder, chat_id="c1", owner="u1", **kw):
    return w.register_watch(
        store, owner_id=owner, chat_id=chat_id,
        path=str(folder), now=NOW, **kw)


def _folder(tmp_path, files=("a.png",)):
    folder = tmp_path / "inbox"
    folder.mkdir()
    payloads = {"a.png": PNG, "b.png": PNG2, "note.txt": NOT_IMAGE}
    for name in files:
        (folder / name).write_bytes(payloads[name])
    return folder


def _byte_files(tmp_path):
    return sorted(
        str(p.relative_to(tmp_path))
        for p in Path(tmp_path).rglob("*")
        if p.is_file() and "vision_attachments" in str(p)
        and p.suffix in (".png", ".jpg", ".gif", ".webp"))


class _FailingProvider:
    provider_id = "test.failing"
    model = "fail-1"
    road = "failing"

    def describe(self, image_bytes, question=""):
        raise vsvc.VisionProviderError("provider blew up on purpose")


def _fake_attacher():
    """An attacher with P-120's shape and refusal discipline."""
    counter = itertools.count(1)
    calls = []

    def attach(data, *, chat_id, owner_id, filename):
        info = sniff_image(data)
        if info.format == "unknown" or info.error:
            raise ValueError("bytes do not sniff as a supported image")
        record = SimpleNamespace(
            id=f"att-{next(counter)}", chat_id=chat_id,
            owner_id=owner_id, filename=filename)
        calls.append(record)
        return record

    attach.calls = calls
    return attach


# --------------------------------------------------------- service


def test_pair_lands_per_file_and_report_described(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png", "b.png"))
    watch = _register(store, folder)
    report = w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert report.describe_requested is True
    assert len(report.ingested) == 2
    assert report.skipped == []
    rows = vstore.list_for_chat("c1")
    assert len(rows) == 2
    assert report.described == [row.id for row in rows]
    assert [row.source_ref for row in rows] == report.ingested
    assert all(row.source_kind == "attachment" for row in rows)
    assert all(row.provider_road == "metadata" for row in rows)
    assert rows[0].image_sha256 == PNG_SHA
    astore = _att_store(tmp_path)
    assert {r.id for r in astore.list_for_chat("c1")} == set(
        report.ingested)
    body = report.to_dict()
    assert body["described"] == report.described
    assert body["ingested"] == report.ingested


def test_question_applies_to_every_file(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png", "b.png"))
    watch = _register(store, folder)
    w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=vsvc.MetadataVisionProvider(),
        question="scan question?", now=NOW)
    rows = vstore.list_for_chat("c1")
    assert len(rows) == 2
    assert all(row.question == "scan question?" for row in rows)


def test_plain_scan_describes_nothing_vision_store_present(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = _register(store, folder)
    report = w.scan_watch(store, watch, now=NOW)
    assert len(report.ingested) == 1
    assert report.describe_requested is False
    assert report.described == []
    assert vstore.list_for_owner("u1") == []
    assert not (
        tmp_path / "data" / vsvc.DESCRIPTIONS_FILENAME).exists()
    assert "described" not in report.to_dict()


def test_plain_report_dict_byte_identical_shape(tmp_path):
    store = _watch_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = _register(store, folder)
    report = w.scan_watch(
        store, watch, attacher=_fake_attacher(), now=NOW)
    assert report.to_dict() == {
        "watch_id": watch.id,
        "chat_id": "c1",
        "scanned": 1,
        "ingested": report.ingested,
        "skipped": [],
        "truncated": False,
    }


def test_failing_provider_named_skips_total_rollback(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png", "b.png"))
    watch = _register(store, folder)
    report = w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=_FailingProvider(), now=NOW)
    assert report.describe_requested is True
    assert report.ingested == []
    assert report.described == []
    assert len(report.skipped) == 2
    assert all(s["reason"].startswith("refused:") for s in report.skipped)
    assert all("blew up" in s["reason"] for s in report.skipped)
    assert _att_store(tmp_path).list_for_chat("c1") == []
    assert _byte_files(tmp_path) == []
    assert vstore.list_for_owner("u1") == []
    assert store.list_ingested(watch.id) == []
    # A later plain scan judges the same files fresh.
    fresh = w.scan_watch(store, watch, now=NOW)
    assert len(fresh.ingested) == 2


def test_no_provider_unavailable_skips_nothing_ingested(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = _register(store, folder)
    report = w.scan_and_describe(
        store, watch, vision_store=vstore, provider=None, now=NOW)
    assert report.ingested == []
    assert report.described == []
    assert len(report.skipped) == 1
    assert "no vision provider is configured" in (
        report.skipped[0]["reason"])
    assert _att_store(tmp_path).list_for_chat("c1") == []
    assert vstore.list_for_owner("u1") == []
    assert store.list_ingested(watch.id) == []


def test_dedupe_never_redescribes(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png", "b.png"))
    watch = _register(store, folder)
    first = w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert len(first.described) == 2
    second = w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert second.ingested == []
    assert second.described == []
    assert len(second.skipped) == 2
    assert all(
        s["reason"] == "already_ingested" for s in second.skipped)
    assert len(vstore.list_for_chat("c1")) == 2


def test_injected_attacher_wrap_describes(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = _register(store, folder)
    report = w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=vsvc.MetadataVisionProvider(),
        attacher=_fake_attacher(), question="wrap q?", now=NOW)
    assert report.ingested == ["att-1"]
    assert len(report.described) == 1
    row = vstore.get(report.described[0])
    assert row is not None
    assert row.source_kind == "attachment"
    assert row.source_ref == "att-1"
    assert row.question == "wrap q?"


def test_injected_describe_failure_is_refused_skip(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = _register(store, folder)
    report = w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=_FailingProvider(),
        attacher=_fake_attacher(), now=NOW)
    assert report.ingested == []
    assert report.described == []
    assert len(report.skipped) == 1
    assert report.skipped[0]["reason"].startswith("refused:")
    assert "blew up" in report.skipped[0]["reason"]
    assert vstore.list_for_owner("u1") == []
    assert store.list_ingested(watch.id) == []


def test_missing_folder_and_disabled_refuse_unchanged(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    missing = _register(store, tmp_path / "does-not-exist")
    with pytest.raises(w.WatchError):
        w.scan_and_describe(
            store, missing, vision_store=vstore,
            provider=vsvc.MetadataVisionProvider(), now=NOW)
    folder = _folder(tmp_path, ("a.png",))
    live = _register(store, folder, chat_id="c2")
    disabled = w.WatchFolder(
        id=live.id, owner_id=live.owner_id, chat_id=live.chat_id,
        path=live.path, recursive=False, enabled=False,
        created_at=live.created_at)
    with pytest.raises(w.WatchError):
        w.scan_and_describe(
            store, disabled, vision_store=vstore,
            provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert vstore.list_for_owner("u1") == []
    assert store.list_ingested(live.id) == []


def test_non_image_is_refused_skip_not_described(tmp_path):
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png", "note.txt"))
    watch = _register(store, folder)
    report = w.scan_and_describe(
        store, watch, vision_store=vstore,
        provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert len(report.ingested) == 1
    assert len(report.described) == 1
    assert len(report.skipped) == 1
    assert report.skipped[0]["path"].endswith("note.txt")
    assert report.skipped[0]["reason"].startswith("refused:")


def test_describing_attacher_missing_attachments_names_absence(
        tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "runmal.vision.attachments", None)
    import runmal.vision as _vpkg
    monkeypatch.delattr(_vpkg, "attachments", raising=False)
    store, vstore = _watch_store(tmp_path), _vis_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = _register(store, folder)
    with pytest.raises(w.WatchError, match="P-120"):
        w.scan_and_describe(
            store, watch, vision_store=vstore,
            provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert store.list_ingested(watch.id) == []


# ------------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, db_path


def _chat(client):
    return client.post("/api/v1/chats", json={}).json()["id"]


def _watch(client, chat_id, folder):
    res = client.post(
        "/api/v1/vision/watch-folders",
        json={"chat_id": chat_id, "path": str(folder)})
    assert res.status_code == 201
    return res.json()["id"]


def _history(client):
    res = client.get("/api/v1/vision/history")
    assert res.status_code == 200
    return res.json()


def _attachments(client, chat_id):
    res = client.get(
        "/api/v1/vision/attachments", params={"chat_id": chat_id})
    assert res.status_code == 200
    return res.json()["attachments"]


def _ingested(client, watch_id):
    res = client.get(f"/api/v1/vision/watch-folders/{watch_id}/ingested")
    assert res.status_code == 200
    return res.json()["ingested"]


PLAIN_KEYS = {"watch_id", "chat_id", "scanned", "ingested",
              "skipped", "truncated"}


def test_http_bodyless_plain_scan_unchanged_shape(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(f"/api/v1/vision/watch-folders/{watch_id}/scan")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == PLAIN_KEYS
    assert "described" not in body
    assert len(body["ingested"]) == 1
    assert _history(client)["total"] == 0


def test_http_describe_false_unchanged(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": False})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == PLAIN_KEYS
    assert len(body["ingested"]) == 1
    assert _history(client)["total"] == 0


def test_http_optin_returns_described_and_persists(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png", "b.png"))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": True})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == PLAIN_KEYS | {"described"}
    assert len(body["ingested"]) == 2
    assert len(body["described"]) == 2
    hist = _history(client)
    assert hist["total"] == 2
    rows = hist["descriptions"]
    assert [row["id"] for row in rows] == body["described"][::-1] or (
        {row["id"] for row in rows} == set(body["described"]))
    by_id = {row["id"]: row for row in rows}
    for desc_id, att_id in zip(body["described"], body["ingested"]):
        assert by_id[desc_id]["source_kind"] == "attachment"
        assert by_id[desc_id]["source_ref"] == att_id
        assert by_id[desc_id]["provider"]["road"] == "metadata"
    last = client.get(
        "/api/v1/vision/last", params={"chat_id": chat_id})
    assert last.status_code == 200
    assert last.json()["id"] in body["described"]


def test_http_optin_deterministic_provider(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": True,
              "describe_provider": "deterministic_test"})
    assert res.status_code == 200
    assert len(res.json()["described"]) == 1
    row = _history(client)["descriptions"][0]
    assert row["provider"]["road"] == "deterministic_test"
    assert "not a semantic" in row["description"]


def test_http_selection_first_unknown_provider_ingests_nothing(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": True, "describe_provider": "nope"})
    assert res.status_code == 422
    assert "unknown vision provider" in res.json()["detail"]
    assert _attachments(client, chat_id) == []
    assert _ingested(client, watch_id) == []
    assert _history(client)["total"] == 0


def test_http_selection_first_require_semantic_ingests_nothing(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": True, "require_semantic": True})
    assert res.status_code == 422
    assert "no semantic vision provider" in res.json()["detail"]
    assert _attachments(client, chat_id) == []
    assert _ingested(client, watch_id) == []
    assert _history(client)["total"] == 0


def test_http_optin_question_carried(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": True,
              "describe_question": "scan question?"})
    assert res.status_code == 200
    row = _history(client)["descriptions"][0]
    assert row["question"] == "scan question?"


def test_http_custody_end_to_end(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": True})
    assert res.status_code == 200
    att_id = res.json()["ingested"][0]
    assert _history(client)["total"] == 1
    deleted = client.delete(f"/api/v1/vision/attachments/{att_id}")
    assert deleted.status_code == 200
    assert deleted.json()["descriptions_purged"] == 1
    assert deleted.json()["watch_records_forgotten"] == 1
    assert _history(client)["total"] == 0
    # The forgotten record lets a plain scan ingest it anew.
    again = client.post(f"/api/v1/vision/watch-folders/{watch_id}/scan")
    assert again.status_code == 200
    assert len(again.json()["ingested"]) == 1
    assert "described" not in again.json()


def test_http_foreign_watch_404_with_describe_body(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    _chat(client)
    res = client.post(
        "/api/v1/vision/watch-folders/nope/scan",
        json={"describe": True})
    assert res.status_code == 404


def test_http_optin_disabled_watch_is_422(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    folder = _folder(tmp_path, ("a.png",))
    watch_id = _watch(client, chat_id, folder)
    off = client.patch(
        f"/api/v1/vision/watch-folders/{watch_id}",
        json={"enabled": False})
    assert off.status_code == 200
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json={"describe": True})
    assert res.status_code == 422
    assert _history(client)["total"] == 0
    assert _attachments(client, chat_id) == []


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _, db_path = make_client(tmp_path, monkeypatch)
    assert current_revision(db_path) == "0041"
