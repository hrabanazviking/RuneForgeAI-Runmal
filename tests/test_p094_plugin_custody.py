"""P-094 Plugin data custody battery.

Pins the contract from hidden_files/P094_DESIGN.md: one
custody surface over every shipped Part VI citizen - a
plugin's data is exportable and deletable with the plugin,
no hostage state. Durable file stores export VERBATIM and
delete owner-scoped (export A, export B, delete A, A gone,
B byte-identical); the summarise citizen's database output
(all ChatSummary versions + its kind=summary memories)
exports and deletes with other owners and non-summary
memories untouched; in-memory citizens export their CURRENT
state or an honest empty and delete through their own clear
roads, filtered to the owner's chats when a session proves
ownership; corrupt durable stores surface as a loud section
error, never a silent empty; the P-093 variables section is
LAZY (module absent on the slice base: unavailable, its file
never touched; on the merged tree, where P-093 is banked,
the same adapter lights up - verbatim export, stamped
manifest, owner-scoped delete - pinned by the banking heal
in this battery); pack-managed plugins delete through
manager.uninstall so no orphan ledger row survives; unknown
ids raise; custody itself holds no data; the HTTP road
refuses unconfirmed deletion and names instance sections
unavailable instead of dressing a partial export as
complete; neighbours: migration head stays 0041, the boot
registry stays empty (P-081), grants stay empty (P-082).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import data_dir, get_or_create_credential
from runmal.backends.embeddings import EmbeddingProvenance
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import ChatSummary, User
from runmal.memory import service as memory_service
from runmal.memory.vectorstore import InMemoryVectorStore
from runmal.plugins import custody as cu
from runmal.plugins import expressions as ex
from runmal.plugins import image_generation as ig
from runmal.plugins import quick_replies as qr
from runmal.plugins import service as plugin_service
from runmal.plugins import stt as stt_mod
from runmal.plugins import translate as tr
from runmal.plugins import tts as tts_mod
from runmal.plugins import vector_storage as vs
from runmal.plugins import web_search as ws
from runmal.plugins.manager import PluginManager
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.packs import build_pack
from runmal.plugins.registry import PluginRegistry


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def seed_chat(factory, uid, title="The Lighthouse"):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


def section(doc, name):
    for row in doc["sections"]:
        if row["name"] == name:
            return row
    raise AssertionError(f"section {name!r} missing from "
                         f"{[s['name'] for s in doc['sections']]}")


# -- Citizen / manifest / coverage -------------------------------------------


def test_manifest_round_trips_and_registers():
    data = cu.manifest_data()
    manifest = manifest_from_data(data)
    assert manifest_to_data(manifest) == data
    assert manifest.id == cu.PLUGIN_ID == "runmal.plugin-custody"
    assert "chat.write" not in manifest.permissions
    registry = PluginRegistry()
    record, plugin = cu.register_plugin(registry)
    assert record.manifest.id == cu.PLUGIN_ID
    assert plugin.manifest.id == cu.PLUGIN_ID


def test_sandbox_grants_are_empty():
    grants = cu.sandbox_grants()
    assert grants.resources == frozenset()


def test_coverage_names_every_citizen():
    coverage = cu.custody_coverage()
    assert coverage["citizens"] == list(cu.CITIZEN_PLUGIN_IDS)
    assert set(coverage["durable_file"]) == {
        "runmal.quick-replies", "runmal.regex-scripts",
        "runmal.expressions", "runmal.variables"}
    assert coverage["database"] == ["runmal.summarise"]
    assert coverage["stateless"] == [cu.PLUGIN_ID]


def test_boot_registry_stays_empty_without_registration(tmp_path):
    registry = plugin_service.build_registry()
    assert registry.keys() == []


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "fresh.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"


@pytest.mark.asyncio
async def test_unknown_plugin_raises():
    with pytest.raises(cu.UnknownPluginError):
        await cu.export_plugin_data("runmal.nope")
    with pytest.raises(cu.UnknownPluginError):
        await cu.delete_plugin_data("runmal.nope")


@pytest.mark.asyncio
async def test_custody_itself_holds_no_data():
    registry = PluginRegistry()
    cu.register_plugin(registry)
    doc = await cu.export_plugin_data(cu.PLUGIN_ID, registry=registry)
    assert doc["plugin_id"] == cu.PLUGIN_ID
    assert [s["name"] for s in doc["sections"]] == [
        "host_ledger", "registration"]
    assert section(doc, "registration")["status"] == "exported"
    assert section(doc, "host_ledger")["status"] == "unavailable"
    assert cu.verify_custody_checksum(doc)
    report = await cu.delete_plugin_data(cu.PLUGIN_ID, registry=registry)
    assert section(report, "host_ledger")["status"] == "unavailable"
    assert registry.find(cu.PLUGIN_ID) is not None  # data verb, not lifecycle


# -- Durable file citizens: verbatim export, owner-scoped delete -------------


@pytest.mark.asyncio
async def test_quick_replies_export_delete_owner_isolation(tmp_path):
    uid_a, uid_b = str(uuid.uuid4()), str(uuid.uuid4())
    qr.create_reply(uid_a, {"name": "Hail", "text": "Hail, A!"})
    qr.create_reply(uid_b, {"name": "Hail", "text": "Hail, B!"})
    path_a = qr.store_path(uid_a)
    path_b = qr.store_path(uid_b)
    bytes_b_before = path_b.read_bytes()
    doc_a = await cu.export_plugin_data("runmal.quick-replies", user_id=uid_a)
    doc_b = await cu.export_plugin_data("runmal.quick-replies", user_id=uid_b)
    sec_a = section(doc_a, "quick_replies_store")
    assert sec_a["status"] == "exported"
    assert sec_a["document"] == json.loads(path_a.read_text("utf-8"))
    assert sec_a["counts"]["replies"] == 1
    assert cu.verify_custody_checksum(doc_a)
    assert "Hail, B!" in json.dumps(section(doc_b, "quick_replies_store")["document"])
    report = await cu.delete_plugin_data("runmal.quick-replies", user_id=uid_a)
    sec = section(report, "quick_replies_store")
    assert sec["status"] == "deleted" and sec["removed"]["files"] == 1
    assert not path_a.exists()
    assert path_b.read_bytes() == bytes_b_before  # B byte-identical
    after = await cu.export_plugin_data("runmal.quick-replies", user_id=uid_a)
    assert section(after, "quick_replies_store")["status"] == "empty"
    again = await cu.delete_plugin_data("runmal.quick-replies", user_id=uid_a)
    assert section(again, "quick_replies_store")["removed"]["files"] == 0


@pytest.mark.asyncio
async def test_file_export_without_owner_is_unavailable_not_empty():
    doc = await cu.export_plugin_data("runmal.expressions")
    sec = section(doc, "expressions_store")
    assert sec["status"] == "unavailable" and "user_id" in sec["reason"]


@pytest.mark.asyncio
async def test_expressions_store_exports_verbatim(tmp_path):
    uid = str(uuid.uuid4())
    character_id = str(uuid.uuid4())
    ex.create_set(uid, {"character_id": character_id, "entries": [
        {"name": "neutral", "label": "Neutral"}], "default": "neutral"})
    doc = await cu.export_plugin_data("runmal.expressions", user_id=uid)
    sec = section(doc, "expressions_store")
    assert sec["status"] == "exported" and sec["counts"]["sets"] == 1
    assert sec["document"] == json.loads(
        ex.store_path(uid).read_text("utf-8"))
    report = await cu.delete_plugin_data("runmal.expressions", user_id=uid)
    assert section(report, "expressions_store")["status"] == "deleted"
    assert not ex.store_path(uid).exists()


@pytest.mark.asyncio
async def test_corrupt_file_store_is_a_loud_error_never_silent_empty(tmp_path):
    uid = str(uuid.uuid4())
    path = qr.store_path(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    doc = await cu.export_plugin_data("runmal.quick-replies", user_id=uid)
    sec = section(doc, "quick_replies_store")
    assert sec["status"] == "error" and sec["error"]
    assert cu.verify_custody_checksum(doc)  # failure is IN the document
    path.write_text(json.dumps({"schema": "wrong", "replies": []}),
                    encoding="utf-8")
    doc2 = await cu.export_plugin_data("runmal.quick-replies", user_id=uid)
    assert section(doc2, "quick_replies_store")["status"] == "error"


@pytest.mark.asyncio
async def test_variables_adapter_lights_up_on_the_merged_tree(tmp_path):
    # Banking heal (P-094, merged truth): on the slice base the
    # P-093 module was absent and this battery pinned the lazy
    # unavailable section + untouched file. P-093 is banked on
    # the merged tree, so the SAME adapter lights up with zero
    # custody changes: the store exports verbatim, the manifest
    # stamps from the real module, and delete removes only the
    # owner's file. Assertions strengthened, never weakened.
    uid = str(uuid.uuid4())
    other = str(uuid.uuid4())
    store_dir = data_dir() / "chat_variables"
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / f"{uid}.json"
    other_path = store_dir / f"{other}.json"
    payload = {"schema": "runmal-p093-chat-variables-v1", "chats": {}}
    other_payload = {"schema": "runmal-p093-chat-variables-v1",
                     "chats": {"chat-1": {"vars": {}, "flags": {}}}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    other_path.write_text(json.dumps(other_payload), encoding="utf-8")
    doc = await cu.export_plugin_data("runmal.variables", user_id=uid)
    sec = section(doc, "variables_store")
    assert sec["status"] == "exported"
    assert sec["schema"] == "runmal-p093-chat-variables-v1"
    assert sec["document"] == payload  # verbatim, nothing dropped
    assert sec["counts"] == {"chats": 0}
    assert doc["manifest"] is not None
    assert doc["manifest"]["id"] == "runmal.variables"
    assert cu.verify_custody_checksum(doc)
    report = await cu.delete_plugin_data("runmal.variables", user_id=uid)
    dsec = section(report, "variables_store")
    assert dsec["status"] == "deleted"
    assert dsec["removed"]["files"] == 1
    assert not path.exists()
    # other owner's store is never touched (owner-scoped delete)
    assert json.loads(other_path.read_text("utf-8")) == other_payload


# -- Summarise database citizen -------------------------------------------------


async def seed_summaries(factory, uid, chat_id, versions=2):
    ids = []
    async with factory() as session:
        for version in range(1, versions + 1):
            row = ChatSummary(user_id=uid, chat_id=chat_id, version=version,
                              summary=f"summary v{version}", source_count=3)
            session.add(row)
            await session.flush()
            ids.append(row.id)
            await memory_service.create_memory(
                session, uid, content=f"summary v{version}", kind="summary",
                chat_id=chat_id,
                extractor={"kind": "summariser", "version": "test-1",
                           "summary_id": row.id},
                sources=(("message", f"m{version}", chat_id),))
        await memory_service.create_memory(
            session, uid, content="an ordinary memory", kind="semantic")
        await session.commit()
    return ids


@pytest.mark.asyncio
async def test_summarise_export_and_delete_owner_scoped(tmp_path):
    factory = make_factory(tmp_path)
    uid_a = await make_user(factory, "a")
    uid_b = await make_user(factory, "b")
    chat_a = await seed_chat(factory, uid_a)
    chat_b = await seed_chat(factory, uid_b)
    ids_a = await seed_summaries(factory, uid_a, chat_a, versions=2)
    ids_b = await seed_summaries(factory, uid_b, chat_b, versions=1)
    async with factory() as session:
        doc = await cu.export_plugin_data(
            "runmal.summarise", user_id=uid_a, session=session)
    sec = section(doc, "summarise_store")
    assert sec["status"] == "exported"
    assert [s["version"] for s in sec["summaries"]] == [1, 2]  # ALL versions
    assert sec["counts"] == {"summaries": 2, "memories": 2}
    assert sec["memories"][0]["sources"][0]["source_id"] == "m1"
    async with factory() as session:
        report = await cu.delete_plugin_data(
            "runmal.summarise", user_id=uid_a, session=session)
        await session.commit()
    assert section(report, "summarise_store")["removed"] == {
        "summaries": 2, "memories": 2}
    async with factory() as session:
        after = await cu.export_plugin_data(
            "runmal.summarise", user_id=uid_a, session=session)
        other = await cu.export_plugin_data(
            "runmal.summarise", user_id=uid_b, session=session)
        remaining = await memory_service.list_memories(session, uid_a)
    assert section(after, "summarise_store")["status"] == "empty"
    assert section(other, "summarise_store")["counts"]["summaries"] == 1
    assert [m.kind for m in remaining] == ["semantic"]  # non-summary kept
    assert ids_a and ids_b  # seeded ids existed (silence linters)


@pytest.mark.asyncio
async def test_summarise_without_session_is_unavailable(tmp_path):
    doc = await cu.export_plugin_data("runmal.summarise", user_id=str(uuid.uuid4()))
    assert section(doc, "summarise_store")["status"] == "unavailable"


# -- In-memory citizens ---------------------------------------------------------


def seeded_translate(chat_id="chat-1"):
    plugin = tr.TranslatePlugin()
    plugin.set_chat_config(chat_id, enabled=True, source_lang="en",
                           target_in="de", target_out="de")
    plugin._translations[(chat_id, "m1")] = {
        "chat_id": chat_id, "message_id": "m1", "translated_text": "Hallo"}
    return plugin


@pytest.mark.asyncio
async def test_translate_export_current_state_and_delete():
    plugin = seeded_translate()
    other = seeded_translate("chat-2")
    instances = {"runmal.translate": plugin}
    doc = await cu.export_plugin_data("runmal.translate", instances=instances)
    sec = section(doc, "translate_state")
    assert sec["status"] == "exported" and sec["counts"]["translations"] == 1
    assert sec["chats"][0]["translations"][0]["translated_text"] == "Hallo"
    report = await cu.delete_plugin_data("runmal.translate", instances=instances)
    assert section(report, "translate_state")["removed"]["translations"] == 1
    assert plugin.translation_status("chat-1")["count"] == 0
    assert other.translation_status("chat-2")["count"] == 1  # untouched
    doc2 = await cu.export_plugin_data("runmal.translate", instances=instances)
    assert section(doc2, "translate_state")["status"] == "empty"


@pytest.mark.asyncio
async def test_instance_section_without_instance_is_unavailable():
    doc = await cu.export_plugin_data("runmal.translate")
    sec = section(doc, "translate_state")
    assert sec["status"] == "unavailable" and "instance" in sec["reason"]


@pytest.mark.asyncio
async def test_instance_delete_filtered_to_owner_chats(tmp_path):
    factory = make_factory(tmp_path)
    uid_a = await make_user(factory, "a")
    uid_b = await make_user(factory, "b")
    chat_a = await seed_chat(factory, uid_a)
    chat_b = await seed_chat(factory, uid_b)
    plugin = seeded_translate(chat_a)
    plugin.set_chat_config(chat_b, enabled=True, source_lang="en")
    plugin._translations[(chat_b, "m9")] = {
        "chat_id": chat_b, "message_id": "m9", "translated_text": "Fremd"}
    instances = {"runmal.translate": plugin}
    async with factory() as session:
        doc = await cu.export_plugin_data(
            "runmal.translate", user_id=uid_a, session=session,
            instances=instances)
        report = await cu.delete_plugin_data(
            "runmal.translate", user_id=uid_a, session=session,
            instances=instances)
    sec = section(doc, "translate_state")
    assert [row["chat_id"] for row in sec["chats"]] == [chat_a]  # B filtered out
    assert section(report, "translate_state")["removed"]["translations"] == 1
    assert plugin.translation_status(chat_a)["count"] == 0
    assert plugin.translation_status(chat_b)["count"] == 1  # B untouched


@pytest.mark.asyncio
async def test_web_search_and_image_and_voice_sections():
    search = ws.WebSearchPlugin()
    search.set_chat_config("chat-1", enabled=True)
    image = ig.ImageGenerationPlugin()
    image.set_chat_enabled("chat-1", True)
    image.record_generation({"chat_id": "chat-1", "prompt": "a lighthouse",
                             "asset_id": "asset-1", "landed": True})
    tts_plugin = tts_mod.TtsPlugin()
    tts_plugin._last_by_chat["chat-1"] = {"plugin_id": tts_mod.PLUGIN_ID,
                                          "chat_id": "chat-1", "kind": "tts"}
    stt_plugin = stt_mod.SttPlugin()
    stt_plugin._last_by_chat["chat-1"] = {"plugin_id": stt_mod.PLUGIN_ID,
                                          "chat_id": "chat-1", "text": "hail"}
    instances = {"runmal.web-search": search, "runmal.image-generation": image,
                 "runmal.tts": tts_plugin, "runmal.stt": stt_plugin}
    doc = await cu.export_plugin_data("runmal.web-search", instances=instances)
    assert section(doc, "web_search_state")["status"] == "exported"
    doc = await cu.export_plugin_data("runmal.image-generation", instances=instances)
    sec = section(doc, "image_generation_state")
    assert sec["landed_asset_ids"] == ["asset-1"]
    assert "host data" in sec["landed_assets_note"]
    report = await cu.delete_plugin_data("runmal.image-generation", instances=instances)
    assert section(report, "image_generation_state")["removed"] == {
        "ledger_records": 1, "enabled_chats": 1}
    assert image.history() == [] and image.enabled_chat_ids() == []
    doc = await cu.export_plugin_data("runmal.tts", instances=instances)
    assert section(doc, "tts_state")["chats"][0]["latest"]["kind"] == "tts"
    report = await cu.delete_plugin_data("runmal.tts", instances=instances)
    assert section(report, "tts_state")["removed"]["results"] == 1
    assert tts_plugin.last_result("chat-1") is None
    doc = await cu.export_plugin_data("runmal.stt", instances=instances)
    assert section(doc, "stt_state")["chats"][0]["latest"]["text"] == "hail"
    report = await cu.delete_plugin_data("runmal.stt", instances=instances)
    assert section(report, "stt_state")["removed"]["transcripts"] == 1


@pytest.mark.asyncio
async def test_vector_index_export_and_delete():
    store = InMemoryVectorStore()
    index = vs.VectorMemoryIndex(store)
    prov = EmbeddingProvenance(provider="local", model="hash-1", dims=3,
                               version="1")
    index.index_vector("chat", "chat-1", "mem-1", (1.0, 0.0, 0.0), prov)
    index.index_vector("chat", "chat-1", "mem-2", (0.0, 1.0, 0.0), prov)
    plugin = vs.VectorStoragePlugin(index=index)
    instances = {"runmal.vector-storage": plugin}
    doc = await cu.export_plugin_data("runmal.vector-storage", instances=instances)
    sec = section(doc, "vector_index")
    assert sec["status"] == "exported" and sec["counts"]["vectors"] == 2
    assert sec["vectors"]["chat|chat-1|mem-1"] == [1.0, 0.0, 0.0]
    assert sec["provenance"]["provider"] == "local"
    report = await cu.delete_plugin_data("runmal.vector-storage", instances=instances)
    assert section(report, "vector_index")["removed"]["vectors"] == 2
    assert index.doc_ids() == []


@pytest.mark.asyncio
async def test_vector_unbound_index_is_unavailable():
    plugin = vs.VectorStoragePlugin()
    doc = await cu.export_plugin_data(
        "runmal.vector-storage", instances={"runmal.vector-storage": plugin})
    assert section(doc, "vector_index")["status"] == "unavailable"


# -- Pack-managed plugins: the P-083 hook point ---------------------------------


ALPHA = {
    "id": "pack.alpha", "name": "Pack Alpha", "version": "1.0.0",
    "api_version": 1, "description": "Alpha pack plugin.", "author": "Tester",
    "capabilities": ["chat.events", "ui.slots"],
    "permissions": ["chat.read", "ui.contribute"],
    "events": ["chat.created", "message.created"],
    "ui_slots": [{"id": "alpha-panel", "slot": "chat.sidebar",
                  "label": "Alpha", "order": 100,
                  "payload": {"kind": "panel", "route": "alpha"}}],
    "enabled_by_default": False,
}


@pytest.mark.asyncio
async def test_pack_plugin_exports_ledger_and_deletes_through_uninstall(tmp_path):
    registry = PluginRegistry()
    manager = PluginManager(registry, tmp_path / "store")
    manager.install(build_pack(ALPHA),
                    granted_permissions=["chat.read", "ui.contribute"])
    assert manager.row_for("pack.alpha") is not None
    doc = await cu.export_plugin_data("pack.alpha", registry=registry,
                                      manager=manager)
    assert [s["name"] for s in doc["sections"]] == [
        "host_ledger", "registration"]
    assert section(doc, "host_ledger")["status"] == "exported"
    assert section(doc, "host_ledger")["row"]["plugin_id"] == "pack.alpha"
    report = await cu.delete_plugin_data("pack.alpha", registry=registry,
                                         manager=manager)
    assert section(report, "host_ledger")["removed"] == {
        "ledger_rows": 1, "unregistered": True}
    assert manager.row_for("pack.alpha") is None  # no orphan row
    assert registry.find("pack.alpha") is None
    # After uninstall the id is completely unknown again (no adapter,
    # no row, no registration): the unknown-id law applies, per design.
    with pytest.raises(cu.UnknownPluginError):
        await cu.delete_plugin_data("pack.alpha", registry=registry,
                                    manager=manager)


@pytest.mark.asyncio
async def test_citizen_delete_with_manager_skips_uninstall_when_no_row(tmp_path):
    registry = PluginRegistry()
    manager = PluginManager(registry, tmp_path / "store")
    uid = str(uuid.uuid4())
    qr.create_reply(uid, {"name": "Hail", "text": "Hail!"})
    report = await cu.delete_plugin_data("runmal.quick-replies", user_id=uid,
                                         registry=registry, manager=manager)
    assert section(report, "quick_replies_store")["status"] == "deleted"
    assert section(report, "host_ledger")["status"] == "empty"


# -- HTTP surface -----------------------------------------------------------------


async def owner_id(tmp_path):
    from runmal.db.owners import get_or_create_owner

    factory = make_factory(tmp_path)
    async with factory() as session:
        owner = await get_or_create_owner(session)
        await session.commit()
        return owner.id


def test_http_export_delete_flow(tmp_path, monkeypatch):
    import asyncio

    client = make_client(tmp_path, monkeypatch)
    uid = asyncio.run(owner_id(tmp_path))
    qr.create_reply(uid, {"name": "Hail", "text": "Hail over HTTP!"})
    got = client.get("/api/v1/plugins/runmal.quick-replies/custody/export")
    assert got.status_code == 200, got.text
    doc = got.json()
    assert section(doc, "quick_replies_store")["status"] == "exported"
    assert cu.verify_custody_checksum(doc)
    refused = client.post(
        "/api/v1/plugins/runmal.quick-replies/custody/delete", json={})
    assert refused.status_code == 422, refused.text
    assert qr.store_path(uid).exists()  # unconfirmed deletion changed nothing
    done = client.post(
        "/api/v1/plugins/runmal.quick-replies/custody/delete",
        json={"confirm": True})
    assert done.status_code == 200, done.text
    assert section(done.json(), "quick_replies_store")["status"] == "deleted"
    assert not qr.store_path(uid).exists()


def test_http_unknown_plugin_404_and_instance_honesty(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    missing = client.get("/api/v1/plugins/runmal.nope/custody/export")
    assert missing.status_code == 404, missing.text
    got = client.get("/api/v1/plugins/runmal.translate/custody/export")
    assert got.status_code == 200, got.text
    sec = section(got.json(), "translate_state")
    assert sec["status"] == "unavailable"
    assert "instance_not_wired_over_http" not in sec["reason"]  # plain reason
    assert "instance" in sec["reason"]
