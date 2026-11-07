"""P-061 acceptance: grammar/JSON-mode as a prompt citizen.

Roadmap line: *Grammar/JSON-mode where backends offer it, as a
prompt citizen (structured replies for bridges/games).*

Honesty contract pinned here (the design's six clauses):
1. unsupported says unsupported, with a warning -- greyed truth
   rows with reason codes, planner degradation WITH its warning,
   loud InvalidRequest from an adapter handed an unplanned mode;
2. validation is labelled validation, never enforcement;
3. no post-hoc parsing presented as enforcement, and no silent
   subset -- out-of-subset schema keywords are not_validatable;
4. no schema / grammar content in any trace, echo, or debug
   payload (S214) -- metadata and presence booleans only;
5. grammar greyed everywhere is a recorded finding, with its
   reason on every row;
6. no row claims measured; truth is per-BACKEND with declared /
   ledger provenance only. Migration: NONE, head stays 0036 (P-065).
"""

from __future__ import annotations

import asyncio
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends import (
    MODES,
    StructuredOutput,
    audit_structured_truth,
    plan_structured,
    structured_from_data,
    structured_matrix,
    structured_to_data,
    truth_for_backend,
    truth_for_model,
    validate_reply,
    wire_payload,
)
from runmal.backends.aesir import AesirChatBackend
from runmal.backends.capabilities import default_model
from runmal.backends.errors import InvalidRequest
from runmal.backends.events import Done, TextDelta
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.models import ModelInfo
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openai_compat import OpenAICompatibleChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.params import SamplingParams
from runmal.backends.profiles import CHAT_BACKENDS
from runmal.backends.retry import RetryPolicy, stream_with_retry
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.generation.service import generate_events
from runmal.presets.bundles import (
    BundleError,
    build_share,
    merge_bundle,
    parse_share,
    validate_bundle,
    validate_overrides,
)
from runmal.prompt.service import resolve_structured, structured_echo

MSGS = [ChatMessage("user", "hi")]
SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name"],
}
CANARY_SCHEMA = "ZqxCanarySchema61"
CANARY_GRAMMAR = "ZqxCanaryGrammar61"

JS = StructuredOutput(mode="json_schema", schema=copy.deepcopy(SCHEMA))
JO = StructuredOutput(mode="json_object")
GR = StructuredOutput(mode="grammar", grammar='root ::= "x"')


def model(backend_key: str) -> ModelInfo:
    return default_model(backend_key)


# ---------------- data validation ----------------

@pytest.mark.parametrize("data", [
    {"mode": "off"},
    {"mode": "json_object"},
    {"mode": "json_schema", "schema": SCHEMA},
    {"mode": "json_schema", "schema": SCHEMA, "name": "r", "strict": True},
    {"mode": "grammar", "grammar": 'root ::= "x"'},
])
def test_mode_round_trips_fixed_point(data):
    parsed = structured_from_data(copy.deepcopy(data))
    out = structured_to_data(parsed)
    assert structured_from_data(copy.deepcopy(out)) == parsed
    assert structured_to_data(structured_from_data(copy.deepcopy(out))) == out


def test_default_is_off_inactive():
    assert StructuredOutput().mode == "off"
    assert StructuredOutput().is_active() is False
    assert structured_from_data({"mode": "off"}).is_active() is False
    assert JO.is_active() and JS.is_active() and GR.is_active()


def test_to_data_deep_copy_isolation():
    out = structured_to_data(JS)
    out["schema"]["properties"]["name"]["type"] = "number"
    assert JS.schema["properties"]["name"]["type"] == "string"
    assert structured_to_data(JS)["schema"] == SCHEMA


@pytest.mark.parametrize("data", [
    {"mode": "off", "bogus": 1},                      # unknown key
    {"mode": "yaml"},                                  # unknown mode
    {"schema": SCHEMA},                                # mode missing
    {"mode": "off", "schema": None},                   # field present as None
    {"mode": "off", "name": "x"},                      # field for wrong mode
    {"mode": "json_object", "strict": False},          # present, wrong mode
    {"mode": "json_object", "grammar": "g"},
    {"mode": "json_schema"},                           # schema missing
    {"mode": "json_schema", "schema": "nope"},         # non-dict schema
    {"mode": "json_schema", "schema": SCHEMA, "grammar": "g"},
    {"mode": "json_schema", "schema": SCHEMA, "strict": 1},   # non-bool strict
    {"mode": "json_schema", "schema": SCHEMA, "strict": "true"},
    {"mode": "json_schema", "schema": SCHEMA, "name": ""},    # empty name
    {"mode": "grammar"},                               # grammar missing
    {"mode": "grammar", "grammar": ""},                # empty grammar
    {"mode": "grammar", "grammar": "   "},             # blank grammar
    {"mode": "grammar", "grammar": "g", "schema": {}},
    "not-a-dict",
    42,
    None,
])
def test_malformed_declarations_raise(data):
    with pytest.raises(ValueError):
        structured_from_data(data)


def test_non_serialisable_schema_raises():
    with pytest.raises(ValueError):
        structured_from_data(
            {"mode": "json_schema", "schema": {"x": object()}})


def test_direct_construction_validates():
    with pytest.raises(ValueError):
        StructuredOutput(mode="json_schema")  # no schema
    with pytest.raises(ValueError):
        StructuredOutput(mode="grammar", grammar="")


# ---------------- truth ----------------

EXPECTED = {
    # backend: mode -> (state, reason_code, source, wire_field)
    "openai": {
        "off": ("available", "supported", "declared", None),
        "json_object": ("available", "supported", "declared", "response_format"),
        "json_schema": ("available", "supported", "declared", "response_format"),
        "grammar": ("greyed", "grammar_not_on_wire", "declared", None),
    },
    "openrouter": {
        "off": ("available", "supported", "declared", None),
        "json_object": ("available", "supported", "declared", "response_format"),
        "json_schema": ("available", "supported", "declared", "response_format"),
        "grammar": ("greyed", "grammar_not_on_wire", "declared", None),
    },
    "ollama": {
        "off": ("available", "supported", "declared", None),
        "json_object": ("available", "supported", "declared", "format"),
        "json_schema": ("available", "supported", "declared", "format"),
        "grammar": ("greyed", "grammar_not_on_wire", "declared", None),
    },
    "aesir": {
        "off": ("available", "supported", "declared", None),
        "json_object": ("greyed", "route_not_served", "ledger", None),
        "json_schema": ("greyed", "route_not_served", "ledger", None),
        "grammar": ("greyed", "grammar_not_on_wire", "ledger", None),
    },
    "fake": {
        "off": ("available", "supported", "declared", None),
        "json_object": ("greyed", "not_declared", "declared", None),
        "json_schema": ("greyed", "not_declared", "declared", None),
        "grammar": ("greyed", "grammar_not_on_wire", "declared", None),
    },
}


@pytest.mark.parametrize("backend_key", sorted(EXPECTED))
def test_truth_rows_pinned(backend_key):
    rows = truth_for_model(model(backend_key))
    assert [r.mode for r in rows] == list(MODES)
    for row in rows:
        state, code, source, wire = EXPECTED[backend_key][row.mode]
        assert (row.state, row.reason_code, row.source, row.wire_field) == (
            state, code, source, wire)
        assert row.supported is (state == "available")
        assert row.backend_key == backend_key
        assert row.model_id == model(backend_key).model_id
        if row.supported:
            assert row.reason == ""
        else:
            assert row.reason  # a human sentence rides every greyed row


def test_fake_json_rows_name_scripted_text():
    for row in truth_for_model(model("fake")):
        if row.mode in ("json_object", "json_schema"):
            assert "scripted" in row.reason


def test_truth_unknown_backend_raises():
    with pytest.raises(ValueError):
        truth_for_model(ModelInfo("m", "M", "nope"))
    with pytest.raises(ValueError):
        truth_for_backend("nope")


def test_matrix_shape_and_registry_order():
    matrix = structured_matrix()
    assert [b["backend_key"] for b in matrix["backends"]] == list(CHAT_BACKENDS)
    assert matrix["audit"] == []
    for entry in matrix["backends"]:
        assert [m["mode"] for m in entry["modes"]] == list(MODES)
        assert entry["available"] == [
            m["mode"] for m in entry["modes"] if m["state"] == "available"]
        assert entry["greyed"] == [
            m["mode"] for m in entry["modes"] if m["state"] == "greyed"]


# ---------------- wire builders ----------------

def test_wire_payloads_exact():
    assert wire_payload("openai", JO) == {"response_format": {"type": "json_object"}}
    assert wire_payload("openrouter", JO) == {
        "response_format": {"type": "json_object"}}
    assert wire_payload("openai", JS) == {
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": SCHEMA, "strict": False},
        }
    }
    assert wire_payload("ollama", JO) == {"format": "json"}
    assert wire_payload("ollama", JS) == {"format": SCHEMA}


def test_wire_payload_deep_copy_isolation():
    payload = wire_payload("ollama", JS)
    payload["format"]["properties"]["name"]["type"] = "number"
    assert JS.schema["properties"]["name"]["type"] == "string"


@pytest.mark.parametrize("backend_key", sorted(EXPECTED))
def test_wire_off_is_empty_everywhere(backend_key):
    assert wire_payload(backend_key, None) == {}
    assert wire_payload(backend_key, StructuredOutput()) == {}


@pytest.mark.parametrize("backend_key,structured", [
    ("openai", GR), ("openrouter", GR), ("ollama", GR),
    ("aesir", JO), ("aesir", JS), ("aesir", GR),
    ("fake", JO), ("fake", JS), ("fake", GR),
])
def test_wire_unserved_raises(backend_key, structured):
    with pytest.raises(ValueError):
        wire_payload(backend_key, structured)


def test_wire_unknown_backend_raises():
    with pytest.raises(ValueError):
        wire_payload("nope", JO)


# ---------------- adapters (captured payload) ----------------

def openai_backend(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        sse = (
            'data: {"choices":[{"delta":{"content":"hi"},'
            '"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        )
        return httpx.Response(200, content=sse.encode(),
                              headers={"Content-Type": "text/event-stream"})

    return OpenAICompatibleChatBackend(
        api_key="k", transport=httpx.MockTransport(handler))


def openrouter_backend(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        sse = (
            'data: {"choices":[{"delta":{"content":"hi"},'
            '"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        )
        return httpx.Response(200, content=sse.encode(),
                              headers={"Content-Type": "text/event-stream"})

    return OpenRouterChatBackend(
        api_key="k", transport=httpx.MockTransport(handler))


def ollama_backend(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        ndjson = (
            '{"message":{"content":"hi"},"done":false}\n'
            '{"message":{"content":""},"done":true,"done_reason":"stop",'
            '"prompt_eval_count":1,"eval_count":1}\n'
        )
        return httpx.Response(200, content=ndjson.encode())

    return OllamaChatBackend(transport=httpx.MockTransport(handler))


def aesir_backend(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        sse = (
            'data: {"choices":[{"delta":{"content":"hi"},'
            '"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        )
        return httpx.Response(200, content=sse.encode(),
                              headers={"Content-Type": "text/event-stream"})

    return AesirChatBackend(transport=httpx.MockTransport(handler))


async def _collect(backend, structured=None):
    stream = backend.chat_stream(
        MSGS, SamplingParams(), asyncio.Event(), structured=structured)
    return [event async for event in stream]


async def test_openai_payload_carries_response_format():
    seen: dict = {}
    events = await _collect(openai_backend(seen), structured=JS)
    assert seen["payload"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": SCHEMA, "strict": False},
    }
    assert any(isinstance(e, Done) for e in events)


async def test_openrouter_payload_carries_response_format():
    seen: dict = {}
    await _collect(openrouter_backend(seen), structured=JO)
    assert seen["payload"]["response_format"] == {"type": "json_object"}


async def test_ollama_format_top_level_never_in_options():
    seen: dict = {}
    await _collect(ollama_backend(seen), structured=JS)
    assert seen["payload"]["format"] == SCHEMA
    assert "format" not in seen["payload"]["options"]
    seen2: dict = {}
    await _collect(ollama_backend(seen2), structured=JO)
    assert seen2["payload"]["format"] == "json"


async def test_payloads_byte_identical_without_structured():
    seen_a: dict = {}
    await _collect(openai_backend(seen_a))
    seen_b: dict = {}
    await _collect(openai_backend(seen_b), structured=StructuredOutput())
    assert seen_a["payload"] == seen_b["payload"]
    assert "response_format" not in seen_a["payload"]
    seen_c: dict = {}
    await _collect(ollama_backend(seen_c))
    assert "format" not in seen_c["payload"]


async def test_aesir_and_fake_refuse_active_structured():
    for backend in (aesir_backend({}), FakeChatBackend()):
        with pytest.raises(InvalidRequest) as excinfo:
            await _collect(backend, structured=JO)
        assert excinfo.value.code == "invalid_request"
        assert excinfo.value.retryable is False


async def test_aesir_and_fake_stream_normally_when_off():
    events = await _collect(aesir_backend({}), structured=StructuredOutput())
    assert any(isinstance(e, TextDelta) for e in events)
    events = await _collect(FakeChatBackend(), structured=None)
    assert any(isinstance(e, Done) for e in events)


async def test_retry_passthrough_delivers_structured():
    seen: dict = {}
    backend = openai_backend(seen)

    async def _sleep(_delay):
        return None

    events = [
        event async for event in stream_with_retry(
            backend, MSGS, SamplingParams(), asyncio.Event(),
            request_id="req-61", policy=RetryPolicy(max_attempts=1),
            sleep=_sleep, structured=JO)
    ]
    assert any(isinstance(e, Done) for e in events)
    assert seen["payload"]["response_format"] == {"type": "json_object"}


async def test_retry_unserved_structured_refusal_propagates():
    async def _sleep(_delay):
        return None

    with pytest.raises(InvalidRequest):
        _ = [
            event async for event in stream_with_retry(
                FakeChatBackend(), MSGS, SamplingParams(), asyncio.Event(),
                request_id="req-61b", policy=RetryPolicy(max_attempts=1),
                sleep=_sleep, fallback=FakeChatBackend(), structured=JO)
        ]


async def test_generate_events_passthrough():
    seen: dict = {}
    out = [
        d async for d in generate_events(
            "req-61c", messages=MSGS, backend=openai_backend(seen),
            structured=JO)
    ]
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert out[-1] == {"type": "done", "finish_reason": "stop"}


async def test_generate_events_fake_active_structured_is_loud_error():
    out = [
        d async for d in generate_events(
            "req-61d", messages=MSGS, backend=FakeChatBackend(),
            structured=JO)
    ]
    assert out[0]["type"] == "error"
    assert out[0]["code"] == "invalid_request"
    assert out[0]["retryable"] is False
    assert out[-1] == {"type": "done", "finish_reason": "error"}


# ---------------- planner ----------------

def test_planner_served_passes_through():
    planned, warnings = plan_structured(JS, model("openai"))
    assert planned is JS and warnings == []
    planned, warnings = plan_structured(JO, model("ollama"))
    assert planned is JO and warnings == []


def test_planner_none_and_off():
    assert plan_structured(None, model("openai")) == (None, [])
    assert plan_structured(StructuredOutput(), model("fake")) == (None, [])


@pytest.mark.parametrize("structured,backend_key,code", [
    (GR, "openai", "grammar_not_on_wire"),
    (JS, "aesir", "route_not_served"),
    (JO, "fake", "not_declared"),
])
def test_planner_unserved_degrades_with_exact_warning(structured, backend_key, code):
    m = model(backend_key)
    planned, warnings = plan_structured(structured, m)
    assert planned is None
    assert warnings == [
        f"structured_output dropped: mode {structured.mode!r} is not "
        f"served by backend {backend_key!r} for model {m.model_id!r} ({code})"
    ]


# ---------------- validation companion ----------------

def test_validate_json_object():
    ok = validate_reply('{"a": 1}', JO)
    assert ok.status == "ok" and ok.parsed == {"a": 1} and ok.errors == ()
    bad = validate_reply('[1, 2]', JO)
    assert bad.status == "invalid" and "not a JSON object" in bad.errors[0]


def test_validate_malformed_json_no_repair():
    bad = validate_reply('{"a": 1,}', JO)
    assert bad.status == "invalid"
    assert "line" in bad.errors[0] and "column" in bad.errors[0]
    fenced = validate_reply('```json\n{"a": 1}\n```', JO)
    assert fenced.status == "invalid"  # fences are NOT stripped


def test_validate_schema_subset_ok_and_paths():
    good = validate_reply('{"name": "Ada", "age": 36}', JS)
    assert good.status == "ok"
    bad = validate_reply('{"name": "Ada", "age": "old"}', JS)
    assert bad.status == "invalid"
    assert "$.age: expected integer" in bad.errors
    missing = validate_reply('{"age": 3}', JS)
    assert missing.status == "invalid"
    assert any("$.name" in e and "required" in e for e in missing.errors)


def test_validate_nested_path_and_items_and_enum():
    schema = StructuredOutput(mode="json_schema", schema={
        "type": "object",
        "properties": {
            "user": {"type": "object",
                     "properties": {"age": {"type": "integer"}},
                     "required": ["age"]},
            "tags": {"type": "array", "items": {"type": "string"}},
            "kind": {"enum": ["a", "b"]},
        },
    })
    bad = validate_reply(
        '{"user": {"age": "x"}, "tags": ["ok", 3], "kind": "z"}', schema)
    assert bad.status == "invalid"
    assert "$.user.age: expected integer" in bad.errors
    assert "$.tags[1]: expected string" in bad.errors
    assert "$.kind: value not in enum" in bad.errors


def test_validate_bool_is_never_a_number():
    schema = StructuredOutput(
        mode="json_schema", schema={"type": "integer"})
    assert validate_reply("true", schema).status == "invalid"
    assert validate_reply("7", schema).status == "ok"


def test_validate_out_of_subset_keyword_not_validatable():
    schema = StructuredOutput(mode="json_schema", schema={
        "type": "object",
        "properties": {"age": {"type": "integer", "minimum": 0}},
    })
    result = validate_reply('{"age": 3}', schema)
    assert result.status == "not_validatable"
    assert "minimum" in result.errors[0]


def test_validate_annotations_are_ignored():
    schema = StructuredOutput(mode="json_schema", schema={
        "$schema": "https://example.invalid/schema",
        "title": "T", "description": "D", "type": "object",
    })
    assert validate_reply('{"a": 1}', schema).status == "ok"


def test_validate_grammar_and_off_not_validatable():
    assert validate_reply("anything", GR).status == "not_validatable"
    assert validate_reply('{"a": 1}', None).status == "not_validatable"
    assert validate_reply('{"a": 1}', StructuredOutput()).status == (
        "not_validatable")


# ---------------- prompt citizen ----------------

def test_resolve_structured():
    structured, source = resolve_structured({"mode": "json_object"})
    assert source == "explicit" and structured == JO
    structured, source = resolve_structured({"mode": "off"})
    assert source == "explicit" and structured is not None
    assert structured.is_active() is False  # explicit off != absence
    assert resolve_structured(None) == (None, "default")
    with pytest.raises(ValueError):
        resolve_structured({"mode": "bogus"})


def test_echo_metadata_and_no_content():
    echo = structured_echo(JS, "explicit", backend_key="openai",
                           model_id="gpt-4o-mini")
    assert echo["declared"] == {
        "mode": "json_schema", "name": "response", "strict": False,
        "schema_present": True, "grammar_present": False,
    }
    assert echo["source"] == "explicit"
    assert echo["warnings"] == []
    assert [r["mode"] for r in echo["truth"]] == list(MODES)
    default = structured_echo(None, "default")
    assert default["declared"] == {
        "mode": "off", "name": None, "strict": False,
        "schema_present": False, "grammar_present": False,
    }
    assert default["truth"] == structured_matrix()["backends"]


def test_echo_planner_warning_against_in_play_backend():
    echo = structured_echo(GR, "explicit", backend_key="openai")
    assert len(echo["warnings"]) == 1
    assert "grammar_not_on_wire" in echo["warnings"][0]


# ---------------- inspector + router ----------------

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_inspect_always_carries_structured_output(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/debug/prompt-inspect", json={"messages": ["hi"]})
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert "structured_output" in result
    assert result["structured_output"]["declared"]["mode"] == "off"
    assert result["structured_output"]["source"] == "default"


def test_inspect_canary_schema_and_grammar_never_leak(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    schema = {"type": "object", "properties": {
        "x": {"type": "string", "description": CANARY_SCHEMA}}}
    resp = client.post("/api/v1/debug/prompt-inspect", json={
        "messages": ["hi"], "backend_key": "openai",
        "structured_output": {"mode": "json_schema", "schema": schema},
    })
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["structured_output"]["declared"]["schema_present"] is True
    assert CANARY_SCHEMA not in json.dumps(result)
    resp = client.post("/api/v1/debug/prompt-inspect", json={
        "messages": ["hi"],
        "structured_output": {
            "mode": "grammar", "grammar": f"{CANARY_GRAMMAR} ::= \"x\""},
    })
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["structured_output"]["declared"]["grammar_present"] is True
    assert CANARY_GRAMMAR not in json.dumps(result)


@pytest.mark.parametrize("route", ["/api/v1/debug/prompt-inspect",
                                   "/api/v1/debug/prompt-preview"])
def test_router_422_on_malformed_declaration(tmp_path, monkeypatch, route):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(route, json={
        "messages": ["hi"], "structured_output": {"mode": "bogus"}})
    assert resp.status_code == 422, resp.text


def test_debug_structured_modes_endpoint(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/debug/structured-modes")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [m["mode"] for m in body["modes"]] == list(MODES)
    fields = {m["mode"]: m["fields"] for m in body["modes"]}
    assert fields["json_schema"] == ["schema", "name", "strict"]
    assert fields["grammar"] == ["grammar"]
    assert [b["backend_key"] for b in body["backends"]] == list(CHAT_BACKENDS)
    assert body["audit"] == []


# ---------------- preset bundles ----------------

def _bundle(**kw):
    base = {"name": "B61", "sampler": {"temperature": 0.5}}
    base.update(kw)
    return base


def test_bundle_section_round_trip_and_fixed_point():
    data = {"mode": "json_schema", "schema": SCHEMA, "name": "r",
            "strict": True}
    out = validate_bundle(_bundle(structured_output=copy.deepcopy(data)))
    assert out["structured_output"] == data
    assert validate_bundle(out) == out  # fixed point extends to the section
    out2 = validate_bundle(_bundle())
    assert out2["structured_output"] is None


def test_bundle_malformed_section_refuses():
    with pytest.raises(BundleError):
        validate_bundle(_bundle(structured_output={"mode": "bogus"}))


def test_bundle_unknown_key_still_extension():
    out = validate_bundle(_bundle(foreign_future_field={"x": 1}))
    assert out["extensions"]["foreign_future_field"] == {"x": 1}
    assert "structured_output" not in out["extensions"]


def test_override_validates_and_null_clears_in_merge():
    data = {"mode": "json_object"}
    assert validate_overrides({"structured_output": data}) == {
        "structured_output": data}
    with pytest.raises(BundleError):
        validate_overrides({"structured_output": {"mode": "bogus"}})
    base = validate_bundle(_bundle(structured_output={"mode": "json_object"}))
    effective, sources = merge_bundle(base, {"structured_output": None})
    assert effective["structured_output"] is None
    assert sources["structured_output"] == "delta1"


def test_merge_replaces_wholesale_and_share_carries():
    base = validate_bundle(_bundle(structured_output={"mode": "json_object"}))
    delta = validate_overrides({"structured_output": {
        "mode": "json_schema", "schema": SCHEMA}})
    effective, sources = merge_bundle(base, delta)
    assert effective["structured_output"] == {
        "mode": "json_schema", "schema": SCHEMA,
        "name": "response", "strict": False}
    assert sources["structured_output"] == "delta1"
    share = build_share(effective)
    assert share["bundle"]["structured_output"] == effective["structured_output"]
    parsed, report = parse_share(share)
    assert parsed["structured_output"] == effective["structured_output"]
    assert report["checksum_verified"] is True


# ---------------- audit + flags + migration ----------------

def test_audit_clean():
    assert audit_structured_truth() == []


@pytest.mark.parametrize("backend_key,flag", [
    ("openai", True), ("openrouter", True), ("ollama", True),
    ("aesir", False), ("fake", False),
])
def test_capability_flag_pins(backend_key, flag):
    assert default_model(backend_key).capabilities.structured_output is flag


def test_migration_head_stays_0036(tmp_path):
    assert MIGRATIONS[-1][0] == "0039"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0039"
