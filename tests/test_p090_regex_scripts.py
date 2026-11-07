"""P-090 Regex Scripts plugin battery.

Pins the citizen contract from hidden_files/P090_DESIGN.md
against src/runmal/plugins/regex_scripts.py: the ST-shaped
importable format (aliases, slash form, placement decode) with
canonical round-trip, declared-stage application through the
pure apply_scripts road and the messages hook, the safe regex
dialect (backreference / lookbehind / nested-quantifier /
quantifier-bound refusals -- including the {,n} brace form and
duplicate group names, both defect-fixed in-slice), the
replacement grammar, per-rule timeout discipline in a forked
child, the durable per-user file store (P-089 idiom), citizen
registration with empty P-082 sandbox grants, and the
migration / boot neighbours (head stays 0041, empty boot
registry). Tests touch no network.
"""

from __future__ import annotations

import pytest

from runmal.db.base import create_db_engine, create_session_factory  # noqa: F401
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import service as plugin_service
from runmal.plugins.hooks import PromptHookContext, apply_message_hooks
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.regex_scripts import (
    DECLARED_EVENTS,
    HOOK_ID,
    MAX_IMPORT_ROWS,
    MAX_SCRIPTS_PER_USER,
    PLUGIN_ID,
    STORE_DIR_NAME,
    UI_LOCAL_ID,
    InvalidRegexError,
    RegexScript,
    RegexScriptsPlugin,
    RegexScriptStoreCorruptError,
    RegexScriptValidationError,
    UnknownFieldError,
    UnsafeRegexError,
    apply_scripts,
    build_manifest,
    create_script,
    delete_script,
    export_scripts,
    get_script,
    import_scripts,
    list_scripts,
    manifest_data,
    register_plugin,
    sandbox_grants,
    script_from_data,
    script_from_document,
    script_to_data,
    select_for_prompt,
    store_path,
    update_script,
    validate_pattern,
    validate_replacement,
)
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.prompt.composer import ComposedMessage

USER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER2 = "99999999-9999-4999-8999-999999999999"
CHAT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OTHER_CHAT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SCRIPT_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SCRIPT_ID2 = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


@pytest.fixture(autouse=True)
def _reset_default_registry():
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def ctx_for(chat_id):
    return PromptHookContext(
        plugin_id=PLUGIN_ID, hook_id=HOOK_ID, stage="messages",
        chat_id=chat_id)


def make_script(**kw):
    base = dict(id=SCRIPT_ID, name="rule", pattern="hello",
                replace_string="bye", stages=("user_input",))
    base.update(kw)
    return RegexScript(**base)


# ---------------- registration / manifest / sandbox ----------------


def test_manifest_data_matches_design():
    data = manifest_data()
    assert data["id"] == PLUGIN_ID == "runmal.regex-scripts"
    assert data["name"] == "Regex Scripts"
    assert data["version"] == "1.0.0"
    assert data["api_version"] == 1
    assert data["capabilities"] == ["chat.events", "prompt.hooks", "ui.slots"]
    assert data["permissions"] == [
        "chat.read", "prompt.inject", "prompt.modify", "ui.contribute"]
    assert data["events"] == list(DECLARED_EVENTS) == [
        "chat.created", "chat.deleted"]
    assert data["prompt_hooks"] == [
        {"id": HOOK_ID, "stage": "messages", "priority": 90}]
    assert data["ui_slots"] == [{
        "id": UI_LOCAL_ID, "slot": "settings.panel",
        "label": "Regex Scripts", "order": 90,
        "payload": {"kind": "panel", "route": "regex-scripts"}}]
    assert data["settings"] == {"schema": {}, "defaults": {}}
    assert data["enabled_by_default"] is False


def test_manifest_round_trips_and_registers():
    manifest = build_manifest()
    assert manifest_from_data(manifest_to_data(manifest)) == manifest
    registry = PluginRegistry()
    record, plugin = register_plugin(registry)
    assert record.state is PluginState.REGISTERED
    assert plugin.manifest == manifest
    registry2 = PluginRegistry()
    record2, _ = register_plugin(registry2, enable=True)
    assert record2.state is PluginState.ENABLED


def test_sandbox_grants_empty():
    grants = sandbox_grants()
    assert grants.resources == frozenset()
    assert grants.plugin_id == PLUGIN_ID
    assert grants.surface_permissions == frozenset(manifest_data()["permissions"])
    assert "chat.write" not in manifest_data()["permissions"]
    assert "network.access" not in manifest_data()["permissions"]


def test_no_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert "0042" not in MIGRATIONS


def test_boot_registry_stays_empty_without_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    assert PLUGIN_ID not in registry.keys()
    assert plugin_service.rehydration_problems() == []


# ---------------- importable format ----------------


def test_st_shaped_import_aliases():
    body = script_from_data({
        "scriptName": "  Shout  ", "findRegex": "/hello\\/world/gi",
        "replaceString": "<$0>", "trimStrings": ["x"],
        "placement": [1, 2, "markdown"], "disabled": True})
    assert body["name"] == "Shout"
    assert body["pattern"] == "hello/world"
    assert body["flags"] == "i"  # g dropped (sub is global), i kept
    assert body["replace_string"] == "<$0>"
    assert body["trim_strings"] == ["x"]
    assert body["stages"] == ["user_input", "ai_output", "display"]
    assert body["enabled"] is False  # disabled inverted
    assert body["scope"] == "user" and body["chat_id"] is None
    assert body["id"] is None


def test_slash_form_flag_merge_and_canonical_flag_order():
    body = script_from_data({
        "name": "x", "findRegex": "/a\\/b/i", "flags": "sm"})
    assert body["pattern"] == "a/b"
    assert body["flags"] == "ims"  # stored sorted in ims order
    body2 = script_from_data({"name": "x", "pattern": "a", "flags": "gu"})
    assert body2["flags"] == ""  # g/u accepted and dropped canonically too


def test_placement_defaults_and_only_filters():
    def stages(**kw):
        doc = {"name": "x", "pattern": "a"}
        doc.update(kw)
        return script_from_data(doc)["stages"]
    assert stages() == ["user_input", "ai_output"]
    assert stages(promptOnly=True) == ["prompt_assembly"]
    assert stages(markdownOnly=True) == ["display"]
    assert stages(promptOnly=True, markdownOnly=True) == [
        "prompt_assembly", "display"]
    # With a placement list: markdownOnly drops prompt_assembly,
    # promptOnly drops display (the design's filter rule).
    assert stages(placement=["prompt", "display"],
                  markdownOnly=True) == ["display"]
    assert stages(placement=["prompt", "display"],
                  promptOnly=True) == ["prompt_assembly"]
    with pytest.raises(RegexScriptValidationError) as ei:
        stages(placement=["prompt"], markdownOnly=True)
    assert ei.value.code == "stage_set_empty"


def test_conflicting_alias_and_contradictory_disabled():
    with pytest.raises(RegexScriptValidationError) as ei:
        script_from_data({"name": "a", "scriptName": "b", "pattern": "x"})
    assert ei.value.code == "conflicting_alias"
    with pytest.raises(RegexScriptValidationError) as ei:
        script_from_data({"pattern": "x", "findRegex": "y", "name": "n"})
    assert ei.value.code == "conflicting_alias"
    with pytest.raises(RegexScriptValidationError) as ei:
        script_from_data({"name": "n", "pattern": "x",
                          "stages": ["display"], "placement": [1]})
    assert ei.value.code == "conflicting_alias"
    with pytest.raises(RegexScriptValidationError) as ei:
        script_from_data({"name": "n", "pattern": "x",
                          "disabled": False, "enabled": False})
    assert ei.value.code == "contradictory_field"
    ok = script_from_data({"name": "n", "pattern": "x",
                           "disabled": True, "enabled": False})
    assert ok["enabled"] is False  # agreeing pair is accepted
    same = script_from_data({"name": "n", "scriptName": "n", "pattern": "x"})
    assert same["name"] == "n"  # identical alias + canonical is fine


def test_unknown_fields_refused():
    with pytest.raises(UnknownFieldError) as ei:
        script_from_data({"name": "n", "pattern": "x", "bogus": 1, "zz": 2})
    assert ei.value.code == "unknown_field"
    assert ei.value.unknown_keys == ("bogus", "zz")


def test_field_validation_matrix():
    def bad(doc, code=None):
        with pytest.raises(RegexScriptValidationError) as ei:
            script_from_data(doc)
        if code is not None:
            assert ei.value.code == code
    bad({"name": "  ", "pattern": "x"})  # name strips to empty
    bad({"name": "n" * 121, "pattern": "x"})
    bad({"name": 5, "pattern": "x"})  # no type coercion
    bad({"name": "n", "pattern": ""}, code="pattern_empty")
    bad({"name": "n", "pattern": "x", "flags": "x"},
        code="unsupported_flag")
    bad({"name": "n", "pattern": "x", "enabled": "yes"})
    bad({"name": "n", "pattern": "x", "stages": "user_input"})
    bad({"name": "n", "pattern": "x", "trim_strings": "ab"})
    bad({"name": "n", "pattern": "x", "trim_strings": [""]})
    bad({"name": "n", "pattern": "x", "scope": "global"})
    bad({"name": "n", "pattern": "x", "scope": "chat"})  # needs chat_id
    bad({"name": "n", "pattern": "x", "chat_id": CHAT})  # user scope
    bad({"name": "n", "pattern": "x", "id": "not-a-uuid"})
    ok = script_from_data({"name": "n", "pattern": "x", "scope": "chat",
                           "chat_id": CHAT.upper()})
    assert ok["chat_id"] == CHAT  # UUID normalised


def test_placement_refusals():
    for placement in ([4], ["1"], [True], ["nowhere"], [1.5]):
        with pytest.raises(RegexScriptValidationError) as ei:
            script_from_data({"name": "n", "pattern": "x",
                              "placement": placement})
        assert ei.value.code == "unsupported_placement"


# ---------------- safe dialect ----------------


@pytest.mark.parametrize("pattern,code", [
    (r"(a+)\1", "backreference"),
    (r"(?P<x>a)(?P=x)", "backreference"),
    (r"(?<=a)b", "lookbehind"),
    (r"(?<!a)b", "lookbehind"),
    (r"(a+)+", "nested_quantifier"),
    (r"a**", "nested_quantifier"),
    (r"(x{,3})+", "nested_quantifier"),  # {,n} is a real quantifier
    (r"a{2}{3}", "nested_quantifier"),
    (r"a{,2000}", "quantifier_bound_too_large"),  # {,n} bound honoured
    (r"a{1001}", "quantifier_bound_too_large"),
    (r"a{0,1001}", "quantifier_bound_too_large"),
    (r"(?>a)", "unsupported_group_construct"),
    (r"(?(1)a|b)", "unsupported_group_construct"),
    (r"(?#c)a", "unsupported_group_construct"),
    (r"(?<n>a)", "unsupported_group_construct"),
    (r"(?P<x>a)(?P<x>b)", "unsupported_group_construct"),  # duplicate name
    (r"(?x)a", "unsupported_group_construct"),  # x not in the ims dialect
])
def test_safe_dialect_refusals(pattern, code):
    with pytest.raises(UnsafeRegexError) as ei:
        validate_pattern(pattern)
    assert ei.value.code == code


@pytest.mark.parametrize("pattern", [
    r"a{,5}", r"a{,}", r"a{}", r"a{1000}", r"a{2,}", r"a*?", r"a??b",
    r"(?:ab|cd)+", r"(?i)hello", r"(?ims:a)", r"[\1]", r"\\1",
    r"(?P<word>\w+)", r"x|y{3}",
])
def test_safe_dialect_accepts(pattern):
    assert validate_pattern(pattern) is not None


def test_heuristic_pass_is_caught_by_timeout_not_scan():
    # The design's honesty line: (a|aa)+$ passes the scan and is
    # caught only by the timeout (pinned in the timeout test).
    assert validate_pattern(r"(a|aa)+$") is not None


def test_invalid_pattern_refused():
    with pytest.raises(InvalidRegexError) as ei:
        validate_pattern("(")
    assert ei.value.code == "invalid_pattern"
    with pytest.raises(RegexScriptValidationError) as ei:
        validate_pattern("")
    assert ei.value.code == "pattern_empty"


# ---------------- replacement grammar ----------------


def test_replacement_grammar_refusals():
    def bad(template, groups, names, code):
        with pytest.raises(RegexScriptValidationError) as ei:
            validate_replacement(template, groups, names)
        assert ei.value.code == code
        assert ei.value.field == "replace_string"
    bad("$9", 1, {}, "unknown_group_reference")
    bad("$<nope>", 1, {"x": 1}, "unknown_group_reference")
    bad("${nope}", 1, {}, "unknown_group_reference")
    bad("${}", 1, {}, "bad_substitution")
    bad("$<x", 1, {"x": 1}, "bad_substitution")
    bad("${1", 1, {}, "bad_substitution")
    bad("trailing$", 0, {}, "bad_substitution")
    bad("$x", 0, {}, "bad_substitution")


def test_replacement_grammar_accepts_and_maximal_digit_run():
    for template in ("$$", "$0", "$&", "$1", "${1}", "$<x>", "${x}",
                     "plain", "a$b".replace("$b", "$1")):
        assert validate_replacement(template, 1, {"x": 1}) is not None
    # $digits is one maximal run: $12 means group 12, never $1 + "2".
    with pytest.raises(RegexScriptValidationError):
        validate_replacement("$12", 1, {})
    assert validate_replacement("$12", 12, {}) is not None


# ---------------- application ----------------


def test_apply_declared_stages_only():
    script = make_script()
    out, rows = apply_scripts("hello world", "user_input", [script])
    assert out == "bye world"
    assert rows[0].status == "applied" and rows[0].match_count == 1
    out, rows = apply_scripts("hello world", "ai_output", [script])
    assert out == "hello world"
    assert rows[0].status == "skipped_wrong_stage"
    out, rows = apply_scripts("hello", "user_input",
                              [make_script(enabled=False)])
    assert out == "hello" and rows[0].status == "skipped_disabled"
    out, rows = apply_scripts("nothing here", "user_input", [script])
    assert out == "nothing here" and rows[0].status == "no_match"
    row_dict = rows[0].to_dict()
    assert set(row_dict) == {"script_id", "name", "stage", "status",
                             "match_count", "duration_ms", "detail_code"}


def test_apply_order_chains_and_failures_are_isolated():
    first = make_script(id=SCRIPT_ID, pattern="a", replace_string="b")
    unsafe = make_script(id=SCRIPT_ID2, name="evil", pattern="(a+)+",
                         replace_string="z")
    last = make_script(id=SCRIPT_ID, name="last", pattern="b",
                       replace_string="c")
    out, rows = apply_scripts("a a", "user_input", [first, unsafe, last])
    assert out == "c c"  # the second rule sees the first rule's output
    assert [r.status for r in rows] == [
        "applied", "refused_unsafe", "applied"]
    assert rows[1].detail_code == "nested_quantifier"


def test_apply_replacement_tokens_and_trims():
    script = make_script(
        pattern=r"(\w+)@(\w+)",
        replace_string="$2/$1 $$ $& ${1}", trim_strings=["/"])
    out, rows = apply_scripts("ab@cd", "user_input", [script])
    # $2/$1 expands to cd/ab, then the / trim is removed per match;
    # $$ is a literal $, $& and ${1} expand to the whole match / group 1.
    assert out == "cdab $ ab@cd ab"
    assert rows[0].status == "applied" and rows[0].match_count == 1
    named = make_script(pattern=r"(?P<w>\w+)", replace_string="<$<w>|${w}>")
    out, _ = apply_scripts("hey", "user_input", [named])
    assert out == "<hey|hey>"
    missing_group = make_script(pattern=r"(a)|(b)", replace_string="[$1$2]")
    out, _ = apply_scripts("b", "user_input", [missing_group])
    assert out == "[b]"  # a non-participating group expands to empty


def test_apply_timeout_discipline():
    evil = make_script(name="evil", pattern=r"(a|aa)+$",
                       replace_string="X")
    good = make_script(id=SCRIPT_ID2, name="good", pattern="!",
                       replace_string="?")
    text = "a" * 30 + "!"
    out, rows = apply_scripts(text, "user_input", [evil, good],
                              timeout_s=0.25)
    assert rows[0].status == "timed_out"
    assert rows[1].status == "applied"  # later rules are unaffected
    assert out == "a" * 30 + "?"  # the timed-out rule changed nothing


def test_apply_whole_call_guards():
    script = make_script()
    with pytest.raises(RegexScriptValidationError):
        apply_scripts("x", "nowhere", [script])
    for bad_timeout in (0, -1, 1.5, True, "0.25"):
        with pytest.raises(RegexScriptValidationError):
            apply_scripts("x", "user_input", [script],
                          timeout_s=bad_timeout)
    with pytest.raises(RegexScriptValidationError) as ei:
        apply_scripts("x" * 65537, "user_input", [script])
    assert ei.value.code == "input_too_large"


def test_apply_output_growth_refused():
    script = make_script(pattern="a", replace_string="b" * 100)
    out, rows = apply_scripts("a" * 3000, "user_input", [script])
    assert rows[0].status == "refused_output_growth"
    assert out == "a" * 3000  # the grown result is discarded whole


# ---------------- durable store ----------------


def test_store_crud_and_canonical_round_trip(tmp_path):
    base = str(tmp_path)
    created = create_script(USER, {
        "scriptName": "Greet", "findRegex": "/hello/i",
        "replaceString": "bye", "placement": [1, 3]}, base_dir=base)
    assert created["stages"] == ["user_input", "prompt_assembly"]
    assert set(created) == {
        "id", "name", "pattern", "flags", "replace_string",
        "trim_strings", "stages", "enabled", "scope", "chat_id",
        "created_at", "updated_at"}
    # Canonical round-trip: stored document -> object -> same dict.
    assert script_to_data(script_from_document(created)) == created
    assert get_script(USER, created["id"], base_dir=base) == created
    assert list_scripts(USER, base_dir=base) == [created]
    assert list_scripts(USER2, base_dir=base) == []  # per-user isolation
    updated = update_script(USER, created["id"], {
        "name": "Greet2", "pattern": "hi", "replace_string": "yo",
        "stages": ["user_input"]}, base_dir=base)
    assert updated["name"] == "Greet2"
    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
    assert update_script(USER, SCRIPT_ID, {
        "name": "x", "pattern": "y"}, base_dir=base) is None
    assert delete_script(USER, created["id"], base_dir=base) is True
    assert delete_script(USER, created["id"], base_dir=base) is False
    assert get_script(USER, created["id"], base_dir=base) is None


def test_store_duplicate_id_and_limit(tmp_path):
    base = str(tmp_path)
    doc = {"id": SCRIPT_ID, "name": "one", "pattern": "a"}
    create_script(USER, doc, base_dir=base)
    with pytest.raises(RegexScriptValidationError) as ei:
        create_script(USER, doc, base_dir=base)
    assert ei.value.code == "duplicate_id"
    rows = [{"name": f"r{i}", "pattern": "a"}
            for i in range(MAX_SCRIPTS_PER_USER - 1)]
    report = import_scripts(USER, rows, base_dir=base)
    assert len(report.accepted) == MAX_SCRIPTS_PER_USER - 1
    with pytest.raises(RegexScriptValidationError) as ei:
        create_script(USER, {"name": "over", "pattern": "a"}, base_dir=base)
    assert ei.value.code == "store_limit"


def test_import_partial_atomicity_and_row_cap(tmp_path):
    base = str(tmp_path)
    # Nothing accepted -> no store file is created at all.
    report = import_scripts(USER, [
        {"scriptName": "bad", "findRegex": "(a+)+"},
        {"scriptName": "bad2", "findRegex": "x", "bogus": 1}], base_dir=base)
    assert report.accepted == ()
    assert [r.index for r in report.refused] == [0, 1]
    assert report.refused[0].code == "nested_quantifier"
    assert report.refused[0].error_type == "UnsafeRegexError"
    assert not store_path(USER, base_dir=base).exists()
    # Mixed import: good rows land, bad rows are reported, and a
    # duplicate of an accepted row inside the same import refuses.
    report = import_scripts(USER, [
        {"id": SCRIPT_ID, "name": "one", "pattern": "a"},
        {"id": SCRIPT_ID, "name": "dup", "pattern": "b"},
        {"scriptName": "two", "findRegex": "/c/", "replaceString": "d"}],
        base_dir=base)
    assert [r["name"] for r in report.accepted] == ["one", "two"]
    assert [r.code for r in report.refused] == ["duplicate_id"]
    assert [r["name"] for r in export_scripts(USER, base_dir=base)] == [
        "one", "two"]
    with pytest.raises(RegexScriptValidationError):
        import_scripts(USER, [{"name": "x", "pattern": "a"}] * (
            MAX_IMPORT_ROWS + 1), base_dir=base)
    assert len(export_scripts(USER, base_dir=base)) == 2  # unchanged


def test_store_corrupt_never_silently_reset(tmp_path):
    base = str(tmp_path)
    path = store_path(USER, base_dir=base)
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(RegexScriptStoreCorruptError):
        list_scripts(USER, base_dir=base)
    assert path.read_text(encoding="utf-8") == "{oops"  # untouched
    path.write_text('{"schema": "other", "scripts": []}',
                    encoding="utf-8")
    with pytest.raises(RegexScriptStoreCorruptError):
        list_scripts(USER, base_dir=base)
    # A stored row carrying import aliases is not canonical -> corrupt.
    import json
    row = {"id": SCRIPT_ID, "name": "x", "pattern": "a", "flags": "",
           "replace_string": "", "trim_strings": [], "stages": ["user_input"],
           "enabled": True, "scope": "user", "chat_id": None,
           "created_at": "t", "updated_at": "t", "scriptName": "x"}
    path.write_text(json.dumps(
        {"schema": "runmal-p090-regex-scripts-v1", "scripts": [row]}),
        encoding="utf-8")
    with pytest.raises(RegexScriptStoreCorruptError):
        list_scripts(USER, base_dir=base)


def test_store_path_validates_and_normalises_user():
    path = store_path(USER.upper())
    assert path.name == f"{USER}.json"
    assert path.parent.name == STORE_DIR_NAME
    with pytest.raises(RegexScriptValidationError):
        store_path("not-a-uuid")
    with pytest.raises(RegexScriptValidationError):
        store_path("../escape")


def test_select_for_prompt_scope():
    rows = [
        {"name": "u", "scope": "user", "chat_id": None},
        {"name": "mine", "scope": "chat", "chat_id": CHAT},
        {"name": "theirs", "scope": "chat", "chat_id": OTHER_CHAT},
        "not-a-dict",
    ]
    picked = select_for_prompt(rows, CHAT)
    assert [r["name"] for r in picked] == ["u", "mine"]
    picked = select_for_prompt(rows, None)
    assert [r["name"] for r in picked] == ["u"]


# ---------------- the citizen hook ----------------


async def test_hook_abstains_without_bound_user(tmp_path):
    plugin = RegexScriptsPlugin(base_dir=str(tmp_path))
    messages = [ComposedMessage("user", "hello", "history")]
    assert await plugin.regex_messages(ctx_for(CHAT), messages) is None


async def test_hook_applies_prompt_assembly_stage_only(tmp_path):
    base = str(tmp_path)
    create_script(USER, {"name": "prompt", "pattern": "hello",
                         "replace_string": "bye",
                         "stages": ["prompt_assembly"]}, base_dir=base)
    create_script(USER, {"name": "input-only", "pattern": "hello",
                         "replace_string": "NOPE",
                         "stages": ["user_input"]}, base_dir=base)
    plugin = RegexScriptsPlugin(base_dir=base, user_id=USER)
    first = ComposedMessage("user", "hello there", "history")
    second = ComposedMessage("assistant", "untouched", "reply")
    out = await plugin.regex_messages(ctx_for(CHAT), [first, second])
    assert out is not None
    assert out[0].content == "bye there"  # prompt_assembly rule applied
    assert out[0].role == "user" and out[0].slot_id == "history"
    assert out[1] is second  # unchanged messages pass through as-is
    # Nothing to change -> abstain.
    quiet = [ComposedMessage("user", "no match here", "history")]
    assert await plugin.regex_messages(ctx_for(CHAT), quiet) is None


async def test_hook_chat_scope(tmp_path):
    base = str(tmp_path)
    create_script(USER, {"name": "scoped", "pattern": "hello",
                         "replace_string": "bye", "scope": "chat",
                         "chat_id": CHAT,
                         "stages": ["prompt_assembly"]}, base_dir=base)
    plugin = RegexScriptsPlugin(base_dir=base, user_id=USER)
    messages = [ComposedMessage("user", "hello", "history")]
    assert await plugin.regex_messages(ctx_for(OTHER_CHAT), messages) is None
    out = await plugin.regex_messages(ctx_for(CHAT), messages)
    assert out is not None and out[0].content == "bye"


async def test_hook_through_message_machinery(tmp_path):
    base = str(tmp_path)
    create_script(USER, {"name": "prompt", "pattern": "hello",
                         "replace_string": "bye",
                         "stages": ["prompt_assembly"]}, base_dir=base)
    registry = PluginRegistry()
    record, _plugin = register_plugin(
        registry, base_dir=base, user_id=USER, enable=True)
    assert record.state is PluginState.ENABLED
    messages = [ComposedMessage("user", "hello world", "history")]
    out, echoes = await apply_message_hooks(
        registry, {"chat_id": CHAT}, messages)
    assert out[0].content == "bye world"
    assert echoes[0]["plugin_id"] == PLUGIN_ID
    assert echoes[0]["outcome"] == "applied"


async def test_on_event_is_noop_and_never_deletes_scripts(tmp_path):
    base = str(tmp_path)
    created = create_script(USER, {"name": "keep", "pattern": "a"},
                            base_dir=base)
    plugin = RegexScriptsPlugin(base_dir=base, user_id=USER)
    assert await plugin.on_event(object()) is None
    assert get_script(USER, created["id"], base_dir=base) is not None


async def test_hook_store_error_propagates_typed(tmp_path):
    base = str(tmp_path)
    path = store_path(USER, base_dir=base)
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    plugin = RegexScriptsPlugin(base_dir=base, user_id=USER)
    messages = [ComposedMessage("user", "hello", "history")]
    with pytest.raises(RegexScriptStoreCorruptError):
        await plugin.regex_messages(ctx_for(CHAT), messages)
