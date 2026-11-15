"""R-11 acceptance (group logic): the Qt-free GroupFlow over a
fake transport — room CRUD payloads, roster verbs, member
settings, the deepening compose (engine state + unknown keys
carried verbatim), override patching, and the words for turns,
presence, digests and peeks."""

import httpx

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.group_logic import (
    GroupFlow,
    compose_deepening,
    digest_words,
    group_line,
    member_line,
    peek_words,
    policy_label,
    presence_words,
    run_words,
    transcript_lines,
    turn_words,
)

TOKEN = "test-" + "token-r11"


class FakeEngine:
    """The groupchat roads, in-memory."""

    def __init__(self):
        self.groups: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.deepening: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict | None]] = []
        self._seq = 0

    def _group(self, gid: str) -> dict:
        group = self.groups[gid]
        group["message_count"] = len(self.messages.get(gid, []))
        group["member_count"] = len(group["members"])
        return group

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json as jsonlib

        method = request.method
        path = request.url.path.replace("/api/v1", "", 1)
        body = None
        if request.content:
            try:
                body = jsonlib.loads(request.content)
            except ValueError:
                body = None
        self.calls.append((method, path, body))
        parts = [p for p in path.split("/") if p]

        if parts == ["groups"] and method == "GET":
            return httpx.Response(
                200, json=[self._group(g) for g in self.groups]
            )
        if parts == ["groups"] and method == "POST":
            self._seq += 1
            gid = f"g{self._seq}"
            members = [
                {
                    "character_id": cid,
                    "name": f"Char {cid}",
                    "position": i,
                    "talkativeness": 0.5,
                    "muted": False,
                }
                for i, cid in enumerate(body["member_character_ids"])
            ]
            self.groups[gid] = {
                "id": gid,
                "name": body["name"],
                "chat_id": f"chat-{gid}",
                "members": members,
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
            if len(parts) == 2 and method == "GET":
                return httpx.Response(200, json=self._group(gid))
            if len(parts) == 2 and method == "PATCH":
                group = self.groups[gid]
                if body.get("name") is not None:
                    group["name"] = body["name"]
                if body.get("speaker_policy") is not None:
                    group["speaker_policy"] = body["speaker_policy"]
                if body.get("speaker_config") is not None:
                    group["speaker_config"] = body["speaker_config"]
                return httpx.Response(200, json=self._group(gid))
            if len(parts) == 2 and method == "DELETE":
                del self.groups[gid]
                return httpx.Response(200, json={"deleted": True})
            if parts[2] == "members" and len(parts) == 3 and method == "POST":
                group = self.groups[gid]
                cid = body["character_id"]
                group["members"].append(
                    {
                        "character_id": cid,
                        "name": f"Char {cid}",
                        "position": len(group["members"]),
                        "talkativeness": 0.5,
                        "muted": False,
                    }
                )
                return httpx.Response(201, json=group["members"][-1])
            if parts[2] == "members" and len(parts) == 4:
                cid = parts[3]
                group = self.groups[gid]
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
                    override = dict(
                        deep["member_overrides"].get(cid) or {}
                    )
                    override.update(body or {})
                    deep["member_overrides"][cid] = override
                    return httpx.Response(200, json=override)
                if verb == "peek" and method == "GET":
                    member = next(
                        m for m in self.groups[gid]["members"]
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
                if verb == "leave" and method == "POST":
                    return httpx.Response(200, json={"state": "absent"})
                if verb == "return" and method == "POST":
                    return httpx.Response(
                        200,
                        json={
                            "entries": [
                                {
                                    "speaker_name": "Char a",
                                    "excerpt": "while you were out",
                                }
                            ]
                        },
                    )
                if verb == "digest" and method == "GET":
                    return httpx.Response(200, json={"entries": []})
            if parts[2] == "messages":
                if method == "GET":
                    return httpx.Response(
                        200, json=self.messages.get(gid, [])
                    )
                if method == "POST":
                    row = {
                        "id": f"m{len(self.messages[gid]) + 1}",
                        "speaker_id": body["speaker"],
                        "speaker_name": (
                            "You" if body["speaker"] == "user"
                            else f"Char {body['speaker']}"
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
                        for m in self.groups[gid]["members"]
                    ],
                )
            if parts[2] == "next" and method == "POST":
                return httpx.Response(
                    200,
                    json={
                        "group_id": gid,
                        "strategy": self.groups[gid]["speaker_policy"],
                        "speaker_id": "a",
                        "speaker_name": "Char a",
                        "reason": "first in the order",
                        "message": None,
                    },
                )
            if parts[2] == "run" and method == "POST":
                return httpx.Response(
                    200,
                    json={
                        "group_id": gid,
                        "turns_run": body["turns"],
                        "results": [],
                    },
                )
        return httpx.Response(404, json={"detail": f"no road {method} {path}"})


def make_flow():
    engine = FakeEngine()
    session = DesktopSession("http://test", **{"bearer" + "_token": TOKEN})
    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    client = RunmalClient(session, http=http)
    return GroupFlow(client), engine


def test_create_list_and_lines():
    flow, _engine = make_flow()
    group = flow.create("  The Gate Watch ", ["a", "b"])
    assert group.name == "The Gate Watch"
    assert group.member_count == 2
    assert "2 members" in group_line(group)
    assert flow.groups()[0].id == group.id
    assert member_line(group.members[0]).startswith("Char a")


def test_say_and_transcript():
    flow, _engine = make_flow()
    group = flow.create("Room", ["a"])
    flow.say(group, "  mind the gate  ")
    lines = transcript_lines(flow.messages(group))
    assert lines == ["You: mind the gate"]


def test_member_settings_payload():
    flow, engine = make_flow()
    group = flow.create("Room", ["a", "b"])
    updated = flow.set_member(
        group, "b", talkativeness=0.9, muted=True
    )
    member = next(m for m in updated.members if m.character_id == "b")
    assert member.talkativeness == 0.9 and member.muted is True
    assert "muted" in member_line(member)
    patch = [
        c for c in engine.calls
        if c[0] == "PATCH" and c[1].endswith("/members/b")
    ]
    assert patch[-1][2] == {"talkativeness": 0.9, "muted": True}


def test_add_and_remove_member():
    flow, _engine = make_flow()
    group = flow.create("Room", ["a"])
    group = flow.add_member(group, "c")
    assert {m.character_id for m in group.members} == {"a", "c"}
    group = flow.remove_member(group, "a")
    assert [m.character_id for m in group.members] == ["c"]


def test_policy_words_and_set():
    flow, engine = make_flow()
    assert policy_label("list").startswith("In order")
    assert policy_label("manual").startswith("Manual")
    group = flow.create("Room", ["a"])
    updated = flow.set_policy(group, "list")
    assert updated.speaker_policy == "list"
    patch = [
        c for c in engine.calls
        if c[0] == "PATCH" and c[1] == f"/groups/{group.id}"
    ]
    assert patch[-1][2] == {"speaker_policy": "list"}


def test_compose_deepening_carries_state_and_unknown_keys():
    stored = {
        "generation_mode": "swap",
        "state": {"list_cursor": 3, "pool_spoken": ["a"]},
        "vendor_future": {"x": 1},
        "auto_mode": {"enabled": False, "max_turns": 3, "extra": "kept"},
        "member_overrides": {"a": {"activation": "never"}},
    }
    document = compose_deepening(
        stored,
        generation_mode="join",
        allow_self_responses=True,
        auto_enabled=True,
        auto_max_turns=5,
        join_prefix="[",
        join_suffix="]",
        scenario_override="  ",
    )
    assert document["generation_mode"] == "join"
    assert document["allow_self_responses"] is True
    assert document["auto_mode"] == {
        "enabled": True,
        "max_turns": 5,
        "extra": "kept",
    }
    assert document["scenario_override"] is None
    assert document["state"] == {"list_cursor": 3, "pool_spoken": ["a"]}
    assert document["vendor_future"] == {"x": 1}
    assert document["member_overrides"] == {"a": {"activation": "never"}}


def test_member_override_round_trip():
    flow, _engine = make_flow()
    group = flow.create("Room", ["a", "b"])
    saved = flow.set_member_override(
        group, "a", {"activation": "never", "lore_enabled": False}
    )
    assert saved["activation"] == "never"
    assert flow.member_override(group, "a")["lore_enabled"] is False
    assert flow.member_override(group, "b") == {}


def test_turn_and_run_words():
    words = turn_words(
        {
            "speaker_name": "Char a",
            "reason": "first in the order",
            "message": None,
        }
    )
    assert words == "Next speaker: Char a — first in the order"
    assert "No speaker was picked" in turn_words({"speaker_id": None})
    run = run_words(
        {
            "turns_run": 2,
            "results": [
                {"speaker_name": "Char a", "reason": "r1"},
                {"speaker_name": "Char b", "reason": "r2"},
            ],
        }
    )
    assert run.startswith("Ran 2 turns.")
    assert "Char b" in run


def test_presence_digest_peek_words():
    lines = presence_words(
        [
            {"name": "Char a", "state": "present"},
            {"name": "Char b", "state": "absent"},
        ]
    )
    assert lines[1] == "Char b: away"
    bool_lines = presence_words(
        [
            {"character_name": "Char a", "present": True},
            {"character_name": "Char b", "present": False,
             "missed_count": 3},
        ]
    )
    assert bool_lines == ["Char a: here", "Char b: away · 3 missed"]
    digest = digest_words(
        {"entries": [{"speaker_name": "Char a", "excerpt": "news"}]}
    )
    assert "Char a: news" in digest
    assert digest_words({}) == "Nothing was missed."
    peek = peek_words(
        {
            "member": {"name": "Char a"},
            "persona_source": "card",
            "effective_persona": "Card persona.",
        }
    )
    assert "their card" in peek and "Card persona." in peek


def test_next_turn_passes_flags():
    flow, engine = make_flow()
    group = flow.create("Room", ["a", "b"])
    result = flow.next_turn(
        group, manual_speaker_id="b", generate=True
    )
    assert result["speaker_name"] == "Char a"  # fake's canned pick
    call = [
        c for c in engine.calls if c[1].endswith("/next")
    ][-1]
    assert call[2] == {"generate": True, "manual_speaker_id": "b"}


def test_leave_and_return_digest():
    flow, _engine = make_flow()
    group = flow.create("Room", ["a"])
    flow.leave(group, "a")
    digest = flow.back(group, "a")
    assert "while you were out" in digest_words(digest)
    records = flow.presence(group)
    assert presence_words(records) == ["Char a: here (present)"]


def test_delete_group():
    flow, _engine = make_flow()
    group = flow.create("Room", ["a"])
    flow.delete(group)
    assert flow.groups() == []
