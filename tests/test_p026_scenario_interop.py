"""P-026 acceptance: scenario interop - Voxta-shaped scenario files in/out.

Clean-room basis = P-003 census VX-28..VX-44 + VX-60 from public
documentation. Fixtures are authored inline in this module only -
never as new fixture files.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios import (
    MAX_SCENARIO_BYTES,
    ScenarioParseError,
    export_native,
    export_native_bytes,
    export_voxta,
    export_voxta_bytes,
    parse_scenario_file,
)

RICH = {
    "name": "Rich",
    "description": "Desc",
    "scenario": "Opening text",
    "chatFlow": "Story",
    "chatStyle": "Roleplay",
    "roles": [
        {"name": "Hero", "characterName": "Aria",
         "enabledOnStart": False, "canSpeak": True},
        {"role": "Guide", "character": "Borin"},
    ],
    "systemPrompt": {"text": "Be vivid", "mode": "replace"},
    "scenarioTemplate": "Tpl {{name}}",
    "bootstrapMessages": [
        {"type": "char", "text": "Hello", "role": "Hero"},
        {"kind": "note", "text": "Note text"},
    ],
    "impersonation": {"name": "Imp", "description": "Imp desc"},
    "narrator": {"name": "Narr", "voice": "deep"},
    "memoryBooks": ["Book One", {"name": "Book Two"}],
    "flags": ["started", "met_hero"],
    "variables": {"gold": 10, "mood": "calm"},
    "contexts": [
        {"key": "k1", "text": "Ctx text", "condition": "gold>5",
         "role": "Hero", "position": "before"},
        {"key": "k2", "content": "Ctx2"},
    ],
    "parent": "Parent Scenario",
    "thumbnail": "thumb.png",
    "scripts": [{"code": "x=1"}],
    "x_unknown": {"a": 1},
}

NATIVE = {
    "name": "Nat",
    "description": "Native desc",
    "scenario_text": "nt",
    "flow": "story",
    "style": "assistant",
    "template_text": "tt",
    "system_prompt_text": "sp",
    "system_prompt_mode": "extend",
    "roles": [
        {"name": "R", "character_name": "C",
         "enabled_on_start": False, "can_speak": False}
    ],
    "bootstrap_messages": [{"kind": "event", "text": "ev", "role": "R"}],
    "impersonation_name": "IN",
    "impersonation_description": "ID",
    "narrator_name": "NN",
    "narrator_voice": "NV",
    "memory_book_refs": ["MB"],
    "initial_flags": {"f": True},
    "initial_variables": {"v": 2},
    "contexts": [
        {"key": "k", "text": "ct", "condition": "c",
         "role": "R", "position": "p"}
    ],
    "parent_ref": "PR",
    "thumbnail_ref": "TR",
}

MAPPED_ALL = [
    "name", "description", "scenario_text", "flow", "style",
    "template_text", "system_prompt_text", "roles",
    "bootstrap_messages", "impersonation", "narrator",
    "memory_book_refs", "initial_flags", "initial_variables",
    "contexts", "parent_ref", "thumbnail_ref",
]


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def rich() -> dict:
    return copy.deepcopy(RICH)


# --- 1. Voxta full-file parse -------------------------------------------


def test_voxta_full_file_parse() -> None:
    p = parse_scenario_file(rich())
    assert p.source_format == "voxta"
    assert p.name == "Rich"
    assert p.description == "Desc"
    assert p.scenario_text == "Opening text"
    assert p.flow == "story"
    assert p.style == "roleplay"
    assert p.template_text == "Tpl {{name}}"
    assert p.system_prompt_text == "Be vivid"
    assert p.system_prompt_mode == "replace"
    assert len(p.roles) == 2
    hero, guide = p.roles
    assert hero.name == "Hero"
    assert hero.character_name == "Aria"
    assert hero.enabled_on_start is False
    assert hero.can_speak is True
    # role / character spellings, with defaults for omitted booleans
    assert guide.name == "Guide"
    assert guide.character_name == "Borin"
    assert guide.enabled_on_start is True
    assert guide.can_speak is True
    assert len(p.bootstrap_messages) == 2
    first, second = p.bootstrap_messages
    assert (first.kind, first.text, first.role) == ("char", "Hello", "Hero")
    assert (second.kind, second.text, second.role) == ("note", "Note text", "")
    assert p.impersonation_name == "Imp"
    assert p.impersonation_description == "Imp desc"
    assert p.narrator_name == "Narr"
    assert p.narrator_voice == "deep"
    assert p.memory_book_refs == ["Book One", "Book Two"]
    assert p.initial_flags == {"started": True, "met_hero": True}
    assert p.initial_variables == {"gold": 10, "mood": "calm"}
    assert len(p.contexts) == 2
    ctx, ctx2 = p.contexts
    assert (ctx.key, ctx.text, ctx.condition, ctx.role, ctx.position) == (
        "k1", "Ctx text", "gold>5", "Hero", "before")
    assert (ctx2.key, ctx2.text) == ("k2", "Ctx2")
    assert p.parent_ref == "Parent Scenario"
    assert p.thumbnail_ref == "thumb.png"
    assert p.report is not None
    assert p.report.source_format == "voxta"
    assert p.report.mapped == MAPPED_ALL
    assert p.report.to_dict()["source_format"] == "voxta"
    assert p.report.to_dict()["mapped"] == MAPPED_ALL
    assert p.report.warnings == []


def test_voxta_system_prompt_string_form() -> None:
    p = parse_scenario_file({"name": "S", "systemPrompt": "plain prompt"})
    assert p.system_prompt_text == "plain prompt"
    assert p.system_prompt_mode == ""
    assert "system_prompt_text" in p.report.mapped


def test_voxta_role_explicit_can_speak_false() -> None:
    p = parse_scenario_file({"name": "S", "roles": [
        {"name": "Mute", "enabledOnStart": True, "canSpeak": False}]})
    assert p.roles[0].enabled_on_start is True
    assert p.roles[0].can_speak is False


def test_voxta_impersonation_and_narrator_string_forms() -> None:
    p = parse_scenario_file(
        {"name": "S", "impersonation": "ImpStr", "narrator": "NarrStr"})
    assert p.impersonation_name == "ImpStr"
    assert p.impersonation_description == ""
    assert p.narrator_name == "NarrStr"
    assert p.narrator_voice == ""


def test_voxta_flags_dict_form() -> None:
    p = parse_scenario_file(
        {"name": "S", "flags": {"a": False, "b": True}})
    assert p.initial_flags == {"a": False, "b": True}


def test_voxta_parent_dict_form() -> None:
    p = parse_scenario_file({"name": "S", "parent": {"id": "pid"}})
    assert p.parent_ref == "pid"


# --- 2. Alias spellings ---------------------------------------------------


def test_alias_scenario_text() -> None:
    p = parse_scenario_file({"name": "A", "scenarioText": "alt text"})
    assert p.scenario_text == "alt text"
    assert p.source_format == "voxta"


def test_alias_flow_and_style() -> None:
    p = parse_scenario_file({"name": "A", "flow": "Story"})
    assert p.flow == "story"
    p = parse_scenario_file({"name": "A", "style": "Companion"})
    assert p.style == "companion"


def test_alias_template() -> None:
    p = parse_scenario_file({"name": "A", "template": "Tmpl"})
    assert p.template_text == "Tmpl"


def test_alias_bootstrap() -> None:
    p = parse_scenario_file(
        {"name": "A", "bootstrap": [{"kind": "user", "text": "hi"}]})
    assert len(p.bootstrap_messages) == 1
    assert p.bootstrap_messages[0].kind == "user"
    assert p.bootstrap_messages[0].text == "hi"


def test_alias_memory_books_spellings() -> None:
    p = parse_scenario_file({"name": "A", "memory_books": ["B1"]})
    assert p.memory_book_refs == ["B1"]
    p = parse_scenario_file(
        {"name": "A", "books": ["B2", {"name": "B3"}]})
    assert p.memory_book_refs == ["B2", "B3"]
    p = parse_scenario_file({"name": "A", "memoryBooks": "Solo"})
    assert p.memory_book_refs == ["Solo"]


def test_alias_initial_flags_and_variables() -> None:
    p = parse_scenario_file({"name": "A", "initialFlags": {"f": True}})
    assert p.initial_flags == {"f": True}
    p = parse_scenario_file({"name": "A", "initialFlags": ["x"]})
    assert p.initial_flags == {"x": True}
    p = parse_scenario_file(
        {"name": "A", "initialVariables": {"v": 1}})
    assert p.initial_variables == {"v": 1}


def test_alias_parent_scenario() -> None:
    p = parse_scenario_file({"name": "A", "parentScenario": "Par"})
    assert p.parent_ref == "Par"


# --- 3. Warnings ------------------------------------------------------------


def test_unknown_flow_warns_and_falls_back_to_chat() -> None:
    p = parse_scenario_file({"name": "W", "chatFlow": "Weird"})
    assert p.flow == "chat"
    assert any("unknown flow" in w and "weird" in w
               for w in p.report.warnings)


def test_unknown_style_warns_and_drops() -> None:
    p = parse_scenario_file({"name": "W", "chatStyle": "Weird"})
    assert p.style == ""
    assert any("unknown style" in w for w in p.report.warnings)


def test_unknown_system_prompt_mode_warns_and_drops() -> None:
    p = parse_scenario_file(
        {"name": "W", "systemPrompt": {"text": "t", "mode": "bogus"}})
    assert p.system_prompt_text == "t"
    assert p.system_prompt_mode == ""
    assert any("unknown system prompt mode" in w
               for w in p.report.warnings)


def test_bootstrap_block_form_warns_not_declared_and_splits() -> None:
    p = parse_scenario_file(
        {"name": "W", "bootstrapMessages": "line one\n\nline two\n"})
    hits = [w for w in p.report.warnings if "not declared" in w]
    assert len(hits) == 1
    assert [m.text for m in p.bootstrap_messages] == [
        "line one", "line two"]
    assert all(m.kind == "message" for m in p.bootstrap_messages)


@pytest.mark.parametrize("key", ["kind", "type"])
def test_unknown_bootstrap_kind_warns_and_maps_message(key) -> None:
    entry = {key: "alien", "text": "hi"}
    p = parse_scenario_file({"name": "W", "bootstrapMessages": [entry]})
    assert p.bootstrap_messages[0].kind == "message"
    assert p.bootstrap_messages[0].text == "hi"
    assert any("alien" in w for w in p.report.warnings)


# --- 4. Unmappable ----------------------------------------------------------

UNMAPPABLE = [
    ("scripts", "scripting"),
    ("events", "event"),
    ("actions", "action"),
    ("tools", "tool"),
    ("buttons", "button"),
    ("controls", "control"),
    ("apps", "app_config"),
    ("assets", "asset_bytes"),
]


@pytest.mark.parametrize("key,kind", UNMAPPABLE)
def test_unmappable_keys_reported_and_carried(key, kind) -> None:
    value = [{"opaque": [1, 2, {"deep": True}]}]
    p = parse_scenario_file({"name": "U", key: copy.deepcopy(value)})
    assert p.report.has_unmappable
    entries = p.report.to_dict()["unmappable"]
    assert len(entries) == 1
    assert entries[0]["path"] == key
    assert entries[0]["kind"] == kind
    assert entries[0]["name"] == key
    assert p.unmappable_values[key] == value
    assert key not in p.extra


def test_unknown_top_level_goes_to_extra_not_unmappable() -> None:
    p = parse_scenario_file(
        {"name": "U", "x_future": {"nested": [1, 2]}})
    assert p.extra == {"x_future": {"nested": [1, 2]}}
    assert p.report.unmappable == []
    assert p.report.carried == ["x_future"]
    assert "x_future" not in p.unmappable_values


def test_unmappable_reemitted_verbatim_by_export_voxta() -> None:
    data = {"name": "U"}
    for key, _kind in UNMAPPABLE:
        data[key] = [{"for": key}, 42]
    data["x_future"] = "kept"
    out = export_voxta(parse_scenario_file(copy.deepcopy(data)))
    for key, _kind in UNMAPPABLE:
        assert out[key] == data[key], key
    assert out["x_future"] == "kept"


# --- 5. Round trips ---------------------------------------------------------


def test_voxta_round_trip_fixed_point() -> None:
    once = export_voxta(parse_scenario_file(rich()))
    twice = export_voxta(parse_scenario_file(copy.deepcopy(once)))
    assert once == twice


def test_native_round_trip_from_voxta_fixed_point() -> None:
    once = export_native(parse_scenario_file(rich()))
    assert once["source_format"] == "native"
    reparsed = parse_scenario_file(copy.deepcopy(once))
    assert reparsed.source_format == "native"
    assert export_native(reparsed) == once


def test_native_file_with_snake_case_keys_parses() -> None:
    p = parse_scenario_file(copy.deepcopy(NATIVE))
    assert p.source_format == "native"
    assert p.report.source_format == "native"
    assert p.name == "Nat"
    assert p.description == "Native desc"
    assert p.scenario_text == "nt"
    assert p.flow == "story"
    assert p.style == "assistant"
    assert p.template_text == "tt"
    assert p.system_prompt_text == "sp"
    assert p.system_prompt_mode == "extend"
    assert p.roles[0].name == "R"
    assert p.roles[0].character_name == "C"
    assert p.roles[0].enabled_on_start is False
    assert p.roles[0].can_speak is False
    assert p.bootstrap_messages[0].kind == "event"
    assert p.bootstrap_messages[0].text == "ev"
    assert p.impersonation_name == "IN"
    assert p.impersonation_description == "ID"
    assert p.narrator_name == "NN"
    assert p.narrator_voice == "NV"
    assert p.memory_book_refs == ["MB"]
    assert p.initial_flags == {"f": True}
    assert p.initial_variables == {"v": 2}
    assert p.contexts[0].text == "ct"
    assert p.parent_ref == "PR"
    assert p.thumbnail_ref == "TR"
    assert p.report.mapped == MAPPED_ALL


def test_native_detected_by_source_format_marker() -> None:
    p = parse_scenario_file(
        {"name": "Marked", "source_format": "native",
         "scenario_text": "x"})
    assert p.source_format == "native"


def test_export_native_clean_shape() -> None:
    out = export_native(parse_scenario_file(rich()))
    assert out["source_format"] == "native"
    for banned in ("raw", "report", "unmappable_values", "extra"):
        assert banned not in out, banned
    assert out["name"] == "Rich"
    assert out["scenario_text"] == "Opening text"


def test_export_voxta_of_native_has_no_source_format() -> None:
    out = export_voxta(parse_scenario_file(copy.deepcopy(NATIVE)))
    assert "source_format" not in out
    assert out["name"] == "Nat"


# --- 6. Bytes variants ------------------------------------------------------


def test_bytes_exports_decode_to_dict_exports() -> None:
    p = parse_scenario_file(rich())
    voxta_bytes = export_voxta_bytes(p)
    native_bytes = export_native_bytes(p)
    assert isinstance(voxta_bytes, bytes)
    assert isinstance(native_bytes, bytes)
    assert json.loads(voxta_bytes.decode("utf-8")) == export_voxta(p)
    assert json.loads(native_bytes.decode("utf-8")) == export_native(p)


def test_parse_accepts_bytes_and_str_json() -> None:
    text = json.dumps(RICH)
    from_bytes = parse_scenario_file(text.encode("utf-8"))
    from_str = parse_scenario_file(text)
    from_dict = parse_scenario_file(rich())
    assert from_bytes.name == "Rich"
    assert from_str.name == "Rich"
    assert export_native(from_bytes) == export_native(from_dict)
    assert export_native(from_str) == export_native(from_dict)


# --- 7. Refusals --------------------------------------------------------------

BAD_INPUTS = [
    ("non-json-string", "this is not json {"),
    ("non-json-bytes", b"{not json"),
    ("json-array-string", "[1, 2]"),
    ("json-array-bytes", b"[1, 2]"),
    ("missing-name", {"description": "x"}),
    ("blank-name", {"name": "  "}),
    ("roles-not-a-list", {"name": "X", "roles": {"a": 1}}),
    ("role-entry-not-object", {"name": "X", "roles": ["Hero"]}),
    ("variables-not-object", {"name": "X", "variables": [1]}),
    ("contexts-not-a-list", {"name": "X", "contexts": {"a": 1}}),
    ("contexts-entry-not-object", {"name": "X", "contexts": ["x"]}),
    ("bootstrap-entry-not-object",
     {"name": "X", "bootstrapMessages": ["hi"]}),
    ("flags-wrong-type", {"name": "X", "flags": "started"}),
    ("oversize-bytes", b"x" * (MAX_SCENARIO_BYTES + 1)),
]


@pytest.mark.parametrize(
    "payload", [p for _label, p in BAD_INPUTS],
    ids=[label for label, _p in BAD_INPUTS],
)
def test_parse_refusals_are_typed(payload) -> None:
    with pytest.raises(ScenarioParseError):
        parse_scenario_file(payload)


def test_parse_error_is_a_value_error() -> None:
    assert issubclass(ScenarioParseError, ValueError)


# --- 8. API -------------------------------------------------------------------


def test_api_import_voxta(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/scenarios/import", json=rich())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_format"] == "voxta"
    assert body["scenario"]["name"] == "Rich"
    assert body["scenario"]["source_format"] == "native"
    assert body["scenario"]["scenario_text"] == "Opening text"
    unmappable = body["report"]["unmappable"]
    assert len(unmappable) == 1
    assert unmappable[0]["path"] == "scripts"
    assert unmappable[0]["kind"] == "scripting"
    assert "name" in body["report"]["mapped"]


def test_api_export_native_and_voxta(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    native = client.post(
        "/api/v1/scenarios/export", json=rich(),
        params={"format": "native"})
    assert native.status_code == 200, native.text
    assert native.json()["source_format"] == "native"
    assert native.json()["name"] == "Rich"
    voxta = client.post(
        "/api/v1/scenarios/export", json=rich(),
        params={"format": "voxta"})
    assert voxta.status_code == 200, voxta.text
    assert voxta.json()["name"] == "Rich"
    assert voxta.json()["chatFlow"] == "Story"
    assert "source_format" not in voxta.json()


def test_api_export_bogus_format_is_422(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/scenarios/export", json=rich(),
        params={"format": "bogus"})
    assert resp.status_code == 422, resp.text


def test_api_import_missing_name_is_422(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/scenarios/import", json={"no_name": True})
    assert resp.status_code == 422, resp.text


def test_api_requires_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    anon = TestClient(client.app)
    resp = anon.post("/api/v1/scenarios/import", json=rich())
    assert resp.status_code == 401, resp.text
    resp = anon.post(
        "/api/v1/scenarios/export", json=rich(),
        params={"format": "native"})
    assert resp.status_code == 401, resp.text


# --- 9. Migration head unchanged ----------------------------------------------


def test_head_revision_is_0029_p037() -> None:
    assert MIGRATIONS[-1][0] == "0036"  # head moved by P-065 (PROVISIONAL 0036)
def test_head_revision_is_0028_p036() -> None:
    assert MIGRATIONS[-1][0] == "0036"  # head moved by P-065 (PROVISIONAL 0036)


def test_migrated_temp_db_head_is_0029_p037(tmp_path) -> None:
    db_path = tmp_path / "migrated.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0036"


def test_head_revision_is_0030_p038() -> None:
    assert MIGRATIONS[-1][0] == "0036"  # head moved by P-065 (PROVISIONAL 0036)


def test_migrated_temp_db_head_is_0030_p038(tmp_path) -> None:
    db_path = tmp_path / "migrated.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0036"
    assert current_revision(db_path) == "0036"
    assert current_revision(db_path) == MIGRATIONS[-1][0]
