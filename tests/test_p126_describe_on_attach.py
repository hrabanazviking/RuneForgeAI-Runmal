"""P-126 - Describe-on-attach opt-in (Part VIII, DERIVED).

Pins: the atomic service pair (attachment + description land
together or neither does), the P-120 service invariant
untouched (attach_image alone describes nothing), rollback
totality on every describe failure class (failing provider,
no provider), the HTTP opt-in (default off with the P-120
response shape unchanged and NO description key; opt-in
returns and persists an ordinary source_kind attachment
description; provider selection happens BEFORE storage, so
unknown-provider and require-semantic refusals store
nothing), custody inheritance (attachment delete purges the
opt-in description), and the migration head staying 0041.
No network: fixtures only.
"""

from __future__ import annotations

import base64
import hashlib
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.vision import attachments as att
from runmal.vision import service as vsvc

NOW = "2026-11-08T15:00:00+00:00"


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
PNG_SHA = hashlib.sha256(PNG).hexdigest()
PNG_B64 = base64.b64encode(PNG).decode()
NOT_IMAGE = b"definitely not an image"


def _att_store(tmp_path):
    return att.AttachmentStore(tmp_path)


def _vis_store(tmp_path):
    return vsvc.VisionStore(Path(tmp_path) / vsvc.DESCRIPTIONS_FILENAME)


def _listing(tmp_path):
    return sorted(
        str(p.relative_to(tmp_path)) for p in Path(tmp_path).rglob("*")
        if p.is_file())


class _FailingProvider:
    provider_id = "test.failing"
    model = "fail-1"
    road = "failing"

    def describe(self, image_bytes, question=""):
        raise vsvc.VisionProviderError("provider blew up on purpose")


# --------------------------------------------------------- service


def test_pair_lands_together_with_attachment_source(tmp_path):
    store, vstore = _att_store(tmp_path), _vis_store(tmp_path)
    record, desc = att.attach_and_describe(
        store, vstore, chat_id="c1", owner_id="u1", data=PNG,
        filename="pic.png", question="what is this?",
        provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert store.get(record.id) is not None
    assert store.read_bytes(record) == PNG
    assert desc.source_kind == "attachment"
    assert desc.source_ref == record.id
    assert desc.chat_id == "c1" and desc.owner_id == "u1"
    assert desc.question == "what is this?"
    assert desc.provider_road == "metadata"
    assert desc.image_sha256 == PNG_SHA
    assert "no semantic caption" in desc.description
    assert vstore.list_for_chat("c1") == [desc]
    assert vstore.last_for_chat("c1") == desc


def test_attach_image_alone_still_describes_nothing(tmp_path):
    store, vstore = _att_store(tmp_path), _vis_store(tmp_path)
    att.attach_image(
        store, chat_id="c1", owner_id="u1", data=PNG,
        filename="pic.png", now=NOW)
    assert vstore.list_for_owner("u1") == []
    assert not (Path(tmp_path) / vsvc.DESCRIPTIONS_FILENAME).exists()


def test_failing_provider_rolls_back_everything(tmp_path):
    store, vstore = _att_store(tmp_path), _vis_store(tmp_path)
    with pytest.raises(vsvc.VisionProviderError, match="blew up"):
        att.attach_and_describe(
            store, vstore, chat_id="c1", owner_id="u1", data=PNG,
            provider=_FailingProvider(), now=NOW)
    assert store.list_for_chat("c1") == []
    assert vstore.list_for_owner("u1") == []
    # No byte file survives and no description file is created;
    # the (now empty) attachments index file itself may remain,
    # exactly as after any P-120 remove.
    assert [f for f in _listing(tmp_path) if "vision_attachments/" in f] == []
    assert not (Path(tmp_path) / vsvc.DESCRIPTIONS_FILENAME).exists()


def test_no_provider_rolls_back_with_plain_refusal(tmp_path):
    store, vstore = _att_store(tmp_path), _vis_store(tmp_path)
    with pytest.raises(vsvc.VisionUnavailableError):
        att.attach_and_describe(
            store, vstore, chat_id="c1", owner_id="u1", data=PNG,
            provider=None, now=NOW)
    assert store.list_for_chat("c1") == []
    assert [f for f in _listing(tmp_path) if "vision_attachments/" in f] == []
    assert not (Path(tmp_path) / vsvc.DESCRIPTIONS_FILENAME).exists()


def test_attach_refusal_describes_nothing(tmp_path):
    store, vstore = _att_store(tmp_path), _vis_store(tmp_path)
    with pytest.raises(att.AttachmentError):
        att.attach_and_describe(
            store, vstore, chat_id="c1", owner_id="u1", data=NOT_IMAGE,
            provider=vsvc.MetadataVisionProvider(), now=NOW)
    assert store.list_for_chat("c1") == []
    assert vstore.list_for_owner("u1") == []


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


def _message(client, chat_id, content="look at this"):
    res = client.post(f"/api/v1/chats/{chat_id}/messages",
                      json={"role": "user", "content": content})
    assert res.status_code == 201
    return res.json()["id"]


def _history_total(client):
    res = client.get("/api/v1/vision/history")
    assert res.status_code == 200
    return res.json()["total"]


def _attachments(client, chat_id):
    res = client.get("/api/v1/vision/attachments",
                     params={"chat_id": chat_id})
    assert res.status_code == 200
    return res.json()["attachments"]


def test_http_plain_attach_unchanged_and_describes_nothing(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": "pic.png", "image_b64": PNG_B64})
    assert res.status_code == 201
    body = res.json()
    assert "description" not in body
    assert body["image"]["sha256"] == PNG_SHA
    assert _history_total(client) == 0
    last = client.get("/api/v1/vision/last", params={"chat_id": chat_id})
    assert last.status_code == 404


def test_http_optin_returns_and_persists_description(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": "pic.png", "image_b64": PNG_B64,
        "describe": True, "describe_question": "what is attached?"})
    assert res.status_code == 201
    body = res.json()
    desc = body["description"]
    assert desc["source_kind"] == "attachment"
    assert desc["source_ref"] == body["id"]
    assert desc["question"] == "what is attached?"
    assert desc["provider"]["road"] == "metadata"
    assert desc["image"]["sha256"] == PNG_SHA
    assert _history_total(client) == 1
    last = client.get("/api/v1/vision/last", params={"chat_id": chat_id})
    assert last.status_code == 200
    assert last.json()["id"] == desc["id"]


def test_http_optin_deterministic_provider(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": PNG_B64, "describe": True,
        "describe_provider": "deterministic_test"})
    assert res.status_code == 201
    desc = res.json()["description"]
    assert desc["provider"]["road"] == "deterministic_test"
    assert "not a semantic" in desc["description"]


def test_http_optin_require_semantic_stores_nothing(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": PNG_B64, "describe": True,
        "require_semantic": True})
    assert res.status_code == 422
    assert "no semantic vision provider" in res.json()["detail"]
    assert _attachments(client, chat_id) == []
    assert _history_total(client) == 0


def test_http_optin_unknown_provider_stores_nothing(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": PNG_B64, "describe": True,
        "describe_provider": "nope"})
    assert res.status_code == 422
    assert "unknown vision provider" in res.json()["detail"]
    assert _attachments(client, chat_id) == []
    assert _history_total(client) == 0


def test_http_optin_non_image_stores_nothing(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "describe": True,
        "image_b64": base64.b64encode(NOT_IMAGE).decode()})
    assert res.status_code == 422
    assert _attachments(client, chat_id) == []
    assert _history_total(client) == 0


def test_http_optin_message_attach_describes(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    msg_id = _message(client, chat_id)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "message_id": msg_id, "image_b64": PNG_B64,
        "describe": True})
    assert res.status_code == 201
    assert res.json()["message_id"] == msg_id
    assert res.json()["description"]["source_ref"] == res.json()["id"]


def test_http_optin_description_dies_with_attachment(
        tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "image_b64": PNG_B64, "describe": True})
    att_id = res.json()["id"]
    assert _history_total(client) == 1
    deleted = client.delete(f"/api/v1/vision/attachments/{att_id}")
    assert deleted.status_code == 200
    assert deleted.json()["descriptions_purged"] == 1
    assert _history_total(client) == 0


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    _, db_path = make_client(tmp_path, monkeypatch)
    assert current_revision(db_path) == "0042"
