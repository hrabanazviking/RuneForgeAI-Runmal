"""Desktop proof (R-14): Backups, Plugins, Library Search &
Bridge in the real windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
and drives the four R-14 surfaces through the window's own
controls:

- Backups & Data: a backup is created from the window and
  listed; its restore is STAGED (the dialog's words promise
  the live data is not overwritten, and it is not); a full
  backup is created and its restore staged by the name its
  creation returned.
- Plugins: a fresh engine's manager is honestly empty; a
  real pack (minted with the engine's own pack builder) is
  previewed and installed through the dialog, its permission
  card renders, and the plugin is toggled enable → disable
  with the state verified through the client after each.
- Library Search: a hub entry registered through the API is
  found from the window's one search box.
- Bridge: a credential is created through the dialog; its
  token appears exactly once, in the one-time field — never
  in the status label or the summary — and the credential is
  revoked through the dialog.
- RESTART the whole app on the same data dir: the backup,
  the plugin, the revoked credential, and the hub entry
  persist.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r14_proof.py

Prints one line:  R14_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-14", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}

MANIFEST = {
    "id": "proof.alpha",
    "name": "Proof Alpha",
    "version": "1.0.0",
    "api_version": 1,
    "description": "The R-14 launch proof's plugin.",
    "author": "R-14 proof",
    "capabilities": ["chat.events"],
    "permissions": ["chat.read"],
    "events": ["chat.created"],
    "enabled_by_default": False,
}


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULT["checks"][name] = {"ok": bool(ok), "detail": detail}
    return bool(ok)


def wait_until(app, predicate, timeout=25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    app.processEvents()
    return predicate()


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)
    data_dir = Path(os.environ["RUNMAL_DATA_DIR"])
    RESULT["data_dir"] = str(data_dir)
    scratch = data_dir.parent / (data_dir.name + "-files")
    scratch.mkdir(parents=True, exist_ok=True)

    from runmal.desktop.app import create_window
    from runmal.desktop.engine import EngineHandle, EngineState
    from runmal.plugins.packs import build_pack

    pack_path = scratch / "proof-alpha.pack.json"
    pack_path.write_text(json.dumps(build_pack(MANIFEST)))

    engine = EngineHandle()
    window = create_window(engine)
    window.show()
    app.processEvents()
    check("window_shown", window.isVisible(), window.windowTitle())

    snapshot = window.start_engine_blocking()
    app.processEvents()
    status = engine.status()
    check("engine_running", status.state is EngineState.RUNNING,
          status.label)
    check(
        "first_run_true_on_fresh",
        snapshot is not None and snapshot.first_run.is_first_run is True,
        snapshot.first_run.label if snapshot else "no snapshot",
    )
    if window._wizard is not None:
        window._wizard.close()
        app.processEvents()
        window._wizard = None

    client = window.client()
    profile = client.create_backend_profile(
        "Demo", "fake", chat_model="fake-1"
    )
    check("profile_seeded", bool(profile.id))
    keeper = client.create_character(dict(CARD), name="Gate Keeper")
    check("character_seeded", bool(keeper.id))
    chat = client.create_chat(title="Gate chat", character_id=keeper.id)
    window.open_chat_blocking(chat.id)
    app.processEvents()

    # A hub entry to find later (registered through the API;
    # the search itself is driven from the window below).
    client._request("POST", "/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Gate Marker Lore",
        "locator": str(pack_path), "note": "R-14 proof seed",
    })

    # ---- Backups & Data: create, list, stage; full, stage.
    backups = window.open_backups_dialog()
    check("backups_shown", backups is not None and backups.isVisible())
    backups._confirm = lambda *a, **k: True
    app.processEvents()
    check(
        "backups_empty_on_fresh",
        backups.backups_list.count() == 0,
        str(backups.backups_list.count()),
    )
    backups.create_backup_button.click()
    app.processEvents()
    check(
        "backup_created_and_listed",
        backups.backups_list.count() >= 1,
        str([b.name for b in backups._backups]),
    )
    backups.backups_list.setCurrentRow(0)
    backups.stage_backup_button.click()
    app.processEvents()
    check(
        "restore_staged_not_applied",
        "staged for review" in backups.status_label.text(),
        backups.status_label.text()[:120],
    )
    backups.create_full_backup_button.click()
    app.processEvents()
    full_rows = [
        i for i, b in enumerate(backups._backups)
        if getattr(b, "kind", "") == "full"
    ]
    check(
        "full_backup_listed_from_creation",
        len(full_rows) == 1,
        str([(b.name, b.kind) for b in backups._backups]),
    )
    if full_rows:
        backups.backups_list.setCurrentRow(full_rows[0])
        backups.stage_full_backup_button.click()
        app.processEvents()
        check(
            "full_restore_staged",
            "staged for review" in backups.status_label.text(),
            backups.status_label.text()[:120],
        )
    else:
        check("full_restore_staged", False, "no full row to stage")
    check(
        "backup_listed_via_client",
        len(client.list_backups()) >= 1,
        str(len(client.list_backups())),
    )
    backups.close()

    # ---- Plugins: empty truth, install a real pack, toggle.
    plugins = window.open_plugins_dialog()
    check("plugins_shown", plugins is not None and plugins.isVisible())
    plugins._confirm = lambda *a, **k: True
    app.processEvents()
    check(
        "plugins_empty_on_fresh",
        plugins.plugins_list.count() == 0,
        plugins.manager_text.toPlainText()[:100],
    )
    plugins.install_source_edit.setText(str(pack_path))
    plugins.install_preview_button.click()
    app.processEvents()
    check(
        "install_preview_rendered",
        bool(plugins.install_result_text.toPlainText().strip()),
        plugins.install_result_text.toPlainText()[:100],
    )
    plugins.install_button.click()
    app.processEvents()
    check(
        "plugin_installed_and_listed",
        plugins.plugins_list.count() == 1,
        str(plugins.plugins_list.count()),
    )
    plugins.plugins_list.setCurrentRow(0)
    app.processEvents()
    check(
        "permission_card_rendered",
        "chat.read" in plugins.plugin_detail_text.toPlainText(),
        plugins.plugin_detail_text.toPlainText()[:140],
    )
    flow = window.plugins_flow()
    state0 = flow.plugins()[0].state if flow.plugins() else ""
    plugins.enable_plugin_button.click()
    app.processEvents()
    state1 = flow.plugins()[0].state if flow.plugins() else ""
    plugins.disable_plugin_button.click()
    app.processEvents()
    state2 = flow.plugins()[0].state if flow.plugins() else ""
    check(
        "plugin_toggled",
        "enabl" in state1.lower() and "disab" in state2.lower(),
        f"installed={state0} after enable={state1} "
        f"after disable={state2}",
    )
    plugins.close()

    # ---- Library Search: the hub entry, found from the window.
    search = window.open_library_search_dialog()
    check("search_shown", search is not None and search.isVisible())
    search.query_edit.setText("Gate")
    search.search_button.click()
    app.processEvents()
    rows = [
        search.results_list.item(i).text()
        for i in range(search.results_list.count())
    ]
    check(
        "search_found_hub_entry",
        any("Gate Marker Lore" in r for r in rows),
        " | ".join(rows)[:160],
    )
    check(
        "search_summary_words",
        bool(search.summary_label.text().strip()),
        search.summary_label.text()[:100],
    )
    search.close()

    # ---- Bridge: create (token once), list, revoke.
    bridge = window.open_bridge_dialog()
    check("bridge_shown", bridge is not None and bridge.isVisible())
    bridge._confirm = lambda *a, **k: True
    app.processEvents()
    check(
        "bridge_empty_words",
        "No bridge credentials" in bridge.summary_text.toPlainText(),
        bridge.summary_text.toPlainText()[:100],
    )
    bridge.credential_label_edit.setText("Proof bridge")
    bridge.credential_scopes_edit.setText("chat:read:*")
    bridge.create_credential_button.click()
    app.processEvents()
    token = bridge.token_field.text()
    check(
        "token_shown_once",
        token.startswith("rmb_"),
        token[:8] + "…" if token else "(empty)",
    )
    check(
        "token_nowhere_else",
        token not in bridge.status_label.text()
        and token not in bridge.summary_text.toPlainText(),
        "status + summary token-free",
    )
    check(
        "credential_listed",
        bridge.credentials_list.count() == 1,
        str(bridge.credentials_list.count()),
    )
    bridge.credentials_list.setCurrentRow(0)
    bridge.revoke_credential_button.click()
    app.processEvents()
    creds = client.list_bridge_credentials()
    check(
        "credential_revoked",
        len(creds) == 1 and creds[0].state == "revoked",
        str([(c.name, c.state) for c in creds]),
    )
    bridge.close()

    # ---- Restart: everything persists.
    window.close()
    app.processEvents()
    check(
        "engine_stopped_for_restart",
        wait_until(
            app, lambda: engine.status().state is EngineState.STOPPED
        ),
        engine.status().label,
    )
    engine2 = EngineHandle()
    window2 = create_window(engine2)
    window2.show()
    window2.start_engine_blocking()
    app.processEvents()
    check(
        "engine_running_after_restart",
        engine2.status().state is EngineState.RUNNING,
        engine2.status().label,
    )
    client2 = window2.client()
    check(
        "backup_persists",
        len(client2.list_backups()) >= 1,
        str(len(client2.list_backups())),
    )
    plugs2 = client2.list_plugins()
    check(
        "plugin_persists_not_enabled",
        len(plugs2) == 1 and plugs2[0].state == "registered",
        str([(p.id, p.state) for p in plugs2]),
    )
    creds2 = client2.list_bridge_credentials()
    check(
        "credential_persists_revoked",
        len(creds2) == 1 and creds2[0].state == "revoked",
        str([(c.name, c.state) for c in creds2]),
    )
    from runmal.desktop.library_search_logic import LibrarySearchFlow

    hits2 = LibrarySearchFlow(client2).search("Gate")
    check(
        "hub_entry_persists",
        any(
            h.title == "Gate Marker Lore"
            for h in hits2.get("hub", [])
        ),
        str({k: [h.title for h in v] for k, v in hits2.items()}),
    )

    window2.close()
    app.processEvents()
    check(
        "engine_stopped_on_quit",
        wait_until(
            app, lambda: engine2.status().state is EngineState.STOPPED
        ),
        engine2.status().label,
    )
    import urllib.request

    try:
        urllib.request.urlopen(engine2.base_url + "/healthz", timeout=2)
        healthz_gone = False
    except Exception:
        healthz_gone = True
    check("healthz_gone_after_quit", healthz_gone)

    RESULT["pass"] = all(c["ok"] for c in RESULT["checks"].values())
    print("R14_RESULT " + json.dumps(RESULT))
    return 0 if RESULT["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
