"""Desktop proof (R-09): Connections & Generation in the real
windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
and drives the R-09 surfaces through the window's own controls,
verifying state via the API after each:

- Two backend profiles: A "Demo" (the canned fake) seeded via
  the API, B "Echo B" created THROUGH the Connections dialog
  against a local OpenAI-compatible echo server.
- Pin A in the dialog -> send -> the Demo reply lands. Pin B in
  the dialog -> send -> the echo reply lands, and the Session
  dock agrees about which profile the chat uses.
- A preset with temperature 0.9 created through the Generation
  dialog's sampler form and applied to the chat: the resolve
  preview shows it, and the echo server's recorded request body
  carries temperature 0.9 on the next send.
- A bundle created in the dialog, assigned to the chat with a
  sampler delta: the resolve preview shows the delta winning
  with its source named.
- RESTART the whole app on the same data dir: profiles and the
  applied preset persist.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r09_proof.py

Prints one line:  R09_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-09", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}
DEMO_REPLY = "Rúnmál hears you."
ECHO_REPLY = "ECHO-B-ANSWER"


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


class _EchoHandler(BaseHTTPRequestHandler):
    """A fast local OpenAI-compatible echo backend: it answers
    with a marker line and records the last request body, so the
    proof can see the sampling params that actually crossed."""

    seen: dict = {}

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
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen = payload
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunk = {
            "id": "echo", "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {"content": ECHO_REPLY},
                "finish_reason": None,
            }],
        }
        final = {
            "id": "echo", "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {},
                         "finish_reason": "stop"}],
        }
        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def send_line(app, window, text: str) -> bool:
    window.composer_edit.setPlainText(text)
    window.send_button.click()
    return wait_until(app, lambda: not window._streaming, timeout=30.0)


def last_reply(client, chat_id: str) -> str:
    history = client.list_chat_messages(chat_id)
    for message in reversed(history):
        if message.role == "assistant":
            return message.content
    return ""


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import Qt, qVersion
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    echo = HTTPServer(("127.0.0.1", 0), _EchoHandler)
    threading.Thread(target=echo.serve_forever, daemon=True).start()
    echo_url = f"http://127.0.0.1:{echo.server_address[1]}"
    RESULT["echo_url"] = echo_url

    app = QApplication(sys.argv)
    data_dir = Path(os.environ["RUNMAL_DATA_DIR"])
    RESULT["data_dir"] = str(data_dir)

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
    character = client.create_character(dict(CARD), name="Gate Keeper")
    chat = client.create_chat(title="Gate chat", character_id=character.id)
    profile_a = client.create_backend_profile(
        "Demo", "fake", chat_model="fake-1"
    )
    check("demo_profile_seeded", bool(profile_a.id), profile_a.id)
    window.refresh_blocking()
    window.open_chat_blocking(chat.id)

    # ---- Connections: pin A through the dialog, send, Demo reply.
    dialog = window.open_connections_dialog()
    check("connections_dialog_shown", dialog is not None and dialog.isVisible())
    check(
        "profiles_loaded_in_dialog",
        wait_until(app, lambda: dialog.profiles_list.count() >= 1),
        f"count={dialog.profiles_list.count()}",
    )
    for index in range(dialog.profiles_list.count()):
        item = dialog.profiles_list.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == profile_a.id:
            dialog.profiles_list.setCurrentItem(item)
            break
    app.processEvents()
    dialog.pin_button.click()
    pinned_a = wait_until(
        app,
        lambda: (client.get_chat(chat.id).backend_profile_id or "")
        == profile_a.id,
    )
    check("pin_a_via_dialog", pinned_a)
    check(
        "session_dock_agrees_a",
        wait_until(
            app, lambda: "Demo" in window.session_profile_label.text()
        ),
        window.session_profile_label.text(),
    )
    sent = send_line(app, window, "First words at the gate.")
    check(
        "demo_reply_landed",
        sent and last_reply(client, chat.id) == DEMO_REPLY,
        last_reply(client, chat.id)[:80],
    )

    # ---- Create profile B through the dialog form; pin it; send.
    dialog.new_profile()
    dialog.name_edit.setText("Echo B")
    backend_index = dialog.chat_backend_combo.findData("openai")
    dialog.chat_backend_combo.setCurrentIndex(backend_index)
    dialog.base_url_edit.setText(echo_url)
    dialog.chat_model_edit.setText("echo-1")
    dialog.save_button.click()
    created_b = wait_until(
        app,
        lambda: any(
            p.name == "Echo B" for p in client.list_backend_profiles()
        ),
    )
    check("profile_b_created_via_dialog", created_b)
    profile_b = next(
        p for p in client.list_backend_profiles() if p.name == "Echo B"
    )
    check(
        "profile_b_base_url_stored",
        profile_b.config.get("base_url") == echo_url,
        str(profile_b.config),
    )
    check(
        "dialog_tracks_saved_b",
        wait_until(app, lambda: dialog._current_id == profile_b.id),
        str(dialog._current_id),
    )
    dialog.pin_button.click()
    pinned_b = wait_until(
        app,
        lambda: (client.get_chat(chat.id).backend_profile_id or "")
        == profile_b.id,
    )
    check("pin_b_via_dialog", pinned_b)
    check(
        "session_dock_agrees_b",
        wait_until(
            app, lambda: "Echo B" in window.session_profile_label.text()
        ),
        window.session_profile_label.text(),
    )
    sent = send_line(app, window, "Second words, echo side.")
    check(
        "echo_reply_landed",
        sent and last_reply(client, chat.id) == ECHO_REPLY,
        last_reply(client, chat.id)[:80],
    )
    dialog.close()
    app.processEvents()

    # ---- Generation: preset 0.9 via the sampler form; apply;
    # the wire carries it to the echo backend.
    gen = window.open_generation_dialog()
    check("generation_dialog_shown", gen is not None and gen.isVisible())
    check(
        "generation_lists_loaded",
        wait_until(app, lambda: "preset(s)" in gen.status_label.text()),
        gen.status_label.text(),
    )
    gen.new_preset()
    gen.preset_name_edit.setText("Warm")
    gen.preset_sampler_form.set_field_value("temperature", 0.9)
    gen.preset_save_button.click()
    created_preset = wait_until(
        app,
        lambda: any(p.name == "Warm" for p in client.list_presets()),
    )
    check("preset_created_via_form", created_preset)
    preset = next(p for p in client.list_presets() if p.name == "Warm")
    detail = client.get_preset_detail(preset.id)
    check(
        "preset_bag_exact",
        detail.params == {"temperature": 0.9},
        str(detail.params),
    )
    check(
        "dialog_detail_loaded",
        wait_until(app, lambda: gen._preset_detail is not None),
    )
    gen.preset_apply_button.click()
    applied = wait_until(
        app,
        lambda: (client.get_chat(chat.id).preset_id or "") == preset.id,
    )
    check("preset_applied_via_dialog", applied)
    gen.tabs.setCurrentIndex(2)
    gen.resolve_refresh_button.click()
    check(
        "resolve_preview_shows_preset",
        wait_until(
            app,
            lambda: "Warm" in gen.resolve_preset_label.text()
            and "0.9" in gen.resolve_preset_label.text(),
        ),
        gen.resolve_preset_label.text()[:120],
    )
    _EchoHandler.seen = {}
    sent = send_line(app, window, "Third words, warm ones.")
    wire_temp = _EchoHandler.seen.get("temperature")
    check(
        "wire_carries_preset_temperature",
        sent and wire_temp == 0.9,
        f"temperature={wire_temp!r}",
    )

    # ---- Bundle + override in the dialog; resolve shows sources.
    gen.tabs.setCurrentIndex(1)
    gen.new_bundle()
    gen.bundle_name_edit.setText("Story")
    gen.bundle_sampler_form.set_field_value("temperature", 0.3)
    gen.bundle_save_button.click()
    created_bundle = wait_until(
        app, lambda: len(client.list_bundles()) >= 1
    )
    check("bundle_created_via_dialog", created_bundle)
    bundle = client.list_bundles()[0]
    scope_combo = gen.override_scope_combo
    scope_index = next(
        i for i in range(scope_combo.count())
        if scope_combo.itemData(i) == ("chat", chat.id)
    )
    scope_combo.setCurrentIndex(scope_index)
    check(
        "override_combo_populated",
        wait_until(
            app,
            lambda: gen.override_bundle_combo.findData(bundle.id) >= 0,
        ),
    )
    bundle_index = gen.override_bundle_combo.findData(bundle.id)
    gen.override_bundle_combo.setCurrentIndex(bundle_index)
    gen.override_delta_form.set_field_value("temperature", 0.7)
    gen.override_set_button.click()
    assigned = wait_until(
        app, lambda: len(client.list_overrides()) >= 1
    )
    check("override_set_via_dialog", assigned)
    gen.tabs.setCurrentIndex(2)
    gen.resolve_refresh_button.click()

    def resolve_shows_delta() -> bool:
        for i in range(gen.resolve_list.count()):
            text = gen.resolve_list.item(i).text()
            if "Temperature" in text and "0.7" in text and "chat" in text:
                return True
        return False

    check(
        "resolve_shows_delta_with_source",
        wait_until(app, resolve_shows_delta),
        gen.resolve_notes_label.text()[:120],
    )
    gen.close()
    app.processEvents()

    # ---- Restart: profiles + applied preset persist.
    window.close()
    app.processEvents()
    deadline = time.time() + 10
    stopped = False
    while time.time() < deadline:
        if engine.status().state is EngineState.STOPPED:
            stopped = True
            break
        time.sleep(0.2)
    check("engine_stopped_for_restart", stopped, engine.status().label)

    engine2 = EngineHandle()
    window2 = create_window(engine2)
    window2.show()
    app.processEvents()
    window2.start_engine_blocking()
    app.processEvents()
    check(
        "engine_running_after_restart",
        engine2.status().state is EngineState.RUNNING,
        engine2.status().label,
    )
    if window2._wizard is not None:
        window2._wizard.close()
        app.processEvents()
        window2._wizard = None
    client2 = window2.client()
    names = {p.name for p in client2.list_backend_profiles()}
    check(
        "profiles_persist_after_restart",
        {"Demo", "Echo B"} <= names,
        str(sorted(names)),
    )
    chat_after = client2.get_chat(chat.id)
    check(
        "preset_persists_after_restart",
        (chat_after.preset_id or "") == preset.id,
        str(chat_after.preset_id),
    )

    # ---- Clean quit stops the engine.
    window2.close()
    app.processEvents()
    deadline = time.time() + 10
    stopped = False
    while time.time() < deadline:
        if engine2.status().state is EngineState.STOPPED:
            stopped = True
            break
        time.sleep(0.2)
    check("engine_stopped_on_quit", stopped, engine2.status().label)
    try:
        urllib.request.urlopen(f"{engine2.base_url}/healthz", timeout=2)
        health_after = True
    except Exception:
        health_after = False
    check("healthz_gone_after_quit", not health_after)

    echo.shutdown()
    app.quit()
    passed = all(c["ok"] for c in RESULT["checks"].values())
    RESULT["pass"] = passed
    print("R09_RESULT " + json.dumps(RESULT, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
