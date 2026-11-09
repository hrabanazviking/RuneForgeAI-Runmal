"""P-199 - Hub distinct-content census (Part XII, DERIVED).

Pins: the distinct-census document (schema tag,
census_state under the closed DISTINCT_CENSUS_STATES
law judged on the parsed axis: no_entries / no_distinct
/ some_distinct / all_distinct); composition verbatim
(the embedded list equals a direct P-187 list_document
call; each pack measured ONLY through its own layer's
verified parse road - parse_pack x3, parse_share for
the preset bundle - under P-188's locator law and
imported size bound); the identity law (two occurrences
are the same value iff exactly equal - no folding, no
normalisation; the empty string counts; dict keys are
never values; content_sha256 subtrees never walked);
the distinct axes (per-row distinct / repeated / extra
copies / shared; estate distinct / repeated / shared /
extra copies; the by-kind pooled distinct axis; the
largest distinct holder); the occurrence agreement
(each row's string_value_count equals P-193's on the
same estate, while no character axis appears anywhere);
the sub-pack overlap heart (two P-195-unique packs
sharing values are stated as sharing; one pack twice
shares every value); the no-silent-omission law (every
entry parsed or named by its row outcome under P-193's
imported OUTCOMES law, coverage_complete as data,
count = parsed + unavailable + invalid; shared counts
over parsed entries only); the no-content law (no
payload value and no digest of one anywhere in the
document); the distinctness fence (no P-189, P-193
char, P-194, P-195, P-196, P-197 or P-198 axis among
this census's own fields); the pure-read law (registry
and pack bytes unchanged); owner scoping (unit and
HTTP); the HTTP road (200 owner, 401 without a bearer);
and the neighbours (migration head stays 0041; the
outcomes law and the bound are the banked modules' own
objects). No network: fixtures only.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import browse as hub_browse
from runmal.hub import census as hub_census
from runmal.hub import content_census as hub_cc
from runmal.hub import distinct_census as hub_dc
from runmal.hub import duplicate_census as hub_dup
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
    record = store.create("owner-p199", body, now=STAMP)
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


def _expected_values(entry, raw):
    """Independent test-side measure: the owning layer's
    own parse road, then a plain recursive string walk
    skipping content_sha256 subtrees. Returns the raw
    value list (the test may hold values; the census
    document never does)."""
    if entry.kind == "lorebook_pack":
        payload = lorebook_packs.parse_pack(raw)["lorebook"]
    elif entry.kind == "prompt_pack":
        payload = prompt_packs.parse_pack(raw)["items"]
    elif entry.kind == "scenario_pack":
        payload = scenario_packs.parse_pack(raw)["scenario"]
    else:
        payload, _report = preset_bundles.parse_share(
            json.loads(raw.decode("utf-8")))
    values = []
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
            values.append(node)
    return values


def _expected_estate(entries):
    """Per-entry value lists plus the estate-wide
    distinct / repeated / shared expectations, computed
    from the raw values alone."""
    per_entry = []
    for entry in entries:
        raw = open(entry.locator, "rb").read()
        per_entry.append(_expected_values(entry, raw))
    distinct_sets = [set(values) for values in per_entry]
    estate_distinct = set().union(*distinct_sets) if distinct_sets else set()
    shared = {v for v in estate_distinct
              if sum(1 for s in distinct_sets if v in s) >= 2}
    occurrences = [len(values) for values in per_entry]
    estate_occurrences = sum(occurrences)
    repeated = {v for v in estate_distinct
                if sum(values.count(v) for values in per_entry) >= 2}
    return per_entry, {
        "total_string_values": estate_occurrences,
        "total_distinct_values": len(estate_distinct),
        "total_repeated_values": len(repeated),
        "total_shared_values": len(shared),
        "total_extra_copies": estate_occurrences - len(estate_distinct),
    }


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
    doc = hub_dc.distinct_census_document([])
    assert doc["schema"] == "runmal-p199-hub-distinct-content-census-v1"
    assert doc["census_state"] == "no_entries"
    assert doc["census_state"] in hub_dc.DISTINCT_CENSUS_STATES
    assert doc["count"] == 0
    assert doc["entries"] == []
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 0, "unavailable": 0}
    assert doc["by_kind_distinct"] == {
        kind: {"entries": 0, "parsed": 0, "string_values": 0,
               "distinct_values": 0, "extra_copies": 0}
        for kind in hub.KIND_FORMATS}
    assert doc["total_string_values"] == 0
    assert doc["total_distinct_values"] == 0
    assert doc["total_repeated_values"] == 0
    assert doc["total_shared_values"] == 0
    assert doc["total_extra_copies"] == 0
    assert doc["largest_distinct_entry"] is None
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS
    assert doc["max_browse_bytes"] == hub_dc.MAX_BROWSE_BYTES


def test_full_estate_all_distinct_and_measured_verbatim(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    per_entry, expected = _expected_estate(entries)
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_distinct"
    assert doc["count"] == 4
    assert doc["parsed_count"] == 4
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document(entries)
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 4, "unavailable": 0}
    distinct_sets = [set(values) for values in per_entry]
    for row, entry, values in zip(
            doc["entries"], entries, per_entry, strict=True):
        assert row["id"] == entry.id
        assert row["outcome"] == "parsed"
        assert row["error"] == ""
        assert row["string_value_count"] == len(values)
        assert row["distinct_value_count"] == len(set(values))
        assert row["repeated_value_count"] == sum(
            1 for v in set(values) if values.count(v) >= 2)
        assert row["extra_copy_count"] == (
            len(values) - len(set(values)))
        assert row["shared_value_count"] == sum(
            1 for v in set(values)
            if sum(1 for s in distinct_sets if v in s) >= 2)
        assert row["verified_content_sha256"] == entry.content_sha256
        axis = doc["by_kind_distinct"][entry.kind]
        assert axis["entries"] == 1 and axis["parsed"] == 1
        assert axis["string_values"] == len(values)
        assert axis["distinct_values"] == len(set(values))
        assert axis["extra_copies"] == len(values) - len(set(values))
    for field, want in expected.items():
        assert doc[field] == want, field
    assert doc["total_shared_values"] <= doc["total_repeated_values"]
    kind_axes = doc["by_kind_distinct"].values()
    assert sum(a["string_values"] for a in kind_axes) == \
        doc["total_string_values"]
    largest = doc["largest_distinct_entry"]
    assert largest["distinct_value_count"] == max(
        row["distinct_value_count"] for row in doc["entries"])
    assert largest["id"] in {row["id"] for row in doc["entries"]}


def test_verified_checksums_are_the_parse_roads_own(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    doc = hub_dc.distinct_census_document(entries)
    for row, entry in zip(doc["entries"], entries, strict=True):
        assert row["verified_content_sha256"] == entry.content_sha256
        assert row["verified_content_sha256"] != ""


# ------------------------------------------------------------ the identity law


def test_identity_law_hand_pinned():
    payload = {
        "content_sha256": "z" * 64,
        "nested": {"content_sha256": {"deep": "hidden"},
                   "keep": "yes"},
        "items": ["one", "one", "One", "one ", "", "", 7, True, None],
        "number": 42,
        "yes": "structure only",
    }
    total, counts = hub_dc._distinct_stats(payload)
    walked = list(hub_dc._string_values(payload))
    # Keys are never values ("yes" as a KEY contributes
    # nothing; its value "structure only" does), the
    # content_sha256 subtrees are never walked, and
    # non-strings never occur.
    assert sorted(walked) == sorted([
        "yes", "one", "one", "One", "one ", "", "",
        "structure only"])
    assert total == 8
    assert len(counts) == 6  # one / One / "one " / "" / yes / structure only
    assert counts[hub_dc._digest("one")] == 2
    assert counts[hub_dc._digest("")] == 2
    assert counts[hub_dc._digest("One")] == 1
    assert hub_dc._digest("hidden") not in counts
    repeated = sum(1 for n in counts.values() if n >= 2)
    assert repeated == 2  # "one" and the empty string


# ------------------------------------------------- agreement + the overlap heart


def test_occurrence_agreement_with_p193_and_no_char_axis(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    estate = store.list_for_owner("u1")
    doc = hub_dc.distinct_census_document(estate)
    p193 = hub_cc.content_census_document(estate)
    # The stated expected agreement: the same occurrences
    # counted - P-193's per-row and total counts match
    # exactly, because both censuses walk the same law.
    assert doc["total_string_values"] == p193["total_string_values"]
    for row, prow in zip(doc["entries"], p193["entries"], strict=True):
        assert row["string_value_count"] == prow["string_value_count"]
    # And no character was ever counted here.
    blob = json.dumps(doc)
    assert "string_char" not in blob
    assert "total_string_chars" not in blob
    assert "largest_content_entry" not in doc
    assert "by_kind_content" not in doc


def test_sub_pack_overlap_shared_but_not_a_duplicate(tmp_path):
    store = make_store(tmp_path)
    entries_a = [
        _lore_entry("a1", "Dawn Entry", "Shared dawn text.", ["dawn"]),
        _lore_entry("a2", "A Only", "Only in A.", ["alpha"])]
    entries_b = [
        _lore_entry("b1", "Dawn Copy", "Shared dawn text.", ["dawn"]),
        _lore_entry("b2", "B Only", "Only in B.", ["beta"])]
    loc_a, pack_a = _lorebook_file(tmp_path, "a.json", entries_a)
    loc_b, pack_b = _lorebook_file(tmp_path, "b.json", entries_b)
    first = _register(store, "lorebook_pack", "Version A", loc_a,
                      pack_a["manifest"]["content_sha256"])
    second = _register(store, "lorebook_pack", "Version B", loc_b,
                       pack_b["manifest"]["content_sha256"])
    estate = store.list_for_owner("u1")
    _per_entry, expected = _expected_estate([first, second])
    doc = hub_dc.distinct_census_document(estate)
    assert doc["total_shared_values"] == expected["total_shared_values"]
    assert doc["total_shared_values"] > 0
    for row in doc["entries"]:
        assert row["shared_value_count"] == doc["total_shared_values"]
    # The same estate at P-195's whole-pack grain: the two
    # packs are simply unique - no duplicate group exists.
    dup = hub_dup.duplicate_census_document(estate)
    assert dup["census_state"] == "no_duplicates"
    assert dup["duplicate_group_count"] == 0
    assert dup["distinct_content_count"] == 2


def test_same_pack_twice_shares_every_distinct_value(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path, "orig.json")
    raw = open(locator, "rb").read()
    copy_path = tmp_path / "copy.json"
    copy_path.write_bytes(raw)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Original", locator, sha)
    _register(store, "lorebook_pack", "Copy", str(copy_path), sha)
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    rows = doc["entries"]
    assert rows[0]["distinct_value_count"] == rows[1]["distinct_value_count"]
    assert doc["total_distinct_values"] == rows[0]["distinct_value_count"]
    assert doc["total_shared_values"] == doc["total_distinct_values"]
    for row in rows:
        assert row["shared_value_count"] == row["distinct_value_count"]
    assert doc["total_string_values"] == 2 * rows[0]["string_value_count"]
    # The by-kind axis pools: the kind's distinct count is
    # the single pack's, not the sum of the rows'.
    axis = doc["by_kind_distinct"]["lorebook_pack"]
    assert axis["distinct_values"] == rows[0]["distinct_value_count"]
    assert axis["string_values"] == doc["total_string_values"]


# ------------------------------------------------------------ outcomes / honesty


def test_mixed_estate_is_some_distinct_with_named_outcomes(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Good", locator,
              pack["manifest"]["content_sha256"])
    _register(store, "prompt_pack", "Ghost", str(tmp_path / "ghost.json"))
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    _register(store, "scenario_pack", "Broken", str(bad))
    _register(store, "preset_bundle", "Dir", str(tmp_path))
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_distinct"
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
    assert rows["Ghost"]["distinct_value_count"] == 0
    assert rows["Ghost"]["shared_value_count"] == 0
    assert rows["Dir"]["outcome"] == "unavailable"
    assert rows["Dir"]["locator_state"] == "not_a_file"
    assert rows["Broken"]["outcome"] == "invalid"
    assert rows["Broken"]["error"] != ""
    assert rows["Broken"]["verified_content_sha256"] == ""
    # Shared counts are computed over parsed entries only:
    # with one parsed entry nothing can be shared.
    assert doc["total_shared_values"] == 0
    assert rows["Good"]["shared_value_count"] == 0
    assert doc["total_distinct_values"] == \
        rows["Good"]["distinct_value_count"]


def test_all_missing_estate_is_no_distinct(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Ghost", str(tmp_path / "g.json"))
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "no_distinct"
    assert doc["parsed_count"] == 0
    assert doc["total_string_values"] == 0
    assert doc["total_distinct_values"] == 0
    assert doc["largest_distinct_entry"] is None
    assert doc["coverage_complete"] is False


def test_bare_bundle_parsed_with_empty_verified_checksum(tmp_path):
    store = make_store(tmp_path)
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Bare", locator)
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "parsed"
    assert row["verified_content_sha256"] == ""
    assert row["string_value_count"] > 0
    assert row["distinct_value_count"] > 0
    assert doc["census_state"] == "all_distinct"


def test_wrong_kind_pack_is_invalid_with_road_refusal(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _prompt_file(tmp_path)
    _register(store, "lorebook_pack", "Wrong kind", locator)
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] != ""
    assert doc["census_state"] == "no_distinct"


def test_oversize_pack_is_invalid_under_the_imported_bound(
        tmp_path, monkeypatch):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Big", locator)
    monkeypatch.setattr(hub_dc, "MAX_BROWSE_BYTES", 8)
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] == "pack file too large to distinct-census"
    assert doc["max_browse_bytes"] == 8


def test_largest_distinct_entry_and_tie_keeps_store_order(tmp_path):
    store = make_store(tmp_path)
    small, _p1 = _lorebook_file(tmp_path, "small.json")
    big_entries = [
        _lore_entry("e7", "First Big", "Unique text seven.", ["seven"]),
        _lore_entry("e8", "Second Big", "Unique text eight.", ["eight"]),
        _lore_entry("e9", "Third Big", "Unique text nine.", ["nine"])]
    big, _p2 = _lorebook_file(tmp_path, "big.json", big_entries)
    _register(store, "lorebook_pack", "Small", small)
    _register(store, "lorebook_pack", "Big", big)
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    assert doc["largest_distinct_entry"]["title"] == "Big"
    store2 = make_store(tmp_path / "second")
    a, _pa = _lorebook_file(tmp_path, "a.json")
    raw = open(a, "rb").read()
    bpath = tmp_path / "b.json"
    bpath.write_bytes(raw)
    first = _register(store2, "lorebook_pack", "First", a)
    _register(store2, "lorebook_pack", "Second", str(bpath))
    doc2 = hub_dc.distinct_census_document(store2.list_for_owner("u1"))
    rows = doc2["entries"]
    assert rows[0]["distinct_value_count"] == rows[1]["distinct_value_count"]
    assert doc2["largest_distinct_entry"]["id"] == first.id


# ------------------------------------------------------------ distinctness fence


def test_distinctness_fence_against_banked_censuses(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    estate = store.list_for_owner("u1")
    doc = hub_dc.distinct_census_document(estate)
    own_blob = json.dumps(doc)
    for banned in ("by_browse_state", "by_checksum_match",
                   "browse_state", "checksum_match",
                   "string_char_count", "total_string_chars",
                   "by_kind_content", "largest_content_entry",
                   "matched_by", "duplicate_groups",
                   "duplicate_entry_count", "distinct_content_count",
                   "unidentified_entry_count", "node_count",
                   "key_count", "max_depth", "file_bytes",
                   "by_size_bucket", "widest", "breadth"):
        assert banned not in own_blob, banned
    for row in doc["entries"]:
        assert "error" in row and "outcome" in row
    # And the banked censuses carry no identity axis.
    p193 = hub_cc.content_census_document(estate)
    assert "distinct_value_count" not in json.dumps(p193)
    dup = hub_dup.duplicate_census_document(estate)
    assert "shared_value_count" not in json.dumps(dup)
    p189 = hub_census.census_document(estate)
    assert "total_distinct_values" not in json.dumps(p189)


def test_no_content_or_digest_anywhere_in_the_document(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "A pack", locator)
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    blob = json.dumps(doc)
    secret = "The Zephyr Quill writes storms."
    assert secret not in blob
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert digest not in blob
    assert '"excerpt":' not in blob
    assert '"payload":' not in blob


# ------------------------------------------------------------ pure read / scope


def test_census_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = {e.locator: open(e.locator, "rb").read()
                  for e in entries}
    hub_dc.distinct_census_document(store.list_for_owner("u1"))
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
    doc = hub_dc.distinct_census_document(store.list_for_owner("u1"))
    assert doc["count"] == 1
    assert doc["entries"][0]["title"] == "Mine"
    # The foreign copy must not make Mine's values "shared".
    assert doc["total_shared_values"] == 0


def test_http_road_owner_scoped_and_bearer_gated(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Mine",
        "locator": locator,
        "content_sha256": pack["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/distinct-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["schema"] == "runmal-p199-hub-distinct-content-census-v1"
    assert doc["count"] == 1
    assert doc["entries"][0]["outcome"] == "parsed"
    assert doc["entries"][0]["distinct_value_count"] > 0
    bare = TestClient(create_app(_factory))
    assert bare.get("/api/v1/hub/distinct-census").status_code == 401


def test_neighbours_migration_head_and_imported_laws(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == MIGRATIONS[-1][0] == "0041"
    assert hub_dc.MAX_BROWSE_BYTES == 16 * 1024 * 1024
    assert hub_dc.MAX_BROWSE_BYTES == hub_browse.MAX_BROWSE_BYTES
    assert hub_dc.OUTCOMES is hub_cc.OUTCOMES
    assert hub_dc.OUTCOME_PARSED == hub_cc.OUTCOME_PARSED
    assert hub_dc.DISTINCT_CENSUS_STATES == frozenset({
        "no_entries", "no_distinct", "some_distinct", "all_distinct"})
