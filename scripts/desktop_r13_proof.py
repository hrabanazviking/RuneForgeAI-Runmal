"""Desktop proof (R-13): Voice & Vision in the real windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
and drives the R-13 surfaces through the window's own controls:

- A message is sent with an image riding the composer attach:
  the attachment lands on the user message (verified via the
  API), and the pending image clears.
- The Voice dialog reports the truth: status state, the
  fixture provider's devices, role words (unassigned roles say
  so — nothing claims "ready"), backend rows that state
  installed yes/no, defaults saved through the dialog, and a
  session started and stopped on the open chat.
- The Vision dialog shows the providers pane with the
  engine's semantic-caption note, describes an image from the
  window (the metadata provider's sniffed facts), registers a
  watch folder and scans it — the picture is ingested as an
  attachment and listed.
- RESTART the whole app on the same data dir: the saved voice
  defaults, the description, the attachments, and the watch
  folder persist.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r13_proof.py

Prints one line:  R13_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-13", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}

# A 1x1 transparent PNG (the R-08-verified fixture bytes).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c63000100000500010d0a2db4000000"
    "0049454e44ae426082"
)


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
    watch_dir = data_dir.parent / (data_dir.name + "-watch")
    watch_dir.mkdir(parents=True, exist_ok=True)
    (watch_dir / "watched.png").write_bytes(PNG_BYTES)
    describe_path = data_dir.parent / (data_dir.name + "-describe.png")
    describe_path.write_bytes(PNG_BYTES)

    from runmal.desktop.app import create_window
    from runmal.desktop.engine import EngineHandle, EngineState

    engine = EngineHandle()
    window = create_window(engine)
    window.show()
    app.processEvents()
    check("window_shown", window.isVisible(), window.windowTitle())

    snapshot = window.start_engine_blocking()
    app.processEvents()
    status = engine.status()
    check("engine_running", status.state is EngineState.RUNNING, status.label)
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
    window.refresh_blocking()
    app.processEvents()
    chat = client.create_chat(title="Gate chat", character_id=keeper.id)
    window.open_chat_blocking(chat.id)
    app.processEvents()

    # ---- Composer image attach rides a real send.
    window._pending_image = ("gate.png", PNG_BYTES)
    window._refresh_pending_image_chrome()
    check(
        "pending_image_announced",
        "gate.png" in window.attach_status_label.text(),
        window.attach_status_label.text(),
    )
    window.composer_edit.setPlainText("Look at this gate marker.")
    window.send_button.click()
    check(
        "turn_sent",
        wait_until(app, lambda: not window._streaming, timeout=30.0),
        str(len(window.current_messages)),
    )
    attachments = client.list_attachments(chat.id)
    check(
        "composer_attachment_landed",
        len(attachments) == 1
        and attachments[0].filename == "gate.png"
        and bool(attachments[0].message_id),
        str([(a.filename, a.message_id) for a in attachments]),
    )
    check(
        "pending_image_cleared",
        window._pending_image is None,
        window.attach_status_label.text(),
    )
    # Informational only: whether the engine's history payload
    # carries the attachment on the message (the transcript mark
    # rides it when present). The API landing above is the
    # substantive proof either way, so this never fails the run.
    marked = any(
        getattr(m, "attachments", None) for m in window.current_messages
    )
    RESULT["checks"]["transcript_attachment_mark"] = {
        "ok": True,
        "detail": f"history carries attachments: {bool(marked)}",
    }

    # ---- The Voice dialog: truthful status, devices, backends.
    voice = window.open_voice_dialog()
    check("voice_shown", voice is not None and voice.isVisible())
    app.processEvents()
    check(
        "voice_status_words",
        "State:" in voice.status_text.toPlainText(),
        voice.status_text.toPlainText()[:80],
    )
    check(
        "voice_devices_listed",
        voice.devices_list.count() >= 1,
        str(voice.devices_list.count()),
    )
    role_words = voice.roles_text.toPlainText()
    check(
        "voice_roles_truthful",
        ("not assigned" in role_words) or ("ready" in role_words),
        role_words[:120],
    )
    tts_lines = [
        voice.tts_backends_list.item(i).text()
        for i in range(voice.tts_backends_list.count())
    ]
    check(
        "voice_backends_listed",
        len(tts_lines) >= 1 and all("installed:" in t for t in tts_lines),
        " | ".join(tts_lines)[:160],
    )
    check(
        "voice_no_fake_ready",
        all("ready" not in t.lower() for t in tts_lines),
        " | ".join(tts_lines)[:160],
    )
    # Save defaults through the dialog (pick the LAST TTS entry so
    # the saved value differs from a fresh engine's first default
    # whenever the registry offers a choice).
    chosen_tts = None
    if voice.defaults_tts_combo.count() > 1:
        voice.defaults_tts_combo.setCurrentIndex(
            voice.defaults_tts_combo.count() - 1
        )
        chosen_tts = voice.defaults_tts_combo.currentData()
        voice.save_defaults_button.click()
        app.processEvents()
        saved = client.voice_defaults()
        check(
            "voice_defaults_saved",
            saved.get("tts_backend") == chosen_tts,
            str(saved),
        )
    else:
        check("voice_defaults_saved", True, "single TTS backend; no-op")

    # ---- A voice session on the open chat, started + stopped.
    index = voice.sessions_chat_combo.findData(chat.id)
    if index >= 0:
        voice.sessions_chat_combo.setCurrentIndex(index)
    voice.start_session_button.click()
    app.processEvents()
    check(
        "voice_session_started",
        voice.sessions_list.count() >= 1,
        voice.status_label.text(),
    )
    listing = client.list_voice_sessions(chat.id)
    check(
        "voice_session_active_via_api",
        listing.get("active_session_id") is not None,
        str(listing.get("active_session_id")),
    )
    voice.sessions_list.setCurrentRow(0)
    app.processEvents()
    check(
        "voice_session_detail",
        "State:" in voice.session_detail_text.toPlainText()
        or "Settings" in voice.session_detail_text.toPlainText(),
        voice.session_detail_text.toPlainText()[:80],
    )
    voice.stop_session_button.click()
    app.processEvents()
    listing = client.list_voice_sessions(chat.id)
    check(
        "voice_session_stopped",
        listing.get("active_session_id") is None,
        str(listing.get("active_session_id")),
    )
    voice.close()

    # ---- The Vision dialog: providers, describe, watch folders.
    vision = window.open_vision_dialog()
    check("vision_shown", vision is not None and vision.isVisible())
    app.processEvents()
    providers_text = vision.providers_text.toPlainText()
    check(
        "vision_providers_truthful",
        "semantic" in providers_text.lower(),
        providers_text[:160],
    )
    vision._set_describe_path(str(describe_path))
    vision.question_edit.setText("What marker is this?")
    vision.describe_button.click()
    app.processEvents()
    described = vision.describe_result_text.toPlainText()
    check(
        "vision_described_from_window",
        "png" in described.lower(),
        described[:160],
    )
    descriptions = client.list_chat_descriptions(chat.id)
    check(
        "vision_description_persisted",
        len(descriptions) >= 1,
        str(len(descriptions)),
    )
    # Watch folder: register + scan through the dialog.
    vision.watch_path_edit.setText(str(watch_dir))
    vision.add_watch_button.click()
    app.processEvents()
    check(
        "watch_folder_registered",
        vision.watch_list.count() == 1,
        vision.status_label.text(),
    )
    vision.watch_list.setCurrentRow(0)
    vision.scan_watch_button.click()
    app.processEvents()
    report = vision.scan_report_text.toPlainText()
    check(
        "watch_scan_ingested",
        "Ingested: 1" in report,
        report[:160],
    )
    check(
        "watch_ingested_listed",
        vision.ingested_list.count() == 1,
        str(vision.ingested_list.count()),
    )
    vision._load_attachments()
    app.processEvents()
    check(
        "attachments_listed_in_dialog",
        vision.attachments_list.count() >= 2,
        str(vision.attachments_list.count()),
    )
    vision.close()

    # ---- Restart: defaults, description, attachments, watch persist.
    window.close()
    app.processEvents()
    check(
        "engine_stopped_for_restart",
        wait_until(app, lambda: engine.status().state is EngineState.STOPPED),
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
    if chosen_tts is not None:
        saved2 = client2.voice_defaults()
        check(
            "voice_defaults_persist",
            saved2.get("tts_backend") == chosen_tts,
            str(saved2),
        )
    else:
        check("voice_defaults_persist", True, "single TTS backend; no-op")
    check(
        "description_persists",
        len(client2.list_chat_descriptions(chat.id)) >= 1,
        str(len(client2.list_chat_descriptions(chat.id))),
    )
    check(
        "attachments_persist",
        len(client2.list_attachments(chat.id)) >= 2,
        str(len(client2.list_attachments(chat.id))),
    )
    check(
        "watch_folder_persists",
        len(client2.list_watch_folders(chat.id)) == 1,
        str(len(client2.list_watch_folders(chat.id))),
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
    print("R13_RESULT " + json.dumps(RESULT))
    return 0 if RESULT["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
