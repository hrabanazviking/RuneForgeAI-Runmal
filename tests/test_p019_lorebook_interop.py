"""P-019 acceptance: lorebook file interop — ST world-info JSON in/out.

Shapes rest on P-005's authored corpus fixtures (shapes from public
documentation only) and P-002's census (ST-15–ST-27). Part III owns
the *behaviour* of the preserved fields; this slice pins that the
file layer drops nothing.
"""

import json
from pathlib import Path

import pytest

from runmal.lorebooks.interop import (
    LorebookParseError,
    export_native,
    export_worldinfo,
    export_worldinfo_bytes,
    parse_lorebook_file,
)
from runmal.lorebooks.transfer import parse_import

CORPUS = Path(__file__).parent / "fixtures" / "interop"


def read_json(name: str) -> dict:
    return json.loads((CORPUS / name).read_text(encoding="utf-8"))


# The 18 fields P-005 pinned as dropped by the DB-path importer
# (group/groupWeight were promoted to first-class fields by
# P-034; probability/useProbability by P-036). P-019 preserves
# all of them at file level: depth/role as first-class at-depth
# data, the other 16 verbatim in `extra`.
P005_DROPPED = {
    "automationId", "characterFilter", "decorators", "delayUntilRecursion",
    "depth", "displayIndex", "excludeRecursion", "groupOverride",
    "id", "ignoreBudget", "outletName", "preventRecursion",
    "role", "scanDepth", "selective",
    "triggers", "useGroupScoring", "vectorized",
}


def test_worldinfo_full_imports_whole() -> None:
    book = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    assert book.name == "Corpus Full-Feature World"
    assert book.source_format == "worldinfo"
    assert book.original_data == {"scan_depth": 4}
    assert [e.name for e in book.entries] == ["The Gale-Bell", "Harbour Law", "Sunken Tithe"]
    gale = book.entries[0]
    assert gale.uid == "0"
    assert gale.keys == ["gale-bell", "bell"] and gale.secondary_keys == ["weather"]
    assert gale.priority == 300 and gale.case_sensitive is True
    assert gale.whole_word is False  # P-005 fix carried
    assert (gale.sticky_prompts, gale.cooldown_prompts, gale.delay_prompts) == (3, 2, 1)


def test_p005_dropped_fields_are_preserved_as_data() -> None:
    book = parse_lorebook_file(read_json("lorebook_worldinfo_full.json"))
    gale = book.entries[0]
    assert gale.depth == 4 and gale.role == 0  # at-depth companions, first-class
    assert set(gale.extra) == P005_DROPPED - {"depth", "role"}
    assert gale.inclusion_group == "weather" and gale.group_weight == 75  # P-034 first-class
    assert "group" not in gale.extra and "groupWeight" not in gale.extra
    assert gale.probability == 80 and gale.use_probability is True  # P-036 first-class
    assert "probability" not in gale.extra and "useProbability" not in gale.extra
    harbour = book.entries[1]
    assert harbour.probability == 100 and harbour.use_probability is False
    assert gale.selective_logic == "not_all"
    assert gale.extra["characterFilter"]["names"][0].startswith("Sigríðr")
    assert gale.extra["scanDepth"] is None  # explicit null preserved, not dropped


def test_at_depth_position_code_maps_as_data() -> None:
    book = parse_lorebook_file(read_json("lorebook_worldinfo_full.json"))
    gale, harbour, tithe = book.entries
    # Code 4 is the at-depth code (P-005); the file layer now keeps
    # it as data instead of collapsing it. The DB-path importer
    # still collapses it — P-038 owns the behaviour change there.
    assert gale.position == "at_depth" and gale.position_code == 4
    assert harbour.position == "before_char" and harbour.position_code == 0
    assert tithe.position == "after_char" and tithe.position_code == 1
    _, db_entries = parse_import(read_json("lorebook_worldinfo_full.json"))
    assert db_entries[0]["position"] == "before_char"  # unchanged, deliberately


def test_worldinfo_round_trip_is_fixed_point() -> None:
    book = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    once = export_worldinfo_bytes(book)
    twice = export_worldinfo_bytes(parse_lorebook_file(once))
    assert once == twice
    assert parse_lorebook_file(once) == book
    out = json.loads(once)
    assert out["originalData"] == {"scan_depth": 4}
    assert out["entries"]["0"]["selectiveLogic"] == 1
    assert out["entries"]["0"]["position"] == 4


def test_export_never_fabricates_at_depth_fields() -> None:
    out = export_worldinfo(parse_lorebook_file(read_json("lorebook_worldinfo_full.json")))
    assert out["entries"]["0"]["depth"] == 4 and out["entries"]["0"]["role"] == 0
    for uid in ("1", "2"):
        assert "depth" not in out["entries"][uid]
        assert "role" not in out["entries"][uid]


def test_unknown_fields_survive_round_trip() -> None:
    data = read_json("lorebook_worldinfo_full.json")
    data["x_future_book_field"] = {"nested": [1, "two", None]}
    data["entries"]["1"]["x_future_entry_field"] = [True, {"k": "v"}]
    out = export_worldinfo(parse_lorebook_file(data))
    assert out["x_future_book_field"] == {"nested": [1, "two", None]}
    assert out["entries"]["1"]["x_future_entry_field"] == [True, {"k": "v"}]


def test_worldinfo_nulls_import_with_defaults() -> None:
    book = parse_lorebook_file(read_json("lorebook_worldinfo_nulls.json"))
    first, second = book.entries
    assert first.priority == 100 and first.position_code is None
    assert first.secondary_keys == [] and first.sticky_prompts == 0
    assert second.priority == 150 and second.sticky_prompts == 2  # strings coerced


def test_unattested_position_code_preserved_verbatim() -> None:
    data = {
        "name": "Future Positions",
        "entries": {"0": {"comment": "Odd", "content": "x", "key": ["odd"], "position": 7}},
    }
    book = parse_lorebook_file(data)
    entry = book.entries[0]
    assert entry.position_code == 7 and entry.position == "before_char"  # no semantics claimed
    assert export_worldinfo(book)["entries"]["0"]["position"] == 7


def test_list_shaped_worldinfo_entries_import() -> None:
    data = {
        "name": "List Shape",
        "entries": [{"comment": "One", "content": "c", "key": ["a"], "order": 5}],
    }
    book = parse_lorebook_file(data)
    assert book.entries[0].name == "One" and book.entries[0].priority == 5
    assert book.entries[0].uid is None
    out = export_worldinfo(book)
    assert out["entries"]["0"]["comment"] == "One"


def test_native_rich_round_trip() -> None:
    book = parse_lorebook_file(read_json("lorebook_native_rich.json"))
    assert book.source_format == "native"
    assert book.scan_depth == 5 and book.token_budget == 800
    ferry = book.entries[0]
    assert ferry.position == "at_depth" and ferry.position_code == 4
    again = parse_lorebook_file(export_native(book))
    assert again == book
    assert export_native(book)["entries"][0]["sticky_prompts"] == 3


def test_native_to_worldinfo_conversion_is_stable() -> None:
    book = parse_lorebook_file(read_json("lorebook_native_rich.json"))
    world = export_worldinfo(book)
    assert world["entries"]["0"]["position"] == 4  # at_depth -> code 4
    assert world["entries"]["0"]["key"] == ["ferry"]
    assert world["entries"]["1"]["position"] == 0
    reparsed = parse_lorebook_file(world)
    assert export_worldinfo(reparsed) == world  # fixed point from conversion on


def test_bad_files_are_rejected() -> None:
    for bad in (b"{not json", b"[1, 2]", {"nope": 1}, {"entries": 42}):
        with pytest.raises(LorebookParseError):
            parse_lorebook_file(bad)
    with pytest.raises(LorebookParseError):  # native shape needs a name
        parse_lorebook_file({"format": "runmal-lorebook", "entries": []})


def test_export_endpoint_worldinfo_format(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from runmal.app import create_app
    from runmal.auth import get_or_create_credential
    from runmal.db.base import create_db_engine, create_session_factory
    from runmal.db.migrate import migrate_to_head

    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    client = TestClient(create_app(create_session_factory(create_db_engine(db_path))))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    fixtures = Path(__file__).parent / "fixtures" / "lorebooks"
    native = json.loads((fixtures / "native.json").read_text())
    book = client.post("/api/v1/lorebooks/import", json=native).json()
    default = client.get(f"/api/v1/lorebooks/{book['id']}/export")
    assert default.status_code == 200 and default.json()["format"] == "runmal-lorebook"
    world = client.get(f"/api/v1/lorebooks/{book['id']}/export?format=worldinfo")
    assert world.status_code == 200
    entries = world.json()["entries"]
    assert entries["0"]["comment"] == "Harbor" and entries["0"]["key"] == ["harbor", "port"]
    assert entries["1"]["position"] == 1  # after_char
    bad = client.get(f"/api/v1/lorebooks/{book['id']}/export?format=sideways")
    assert bad.status_code == 422
