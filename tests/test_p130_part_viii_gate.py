"""P-130 Part VIII gate battery: Vision Services, whole.

Gate discipline (P-030 / P-100 / P-116 pattern): the gate
builds no new behaviour; it judges the banked Part VIII
slices (P-117..P-129) end to end through their own public
contracts, from measured evidence only. Part VIII's slice
definitions are DERIVED (the filed roadmap gives Part VIII
only its part line, "VIII | Vision Services | P-117 -
P-130"); the census this gate judges is the one the banked
slice docs declare.

- Area A (census): every P-117..P-129 vision surface is
  present - modules, service functions, HTTP roads, the
  vision __init__ module map, the slice docs, and the
  P-118 prompt variable registry.
- Area B (one world, together): one vision world walks
  describe (both provider roads) -> last-per-chat -> the
  prompt template variable; plain attach (describes
  nothing) -> thumbnail -> history/search; the
  describe-on-attach opt-in (atomic pair, selection-first
  refusals); the watcher end to end (register -> scan ->
  dedupe -> history/search, plain scans describing
  nothing); the describe-on-scan opt-in (pairs land,
  already-ingested files never re-described); and the
  recursive flag changing scan depth only when flipped.
- Area C (custody + control parity): the PATCH road moves
  enabled and recursive (either, both, empty refused); a
  disabled watch refuses to scan; the DELETE watch road
  reports the ingested records it removes and leaves the
  ingested attachments under P-120 custody; deleting an
  attachment purges its descriptions AND forgets its
  watcher records so its source file ingests anew;
  chat deletion purges descriptions, attachments and
  watches together; message deletion purges the message's
  attachment chain (attachment + derived description +
  watcher record).
- Area D (honest accounting): the bounds are pinned as
  measured facts, never loosened - Capabilities.vision is
  False for every backend, no provider is semantic and
  semantic_caption_available is False, a semantic
  requirement never falls back, no-provider and unknown
  provider refusals are plain and store nothing,
  thumbnails are PNG-only and store nothing, every search
  is literal-only and owner-scoped first, and the scan
  report is a synchronous result that persists nothing
  (no daemon, no scan-history store).
- Hygiene: migration head stays 0041; the gate world
  (ZqxGate130) lives only in this battery.

Clean-room note: the gate world is fresh-authored for this
gate (P-005 discipline); no SillyTavern or Voxta source was
inspected, and no real user files are read. Plain pytest
functions, no test classes.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import struct
import zlib
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets.imaging import sniff_image
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.prompt import vision_link as vl
from runmal.prompt.variables import (
    list_variables,
    resolve_variables_for_chat,
)
from runmal.vision import attachments as att
from runmal.vision import selection as sel
from runmal.vision import service as vis
from runmal.vision import watcher as w

REPO = Path(__file__).parent.parent
Z = "ZqxGate130"
NOW = "2026-11-08T17:00:00+00:00"
FIXED = datetime(2026, 11, 8, 17, 0, 0)


def _chunk(ctype, data):
    raw = ctype + data
    return struct.pack(">I", len(data)) + raw + struct.pack(
        ">I", zlib.crc32(raw) & 0xFFFFFFFF)


def make_png_bytes(width=6, height=4, color=(200, 30, 30)):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(color) * width
    idat = zlib.compress(row * height)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", idat) + _chunk(b"IEND", b""))


def make_jpeg_bytes(width=8, height=6):
    sof = struct.pack(">H", 8 + 3 * 3) + bytes([8]) + struct.pack(
        ">HH", height, width) + bytes(
            [3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
    return b"\xff\xd8" + b"\xff\xc0" + sof + b"\xff\xd9"


PNG = make_png_bytes()
PNG2 = make_png_bytes(2, 2, (10, 200, 10))
BIG_PNG = make_png_bytes(512, 256)
JPEG = make_jpeg_bytes()
PNG_SHA = hashlib.sha256(PNG).hexdigest()
PNG_B64 = base64.b64encode(PNG).decode()
JPEG_B64 = base64.b64encode(JPEG).decode()
NOT_IMAGE = b"definitely not an image"


def _vis_store(tmp_path):
    return vis.VisionStore(tmp_path / vis.DESCRIPTIONS_FILENAME)


def _att_store(tmp_path):
    return att.AttachmentStore(tmp_path)


def _watch_store(tmp_path):
    return w.WatchStore(tmp_path)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _chat(client, **kw):
    res = client.post("/api/v1/chats", json=kw)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _message(client, chat_id, content="look at this"):
    res = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "user", "content": content})
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _folder(tmp_path, files=("a.png",), sub=None):
    folder = tmp_path / "inbox"
    folder.mkdir(exist_ok=True)
    payloads = {"a.png": PNG, "b.png": PNG2, "note.txt": NOT_IMAGE}
    for name in files:
        (folder / name).write_bytes(payloads[name])
    if sub:
        deep = folder / "deep"
        deep.mkdir(exist_ok=True)
        for name in sub:
            (deep / name).write_bytes(payloads[name])
    return folder


# -- Area A: the Part VIII census is present ----------------


def test_a_vision_modules_and_services_present():
    expected = {
        "service": ["describe_image", "VisionStore",
                    "MetadataVisionProvider", "VisionError",
                    "VisionUnavailableError"],
        "selection": ["provider_catalogue", "select_provider",
                      "select_semantic_provider",
                      "semantic_caption_available",
                      "backend_vision_truth",
                      "providers_payload",
                      "DeterministicTestVisionProvider"],
        "attachments": ["attach_image", "AttachmentStore",
                        "thumbnail_bytes", "attach_and_describe",
                        "AttachmentError"],
        "watcher": ["register_watch", "scan_watch",
                    "scan_and_describe", "WatchStore",
                    "WatchError"],
    }
    for module_name, funcs in expected.items():
        module = importlib.import_module(f"runmal.vision.{module_name}")
        for name in funcs:
            assert hasattr(module, name), f"{module_name}.{name} missing"
    store_methods = {
        vis.VisionStore: ["append", "list_for_chat", "last_for_chat",
                          "get", "list_for_owner", "search", "remove",
                          "purge_source"],
        att.AttachmentStore: ["append", "get", "list_for_chat",
                              "list_for_message", "list_for_owner",
                              "search", "remove", "purge_chat",
                              "purge_message", "read_bytes"],
        w.WatchStore: ["add_watch", "get_watch", "list_for_owner",
                       "list_for_chat", "remove_watch", "set_enabled",
                       "set_recursive", "purge_chat", "list_ingested",
                       "record_ingested", "forget_attachment",
                       "search", "list_ingested_for_owner",
                       "search_ingested"],
    }
    for cls, methods in store_methods.items():
        for name in methods:
            assert hasattr(cls, name), f"{cls.__name__}.{name} missing"
    router_mod = importlib.import_module("runmal.vision.router")
    assert hasattr(router_mod, "router")


def test_a_http_roads_present():
    module = importlib.import_module("runmal.vision.router")
    paths = {"/api/v1" + getattr(r, "path", "")
             for r in module.router.routes}
    for road in (
            "/api/v1/vision/describe",
            "/api/v1/vision/providers",
            "/api/v1/vision/descriptions",
            "/api/v1/vision/last",
            "/api/v1/vision/history",
            "/api/v1/vision/descriptions/{description_id}",
            "/api/v1/vision/attachments",
            "/api/v1/vision/attachments/history",
            "/api/v1/vision/attachments/{attachment_id}",
            "/api/v1/vision/attachments/{attachment_id}/content",
            "/api/v1/vision/attachments/{attachment_id}/thumbnail",
            "/api/v1/vision/watch-folders",
            "/api/v1/vision/watch-folders/history",
            "/api/v1/vision/watch-folders/ingested/history",
            "/api/v1/vision/watch-folders/{watch_id}",
            "/api/v1/vision/watch-folders/{watch_id}/scan",
            "/api/v1/vision/watch-folders/{watch_id}/ingested"):
        assert road in paths, road


def test_a_module_map_slice_docs_and_variable_present():
    init_text = (REPO / "src" / "runmal" / "vision" / "__init__.py"
                 ).read_text(encoding="utf-8")
    for token in ("service", "selection", "attachments", "router",
                  "watcher", "P-117", "P-119", "P-120", "P-121",
                  "P-122", "P-123", "P-124", "P-125", "P-126",
                  "P-127", "P-128", "P-129"):
        assert token in init_text, token
    for doc in ("VISION_FOUNDATION_2026-11-08.md",
                "VISION_TEMPLATE_VARIABLE_2026-11-08.md",
                "VISION_PROVIDER_SELECTION_2026-11-08.md",
                "VISION_HISTORY_CUSTODY_2026-11-08.md",
                "VISION_ATTACHMENT_THUMBNAILS_2026-11-08.md",
                "VISION_WATCHER_CUSTODY_CONTROL_2026-11-08.md",
                "VISION_ATTACHMENT_HISTORY_2026-11-08.md",
                "VISION_DESCRIBE_ON_ATTACH_2026-11-08.md",
                "VISION_WATCHER_HISTORY_2026-11-08.md",
                "VISION_DESCRIBE_ON_SCAN_2026-11-08.md",
                "VISION_WATCHER_CONTROL_PARITY_2026-11-08.md"):
        assert (REPO / "docs" / doc).exists(), doc
    # P-120's and P-121's slice docs ride other names in-tree;
    # their surfaces are pinned by Areas A-C behaviourally.
    assert "last_vision_description" in {
        v["name"] for v in list_variables()}


def test_a_openapi_succeeds_and_names_vision_roads(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    assert "/api/v1/vision/providers" in paths
    assert "/api/v1/vision/describe" in paths


# -- Area B: one vision world, together ---------------------


def test_b_describe_roads_last_and_prompt_variable_agree(tmp_path):
    store = _vis_store(tmp_path)
    meta = vis.describe_image(
        store, chat_id="c1", owner_id="u1", image_bytes=PNG,
        provider=sel.select_provider(), now=NOW)
    assert meta.provider_road == "metadata"
    assert "no semantic caption" in meta.description
    det = vis.describe_image(
        store, chat_id="c1", owner_id="u1", image_bytes=PNG2,
        provider=sel.select_provider("deterministic_test"),
        question="gate question", now=NOW)
    assert det.provider_road == "deterministic_test"
    assert "not a semantic caption" in det.description
    # One store, one truth: list, last and the prompt link agree.
    assert store.list_for_chat("c1") == [meta, det]
    assert store.last_for_chat("c1") == det
    assert vl.last_description_text("c1", tmp_path) == det.description
    out = resolve_variables_for_chat(
        "Seen: {{last_vision_description}}", chat_id="c1",
        data_dir=tmp_path, now=FIXED)
    assert out.text == f"Seen: {det.description}"
    assert out.resolved == ["last_vision_description"]
    out = resolve_variables_for_chat(
        "Seen: [{{last_vision_description}}]", chat_id="c-none",
        data_dir=tmp_path, now=FIXED)
    assert out.text == "Seen: []"


def test_b_http_describe_providers_history_and_last_agree(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    payload = client.get("/api/v1/vision/providers").json()
    assert payload["semantic_caption_available"] is False
    assert {p["road"] for p in payload["providers"]} == {
        "metadata", "deterministic_test"}
    assert all(p["semantic"] is False for p in payload["providers"])
    assert all(b["vision_declared"] is False
               for b in payload["backends"])
    res = client.post("/api/v1/vision/describe", json={
        "chat_id": chat_id, "image_b64": PNG_B64})
    assert res.status_code == 200, res.text
    first = res.json()
    assert first["provider"]["road"] == "metadata"
    res = client.post("/api/v1/vision/describe", json={
        "chat_id": chat_id, "image_b64": PNG_B64,
        "provider": "deterministic_test", "question": "gate?"})
    assert res.status_code == 200, res.text
    second = res.json()
    assert second["provider"]["road"] == "deterministic_test"
    listed = client.get(
        "/api/v1/vision/descriptions",
        params={"chat_id": chat_id}).json()
    assert [d["id"] for d in listed["descriptions"]] == [
        first["id"], second["id"]]
    last = client.get(
        "/api/v1/vision/last", params={"chat_id": chat_id}).json()
    assert last["id"] == second["id"]
    hist = client.get(
        "/api/v1/vision/history", params={"q": "deterministic"}).json()
    assert hist["total"] == 1
    assert hist["descriptions"][0]["id"] == second["id"]
    hist = client.get(
        "/api/v1/vision/history",
        params={"provider_road": "metadata"}).json()
    assert hist["total"] == 1
    assert hist["descriptions"][0]["id"] == first["id"]


def test_b_attach_plain_thumbnail_history_then_describe(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": "gate-pic.png",
        "image_b64": base64.b64encode(BIG_PNG).decode()})
    assert res.status_code == 201, res.text
    record = res.json()
    assert record["image"]["format"] == "png"
    assert record["image"]["sha256"] == hashlib.sha256(
        BIG_PNG).hexdigest()
    # A plain attach describes nothing (P-120 bound, P-126 seam).
    assert client.get(
        "/api/v1/vision/last",
        params={"chat_id": chat_id}).status_code == 404
    # The thumbnail is a real derived PNG and stores nothing.
    before = sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")
        if p.is_file())
    thumb = client.get(
        f"/api/v1/vision/attachments/{record['id']}/thumbnail")
    assert thumb.status_code == 200, thumb.text
    info = sniff_image(thumb.content)
    assert info.format == "png"
    assert (info.width, info.height) == (256, 128)
    after = sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")
        if p.is_file())
    assert before == after
    # History/search sees the attachment by filename and by sha.
    hist = client.get(
        "/api/v1/vision/attachments/history",
        params={"q": "gate-pic"}).json()
    assert hist["total"] == 1
    assert hist["attachments"][0]["id"] == record["id"]
    hist = client.get(
        "/api/v1/vision/attachments/history",
        params={"q": record["image"]["sha256"][:12]}).json()
    assert hist["total"] == 1
    # Describing the attachment lands an attachment-sourced
    # record that every describe surface then agrees on.
    res = client.post("/api/v1/vision/describe", json={
        "chat_id": chat_id, "attachment_id": record["id"]})
    assert res.status_code == 200, res.text
    desc = res.json()
    assert desc["source_kind"] == "attachment"
    assert desc["source_ref"] == record["id"]
    last = client.get(
        "/api/v1/vision/last", params={"chat_id": chat_id}).json()
    assert last["id"] == desc["id"]
    hist = client.get(
        "/api/v1/vision/history",
        params={"source_kind": "attachment"}).json()
    assert hist["total"] == 1


def test_b_describe_on_attach_pair_lands_atomically(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": "pair.png",
        "image_b64": PNG_B64, "describe": True,
        "describe_provider": "deterministic_test",
        "describe_question": "gate pair?"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["description"]["source_kind"] == "attachment"
    assert body["description"]["source_ref"] == body["id"]
    assert body["description"]["question"] == "gate pair?"
    last = client.get(
        "/api/v1/vision/last", params={"chat_id": chat_id}).json()
    assert last["id"] == body["description"]["id"]
    # Selection happens BEFORE storage: a semantic refusal
    # leaves no attachment, no bytes, no description.
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "filename": "never.png",
        "image_b64": PNG_B64, "describe": True,
        "require_semantic": True})
    assert res.status_code == 422, res.text
    listed = client.get(
        "/api/v1/vision/attachments",
        params={"chat_id": chat_id}).json()
    assert [a["filename"] for a in listed["attachments"]] == [
        "pair.png"]
    # Service-level atomicity: a failing provider rolls the
    # attachment back too (P-126's pair-or-nothing law).

    class _Failing:
        provider_id = "test.failing"
        model = "fail-1"
        road = "failing"

        def describe(self, image_bytes, question=""):
            raise vis.VisionProviderError("blew up on purpose")

    astore, vstore = _att_store(tmp_path), _vis_store(tmp_path)
    with pytest.raises(vis.VisionProviderError):
        att.attach_and_describe(
            astore, vstore, chat_id="cx", owner_id="u1", data=PNG,
            filename="rollback.png", provider=_Failing(), now=NOW)
    assert astore.list_for_chat("cx") == []
    assert vstore.list_for_chat("cx") == []


def test_b_watcher_end_to_end_plain_scan_describes_nothing(tmp_path):
    wstore, astore, vstore = (
        _watch_store(tmp_path), _att_store(tmp_path),
        _vis_store(tmp_path))
    folder = _folder(tmp_path, ("a.png", "note.txt"))
    watch = w.register_watch(
        wstore, owner_id="u1", chat_id="c1", path=str(folder),
        now=NOW)
    report = w.scan_watch(wstore, watch, now=NOW)
    assert len(report.ingested) == 1
    assert report.to_dict().get("described") is None
    assert [s["path"] for s in report.skipped] == [
        str(folder / "note.txt")]
    assert "refused" in report.skipped[0]["reason"]
    attachments = astore.list_for_chat("c1")
    assert len(attachments) == 1
    assert attachments[0].id == report.ingested[0]
    assert attachments[0].filename == "a.png"
    # A plain scan describes nothing, on any surface.
    assert vstore.list_for_chat("c1") == []
    # Dedupe: a second scan ingests nothing new.
    report2 = w.scan_watch(wstore, watch, now=NOW)
    assert report2.ingested == []
    assert any(s["reason"] == "already_ingested"
               for s in report2.skipped)
    assert len(astore.list_for_chat("c1")) == 1
    # A changed file at the same path ingests anew.
    (folder / "a.png").write_bytes(PNG2)
    report3 = w.scan_watch(wstore, watch, now=NOW)
    assert len(report3.ingested) == 1
    assert report3.ingested[0] != report.ingested[0]
    assert len(astore.list_for_chat("c1")) == 2
    assert len(wstore.list_ingested(watch.id)) == 2


def test_b_describe_on_scan_pairs_and_never_redescribes(tmp_path):
    wstore, astore, vstore = (
        _watch_store(tmp_path), _att_store(tmp_path),
        _vis_store(tmp_path))
    folder = _folder(tmp_path, ("a.png", "b.png"))
    watch = w.register_watch(
        wstore, owner_id="u1", chat_id="c1", path=str(folder),
        now=NOW)
    report = w.scan_and_describe(
        wstore, watch, vision_store=vstore,
        provider=vis.MetadataVisionProvider(),
        question="scan gate?", now=NOW)
    assert report.describe_requested is True
    assert len(report.ingested) == 2
    assert len(report.described) == 2
    descriptions = vstore.list_for_chat("c1")
    assert {d.id for d in descriptions} == set(report.described)
    assert {d.source_ref for d in descriptions} == set(
        report.ingested)
    assert all(d.source_kind == "attachment" for d in descriptions)
    assert all(d.question == "scan gate?" for d in descriptions)
    assert vstore.last_for_chat("c1").id in report.described
    # Already-ingested files are never re-described.
    report2 = w.scan_and_describe(
        wstore, watch, vision_store=vstore,
        provider=vis.MetadataVisionProvider(), now=NOW)
    assert report2.ingested == []
    assert report2.described == []
    assert len(vstore.list_for_chat("c1")) == 2


def test_b_watcher_history_search_agrees_with_stores(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    folder = _folder(tmp_path, ("a.png",))
    res = client.post("/api/v1/vision/watch-folders", json={
        "chat_id": chat_id, "path": str(folder)})
    assert res.status_code == 201, res.text
    watch = res.json()
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch['id']}/scan",
        json={})
    assert res.status_code == 200, res.text
    assert len(res.json()["ingested"]) == 1
    # Registration history finds the watch by folder fragment.
    hist = client.get(
        "/api/v1/vision/watch-folders/history",
        params={"q": "inbox"}).json()
    assert hist["total"] == 1
    assert hist["watch_folders"][0]["id"] == watch["id"]
    # Ingested history finds the record by sha fragment, and
    # the per-watch road agrees with it.
    ing = client.get(
        "/api/v1/vision/watch-folders/ingested/history",
        params={"q": PNG_SHA[:12]}).json()
    assert ing["total"] == 1
    assert ing["ingested"][0]["sha256"] == PNG_SHA
    per_watch = client.get(
        f"/api/v1/vision/watch-folders/{watch['id']}/ingested"
    ).json()
    assert [r["sha256"] for r in per_watch["ingested"]] == [PNG_SHA]
    # The ingested attachment is a P-120 attachment of the chat.
    listed = client.get(
        "/api/v1/vision/attachments",
        params={"chat_id": chat_id}).json()
    assert [a["id"] for a in listed["attachments"]] == [
        ing["ingested"][0]["attachment_id"]]


def test_b_recursive_flip_changes_depth_and_keeps_dedupe(tmp_path):
    wstore, astore = _watch_store(tmp_path), _att_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",), sub=("b.png",))
    watch = w.register_watch(
        wstore, owner_id="u1", chat_id="c1", path=str(folder),
        now=NOW)
    assert watch.recursive is False
    report = w.scan_watch(wstore, watch, now=NOW)
    assert len(report.ingested) == 1
    flipped = wstore.set_recursive(watch.id, True)
    assert flipped.recursive is True
    assert flipped.enabled is True
    # The flip preserves the registration AND its dedupe memory.
    assert wstore.get_watch(watch.id).path == str(folder)
    assert len(wstore.list_ingested(watch.id)) == 1
    report2 = w.scan_watch(wstore, flipped, now=NOW)
    assert len(report2.ingested) == 1
    assert len(astore.list_for_chat("c1")) == 2
    assert {a.filename for a in astore.list_for_chat("c1")} == {
        "a.png", "b.png"}


# -- Area C: custody + control parity -----------------------


def test_c_patch_moves_either_flag_and_refuses_empty(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    folder = _folder(tmp_path, ("a.png",))
    watch = client.post("/api/v1/vision/watch-folders", json={
        "chat_id": chat_id, "path": str(folder)}).json()
    url = f"/api/v1/vision/watch-folders/{watch['id']}"
    res = client.patch(url, json={})
    assert res.status_code == 422, res.text
    res = client.patch(url, json={"enabled": False})
    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is False
    assert res.json()["recursive"] is False
    # A disabled watch refuses to scan, plainly.
    res = client.post(url + "/scan", json={})
    assert res.status_code == 422, res.text
    res = client.patch(url, json={"recursive": True})
    assert res.json()["recursive"] is True
    assert res.json()["enabled"] is False
    res = client.patch(url, json={"enabled": True,
                                  "recursive": False})
    assert res.json()["enabled"] is True
    assert res.json()["recursive"] is False
    res = client.post(url + "/scan", json={})
    assert res.status_code == 200, res.text
    assert len(res.json()["ingested"]) == 1


def test_c_delete_watch_reports_ingested_keeps_attachments(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    folder = _folder(tmp_path, ("a.png", "b.png"))
    watch = client.post("/api/v1/vision/watch-folders", json={
        "chat_id": chat_id, "path": str(folder)}).json()
    scanned = client.post(
        f"/api/v1/vision/watch-folders/{watch['id']}/scan",
        json={}).json()
    assert len(scanned["ingested"]) == 2
    res = client.delete(f"/api/v1/vision/watch-folders/{watch['id']}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"deleted": True, "id": watch["id"],
                    "ingested_records_removed": 2}
    assert client.get(
        f"/api/v1/vision/watch-folders/{watch['id']}"
    ).status_code == 404
    # The ingested attachments are NOT the watch's to delete:
    # they stay under P-120 custody.
    listed = client.get(
        "/api/v1/vision/attachments",
        params={"chat_id": chat_id}).json()
    assert len(listed["attachments"]) == 2


def test_c_delete_attachment_purges_and_forgets_so_rescan_lands(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    folder = _folder(tmp_path, ("a.png",))
    watch = client.post("/api/v1/vision/watch-folders", json={
        "chat_id": chat_id, "path": str(folder)}).json()
    scan_url = f"/api/v1/vision/watch-folders/{watch['id']}/scan"
    scanned = client.post(scan_url, json={
        "describe": True,
        "describe_provider": "deterministic_test"}).json()
    assert len(scanned["ingested"]) == 1
    assert len(scanned["described"]) == 1
    att_id = scanned["ingested"][0]
    assert client.get(
        "/api/v1/vision/last",
        params={"chat_id": chat_id}).status_code == 200
    res = client.delete(f"/api/v1/vision/attachments/{att_id}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["deleted"] is True
    assert body["descriptions_purged"] == 1
    assert body["watch_records_forgotten"] == 1
    # Every derived surface agrees the chain is gone.
    assert client.get(
        "/api/v1/vision/last",
        params={"chat_id": chat_id}).status_code == 404
    ing = client.get(
        f"/api/v1/vision/watch-folders/{watch['id']}/ingested"
    ).json()
    assert ing["ingested"] == []
    # Because the dedupe record was forgotten, the same file
    # ingests anew instead of skipping forever.
    rescanned = client.post(scan_url, json={}).json()
    assert len(rescanned["ingested"]) == 1
    assert rescanned["ingested"][0] != att_id


def test_c_chat_deletion_purges_all_three_stores(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    doomed = _chat(client, title=Z + " doomed")
    keeper = _chat(client, title=Z + " keeper")
    folder = _folder(tmp_path, ("a.png",))
    for cid in (doomed, keeper):
        res = client.post("/api/v1/vision/attachments", json={
            "chat_id": cid, "image_b64": PNG_B64,
            "describe": True})
        assert res.status_code == 201, res.text
        watch = client.post("/api/v1/vision/watch-folders", json={
            "chat_id": cid, "path": str(folder)}).json()
        scanned = client.post(
            f"/api/v1/vision/watch-folders/{watch['id']}/scan",
            json={})
        assert scanned.status_code == 200, scanned.text
    res = client.delete(f"/api/v1/chats/{doomed}")
    assert res.status_code in (200, 204), res.text
    # Descriptions, attachments and watches of the doomed chat
    # are gone from the stores themselves; the keeper's stay.
    assert _vis_store(tmp_path).list_for_chat(doomed) == []
    assert _att_store(tmp_path).list_for_chat(doomed) == []
    assert _watch_store(tmp_path).list_for_chat(doomed) == []
    assert len(_vis_store(tmp_path).list_for_chat(keeper)) == 1
    assert len(_att_store(tmp_path).list_for_chat(keeper)) == 2
    assert len(_watch_store(tmp_path).list_for_chat(keeper)) == 1
    assert vl.last_description_text(doomed, tmp_path) == ""


def test_c_message_deletion_purges_the_attachment_chain(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    msg_id = _message(client, chat_id)
    res = client.post("/api/v1/vision/attachments", json={
        "chat_id": chat_id, "message_id": msg_id,
        "image_b64": PNG_B64, "describe": True})
    assert res.status_code == 201, res.text
    att_id = res.json()["id"]
    # A watcher record naming this attachment (the scan chain).
    wstore = _watch_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = w.register_watch(
        wstore, owner_id=res.json()["owner_id"], chat_id=chat_id,
        path=str(folder), now=NOW)
    wstore.record_ingested(w.IngestedRecord(
        watch_id=watch.id, source_path=str(folder / "a.png"),
        sha256=PNG_SHA, size=len(PNG), attachment_id=att_id,
        ingested_at=NOW))
    res = client.delete(
        f"/api/v1/chats/{chat_id}/messages/{msg_id}")
    assert res.status_code in (200, 204), res.text
    assert _att_store(tmp_path).list_for_chat(chat_id) == []
    assert _vis_store(tmp_path).list_for_chat(chat_id) == []
    assert _watch_store(tmp_path).list_ingested(watch.id) == []


def test_c_description_remove_and_purge_source_are_exact(tmp_path):
    store = _vis_store(tmp_path)
    provider = vis.MetadataVisionProvider()
    keep = vis.describe_image(
        store, chat_id="c1", owner_id="u1", image_bytes=PNG,
        provider=provider, source_kind=vis.SOURCE_INLINE,
        source_ref="", now=NOW)
    derived = vis.describe_image(
        store, chat_id="c1", owner_id="u1", image_bytes=PNG,
        provider=provider, source_kind=vis.SOURCE_ATTACHMENT,
        source_ref="att-1", now=NOW)
    other = vis.describe_image(
        store, chat_id="c1", owner_id="u1", image_bytes=PNG2,
        provider=provider, source_kind=vis.SOURCE_ATTACHMENT,
        source_ref="att-2", now=NOW)
    assert store.purge_source(vis.SOURCE_ATTACHMENT, "") == 0
    assert store.purge_source(vis.SOURCE_ATTACHMENT, "att-1") == 1
    assert store.get(derived.id) is None
    removed = store.remove(keep.id)
    assert removed is not None and removed.id == keep.id
    assert store.remove(keep.id) is None
    assert store.list_for_chat("c1") == [other]


# -- Area D: the honesty bounds, pinned ----------------------


def test_d_capability_truth_vision_false_everywhere():
    rows = sel.backend_vision_truth()
    assert rows, "the census must name at least one backend"
    assert all(row.vision_declared is False for row in rows)
    assert all(row.source == "declared" for row in rows)
    assert sel.any_backend_declares_vision() is False
    catalogue = sel.provider_catalogue()
    assert {row.road for row in catalogue} == {
        "metadata", "deterministic_test"}
    assert all(row.semantic is False for row in catalogue)
    assert all(row.available is True for row in catalogue)
    assert sel.semantic_caption_available() is False
    payload = sel.providers_payload()
    assert payload["semantic_caption_available"] is False
    assert "No semantic caption provider exists in-tree" in (
        payload["semantic_caption_note"])


def test_d_semantic_requirement_never_falls_back(tmp_path, monkeypatch):
    with pytest.raises(vis.VisionUnavailableError):
        sel.select_semantic_provider()
    with pytest.raises(vis.VisionUnavailableError):
        sel.select_provider(semantic_required=True)
    with pytest.raises(vis.VisionUnavailableError):
        sel.select_provider(
            "deterministic_test", semantic_required=True)
    client = make_client(tmp_path, monkeypatch)
    chat_id = _chat(client, title=Z)
    res = client.post("/api/v1/vision/describe", json={
        "chat_id": chat_id, "image_b64": PNG_B64,
        "require_semantic": True})
    assert res.status_code == 422, res.text
    assert _vis_store(tmp_path).list_for_chat(chat_id) == []
    # Describe-on-scan refuses the same way, before scanning.
    folder = _folder(tmp_path, ("a.png",))
    watch = client.post("/api/v1/vision/watch-folders", json={
        "chat_id": chat_id, "path": str(folder)}).json()
    res = client.post(
        f"/api/v1/vision/watch-folders/{watch['id']}/scan",
        json={"describe": True, "require_semantic": True})
    assert res.status_code == 422, res.text
    assert _att_store(tmp_path).list_for_chat(chat_id) == []


def test_d_no_provider_and_unknown_provider_refuse_plainly(tmp_path):
    store = _vis_store(tmp_path)
    with pytest.raises(vis.VisionUnavailableError):
        vis.describe_image(
            store, chat_id="c1", owner_id="u1", image_bytes=PNG,
            provider=None, now=NOW)
    assert store.list_for_chat("c1") == []
    with pytest.raises(vis.VisionError):
        vis.describe_image(
            store, chat_id="c1", owner_id="u1", image_bytes=b"",
            provider=vis.MetadataVisionProvider(), now=NOW)
    with pytest.raises(vis.VisionProviderError):
        vis.describe_image(
            store, chat_id="c1", owner_id="u1",
            image_bytes=NOT_IMAGE,
            provider=vis.MetadataVisionProvider(), now=NOW)
    assert store.list_for_chat("c1") == []
    with pytest.raises(vis.VisionProviderError) as excinfo:
        sel.select_provider("no-such-road")
    assert "metadata" in str(excinfo.value)
    assert "deterministic_test" in str(excinfo.value)
    default = sel.select_provider()
    assert default.road == "metadata"
    assert sel.select_provider("metadata").road == "metadata"
    assert sel.select_provider(
        "deterministic_test").road == "deterministic_test"


def test_d_thumbnail_bound_is_png_only_and_stores_nothing(tmp_path):
    store = _att_store(tmp_path)
    png_rec = att.attach_image(
        store, chat_id="c1", owner_id="u1", data=BIG_PNG,
        filename="big.png", now=NOW)
    jpg_rec = att.attach_image(
        store, chat_id="c1", owner_id="u1", data=JPEG,
        filename="photo.jpg", now=NOW)
    assert jpg_rec.image_format == "jpeg"
    with pytest.raises(att.AttachmentError) as excinfo:
        att.thumbnail_bytes(store, jpg_rec)
    assert "PNG-only" in str(excinfo.value)
    with pytest.raises(att.AttachmentError):
        att.thumbnail_bytes(store, png_rec, max_dim=0)
    with pytest.raises(att.AttachmentError):
        att.thumbnail_bytes(store, png_rec, max_dim=5000)
    before = sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")
        if p.is_file())
    thumb = att.thumbnail_bytes(store, png_rec, max_dim=64)
    assert sniff_image(thumb).format == "png"
    after = sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")
        if p.is_file())
    assert before == after
    # The record itself carries no thumbnail claim.
    assert "thumbnail" not in png_rec.to_dict()


def test_d_every_search_is_literal_and_owner_scoped(tmp_path):
    vstore, astore, wstore = (
        _vis_store(tmp_path), _att_store(tmp_path),
        _watch_store(tmp_path))
    mine = vis.describe_image(
        vstore, chat_id="c1", owner_id="u1", image_bytes=PNG,
        provider=vis.MetadataVisionProvider(),
        question="gate question", now=NOW)
    vis.describe_image(
        vstore, chat_id="c2", owner_id="u2", image_bytes=PNG,
        provider=vis.MetadataVisionProvider(),
        question="gate question", now=NOW)
    # Literal hits on stored text; a semantic-sounding query
    # that appears in no stored text finds nothing - the red
    # PNG is never "a red door" to any search in this tree.
    rows, total = vstore.search("u1", "gate question")
    assert total == 1 and rows[0].id == mine.id
    rows, total = vstore.search("u1", "a red door")
    assert total == 0 and rows == []
    rows, total = vstore.search("u1", "")
    assert total == 1  # owner-scoped first: u2's row never counts
    att.attach_image(
        astore, chat_id="c1", owner_id="u1", data=PNG,
        filename="gate-pic.png", now=NOW)
    att.attach_image(
        astore, chat_id="c2", owner_id="u2", data=PNG,
        filename="gate-pic.png", now=NOW)
    rows, total = astore.search("u1", "gate-pic")
    assert total == 1
    rows, total = astore.search("u1", "red door")
    assert total == 0
    rows, total = astore.search("u1", PNG_SHA[:10])
    assert total == 1
    folder = _folder(tmp_path, ("a.png",))
    watch = w.register_watch(
        wstore, owner_id="u1", chat_id="c1", path=str(folder),
        now=NOW)
    w.register_watch(
        wstore, owner_id="u2", chat_id="c2", path=str(folder),
        now=NOW)
    rows, total = wstore.search("u1", "inbox")
    assert total == 1 and rows[0].id == watch.id
    rows, total = wstore.search("u1", "the folder with red doors")
    assert total == 0
    wstore.record_ingested(w.IngestedRecord(
        watch_id=watch.id, source_path=str(folder / "a.png"),
        sha256=PNG_SHA, size=len(PNG), attachment_id="att-x",
        ingested_at=NOW))
    rows, total = wstore.search_ingested("u1", PNG_SHA[:10])
    assert total == 1
    rows, total = wstore.search_ingested("u2", PNG_SHA[:10])
    assert total == 0  # foreign watches' records never surface


def test_d_scan_report_persists_nothing_and_no_daemon(tmp_path):
    wstore = _watch_store(tmp_path)
    folder = _folder(tmp_path, ("a.png",))
    watch = w.register_watch(
        wstore, owner_id="u1", chat_id="c1", path=str(folder),
        now=NOW)
    report = w.scan_watch(wstore, watch, now=NOW)
    assert len(report.ingested) == 1
    # The only files a scan leaves are the three known stores
    # (watcher index, attachment index + bytes, and - here -
    # no descriptions file at all): the report itself is a
    # synchronous result, never persisted (P-127's stance).
    names = {p.name for p in tmp_path.rglob("*") if p.is_file()}
    assert "vision_descriptions.json" not in names
    assert not any("scan" in name for name in names)
    assert not any("report" in name for name in names)
    # No daemon surface exists on the watcher module or store:
    # a scan is a deliberate call, never a background watcher.
    for name in dir(w) + dir(w.WatchStore):
        lowered = name.lower()
        assert "daemon" not in lowered
        assert "watch_forever" not in lowered
        assert "background" not in lowered


# -- Hygiene -------------------------------------------------


def test_h_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"


def test_h_gate_world_lives_only_in_this_battery():
    text = Path(__file__).read_text(encoding="utf-8")
    assert Z in text
    for path in (REPO / "src").rglob("*.py"):
        assert Z not in path.read_text(
            encoding="utf-8", errors="ignore"), path
