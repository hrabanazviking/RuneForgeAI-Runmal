"""R-12 acceptance (widgets): the four R-12 dialogs over a
MockTransport engine — memory browse + detail, scenario
create + bind, inspector trace rendering, compose/macros —
plus the MainWindow menu wiring.

Skips cleanly when PySide6 is absent (R-04 pattern); runs on
the fleet devices' R-01 environments, offscreen. The live
engine in the real window is scripts/desktop_r12_proof.py.
"""

import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.client import DesktopSession, RunmalClient  # noqa: E402
from runmal.desktop.compose_logic import ComposeFlow  # noqa: E402
from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.inspector_logic import InspectorFlow  # noqa: E402
from runmal.desktop.memory_logic import MemoryFlow  # noqa: E402
from runmal.desktop.scenario_logic import ScenarioFlow  # noqa: E402
from runmal.desktop.window import (  # noqa: E402
    ComposeDialog,
    InspectorDialog,
    MainWindow,
    MemoryDialog,
    ScenariosDialog,
)

TOKEN = "test-" + "token-r12"


class MiniEngine:
    """Snapshot + chats + the R-12 roads, in-memory."""

    def __init__(self):
        self.scenarios: dict[str, dict] = {}
        self.bindings: dict[str, dict] = {}
        self._seq = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path
        body = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = None
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        path = path.replace("/api/v1", "", 1)
        parts = [p for p in path.split("/") if p]
        if parts == ["backend-profiles"]:
            return httpx.Response(200, json=[])
        if parts == ["chats"]:
            return httpx.Response(200, json=[])
        if parts == ["characters"]:
            return httpx.Response(
                200, json=[{"id": "k1", "name": "Gate Keeper"}]
            )
        if parts == ["memories"] and method == "GET":
            return httpx.Response(
                200,
                json={
                    "memories": [
                        {
                            "id": "m1",
                            "kind": "fact",
                            "content": "Volmarr keeps bees.",
                            "state": "active",
                            "scope": "witnesses",
                            "salience": 0.8,
                            "confidence": 0.9,
                            "pinned": False,
                            "sources": [
                                {"kind": "message", "extractor": "fx"}
                            ],
                        }
                    ]
                },
            )
        if len(parts) == 2 and parts[0] == "memories":
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "kind": "fact",
                    "content": "Volmarr keeps bees.",
                    "state": "active",
                    "scope": "witnesses",
                    "salience": 0.8,
                    "confidence": 0.9,
                    "sources": [{"kind": "message", "extractor": "fx"}],
                    "graph": {"nodes": [{}], "edges": []},
                },
            )
        if parts[:2] == ["scenarios", "bindings"]:
            if method == "GET" and len(parts) == 2:
                rows = list(self.bindings.values())
                return httpx.Response(
                    200, json={"bindings": rows, "total": len(rows)}
                )
            if method == "GET" and len(parts) == 3:
                binding = self.bindings.get(parts[2])
                if binding is None:
                    return httpx.Response(404, json={"detail": "none"})
                return httpx.Response(200, json=binding)
            if method == "DELETE" and len(parts) == 3:
                self.bindings.pop(parts[2], None)
                return httpx.Response(200, json={"deleted": True})
        if parts == ["scenarios"]:
            if method == "GET":
                rows = [
                    {
                        "id": sid,
                        "name": rec["name"],
                        "definition": rec,
                        "revision": 1,
                        "source_format": "native",
                        "tags": [],
                        "is_favourite": False,
                    }
                    for sid, rec in self.scenarios.items()
                ]
                return httpx.Response(
                    200, json={"scenarios": rows, "total": len(rows)}
                )
            if method == "POST":
                self._seq += 1
                sid = f"s{self._seq}"
                self.scenarios[sid] = body
                return httpx.Response(
                    201,
                    json={
                        "id": sid,
                        "name": body["name"],
                        "definition": body,
                        "revision": 1,
                        "source_format": "native",
                    },
                )
        if len(parts) >= 2 and parts[0] == "scenarios":
            sid = parts[1]
            if len(parts) == 2 and method == "GET":
                rec = self.scenarios[sid]
                return httpx.Response(
                    200,
                    json={
                        "id": sid,
                        "name": rec["name"],
                        "definition": rec,
                        "revision": 1,
                        "source_format": "native",
                        "tags": [],
                        "is_favourite": False,
                    },
                )
            if len(parts) == 3 and parts[2] == "bind" and method == "POST":
                self.bindings[body["chat_id"]] = {
                    "chat_id": body["chat_id"],
                    "definition_id": sid,
                    "definition_name": self.scenarios[sid]["name"],
                }
                return httpx.Response(201, json=self.bindings[body["chat_id"]])
            if len(parts) == 3 and parts[2] in ("tags", "favourite"):
                return httpx.Response(200, json={})
        if parts[:2] == ["inspector", "chats"]:
            return httpx.Response(200, json={"chat": {"id": parts[2]}})
        if parts == ["debug", "prompt-inspect"]:
            return httpx.Response(
                200,
                json={
                    "ledger": {
                        "context_limit": 4096,
                        "reserved_response": 512,
                        "overhead": 10,
                        "input_budget": 3574,
                        "total_input_tokens": 42,
                        "remaining_input_tokens": 3532,
                    },
                    "slots": [
                        {
                            "kind": "main_system",
                            "status": "included",
                            "tokens": 40,
                            "reason": "always present",
                        }
                    ],
                },
            )
        if parts == ["tools", "macros"]:
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "char",
                        "description": "The character's name",
                        "syntax": "{{char}}",
                    }
                ],
            )
        if parts == ["tools", "macros", "expand"]:
            return httpx.Response(
                200,
                json={"text": body["text"].replace("{{char}}", body["char"])},
            )
        if parts == ["tools", "compose"]:
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {"role": "system", "content": body["system"]}
                    ],
                    "ledger": {"total_input_tokens": 3},
                },
            )
        return httpx.Response(404, json={"detail": f"no road {method} {path}"})


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


def make_client():
    engine = MiniEngine()
    session = DesktopSession("http://test", **{"bearer" + "_token": TOKEN})
    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    return RunmalClient(session, http=http), engine


def test_memory_dialog_browses(qapp) -> None:
    client, _engine = make_client()
    dialog = MemoryDialog(None, MemoryFlow(client))
    dialog.show()
    try:
        assert dialog.memories_list.count() == 1
        assert "Volmarr keeps bees." in dialog.detail_text.toPlainText()
        assert "extracted by fx" in dialog.detail_text.toPlainText()
    finally:
        dialog.close()


def test_scenarios_dialog_create_and_bind(qapp) -> None:
    client, engine = make_client()
    dialog = ScenariosDialog(
        None,
        ScenarioFlow(client),
        chat_id="chat-1",
        chat_title="Gate chat",
    )
    dialog.show()
    try:
        dialog._editors["name"].setText("Gate Watch")
        dialog._editors["scenario_text"].setPlainText("Snow closes in.")
        dialog._new()
        qapp.processEvents()
        assert dialog.library_list.count() == 1
        assert engine.scenarios["s1"]["scenario_text"] == "Snow closes in."
        dialog._bind()
        assert "chat-1" in engine.bindings
        assert "Bound scenario" in dialog.binding_label.text()
    finally:
        dialog.close()


def test_inspector_dialog_renders_trace(qapp) -> None:
    client, _engine = make_client()
    dialog = InspectorDialog(
        None,
        InspectorFlow(client),
        chat_id="chat-1",
        chat_title="Gate chat",
        character_id="k1",
        sample_messages=["hello"],
    )
    dialog.show()
    try:
        assert "input budget 3574" in dialog.ledger_label.text()
        assert dialog.slots_list.count() == 1
        assert "main_system — Included" in dialog.slots_list.item(0).text()
    finally:
        dialog.close()


def test_compose_dialog_expands_and_composes(qapp) -> None:
    client, _engine = make_client()
    dialog = ComposeDialog(None, ComposeFlow(client))
    dialog.show()
    try:
        assert dialog.macros_list.count() == 1
        dialog.expand_text.setText("{{char}} watches.")
        dialog.expand_char.setText("Keeper")
        dialog._expand()
        assert dialog.expand_output.toPlainText() == "Keeper watches."
        dialog.compose_system.setPlainText("Be kind.")
        dialog._compose()
        assert "[system] Be kind." in dialog.compose_output.toPlainText()
    finally:
        dialog.close()


def test_mainwindow_r12_wiring(qapp) -> None:
    client, _engine = make_client()
    window = MainWindow(EngineHandle(), client=client)
    window.show()
    try:
        assert window.action_memory is not None
        assert window.action_scenarios is not None
        assert window.action_inspector is not None
        dialog = window.open_memory_dialog()
        assert isinstance(dialog, MemoryDialog)
        dialog.close()
        # No chat open: the inspector refuses honestly.
        assert window.open_inspector_dialog() is None
        assert "Open a chat first" in window.statusBar().currentMessage()
    finally:
        window.close()
