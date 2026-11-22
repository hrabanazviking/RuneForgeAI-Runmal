"""R-13 acceptance (widgets): the Voice and Vision dialogs
over fake flows, the MainWindow Tools-menu wiring, and the
composer image attach (pending cleared on a landed
attachment, kept — with words — on an attach failure).

Skips cleanly when PySide6 is absent (R-04 pattern). The
flows here are fakes recording calls; the real flows and
client views are the sibling crew's ``voice_logic`` /
``vision_logic`` / ``client`` deliverables, exercised live
in scripts/desktop_r13_proof.py after integration.
"""

import dataclasses
import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.chat_logic import (  # noqa: E402
    OpenChat,
    StreamDraft,
    message_list_label,
    transcript_html,
)
from runmal.desktop.client.models import (  # noqa: E402
    ChatSummary,
    MessageView,
    VisionAttachmentView,
    VisionDescriptionView,
    VisionProviderView,
    VoiceBackendView,
    VoiceDeviceView,
    VoiceSessionView,
    WatchFolderView,
)
from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.window import (  # noqa: E402
    MainWindow,
    VisionDialog,
    VoiceDialog,
)

CHATS = [ChatSummary(id="chat-1", title="Gate chat")]

# A 1x1 transparent PNG.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c63000100000500010d0a2db4000000"
    "0049454e44ae426082"
)


def make_view(cls, **kwargs):
    """Build a client view tolerantly: pass the named fields,
    fill any other required field with a plain empty value —
    the views' exact field sets are the sibling deliverable."""
    values = {}
    for field in dataclasses.fields(cls):
        if field.name in kwargs:
            values[field.name] = kwargs[field.name]
        elif field.default is not dataclasses.MISSING:
            continue
        elif field.default_factory is not dataclasses.MISSING:
            continue
        else:
            annotation = str(field.type)
            if "int" in annotation:
                values[field.name] = 0
            elif "bool" in annotation:
                values[field.name] = False
            elif "list" in annotation:
                values[field.name] = []
            elif "dict" in annotation:
                values[field.name] = {}
            else:
                values[field.name] = ""
    return cls(**values)


def mic():
    return make_view(
        VoiceDeviceView,
        device_id="mic-1",
        name="Gate Mic",
        direction="input",
        host_api="fixture",
        max_channels=1,
        sample_rates=(16000,),
        is_system_default=True,
    )


def speaker():
    return make_view(
        VoiceDeviceView,
        device_id="spk-1",
        name="Gate Speakers",
        direction="output",
        host_api="fixture",
        max_channels=2,
        sample_rates=(16000,),
        is_system_default=False,
    )


class FakeVoiceFlow:
    def __init__(self):
        self.calls: list = []
        self._devices = [mic(), speaker()]
        self._roles = {
            "assignments": {
                "user_mic": {
                    "device_id": "mic-1",
                    "name": "Gate Mic",
                    "host_api": "fixture",
                }
            },
            "resolution": {
                "user_mic": {
                    "status": "ok",
                    "device_id": "mic-1",
                    "saved": {"device_id": "mic-1"},
                },
                "user_playback": {
                    "status": "unassigned",
                    "device_id": None,
                    "saved": None,
                },
            },
        }
        self._session = make_view(
            VoiceSessionView,
            session_id="sess-1",
            chat_id="chat-1",
            state="active",
            turn_count=2,
        )

    def status(self):
        return {"state": "ready", "sessions_active": 1}

    def device_provider(self):
        return "fixture"

    def devices(self):
        return list(self._devices)

    def roles(self):
        return self._roles

    def assign_role(self, role, device_id):
        self.calls.append(("assign_role", role, device_id))
        return self._roles

    def backends(self):
        return {
            "tts": [
                make_view(
                    VoiceBackendView,
                    key="tts-a",
                    kind="tts",
                    display_name="TTS A",
                    installed=True,
                    selected=True,
                    installable=False,
                ),
                make_view(
                    VoiceBackendView,
                    key="tts-b",
                    kind="tts",
                    display_name="TTS B",
                    installed=False,
                    selected=False,
                    installable=True,
                ),
            ],
            "stt": [
                make_view(
                    VoiceBackendView,
                    key="stt-a",
                    kind="stt",
                    display_name="STT A",
                    installed=True,
                    selected=True,
                    installable=False,
                )
            ],
        }

    def install_backend(self, kind, key):
        self.calls.append(("install_backend", kind, key))
        return {"status": "refused", "error": "no installer for this host"}

    def defaults(self):
        return {"tts_backend": "tts-a", "stt_backend": "stt-a"}

    def set_defaults(self, tts_backend=None, stt_backend=None):
        self.calls.append(("set_defaults", tts_backend, stt_backend))
        return {"status": "saved"}

    def sessions(self, chat_id=""):
        self.calls.append(("sessions", chat_id))
        # The real flow's envelope (client.list_voice_sessions).
        return {
            "sessions": [self._session],
            "active_session_id": self._session.session_id,
        }

    def start_session(self, chat_id, auto_project=False):
        self.calls.append(("start_session", chat_id, auto_project))
        return self._session

    def stop_session(self, session_id, note=""):
        self.calls.append(("stop_session", session_id))
        return {"status": "stopped"}

    def session_detail(self, session_id):
        return {"session_id": session_id, "state": "active"}

    def session_latency(self, session_id):
        return {"session_id": session_id, "last_ms": 42}

    def live(self, session_id):
        return {"state": "active", "session_id": session_id}


class FakeVisionFlow:
    def __init__(self):
        self.calls: list = []
        self._attachment = make_view(
            VisionAttachmentView,
            id="att-1",
            filename="cat.png",
            image_format="png",
            image_width=10,
            image_height=8,
        )
        self._description = make_view(
            VisionDescriptionView, id="desc-1"
        )
        self._watch = make_view(
            WatchFolderView,
            id="watch-1",
            path="/tmp/pics",
            recursive=True,
            enabled=True,
        )

    def providers(self):
        # The real flow's envelope (client.vision_providers):
        # views under "providers", the semantic note beside them.
        return {
            "providers": [
                make_view(
                    VisionProviderView,
                    provider_id="pv1",
                    model="Local Vision",
                    road="metadata",
                    available=True,
                )
            ],
            "semantic_caption_note": (
                "No semantic caption provider exists in-tree."
            ),
            "backends": [],
        }

    def chat_descriptions(self, chat_id):
        return [self._description]

    def history(self, q, chat_id=None):
        self.calls.append(("history", q, chat_id))
        # The real flow's envelope (client.vision_history).
        return {"descriptions": [self._description], "total": 1}

    def delete_description(self, description_id):
        self.calls.append(("delete_description", description_id))
        return {"status": "deleted"}

    def attachments(self, chat_id):
        return [self._attachment]

    def thumbnail(self, attachment_id):
        self.calls.append(("thumbnail", attachment_id))
        return PNG_BYTES

    def delete_attachment(self, attachment_id):
        self.calls.append(("delete_attachment", attachment_id))
        return {"status": "deleted", "descriptions_purged": 2}

    def attach_file(self, chat_id, path, message_id=None, describe=False,
                    question=""):
        self.calls.append(("attach_file", chat_id, path))
        return self._attachment

    def describe_file(self, chat_id, path, question="", provider=None):
        self.calls.append(("describe_file", chat_id, path, question, provider))
        return self._description

    def describe_attachment(self, chat_id, attachment_id, question="",
                            provider=None):
        self.calls.append(
            ("describe_attachment", chat_id, attachment_id, question)
        )
        return self._description

    def watch_folders(self, chat_id):
        return [self._watch]

    def add_watch_folder(self, chat_id, path, recursive=False):
        self.calls.append(("add_watch_folder", chat_id, path, recursive))
        return self._watch

    def update_watch_folder(self, watch_id, enabled=None, recursive=None):
        self.calls.append(("update_watch_folder", watch_id, enabled, recursive))
        return self._watch

    def delete_watch_folder(self, watch_id):
        self.calls.append(("delete_watch_folder", watch_id))
        return {"status": "deleted", "ingested_records_removed": 3}

    def scan(self, watch_id, **kwargs):
        self.calls.append(("scan", watch_id))
        return {"watch_id": watch_id, "scanned": 3, "ingested": 1}

    def ingested(self, watch_id):
        return [{"filename": "cat.png", "watch_id": watch_id}]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def wait_for(qapp, predicate, timeout=10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


# ------------------------------------------------------------- voice


def test_voice_dialog_populates(qapp) -> None:
    flow = FakeVoiceFlow()
    dialog = VoiceDialog(None, flow, CHATS, "chat-1")
    dialog.show()
    try:
        assert dialog.tabs.count() == 3
        assert dialog.devices_list.count() == 2
        assert "fixture" in dialog.status_text.toPlainText()
        assert dialog.tts_backends_list.count() == 2
        assert dialog.stt_backends_list.count() == 1
        assert dialog.defaults_tts_combo.currentData() == "tts-a"
        assert dialog.defaults_stt_combo.currentData() == "stt-a"
        assert dialog.sessions_list.count() == 1
        assert "user_mic" in dialog.role_combos
        # The mic role's combo offers input devices only.
        combo = dialog.role_combos["user_mic"]
        offered = {combo.itemData(i) for i in range(combo.count())}
        assert offered == {"mic-1"}
    finally:
        dialog.close()


def test_voice_assign_calls_flow(qapp) -> None:
    flow = FakeVoiceFlow()
    dialog = VoiceDialog(None, flow, CHATS, "chat-1")
    dialog.show()
    try:
        combo = dialog.role_combos["user_playback"]
        index = combo.findData("spk-1")
        assert index >= 0
        combo.setCurrentIndex(index)
        dialog._assign_role("user_playback")
        assert ("assign_role", "user_playback", "spk-1") in flow.calls
    finally:
        dialog.close()


def test_voice_install_refusal_is_words(qapp) -> None:
    flow = FakeVoiceFlow()
    dialog = VoiceDialog(None, flow, CHATS, "chat-1")
    dialog.show()
    try:
        # Select the installable TTS B row by its (kind, key) data.
        from PySide6.QtCore import Qt

        row = 0
        for i in range(dialog.tts_backends_list.count()):
            if dialog.tts_backends_list.item(i).data(
                Qt.ItemDataRole.UserRole
            ) == ("tts", "tts-b"):
                row = i
        dialog.tts_backends_list.setCurrentRow(row)
        dialog._show_backend_detail()
        assert dialog.install_backend_button.isEnabled()
        dialog._install_backend()
        assert ("install_backend", "tts", "tts-b") in flow.calls
        assert "refused" in dialog.status_label.text()
    finally:
        dialog.close()


def test_voice_session_start_stop(qapp) -> None:
    flow = FakeVoiceFlow()
    dialog = VoiceDialog(None, flow, CHATS, "chat-1")
    dialog.show()
    try:
        dialog.auto_project_check.setChecked(True)
        dialog._start_session()
        assert ("start_session", "chat-1", True) in flow.calls
        dialog.sessions_list.setCurrentRow(0)
        dialog._stop_session()
        assert ("stop_session", "sess-1") in flow.calls
    finally:
        dialog.close()


# ------------------------------------------------------------ vision


def test_vision_describe_uses_chosen_provider(qapp) -> None:
    flow = FakeVisionFlow()
    dialog = VisionDialog(None, flow, CHATS, "chat-1")
    dialog.show()
    try:
        assert dialog.tabs.count() == 4
        dialog._set_describe_path("/tmp/cat.png")
        dialog.question_edit.setText("What is it?")
        index = dialog.provider_combo.findData("pv1")
        assert index >= 0
        dialog.provider_combo.setCurrentIndex(index)
        dialog._describe()
        assert (
            "describe_file",
            "chat-1",
            "/tmp/cat.png",
            "What is it?",
            "pv1",
        ) in flow.calls
    finally:
        dialog.close()


def test_vision_attachment_delete_reports_purge(qapp) -> None:
    flow = FakeVisionFlow()
    dialog = VisionDialog(None, flow, CHATS, "chat-1")
    dialog.show()
    try:
        dialog._confirm = lambda _title, _text: True
        assert dialog.attachments_list.count() == 1
        dialog.attachments_list.setCurrentRow(0)
        dialog._delete_attachment()
        assert ("delete_attachment", "att-1") in flow.calls
        assert "2 derived description(s)" in dialog.status_label.text()
    finally:
        dialog.close()


def test_vision_watch_scan_renders_report(qapp) -> None:
    flow = FakeVisionFlow()
    dialog = VisionDialog(None, flow, CHATS, "chat-1")
    dialog.show()
    try:
        assert dialog.watch_list.count() == 1
        dialog.watch_list.setCurrentRow(0)
        dialog._scan_watch()
        assert ("scan", "watch-1") in flow.calls
        assert dialog.scan_report_text.toPlainText() != ""
    finally:
        dialog.close()


# ---------------------------------------------------- window + composer


class FakeClient:
    def new_request_id(self):
        return "req-r13"

    def list_presets(self):
        return []


class FakeChatFlow:
    """A ChatFlow stand-in returning one canned turn result."""

    def __init__(self, result):
        self.result = result
        self.calls: list = []

    def send_turn(self, chat_id, text, *, on_event=None, request_id=None,
                  image=None):
        self.calls.append(("send_turn", chat_id, text, image))
        return self.result

    def open_chat(self, chat_id):
        return OpenChat(
            chat=ChatSummary(id=chat_id, title="Gate chat"),
            messages=[],
            session=None,
        )


def make_window(qapp, result):
    window = MainWindow(EngineHandle(), client=FakeClient())
    window._flow_instance = FakeChatFlow(result)
    window.current_chat_id = "chat-1"
    window.current_chat = ChatSummary(id="chat-1", title="Gate chat")
    window.current_messages = []
    window._update_composer_chrome()
    window.show()
    return window


def turn_result(attachment=None, attachment_error=""):
    return SimpleNamespace(
        status_words="Reply received and saved.",
        draft=StreamDraft(text="hi", finish="stop"),
        attachment=attachment,
        attachment_error=attachment_error,
    )


def test_mainwindow_r13_wiring(qapp) -> None:
    window = MainWindow(EngineHandle(), client=FakeClient())
    window._voice_flow_instance = FakeVoiceFlow()
    window._vision_flow_instance = FakeVisionFlow()
    window._chats_cache = list(CHATS)
    window.show()
    try:
        assert window.action_voice.text() == "Voice…"
        assert window.action_vision.text() == "Vision…"
        voice = window.open_voice_dialog()
        assert isinstance(voice, VoiceDialog)
        voice.close()
        vision = window.open_vision_dialog()
        assert isinstance(vision, VisionDialog)
        vision.close()
    finally:
        window.close()


def test_composer_attach_landed_clears_pending(qapp) -> None:
    attachment = make_view(
        VisionAttachmentView,
        id="att-1",
        filename="cat.png",
        image_format="png",
        image_width=10,
        image_height=8,
    )
    window = make_window(qapp, turn_result(attachment=attachment))
    try:
        window._pending_image = ("cat.png", PNG_BYTES)
        window._refresh_pending_image_chrome()
        assert "Image ready: cat.png" in window.attach_status_label.text()
        window.composer_edit.setPlainText("look at this")
        window.send_current_message()
        assert wait_for(qapp, lambda: window._pending_image is None)
        assert window._flow_instance.calls[0][3] == ("cat.png", PNG_BYTES)
        assert window.attach_status_label.text() == ""
    finally:
        window.close()


def test_composer_attach_failure_keeps_pending(qapp) -> None:
    window = make_window(
        qapp, turn_result(attachment_error="engine said no")
    )
    try:
        window._pending_image = ("cat.png", PNG_BYTES)
        window._refresh_pending_image_chrome()
        window.composer_edit.setPlainText("look at this")
        window.send_current_message()
        assert wait_for(
            qapp,
            lambda: "could not be attached" in window.attach_status_label.text(),
        )
        assert window._pending_image == ("cat.png", PNG_BYTES)
        assert "engine said no" in window.attach_status_label.text()
    finally:
        window.close()


def test_transcript_marks_attachments(qapp) -> None:
    field_names = {f.name for f in dataclasses.fields(MessageView)}
    if "attachments" not in field_names:
        pytest.skip(
            "MessageView.attachments is the sibling crew's deliverable; "
            "not present in this worktree yet"
        )
    attachment = make_view(
        VisionAttachmentView,
        id="att-1",
        filename="cat.png",
        image_format="png",
        image_width=10,
        image_height=8,
    )
    message = MessageView(
        id="m1",
        role="user",
        content="look",
        attachments=[attachment],
    )
    rendered = transcript_html([message])
    assert "[Image attached: cat.png — PNG, 10×8]" in rendered
    assert "image attached" in message_list_label(message)
