"""P-082 plugin sandbox battery.

Pins the plugin sandbox contract: the policy module turns a
P-081-shaped manifest into a closed, immutable GrantSet (surface
permissions grant no resource access, unknown names refuse loudly
as UNKNOWN_GRANT, malformed declarations refuse as
MALFORMED_MANIFEST, and grant sets never widen at runtime), and
the guard's Sandbox is the only context a plugin handler is
handed: files stay inside the sandbox root, network and secrets
are reachable only under a declared grant, every allow/deny is
audited without ever recording file contents or secret values,
and a handler that keeps failing is quarantined after
FAILURE_LIMIT consecutive failures without ever raising into the
chat path. No new migration: this slice is pure policy + guard.
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from runmal.db.migrations import MIGRATIONS
from runmal.sandbox.guard import FAILURE_LIMIT, Sandbox
from runmal.sandbox.policy import (
    KNOWN_CAPABILITIES,
    RESOURCE_PERMISSIONS,
    SURFACE_PERMISSIONS,
    GrantSet,
    SandboxError,
    SandboxErrorKind,
    grants_from_manifest,
)

SECRET = "ZqxSandboxSecret82"
OTHER_SECRET = "ZqxOtherSecret82"
PLUGIN = "acme.example"
ALL_SURFACE = sorted(SURFACE_PERMISSIONS)
ALL_CAPS = sorted(KNOWN_CAPABILITIES)
ALL_RESOURCES = sorted(RESOURCE_PERMISSIONS)


def manifest(**over):
    data = {"id": PLUGIN, "permissions": [], "capabilities": []}
    data.update(over)
    return data


def deny_entries(sb):
    return [e for e in sb.audit_log() if e.outcome == "deny"]


def allow_entries(sb):
    return [e for e in sb.audit_log() if e.outcome == "allow"]


def boom():
    raise RuntimeError("kaput")


# ---------------- grants derivation ----------------


def test_empty_manifest_data_grants_nothing():
    grants = grants_from_manifest(manifest())
    assert grants.plugin_id == PLUGIN
    assert grants.resources == frozenset()
    assert grants.surface_permissions == frozenset()
    assert grants.capabilities == frozenset()


def test_v1_surface_only_manifest_grants_no_resources():
    grants = grants_from_manifest(
        manifest(permissions=ALL_SURFACE, capabilities=ALL_CAPS)
    )
    assert grants.resources == frozenset()
    assert grants.surface_permissions == SURFACE_PERMISSIONS
    assert grants.capabilities == KNOWN_CAPABILITIES


def test_resource_permissions_become_exact_resources():
    grants = grants_from_manifest(manifest(permissions=ALL_RESOURCES))
    assert grants.resources == RESOURCE_PERMISSIONS
    assert grants.surface_permissions == frozenset()
    assert grants.capabilities == frozenset()


def test_mixed_manifest_splits_surface_and_resources():
    grants = grants_from_manifest(
        manifest(
            permissions=["files.read", "chat.read", "ui.contribute"],
            capabilities=["chat.events"],
        )
    )
    assert grants.resources == frozenset({"files.read"})
    assert grants.surface_permissions == frozenset({"chat.read", "ui.contribute"})
    assert grants.capabilities == frozenset({"chat.events"})


def test_unknown_permission_is_unknown_grant():
    with pytest.raises(SandboxError) as excinfo:
        grants_from_manifest(manifest(permissions=["files.read", "teleport"]))
    assert excinfo.value.kind == SandboxErrorKind.UNKNOWN_GRANT


def test_unknown_capability_is_unknown_grant():
    with pytest.raises(SandboxError) as excinfo:
        grants_from_manifest(manifest(capabilities=["chat.events", "time.travel"]))
    assert excinfo.value.kind == SandboxErrorKind.UNKNOWN_GRANT


def test_missing_id_is_malformed():
    with pytest.raises(SandboxError) as excinfo:
        grants_from_manifest({"permissions": [], "capabilities": []})
    assert excinfo.value.kind == SandboxErrorKind.MALFORMED_MANIFEST


def test_empty_id_is_malformed():
    with pytest.raises(SandboxError) as excinfo:
        grants_from_manifest(manifest(id=""))
    assert excinfo.value.kind == SandboxErrorKind.MALFORMED_MANIFEST


def test_nonstring_id_is_malformed():
    with pytest.raises(SandboxError) as excinfo:
        grants_from_manifest(manifest(id=42))
    assert excinfo.value.kind == SandboxErrorKind.MALFORMED_MANIFEST


def test_callable_in_permissions_is_malformed():
    with pytest.raises(SandboxError) as excinfo:
        grants_from_manifest(manifest(permissions=[len]))
    assert excinfo.value.kind == SandboxErrorKind.MALFORMED_MANIFEST


def test_bare_string_permissions_is_malformed():
    with pytest.raises(SandboxError) as excinfo:
        grants_from_manifest(manifest(permissions="files.read"))
    assert excinfo.value.kind == SandboxErrorKind.MALFORMED_MANIFEST


def test_duck_typed_object_manifest_works():
    obj = SimpleNamespace(
        id=PLUGIN, permissions=["files.read"], capabilities=["chat.events"]
    )
    grants = grants_from_manifest(obj)
    assert grants.plugin_id == PLUGIN
    assert grants.resources == frozenset({"files.read"})
    assert grants.capabilities == frozenset({"chat.events"})


def test_grantset_is_frozen():
    grants = grants_from_manifest(manifest())
    with pytest.raises(FrozenInstanceError):
        grants.plugin_id = "other.example"


def test_grantset_expanded_is_escalation():
    grants = grants_from_manifest(manifest(permissions=["files.read"]))
    with pytest.raises(SandboxError) as excinfo:
        grants.expanded("files.write")
    assert excinfo.value.kind == SandboxErrorKind.ESCALATION


def test_grantset_allows_checks_resources_only():
    grants = grants_from_manifest(manifest(permissions=["files.read", "chat.read"]))
    assert grants.allows("files.read") is True
    assert grants.allows("files.write") is False
    assert grants.allows("chat.read") is False


# ---------------- construction escalation ----------------


def test_sandbox_extra_resource_grant_escalates():
    greedy = GrantSet(plugin_id=PLUGIN, resources=frozenset({"files.read"}))
    with pytest.raises(SandboxError) as excinfo:
        Sandbox(manifest(), grants=greedy)
    assert excinfo.value.kind == SandboxErrorKind.ESCALATION


def test_sandbox_subset_grants_accepted():
    subset = GrantSet(plugin_id=PLUGIN, resources=frozenset({"files.read"}))
    sb = Sandbox(manifest(permissions=["files.read", "files.write"]), grants=subset)
    assert sb.plugin_id == PLUGIN
    assert sb.grants.resources == frozenset({"files.read"})


def test_sandbox_mismatched_plugin_id_escalates():
    foreign = GrantSet(plugin_id="evil.example")
    with pytest.raises(SandboxError) as excinfo:
        Sandbox(manifest(), grants=foreign)
    assert excinfo.value.kind == SandboxErrorKind.ESCALATION


# ---------------- files ----------------


def test_read_ungranted_denied_and_audited(tmp_path):
    sb = Sandbox(manifest(), root=tmp_path)
    with pytest.raises(SandboxError) as excinfo:
        sb.read_file("note.txt")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED
    assert any(
        e.kind == SandboxErrorKind.PERMISSION_DENIED for e in deny_entries(sb)
    )


def test_write_ungranted_denied_and_audited(tmp_path):
    sb = Sandbox(manifest(), root=tmp_path)
    with pytest.raises(SandboxError) as excinfo:
        sb.write_file("note.txt", b"hello")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED
    assert any(
        e.kind == SandboxErrorKind.PERMISSION_DENIED for e in deny_entries(sb)
    )
    assert not (tmp_path / "note.txt").exists()


def test_write_read_roundtrip_with_nested_subdir(tmp_path):
    sb = Sandbox(manifest(permissions=["files.read", "files.write"]), root=tmp_path)
    sb.write_file("sub/dir/note.txt", b"hello sandbox")
    assert (tmp_path / "sub" / "dir" / "note.txt").read_bytes() == b"hello sandbox"
    assert sb.read_file("sub/dir/note.txt") == b"hello sandbox"
    assert allow_entries(sb)


def test_read_only_grant_cannot_write(tmp_path):
    sb = Sandbox(manifest(permissions=["files.read"]), root=tmp_path)
    with pytest.raises(SandboxError) as excinfo:
        sb.write_file("note.txt", b"nope")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED


def test_write_only_grant_cannot_read(tmp_path):
    (tmp_path / "note.txt").write_bytes(b"data")
    sb = Sandbox(manifest(permissions=["files.write"]), root=tmp_path)
    with pytest.raises(SandboxError) as excinfo:
        sb.read_file("note.txt")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED


def test_dotdot_escape_is_path_escape(tmp_path):
    sb = Sandbox(manifest(permissions=["files.read", "files.write"]), root=tmp_path)
    with pytest.raises(SandboxError) as excinfo:
        sb.read_file("../outside.txt")
    assert excinfo.value.kind == SandboxErrorKind.PATH_ESCAPE
    with pytest.raises(SandboxError) as excinfo:
        sb.write_file("../outside.txt", b"escape")
    assert excinfo.value.kind == SandboxErrorKind.PATH_ESCAPE


def test_absolute_path_outside_root_is_path_escape(tmp_path):
    sb = Sandbox(manifest(permissions=["files.read"]), root=tmp_path)
    outside = str(tmp_path.parent / "p082_outside.txt")
    with pytest.raises(SandboxError) as excinfo:
        sb.read_file(outside)
    assert excinfo.value.kind == SandboxErrorKind.PATH_ESCAPE


def test_symlink_inside_root_pointing_outside_is_path_escape(tmp_path):
    outside = tmp_path.parent / "p082_link_target.txt"
    outside.write_bytes(b"outside data")
    os.symlink(outside, tmp_path / "link.txt")
    sb = Sandbox(manifest(permissions=["files.read"]), root=tmp_path)
    with pytest.raises(SandboxError) as excinfo:
        sb.read_file("link.txt")
    assert excinfo.value.kind == SandboxErrorKind.PATH_ESCAPE


def test_absolute_path_inside_root_allowed(tmp_path):
    sb = Sandbox(manifest(permissions=["files.read", "files.write"]), root=tmp_path)
    target = str(tmp_path / "abs.txt")
    sb.write_file(target, b"absolute")
    assert sb.read_file(target) == b"absolute"


def test_no_root_is_path_escape():
    sb = Sandbox(manifest(permissions=["files.read"]))
    with pytest.raises(SandboxError) as excinfo:
        sb.read_file("note.txt")
    assert excinfo.value.kind == SandboxErrorKind.PATH_ESCAPE


def test_write_non_bytes_is_type_error(tmp_path):
    sb = Sandbox(manifest(permissions=["files.write"]), root=tmp_path)
    with pytest.raises(TypeError):
        sb.write_file("note.txt", "not bytes")


def test_denied_error_contains_no_file_content(tmp_path):
    sb = Sandbox(manifest(permissions=["files.write"]), root=tmp_path)
    sb.write_file("diary.txt", SECRET.encode())
    with pytest.raises(SandboxError) as excinfo:
        sb.read_file("other.txt")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED
    assert SECRET not in str(excinfo.value)
    assert SECRET not in str([e.to_dict() for e in sb.audit_log()])


# ---------------- network ----------------


def test_fetch_ungranted_denied():
    sb = Sandbox(manifest(), network_transport=lambda m, u: "body")
    with pytest.raises(SandboxError) as excinfo:
        sb.fetch("https://example.invalid/data")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED


def test_fetch_granted_uses_transport_with_get():
    calls = []

    def transport(method, url):
        calls.append((method, url))
        return "response-body"

    sb = Sandbox(
        manifest(permissions=["network.access"]), network_transport=transport
    )
    assert sb.fetch("https://example.invalid/data") == "response-body"
    assert calls == [("GET", "https://example.invalid/data")]


def test_fetch_post_is_uppercased_for_transport():
    calls = []

    def transport(method, url):
        calls.append((method, url))
        return "ok"

    sb = Sandbox(
        manifest(permissions=["network.access"]), network_transport=transport
    )
    assert sb.fetch("https://example.invalid/submit", method="post") == "ok"
    assert calls == [("POST", "https://example.invalid/submit")]


def test_fetch_granted_without_transport_is_no_transport():
    sb = Sandbox(manifest(permissions=["network.access"]))
    with pytest.raises(SandboxError) as excinfo:
        sb.fetch("https://example.invalid/data")
    assert excinfo.value.kind == SandboxErrorKind.NO_TRANSPORT


def test_fetch_ftp_scheme_denied():
    calls = []
    sb = Sandbox(
        manifest(permissions=["network.access"]),
        network_transport=lambda m, u: calls.append((m, u)),
    )
    with pytest.raises(SandboxError) as excinfo:
        sb.fetch("ftp://example.invalid/file")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED
    assert calls == []


def test_fetch_file_scheme_denied():
    sb = Sandbox(
        manifest(permissions=["network.access"]),
        network_transport=lambda m, u: "body",
    )
    with pytest.raises(SandboxError) as excinfo:
        sb.fetch("file:///etc/passwd")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED


# ---------------- secrets ----------------


def test_get_secret_ungranted_denied():
    sb = Sandbox(manifest(), secret_provider={"api_key": SECRET})
    with pytest.raises(SandboxError) as excinfo:
        sb.get_secret("api_key")
    assert excinfo.value.kind == SandboxErrorKind.PERMISSION_DENIED
    assert SECRET not in str(excinfo.value)


def test_get_secret_from_dict_provider():
    sb = Sandbox(
        manifest(permissions=["secrets.read"]),
        secret_provider={"api_key": SECRET},
    )
    assert sb.get_secret("api_key") == SECRET
    assert SECRET not in str([e.to_dict() for e in sb.audit_log()])


def test_get_secret_from_callable_provider():
    def provider(name):
        return {"token": SECRET}[name]

    sb = Sandbox(manifest(permissions=["secrets.read"]), secret_provider=provider)
    assert sb.get_secret("token") == SECRET


def test_get_secret_missing_names_name_without_leaking_values():
    provider = {"api_key": SECRET, "other": OTHER_SECRET}
    sb = Sandbox(manifest(permissions=["secrets.read"]), secret_provider=provider)
    with pytest.raises(SandboxError) as excinfo:
        sb.get_secret("missing_key")
    assert excinfo.value.kind == SandboxErrorKind.SECRET_NOT_FOUND
    assert "missing_key" in str(excinfo.value)
    assert SECRET not in str(excinfo.value)
    assert OTHER_SECRET not in str(excinfo.value)
    audit_text = str([e.to_dict() for e in sb.audit_log()])
    assert SECRET not in audit_text
    assert OTHER_SECRET not in audit_text


def test_get_secret_without_provider_is_not_found():
    sb = Sandbox(manifest(permissions=["secrets.read"]))
    with pytest.raises(SandboxError) as excinfo:
        sb.get_secret("api_key")
    assert excinfo.value.kind == SandboxErrorKind.SECRET_NOT_FOUND


# ---------------- capabilities ----------------


def test_require_declared_capability_passes_and_audits():
    sb = Sandbox(manifest(capabilities=["chat.events", "ui.slots"]))
    sb.require_capability("chat.events")
    sb.require_capability("ui.slots")
    assert allow_entries(sb)


def test_require_undeclared_capability_denied_and_audited():
    sb = Sandbox(manifest(capabilities=["chat.events"]))
    with pytest.raises(SandboxError) as excinfo:
        sb.require_capability("prompt.hooks")
    assert excinfo.value.kind == SandboxErrorKind.CAPABILITY_DENIED
    assert any(
        e.kind == SandboxErrorKind.CAPABILITY_DENIED for e in deny_entries(sb)
    )


# ---------------- isolation: run / quarantine ----------------


def test_run_success_returns_value():
    sb = Sandbox(manifest())
    outcome = sb.run(lambda: 42)
    assert outcome.ok is True
    assert outcome.value == 42
    assert sb.consecutive_failures == 0
    assert sb.quarantined is False


def test_run_passes_args_and_kwargs():
    sb = Sandbox(manifest())
    outcome = sb.run(lambda a, b=0: a + b, 2, b=3)
    assert outcome.ok is True
    assert outcome.value == 5


def test_run_exception_is_captured_never_raised():
    sb = Sandbox(manifest())
    outcome = sb.run(boom)
    assert outcome.ok is False
    assert outcome.failure.error_type == "RuntimeError"
    assert "kaput" in outcome.failure.message
    assert sb.consecutive_failures == 1
    assert len(sb.failures()) == 1


def test_run_failure_message_truncated_at_200():
    def loud():
        raise RuntimeError("x" * 500)

    sb = Sandbox(manifest())
    outcome = sb.run(loud)
    assert outcome.ok is False
    assert 0 < len(outcome.failure.message) <= 200


def test_run_success_resets_failure_counter():
    sb = Sandbox(manifest())
    sb.run(boom)
    assert sb.consecutive_failures == 1
    outcome = sb.run(lambda: "fine")
    assert outcome.ok is True
    assert sb.consecutive_failures == 0
    assert sb.quarantined is False


def test_three_consecutive_failures_quarantine():
    assert FAILURE_LIMIT == 3
    sb = Sandbox(manifest())
    for _ in range(FAILURE_LIMIT):
        assert sb.run(boom).ok is False
    assert sb.quarantined is True
    assert sb.consecutive_failures == FAILURE_LIMIT
    assert len(sb.failures()) == FAILURE_LIMIT


def test_quarantined_run_returns_quarantined_without_calling():
    sb = Sandbox(manifest())
    for _ in range(FAILURE_LIMIT):
        sb.run(boom)
    called = []
    outcome = sb.run(lambda: called.append(True))
    assert outcome.ok is False
    assert outcome.kind == "quarantined"
    assert called == []


def test_reset_failures_clears_quarantine():
    sb = Sandbox(manifest())
    for _ in range(FAILURE_LIMIT):
        sb.run(boom)
    assert sb.quarantined is True
    sb.reset_failures()
    assert sb.quarantined is False
    assert sb.consecutive_failures == 0
    outcome = sb.run(lambda: "back")
    assert outcome.ok is True
    assert outcome.value == "back"


# ---------------- audit hygiene ----------------


def test_audit_entries_carry_context_fields(tmp_path):
    sb = Sandbox(
        manifest(
            permissions=["files.write", "network.access"],
            capabilities=["chat.events"],
        ),
        root=tmp_path,
        network_transport=lambda m, u: "body",
    )
    sb.write_file("note.txt", b"hi")
    sb.fetch("https://example.invalid/")
    sb.require_capability("chat.events")
    with pytest.raises(SandboxError):
        sb.require_capability("ui.slots")
    entries = sb.audit_log()
    assert entries
    assert allow_entries(sb)
    assert deny_entries(sb)
    for entry in entries:
        assert entry.plugin_id == PLUGIN
        assert entry.resource
        assert entry.action
        assert entry.outcome in ("allow", "deny")
    assert any(
        e.kind == SandboxErrorKind.CAPABILITY_DENIED for e in deny_entries(sb)
    )


def test_audit_entry_to_dict_keys_exact(tmp_path):
    sb = Sandbox(manifest(permissions=["files.write"]), root=tmp_path)
    sb.write_file("note.txt", b"hi")
    entry = sb.audit_log()[0]
    assert set(entry.to_dict()) == {
        "plugin_id",
        "resource",
        "action",
        "outcome",
        "kind",
        "at",
    }
    assert entry.to_dict()["plugin_id"] == PLUGIN


# ---------------- neighbours ----------------


def test_no_new_migration_in_p082():
    assert "0042" not in MIGRATIONS
