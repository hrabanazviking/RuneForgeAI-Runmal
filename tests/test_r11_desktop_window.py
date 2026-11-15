"""R-11 acceptance (widgets): the Groups dialog over a
MockTransport engine — create a two-character room from the
roster checklist, speak in the room, run strategy turns from
the dialog, edit a member + override, and the MainWindow's
Chat ▸ Groups… wiring.

Skips cleanly when PySide6 is absent (R-04 pattern); runs on
the fleet devices' R-01 environments, offscreen. The live
engine in the real window is scripts/desktop_r11_proof.py.
"""

import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.client import DesktopSession, RunmalClient  # noqa: E402
from runmal.desktop.client.models import CharacterSummary  # noqa: E402
from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.group_logic import GroupFlow  # noqa: E402
from runmal.desktop.window import GroupsDialog, MainWindow  # noqa: E402

TOKEN = "test-" + "token-r11"

CHARACTERS = [
    {"id": "a", "name": "Gate Keeper"},
    {"id": "b", "name": "Mask Bearer"},
]


class MiniEngine:
    """Snapshot + characters + the groupchat roads, in-memory."""

    def __init__(self):
        self.groups: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.deepening: dict[str, dict] = {}
        self._seq = 0

    def _group(self, gid):
        group = self.groups[gid]
        group["message_count"] = len(self.messages.get(gid, []))
        group["member_count"] = len(group["members"])
        return group

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
            return httpx.Response(200, json=CHARACTERS)
        if parts == ["groups"] and method == "GET":
            return httpx.Response(
                200, json=[self._group(g) for g in self.groups]
            )
        if parts == ["groups"] and method == "POST":
            self._seq += 1
            gid = f"g{self._seq}"
            names = {c["id"]: c["name"] for c in CHARACTERS}
            self.groups[gid] = {
                "id": gid,
                "name": body["name"],
                "chat_id": f"chat-{gid}",
                "members": [
                    {
                        "character_id": cid,
                        "name": names[cid],
                        "position": i,
                        "talkativeness": 0.5,
                        "muted": False,
                    }
                    for i, cid in enumerate(body["member_character_ids"])
                ],
                "speaker_policy": "natural",
                "speaker_config": {},
                "created_at": "2026-11-15T00:00:00",
            }
            self.messages[gid] = []
            self.deepening[gid] = {
                "generation_mode": "swap",
                "join_prefix": "",
                "join_suffix": "",
                "scenario_override": None,
                "allow_self_responses": False,
                "auto_mode": {"enabled": False, "max_turns": 3},
                "member_overrides": {},
                "state": {"list_cursor": 0, "pool_spoken": []},
            }
            return httpx.Response(201, json=self._group(gid))
        if len(parts) >= 2 and parts[0] == "groups":
            gid = parts[1]
            group = self.groups[gid]
            if len(parts) == 2 and method == "GET":
                return httpx.Response(200, json=self._group(gid))
            if len(parts) == 2 and method == "PATCH":
                if body.get("name") is not None:
                    group["name"] = body["name"]
                if body.get("speaker_policy") is not None:
                    group["speaker_policy"] = body["speaker_policy"]
                return httpx.Response(200, json=self._group(gid))
            if len(parts) == 2 and method == "DELETE":
                del self.groups[gid]
                return httpx.Response(200, json={"deleted": True})
            if parts[2] == "members" and len(parts) == 3 and method == "POST":
                names = {c["id"]: c["name"] for c in CHARACTERS}
                cid = body["character_id"]
                group["members"].append(
                    {
                        "character_id": cid,
                        "name": names[cid],
                        "position": len(group["members"]),
                        "talkativeness": 0.5,
                        "muted": False,
                    }
                )
                return httpx.Response(201, json=group["members"][-1])
            if parts[2] == "members" and len(parts) == 4:
                cid = parts[3]
                if method == "DELETE":
                    group["members"] = [
                        m for m in group["members"]
                        if m["character_id"] != cid
                    ]
                    return httpx.Response(200, json={"deleted": True})
                if method == "PATCH":
                    member = next(
                        m for m in group["members"]
                        if m["character_id"] == cid
                    )
                    member.update(body or {})
                    return httpx.Response(200, json=member)
            if parts[2] == "members" and len(parts) == 5:
                cid, verb = parts[3], parts[4]
                if verb == "override" and method == "PATCH":
                    deep = self.deepening[gid]
                    override = dict(deep["member_overrides"].get(cid) or {})
                    override.update(body or {})
                    deep["member_overrides"][cid] = override
                    return httpx.Response(200, json=override)
                if verb == "peek" and method == "GET":
                    member = next(
                        m for m in group["members"]
                        if m["character_id"] == cid
                    )
                    override = self.deepening[gid][
                        "member_overrides"
                    ].get(cid) or {}
                    return httpx.Response(
                        200,
                        json={
                            "member": member,
                            "override": override,
                            "persona_source": (
                                "override"
                                if override.get("persona_override")
                                else "card"
                            ),
                            "effective_persona": "Persona text.",
                        },
                    )
                if verb in ("leave", "return") and method == "POST":
                    return httpx.Response(
                        200, json={"entries": []}
                        if verb == "return" else {"state": "absent"}
                    )
            if parts[2] == "messages":
                if method == "GET":
                    return httpx.Response(200, json=self.messages[gid])
                if method == "POST":
                    names = {c["id"]: c["name"] for c in CHARACTERS}
                    row = {
                        "id": f"m{len(self.messages[gid]) + 1}",
                        "speaker_id": body["speaker"],
                        "speaker_name": (
                            "You" if body["speaker"] == "user"
                            else names[body["speaker"]]
                        ),
                        "role": "user" if body["speaker"] == "user"
                        else "assistant",
                        "content": body["content"],
                    }
                    self.messages[gid].append(row)
                    return httpx.Response(201, json=row)
            if parts[2] == "deepening":
                if method == "GET":
                    return httpx.Response(200, json=self.deepening[gid])
                if method == "PUT":
                    self.deepening[gid] = body
                    return httpx.Response(200, json=body)
            if parts[2] == "presence" and method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {"character_id": m["character_id"],
                         "name": m["name"], "state": "present"}
                        for m in group["members"]
                    ],
                )
            if parts[2] in ("next", "run") and method == "POST":
                cursor = self.deepening[gid]["state"]["list_cursor"]
                members = group["members"]
                member = members[cursor % len(members)]
                self.deepening[gid]["state"]["list_cursor"] = cursor + 1
                message = None
                if (body or {}).get("generate"):
                    message = {
                        "id": "gen",
                        "speaker_id": member["character_id"],
                        "speaker_name": member["name"],
                        "role": "assistant",
                        "content": f"{member['name']} replies.",
                    }
                    self.messages[gid].append(message)
                one = {
                    "group_id": gid,
                    "strategy": group["speaker_policy"],
                    "speaker_id": member["character_id"],
                    "speaker_name": member["name"],
                    "reason": "in order",
                    "message": message,
                }
                if parts[2] == "next":
                    return httpx.Response(200, json=one)
                return httpx.Response(
                    200,
                    json={
                        "group_id": gid,
                        "turns_run": body["turns"],
                        "results": [one],
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


def make_dialog(qapp):
    client, engine = make_client()
    characters = [
        CharacterSummary(id=c["id"], name=c["name"]) for c in CHARACTERS
    ]
    dialog = GroupsDialog(None, GroupFlow(client), characters)
    dialog.show()
    qapp.processEvents()
    return dialog, engine


def create_room(dialog, qapp):
    dialog.new_name.setText("Gate Watch")
    for i in range(dialog.new_roster.count()):
        dialog.new_roster.item(i).setCheckState(Qt.CheckState.Checked)
    dialog._create()
    qapp.processEvents()
    assert dialog.groups_list.count() == 1


def test_create_room_and_run_turns(qapp) -> None:
    dialog, engine = make_dialog(qapp)
    try:
        create_room(dialog, qapp)
        assert dialog._group is not None
        assert dialog._group.member_count == 2
        assert dialog.members_list.count() == 2
        dialog.say_field.setText("Who watches tonight?")
        dialog._say()
        assert "You: Who watches tonight?" in dialog.transcript.toPlainText()
        dialog._next_turn()
        assert dialog.turn_label.text().startswith("Next speaker:")
        transcript = dialog.transcript.toPlainText()
        assert "replies." in transcript  # generated reply landed
        dialog.run_spin.setValue(2)
        dialog._run_turns()
        assert dialog.turn_label.text().startswith("Ran 2 turns.")
    finally:
        dialog.close()


def test_roster_editors_and_settings(qapp) -> None:
    dialog, engine = make_dialog(qapp)
    try:
        create_room(dialog, qapp)
        dialog.members_list.setCurrentRow(1)
        dialog.talk_spin.setValue(0.9)
        dialog.muted_check.setChecked(True)
        dialog._save_member()
        member = engine.groups["g1"]["members"][1]
        assert member["talkativeness"] == 0.9 and member["muted"] is True
        dialog.activation_combo.setCurrentIndex(
            dialog.activation_combo.findData("never")
        )
        dialog.persona_override.setPlainText("A sterner bearer.")
        dialog._save_override()
        override = engine.deepening["g1"]["member_overrides"]["b"]
        assert override["activation"] == "never"
        dialog._peek()
        assert "Persona text." in dialog.peek_text.toPlainText()
        # Settings: rename + strategy + deepening mode.
        dialog.name_field.setText("Night Watch")
        dialog.policy_combo.setCurrentIndex(
            dialog.policy_combo.findData("list")
        )
        dialog.mode_combo.setCurrentIndex(
            dialog.mode_combo.findData("join")
        )
        dialog._save_settings()
        assert engine.groups["g1"]["name"] == "Night Watch"
        assert engine.groups["g1"]["speaker_policy"] == "list"
        assert engine.deepening["g1"]["generation_mode"] == "join"
        assert engine.deepening["g1"]["state"]["list_cursor"] >= 0
    finally:
        dialog.close()


def test_mainwindow_groups_wiring(qapp) -> None:
    client, _engine = make_client()
    window = MainWindow(EngineHandle(), client=client)
    window.show()
    try:
        window.refresh_blocking()
        assert wait_for(qapp, lambda: window._characters_cache != [])
        dialog = window.open_groups_dialog()
        assert isinstance(dialog, GroupsDialog)
        dialog.close()
    finally:
        window.close()
