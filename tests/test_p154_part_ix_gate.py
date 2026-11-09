"""P-154 Part IX gate battery: Scenarios, whole.

Gate discipline (P-030 / P-048 / P-064 / P-080 / P-100 /
P-116 / P-130 pattern): the gate builds no new behaviour;
it judges the banked Part IX slices (P-131..P-152) end
to end through their own public contracts, from measured
evidence only, and accounts for P-153 - banking in
parallel from team-02 commit 4d35cff, NOT in this base -
by overlay: its committed module is loaded read-only
from the team-02 worktree and reconciled against the
in-base P-136 service (the P-116 precedent). Part IX's
slice definitions are DERIVED (the filed roadmap gives
Part IX only its part line, "IX | Scenarios - the Visual
Novel Engine | P-131 - P-154"); the census this gate
judges is the one the banked slice docs declare.

- Area A (census): every P-131..P-152 scenario surface
  is present - modules, service functions, store verbs,
  HTTP roads, the scenarios __init__ module map, the
  slice docs - and app OpenAPI generation succeeds and
  names the scenario roads. The P-153 road is honestly
  ABSENT on this base and named as the merged shape.
- Area B (one world, together): a stored definition
  binds to a chat seeding flags/variables per P-093 law
  (missing keys only); the chat-scoped preview judges
  before any write and agrees with the bind that lands;
  the binding censuses P-144 / P-148 / P-150 reconcile
  row for row; the definition and chat censuses P-151 /
  P-152 reconcile on one world; the P-153 overlay census
  reconciles with P-136's per-definition envelopes;
  duplication, stored export and organisation compose;
  pack preview agrees with pack import; candidate
  previews judge without writing.
- Area C (custody): deleting a definition orphans its
  bindings and organisation row, named before (P-139)
  and after (P-144), repaired by nothing; replacing
  leaves superseded pins named before (P-140) and after;
  deleting a chat leaves the binding document
  byte-untouched, named before (P-149) and after
  (P-148) - the cascade decision stays Volmarr's;
  unbind removes only the record; every census and
  every preview writes nothing.
- Area D (honest accounting): the bounds are pinned as
  measured facts, never loosened - the P-133 F1 leak is
  closed on the stateless road (P-142) and the two
  export roads agree; unmappable Voxta raw values never
  persist, are named by the stored report, the P-145
  census and the export report, and are never restored;
  stored content stays data (P-027) - binding executes
  nothing; the delete_chat cascade stays reserved and
  untaken; the portable archive carries no scenario
  store; every census is owner-scoped.
- Hygiene: migration head stays 0041; the gate world
  (ZqxGate154) lives only in this battery.

Clean-room note: the gate world is fresh-authored for
this gate (P-005 discipline); no SillyTavern or Voxta
source was inspected, and no real user files are read.
Plain pytest functions, no test classes.
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.plugins.variables import get_entry, get_variable, seed_variables
from runmal.scenarios.binding import (
    ScenarioBinding,
    ScenarioBindingStore,
    bind_scenario,
    get_binding,
    plan_materialisation,
    unbind,
)
from runmal.scenarios.bindingcensus import census_bindings
from runmal.scenarios.bindpreview import preview_bind_plan
from runmal.scenarios.chatcoverage import census_chat_coverage
from runmal.scenarios.chatpreview import preview_bind_for_chat
from runmal.scenarios.candidatechatpreview import preview_candidate_for_chat
from runmal.scenarios.candidatepreview import preview_candidate_replace
from runmal.scenarios.chatcensus import census_binding_chats
from runmal.scenarios.chatdeletepreview import preview_chat_delete_impact
from runmal.scenarios.custodycensus import census_binding_custody
from runmal.scenarios.definitioncensus import census_definitions
from runmal.scenarios.deletepreview import preview_delete_impact
from runmal.scenarios.fileexport import export_voxta
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.organisation import ScenarioOrganisationStore
from runmal.scenarios.packpreview import preview_pack_import
from runmal.scenarios.packs import build_pack, import_pack, inspect_pack
from runmal.scenarios.replacepreview import preview_replace_impact
from runmal.scenarios.reportcensus import census_unmappable
from runmal.scenarios.store import ScenarioStore
from runmal.scenarios.storedexport import export_stored_definition

REPO = Path(__file__).parent.parent
Z = "ZqxGate154"
NOW = "2026-11-08T22:00:00+00:00"
OWNER = "owner-g154"
FOREIGN = "foreign-g154"
TEAM02 = Path.home() / "runmal-team-02"

BODY = {
    "name": "Harbour Lights at Dusk",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
    "narrator_name": "The Harbour Voice",
    "impersonation_name": "Ash",
    "roles": [
        {"name": "Narrator", "character_name": "Maera",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "note", "text": "The tide is going out.", "role": "Narrator"},
        {"kind": "user", "text": "I never left.", "role": ""},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}


def body(name=None) -> dict:
    out = copy.deepcopy(BODY)
    if name:
        out["name"] = name
    return out


def revised_body() -> dict:
    out = body()
    out["scenario_text"] = "The ferry has returned."
    return out


def voxta_body(name, *, scripts=False) -> dict:
    out = {"name": name, "chatFlow": "Story",
           "scenario": "A harbour, voiced."}
    if scripts:
        out["scripts"] = [{"code": "x=1"}]
    return out


def _stores(tmp_path):
    definitions = ScenarioStore(tmp_path / "scenarios.json")
    bindings = ScenarioBindingStore(tmp_path / "scenario_bindings.json")
    organisation = ScenarioOrganisationStore(
        tmp_path / "scenario_organisation.json")
    return definitions, bindings, organisation


def _rec(bid, owner, chat, definition, name="Harbour", rev=1):
    return ScenarioBinding(
        id=bid, owner_id=owner, chat_id=chat, definition_id=definition,
        definition_name=name, definition_revision=rev, bound_at=NOW,
        cast=[{"name": "Narrator"}],
        seeded_messages=[{"message_id": "m1"}],
        seeded_keys=["scenario:trust"],
        skipped=[],
    )


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def make_chat(factory, user_id, title="Harbour"):
    async with factory() as session:
        chat = await svc.create_chat(session, user_id, title)
        return chat.id


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _snap(tmp_path):
    out = {}
    for name in ("scenarios.json", "scenario_bindings.json",
                 "scenario_organisation.json"):
        path = tmp_path / name
        out[name] = path.read_bytes() if path.exists() else None
    return out


# -- Area A: the Part IX census is present ----------------


def test_a_scenario_modules_and_services_present():
    expected = {
        "store": ["ScenarioStore", "ScenarioDefinition", "definitions_path"],
        "binding": ["ScenarioBindingStore", "bind_scenario",
                    "plan_materialisation", "list_bindings",
                    "get_binding", "unbind"],
        "storedexport": ["export_stored_definition",
                         "scenario_file_from_stored"],
        "organisation": ["ScenarioOrganisationStore", "query_definitions",
                         "list_tags", "organisation_view"],
        "bindpreview": ["preview_bind_plan"],
        "chatpreview": ["preview_bind_for_chat"],
        "candidatechatpreview": ["preview_candidate_for_chat"],
        "deletepreview": ["preview_delete_impact"],
        "replacepreview": ["preview_replace_impact"],
        "candidatepreview": ["preview_candidate_replace"],
        "chatdeletepreview": ["preview_chat_delete_impact"],
        "bindingcensus": ["census_bindings", "BINDING_STATES"],
        "chatcensus": ["census_binding_chats", "CHAT_CUSTODY_STATES"],
        "custodycensus": ["census_binding_custody", "CUSTODY_STATES"],
        "definitioncensus": ["census_definitions",
                             "DEFINITION_CUSTODY_STATES"],
        "chatcoverage": ["census_chat_coverage", "CHAT_COVERAGE_STATES"],
        "reportcensus": ["census_unmappable"],
        "packs": ["build_pack", "inspect_pack", "import_pack",
                  "parse_pack", "pack_to_bytes"],
        "packpreview": ["preview_pack_import"],
        "fileimport": ["parse_scenario_file"],
        "fileexport": ["export_native", "export_voxta"],
    }
    for module_name, funcs in expected.items():
        module = importlib.import_module(f"runmal.scenarios.{module_name}")
        for name in funcs:
            assert hasattr(module, name), f"{module_name}.{name} missing"
    store_methods = {
        ScenarioStore: ["create", "get", "list_for_owner", "replace",
                        "remove", "duplicate"],
        ScenarioBindingStore: ["add", "get_for_chat", "list_for_owner",
                               "list_for_definition", "remove_for_chat"],
        ScenarioOrganisationStore: ["get", "list_for_owner", "set_tags",
                                    "add_tags", "remove_tag",
                                    "set_favourite"],
    }
    for cls, methods in store_methods.items():
        for name in methods:
            assert hasattr(cls, name), f"{cls.__name__}.{name} missing"
    router_mod = importlib.import_module("runmal.scenarios.router")
    assert hasattr(router_mod, "router")


def test_a_http_roads_present():
    module = importlib.import_module("runmal.scenarios.router")
    paths = {"/api/v1" + getattr(r, "path", "")
             for r in module.router.routes}
    for road in (
            "/api/v1/scenarios/import",
            "/api/v1/scenarios/export",
            "/api/v1/scenarios",
            "/api/v1/scenarios/library/tags",
            "/api/v1/scenarios/library/unmappable",
            "/api/v1/scenarios/library/census",
            "/api/v1/scenarios/bindings",
            "/api/v1/scenarios/bindings/census",
            "/api/v1/scenarios/bindings/chat-census",
            "/api/v1/scenarios/bindings/custody-census",
            "/api/v1/scenarios/import-pack",
            "/api/v1/scenarios/pack/inspect",
            "/api/v1/scenarios/pack/import-preview",
            "/api/v1/scenarios/{definition_id}",
            "/api/v1/scenarios/{definition_id}/duplicate",
            "/api/v1/scenarios/{definition_id}/delete-impact",
            "/api/v1/scenarios/{definition_id}/organisation",
            "/api/v1/scenarios/{definition_id}/tags",
            "/api/v1/scenarios/{definition_id}/favourite",
            "/api/v1/scenarios/{definition_id}/bind",
            "/api/v1/scenarios/bindings/{chat_id}",
            "/api/v1/scenarios/bindings/{chat_id}/delete-impact",
            "/api/v1/scenarios/{definition_id}/bindings",
            "/api/v1/scenarios/{definition_id}/bind-plan",
            "/api/v1/scenarios/{definition_id}/bind-plan/{chat_id}",
            "/api/v1/scenarios/{definition_id}/replace-impact",
            "/api/v1/scenarios/{definition_id}/replace-preview",
            "/api/v1/scenarios/{definition_id}/export",
            "/api/v1/scenarios/{definition_id}/pack",
            "/api/v1/scenarios/{definition_id}/replace-preview/{chat_id}",
            "/api/v1/scenarios/chats/census"):
        assert road in paths, road
    # P-153 banked in parallel (4d35cff, banked before this
    # gate): on the merged tree its road is LIVE - the gate
    # doc's F2 merged-truth shape, healed at banking to the
    # merged truth (the gate base asserted it absent).
    assert "/api/v1/scenarios/library/bind-plans" in paths


def test_a_module_map_slice_docs_and_roadmap_present():
    init_text = (REPO / "src" / "runmal" / "scenarios" / "__init__.py"
                 ).read_text(encoding="utf-8")
    for token in ("store", "binding", "storedexport", "organisation",
                  "bindpreview", "chatpreview", "candidatechatpreview",
                  "deletepreview", "chatdeletepreview", "replacepreview",
                  "candidatepreview", "bindingcensus", "chatcensus",
                  "custodycensus", "definitioncensus", "chatcoverage",
                  "reportcensus", "packs", "packpreview",
                  "P-131", "P-144", "P-148", "P-150", "P-151", "P-152"):
        assert token in init_text, token
    for doc in (
            "SCENARIO_DEFINITIONS_2026-11-08.md",
            "SCENARIO_BINDING_2026-11-08.md",
            "SCENARIO_STORED_EXPORT_2026-11-08.md",
            "SCENARIO_ORGANISATION_2026-11-08.md",
            "SCENARIO_BINDING_READ_SURFACE_2026-11-08.md",
            "SCENARIO_BIND_PLAN_PREVIEW_2026-11-08.md",
            "SCENARIO_DUPLICATION_2026-11-08.md",
            "SCENARIO_BIND_PLAN_CHAT_PREVIEW_2026-11-08.md",
            "SCENARIO_DELETE_IMPACT_2026-11-08.md",
            "SCENARIO_REPLACE_IMPACT_2026-11-08.md",
            "SCENARIO_PACKS_2026-11-08.md",
            "SCENARIO_NATIVE_VOXTA_EXPORT_2026-11-08.md",
            "SCENARIO_PACK_IMPORT_PREVIEW_2026-11-08.md",
            "SCENARIO_BINDING_CENSUS_2026-11-08.md",
            "SCENARIO_UNMAPPABLE_CENSUS_2026-11-08.md",
            "SCENARIO_CANDIDATE_REPLACE_PREVIEW_2026-11-08.md",
            "SCENARIO_CANDIDATE_CHAT_PREVIEW_2026-11-08.md",
            "SCENARIO_CHAT_CUSTODY_CENSUS_2026-11-08.md",
            "SCENARIO_CHAT_DELETE_IMPACT_2026-11-08.md",
            "SCENARIO_CUSTODY_CENSUS_2026-11-08.md",
            "SCENARIO_DEFINITION_CENSUS_2026-11-08.md",
            "SCENARIO_CHAT_COVERAGE_CENSUS_2026-11-08.md"):
        assert (REPO / "docs" / doc).exists(), doc
    roadmap = (REPO / "docs"
               / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"
               ).read_text(encoding="utf-8")
    assert "Visual Novel Engine" in roadmap
    assert "P-131" in roadmap and "P-154" in roadmap


def test_a_openapi_succeeds_and_names_scenario_roads(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    assert "/api/v1/scenarios" in paths
    assert "/api/v1/scenarios/bindings/census" in paths
    assert "/api/v1/scenarios/library/census" in paths
    assert "/api/v1/scenarios/chats/census" in paths


# -- Area B: one scenario world, together -----------------


async def test_b_bind_seeds_per_p093_missing_keys_only(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        bound = await bind_scenario(
            session, user, record.id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
    assert bound.definition_revision == 1
    assert len(bound.seeded_messages) == 2
    assert len(bound.seeded_keys) == 2
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
    assert [m.content for m in history] == [
        "The tide is going out.", "I never left."]
    assert get_variable(user, chat_id, "trust",
                        writer_kind="scenario",
                        writer_id="runmal.scenario",
                        base_dir=tmp_path) == 2
    flag = get_entry(user, chat_id, "met_maera",
                     writer_kind="scenario",
                     writer_id="runmal.scenario", base_dir=tmp_path)
    assert flag is not None and flag["value"] is True
    # P-093 law: a key the chat already holds is never
    # overwritten - it is named skipped on the record
    chat2 = await make_chat(factory, user, "Second")
    seed_variables(user, chat2, {"trust": 99}, base_dir=tmp_path)
    async with factory() as session:
        bound2 = await bind_scenario(
            session, user, record.id, chat2,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
    assert get_variable(user, chat2, "trust",
                        writer_kind="scenario",
                        writer_id="runmal.scenario",
                        base_dir=tmp_path) == 99
    assert any(s["key_or_index"] == "trust" for s in bound2.skipped)


async def test_b_chat_preview_judges_before_write_then_bind_agrees(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    before = _snap(tmp_path)
    async with factory() as session:
        env = await preview_bind_for_chat(
            session, record, user, chat_id,
            bindings=bindings, variables_base_dir=tmp_path)
    assert env is not None
    assert env["would_bind"] is True
    assert env["counts"] == preview_bind_plan(record)["counts"]
    assert env["plan"] == plan_materialisation(record.definition)
    assert len(env["keys"]["would_seed"]) == 2
    assert env["keys"]["already_present"] == []
    assert _snap(tmp_path) == before
    async with factory() as session:
        bound = await bind_scenario(
            session, user, record.id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
    assert len(bound.seeded_messages) == env["counts"]["messages"]
    assert len(bound.seeded_keys) == (
        env["counts"]["flags"] + env["counts"]["variables"])


async def test_b_binding_censuses_reconcile_p144_p148_p150(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    rec_a = definitions.create(user, body("Alpha"), now=NOW)
    rec_b = definitions.create(user, body("Beta"), now=NOW)
    live1 = await make_chat(factory, user, "Live One")
    live2 = await make_chat(factory, user, "Live Two")
    bindings.add(_rec("b1", user, live1, rec_a.id, name="Alpha", rev=1))
    bindings.add(_rec("b2", user, "chat-ghost", rec_a.id,
                      name="Alpha", rev=1))
    bindings.add(_rec("b3", user, live2, rec_b.id, name="Beta", rev=99))
    records = definitions.list_for_owner(user)
    live_ids = {r.id for r in records}
    c144 = census_bindings(bindings, user, records)
    async with factory() as session:
        c148 = await census_binding_chats(session, bindings, user, live_ids)
        c150 = await census_binding_custody(
            session, bindings, user, records)
    assert c144["counts"]["bindings_total"] == 3
    assert c148["counts"]["bindings_total"] == 3
    assert c150["counts"]["bindings_total"] == 3
    for key in ("current", "superseded", "ahead", "stale"):
        assert c150["counts"][key] == c144["counts"][key], key
    for key in ("live", "orphaned"):
        assert c150["counts"][key] == c148["counts"][key], key
    join = {("current", "live"): "sound",
            ("current", "orphaned"): "chat_orphaned",
            ("ahead", "live"): "definition_drift"}
    for row in c150["bindings"]:
        assert row["custody_state"] == join[
            (row["state"], row["chat_state"])], row
    assert c150["counts"]["sound"] == 1
    assert c150["counts"]["chat_orphaned"] == 1
    assert c150["counts"]["definition_drift"] == 1


async def test_b_definition_and_chat_censuses_reconcile_p151_p152(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    rec_a = definitions.create(user, body("Alpha"), now=NOW)
    definitions.create(user, body("Beta"), now=NOW)
    bound_chat = await make_chat(factory, user, "Bound")
    await make_chat(factory, user, "Free")
    bindings.add(_rec("b1", user, bound_chat, rec_a.id,
                      name="Alpha", rev=1))
    records = definitions.list_for_owner(user)
    async with factory() as session:
        c151 = await census_definitions(session, bindings, user, records)
        c152 = await census_chat_coverage(session, bindings, user, records)
    assert c151["counts"]["definitions_total"] == 2
    assert c151["counts"]["definitions_unbound"] == 1
    assert c151["counts"]["definitions_sound"] == 1
    assert c152["counts"]["chats_total"] == 2
    assert c152["counts"]["chats_unbound"] == 1
    assert c152["counts"]["chats_sound"] == 1
    assert c151["counts"]["bindings_total"] == 1
    assert c152["counts"]["bindings_total"] == 1


def test_b_bind_plan_census_overlay_reconciles_with_p136(tmp_path):
    # P-153 is NOT in this base: load its committed module
    # read-only from the team-02 worktree (P-116 overlay
    # precedent) and reconcile against in-base P-136.
    module_path = TEAM02 / "src" / "runmal" / "scenarios" / "plancensus.py"
    assert module_path.exists()
    spec = importlib.util.spec_from_file_location(
        "p153_plancensus_overlay", module_path)
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)
    definitions, _b, _o = _stores(tmp_path)
    clean = definitions.create(OWNER, body("Clean"), now=NOW)
    partial_body = body("Partial")
    partial_body["initial_flags"] = {"met_maera": True, "bad_flag": "yes"}
    partial = definitions.create(OWNER, partial_body, now=NOW)
    empty = definitions.create(OWNER, {"name": "Empty"}, now=NOW)
    records = definitions.list_for_owner(OWNER)
    out = overlay.census_bind_plans(records)
    assert out["counts"]["definitions_total"] == 3
    by_id = {row["definition"]["id"]: row for row in out["definitions"]}
    for record in (clean, partial, empty):
        env = preview_bind_plan(record)
        row = by_id[record.id]
        assert row["definition"] == record.summary()
        assert row["planned_total"] == (
            env["counts"]["messages"] + env["counts"]["flags"]
            + env["counts"]["variables"])
        assert row["skipped_total"] == env["counts"]["skipped"]
        assert row["definition_revision"] == env["definition_revision"]
    assert by_id[clean.id]["plan_state"] == "clean"
    assert by_id[partial.id]["plan_state"] == "partial"
    assert by_id[empty.id]["plan_state"] == "empty"
    assert out["counts"]["planned_total"] == sum(
        row["planned_total"] for row in out["definitions"])
    assert out["counts"]["skipped_total"] == sum(
        entry["count"] for entry in out["by_where"])
    battery = (TEAM02 / "tests" / "test_p153_bind_plan_census.py"
               ).read_text(encoding="utf-8")
    assert battery.count("def test_") == 19


def test_b_duplicate_stored_export_and_organisation_compose(tmp_path):
    definitions, _b, organisation = _stores(tmp_path)
    record = definitions.create(
        OWNER, voxta_body("Vox Harbour", scripts=True), now=NOW)
    clone = definitions.duplicate(record.id, OWNER, now=NOW)
    assert clone.id != record.id
    assert clone.name == record.name + " (copy)"
    assert clone.definition["name"] == clone.name
    assert {k: v for k, v in clone.definition.items() if k != "name"} == {k: v for k, v in record.definition.items() if k != "name"}
    assert clone.report == record.report
    assert clone.source_format == record.source_format
    file_dict, _report = export_stored_definition(record, "native")
    assert file_dict == record.definition
    organisation.set_tags(record.id, OWNER, ["Harbour"], now=NOW)
    row = organisation.get(record.id, OWNER)
    assert row is not None and list(row.tags) == ["Harbour"]
    from runmal.scenarios.organisation import enrich_summary, list_tags
    enriched = enrich_summary(record.summary(), row)
    assert enriched["tags"] == ["Harbour"]
    tags = list_tags(definitions.list_for_owner(OWNER),
                     {record.id: row, clone.id: None})
    assert [t["tag"] for t in tags] == ["Harbour"]


def test_b_pack_preview_agrees_with_pack_import(tmp_path):
    definitions, _b, _o = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    pack = build_pack(record, exported_at=NOW)
    inspected = inspect_pack(pack)
    assert inspected["valid"] is True
    assert inspected["checksum_verified"] is True
    assert inspected["definition_name"] == record.name
    assert inspected["provenance"]["source_report"] == record.report
    out = preview_pack_import(definitions, OWNER, pack)
    assert out["outcome"] == "duplicate_exact"
    assert out["would_create"] is False
    again, _rep = import_pack(definitions, OWNER, pack, now=NOW)
    assert again.id == record.id
    assert len(definitions.list_for_owner(OWNER)) == 1
    fresh = ScenarioStore(tmp_path / "fresh.json")
    preview = preview_pack_import(fresh, OWNER, pack)
    assert preview["outcome"] == "would_create"
    created, _rep2 = import_pack(fresh, OWNER, pack, now=NOW)
    assert created.definition == record.definition
    assert created.id != record.id


async def test_b_candidate_previews_judge_without_writing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    live_ids = {r.id for r in definitions.list_for_owner(user)}
    before = _snap(tmp_path)
    env = preview_candidate_replace(
        record, bindings, organisation, live_ids, revised_body())
    assert env["definition_id"] == record.id
    assert env["next_revision"] == 2
    assert env["candidate"]["definition"] != record.definition
    async with factory() as session:
        chat_env = await preview_candidate_for_chat(
            session, record, user, chat_id, revised_body(),
            bindings=bindings, variables_base_dir=tmp_path)
    assert chat_env is not None
    assert chat_env["definition_id"] == record.id
    assert _snap(tmp_path) == before
    assert definitions.get(record.id, user).revision == 1


# -- Area C: custody seams agree --------------------------


def test_c_delete_definition_orphans_named_never_repaired(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id,
                      name=record.name, rev=1))
    organisation.set_tags(record.id, OWNER, ["Harbour"], now=NOW)
    live_ids = {r.id for r in definitions.list_for_owner(OWNER)}
    env = preview_delete_impact(record, bindings, organisation, live_ids)
    assert [row["id"] for row in env["bindings"]] == ["b1"]
    assert env["organisation_row_exists"] is True
    definitions.remove(record.id, OWNER)
    out = census_bindings(bindings, OWNER, [])
    assert out["counts"]["stale"] == 1
    # named, never repaired: both orphan rows still stand
    assert bindings.get_for_chat("chat-1", OWNER) is not None
    assert organisation.get(record.id, OWNER) is not None


def test_c_replace_leaves_superseded_pin_named(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id,
                      name=record.name, rev=1))
    live_ids = {r.id for r in definitions.list_for_owner(OWNER)}
    env = preview_replace_impact(record, bindings, organisation, live_ids)
    assert env["next_revision"] == 2
    assert [row["id"] for row in env["bindings"]] == ["b1"]
    definitions.replace(record.id, OWNER, revised_body(), now=NOW)
    out = census_bindings(bindings, OWNER,
                           definitions.list_for_owner(OWNER))
    assert out["counts"]["superseded"] == 1
    assert bindings.get_for_chat("chat-1", OWNER).definition_revision == 1


async def test_c_chat_deletion_leaves_binding_byte_untouched(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        await bind_scenario(
            session, user, record.id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
        env = await preview_chat_delete_impact(
            session, bindings, definitions, user, chat_id)
    assert env is not None
    assert env["impact"]["binding_would_orphan"] is True
    binds_file = tmp_path / "scenario_bindings.json"
    before = binds_file.read_bytes()
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    # today's law, measured: delete_chat does NOT cascade
    # into the binding store (the decision is Volmarr's)
    assert binds_file.read_bytes() == before
    live_ids = {r.id for r in definitions.list_for_owner(user)}
    async with factory() as session:
        c148 = await census_binding_chats(session, bindings, user, live_ids)
    assert c148["counts"]["orphaned"] == 1


async def test_c_unbind_removes_only_the_record(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        await bind_scenario(
            session, user, record.id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
    removed = unbind(bindings, user, chat_id)
    assert removed is not None and removed.chat_id == chat_id
    assert get_binding(bindings, user, chat_id) is None
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
    assert len(history) == 2
    assert get_variable(user, chat_id, "trust",
                        writer_kind="scenario",
                        writer_id="runmal.scenario",
                        base_dir=tmp_path) == 2


async def test_c_every_census_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    organisation.set_tags(record.id, user, ["Harbour"], now=NOW)
    records = definitions.list_for_owner(user)
    live_ids = {r.id for r in records}
    before = _snap(tmp_path)
    census_bindings(bindings, user, records)
    census_unmappable(records)
    async with factory() as session:
        await census_binding_chats(session, bindings, user, live_ids)
        await census_binding_custody(session, bindings, user, records)
        await census_definitions(session, bindings, user, records)
        await census_chat_coverage(session, bindings, user, records)
    assert _snap(tmp_path) == before


async def test_c_every_preview_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    live_ids = {r.id for r in definitions.list_for_owner(user)}
    pack = build_pack(record, exported_at=NOW)
    before = _snap(tmp_path)
    preview_bind_plan(record)
    preview_delete_impact(record, bindings, organisation, live_ids)
    preview_replace_impact(record, bindings, organisation, live_ids)
    preview_candidate_replace(
        record, bindings, organisation, live_ids, revised_body())
    preview_pack_import(definitions, user, pack)
    async with factory() as session:
        await preview_bind_for_chat(
            session, record, user, chat_id,
            bindings=bindings, variables_base_dir=tmp_path)
        await preview_candidate_for_chat(
            session, record, user, chat_id, revised_body(),
            bindings=bindings, variables_base_dir=tmp_path)
        await preview_chat_delete_impact(
            session, bindings, definitions, user, chat_id)
    assert _snap(tmp_path) == before
    assert definitions.get(record.id, user).revision == 1


# -- Area D: honest accounting, pinned --------------------


def test_d_f1_closed_stateless_agrees_with_stored(tmp_path):
    out = export_voxta(parse_scenario_file(body()))
    assert "scenario" in out
    assert "scenario_text" not in out
    assert "initial_variables" not in out
    assert "initial_flags" not in out
    assert "bootstrap_messages" not in out
    assert parse_scenario_file(out).source_format == "voxta"
    definitions, _b, _o = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    file_dict, _report = export_stored_definition(record, "voxta")
    assert file_dict == out


def test_d_unmappable_named_never_persisted_never_restored(tmp_path):
    definitions, _b, _o = _stores(tmp_path)
    record = definitions.create(
        OWNER, voxta_body("Vox Script", scripts=True), now=NOW)
    assert record.source_format == "voxta"
    assert "scripts" not in record.definition
    census = census_unmappable([record])
    assert census["counts"]["unmappable_total"] >= 1
    assert census["counts"]["definitions_with_unmappable"] == 1
    _file, report = export_stored_definition(record, "native")
    assert len(report["not_restored"]) >= 1


async def test_d_content_stays_data_binding_executes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    record = definitions.create(
        user, voxta_body("Vox Data", scripts=True), now=NOW)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        bound = await bind_scenario(
            session, user, record.id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
        history = await svc.get_history(session, user, chat_id)
    assert bound.seeded_keys == []
    assert all("x=1" not in (m.content or "") for m in history)


async def test_d_delete_chat_cascade_reserved_and_untaken(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        await bind_scenario(
            session, user, record.id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
        env = await preview_chat_delete_impact(
            session, bindings, definitions, user, chat_id)
    notes = " ".join(env["notes"])
    assert "does not cascade into the scenario binding store" in notes
    assert "no in-tree record has taken" in notes
    assert "does not take it" in notes
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    # the orphaned record still answers the per-chat read
    # exactly as if the chat lived - named, not erased
    standing = get_binding(bindings, user, chat_id)
    assert standing is not None and standing.definition_id == record.id


def test_d_portable_archive_carries_no_scenario_store():
    portable_dir = REPO / "src" / "runmal" / "portable"
    hits = []
    for path in portable_dir.rglob("*.py"):
        if "scenario" in path.read_text(encoding="utf-8").lower():
            hits.append(path.name)
    assert hits == []
    from runmal.scenarios.binding import BINDINGS_FILENAME
    from runmal.scenarios.organisation import ORGANISATION_FILENAME
    from runmal.scenarios.store import DEFINITIONS_FILENAME
    assert DEFINITIONS_FILENAME.endswith(".json")
    assert BINDINGS_FILENAME.endswith(".json")
    assert ORGANISATION_FILENAME.endswith(".json")


async def test_d_censuses_are_owner_scoped(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings, _org = _stores(tmp_path)
    mine = definitions.create(user, body("Mine"), now=NOW)
    foreign = definitions.create(FOREIGN, body("Foreign"), now=NOW)
    my_chat = await make_chat(factory, user)
    bindings.add(_rec("b1", user, my_chat, mine.id, name="Mine", rev=1))
    bindings.add(_rec("b2", FOREIGN, "chat-foreign", foreign.id,
                      name="Foreign", rev=1))
    records = definitions.list_for_owner(user)
    c144 = census_bindings(bindings, user, records)
    assert c144["counts"]["bindings_total"] == 1
    assert c144["bindings"][0]["id"] == "b1"
    async with factory() as session:
        c151 = await census_definitions(session, bindings, user, records)
        c152 = await census_chat_coverage(session, bindings, user, records)
    assert c151["counts"]["definitions_total"] == 1
    assert c152["counts"]["chats_total"] == 1
    assert census_unmappable(records)["counts"]["definitions_total"] == 1


# -- Hygiene ----------------------------------------------


def test_h_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "gate.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"


def test_h_gate_world_lives_only_in_this_battery():
    hits = []
    for root in (REPO / "src", REPO / "tests"):
        for path in root.rglob("*.py"):
            if Z in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(path)
    assert hits == [Path(__file__)]
