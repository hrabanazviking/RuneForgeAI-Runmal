"""P-195 - Hub duplicate-content census (Part XII, DERIVED).

Pins: the duplicate-census document (schema tag,
census_state under the closed DUPLICATE_CENSUS_STATES
law judged on the duplicate axis: no_entries /
no_duplicates / some_duplicates / all_duplicates);
composition verbatim (P-193's content census composed
once and embedded whole; the pure aggregator over a
direct P-193 document equals the composing wrapper);
the identity law (only a NON-EMPTY verified checksum
is an identity - grouping is by the verified checksum
alone, regardless of kind or of the caller's claim);
the partition law (duplicate + unique + unidentified
always equals the estate count); the honesty law for
bare bundles (two byte-identical bare bundles are
unidentified, never grouped - no identity was
verified and none is faked); claim irrelevance both
ways (different claims cannot break a verified group;
one shared claim cannot create one); coverage honesty
(unavailable / invalid rows are unidentified and the
composed coverage verdict rides verbatim); the
distinctness fence (no P-189 browse/checksum axis, no
P-193 volume axis and no P-194 matched-by axis among
the census's own top-level fields); the pure-read law
(registry and pack bytes unchanged); owner scoping
(unit and HTTP); the HTTP road (200 owner, 401
without a bearer); and the neighbours (migration head
stays 0041; the composed laws are P-187's and
P-193's banked ones). No network: fixtures only.
"""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import content_census as hub_cc
from runmal.hub import duplicate_census as hub_dc
from runmal.hub import registry as hub
from runmal.lorebooks import packs as lorebook_packs
from runmal.plugins import service as plugin_service
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs
from runmal.scenarios.store import ScenarioStore

STAMP = "2026-11-09T00:00:00+00:00"
WRONG_SHA = "0" * 64


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def make_store(tmp_path):
    return hub.HubStore(tmp_path / "data")


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


def _register(store, kind, title, locator, sha="", owner="u1"):
    return hub.register_entry(
        store, owner_id=owner, kind=kind, title=title,
        locator=locator, content_sha256=sha)


# ------------------------------------------------------------ pack fixtures


def _lore_entry(eid, name, content, keys):
    return {
        "id": eid, "lorebook_id": "book-1", "name": name,
        "content": content, "keys": keys, "secondary_keys": [],
        "selective_logic": "and_any", "inclusion_group": "",
        "group_weight": 100, "probability": 100, "priority": 100,
        "position": "before_char", "depth": None, "role": "system",
        "enabled": True, "constant": False, "vectorised": False,
        "case_sensitive": False, "whole_word": True,
        "sticky_prompts": 0, "cooldown_prompts": 0,
        "delay_prompts": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": None,
    }


def _lorebook_file(tmp_path, name="lorebook-pack.json", entries=None):
    if entries is None:
        entries = [_lore_entry(
            "e1", "Mist Entry",
            "The Zephyr Quill writes storms.", ["quill"])]
    book = {
        "id": "book-1", "name": "Plain Book",
        "description": "World lore.", "scan_depth": 7,
        "token_budget": 900, "scan_mode": "depth",
        "scan_external_context": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "entry_count": len(entries),
    }
    pack = lorebook_packs.build_pack(book, entries, exported_at=STAMP)
    path = tmp_path / name
    path.write_bytes(lorebook_packs.pack_to_bytes(pack))
    return str(path), pack


def _prompt_file(tmp_path):
    item = {
        "kind": "preset", "name": "Hall Preset",
        "payload": {
            "name": "Hall Preset",
            "params": {"temperature": 0.7},
            "template_ref": "", "source_format": "st-chat",
            "raw": {"temperature": 0.7},
            "prompts": [{"identifier": "main",
                        "content": "Zephyr prompt text for the hall."}],
            "prompt_order": [{"identifier": "main", "enabled": True}],
        },
    }
    pack = prompt_packs.build_pack("Workshop", [item], exported_at=STAMP)
    path = tmp_path / "prompt-pack.json"
    path.write_bytes(prompt_packs.pack_to_bytes(pack))
    return str(path), pack


def _scenario_file(tmp_path):
    store = ScenarioStore(tmp_path / "scenarios.json")
    body = {
        "name": "Harbour Lights",
        "description": "A quiet harbour.",
        "scenario_text": "The Zephyr ferry has just left.",
        "flow": "story", "style": "storytelling",
        "narrator_name": "The Harbour Voice",
        "impersonation_name": "Ash",
        "roles": [{"name": "Narrator", "character_name": "Maera",
                   "enabled_on_start": True, "can_speak": True}],
        "bootstrap_messages": [
            {"kind": "note", "text": "The tide is going out.",
             "role": "Narrator"}],
        "initial_flags": {"met_maera": True},
        "initial_variables": {"trust": 2},
    }
    record = store.create("owner-p195", body, now=STAMP)
    pack = scenario_packs.build_pack(record, exported_at=STAMP)
    path = tmp_path / "scenario-pack.json"
    path.write_bytes(scenario_packs.pack_to_bytes(pack))
    return str(path), pack


def _bundle_file(tmp_path, *, bare: bool = False,
                 name="preset-bundle.json"):
    bundle = preset_bundles.validate_bundle({
        "name": "Hall Bundle",
        "prompts": [{"identifier": "main",
                     "content": "Zephyr bundle text for the hall."}],
        "prompt_order": [{"identifier": "main", "enabled": True}],
    })
    share = preset_bundles.build_share(bundle, exported_at=STAMP)
    path = tmp_path / name
    if bare:
        path.write_text(json.dumps(bundle))
        return str(path), bundle
    path.write_text(json.dumps(share))
    return str(path), share


def _full_estate(tmp_path, store):
    entries = []
    for kind, maker in (
            ("lorebook_pack", _lorebook_file),
            ("prompt_pack", _prompt_file),
            ("scenario_pack", _scenario_file),
            ("preset_bundle", _bundle_file)):
        locator, pack = maker(tmp_path)
        sha = pack["manifest"]["content_sha256"] \
            if "manifest" in pack else ""
        entries.append(_register(store, kind, "A pack", locator, sha))
    return entries


def _copy(tmp_path, locator, name):
    target = tmp_path / name
    shutil.copyfile(locator, target)
    return str(target)


def _partition(doc):
    return (
        doc["duplicate_entry_count"] + doc["unique_entry_count"]
        + doc["unidentified_entry_count"])


# ------------------------------------------------------------ the estate view


def test_empty_estate_is_no_entries_with_zero_filled_axes(tmp_path):
    doc = hub_dc.duplicate_census_document([])
    assert doc["schema"] == "runmal-p195-hub-duplicate-census-v1"
    assert doc["census_state"] == "no_entries"
    assert doc["census_state"] in hub_dc.DUPLICATE_CENSUS_STATES
    assert doc["count"] == 0
    assert doc["duplicate_groups"] == []
    assert doc["duplicate_group_count"] == 0
    assert doc["duplicate_entry_count"] == 0
    assert doc["redundant_copy_count"] == 0
    assert doc["distinct_content_count"] == 0
    assert doc["unique_entry_count"] == 0
    assert doc["unidentified_entry_count"] == 0
    assert doc["parsed_count"] == 0
    assert doc["coverage_complete"] is True
    assert doc["largest_duplicate_group"] is None
    assert doc["by_kind"] == {
        kind: {"entries": 0, "duplicate_entries": 0}
        for kind in hub.KIND_FORMATS}
    assert doc["content_census"] == hub_cc.content_census_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS


def test_full_unique_estate_is_no_duplicates(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "no_duplicates"
    assert doc["count"] == 4
    assert doc["parsed_count"] == 4
    assert doc["coverage_complete"] is True
    assert doc["distinct_content_count"] == 4
    assert doc["unique_entry_count"] == 4
    assert doc["duplicate_entry_count"] == 0
    assert doc["unidentified_entry_count"] == 0
    assert _partition(doc) == doc["count"]
    assert doc["duplicate_groups"] == []
    assert doc["largest_duplicate_group"] is None
    assert doc["by_kind"] == {
        kind: {"entries": 1, "duplicate_entries": 0}
        for kind in hub.KIND_FORMATS}


def test_composition_is_the_direct_content_census_verbatim(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    direct = hub_cc.content_census_document(entries)
    built = hub_dc.build_duplicate_census(direct)
    wrapped = hub_dc.duplicate_census_document(entries)
    assert wrapped == built
    assert wrapped["content_census"] == direct
    assert wrapped["content_census"]["schema"] == \
        "runmal-p193-hub-content-census-v1"
    assert wrapped["parsed_count"] == direct["parsed_count"]
    assert wrapped["coverage_complete"] == direct["coverage_complete"]


def test_duplicate_pair_plus_unique_is_some_duplicates(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    first = _register(store, "lorebook_pack", "First copy", locator, sha)
    second = _register(
        store, "lorebook_pack", "Second copy",
        _copy(tmp_path, locator, "lorebook-copy.json"), sha)
    plocator, ppack = _prompt_file(tmp_path)
    _register(store, "prompt_pack", "Solo",
              plocator, ppack["manifest"]["content_sha256"])
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_duplicates"
    assert doc["count"] == 3
    assert doc["distinct_content_count"] == 2
    assert doc["duplicate_group_count"] == 1
    assert doc["duplicate_entry_count"] == 2
    assert doc["redundant_copy_count"] == 1
    assert doc["unique_entry_count"] == 1
    assert doc["unidentified_entry_count"] == 0
    assert _partition(doc) == doc["count"]
    group = doc["duplicate_groups"][0]
    assert group["verified_content_sha256"] == sha
    assert group["count"] == 2
    assert [m["id"] for m in group["entries"]] == [first.id, second.id]
    assert [m["title"] for m in group["entries"]] == [
        "First copy", "Second copy"]
    assert all(m["kind"] == "lorebook_pack" for m in group["entries"])
    assert all(m["string_value_count"] > 0 for m in group["entries"])
    assert doc["largest_duplicate_group"] == {
        "verified_content_sha256": sha, "count": 2}
    assert doc["by_kind"]["lorebook_pack"] == {
        "entries": 2, "duplicate_entries": 2}
    assert doc["by_kind"]["prompt_pack"] == {
        "entries": 1, "duplicate_entries": 0}
    assert sum(a["entries"] for a in doc["by_kind"].values()) == 3
    assert sum(
        a["duplicate_entries"] for a in doc["by_kind"].values()) == 2


def test_duplicate_only_estate_is_all_duplicates(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _scenario_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "scenario_pack", "One", locator, sha)
    _register(store, "scenario_pack", "Two",
              _copy(tmp_path, locator, "scenario-copy.json"), sha)
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_duplicates"
    assert doc["duplicate_entry_count"] == doc["count"] == 2
    assert doc["unique_entry_count"] == 0
    assert doc["unidentified_entry_count"] == 0
    assert _partition(doc) == doc["count"]


def test_triple_copy_redundant_count_and_largest_group(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "A", locator, sha)
    _register(store, "lorebook_pack", "B",
              _copy(tmp_path, locator, "copy-b.json"), sha)
    _register(store, "lorebook_pack", "C",
              _copy(tmp_path, locator, "copy-c.json"), sha)
    plocator, ppack = _prompt_file(tmp_path)
    psha = ppack["manifest"]["content_sha256"]
    _register(store, "prompt_pack", "P1", plocator, psha)
    _register(store, "prompt_pack", "P2",
              _copy(tmp_path, plocator, "prompt-copy.json"), psha)
    slocator, spack = _scenario_file(tmp_path)
    _register(store, "scenario_pack", "Solo", slocator,
              spack["manifest"]["content_sha256"])
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_duplicates"
    assert doc["count"] == 6
    assert doc["unique_entry_count"] == 1
    assert _partition(doc) == doc["count"]
    assert doc["duplicate_group_count"] == 2
    assert doc["duplicate_entry_count"] == 5
    assert doc["redundant_copy_count"] == 3
    assert doc["largest_duplicate_group"] == {
        "verified_content_sha256": sha, "count": 3}
    assert [g["count"] for g in doc["duplicate_groups"]] == [3, 2]


def test_largest_group_tie_keeps_first_appearance_order(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "A", locator, sha)
    _register(store, "lorebook_pack", "B",
              _copy(tmp_path, locator, "copy-b.json"), sha)
    plocator, ppack = _prompt_file(tmp_path)
    psha = ppack["manifest"]["content_sha256"]
    _register(store, "prompt_pack", "P1", plocator, psha)
    _register(store, "prompt_pack", "P2",
              _copy(tmp_path, plocator, "prompt-copy.json"), psha)
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["largest_duplicate_group"] == {
        "verified_content_sha256": sha, "count": 2}
    assert [g["verified_content_sha256"]
            for g in doc["duplicate_groups"]] == [sha, psha]


def test_bare_bundles_are_unidentified_never_grouped(tmp_path):
    store = make_store(tmp_path)
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Bare one", locator)
    _register(store, "preset_bundle", "Bare two",
              _copy(tmp_path, locator, "bare-copy.json"))
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "no_duplicates"
    assert doc["parsed_count"] == 2
    assert doc["unidentified_entry_count"] == 2
    assert doc["distinct_content_count"] == 0
    assert doc["duplicate_groups"] == []
    assert _partition(doc) == doc["count"]


def test_claims_neither_create_nor_break_a_group(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Right claim", locator, sha)
    _register(store, "lorebook_pack", "Wrong claim",
              _copy(tmp_path, locator, "copy.json"), WRONG_SHA)
    plocator, ppack = _prompt_file(tmp_path)
    _register(store, "prompt_pack", "Shared claim", plocator, sha)
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["duplicate_group_count"] == 1
    assert doc["duplicate_groups"][0]["verified_content_sha256"] == sha
    assert doc["duplicate_entry_count"] == 2
    assert doc["unique_entry_count"] == 1
    assert _partition(doc) == doc["count"]


def test_unparsed_rows_are_unidentified_and_coverage_carried(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Good", locator, sha)
    _register(store, "lorebook_pack", "Twin",
              _copy(tmp_path, locator, "copy.json"), sha)
    _register(store, "prompt_pack", "Ghost", str(tmp_path / "ghost.json"))
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    _register(store, "scenario_pack", "Broken", str(bad))
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_duplicates"
    assert doc["coverage_complete"] is False
    assert doc["parsed_count"] == 2
    assert doc["unidentified_entry_count"] == 2
    assert doc["duplicate_entry_count"] == 2
    assert _partition(doc) == doc["count"] == 4
    composed = doc["content_census"]
    assert composed["by_outcome"] == {
        "invalid": 1, "parsed": 2, "unavailable": 1}


def test_same_locator_under_two_titles_is_one_registration_apart(
        tmp_path):
    # The registry refuses the identical (kind, locator)
    # triple; a duplicate holding needs its own locator -
    # the second file copy is what this census groups.
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Only", locator, sha)
    with pytest.raises(hub.HubError):
        _register(store, "lorebook_pack", "Again", locator, sha)
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "no_duplicates"
    assert doc["unique_entry_count"] == 1


# ------------------------------------------------------------ fences


def test_distinctness_fence_no_banked_axis_at_top_level(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    for field in (
            "by_browse_state", "by_checksum_match", "browse_state",
            "total_string_values", "total_string_chars",
            "by_kind_content", "largest_content_entry",
            "by_matched_by", "by_matched_field", "matches",
            "total_occurrences", "excerpt"):
        assert field not in doc
    composed = json.dumps(doc["content_census"])
    assert "Zephyr" not in json.dumps(
        {k: v for k, v in doc.items() if k != "content_census"})
    assert isinstance(composed, str)


def test_pure_read_registry_and_pack_bytes_unchanged(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "A", locator, sha)
    _register(store, "lorebook_pack", "B",
              _copy(tmp_path, locator, "copy.json"), sha)
    index_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = open(locator, "rb").read()
    hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert (tmp_path / "data" / "hub.json").read_bytes() == index_bytes
    assert open(locator, "rb").read() == pack_bytes


def test_owner_scoping_foreign_entries_never_counted(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Mine", locator, sha, owner="u1")
    _register(store, "lorebook_pack", "Theirs",
              _copy(tmp_path, locator, "copy.json"), sha, owner="u2")
    doc = hub_dc.duplicate_census_document(store.list_for_owner("u1"))
    assert doc["count"] == 1
    assert doc["census_state"] == "no_duplicates"
    other = hub_dc.duplicate_census_document(store.list_for_owner("u2"))
    assert other["count"] == 1
    assert other["census_state"] == "no_duplicates"


def test_neighbours_laws_are_the_banked_ones():
    assert hub_dc.hub_content_census is hub_cc
    assert hub_cc.CONTENT_CENSUS_SCHEMA == \
        "runmal-p193-hub-content-census-v1"
    assert hub_cc.OUTCOMES == frozenset(
        {"parsed", "unavailable", "invalid"})
    assert hub.HUB_KINDS == frozenset({
        "lorebook_pack", "prompt_pack",
        "preset_bundle", "scenario_pack"})
    assert MIGRATIONS[-1][0] == "0042"


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"


# ------------------------------------------------------------ HTTP


def test_http_duplicate_census_owner_reads_200(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    for title, loc in (
            ("A", locator),
            ("B", _copy(tmp_path, locator, "copy.json"))):
        created = client.post("/api/v1/hub/entries", json={
            "kind": "lorebook_pack", "title": title,
            "locator": loc, "content_sha256": sha})
        assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/duplicate-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["schema"] == "runmal-p195-hub-duplicate-census-v1"
    assert doc["census_state"] == "all_duplicates"
    assert doc["duplicate_group_count"] == 1
    assert doc["content_census"]["schema"] == \
        "runmal-p193-hub-content-census-v1"


def test_http_duplicate_census_skips_are_data_at_200(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "prompt_pack", "title": "Ghost",
        "locator": str(tmp_path / "ghost.json")})
    assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/duplicate-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["census_state"] == "no_duplicates"
    assert doc["unidentified_entry_count"] == 1
    assert doc["coverage_complete"] is False


def test_http_duplicate_census_requires_bearer(tmp_path):
    _factory, client = _client(tmp_path)
    client.headers.pop("Authorization")
    response = client.get("/api/v1/hub/duplicate-census")
    assert response.status_code == 401
