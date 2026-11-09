"""P-193 - Hub content census, content coverage (Part XII, DERIVED).

Pins: the content-census document (schema tag,
census_state under the closed CONTENT_CENSUS_STATES law
judged on the content axis: no_entries / no_content /
some_content / all_content); composition verbatim (the
embedded list equals a direct P-187 list_document call;
each pack measured ONLY through its own layer's verified
parse road - parse_pack x3, parse_share for the preset
bundle - under P-188's locator law and imported size
bound); the volume law (per-row and per-kind string
value / string character counts under P-191's string
walk law, summed to the totals; the largest content
holder); the honesty exclusions (dict keys, non-string
values and content_sha256 subtrees are never counted;
no content text or payload appears anywhere in the
document); the no-silent-omission law (every entry
parsed or named by its row outcome under the closed
OUTCOMES law, coverage_complete as data, count =
parsed + unavailable + invalid); the distinctness fence
(P-189's census over the same estate carries no volume
field and this census carries no browse/checksum axis);
the pure-read law (registry and pack bytes unchanged);
owner scoping (unit and HTTP); the HTTP road (200
owner, 401 without a bearer); and the neighbours
(migration head stays 0041; the bound is P-188's own).
No network: fixtures only.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import census as hub_census
from runmal.hub import content_census as hub_cc
from runmal.hub import registry as hub
from runmal.lorebooks import packs as lorebook_packs
from runmal.plugins import service as plugin_service
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs
from runmal.scenarios.store import ScenarioStore

STAMP = "2026-11-09T00:00:00+00:00"


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
    record = store.create("owner-p193", body, now=STAMP)
    pack = scenario_packs.build_pack(record, exported_at=STAMP)
    path = tmp_path / "scenario-pack.json"
    path.write_bytes(scenario_packs.pack_to_bytes(pack))
    return str(path), pack


def _bundle_file(tmp_path, *, bare: bool = False):
    bundle = preset_bundles.validate_bundle({
        "name": "Hall Bundle",
        "prompts": [{"identifier": "main",
                     "content": "Zephyr bundle text for the hall."}],
        "prompt_order": [{"identifier": "main", "enabled": True}],
    })
    share = preset_bundles.build_share(bundle, exported_at=STAMP)
    path = tmp_path / "preset-bundle.json"
    if bare:
        path.write_text(json.dumps(bundle))
        return str(path), bundle
    path.write_text(json.dumps(share))
    return str(path), share


def _expected_stats(entry, raw):
    """Independent test-side measure: the owning layer's
    own parse road, then a plain recursive string walk
    skipping content_sha256 subtrees."""
    if entry.kind == "lorebook_pack":
        payload = lorebook_packs.parse_pack(raw)["lorebook"]
    elif entry.kind == "prompt_pack":
        payload = prompt_packs.parse_pack(raw)["items"]
    elif entry.kind == "scenario_pack":
        payload = scenario_packs.parse_pack(raw)["scenario"]
    else:
        payload, _report = preset_bundles.parse_share(
            json.loads(raw.decode("utf-8")))
    count = 0
    chars = 0
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key != "content_sha256":
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            count += 1
            chars += len(node)
    return count, chars


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


# ------------------------------------------------------------ the estate view


def test_empty_estate_is_no_entries_with_zero_filled_axes(tmp_path):
    doc = hub_cc.content_census_document([])
    assert doc["schema"] == "runmal-p193-hub-content-census-v1"
    assert doc["census_state"] == "no_entries"
    assert doc["census_state"] in hub_cc.CONTENT_CENSUS_STATES
    assert doc["count"] == 0
    assert doc["entries"] == []
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 0, "unavailable": 0}
    assert doc["by_kind_content"] == {
        kind: {"entries": 0, "parsed": 0,
               "string_values": 0, "string_chars": 0}
        for kind in hub.KIND_FORMATS}
    assert doc["total_string_values"] == 0
    assert doc["total_string_chars"] == 0
    assert doc["largest_content_entry"] is None
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS
    assert doc["max_browse_bytes"] == hub_cc.MAX_BROWSE_BYTES


def test_full_estate_all_content_and_measured_verbatim(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_content"
    assert doc["count"] == 4
    assert doc["parsed_count"] == 4
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document(entries)
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 4, "unavailable": 0}
    total_values = 0
    total_chars = 0
    for row, entry in zip(doc["entries"], entries, strict=True):
        raw = open(entry.locator, "rb").read()
        values, chars = _expected_stats(entry, raw)
        assert row["id"] == entry.id
        assert row["outcome"] == "parsed"
        assert row["string_value_count"] == values
        assert row["string_char_count"] == chars
        assert values > 0 and chars > 0
        assert row["error"] == ""
        total_values += values
        total_chars += chars
        axis = doc["by_kind_content"][entry.kind]
        assert axis == {"entries": 1, "parsed": 1,
                        "string_values": values,
                        "string_chars": chars}
    assert doc["total_string_values"] == total_values
    assert doc["total_string_chars"] == total_chars
    kind_sums = doc["by_kind_content"].values()
    assert sum(a["string_values"] for a in kind_sums) == total_values
    assert sum(a["string_chars"] for a in kind_sums) == total_chars
    largest = doc["largest_content_entry"]
    assert largest["string_char_count"] == max(
        row["string_char_count"] for row in doc["entries"])
    assert largest["id"] in {row["id"] for row in doc["entries"]}


def test_verified_checksums_are_the_parse_roads_own(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    doc = hub_cc.content_census_document(entries)
    for row, entry in zip(doc["entries"], entries, strict=True):
        assert row["verified_content_sha256"] == entry.content_sha256
        assert row["verified_content_sha256"] != ""


def test_mixed_estate_is_some_content_with_named_outcomes(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Good", locator,
              pack["manifest"]["content_sha256"])
    _register(store, "prompt_pack", "Ghost", str(tmp_path / "ghost.json"))
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    _register(store, "scenario_pack", "Broken", str(bad))
    _register(store, "preset_bundle", "Dir", str(tmp_path))
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_content"
    assert doc["coverage_complete"] is False
    assert doc["by_outcome"] == {
        "invalid": 1, "parsed": 1, "unavailable": 2}
    assert doc["count"] == (
        doc["by_outcome"]["parsed"]
        + doc["by_outcome"]["unavailable"]
        + doc["by_outcome"]["invalid"])
    rows = {row["title"]: row for row in doc["entries"]}
    assert rows["Ghost"]["outcome"] == "unavailable"
    assert rows["Ghost"]["locator_state"] == "missing"
    assert rows["Ghost"]["string_value_count"] == 0
    assert rows["Dir"]["outcome"] == "unavailable"
    assert rows["Dir"]["locator_state"] == "not_a_file"
    assert rows["Broken"]["outcome"] == "invalid"
    assert rows["Broken"]["error"] != ""
    assert rows["Broken"]["verified_content_sha256"] == ""


def test_all_missing_estate_is_no_content(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Ghost", str(tmp_path / "g.json"))
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "no_content"
    assert doc["parsed_count"] == 0
    assert doc["total_string_values"] == 0
    assert doc["largest_content_entry"] is None
    assert doc["coverage_complete"] is False


def test_bare_bundle_parsed_with_empty_verified_checksum(tmp_path):
    store = make_store(tmp_path)
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Bare", locator)
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "parsed"
    assert row["verified_content_sha256"] == ""
    assert row["string_value_count"] > 0
    assert doc["census_state"] == "all_content"


def test_wrong_kind_pack_is_invalid_with_road_refusal(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _prompt_file(tmp_path)
    _register(store, "lorebook_pack", "Wrong kind", locator)
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] != ""
    assert doc["census_state"] == "no_content"


def test_oversize_pack_is_invalid_under_the_imported_bound(
        tmp_path, monkeypatch):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Big", locator)
    monkeypatch.setattr(hub_cc, "MAX_BROWSE_BYTES", 8)
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] == "pack file too large to census"
    assert doc["max_browse_bytes"] == 8


# ------------------------------------------------------------ the walk law


def test_walker_excludes_keys_non_strings_and_sha_subtrees():
    payload = {
        "content_sha256": "z" * 64,
        "nested": {"content_sha256": {"deep": "hidden"},
                   "keep": "yes"},
        "items": ["one", 7, True, None, {"two": "2"}],
        "number": 42,
    }
    assert hub_cc._string_stats(payload) == (3, 7)
    assert list(hub_cc._string_values(payload)) == ["yes", "one", "2"] or \
        set(hub_cc._string_values(payload)) == {"yes", "one", "2"}


def test_no_content_text_anywhere_in_the_document(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "A pack", locator)
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    blob = json.dumps(doc)
    assert "Zephyr Quill writes storms" not in blob
    assert '"excerpt":' not in blob
    assert '"payload":' not in blob


def test_largest_content_entry_and_tie_keeps_store_order(tmp_path):
    store = make_store(tmp_path)
    small, _p1 = _lorebook_file(tmp_path, "small.json")
    big_entries = [_lore_entry(
        "e9", "Big Entry", "x" * 400, ["k"])]
    big, _p2 = _lorebook_file(tmp_path, "big.json", big_entries)
    _register(store, "lorebook_pack", "Small", small)
    _register(store, "lorebook_pack", "Big", big)
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    assert doc["largest_content_entry"]["title"] == "Big"
    store2 = make_store(tmp_path / "second")
    a, _pa = _lorebook_file(tmp_path, "a.json")
    b, _pb = _lorebook_file(tmp_path, "b.json")
    first = _register(store2, "lorebook_pack", "First", a)
    _register(store2, "lorebook_pack", "Second", b)
    doc2 = hub_cc.content_census_document(store2.list_for_owner("u1"))
    rows = doc2["entries"]
    if rows[0]["string_char_count"] == rows[1]["string_char_count"]:
        assert doc2["largest_content_entry"]["id"] == first.id


# ------------------------------------------------------------ distinctness


def test_distinct_from_p189_census_axes(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    estate = store.list_for_owner("u1")
    p189 = hub_census.census_document(estate)
    p193 = hub_cc.content_census_document(estate)
    assert "total_string_values" not in json.dumps(p189)
    assert "string_value_count" not in json.dumps(p189)
    assert "by_browse_state" not in p193
    assert "by_checksum_match" not in p193
    for row in p193["entries"]:
        assert "browse_state" not in row
        assert "checksum_match" not in row
    # The expected agreement, stated in the design: parsed
    # counts match P-189's inspected counts on a clean
    # estate, because inspect stands on parse.
    assert p193["by_outcome"]["parsed"] == \
        p189["by_browse_state"]["inspected"]


# ------------------------------------------------------------ pure read / scope


def test_census_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = {e.locator: open(e.locator, "rb").read()
                  for e in entries}
    hub_cc.content_census_document(store.list_for_owner("u1"))
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes
    for locator, raw in pack_bytes.items():
        assert open(locator, "rb").read() == raw


def test_foreign_entries_never_enter_the_census(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Mine", locator,
              pack["manifest"]["content_sha256"], owner="u1")
    _register(store, "lorebook_pack", "Theirs", locator,
              pack["manifest"]["content_sha256"], owner="u2")
    doc = hub_cc.content_census_document(store.list_for_owner("u1"))
    assert doc["count"] == 1
    assert doc["entries"][0]["title"] == "Mine"


def test_http_road_owner_scoped_and_bearer_gated(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Mine",
        "locator": locator,
        "content_sha256": pack["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/content-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["schema"] == "runmal-p193-hub-content-census-v1"
    assert doc["count"] == 1
    assert doc["entries"][0]["outcome"] == "parsed"
    bare = TestClient(create_app(_factory))
    assert bare.get("/api/v1/hub/content-census").status_code == 401


def test_neighbours_migration_head_and_bound_law(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == MIGRATIONS[-1][0] == "0041"
    assert hub_cc.MAX_BROWSE_BYTES == 16 * 1024 * 1024
    import runmal.hub.browse as browse_module
    assert hub_cc.MAX_BROWSE_BYTES == browse_module.MAX_BROWSE_BYTES
