"""P-119 — Vision provider selection + capability truth (DERIVED).

Pins: the deterministic test provider (deterministic,
labelled, refuses non-images, never claims semantic), the
provider catalogue as data (no semantic provider today,
stated plainly), backend Capabilities.vision truth derived
from the adapters' own declarations (all False today, source
"declared", agreeing with the adapters read directly), the
selection rules (default = metadata, by road and by
provider_id, unknown refused naming the known roads,
semantic-required never falls back), describe_image through
the selected provider recording full provider truth, and the
HTTP surface (providers road, provider selection on
describe, 422 shapes). Migration head stays 0041.
No network: fakes/fixtures only.
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
from runmal.backends.capabilities import default_model
from runmal.backends.profiles import CHAT_BACKENDS
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.vision import selection as sel
from runmal.vision import service as vis

NOW = "2026-11-08T13:00:00+00:00"


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
    return vis.VisionStore(tmp_path / "vision_descriptions.json")


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


# ------------------------------------------- deterministic provider


def test_deterministic_provider_is_deterministic_and_labelled():
    provider = sel.DeterministicTestVisionProvider()
    first = provider.describe(PNG, "what is this?")
    second = provider.describe(PNG, "a different question")
    assert first == second
    assert "deterministic_test" in first
    assert "not a semantic caption" in first
    assert "no semantic caption was produced" in first
    assert PNG_SHA in first
    assert "6x4" in first
    assert provider.provider_id == "runmal.vision.deterministic-test"
    assert provider.road == "deterministic_test"


def test_deterministic_provider_refuses_non_image():
    with pytest.raises(vis.VisionProviderError):
        sel.DeterministicTestVisionProvider().describe(
            b"definitely not an image")


def test_deterministic_provider_distinguishes_bytes():
    other = make_png_bytes(2, 2)
    a = sel.DeterministicTestVisionProvider().describe(PNG)
    b = sel.DeterministicTestVisionProvider().describe(other)
    assert a != b
    assert hashlib.sha256(other).hexdigest() in b


# ------------------------------------------------------ catalogue


def test_catalogue_names_both_providers_neither_semantic():
    rows = sel.provider_catalogue()
    by_road = {row.road: row for row in rows}
    assert set(by_road) == {"metadata", "deterministic_test"}
    assert by_road["metadata"].provider_id == "runmal.vision.metadata"
    assert by_road["deterministic_test"].provider_id == (
        "runmal.vision.deterministic-test")
    for row in rows:
        assert row.semantic is False
        assert row.available is True
        assert "Not a semantic caption" in row.note
    assert sel.semantic_caption_available() is False


# -------------------------------------------------- backend truth


def test_backend_vision_truth_matches_adapter_declarations():
    rows = sel.backend_vision_truth()
    assert [row.backend_key for row in rows] == list(CHAT_BACKENDS)
    for row in rows:
        declared = default_model(row.backend_key).capabilities.vision
        assert row.vision_declared == declared
        assert row.source == "declared"
        assert row.model_id == default_model(row.backend_key).model_id
    # Today's honest state: no adapter declares vision.
    assert all(row.vision_declared is False for row in rows)
    assert sel.any_backend_declares_vision() is False


# ------------------------------------------------------- selection


def test_select_default_is_metadata():
    provider = sel.select_provider()
    assert provider.road == "metadata"
    assert provider.provider_id == "runmal.vision.metadata"


def test_select_by_road_and_by_provider_id():
    by_road = sel.select_provider("deterministic_test")
    by_id = sel.select_provider("runmal.vision.deterministic-test")
    assert by_road.provider_id == by_id.provider_id
    assert sel.select_provider("metadata").road == "metadata"
    assert sel.select_provider("runmal.vision.metadata").road == "metadata"


def test_select_unknown_refused_naming_known_roads():
    with pytest.raises(vis.VisionProviderError) as excinfo:
        sel.select_provider("hallucinator-9000")
    message = str(excinfo.value)
    assert "metadata" in message
    assert "deterministic_test" in message


def test_semantic_requirement_never_falls_back():
    with pytest.raises(vis.VisionUnavailableError):
        sel.select_semantic_provider()
    with pytest.raises(vis.VisionUnavailableError):
        sel.select_provider(semantic_required=True)
    # Even naming a real (non-semantic) provider does not
    # satisfy a semantic requirement silently.
    with pytest.raises(vis.VisionUnavailableError):
        sel.select_provider("metadata", semantic_required=True)


# ------------------------------------------- describe via selection


def test_describe_via_deterministic_provider_records_truth(tmp_path):
    store = _store(tmp_path)
    provider = sel.select_provider("deterministic_test")
    rec = vis.describe_image(
        store, chat_id="c1", owner_id="u1", image_bytes=PNG,
        provider=provider, question="look", now=NOW)
    assert rec.provider_id == "runmal.vision.deterministic-test"
    assert rec.provider_model == "byte-fingerprint-1"
    assert rec.provider_road == "deterministic_test"
    assert "not a semantic caption" in rec.description
    assert store.last_for_chat("c1").id == rec.id


# -------------------------------------------------------------- HTTP


def _chat(client, **kw):
    return client.post("/api/v1/chats", json=kw).json()["id"]


def test_http_providers_road_tells_the_truth(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/vision/providers")
    assert res.status_code == 200
    body = res.json()
    assert body["semantic_caption_available"] is False
    assert {p["road"] for p in body["providers"]} == {
        "metadata", "deterministic_test"}
    assert all(p["semantic"] is False for p in body["providers"])
    assert [b["backend_key"] for b in body["backends"]] == list(
        CHAT_BACKENDS)
    assert all(b["vision_declared"] is False for b in body["backends"])
    assert all(b["source"] == "declared" for b in body["backends"])


def test_http_describe_with_selected_provider(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="vision")
    b64 = base64.b64encode(PNG).decode()
    res = client.post(
        "/api/v1/vision/describe",
        json={"chat_id": chat_id, "image_b64": b64,
              "provider": "deterministic_test"})
    assert res.status_code == 200
    body = res.json()
    assert body["provider"]["road"] == "deterministic_test"
    assert body["provider"]["provider_id"] == (
        "runmal.vision.deterministic-test")
    last = client.get("/api/v1/vision/last", params={"chat_id": chat_id})
    assert last.json()["provider"]["road"] == "deterministic_test"


def test_http_describe_default_stays_metadata(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="vision")
    b64 = base64.b64encode(PNG).decode()
    res = client.post("/api/v1/vision/describe",
                      json={"chat_id": chat_id, "image_b64": b64})
    assert res.status_code == 200
    assert res.json()["provider"]["road"] == "metadata"


def test_http_unknown_provider_and_semantic_422(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title="vision")
    b64 = base64.b64encode(PNG).decode()
    res = client.post(
        "/api/v1/vision/describe",
        json={"chat_id": chat_id, "image_b64": b64,
              "provider": "hallucinator-9000"})
    assert res.status_code == 422
    res = client.post(
        "/api/v1/vision/describe",
        json={"chat_id": chat_id, "image_b64": b64,
              "require_semantic": True})
    assert res.status_code == 422
    assert "semantic" in res.json()["detail"]
    # Nothing was stored by either refusal.
    listed = client.get("/api/v1/vision/descriptions",
                        params={"chat_id": chat_id})
    assert listed.json()["descriptions"] == []


def test_http_providers_openapi_lists_new_road(tmp_path, monkeypatch):
    client, _f, _db = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/vision/providers" in paths


# --------------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == MIGRATIONS[-1][0] == "0041"
