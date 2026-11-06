"""P-021 acceptance: preset interop — ST-shaped preset files in/out.

Shapes rest on P-002's census (ST-34, official public docs) and
P-005's authored corpus fixtures. Extra presets are authored
inline in this module only — never as new fixture files (the
corpus manifest test fails on unlisted files).
"""

from __future__ import annotations

import copy
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.presets.interop import (
    PresetFileView,
    PresetParseError,
    export_preset,
    parse_preset,
)
from runmal.presets.service import validate_params

CORPUS = Path(__file__).parent / "fixtures" / "interop"
UPGRADES = Path(__file__).parent / "fixtures" / "upgrades"
TEXT_NAME = "preset_st_textcompletion.json"
CHAT_NAME = "preset_st_chatcompletion.json"

TEXT_BAG = {
    "temperature": 0.9,
    "top_p": 0.92,
    "top_k": 40,
    "min_p": 0.05,
    "repetition_penalty": 1.08,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "max_tokens": 350,
    "context_length": 8192,
}
CHAT_BAG = {
    "temperature": 0.85,
    "top_p": 0.95,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "max_tokens": 900,
    "context_length": 128000,
}
CHAT_ORDER_IDS = [
    "main",
    "worldInfoBefore",
    "personaDescription",
    "charDescription",
    "scenario",
    "dialogueExamples",
    "chatHistory",
    "jailbreak",
]
MAIN_CONTENT = (
    "You are an expert actor that can fully immerse yourself "
    "into any role given."
)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def load_fixture(name: str) -> dict:
    return json.loads((CORPUS / name).read_text(encoding="utf-8"))


def fixture_bytes(name: str) -> bytes:
    return (CORPUS / name).read_bytes()


def _export(view, format=None) -> bytes:
    """Export a parsed preset, tolerating a distinct file-view type."""
    try:
        return export_preset(view, format=format)
    except (TypeError, AttributeError):
        file_view = PresetFileView(
            name=view.name,
            params=dict(view.params),
            template_ref=view.template_ref,
            source_format=view.source_format,
            raw=copy.deepcopy(view.raw),
            prompts=copy.deepcopy(view.prompts),
            prompt_order=copy.deepcopy(view.prompt_order),
        )
        return export_preset(file_view, format=format)


def _order_ids(order) -> list:
    return [e["identifier"] if isinstance(e, dict) else e for e in order]


# --- corpus imports (unit) ----------------------------------------------


def test_corpus_text_import_exact_bag() -> None:
    parsed = parse_preset(fixture_bytes(TEXT_NAME))
    assert parsed.name == "Corpus Community Preset"
    assert parsed.source_format == "st-text"
    assert parsed.params == TEXT_BAG
    assert parsed.template_ref == ""
    assert parsed.prompts == [] and parsed.prompt_order == []
    # the promoted bag is canonical: it passes S207 validation as-is
    assert validate_params(parsed.params) == TEXT_BAG


def test_corpus_text_carriage_in_raw_not_bag() -> None:
    parsed = parse_preset(fixture_bytes(TEXT_NAME))
    raw = parsed.raw
    assert raw["tfs"] == 0.95 and raw["dry_base"] == 1.75
    assert raw["dry_multiplier"] == 0 and raw["xtc_threshold"] == 0.1
    assert raw["dynatemp_exponent"] == 1 and raw["seed"] == -1
    for key in ("tfs", "dry_base", "dry_multiplier", "xtc_threshold",
                "dynatemp_exponent", "temp", "rep_pen", "genamt"):
        assert key not in parsed.params, key


def test_corpus_chat_import_exact_bag_and_prompts() -> None:
    parsed = parse_preset(fixture_bytes(CHAT_NAME))
    assert parsed.name == "Imported preset"
    assert parsed.source_format == "st-chat"
    assert parsed.params == CHAT_BAG
    assert validate_params(parsed.params) == CHAT_BAG
    assert len(parsed.prompts) == 3
    main = parsed.prompts[0]
    assert main["identifier"] == "main"
    assert main["content"] == MAIN_CONTENT
    assert main["role"] == "system"
    assert [p["identifier"] for p in parsed.prompts] == [
        "main", "worldInfoBefore", "jailbreak",
    ]
    assert _order_ids(parsed.prompt_order) == CHAT_ORDER_IDS
    char_entry = next(
        e for e in parsed.prompt_order
        if (e["identifier"] if isinstance(e, dict) else e) == "charDescription"
    )
    assert isinstance(char_entry, dict) and char_entry["enabled"] is False


def test_corpus_chat_carriage_in_raw_not_bag() -> None:
    parsed = parse_preset(fixture_bytes(CHAT_NAME))
    assert parsed.raw["logit_bias"] == {}
    assert parsed.raw["model"] == "corpus-model"
    assert parsed.raw["chat_completion_source"] == "openai"
    for key in ("logit_bias", "model", "chat_completion_source",
                "openai_max_tokens", "openai_max_context"):
        assert key not in parsed.params, key


def test_name_chain() -> None:
    by_name = parse_preset({"name": "By Name", "temp": 0.5})
    assert by_name.name == "By Name"
    by_preset = parse_preset({"preset": "By Preset", "temp": 0.5})
    assert by_preset.name == "By Preset"
    both = parse_preset({"name": "Wins", "preset": "Loses", "temp": 0.5})
    assert both.name == "Wins"
    nameless = parse_preset({"temp": 0.5})
    assert nameless.name == "Imported preset"


# --- fixed points + unknown survival -------------------------------------


@pytest.mark.parametrize("fixture", [TEXT_NAME, CHAT_NAME])
def test_export_parse_is_fixed_point(fixture) -> None:
    parsed = parse_preset(fixture_bytes(fixture))
    once = _export(parsed)
    reparsed = parse_preset(once)
    assert reparsed.name == parsed.name
    assert reparsed.params == parsed.params
    assert reparsed.template_ref == parsed.template_ref
    assert reparsed.source_format == parsed.source_format
    assert reparsed.prompts == parsed.prompts
    assert reparsed.prompt_order == parsed.prompt_order
    assert reparsed.raw == parsed.raw
    twice = _export(reparsed)
    assert once == twice  # second export byte-identical


FUTURE_FIELDS = {
    "x_future_string": "must-survive",
    "x_future_number": 42.5,
    "x_future_int": 7,
    "x_future_bool": True,
    "x_future_null": None,
    "x_future_array": ["a", 1, None, {"k": "v"}],
    "x_future_object": {"nested": {"list": [True, False, {"deep": [1, 2]}]}},
}


@pytest.mark.parametrize("fixture", [TEXT_NAME, CHAT_NAME])
def test_unknown_fields_survive_same_shape_round_trip(fixture) -> None:
    data = load_fixture(fixture)
    data.update(copy.deepcopy(FUTURE_FIELDS))
    parsed = parse_preset(data)
    for key, value in FUTURE_FIELDS.items():
        assert parsed.raw[key] == value, key
        assert key not in parsed.params, key
    out = json.loads(_export(parsed))
    for key, value in FUTURE_FIELDS.items():
        assert out[key] == value, key


# --- sentinels + coercion -------------------------------------------------


def test_seed_minus_one_is_unset_and_restored_on_export() -> None:
    parsed = parse_preset(fixture_bytes(TEXT_NAME))
    assert "seed" not in parsed.params
    out = json.loads(_export(parsed))
    assert out["seed"] == -1


def test_seed_minus_two_rejected() -> None:
    with pytest.raises(PresetParseError):
        parse_preset({"preset": "S", "temp": 0.5, "seed": -2})


def test_numeric_strings_and_integral_floats_coerce() -> None:
    parsed = parse_preset(
        {"preset": "S", "temp": "0.7", "top_p": "0.9", "top_k": 40.0}
    )
    assert parsed.params["temperature"] == 0.7
    assert parsed.params["top_p"] == 0.9
    assert parsed.params["top_k"] == 40
    assert isinstance(parsed.params["top_k"], int)


def test_null_mapped_field_is_omitted() -> None:
    parsed = parse_preset({"preset": "S", "temp": 0.5, "top_p": None})
    assert parsed.params == {"temperature": 0.5}


def test_bool_for_temperature_rejected() -> None:
    with pytest.raises(PresetParseError):
        parse_preset({"preset": "S", "temp": True})


def test_promoted_canonical_ranges_enforced() -> None:
    with pytest.raises(PresetParseError):
        parse_preset({"preset": "S", "temp": 0.5, "min_p": 1.5})
    with pytest.raises(PresetParseError):
        parse_preset({"preset": "S", "temp": 0.5, "context_length": 0})
    ok = parse_preset({"preset": "S", "temp": 0.5, "min_p": 0, "context_length": 1})
    assert ok.params["min_p"] == 0 and ok.params["context_length"] == 1


# --- duplicate spellings ---------------------------------------------------


def test_canonical_spelling_wins_over_openai_duplicate() -> None:
    data = load_fixture(CHAT_NAME)
    data["max_tokens"] = 500
    data["openai_max_tokens"] = 900
    parsed = parse_preset(data)
    assert parsed.params["max_tokens"] == 500


def test_max_context_length_alone_maps_nothing() -> None:
    parsed = parse_preset(
        {"preset": "S", "temp": 0.5, "max_context_length": 4096}
    )
    assert "context_length" not in parsed.params
    assert parsed.raw["max_context_length"] == 4096


# --- parse errors -----------------------------------------------------------


BAD_INPUTS = [
    ("non-utf8", b"\xff\xfe\x00bad"),
    ("malformed-json", b"{not json"),
    ("json-list", b"[1, 2]"),
    ("empty-object", {}),
    ("unrecognized-flat", {"hello": "world", "count": 3}),
    (
        "invalid-prompt-role",
        {"temperature": 0.8,
         "prompts": [{"identifier": "x", "role": "narrator",
                      "content": "hi"}]},
    ),
    (
        "prompts-not-a-list",
        {"temperature": 0.8, "prompts": {"identifier": "x"}},
    ),
    (
        "prompt-without-identifier",
        {"temperature": 0.8, "prompts": [{"content": "hi"}]},
    ),
    (
        "non-bool-enabled",
        {"temperature": 0.8,
         "prompt_order": [{"identifier": "main", "enabled": "yes"}]},
    ),
    ("oversize", b"x" * (8 * 1024 * 1024 + 1)),
]


@pytest.mark.parametrize(
    "payload", [p for _label, p in BAD_INPUTS],
    ids=[label for label, _p in BAD_INPUTS],
)
def test_parse_errors_are_typed(payload) -> None:
    with pytest.raises(PresetParseError):
        parse_preset(payload)


def test_parse_error_is_a_value_error() -> None:
    assert issubclass(PresetParseError, ValueError)


# --- native shape (unit) ----------------------------------------------------


def test_native_dict_shape_parses() -> None:
    parsed = parse_preset(
        {"name": "Native One",
         "params": {"temperature": 0.5, "min_p": 0.1},
         "template_ref": "chat-v1"}
    )
    assert parsed.name == "Native One"
    assert parsed.source_format == "native"
    assert parsed.params == {"temperature": 0.5, "min_p": 0.1}
    assert parsed.template_ref == "chat-v1"


# --- API: import + persistence ----------------------------------------------


def test_api_import_text_preset(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/presets/import", json=load_fixture(TEXT_NAME))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Corpus Community Preset"
    assert body["params"] == TEXT_BAG
    assert body["source_format"] == "st-text"
    assert body["prompts"] == [] and body["prompt_order"] == []
    listed = client.get("/api/v1/presets").json()
    assert [p["id"] for p in listed] == [body["id"]]
    assert listed[0]["source_format"] == "st-text"
    fetched = client.get(f"/api/v1/presets/{body['id']}").json()
    assert fetched["params"] == TEXT_BAG


def test_api_import_chat_preset(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/presets/import", json=load_fixture(CHAT_NAME),
        params={"name": "Chat Corpus"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Chat Corpus"
    assert body["params"] == CHAT_BAG
    assert body["source_format"] == "st-chat"
    assert len(body["prompts"]) == 3
    assert body["prompts"][0]["content"] == MAIN_CONTENT
    assert _order_ids(body["prompt_order"]) == CHAT_ORDER_IDS


def test_api_import_default_name_for_nameless_chat(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/presets/import", json=load_fixture(CHAT_NAME))
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Imported preset"


def test_api_reimport_same_name_conflicts(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    data = load_fixture(TEXT_NAME)
    assert client.post("/api/v1/presets/import", json=data).status_code == 201
    dup = client.post("/api/v1/presets/import", json=data)
    assert dup.status_code == 409, dup.text


def test_api_import_invalid_file_is_422(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/presets/import", json={"hello": "world"}
    )
    assert resp.status_code == 422, resp.text
    assert client.get("/api/v1/presets").json() == []


def test_api_import_and_export_require_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/presets/import", json=load_fixture(TEXT_NAME)
    ).json()
    anon = TestClient(client.app)
    resp = anon.post("/api/v1/presets/import", json=load_fixture(CHAT_NAME))
    assert resp.status_code in (401, 403)
    resp = anon.get(f"/api/v1/presets/{created['id']}/export")
    assert resp.status_code in (401, 403)


# --- API: export, native round trip, cross-shape ----------------------------


def test_api_export_defaults_to_source_shape(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    text = client.post(
        "/api/v1/presets/import", json=load_fixture(TEXT_NAME)
    ).json()
    out = client.get(f"/api/v1/presets/{text['id']}/export")
    assert out.status_code == 200, out.text
    assert parse_preset(out.content).source_format == "st-text"
    assert out.json()["temp"] == 0.9 and out.json()["genamt"] == 350
    chat = client.post(
        "/api/v1/presets/import", json=load_fixture(CHAT_NAME),
        params={"name": "chatty"},
    ).json()
    out = client.get(f"/api/v1/presets/{chat['id']}/export")
    assert out.status_code == 200
    assert parse_preset(out.content).source_format == "st-chat"
    assert "prompts" in out.json()


def test_api_export_unknown_id_and_format(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/presets/ghost/export").status_code == 404
    created = client.post(
        "/api/v1/presets/import", json=load_fixture(TEXT_NAME)
    ).json()
    resp = client.get(
        f"/api/v1/presets/{created['id']}/export",
        params={"format": "bogus"},
    )
    assert resp.status_code == 422, resp.text


def test_api_native_round_trip(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/presets",
        json={"name": "native-one",
              "params": {"temperature": 0.7, "seed": 7},
              "template_ref": "chat-v1"},
    )
    assert created.status_code == 201, created.text
    preset_id = created.json()["id"]
    assert created.json()["source_format"] == "native"
    out = client.get(
        f"/api/v1/presets/{preset_id}/export", params={"format": "native"}
    )
    assert out.status_code == 200
    parsed = parse_preset(out.content)
    assert parsed.name == "native-one"
    assert parsed.params == {"temperature": 0.7, "seed": 7}
    assert parsed.template_ref == "chat-v1"
    assert parsed.source_format == "native"
    again = client.post(
        "/api/v1/presets/import", json=out.json(),
        params={"name": "native-copy"},
    )
    assert again.status_code == 201, again.text
    assert again.json()["params"] == {"temperature": 0.7, "seed": 7}
    assert again.json()["template_ref"] == "chat-v1"
    assert again.json()["source_format"] == "native"


def test_api_st_import_native_export_keeps_carriage(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    imported = client.post(
        "/api/v1/presets/import", json=load_fixture(CHAT_NAME),
        params={"name": "carrier"},
    ).json()
    native = client.get(
        f"/api/v1/presets/{imported['id']}/export",
        params={"format": "native"},
    )
    assert native.status_code == 200
    parsed = parse_preset(native.content)
    assert parsed.source_format == "native"
    assert parsed.params == CHAT_BAG
    assert [p["identifier"] for p in parsed.prompts] == [
        "main", "worldInfoBefore", "jailbreak",
    ]
    assert _order_ids(parsed.prompt_order) == CHAT_ORDER_IDS
    reimported = client.post(
        "/api/v1/presets/import", json=native.json(),
        params={"name": "carrier-2"},
    )
    assert reimported.status_code == 201, reimported.text
    assert len(reimported.json()["prompts"]) == 3
    back = client.get(
        f"/api/v1/presets/{reimported.json()['id']}/export",
        params={"format": "st-chat"},
    )
    assert back.status_code == 200
    assert back.json()["logit_bias"] == {}
    assert back.json()["model"] == "corpus-model"
    assert back.json()["prompts"][0]["content"] == MAIN_CONTENT


def test_api_chat_origin_st_text_export(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    imported = client.post(
        "/api/v1/presets/import", json=load_fixture(CHAT_NAME),
        params={"name": "cross"},
    ).json()
    out = client.get(
        f"/api/v1/presets/{imported['id']}/export",
        params={"format": "st-text"},
    )
    assert out.status_code == 200, out.text
    file_obj = out.json()
    assert file_obj["temp"] == 0.85
    assert file_obj["genamt"] == 900
    assert file_obj["freq_pen"] == 0 and file_obj["presence_pen"] == 0
    assert file_obj["top_p"] == 0.95
    assert "prompts" not in file_obj and "prompt_order" not in file_obj
    # the stored preset itself still carries its prompts
    stored = client.get(f"/api/v1/presets/{imported['id']}").json()
    assert len(stored["prompts"]) == 3
    assert _order_ids(stored["prompt_order"]) == CHAT_ORDER_IDS


def test_api_text_origin_st_text_reverse_keys(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    imported = client.post(
        "/api/v1/presets/import", json=load_fixture(TEXT_NAME)
    ).json()
    out = client.get(f"/api/v1/presets/{imported['id']}/export")
    file_obj = out.json()
    assert file_obj["temp"] == 0.9 and file_obj["rep_pen"] == 1.08
    assert file_obj["genamt"] == 350 and file_obj["min_p"] == 0.05


def test_api_native_to_st_chat_emits_only_set_keys(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/presets",
        json={"name": "sparse", "params": {"temperature": 0.6}},
    ).json()
    out = client.get(
        f"/api/v1/presets/{created['id']}/export",
        params={"format": "st-chat"},
    )
    assert out.status_code == 200, out.text
    file_obj = out.json()
    assert file_obj["temperature"] == 0.6
    assert "top_p" not in file_obj and "seed" not in file_obj
    assert "prompts" not in file_obj and "prompt_order" not in file_obj


def test_api_patch_params_keeps_prompts_and_reexports(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    imported = client.post(
        "/api/v1/presets/import", json=load_fixture(CHAT_NAME),
        params={"name": "patchme"},
    ).json()
    new_bag = {
        "temperature": 0.5,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "max_tokens": 900,
        "context_length": 128000,
    }
    patched = client.patch(
        f"/api/v1/presets/{imported['id']}", json={"params": new_bag}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["params"] == new_bag
    assert len(patched.json()["prompts"]) == 3  # PATCH did not clear them
    assert _order_ids(patched.json()["prompt_order"]) == CHAT_ORDER_IDS
    out = client.get(f"/api/v1/presets/{imported['id']}/export")
    assert out.status_code == 200
    file_obj = out.json()
    assert file_obj["temperature"] == 0.5  # lowered value, same shape
    assert "top_p" not in file_obj  # removed key stays removed


# --- real against existing systems ------------------------------------------


def test_imported_preset_drives_generation_manifest(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    client.post(
        "/api/v1/connections",
        json={"name": "laptop", "backend": "ollama",
              "base_url": "http://localhost:11434", "model": "llama3.1"},
    )
    preset = client.post(
        "/api/v1/presets/import", json=load_fixture(TEXT_NAME)
    ).json()
    chat = client.post("/api/v1/chats", json={"title": "Ford"}).json()
    applied = client.post(
        f"/api/v1/chats/{chat['id']}/preset",
        json={"preset_id": preset["id"]},
    )
    assert applied.status_code == 200, applied.text
    manifest = client.get(
        f"/api/v1/chats/{chat['id']}/generation-manifest"
    ).json()
    assert manifest["backend"] == "ollama"
    assert manifest["preset"]["name"] == "Corpus Community Preset"
    assert manifest["params"]["temperature"] == 0.9
    assert manifest["params"]["num_predict"] == 350  # max_tokens mapped
    assert manifest["params"]["repeat_penalty"] == 1.08  # rep. mapped
    assert {(m["source"], m["dest"]) for m in manifest["mapped"]} == {
        ("max_tokens", "num_predict"),
        ("repetition_penalty", "repeat_penalty"),
    }
    dropped = [d["param"] for d in manifest["dropped"]]
    for param in ("frequency_penalty", "presence_penalty",
                  "min_p", "context_length"):
        assert param in dropped, param


def test_sampling_params_from_imported_bag() -> None:
    from runmal.backends.params import SamplingParams

    parsed = parse_preset(fixture_bytes(TEXT_NAME))
    params = SamplingParams.from_bag(parsed.params)
    assert params.temperature == 0.9 and params.top_p == 0.92
    assert params.min_p == 0.05 and params.context_length == 8192
    assert params.max_output_tokens == 350
    assert params.repetition_penalty == 1.08
    assert params.to_bag() == TEXT_BAG


def test_s208_ollama_filter_on_imported_bag() -> None:
    from runmal.generation.compat import filter_for_backend

    parsed = parse_preset(fixture_bytes(TEXT_NAME))
    result = filter_for_backend(parsed.params, "ollama")
    assert result.params["repeat_penalty"] == 1.08
    assert result.params["num_predict"] == 350
    assert result.params["temperature"] == 0.9
    dropped = [d.param for d in result.dropped]
    assert "min_p" in dropped and "context_length" in dropped


# --- migration (0019) + portable archive ------------------------------------


def test_head_revision_is_0030_p038() -> None:
    # Head pin: moved by P-038's provisional 0030 (0029 reserved for P-037).
    assert MIGRATIONS[-1][0] == "0030"


def test_0016_fixture_migrates_to_head_with_interop_defaults(
    tmp_path,
) -> None:
    work = tmp_path / "runmal-0016.db"
    shutil.copy2(UPGRADES / "runmal-0016.db", work)
    assert current_revision(work) == "0016"
    # The 0016 fixture's own presets table is empty, so a preset row
    # is first written with the pre-0019 schema — a genuinely
    # pre-existing row at migration time (the 0009 fixture's real
    # row is covered by the next test).
    conn = sqlite3.connect(work)
    user_id = conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO sampling_presets"
        " (id, user_id, name, params_json, template_ref, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("00000000-0000-4000-8000-0000000000aa", user_id, "legacy",
         '{"temperature": 0.4}', "", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()
    applied = migrate_to_head(work)
    assert "0019" in applied
    assert current_revision(work) == MIGRATIONS[-1][0]
    conn = sqlite3.connect(f"file:{work}?mode=ro", uri=True)
    try:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sampling_presets)")
        }
        assert {"source_format", "interop_json"} <= cols
        row = conn.execute(
            "SELECT source_format, interop_json FROM sampling_presets"
            " WHERE name = 'legacy'"
        ).fetchone()
        assert row == ("native", "{}")
    finally:
        conn.close()


async def test_0009_fixture_preset_row_reads_native_after_migration(
    tmp_path,
) -> None:
    from runmal.presets.service import list_presets, preset_to_dict

    work = tmp_path / "runmal-0009.db"
    shutil.copy2(UPGRADES / "runmal-0009.db", work)
    assert current_revision(work) == "0009"
    migrate_to_head(work)
    assert current_revision(work) == MIGRATIONS[-1][0]
    conn = sqlite3.connect(f"file:{work}?mode=ro", uri=True)
    user_id = conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
    conn.close()
    factory = create_session_factory(create_db_engine(work))
    async with factory() as session:
        presets = await list_presets(session, user_id)
    assert [p.name for p in presets] == ["calm"]
    view = preset_to_dict(presets[0])
    assert view["source_format"] == "native"
    assert view["params"] == {"temperature": 0.4}
    assert view["prompts"] == [] and view["prompt_order"] == []


async def test_portable_archive_includes_interop_columns(tmp_path) -> None:
    from runmal.db.models import SamplingPreset, User
    from runmal.portable.archive import export_archive

    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    carriage = json.dumps(
        {"raw": {"temp": 0.9}, "prompts": [], "prompt_order": []}
    )
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        user_id = user.id
        session.add(
            SamplingPreset(
                user_id=user_id,
                name="imported",
                params_json='{"temperature": 0.9}',
                source_format="st-text",
                interop_json=carriage,
            )
        )
        await session.commit()
        dest = tmp_path / "out.runmal"
        await export_archive(session, user_id, dest, base_dir=tmp_path)
    with zipfile.ZipFile(dest) as zf:
        names = [n for n in zf.namelist() if n.startswith("presets/")]
        assert len(names) == 1
        member = json.loads(zf.read(names[0]))
    assert member["source_format"] == "st-text"
    assert json.loads(member["interop_json"])["raw"] == {"temp": 0.9}
