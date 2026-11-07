"""P-051 Context templates battery (BUILDER-3).

Pins the context-template contract: registry/default identity,
context_from_data validation and fill-missing, apply semantics
(reorder, disable, literal wrapping, depth splice, idempotent
wrapping), story-string serialise/parse, preset import, plain
assembly, the resolve/echo service, and the inspector/API
surface (echo, trace discards, 422s, no prompt content leak,
registry endpoints). Authored clean-room for P-051.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.presets.interop import parse_preset
from runmal.prompt.composer import compose
from runmal.prompt.context import (
    CONTEXT_TEMPLATE_ORDER,
    DISABLED_REASON,
    IDENTIFIER_TO_ANCHOR,
    SEGMENT_KINDS,
    SEGMENT_ORDER,
    STORY_ALIASES,
    ContextSegment,
    ContextTemplate,
    apply_context_template,
    context_from_data,
    context_template_from_preset,
    context_to_data,
    default_context_template,
    from_story_string,
    get_context_template,
    list_context_templates,
    to_story_string,
)
from runmal.prompt.inspect import MAIN_SYSTEM_TEXT
from runmal.prompt.instruct import get_template as get_instruct_template
from runmal.prompt.render import render_prompt
from runmal.prompt.service import context_echo, resolve_context_template
from runmal.prompt.slots import BASELINE_ORDER, make_slot

FIXTURES = Path(__file__).parent / "fixtures" / "interop"
CHAT_FIXTURE = FIXTURES / "preset_st_chatcompletion.json"
TEXT_FIXTURE = FIXTURES / "preset_st_textcompletion.json"
CTX = dict(context_limit=4096, reserve_response=512)
EXPECTED_ORDER = (
    "system", "persona", "memory_nucleus", "world_before",
    "memory_retrieved", "examples", "history", "world_after",
    "authors_note", "post_history",
)


def all_kind_slots():
    slots = []
    for kind in BASELINE_ORDER:
        if kind == "history":
            slots.append(make_slot(kind, "user", "", id=f"s/{kind}",
                                   splittable=True, parts=("h1", "h2")))
        else:
            slots.append(make_slot(kind, "system", f"content-{kind}",
                                   id=f"s/{kind}"))
    return slots

# ---------------- 1. registry / default ----------------

def test_segment_order_and_registry():
    assert SEGMENT_ORDER == EXPECTED_ORDER
    assert CONTEXT_TEMPLATE_ORDER == ("default",)
    assert [t.name for t in list_context_templates()] == ["default"]
    assert SEGMENT_KINDS["system"] == ("main_system",)
    assert SEGMENT_KINDS["world_before"] == ("lore_before",)
    assert SEGMENT_KINDS["world_after"] == ("lore_after",)
    assert SEGMENT_KINDS["history"] == ("history",)
    assert SEGMENT_KINDS["post_history"] == ("post_history",)


def test_get_unknown_template_raises():
    with pytest.raises(ValueError):
        get_context_template("nope")


def test_default_template_all_enabled_in_order():
    template = default_context_template()
    assert template.name == "default"
    assert [s.anchor for s in template.segments] == list(SEGMENT_ORDER)
    assert all(s.enabled for s in template.segments)
    assert all(template.is_enabled(a) for a in SEGMENT_ORDER)
    assert template.separator == ""
    assert template.example_separator == ""
    assert template.chat_start_separator == ""
    assert template.stop_strings() == ()


def test_context_roundtrip_default():
    template = default_context_template()
    data = context_to_data(template)
    assert context_from_data(data) == template
    assert context_to_data(context_from_data(data)) == data


def test_prompt_package_exports_context_symbols():
    import runmal.prompt as pkg
    for name in ("SEGMENT_ORDER", "SEGMENT_KINDS",
                 "CONTEXT_TEMPLATE_ORDER", "ContextTemplate",
                 "ContextSegment", "apply_context_template",
                 "context_from_data",
                 "context_to_data", "default_context_template",
                 "from_story_string", "to_story_string",
                 "get_context_template", "list_context_templates",
                 "context_template_from_preset"):
        assert name in pkg.__all__, name
        assert getattr(pkg, name) is not None
    assert pkg.CONTEXT_DISABLED_REASON == "context_template_disabled"
    assert DISABLED_REASON == "context_template_disabled"

# ---------------- 2. default identity ----------------

def test_default_apply_identity_order():
    kept, dropped = apply_context_template(
        all_kind_slots(), default_context_template())
    assert dropped == []
    assert [s.kind for s in sorted(kept, key=lambda s: s.order)] == list(BASELINE_ORDER)


def test_default_compose_identity():
    slots = all_kind_slots()
    kept, _ = apply_context_template(slots, default_context_template())
    plain = compose(list(slots), **CTX)
    managed = compose(kept, **CTX)
    assert [m.slot_id for m in managed.messages] == [m.slot_id for m in plain.messages]
    assert [m.content for m in managed.messages] == [m.content for m in plain.messages]


def test_default_identity_triple_render():
    # Design S3 identity triple: (a) compose identity (pinned
    # above), (b) identity against the default P-049 layout,
    # (c) PLAIN render strings equal. There is no second render
    # path: assembly IS apply + compose + the P-050 render.
    from runmal.prompt.manager import apply_layout, default_layout
    slots = all_kind_slots()  # no depth slots in this set
    plain = compose(list(slots), **CTX)
    laid, dropped = apply_layout(list(slots), default_layout())
    assert dropped == []
    kept, dropped2 = apply_context_template(laid, default_context_template())
    assert dropped2 == []
    both = compose(kept, **CTX)
    assert [m.slot_id for m in both.messages] == [m.slot_id for m in plain.messages]
    assert [m.content for m in both.messages] == [m.content for m in plain.messages]
    plain_template = get_instruct_template("plain")
    assert render_prompt(both.messages, plain_template).text == \
        render_prompt(plain.messages, plain_template).text

# ---------------- 3. context_from_data validation ----------------

@pytest.mark.parametrize("bad", [
    "default",
    42,
    [],
    {"name": "x", "bogus": 1},
    {"name": ""},
    {"name": "   "},
    {"name": 3},
    {"name": "x", "separator": 1},
    {"name": "x", "stops_from_separators": "yes"},
    {"name": "x", "segments": "history"},
    {"name": "x", "segments": []},
    {"name": "x", "segments": ["history"]},
    {"name": "x", "segments": [{"anchor": "nope"}]},
    {"name": "x", "segments": [{"anchor": "history"}, {"anchor": "history"}]},
    {"name": "x", "segments": [{"anchor": "history", "enabled": "true"}]},
    {"name": "x", "segments": [{"anchor": "history", "enabled": 1}]},
    {"name": "x", "segments": [{"anchor": "history", "prefix": 1}]},
    {"name": "x", "segments": [{"anchor": "history", "suffix": None}]},
    {"name": "x", "segments": [{"anchor": "history", "weird": ""}]},
])
def test_context_from_data_rejects(bad):
    with pytest.raises(ValueError):
        context_from_data(bad)


def test_fill_missing_history_only_disabled():
    template = context_from_data(
        {"name": "f", "segments": [{"anchor": "history", "enabled": False}]})
    assert [s.anchor for s in template.segments] == list(SEGMENT_ORDER)
    assert template.is_enabled("history") is False
    assert template.position("history") == list(SEGMENT_ORDER).index("history")
    assert all(template.is_enabled(a) for a in SEGMENT_ORDER if a != "history")


def test_from_data_without_segments_is_all_enabled():
    template = context_from_data({"name": "bare"})
    assert [s.anchor for s in template.segments] == list(SEGMENT_ORDER)
    assert all(s.enabled for s in template.segments)

# ---------------- 4. apply semantics ----------------

def _slot(kind, role, content, slot_id, **kw):
    return make_slot(kind, role, content, id=slot_id, **kw)


def test_reorder_history_first_changes_compose_order():
    template = context_from_data({"name": "rev", "segments": [
        {"anchor": "history"}, {"anchor": "system"}, {"anchor": "persona"}]})
    slots = [
        _slot("main_system", "system", "SYS", "system/main", required=True),
        _slot("persona", "system", "PERSONA", "persona/x"),
        _slot("history", "user", "", "history", splittable=True, parts=("h1",)),
    ]
    kept, dropped = apply_context_template(slots, template)
    assert dropped == []
    ids = [m.slot_id for m in compose(kept, **CTX).messages]
    assert ids == ["history", "system/main", "persona/x"]


def test_disabling_persona_drops_it():
    template = context_from_data({"name": "np", "segments": [
        {"anchor": "persona", "enabled": False}]})
    slots = [
        _slot("main_system", "system", "SYS", "system/main", required=True),
        _slot("persona", "system", "PERSONA", "persona/x"),
    ]
    kept, dropped = apply_context_template(slots, template)
    assert [s.id for s in dropped] == ["persona/x"]
    assert [s.id for s in kept] == ["system/main"]
    assert DISABLED_REASON == "context_template_disabled"

def _wrap_template(chat_start=""):
    return ContextTemplate(
        name="w", chat_start_separator=chat_start,
        segments=(
            ContextSegment("system"),
            ContextSegment("persona", prefix="<P>", suffix="</P>"),
            ContextSegment("history", prefix="<H>", suffix="</H>"),
        ))


def test_prefix_suffix_wrap_normal_slot():
    slots = [_slot("persona", "system", "PERSONA", "persona/x")]
    kept, dropped = apply_context_template(slots, _wrap_template())
    assert dropped == []
    assert kept[0].content == "<P>PERSONA</P>"
    msgs = compose(kept, **CTX).messages
    assert [(m.slot_id, m.content) for m in msgs] == [("persona/x", "<P>PERSONA</P>")]


def test_prefix_suffix_wrap_splittable_history_first_last():
    slots = [_slot("history", "user", "", "history",
                   splittable=True, parts=("h1", "h2"))]
    kept, _ = apply_context_template(slots, _wrap_template())
    assert kept[0].parts == ("<H>h1", "h2</H>")
    msgs = compose(kept, **CTX).messages
    assert msgs[0].content == "<H>h1\nh2</H>"


def test_chat_start_separator_prefixes_history():
    slots = [_slot("history", "user", "", "history",
                   splittable=True, parts=("h1", "h2"))]
    kept, _ = apply_context_template(slots, _wrap_template(chat_start="[start]"))
    # Chat-start separator comes before the segment's own prefix.
    assert kept[0].parts == ("[start]<H>h1", "h2</H>")
    assert compose(kept, **CTX).messages[0].content.startswith("[start]")


def test_wrapping_is_idempotent():
    template = _wrap_template(chat_start="[start]")
    slots = [
        _slot("persona", "system", "PERSONA", "persona/x"),
        _slot("history", "user", "", "history",
              splittable=True, parts=("h1", "h2")),
    ]
    once, _ = apply_context_template(slots, template)
    twice, _ = apply_context_template(list(once), template)
    once_msgs = compose(list(once), **CTX).messages
    twice_msgs = compose(list(twice), **CTX).messages
    assert [m.slot_id for m in twice_msgs] == [m.slot_id for m in once_msgs]
    assert [m.content for m in twice_msgs] == [m.content for m in once_msgs]
    contents = [m.content for m in twice_msgs]
    assert "<P>PERSONA</P>" in contents
    assert "[start]<H>h1\nh2</H>" in contents


def test_depth_slot_splices_despite_segment_before_history():
    template = context_from_data({"name": "d", "segments": [
        {"anchor": "authors_note"}, {"anchor": "history"}]})
    assert template.position("authors_note") < template.position("history")
    depth = _slot("authors_note", "system", "DEPTHNOTE", "depth1", depth=2)
    history = _slot("history", "user", "", "history",
                    splittable=True, parts=("m1", "m2", "m3"))
    kept, dropped = apply_context_template([depth, history], template)
    assert dropped == []
    by_id = {s.id: s for s in kept}
    assert by_id["depth1"].order > by_id["history"].order
    msgs = compose(kept, **CTX).messages
    assert [(m.slot_id, m.content) for m in msgs] == [
        ("history", "m1"), ("depth1", "DEPTHNOTE"), ("history", "m2\nm3")]

# ---------------- 5. story strings ----------------

def test_to_story_string_default_contains_all_in_order():
    text = to_story_string(default_context_template())
    positions = [text.index("{{" + a + "}}") for a in SEGMENT_ORDER]
    assert positions == sorted(positions)
    assert text == "".join("{{" + a + "}}" for a in SEGMENT_ORDER)


def test_story_roundtrip_reproduces_enabled_set_and_order():
    parsed = from_story_string(to_story_string(default_context_template()))
    assert [s.anchor for s in parsed.segments if s.enabled] == list(SEGMENT_ORDER)
    assert all(s.enabled for s in parsed.segments)


def test_story_literals_become_prefix_and_suffix():
    parsed = from_story_string("{{system}}\n\n---\n{{persona}} tail")
    assert parsed.separator == ""
    system = parsed.segment("system")
    persona = parsed.segment("persona")
    assert system.enabled and system.prefix == "" and system.suffix == ""
    assert persona.enabled and persona.prefix == "\n\n---\n"
    assert persona.suffix == " tail"
    assert [s.anchor for s in parsed.segments if s.enabled] == ["system", "persona"]
    assert all(not s.enabled for s in parsed.segments
               if s.anchor not in ("system", "persona"))


@pytest.mark.parametrize("alias,anchor", [
    ("worldInfoBefore", "world_before"),
    ("worldInfoAfter", "world_after"),
    ("chatHistory", "history"),
    ("dialogueExamples", "examples"),
    ("mesExamples", "examples"),
    ("authorsNote", "authors_note"),
    ("main", "system"),
])
def test_story_aliases_parse(alias, anchor):
    assert STORY_ALIASES[alias] == anchor
    parsed = from_story_string("{{" + alias + "}}")
    assert [s.anchor for s in parsed.segments if s.enabled] == [anchor]


@pytest.mark.parametrize("bad", [
    "{{nope}}",
    "{{system}} and {{system}}",
    "{{examples}} and {{dialogueExamples}}",
    "no placeholders at all",
    "",
    "{{#if}} {{system}}",
    "{{system}} {{#if x}} tail",
])
def test_story_string_rejects(bad):
    with pytest.raises(ValueError):
        from_story_string(bad)

# ---------------- 6. preset derivation (design S5) ----------------

def _chat_preset():
    return parse_preset(CHAT_FIXTURE.read_bytes())


def test_preset_chat_fixture_end_to_end():
    template = context_template_from_preset(_chat_preset())
    assert template is not None
    # The preset's own order is preserved (system,
    # world_before, persona, examples, history, post_history);
    # the four unmentioned anchors fill ENABLED at their
    # baseline-relative positions.
    assert [s.anchor for s in template.segments] == [
        "system", "memory_nucleus", "world_before", "persona",
        "memory_retrieved", "examples", "history", "world_after",
        "authors_note", "post_history"]
    assert all(s.enabled for s in template.segments)
    # personaDescription (enabled, first) beats charDescription
    # (enabled=false, later): first occurrence wins.
    assert template.segment("persona").enabled is True
    assert template.segment("post_history").enabled is True


def test_preset_text_fixture_returns_none():
    parsed = parse_preset(TEXT_FIXTURE.read_bytes())
    assert context_template_from_preset(parsed) is None


def test_preset_str_entries_unknown_skipped():
    template = context_template_from_preset(
        {"name": "x", "prompt_order": ["chatHistory", "bogusId", "main"]})
    assert template is not None
    assert template.position("history") < template.position("system")
    assert {s.anchor for s in template.segments} == set(SEGMENT_ORDER)
    assert all(s.enabled for s in template.segments)


def test_preset_first_wins_disabled_persona():
    template = context_template_from_preset({"prompt_order": [
        {"identifier": "charDescription", "enabled": False},
        {"identifier": "personaDescription"}]})
    assert template.segment("persona").enabled is False


def test_preset_nothing_mappable_returns_none():
    assert context_template_from_preset({"prompt_order": ["zzz"]}) is None
    assert context_template_from_preset({"prompt_order": []}) is None
    assert context_template_from_preset({}) is None


def test_preset_grouped_raw_flattened():
    grouped = {"name": "g", "prompt_order": [],
               "raw": {"prompt_order": [
                   {"identifier": "char1", "order": [
                       {"identifier": "chatHistory"},
                       {"identifier": "main"}]}]}}
    template = context_template_from_preset(grouped)
    assert template.position("history") < template.position("system")
    direct = {"name": "g", "prompt_order": [
        {"order": ["chatHistory", "main"]}]}
    template2 = context_template_from_preset(direct)
    assert template2.position("history") < template2.position("system")


def test_preset_context_template_key_wins():
    preset = {"name": "p",
              "context_template": {"name": "ct", "segments": [
                  {"anchor": "history"}]},
              "raw": {"story_string": "{{system}}"},
              "prompt_order": ["system"]}
    template = context_template_from_preset(preset)
    assert template.name == "ct"
    assert template.position("history") == list(SEGMENT_ORDER).index("history")


def test_preset_context_template_string_form():
    template = context_template_from_preset(
        {"name": "p", "context_template": "{{history}}",
         "prompt_order": ["system"]})
    assert template.segment("history").enabled is True
    assert template.segment("system").enabled is False


def test_preset_story_string_beats_prompt_order():
    template = context_template_from_preset(
        {"name": "p", "raw": {"story_string": "{{history}}"},
         "prompt_order": ["system"]})
    assert template.segment("history").enabled is True
    # Story strings fill DISABLED: the string is the whole assembly.
    assert template.segment("system").enabled is False


def test_preset_raw_context_template_beats_raw_story():
    template = context_template_from_preset({"name": "p", "raw": {
        "context_template": {"name": "rct", "segments": [
            {"anchor": "system"}]},
        "story_string": "{{history}}"}})
    assert template.name == "rct"
    # Data form fills ENABLED (the story form would disable it).
    assert template.segment("history").enabled is True

# ---------------- 7. service resolve / echo (design S6) ----------------

def test_resolve_explicit_forms():
    template, source = resolve_context_template("default")
    assert source == "explicit" and template.name == "default"
    template, source = resolve_context_template(
        {"name": "d", "segments": [{"anchor": "history"}]})
    assert source == "explicit" and template.name == "d"
    template, source = resolve_context_template("{{history}}")
    assert source == "explicit"
    assert template.segment("system").enabled is False
    with pytest.raises(ValueError):
        resolve_context_template("nope")


def test_resolve_preset_tier_and_default_none():
    template, source = resolve_context_template(None, preset=_chat_preset())
    assert source == "preset" and template is not None
    template, source = resolve_context_template(
        None, preset={"prompt_order": []})
    assert template is None and source == "default"
    template, source = resolve_context_template(None)
    assert template is None and source == "default"


def test_echo_whitelist_and_no_affix_leak():
    template = context_from_data({
        "name": "w", "separator": "SEPMARK",
        "stops_from_separators": True,
        "segments": [{"anchor": "system", "prefix": "SECRET-PREFIX-XYZ"}]})
    echo = context_echo(template, "explicit")
    assert set(echo) == {"source", "segments", "stop_strings"}
    assert echo["source"] == "explicit"
    assert echo["stop_strings"] == ["SEPMARK"]
    assert all(set(row) == {"anchor", "enabled"} for row in echo["segments"])
    assert "SECRET-PREFIX-XYZ" not in json.dumps(echo)


def test_echo_none_is_default_template():
    echo = context_echo(None, "default")
    assert echo == {
        "source": "default",
        "segments": [{"anchor": a, "enabled": True} for a in SEGMENT_ORDER],
        "stop_strings": [],
    }

# ---------------- 8. inspector / API (design S6/S8H) ----------------

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _inspect(client, **kw):
    resp = client.post("/api/v1/debug/prompt-inspect", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _default_echo(source="default"):
    return {
        "source": source,
        "segments": [{"anchor": a, "enabled": True} for a in SEGMENT_ORDER],
        "stop_strings": [],
    }


def test_api_context_default_echo(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=["hello"])
    assert result["context_template"] == _default_echo()


def test_api_context_no_input_matches_explicit_default(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    plain = _inspect(client, messages=["hello"])
    explicit = _inspect(client, messages=["hello"], context_template="default")
    assert explicit["context_template"] == _default_echo("explicit")
    assert explicit["slots"] == plain["slots"]
    assert explicit["ledger"] == plain["ledger"]
    assert explicit["rendered_tokens"] == plain["rendered_tokens"]


def test_api_context_story_string_discards_system(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=["hello"], context_template="{{history}}")
    by_id = {s["slot_id"]: s for s in result["slots"]}
    assert by_id["system/main"]["status"] == "discarded"
    assert by_id["system/main"]["reason"] == "context_template_disabled"
    segments = {r["anchor"]: r["enabled"]
                for r in result["context_template"]["segments"]}
    assert segments["history"] is True
    assert segments["system"] is False
    assert MAIN_SYSTEM_TEXT not in json.dumps(result)


def test_api_context_wrap_tokens_and_no_leak(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    baseline = _inspect(client, messages=["hello"])
    wrapped = _inspect(client, messages=["hello"], context_template={
        "name": "w", "segments": [
            {"anchor": "system", "prefix": "WRAPMARK "}]})
    assert wrapped["rendered_tokens"] > baseline["rendered_tokens"]
    assert "WRAPMARK" not in json.dumps(wrapped)


def test_api_context_preset_tier_applies(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    preset = {"prompt_order": [
        {"identifier": "main", "enabled": False},
        {"identifier": "chatHistory"}]}
    result = _inspect(client, messages=["hello"], context_preset=preset)
    assert result["context_template"]["source"] == "preset"
    by_id = {s["slot_id"]: s for s in result["slots"]}
    assert by_id["system/main"]["status"] == "discarded"
    assert by_id["system/main"]["reason"] == "context_template_disabled"


def test_api_context_layout_then_context_precedence(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(
        client, messages=["hello"],
        prompt_layout={"blocks": [{"block": "history"},
                                  {"block": "system"}]},
        context_template="{{system}}\n{{history}}")
    included = [s["slot_id"] for s in result["slots"]
                if s["status"] == "included"]
    assert included.index("system/main") < included.index("history")


def test_api_context_422s(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    for payload in ({"context_template": {"name": "x", "bogus": 1}},
                    {"context_template": "{{nope}}"},
                    {"context_template": "nope"}):
        resp = client.post("/api/v1/debug/prompt-inspect", json=payload)
        assert resp.status_code == 422, payload


def test_api_context_registry_endpoints(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    listing = client.get("/api/v1/debug/context-templates")
    assert listing.status_code == 200
    assert [t["name"] for t in listing.json()["templates"]] == ["default"]
    default = client.get("/api/v1/debug/context-templates/default")
    assert default.status_code == 200
    body = default.json()
    assert body["template"] == _default_echo()
    assert body["story_string"].startswith("{{system}}")


def test_migration_head_still_0032():
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0035"  # head moved by P-057 (PROVISIONAL 0035)

# ---------------- 9. extra apply / story pins ----------------

@pytest.mark.parametrize("bad", [
    "{{char}}", "{{summary}}", "{{charDescription}}",
    "{{WorldInfoBefore}}", "{{outlet::X}}",
])
def test_story_string_rejects_macros_and_ids(bad):
    with pytest.raises(ValueError):
        from_story_string(bad)


def test_story_string_allows_spaces_in_braces():
    parsed = from_story_string("{{ system }}")
    assert [s.anchor for s in parsed.segments if s.enabled] == ["system"]


def test_bare_list_equals_segments_dict():
    bare = context_from_data([{"anchor": "history", "enabled": False}])
    wrapped = context_from_data(
        {"name": "custom", "segments": [{"anchor": "history",
                                          "enabled": False}]})
    assert bare == wrapped


def test_apply_multi_slot_lore_wraps_per_slot():
    template = ContextTemplate(name="w", segments=(
        ContextSegment("world_before", prefix="<W>", suffix="</W>"),))
    slots = [
        _slot("lore_before", "system", "L1", "lore/1"),
        _slot("lore_before", "system", "L2", "lore/2"),
    ]
    kept, dropped = apply_context_template(slots, template)
    assert dropped == []
    assert [s.content for s in kept] == ["<W>L1</W>", "<W>L2</W>"]


def test_apply_inputs_unmutated():
    template = _wrap_template(chat_start="[start]")
    persona = _slot("persona", "system", "PERSONA", "persona/x")
    history = _slot("history", "user", "", "history",
                    splittable=True, parts=("h1", "h2"))
    apply_context_template([persona, history], template)
    assert persona.content == "PERSONA"
    assert history.parts == ("h1", "h2")


def test_apply_unknown_kind_goes_to_tail():
    template = ContextTemplate(
        name="t", segments=(ContextSegment("system"),))
    mystery = make_slot("mystery", "system", "M", id="s/mystery")
    kept, dropped = apply_context_template([mystery], template)
    assert dropped == []
    assert kept[0].order == 100 + len(BASELINE_ORDER)


def test_chat_start_without_history_is_noop():
    template = _wrap_template(chat_start="[start]")
    slots = [_slot("persona", "system", "PERSONA", "persona/x")]
    kept, _ = apply_context_template(slots, template)
    assert kept[0].content == "<P>PERSONA</P>"
    assert "[start]" not in kept[0].content


def test_depth_slot_history_disabled_no_raise():
    template = context_from_data({"name": "x", "segments": [
        {"anchor": "history", "enabled": False},
        {"anchor": "authors_note"}]})
    depth = _slot("authors_note", "system", "NOTE", "depth1", depth=1)
    history = _slot("history", "user", "", "history",
                    splittable=True, parts=("m1",))
    kept, dropped = apply_context_template([depth, history], template)
    assert [s.id for s in dropped] == ["history"]
    expected = (template.position("authors_note") * 100
                + list(BASELINE_ORDER).index("authors_note"))
    assert kept[0].order == expected
