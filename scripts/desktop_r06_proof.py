"""Desktop proof (R-06): Chat Stage I in the real windowed app.

Launches the REAL windowed app (``runmal.desktop.app`` road, no
auto-wizard — this proof drives the stage itself) on a fresh
throwaway data dir, seeds a Demo profile, a character and a preset
through the real API, and then works the stage's own controls:

- New Chat through the dialog's character picker: the greeting is
  seeded and rendered; the chat is pinned to the Demo profile and
  the preset applied (client roads), and the Session dock must
  show those real values (character / persona / profile / model /
  preset, in words).
- A message typed into the composer and sent with the Send button:
  the composed reply streams in and LANDS in the stored history.
- A second chat pinned to a slow local echo backend (eight chunks
  x 0.4s): Send, watch tokens arrive, press Stop — the stream must
  end stopped and the partial reply must NOT be in the history.
- Reopen the first chat: greeting + user line + reply all persist.
- Rename through the Rename dialog; export from the dock road to
  a file and read it back.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r06_proof.py

Prints one line:  R06_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-06", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

GREETING = "Well met, traveller. The pass is open."
USER_LINE = "I seek passage."
RENAMED = "The Pass Chat"


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


class _SlowEchoHandler(BaseHTTPRequestHandler):
    """OpenAI-compatible backend streaming 8 chunks x 0.4s."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/models"):
            body = {"data": [{"id": "echo-1", "object": "model"}]}
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for index in range(8):
                chunk = {
                    "id": "echo", "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"chunk-{index} "},
                        "finish_reason": None,
                    }],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.4)
            final = {
                "id": "echo", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {},
                             "finish_reason": "stop"}],
            }
            self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    echo = HTTPServer(("127.0.0.1", 0), _SlowEchoHandler)
    threading.Thread(target=echo.serve_forever, daemon=True).start()
    echo_url = f"http://127.0.0.1:{echo.server_address[1]}"
    RESULT["echo_url"] = echo_url

    app = QApplication(sys.argv)

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
    # This proof drives the stage itself, not the wizard: dismiss
    # the auto-opened wizard if the app entry raised it.
    if window._wizard is not None:
        window._wizard.close()
        app.processEvents()
        window._wizard = None

    client = window.client()

    # ---- Seed through the real API: Demo profile, character, preset.
    profile = client.create_backend_profile(
        "Demo mode", "fake", chat_model="fake-1"
    )
    character = client.create_character(
        {
            "name": "Gate Keeper",
            "description": "Guards the high pass.",
            "personality": "Calm, dry, kind.",
            "first_mes": GREETING,
        },
        name="Gate Keeper",
    )
    import httpx

    from runmal.auth import get_or_create_credential

    with httpx.Client(
        base_url=engine.base_url, trust_env=False, timeout=10.0,
        headers={"Authorization": f"Bearer {get_or_create_credential()}"},
    ) as http:
        created = http.post(
            "/api/v1/presets",
            json={"name": "Storyteller", "params": {"temperature": 0.4}},
        )
    preset_id = created.json()["id"] if created.status_code == 201 else ""
    check("seeded_via_real_api", bool(profile.id and character.id and preset_id),
          f"profile={profile.id} character={character.id} preset={preset_id}")
    window.refresh_blocking()
    app.processEvents()

    # ---- New Chat through the dialog's character picker.
    dialog = window.open_new_chat_dialog()
    check("new_chat_dialog_shown", dialog.isVisible())
    dialog.select_character(character.id)
    dialog.title_edit.setText("Gate chat")
    dialog.accept()
    created_chat = wait_until(app, lambda: window.current_chat_id is not None)
    chat_id = window.current_chat_id or ""
    check("chat_created_via_picker", created_chat and bool(chat_id), chat_id)
    check(
        "greeting_rendered_in_stage",
        GREETING in window.message_view.toPlainText(),
        window.message_view.toPlainText()[:120],
    )
    check(
        "stage_title_names_character",
        window.stage_title.text() == "Chat with Gate Keeper",
        window.stage_title.text(),
    )

    # Pin the Demo profile + apply the preset (client roads); the
    # Session dock must then show those real values.
    client.set_chat_backend_profile(chat_id, profile.id)
    client.set_chat_preset(chat_id, preset_id)
    window.open_chat_blocking(chat_id)
    app.processEvents()
    check(
        "session_character_and_persona",
        "Gate Keeper" in window.session_character_label.text()
        and "Gate Keeper" in window.session_persona_label.text(),
        f"{window.session_character_label.text()} | "
        f"{window.session_persona_label.text()}",
    )
    check(
        "session_profile_and_model",
        "Demo mode" in window.session_profile_label.text()
        and window.session_model_label.text() == "Model: fake-1",
        f"{window.session_profile_label.text()} | "
        f"{window.session_model_label.text()}",
    )
    check(
        "session_preset",
        window.session_preset_label.text() == "Preset: Storyteller",
        window.session_preset_label.text(),
    )

    # ---- Send from the composer; the composed reply streams + lands.
    window.composer_edit.setPlainText(USER_LINE)
    window.send_button.click()
    sent = wait_until(
        app,
        lambda: not window._streaming
        and "Rúnmál hears you." in window.message_view.toPlainText(),
        timeout=30.0,
    )
    check("composed_reply_streamed_in", sent,
          window.message_view.toPlainText()[:160])
    check(
        "turn_words_saved",
        "saved" in window.chat_stage_status.text(),
        window.chat_stage_status.text(),
    )
    history = client.list_chat_messages(chat_id)
    check(
        "history_landed",
        [m.role for m in history] == ["assistant", "user", "assistant"]
        and history[1].content == USER_LINE
        and history[2].content == "Rúnmál hears you.",
        f"roles={[m.role for m in history]}",
    )

    # ---- Second chat on the slow echo backend: Stop mid-flight.
    slow_profile = client.create_backend_profile(
        "Slow Echo", "openai", chat_model="echo-1",
        config={"base_url": echo_url},
    )
    slow = window.create_chat_blocking(character_id=character.id,
                                       title="Slow chat")
    client.set_chat_backend_profile(slow.chat.id, slow_profile.id)
    window.open_chat_blocking(slow.chat.id)
    app.processEvents()
    window.composer_edit.setPlainText("Tell me slowly.")
    window.send_button.click()
    streaming = wait_until(
        app,
        lambda: window._streaming
        and "chunk-" in window.message_view.toPlainText(),
        timeout=20.0,
    )
    check("slow_stream_arriving", streaming,
          window.message_view.toPlainText()[:160])
    check(
        "stop_enabled_while_streaming",
        window.stop_button.isEnabled(),
    )
    window.stop_button.click()
    stopped = wait_until(app, lambda: not window._streaming, timeout=25.0)
    check("stream_stopped", stopped)
    check(
        "stop_words_honest",
        "not saved" in window.chat_stage_status.text(),
        window.chat_stage_status.text(),
    )
    slow_history = client.list_chat_messages(slow.chat.id)
    check(
        "partial_not_persisted",
        [m.role for m in slow_history] == ["assistant", "user"],
        f"roles={[m.role for m in slow_history]}",
    )

    # ---- Reopen the first chat: history persisted across reopen.
    window.open_chat_blocking(chat_id)
    app.processEvents()
    reopened_text = window.message_view.toPlainText()
    check(
        "reopen_shows_persisted_history",
        GREETING in reopened_text
        and USER_LINE in reopened_text
        and "Rúnmál hears you." in reopened_text,
        reopened_text[:200],
    )

    # ---- Rename through the Rename dialog.
    rename = window.open_rename_dialog()
    check("rename_dialog_shown", rename is not None and rename.isVisible())
    if rename is not None:
        rename.title_edit.setText(RENAMED)
        rename.accept()
    renamed = wait_until(
        app,
        lambda: any(
            window.chats_list.item(i).text() == RENAMED
            for i in range(window.chats_list.count())
        ),
    )
    check("rename_landed_in_dock", renamed, window._chat_title_for(chat_id))

    # ---- Export from the dock road to a real file.
    export_path = os.path.join(
        tempfile.mkdtemp(prefix="r06-export-"), "pass-chat.json"
    )
    window.export_chat_to_path(chat_id, export_path)
    try:
        document = json.loads(
            open(export_path, encoding="utf-8").read()
        )
        export_ok = (
            document["chat"]["title"] == RENAMED
            and len(document["messages"]) == 3
        )
        export_detail = f"messages={len(document.get('messages', []))}"
    except Exception as exc:  # noqa: BLE001
        export_ok, export_detail = False, str(exc)
    check("export_file_verified", export_ok, export_detail)

    # ---- Clean quit stops the engine.
    window.close()
    app.processEvents()
    deadline = time.time() + 10
    stopped_engine = False
    while time.time() < deadline:
        if engine.status().state is EngineState.STOPPED:
            stopped_engine = True
            break
        time.sleep(0.2)
    check("engine_stopped_on_quit", stopped_engine, engine.status().label)
    try:
        urllib.request.urlopen(f"{engine.base_url}/healthz", timeout=2)
        health_after = True
    except Exception:
        health_after = False
    check("healthz_gone_after_quit", not health_after)

    echo.shutdown()
    app.quit()
    passed = all(c["ok"] for c in RESULT["checks"].values())
    RESULT["pass"] = passed
    print("R06_RESULT " + json.dumps(RESULT, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
