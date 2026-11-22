"""R-14 acceptance (live): the backups / plugins / library
search / bridge flows against the real engine, in-process.

Fresh-engine plugin truth (probed 2026-11-22 against a clean
``RUNMAL_DATA_DIR``): ``GET /plugins/manager`` answers
``{"installed": [], "rehydration_problems": []}`` and
``GET /plugins`` answers ``[]`` — a fresh engine registers NO
plugins, so there is no plugin to toggle. The plugin test below
asserts that empty state explicitly (it is the truth, not a
skip); the enable/disable verbs are proven over the fake
transport in the logic battery, and against a real plugin the
day a fresh engine ships one.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from runmal.desktop.backups_logic import BackupFlow, backups_words
from runmal.desktop.bridge_logic import BridgeFlow, bridge_status_words
from runmal.desktop.client import DesktopSession, NotFoundError, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.library_search_logic import LibrarySearchFlow
from runmal.desktop.plugin_logic import PluginFlow


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> Iterator[EngineHandle]:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    try:
        yield handle
    finally:
        handle.stop()


def make_client(engine: EngineHandle) -> RunmalClient:
    session = DesktopSession.from_local_credential(engine.base_url)
    return RunmalClient(session)


def test_backup_create_list_stage(engine: EngineHandle) -> None:
    flow = BackupFlow(make_client(engine))

    assert flow.list_backups() == []

    created = flow.create_backup()
    assert created.kind == "database"
    assert created.sha256 and created.schema_revision
    assert created.secrets_included is False

    listed = flow.list_backups()
    assert [b.name for b in listed] == [created.name]
    assert listed[0].size_bytes == created.size_bytes
    assert created.name in backups_words(listed)

    staged = flow.stage_backup(created.name)
    assert staged["sha256"] == created.sha256
    assert staged["schema_revision"] == created.schema_revision
    assert staged["name"].startswith("restore-")


def test_full_backup_create_stage(engine: EngineHandle) -> None:
    flow = BackupFlow(make_client(engine))

    created = flow.create_full_backup()
    assert created.kind == "full"
    assert created.asset_files == 0  # a fresh engine has no assets
    assert created.secrets_included is False

    # Engine truth: GET /backups lists database backups only
    # (its filename law matches runmal-backup-*.db) — a full
    # bundle is staged by the name the create road returned,
    # never discovered through the listing.
    assert flow.list_backups() == []

    report = flow.stage_full_backup(created.name)
    assert report["ok"] is True
    assert report["schema_revision"] == created.schema_revision
    checks = {c["name"]: c["ok"] for c in report["checks"]}
    assert checks["checksums"] is True
    assert checks["database_integrity"] is True
    assert report["counts"]["characters"] == 0


def test_plugin_surface_on_a_fresh_engine(engine: EngineHandle) -> None:
    flow = PluginFlow(make_client(engine))

    manager = flow.manager()
    assert manager == {"installed": [], "rehydration_problems": []}

    # The fresh-engine truth, asserted — not skipped: no plugin
    # is registered, so no enable/disable toggle exists to make.
    assert flow.plugins() == []
    assert flow.failure_reports() == []
    with pytest.raises(NotFoundError):
        flow.detail("quick-replies")


def test_quick_reply_and_expression_round_trips(
    engine: EngineHandle,
) -> None:
    client = make_client(engine)
    flow = PluginFlow(client)
    chat = client.create_chat(title="R-14 stage")
    character = client.create_character(
        {"name": "Expr"}, name="Expr"
    )

    reply = flow.create_quick_reply(
        {"name": "Greet", "text": "hello there"}
    )
    assert reply.enabled is True and reply.step_count == 1
    assert [r.id for r in flow.quick_replies()] == [reply.id]

    updated = flow.update_quick_reply(
        reply.id, {"name": "Greet", "text": "hello again"}
    )
    assert updated.first_text == "hello again"

    record = flow.execute_quick_reply(reply.id, {"chat_id": chat.id})
    assert record["status"] == "ok"
    messages = client.list_chat_messages(chat.id)
    assert any(m.content == "hello again" for m in messages)
    assert flow.quick_reply_executions()

    assert flow.delete_quick_reply(reply.id) is True
    assert flow.quick_replies() == []

    saved = flow.save_expression_set(
        character.id,
        {
            "character_id": character.id,
            "entries": [
                {"name": "neutral", "label": "Neutral",
                 "asset_id": None, "notes": ""},
            ],
            "default": "neutral",
        },
    )
    assert saved.character_id == character.id
    assert saved.entry_names == ["neutral"]
    assert [s.character_id for s in flow.expression_sets()] == [
        character.id
    ]

    # Nothing was ever selected for this chat: the engine 404s
    # and the flow surfaces that absence honestly.
    with pytest.raises(NotFoundError):
        flow.expressions_current(chat.id)

    assert flow.delete_expression_set(character.id) is True
    assert flow.expression_sets() == []


def test_library_search_structured_per_source(
    engine: EngineHandle,
) -> None:
    flow = LibrarySearchFlow(make_client(engine))

    results = flow.search("gate")
    # Only the hub has an owner-wide search route; the fresh
    # hub is empty and says so with an empty list, honestly.
    assert results == {"hub": []}
    assert "faces" not in results  # no faces search route exists

    hits = flow.search_hub("gate")
    assert hits == []


def test_bridge_credential_lifecycle(engine: EngineHandle) -> None:
    client = make_client(engine)
    flow = BridgeFlow(client)

    assert flow.credentials() == []

    created = flow.create_credential(
        {"name": "R-14 probe", "scopes": ["chat:read:*"]}
    )
    token = created["token"]
    assert token.startswith("rmb_")
    assert created["name"] == "R-14 probe"
    assert created["scopes"] == ["chat:read:*"]

    listed = flow.credentials()
    assert [c.id for c in listed] == [created["id"]]
    view = listed[0]
    assert view.state == "active"
    assert view.scopes == ["chat:read:*"]
    # The list payload (and everything built from it) must not
    # carry the token — INV-023.
    raw_list = client._request("GET", "/api/v1/bridge/credentials")
    assert all("token" not in row for row in raw_list)
    assert token not in bridge_status_words(listed)
    assert token not in repr(view)

    revoked = flow.revoke(created["id"])
    assert revoked.state == "revoked"
    assert revoked.revoked_at
    assert flow.credentials()[0].state == "revoked"
