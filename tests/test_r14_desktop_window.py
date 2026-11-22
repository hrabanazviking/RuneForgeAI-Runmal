"""R-14 acceptance (widgets): the Backups, Plugins, Library
Search, and Bridge dialogs over fake flows, and the
MainWindow Tools-menu wiring.

Skips cleanly when PySide6 is absent (R-04 pattern). The
flows here are fakes recording calls; the real flows and
renderers are the sibling crew's ``backups_logic`` /
``plugin_logic`` / ``library_search_logic`` / ``bridge_logic``
deliverables, exercised live after integration. Views are
the client layer's real view classes (BackupView /
PluginView / BridgeCredentialView / …) — exactly what the
dialogs receive in production; the dialogs additionally
read ids through getattr fallbacks, never by concrete type.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.client import (  # noqa: E402
    BackupView,
    BridgeCredentialView,
    ExpressionSetView,
    LibraryHitView,
    PluginFailureReportView,
    PluginView,
    QuickReplyView,
)
from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.window import (  # noqa: E402
    BackupsDialog,
    BridgeDialog,
    LibrarySearchDialog,
    MainWindow,
    PluginsDialog,
)

TOKEN = "tok-shown-once-123"


def backup(filename="backup-1.zip", kind="full"):
    return BackupView(name=filename, kind=kind)


def plugin(plugin_id="plug-1", name="Gate Plugin"):
    return PluginView(
        id=plugin_id, name=name, version="1.0", state="enabled"
    )


def credential(credential_id="cred-1", label="Gate bridge"):
    return BridgeCredentialView(
        id=credential_id, name=label, scopes=["read"]
    )


class FakeBackupFlow:
    def __init__(self):
        self.calls: list = []
        self._backups = [backup(), backup("backup-2.zip", "incremental")]

    def list_backups(self):
        return list(self._backups)

    def create_backup(self):
        self.calls.append(("create_backup",))
        return {"status": "created", "filename": "backup-3.zip"}

    def create_full_backup(self):
        self.calls.append(("create_full_backup",))
        return {"status": "created", "filename": "backup-4.zip"}

    def stage_backup(self, filename):
        self.calls.append(("stage_backup", filename))
        return {"status": "staged", "filename": filename}

    def stage_full_backup(self, filename):
        self.calls.append(("stage_full_backup", filename))
        return {"status": "staged", "filename": filename}

    def import_archive(self, path):
        self.calls.append(("import_archive", path))
        return {"status": "imported", "path": path}


class FakePluginFlow:
    def __init__(self):
        self.calls: list = []
        self._plugins = [plugin(), plugin("plug-2", "Second Plugin")]
        self._quick_replies = [
            QuickReplyView(
                id="qr-1", name="Hello",
                steps=[{"kind": "message", "text": "Hello there"}],
            )
        ]
        self._expression_sets = [
            ExpressionSetView(
                character_id="char-1", entries=[{"name": "smile"}]
            )
        ]
        self._failures = [
            PluginFailureReportView(
                plugin_id="plug-2", state="self-disabled",
                plain="blew up",
            )
        ]

    def manager(self):
        return {"plugins_installed": 2}

    def plugins(self):
        return list(self._plugins)

    def detail(self, plugin_id):
        self.calls.append(("detail", plugin_id))
        return {"plugin_id": plugin_id, "name": "Gate Plugin"}

    def permission_card(self, plugin_id):
        self.calls.append(("permission_card", plugin_id))
        return {
            "plugin_id": plugin_id,
            "permissions": ["filesystem.read"],
        }

    def failure_reports(self):
        return list(self._failures)

    def install_preview(self, payload):
        self.calls.append(("install_preview", payload))
        return {"verdict": "safe to install"}

    def install(self, payload):
        self.calls.append(("install", payload))
        return {"status": "installed"}

    def update(self, plugin_id):
        self.calls.append(("update", plugin_id))
        return {"status": "updated"}

    def uninstall(self, plugin_id):
        self.calls.append(("uninstall", plugin_id))
        return {"status": "uninstalled"}

    def enable(self, plugin_id):
        self.calls.append(("enable", plugin_id))
        return {"status": "enabled"}

    def disable(self, plugin_id):
        self.calls.append(("disable", plugin_id))
        return {"status": "disabled"}

    def acknowledge(self, plugin_id):
        self.calls.append(("acknowledge", plugin_id))
        return {"status": "acknowledged"}

    def quick_replies(self):
        return list(self._quick_replies)

    def create_quick_reply(self, payload):
        self.calls.append(("create_quick_reply", payload))
        return {"status": "created"}

    def update_quick_reply(self, reply_id, payload):
        self.calls.append(("update_quick_reply", reply_id, payload))
        return {"status": "updated"}

    def delete_quick_reply(self, reply_id):
        self.calls.append(("delete_quick_reply", reply_id))
        return {"status": "deleted"}

    def execute_quick_reply(self, reply_id, payload=None):
        self.calls.append(("execute_quick_reply", reply_id, payload))
        return {"status": "executed"}

    def expression_sets(self):
        return list(self._expression_sets)

    def expression_set(self, character_id):
        self.calls.append(("expression_set", character_id))
        return {"character_id": character_id, "expressions": ["smile"]}

    def save_expression_set(self, character_id, payload):
        self.calls.append(("save_expression_set", character_id, payload))
        return {"status": "saved"}

    def delete_expression_set(self, character_id):
        self.calls.append(("delete_expression_set", character_id))
        return {"status": "deleted"}

    def expressions_current(self):
        return {"character_id": "char-1", "expression": "smile"}


class FakeLibrarySearchFlow:
    def __init__(self):
        self.calls: list = []

    def search(self, query):
        self.calls.append(("search", query))
        return {
            "hub": [LibraryHitView(source="hub", title="Gate Card")],
            "workspaces": [],
            "faces": [LibraryHitView(source="faces", title="Gate Face")],
        }


class FakeBridgeFlow:
    def __init__(self):
        self.calls: list = []
        self._credentials = [credential()]

    def credentials(self):
        return list(self._credentials)

    def create_credential(self, payload):
        self.calls.append(("create_credential", payload))
        return {"credential_id": "cred-2", "token": TOKEN}

    def revoke(self, credential_id):
        self.calls.append(("revoke", credential_id))
        return {"status": "revoked"}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------- backups


def test_backups_dialog_populates_and_creates(qapp) -> None:
    flow = FakeBackupFlow()
    dialog = BackupsDialog(None, flow)
    dialog.show()
    try:
        assert dialog.backups_list.count() == 2
        assert "does NOT overwrite the live data" in (
            dialog.STAGING_NOTE
        )
        dialog._create_backup(full=False)
        assert ("create_backup",) in flow.calls
        dialog._create_backup(full=True)
        assert ("create_full_backup",) in flow.calls
    finally:
        dialog.close()


def test_backups_stage_calls_flow_with_selected_filename(qapp) -> None:
    flow = FakeBackupFlow()
    dialog = BackupsDialog(None, flow)
    dialog.show()
    try:
        dialog._confirm = lambda _title, _text: True
        dialog.backups_list.setCurrentRow(1)
        dialog._stage_backup(full=False)
        assert ("stage_backup", "backup-2.zip") in flow.calls
        assert "NOT overwritten" in dialog.status_label.text()
        dialog.backups_list.setCurrentRow(0)
        dialog._stage_backup(full=True)
        assert ("stage_full_backup", "backup-1.zip") in flow.calls
        assert dialog.detail_text.toPlainText() != ""
    finally:
        dialog.close()


def test_backups_import_dispatches_chosen_path(qapp) -> None:
    flow = FakeBackupFlow()
    dialog = BackupsDialog(None, flow)
    dialog.show()
    try:
        dialog._confirm = lambda _title, _text: True
        import runmal.desktop.window as window_module

        original = window_module.QFileDialog.getOpenFileName
        window_module.QFileDialog.getOpenFileName = staticmethod(
            lambda *_a, **_k: ("/tmp/archive.zip", "")
        )
        try:
            dialog._import_archive()
        finally:
            window_module.QFileDialog.getOpenFileName = original
        assert ("import_archive", "/tmp/archive.zip") in flow.calls
    finally:
        dialog.close()


# ------------------------------------------------------------- plugins


def test_plugins_manager_detail_and_dispatch(qapp) -> None:
    flow = FakePluginFlow()
    dialog = PluginsDialog(None, flow)
    dialog.show()
    try:
        assert dialog.tabs.count() == 4
        assert dialog.plugins_list.count() == 2
        dialog.plugins_list.setCurrentRow(0)
        dialog._show_plugin_detail()
        assert ("detail", "plug-1") in flow.calls
        assert ("permission_card", "plug-1") in flow.calls
        # The detail pane renders the detail + permission words.
        assert dialog.plugin_detail_text.toPlainText() != ""
        dialog._plugin_action("enable")
        assert ("enable", "plug-1") in flow.calls
        dialog._plugin_action("disable")
        assert ("disable", "plug-1") in flow.calls
        dialog._plugin_action("update")
        assert ("update", "plug-1") in flow.calls
        dialog._plugin_action("acknowledge")
        assert ("acknowledge", "plug-1") in flow.calls
    finally:
        dialog.close()


def test_plugins_uninstall_behind_confirm(qapp) -> None:
    flow = FakePluginFlow()
    dialog = PluginsDialog(None, flow)
    dialog.show()
    try:
        dialog.plugins_list.setCurrentRow(0)
        dialog._confirm = lambda _title, _text: False
        dialog._uninstall_plugin()
        assert ("uninstall", "plug-1") not in flow.calls
        dialog._confirm = lambda _title, _text: True
        dialog._uninstall_plugin()
        assert ("uninstall", "plug-1") in flow.calls
    finally:
        dialog.close()


def test_plugins_install_preview_then_install(qapp) -> None:
    flow = FakePluginFlow()
    dialog = PluginsDialog(None, flow)
    dialog.show()
    try:
        dialog._confirm = lambda _title, _text: True
        dialog.install_source_edit.setText("/tmp/gate-plugin")
        dialog._install_preview()
        preview = flow.calls[-1]
        assert preview[0] == "install_preview"
        assert preview[1]["source"] == "/tmp/gate-plugin"
        assert "safe to install" in dialog.install_result_text.toPlainText()
        dialog._install()
        installs = [call for call in flow.calls if call[0] == "install"]
        assert installs == [
            (
                "install",
                {"source": "/tmp/gate-plugin", "path": "/tmp/gate-plugin"},
            )
        ]
    finally:
        dialog.close()


def test_quick_reply_create_and_execute(qapp) -> None:
    flow = FakePluginFlow()
    dialog = PluginsDialog(None, flow)
    dialog.show()
    try:
        assert dialog.quick_replies_list.count() == 1
        dialog.qr_name_edit.setText("Wave")
        dialog.qr_text_edit.setPlainText("waves hello")
        dialog._create_quick_reply()
        assert (
            "create_quick_reply",
            {"name": "Wave", "text": "waves hello"},
        ) in flow.calls
        dialog.quick_replies_list.setCurrentRow(0)
        dialog._execute_quick_reply()
        assert ("execute_quick_reply", "qr-1", None) in flow.calls
    finally:
        dialog.close()


def test_plugins_expressions_and_failures(qapp) -> None:
    flow = FakePluginFlow()
    dialog = PluginsDialog(None, flow)
    dialog.show()
    try:
        assert dialog.expression_sets_list.count() == 1
        assert "smile" in dialog.expression_current_text.toPlainText()
        dialog.expression_sets_list.setCurrentRow(0)
        dialog._show_expression_set()
        assert ("expression_set", "char-1") in flow.calls
        assert dialog.failures_list.count() == 1
        dialog.failures_list.setCurrentRow(0)
        dialog._show_failure_detail()
        assert dialog.failure_detail_text.toPlainText() != ""
    finally:
        dialog.close()


# ------------------------------------------------------ library search


def test_library_search_renders_grouped_results(qapp) -> None:
    flow = FakeLibrarySearchFlow()
    dialog = LibrarySearchDialog(None, flow)
    dialog.show()
    try:
        dialog.query_edit.setText("gate")
        dialog._search()
        assert ("search", "gate") in flow.calls
        texts = [
            dialog.results_list.item(i).text()
            for i in range(dialog.results_list.count())
        ]
        # Grouped by source: a header per non-empty source plus
        # one row per hit (hub 1, faces 1; workspaces empty).
        assert any(text.startswith("hub") for text in texts)
        assert any(text.startswith("faces") for text in texts)
        assert dialog.results_list.count() == 4
        assert dialog.summary_label.text() != ""
    finally:
        dialog.close()


# -------------------------------------------------------------- bridge


def test_bridge_create_shows_token_once_and_revoke(qapp) -> None:
    flow = FakeBridgeFlow()
    dialog = BridgeDialog(None, flow)
    dialog.show()
    try:
        assert dialog.credentials_list.count() == 1
        assert dialog.summary_text.toPlainText() != ""
        assert dialog.token_field.text() == ""
        dialog.credential_label_edit.setText("Phone bridge")
        dialog.credential_scopes_edit.setText("read, write")
        dialog._create_credential()
        assert (
            "create_credential",
            {"label": "Phone bridge", "scopes": ["read", "write"]},
        ) in flow.calls
        # The token lives ONLY in the one-time field.
        assert dialog.token_field.text() == TOKEN
        assert TOKEN not in dialog.status_label.text()
        assert TOKEN not in dialog.summary_text.toPlainText()
        dialog._confirm = lambda _title, _text: True
        dialog.credentials_list.setCurrentRow(0)
        dialog._revoke_credential()
        assert ("revoke", "cred-1") in flow.calls
        assert dialog.token_field.text() == ""
    finally:
        dialog.close()


# ---------------------------------------------------- window wiring


class FakeClient:
    def new_request_id(self):
        return "req-r14"

    def list_presets(self):
        return []


def test_mainwindow_r14_wiring(qapp) -> None:
    window = MainWindow(EngineHandle(), client=FakeClient())
    window._backups_flow_instance = FakeBackupFlow()
    window._plugins_flow_instance = FakePluginFlow()
    window._library_search_flow_instance = FakeLibrarySearchFlow()
    window._bridge_flow_instance = FakeBridgeFlow()
    window.show()
    try:
        assert window.action_backups.text() == "Backups & Data…"
        assert window.action_plugins.text() == "Plugins…"
        assert window.action_library_search.text() == "Library Search…"
        assert window.action_bridge.text() == "Bridge…"
        backups = window.open_backups_dialog()
        assert isinstance(backups, BackupsDialog)
        backups.close()
        plugins = window.open_plugins_dialog()
        assert isinstance(plugins, PluginsDialog)
        plugins.close()
        search = window.open_library_search_dialog()
        assert isinstance(search, LibrarySearchDialog)
        search.close()
        bridge = window.open_bridge_dialog()
        assert isinstance(bridge, BridgeDialog)
        bridge.close()
    finally:
        window.close()
