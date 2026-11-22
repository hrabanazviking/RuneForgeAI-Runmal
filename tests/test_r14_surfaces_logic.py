"""R-14 acceptance (logic): the backups / plugins / library
search / bridge client views, request shapes, and Qt-free logic
words over a fake transport.

Payloads are copied from the engine's own shapes:
``BackupInfo.to_dict`` / ``service.list_backups`` rows /
``FullBackupInfo.to_dict`` / ``RestoreReport.to_dict``,
``record_to_dict`` / ``record_detail_to_dict`` /
``permission_card`` / ``FailureReport.to_dict``,
``reply_to_data`` (quick replies), ``set_to_data`` +
selection documents (expressions), the hub + workspace
unified-search documents, and ``credential_to_dict``.
"""

import httpx
import pytest

from runmal.desktop.backups_logic import (
    BackupFlow,
    backup_line,
    backups_words,
    stage_words,
)
from runmal.desktop.bridge_logic import (
    BridgeFlow,
    bridge_status_words,
    credential_line,
)
from runmal.desktop.client import (
    BackupView,
    BridgeCredentialView,
    DesktopSession,
    ExpressionSetView,
    LibraryHitView,
    NotFoundError,
    PluginFailureReportView,
    PluginView,
    QuickReplyView,
    RunmalClient,
)
from runmal.desktop.library_search_logic import (
    LibrarySearchFlow,
    hit_line,
    results_words,
)
from runmal.desktop.plugin_logic import (
    PluginFlow,
    expression_set_line,
    failure_line,
    permission_words,
    plugin_detail_words,
    plugin_line,
    quick_reply_line,
)

TOKEN = "test-token-r14"
CHAR_ID = "11111111-1111-4111-8111-111111111111"
CHAT_ID = "22222222-2222-4222-8222-222222222222"
CRED_ID = "33333333-3333-4333-8333-333333333333"
REPLY_ID = "44444444-4444-4444-8444-444444444444"

BACKUP_INFO = {
    "name": "runmal-backup-20261122T131905.db",
    "path": "/data/backups/runmal-backup-20261122T131905.db",
    "sha256": "ab12cd",
    "size_bytes": 540672,
    "created_at": "2026-11-22T13:19:05+00:00",
    "schema_revision": "0042",
    "app_version": "0.1.0",
    "secrets_included": False,
}

BACKUP_LIST_ROW = {
    "name": "runmal-backup-20261122T131905.db",
    "size_bytes": 540672,
    "modified_at": "2026-11-22T13:19:05+00:00",
}

FULL_INFO = {
    "name": "runmal-full-backup-20261122T131905.zip",
    "path": "/data/backups/runmal-full-backup-20261122T131905.zip",
    "sha256": "ef34ab",
    "size_bytes": 9793,
    "created_at": "2026-11-22T13:19:05+00:00",
    "schema_revision": "0042",
    "app_version": "0.1.0",
    "asset_files": 3,
    "secrets_included": False,
}

FULL_STAGE_REPORT = {
    "ok": True,
    "bundle": "/data/backups/runmal-full-backup-20261122T131905.zip",
    "staged_db": "/data/staging/full-restore-1/runmal.db",
    "staged_assets_dir": "/data/staging/full-restore-1/assets",
    "schema_revision": "0042",
    "counts": {"characters": 2, "chats": 1},
    "checks": [
        {"name": "checksums", "ok": True,
         "detail": "all member checksums verified"},
        {"name": "assets", "ok": True, "detail": "3 asset files staged"},
    ],
    "warnings": [],
}

PLUGIN = {
    "id": "quick-replies",
    "name": "Quick Replies",
    "version": "1.0.0",
    "api_version": 1,
    "state": "enabled",
    "capabilities": ["chat.events", "ui.slots"],
    "permissions": ["chat.read", "ui.contribute"],
    "events": ["chat.message"],
    "prompt_hooks": 0,
    "ui_slots": 1,
    "consecutive_failures": 0,
    "last_error": None,
}

PLUGIN_DETAIL = {
    **PLUGIN,
    "manifest": {
        "id": "quick-replies", "name": "Quick Replies",
        "version": "1.0.0", "api_version": 1,
        "description": "User-defined one-tap macros.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": ["chat.message"], "prompt_hooks": [],
        "ui_slots": [], "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    },
    "failure_log": [
        {"plugin_id": "quick-replies", "surface": "event",
         "hook": "chat.message", "error_type": "ValueError",
         "message": "boom", "at": "2026-11-22T10:00:00+00:00"},
    ],
    "ui_contributions": [],
    "reserved_permissions": [],
}

CARD = {
    "plugin_id": "quick-replies",
    "name": "Quick Replies",
    "version": "1.0.0",
    "api_version": 1,
    "description": "User-defined one-tap macros.",
    "author": "Rúnmál",
    "capabilities": [
        {"name": "chat.events", "note": "Subscribes to the declared chat events."},
        {"name": "ui.slots", "note": "Contributes to the declared UI slots."},
    ],
    "permissions": [
        {"name": "chat.read",
         "effect": "Message text may ride in the chat events this "
                   "plugin subscribes to.",
         "reserved": False, "granted": None},
        {"name": "chat.write", "effect": "RESERVED: declared for "
         "future use.", "reserved": True, "granted": False},
    ],
    "permission_names": ["chat.read", "chat.write"],
    "events": ["chat.message"],
    "prompt_hooks": [],
    "ui_slots": [],
    "settings_declared": True,
    "enabled_by_default": False,
    "requires_grant": True,
    "notes": ["permission 'chat.write' is reserved in v1"],
    "changes": None,
    "manifest": {},
}

FAILURE_REPORT = {
    "plugin_id": "quick-replies",
    "state": "enabled",
    "enabled": True,
    "self_disabled": False,
    "consecutive_failures": 1,
    "failure_limit": 3,
    "total_recorded": 2,
    "last_failure": {"surface": "event", "hook": "chat.message",
                     "error_type": "ValueError",
                     "at": "2026-11-22T10:00:00+00:00"},
    "failures": [],
    "plain": "1 failure in a row; the plugin is still enabled.",
    "reenable_rule": "deliberate enable only",
}

QUICK_REPLY = {
    "id": REPLY_ID,
    "name": "Greet",
    "steps": [{"kind": "message", "role": "user",
               "text": "hello there", "sender": "input_sender"}],
    "scope": "user",
    "chat_id": None,
    "enabled": True,
    "created_at": "2026-11-22T10:00:00+00:00",
    "updated_at": "2026-11-22T10:00:00+00:00",
}

EXPRESSION_SET = {
    "character_id": CHAR_ID,
    "entries": [
        {"name": "neutral", "label": "Neutral", "asset_id": None,
         "notes": ""},
        {"name": "smile", "label": "Smile", "asset_id": None,
         "notes": "warm"},
    ],
    "default": "neutral",
    "created_at": "2026-11-22T10:00:00+00:00",
    "updated_at": "2026-11-22T10:00:00+00:00",
}

SELECTION = {
    "chat_id": CHAT_ID,
    "character_id": CHAR_ID,
    "expression": "smile",
    "selected_at": "2026-11-22T10:05:00+00:00",
    "provenance": {"via": "expression_plugin", "source": "manual",
                   "actor_user_id": "owner", "reason": None,
                   "message_id": None, "previous_expression": "neutral"},
}

HUB_HIT = {
    "id": "hub-1", "owner_id": "owner", "kind": "lorebook_pack",
    "format": "runmal-lorebook-pack", "title": "Gate Lore",
    "locator": "/packs/gate.runmal-pack", "content_sha256": "aa",
    "note": "", "created_at": "2026-11-22T09:00:00+00:00",
    "locator_state": "ready", "matched_fields": ["title"],
    "matched_by": "metadata", "metadata_match": True,
    "content_match": False, "occurrences": None, "excerpt": None,
    "verified_content_sha256": None,
}

HUB_DOC = {
    "query": "gate", "matches": [HUB_HIT], "total_matches": 1,
    "search_state": "matches",
}

WS_HIT = {
    "name": "gate.txt", "kind": "file", "size_bytes": 42,
    "hidden": False, "escapes": False, "path": "notes/gate.txt",
    "matched_by": "both", "name_match": True, "content_match": True,
    "occurrences": 2, "excerpt": "the gate at dusk",
}

WS_DOC = {
    "query": "gate", "matches": [WS_HIT], "total_matches": 1,
    "match_count": 1,
}

CREDENTIAL = {
    "id": CRED_ID,
    "name": "Second Life bridge",
    "scopes": ["chat:read:*", "chat:write:*"],
    "created_at": "2026-11-22T10:00:00+00:00",
    "revoked_at": None,
    "last_used_at": None,
}

SECRET_TOKEN = "rmb_test_token_shown_once"


class FakeEngine:
    """A router-shaped fake: real engine payload shapes, in
    registration order (fixed segments before parameterised)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.replies: dict[str, dict] = {}
        self.sets: dict[str, dict] = {}
        self.credentials: list[dict] = []
        self.variables: dict = {"variables": {}, "flags": {}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path
        assert path.startswith("/api/v1/")
        parts = path[len("/api/v1/"):].split("/")
        body = None
        if request.content:
            import json as jsonlib

            body = jsonlib.loads(request.content)
        self.calls.append(
            {"method": method, "path": path, "json": body,
             "params": dict(request.url.params)}
        )

        # -- backups ---------------------------------------------
        if parts == ["backups"]:
            if method == "POST":
                return httpx.Response(201, json=BACKUP_INFO)
            return httpx.Response(200, json=[BACKUP_LIST_ROW, {
                "name": FULL_INFO["name"], "size_bytes": 9793,
                "modified_at": "2026-11-22T13:19:05+00:00",
            }])
        if parts == ["backups", "full"] and method == "POST":
            return httpx.Response(201, json=FULL_INFO)
        if len(parts) == 4 and parts[:2] == ["backups", "full"] \
                and parts[3] == "stage":
            return httpx.Response(200, json=FULL_STAGE_REPORT)
        if len(parts) == 3 and parts[0] == "backups" \
                and parts[2] == "stage":
            return httpx.Response(200, json={
                **BACKUP_INFO, "name": "restore-20261122T131905.db",
            })
        if parts == ["archive", "import"]:
            return httpx.Response(200, json={
                "ok": True, "archive": body["path"],
                "staged_db": "/staging/runmal.db",
                "staged_root": "/staging",
                "schema_revision": "0042",
                "counts": {"characters": 2}, "checks": [],
                "warnings": [],
            })

        # -- plugins ----------------------------------------------
        if parts == ["plugins", "manager"]:
            return httpx.Response(200, json={
                "installed": [], "rehydration_problems": [],
            })
        if parts == ["plugins", "failure-reports"]:
            return httpx.Response(200, json=[FAILURE_REPORT])
        if parts == ["plugins", "install", "preview"]:
            return httpx.Response(200, json=CARD)
        if parts == ["plugins", "install"]:
            return httpx.Response(201, json={
                "outcome": "installed", "plugin": PLUGIN_DETAIL,
                "manager": {"plugin_id": "quick-replies"},
                "permission_card": CARD,
            })
        if parts == ["plugins"]:
            return httpx.Response(200, json=[PLUGIN])
        if len(parts) >= 2 and parts[0] == "plugins":
            pid = parts[1]
            if len(parts) == 2 and method == "GET":
                return httpx.Response(200, json=PLUGIN_DETAIL)
            if len(parts) == 3 and parts[2] == "permission-card":
                return httpx.Response(200, json=CARD)
            if len(parts) == 3 and parts[2] == "failure-report":
                return httpx.Response(200, json=FAILURE_REPORT)
            if len(parts) == 3 and parts[2] in (
                "enable", "disable", "acknowledge", "update",
            ):
                return httpx.Response(200, json=PLUGIN_DETAIL)
            if len(parts) == 3 and parts[2] == "uninstall":
                return httpx.Response(200, json={
                    "outcome": "uninstalled", "plugin_id": pid,
                    "permission_card": CARD,
                })

        # -- quick replies ------------------------------------------
        if parts == ["quick-replies", "executions"]:
            return httpx.Response(200, json=[{
                "id": "exec-1", "reply_id": REPLY_ID,
                "reply_name": "Greet", "chat_id": CHAT_ID,
                "status": "ok", "steps": [],
            }])
        if parts == ["quick-replies"]:
            if method == "POST":
                reply = {**QUICK_REPLY, "name": body["name"]}
                self.replies[reply["id"]] = reply
                return httpx.Response(201, json=reply)
            return httpx.Response(200, json=list(self.replies.values()))
        if len(parts) >= 2 and parts[0] == "quick-replies":
            rid = parts[1]
            if len(parts) == 3 and parts[2] == "execute":
                return httpx.Response(200, json={
                    "id": "exec-1", "reply_id": rid,
                    "reply_name": "Greet", "chat_id": body["chat_id"],
                    "status": "ok", "steps": [], "variables": {},
                })
            if method == "GET":
                return httpx.Response(200, json=self.replies[rid])
            if method == "PUT":
                reply = {**self.replies[rid], "name": body["name"]}
                self.replies[rid] = reply
                return httpx.Response(200, json=reply)
            if method == "DELETE":
                self.replies.pop(rid, None)
                return httpx.Response(200, json={
                    "deleted": True, "id": rid,
                })

        # -- expressions ---------------------------------------------
        if parts == ["expressions", "current"]:
            return httpx.Response(200, json=SELECTION)
        if parts == ["expressions", "sets"]:
            if method == "POST":
                self.sets[body["character_id"]] = {
                    **EXPRESSION_SET, "character_id": body["character_id"],
                }
                return httpx.Response(201, json=self.sets[body["character_id"]])
            return httpx.Response(200, json=list(self.sets.values()))
        if len(parts) >= 3 and parts[:2] == ["expressions", "sets"]:
            cid = parts[2]
            if len(parts) == 4 and parts[3] == "bindings":
                return httpx.Response(200, json={
                    "character_id": cid, "bindings": [],
                })
            if len(parts) == 4 and parts[3] == "derive":
                return httpx.Response(200, json={
                    **EXPRESSION_SET, "character_id": cid,
                })
            if method == "GET":
                if cid not in self.sets:
                    return httpx.Response(404, json={
                        "detail": "unknown expression set",
                    })
                return httpx.Response(200, json=self.sets[cid])
            if method == "PUT":
                if cid not in self.sets:
                    return httpx.Response(404, json={
                        "detail": "unknown expression set",
                    })
                self.sets[cid] = {**EXPRESSION_SET, "character_id": cid}
                return httpx.Response(200, json=self.sets[cid])
            if method == "DELETE":
                self.sets.pop(cid, None)
                return httpx.Response(200, json={
                    "deleted": True, "character_id": cid,
                })

        # -- chat variables -------------------------------------------
        if parts == ["chat-variables"]:
            return httpx.Response(200, json=self.variables)
        if parts == ["chat-variables", "set"]:
            return httpx.Response(200, json={
                "chat_id": body["chat_id"], "key": body["key"],
                "value": body.get("value"), "flag": body.get("flag"),
            })
        if parts == ["chat-variables", "unset"]:
            return httpx.Response(200, json={"deleted": True})
        if parts == ["chat-variables", "clear"]:
            return httpx.Response(200, json={
                "cleared": True, "chat_id": body["chat_id"],
                "removed": 2,
            })

        # -- library search ---------------------------------------------
        if parts == ["hub", "unified-search"]:
            return httpx.Response(200, json=HUB_DOC)
        if parts == ["workspaces", "unified-search"]:
            return httpx.Response(200, json=WS_DOC)

        # -- bridge admin ------------------------------------------------
        if parts == ["bridge", "credentials"]:
            if method == "POST":
                created = {
                    **CREDENTIAL, "name": body["name"],
                    "scopes": body["scopes"],
                    "token": SECRET_TOKEN,
                }
                self.credentials.append(
                    {k: v for k, v in created.items() if k != "token"}
                )
                return httpx.Response(201, json=created)
            return httpx.Response(200, json=self.credentials)
        if len(parts) == 4 and parts[:2] == ["bridge", "credentials"] \
                and parts[3] == "revoke":
            for cred in self.credentials:
                if cred["id"] == parts[2]:
                    cred["revoked_at"] = "2026-11-22T11:00:00+00:00"
                    return httpx.Response(200, json=cred)
            return httpx.Response(404, json={"detail": "not found"})

        return httpx.Response(404, json={"detail": f"no road {path}"})


def make_client(engine: FakeEngine) -> RunmalClient:
    session = DesktopSession(
        "http://test", **{"bearer" + "_token": TOKEN}
    )
    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    return RunmalClient(session, http=http)


def last_call(engine: FakeEngine, method: str, path: str) -> dict:
    matches = [
        c for c in engine.calls
        if c["method"] == method and c["path"] == path
    ]
    assert matches, f"no {method} {path} in {engine.calls}"
    return matches[-1]


# ------------------------------------------------------------- views


def test_backup_views_from_both_shapes() -> None:
    created = BackupView.from_dict(BACKUP_INFO)
    assert created.kind == "database"
    assert created.schema_revision == "0042"
    assert created.secrets_included is False

    listed = BackupView.from_dict(BACKUP_LIST_ROW)
    assert listed.name == created.name
    assert listed.modified_at.startswith("2026-11-22")
    assert listed.sha256 == ""  # the listing shape carries none

    full = BackupView.from_dict(FULL_INFO)
    assert full.kind == "full" and full.asset_files == 3


def test_plugin_and_failure_views() -> None:
    view = PluginView.from_dict(PLUGIN)
    assert view.id == "quick-replies" and view.state == "enabled"
    assert view.permissions == ["chat.read", "ui.contribute"]

    report = PluginFailureReportView.from_dict(FAILURE_REPORT)
    assert report.total_recorded == 2
    assert report.consecutive_failures == 1
    assert "still enabled" in report.plain


def test_quick_reply_and_expression_views() -> None:
    reply = QuickReplyView.from_dict(QUICK_REPLY)
    assert reply.step_count == 1
    assert reply.first_text == "hello there"
    assert reply.enabled is True

    expr = ExpressionSetView.from_dict(EXPRESSION_SET)
    assert expr.entry_count == 2
    assert expr.entry_names == ["neutral", "smile"]
    assert expr.default == "neutral"


def test_credential_view_never_carries_a_token() -> None:
    poisoned = {**CREDENTIAL, "token": SECRET_TOKEN, "token_hash": "x"}
    view = BridgeCredentialView.from_dict(poisoned)
    assert view.state == "active"
    assert view.label == "Second Life bridge"
    assert not hasattr(view, "token")
    assert SECRET_TOKEN not in repr(view)

    revoked = BridgeCredentialView.from_dict(
        {**CREDENTIAL, "revoked_at": "2026-11-22T11:00:00+00:00"}
    )
    assert revoked.state == "revoked"


def test_library_hit_views_from_both_sources() -> None:
    hub = LibraryHitView.from_hub(HUB_HIT)
    assert hub.source == "hub" and hub.title == "Gate Lore"
    assert hub.locator == "/packs/gate.runmal-pack"
    assert hub.matched_by == "metadata"

    ws = LibraryHitView.from_workspace(WS_HIT)
    assert ws.source == "workspaces" and ws.title == "gate.txt"
    assert ws.locator == "notes/gate.txt"
    assert ws.occurrences == 2 and ws.excerpt == "the gate at dusk"


# ------------------------------------------------------------- words


def test_backup_words() -> None:
    views = [
        BackupView.from_dict(BACKUP_LIST_ROW),
        BackupView.from_dict(FULL_INFO),
    ]
    line = backup_line(views[0])
    assert "database backup" in line and "540" in line
    assert "full backup" in backup_line(views[1])
    words = backups_words(views)
    assert words.startswith("2 backup(s)")
    assert "No backups yet" in backups_words([])

    staged = stage_words({**BACKUP_INFO, "name": "restore-x.db"})
    assert "staged and verified" in staged
    assert "live installation was not touched" in staged
    full = stage_words(FULL_STAGE_REPORT)
    assert "Full backup staged and verified" in full
    assert "characters: 2" in full
    assert "check checksums: ok" in full


def test_plugin_words() -> None:
    assert "Quick Replies" in plugin_line(PluginView.from_dict(PLUGIN))
    detail = plugin_detail_words(PLUGIN_DETAIL)
    assert "User-defined one-tap macros." in detail
    assert "Recorded failures: 1" in detail
    assert "ValueError" in detail

    card = permission_words(CARD)
    assert "chat.read" in card and "RESERVED" in card
    assert "granted set equals the declared set exactly" in card
    assert "reserved in v1" in card

    line = failure_line(PluginFailureReportView.from_dict(FAILURE_REPORT))
    assert "2 recorded failure(s)" in line
    assert failure_line(FAILURE_REPORT) == line  # dicts parse too

    assert "Greet" in quick_reply_line(QuickReplyView.from_dict(QUICK_REPLY))
    expr_line = expression_set_line(
        ExpressionSetView.from_dict(EXPRESSION_SET)
    )
    assert "2 expression(s)" in expr_line and "default: neutral" in expr_line


def test_library_words() -> None:
    results = {
        "hub": [LibraryHitView.from_hub(HUB_HIT)],
        "workspaces": [LibraryHitView.from_workspace(WS_HIT)],
    }
    words = results_words(results)
    assert "hub: 1 hit(s)" in words and "workspaces: 1 hit(s)" in words
    assert "faces" not in words  # no such source exists
    assert "the gate at dusk" in hit_line(
        "workspaces", results["workspaces"][0]
    )
    empty = results_words({"hub": []})
    assert "No matches in the searched sources." in empty


def test_bridge_words_carry_no_token() -> None:
    views = [
        BridgeCredentialView.from_dict(CREDENTIAL),
        BridgeCredentialView.from_dict(
            {**CREDENTIAL, "id": "x", "name": "Old bridge",
             "scopes": ["events:read:*"],
             "revoked_at": "2026-11-22T11:00:00+00:00"}
        ),
    ]
    words = bridge_status_words(views)
    assert "1 active, 1 revoked" in words
    assert "chat:read:*" in words
    assert SECRET_TOKEN not in words
    assert "No bridge credentials" in bridge_status_words([])
    assert "Second Life bridge" in credential_line(views[0])


# ------------------------------------------------------------- flows


def test_backup_flow_requests() -> None:
    engine = FakeEngine()
    flow = BackupFlow(make_client(engine))

    created = flow.create_backup()
    assert created.name == BACKUP_INFO["name"]
    last_call(engine, "POST", "/api/v1/backups")

    full = flow.create_full_backup()
    assert full.kind == "full" and full.asset_files == 3

    listed = flow.list_backups()
    assert [v.kind for v in listed] == ["database", "full"]

    staged = flow.stage_backup(BACKUP_INFO["name"])
    assert staged["name"].startswith("restore-")
    last_call(
        engine, "POST", f"/api/v1/backups/{BACKUP_INFO['name']}/stage"
    )
    report = flow.stage_full_backup(FULL_INFO["name"])
    assert report["ok"] is True

    imported = flow.import_archive("/tmp/x.runmal")
    assert imported["ok"] is True
    call = last_call(engine, "POST", "/api/v1/archive/import")
    assert call["json"] == {"path": "/tmp/x.runmal"}


def test_plugin_flow_requests() -> None:
    engine = FakeEngine()
    flow = PluginFlow(make_client(engine))

    manager = flow.manager()
    assert manager == {"installed": [], "rehydration_problems": []}
    assert [p.id for p in flow.plugins()] == ["quick-replies"]
    assert flow.detail("quick-replies")["name"] == "Quick Replies"
    assert flow.permission_card("quick-replies")["plugin_id"] == "quick-replies"
    assert flow.failure_reports()[0].plugin_id == "quick-replies"
    assert flow.failure_report("quick-replies").total_recorded == 2

    preview = flow.install_preview({"pack": {"id": "x"}})
    assert preview["requires_grant"] is True
    call = last_call(engine, "POST", "/api/v1/plugins/install/preview")
    assert call["json"] == {"pack": {"id": "x"}}

    outcome = flow.install({"pack": {}, "granted_permissions": []})
    assert outcome["outcome"] == "installed"
    updated = flow.update("quick-replies", {"pack": {}})
    assert updated["name"] == "Quick Replies"
    with pytest.raises(ValueError, match="requires the new pack"):
        flow.update("quick-replies")
    assert flow.uninstall("quick-replies")["outcome"] == "uninstalled"
    assert flow.enable("quick-replies")["state"] == "enabled"
    assert flow.disable("quick-replies")["state"] == "enabled"
    assert flow.acknowledge("quick-replies")["state"] == "enabled"


def test_quick_reply_flow_requests() -> None:
    engine = FakeEngine()
    flow = PluginFlow(make_client(engine))

    created = flow.create_quick_reply({"name": "Greet", "text": "hi"})
    assert created.id == REPLY_ID
    assert [r.id for r in flow.quick_replies()] == [REPLY_ID]

    updated = flow.update_quick_reply(REPLY_ID, {"name": "Greet 2"})
    assert updated.name == "Greet 2"
    last_call(engine, "PUT", f"/api/v1/quick-replies/{REPLY_ID}")

    record = flow.execute_quick_reply(REPLY_ID, {"chat_id": CHAT_ID})
    assert record["status"] == "ok" and record["chat_id"] == CHAT_ID
    assert flow.quick_reply_executions()[0]["status"] == "ok"

    assert flow.delete_quick_reply(REPLY_ID) is True
    assert flow.quick_replies() == []


def test_expression_flow_requests_and_save_fallback() -> None:
    engine = FakeEngine()
    flow = PluginFlow(make_client(engine))

    # No set yet: save falls back from the refused PUT to POST.
    saved = flow.save_expression_set(CHAR_ID, {"entries": [], "default": None})
    assert saved.character_id == CHAR_ID
    methods = [c["method"] for c in engine.calls]
    assert methods == ["PUT", "POST"]

    # Now it exists: save is the PUT alone.
    engine.calls.clear()
    flow.save_expression_set(CHAR_ID, {"entries": []})
    assert [c["method"] for c in engine.calls] == ["PUT"]

    assert [s.character_id for s in flow.expression_sets()] == [CHAR_ID]
    assert flow.expression_set(CHAR_ID).entry_count == 2
    assert flow.delete_expression_set(CHAR_ID) is True

    current = flow.expressions_current(CHAT_ID)
    assert current["expression"] == "smile"
    assert flow.expressions_current() == {}  # no chat, no invention
    with pytest.raises(NotFoundError):
        flow.expression_set(CHAR_ID)


def test_chat_variable_flow_requests() -> None:
    engine = FakeEngine()
    flow = PluginFlow(make_client(engine))

    assert flow.chat_variables(CHAT_ID) == {"variables": {}, "flags": {}}
    call = last_call(engine, "GET", "/api/v1/chat-variables")
    assert call["params"] == {"chat_id": CHAT_ID}

    flow.set_chat_variable(CHAT_ID, "mood", value="calm")
    call = last_call(engine, "POST", "/api/v1/chat-variables/set")
    assert call["json"] == {
        "chat_id": CHAT_ID, "key": "mood", "value": "calm",
    }
    flow.set_chat_variable(CHAT_ID, "met", flag=True)
    call = last_call(engine, "POST", "/api/v1/chat-variables/set")
    assert call["json"] == {"chat_id": CHAT_ID, "key": "met", "flag": True}

    assert flow.unset_chat_variable(CHAT_ID, "mood") is True
    assert flow.clear_chat_variables(CHAT_ID)["removed"] == 2


def test_library_search_flow_fan_out() -> None:
    engine = FakeEngine()
    flow = LibrarySearchFlow(make_client(engine))

    results = flow.search("gate")
    assert list(results) == ["hub"]  # workspaces needs a chat
    assert results["hub"][0].title == "Gate Lore"
    call = last_call(engine, "GET", "/api/v1/hub/unified-search")
    assert call["params"] == {"q": "gate"}

    results = flow.search("gate", chat_id=CHAT_ID)
    assert list(results) == ["hub", "workspaces"]
    assert results["workspaces"][0].locator == "notes/gate.txt"
    call = last_call(engine, "GET", "/api/v1/workspaces/unified-search")
    assert call["params"] == {"chat_id": CHAT_ID, "q": "gate"}

    assert flow.search_hub("gate")[0].id == "hub-1"
    assert flow.search_workspaces("gate", CHAT_ID)[0].title == "gate.txt"


def test_bridge_flow_and_token_discipline() -> None:
    engine = FakeEngine()
    flow = BridgeFlow(make_client(engine))

    created = flow.create_credential(
        {"name": "Second Life bridge", "scopes": ["chat:read:*"]}
    )
    # The raw create result is the ONE place the token appears:
    # the caller (the window) shows it once and drops it.
    assert created["token"] == SECRET_TOKEN
    assert created["id"] == CRED_ID

    listed = flow.credentials()
    assert [c.id for c in listed] == [CRED_ID]
    assert all(not hasattr(c, "token") for c in listed)
    assert SECRET_TOKEN not in bridge_status_words(listed)

    revoked = flow.revoke(CRED_ID)
    assert revoked.state == "revoked"
    last_call(
        engine, "POST", f"/api/v1/bridge/credentials/{CRED_ID}/revoke"
    )
