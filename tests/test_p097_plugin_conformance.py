"""P-097 Plugin conformance kit battery.

Pins the contract from hidden_files/P097_DESIGN.md: a plugin
must pass contract + sandbox tests to be listed. Every
shipped Part VI citizen (P-084..P-095, plus the kit citizen
itself, plus any further citizen module discovery finds -
the P-096 road) passes the kit AS SHIPPED; the corpus is
deterministic (byte-identical checksummed core, twice) and
its listable set is exactly the passing set; a minimal
data-only plugin and a UI data plugin pass on data alone;
deliberately non-conforming fixtures fail with EVERY failure
named (unknown vocabulary, a smuggled resource permission,
an unsupported api version, unmet surface requirements, an
oversize UI payload, duplicate hook ids, missing and
undeclared hook handlers, malformed settings, and a lying
citizen whose claimed grants differ from its manifest);
checking never mutates the submission or the default
registry; neighbours: migration head stays 0041, the boot
registry stays empty (P-081), the kit citizen's grants stay
empty (P-082).
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import conformance as cf
from runmal.plugins import service as plugin_service
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRegistry
from runmal.sandbox.policy import GrantSet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def base_data(**overrides):
    data = {
        "id": "example.echo",
        "name": "Echo",
        "version": "1.0.0",
        "api_version": 1,
        "description": "A deliberately small test plugin.",
        "author": "Test",
        "capabilities": [],
        "permissions": [],
        "events": [],
        "prompt_hooks": [],
        "ui_slots": [],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }
    data.update(overrides)
    return data


def hook_data(**overrides):
    base = {
        "capabilities": ["prompt.hooks"],
        "permissions": ["prompt.inject"],
        "prompt_hooks": [
            {"id": "echo-hook", "stage": "slots", "priority": 100}],
    }
    base.update(overrides)
    return base_data(**base)


def failures_of(report):
    return "\n".join(report["failures"])


# -- The kit citizen itself --------------------------------------------------


def test_kit_manifest_round_trips_and_registers():
    data = cf.manifest_data()
    manifest = manifest_from_data(data)
    assert manifest_to_data(manifest)["id"] == "runmal.plugin-conformance"
    registry = PluginRegistry()
    record, _plugin = cf.register_plugin(registry)
    assert record.state.value == "registered"
    assert registry.keys() == ["runmal.plugin-conformance"]


def test_kit_grants_empty():
    grants = cf.sandbox_grants()
    assert grants.resources == frozenset()
    assert grants.plugin_id == "runmal.plugin-conformance"


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"


def test_boot_registry_stays_empty():
    assert plugin_service.build_registry().keys() == []


# -- The corpus: every shipped citizen passes as shipped ---------------------


def test_every_shipped_citizen_passes():
    modules = cf.citizen_modules()
    ids = [plugin_id for _path, plugin_id in modules]
    for expected in ("runmal.summarise", "runmal.vector-storage",
                     "runmal.translate", "runmal.image-generation",
                     "runmal.web-search", "runmal.quick-replies",
                     "runmal.regex-scripts", "runmal.tts", "runmal.stt",
                     "runmal.expressions", "runmal.variables",
                     "runmal.plugin-custody", "runmal.gallery",
                     "runmal.plugin-conformance"):
        assert expected in ids
    for path, plugin_id in modules:
        report = cf.check_citizen(path)
        assert report["plugin_id"] == plugin_id
        assert report["passed"], (
            f"{plugin_id} failed its own kit: {report['failures']}")
        assert report["listable"] is True
        assert [c["name"] for c in report["checks"]][-1] == "citizen_pattern"


def test_corpus_all_passed_listable_and_deterministic():
    corpus = cf.conformance_corpus()
    assert corpus["all_passed"] is True
    assert corpus["failed"] == []
    assert corpus["listable"] == corpus["passed"]
    assert len(corpus["citizens"]) >= 14
    again = cf.conformance_corpus()
    assert again["content_sha256"] == corpus["content_sha256"]
    assert again["citizens"] == corpus["citizens"]


def test_report_is_jsonable_and_deterministic():
    report = cf.check_citizen("runmal.plugins.summarise")
    json.dumps(report)
    second = cf.check_citizen("runmal.plugins.summarise")
    assert second == report
    assert len(report["content_sha256"]) == 64


def test_check_names_fixed_order():
    report = cf.check_manifest_data(base_data())
    assert [c["name"] for c in report["checks"]] == [
        "vocabulary", "identity", "manifest_parses", "round_trip",
        "surface_requirements", "ui_contributions", "settings_shape",
        "handlers_binding", "registration", "grants_derived",
        "grants_empty_resources", "sandbox_denials"]
    assert report["passed"] and report["failures"] == []


# -- Passing submissions -------------------------------------------------------


def test_minimal_data_plugin_passes():
    report = cf.check_manifest_data(base_data())
    assert report["passed"], report["failures"]
    assert cf.is_listable(report)


def test_ui_data_plugin_passes():
    data = base_data(
        capabilities=["ui.slots"], permissions=["ui.contribute"],
        ui_slots=[{"id": "echo-panel", "slot": "chat.sidebar",
                   "label": "Echo", "order": 10,
                   "payload": {"kind": "panel", "route": "echo"}}])
    report = cf.check_manifest_data(data)
    assert report["passed"], report["failures"]


def test_hook_plugin_with_handlers_passes():
    handlers = PluginHandlers(
        prompt_hooks={"echo-hook": lambda ctx, slots: None})
    report = cf.check_manifest_data(hook_data(), handlers=handlers)
    assert report["passed"], report["failures"]


def test_check_manifest_accepts_manifest_object():
    manifest = manifest_from_data(base_data())
    report = cf.check_manifest(manifest)
    assert report["passed"], report["failures"]
    assert report["plugin_id"] == "example.echo"


def test_check_never_mutates_submission_or_default_registry():
    data = hook_data()
    snapshot = copy.deepcopy(data)
    handlers = PluginHandlers(
        prompt_hooks={"echo-hook": lambda ctx, slots: None})
    cf.check_manifest_data(data, handlers=handlers)
    assert data == snapshot
    assert plugin_service.get_default_registry() is None
    cf.conformance_corpus()
    assert plugin_service.get_default_registry() is None


# -- Non-conforming fixtures: every failure named ------------------------------


def test_unknown_capability_fails_named():
    report = cf.check_manifest_data(base_data(capabilities=["teleport"]))
    assert not report["passed"] and not cf.is_listable(report)
    assert "unknown_capability: 'teleport'" in failures_of(report)


def test_smuggled_resource_permission_fails_named_twice():
    report = cf.check_manifest_data(
        base_data(permissions=["network.access"]))
    assert not report["passed"]
    text = failures_of(report)
    assert "unknown_permission: 'network.access'" in text
    assert "resource_grant_present: 'network.access'" in text


def test_unsupported_api_version_fails_named():
    report = cf.check_manifest_data(base_data(api_version=99))
    assert not report["passed"]
    text = failures_of(report)
    assert "unsupported_api_version: 99" in text
    assert "registration_failed" in text


def test_invalid_identity_fails_named():
    report = cf.check_manifest_data(
        base_data(id="Bad ID!", version="1.0"))
    assert not report["passed"]
    text = failures_of(report)
    assert "invalid_plugin_id" in text
    assert "invalid_version" in text


def test_surface_ui_without_capability_or_permission_fails_named():
    data = base_data(ui_slots=[{
        "id": "echo-panel", "slot": "chat.sidebar", "label": "Echo",
        "order": 10, "payload": {"kind": "panel"}}])
    report = cf.check_manifest_data(data)
    assert not report["passed"]
    text = failures_of(report)
    assert "declared ui slots require capability 'ui.slots'" in text
    assert "declared ui slots require permission 'ui.contribute'" in text


def test_surface_slots_hook_without_inject_fails_named():
    data = hook_data(permissions=[])
    handlers = PluginHandlers(
        prompt_hooks={"echo-hook": lambda ctx, slots: None})
    report = cf.check_manifest_data(data, handlers=handlers)
    assert not report["passed"]
    assert "requires permission 'prompt.inject'" in failures_of(report)


def test_surface_generation_event_without_observe_fails_named():
    data = base_data(capabilities=["chat.events"],
                     permissions=["chat.read"],
                     events=["generation.after"])
    report = cf.check_manifest_data(data)
    assert not report["passed"]
    assert "generation.observe" in failures_of(report)


def test_oversize_ui_payload_fails_named():
    data = base_data(
        capabilities=["ui.slots"], permissions=["ui.contribute"],
        ui_slots=[{"id": "echo-panel", "slot": "chat.sidebar",
                   "label": "Echo", "order": 10,
                   "payload": {"blob": "x" * 5000}}])
    report = cf.check_manifest_data(data)
    assert not report["passed"]
    assert "ui_payload_too_large" in failures_of(report)


def test_duplicate_hook_id_fails_named():
    data = hook_data(prompt_hooks=[
        {"id": "echo-hook", "stage": "slots", "priority": 100},
        {"id": "echo-hook", "stage": "slots", "priority": 90}])
    report = cf.check_manifest_data(data)
    assert not report["passed"]
    assert "duplicate prompt hook id" in failures_of(report)


def test_missing_hook_handler_fails_named():
    report = cf.check_manifest_data(hook_data())
    assert not report["passed"]
    text = failures_of(report)
    assert "missing_hook_handler: 'echo-hook'" in text
    assert "registration_failed" in text


def test_undeclared_hook_handler_fails_named():
    handlers = PluginHandlers(prompt_hooks={
        "echo-hook": lambda ctx, slots: None,
        "sneaky-hook": lambda ctx, slots: None})
    report = cf.check_manifest_data(hook_data(), handlers=handlers)
    assert not report["passed"]
    assert "undeclared_hook_handler: 'sneaky-hook'" in failures_of(report)


def test_malformed_settings_fail_named():
    report = cf.check_manifest_data(
        base_data(settings={"schema": {}, "defaults": {}, "bogus": {}}))
    assert not report["passed"]
    assert "settings_shape" in failures_of(report)


def test_mega_fixture_every_failure_named():
    """One deliberately non-conforming plugin; each failure named."""
    data = base_data(capabilities=["teleport"],
                     permissions=["network.access"], api_version=99)
    report = cf.check_manifest_data(data)
    assert not report["passed"] and not report["listable"]
    text = failures_of(report)
    for needle in ("unknown_capability: 'teleport'",
                   "unknown_permission: 'network.access'",
                   "unsupported_api_version: 99",
                   "resource_grant_present: 'network.access'"):
        assert needle in text, needle
    assert report["failures"]  # the flat list is never empty on a fail
    for row in report["checks"]:
        if not row["passed"]:
            assert row["failures"], row["name"]


def test_lying_citizen_fails_named():
    """A citizen claiming grants its manifest does not derive."""
    def lying_grants():
        return GrantSet(plugin_id=cf.PLUGIN_ID,
                        resources=frozenset({"network.access"}))
    fake = SimpleNamespace(
        PLUGIN_ID=cf.PLUGIN_ID, manifest_data=cf.manifest_data,
        build_manifest=cf.build_manifest,
        register_plugin=cf.register_plugin, sandbox_grants=lying_grants)
    report = cf.check_citizen(fake)
    assert not report["passed"]
    assert "sandbox_grants_mismatch" in failures_of(report)


def test_incomplete_citizen_fails_named():
    fake = SimpleNamespace(PLUGIN_ID="example.incomplete")
    report = cf.check_citizen(fake)
    assert not report["passed"]
    assert "citizen_pattern_missing" in failures_of(report)


def test_listing_gate_filters_to_passing_only():
    good = cf.check_manifest_data(base_data())
    bad = cf.check_manifest_data(base_data(capabilities=["teleport"]))
    assert cf.listable_ids([good, bad]) == ["example.echo"]
    assert cf.is_listable(good) and not cf.is_listable(bad)


def test_check_names_fixed_order_on_parse_failure():
    """The fixed order holds on the not_run road too (design s.3):
    settings_shape sits in its own slot, before the not_run
    handlers_binding / registration rows - a parse failure must
    not reshuffle the report."""
    report = cf.check_manifest_data(base_data(capabilities=["teleport"]))
    assert not report["passed"]
    assert [c["name"] for c in report["checks"]] == [
        "vocabulary", "identity", "manifest_parses", "round_trip",
        "surface_requirements", "ui_contributions", "settings_shape",
        "handlers_binding", "registration", "grants_derived",
        "grants_empty_resources", "sandbox_denials"]
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["handlers_binding"]["failures"] == [
        "not_run: manifest did not parse"]
    assert by_name["registration"]["failures"] == [
        "not_run: manifest did not parse"]
