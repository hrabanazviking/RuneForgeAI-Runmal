"""R-12 acceptance (logic): the four Qt-free flows over a fake
transport — memory search/detail words, scenario compose
(authored fields over the stored definition, structured
sections carried), organisation + binding verbs, inspector
ledger/slot/lore words and the generic document renderer, and
the compose/macros words."""

import httpx

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.compose_logic import (
    ComposeFlow,
    compose_words,
    expansion_words,
    macro_line,
)
from runmal.desktop.inspector_logic import (
    InspectorFlow,
    document_words,
    ledger_words,
    lore_account_words,
    slot_lines,
)
from runmal.desktop.memory_logic import MemoryFlow, detail_words, memory_line
from runmal.desktop.scenario_logic import (
    ScenarioFlow,
    binding_words,
    bindings_lines,
    carried_words,
    compose_definition,
    scenario_line,
)

TOKEN = "test-" + "token-r12"

MEMORY = {
    "id": "m1",
    "kind": "fact",
    "content": "Volmarr keeps bees.",
    "state": "active",
    "scope": "witnesses",
    "subject": "Volmarr",
    "salience": 0.8,
    "stability": 0.5,
    "confidence": 0.9,
    "pinned": True,
    "witnesses": ["char-a"],
    "recall_count": 2,
    "sources": [
        {"kind": "message", "extractor": "fake-fx", "ref": "m1"}
    ],
    "graph": {"nodes": [{"id": "m1"}], "edges": []},
}

SCENARIO_DEF = {
    "name": "Gate Watch",
    "description": "A night at the pass.",
    "scenario_text": "Snow closes in.",
    "flow": "chat",
    "roles": [{"name": "Keeper"}],
    "bootstrap_messages": [{"role": "assistant", "content": "Well met."}],
    "initial_flags": {"gate_open": True},
}


class FakeEngine:
    """The memory / scenario / inspector / tools roads."""

    def __init__(self):
        self.memories = [dict(MEMORY)]
        self.scenarios: dict[str, dict] = {}
        self.bindings: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict | None]] = []
        self._seq = 0

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

        if parts == ["memories"] and method == "GET":
            q = request.url.params.get("q", "").lower()
            rows = [
                m for m in self.memories
                if not q or q in m["content"].lower()
            ]
            return httpx.Response(200, json={"memories": rows})
        if len(parts) == 2 and parts[0] == "memories" and method == "GET":
            row = next(m for m in self.memories if m["id"] == parts[1])
            return httpx.Response(200, json=row)
        if parts == ["scenarios"]:
            if method == "GET":
                rows = [
                    {
                        "id": sid,
                        "name": rec["definition"]["name"],
                        "definition": rec["definition"],
                        "revision": rec["revision"],
                        "source_format": "native",
                        "tags": rec.get("tags", []),
                        "is_favourite": rec.get("is_favourite", False),
                        "role_count": len(
                            rec["definition"].get("roles") or []
                        ),
                    }
                    for sid, rec in self.scenarios.items()
                ]
                return httpx.Response(
                    200, json={"scenarios": rows, "total": len(rows)}
                )
            if method == "POST":
                self._seq += 1
                sid = f"s{self._seq}"
                self.scenarios[sid] = {
                    "definition": body, "revision": 1,
                    "tags": [], "is_favourite": False,
                }
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
        if parts[:2] == ["scenarios", "bindings"]:
            if len(parts) == 2 and method == "GET":
                rows = list(self.bindings.values())
                return httpx.Response(
                    200, json={"bindings": rows, "total": len(rows)}
                )
            if len(parts) == 3:
                chat_id = parts[2]
                if method == "GET":
                    binding = self.bindings.get(chat_id)
                    if binding is None:
                        return httpx.Response(
                            404, json={"detail": "binding not found"}
                        )
                    return httpx.Response(200, json=binding)
                if method == "DELETE":
                    self.bindings.pop(chat_id, None)
                    return httpx.Response(200, json={"deleted": True})
        if len(parts) >= 2 and parts[0] == "scenarios":
            sid = parts[1]
            if len(parts) == 2:
                rec = self.scenarios[sid]
                if method == "GET":
                    return httpx.Response(
                        200,
                        json={
                            "id": sid,
                            "name": rec["definition"]["name"],
                            "definition": rec["definition"],
                            "revision": rec["revision"],
                            "source_format": "native",
                            "tags": rec["tags"],
                            "is_favourite": rec["is_favourite"],
                        },
                    )
                if method == "PUT":
                    rec["definition"] = body
                    rec["revision"] += 1
                    return httpx.Response(
                        200,
                        json={
                            "id": sid,
                            "name": body["name"],
                            "definition": body,
                            "revision": rec["revision"],
                            "source_format": "native",
                        },
                    )
                if method == "DELETE":
                    del self.scenarios[sid]
                    return httpx.Response(200, json={"deleted": True})
            if len(parts) == 3 and parts[2] == "duplicate" and method == "POST":
                self._seq += 1
                nid = f"s{self._seq}"
                import copy

                self.scenarios[nid] = copy.deepcopy(self.scenarios[sid])
                self.scenarios[nid]["definition"]["name"] += " (copy)"
                return httpx.Response(
                    201,
                    json={
                        "id": nid,
                        "name": self.scenarios[nid]["definition"]["name"],
                        "definition": self.scenarios[nid]["definition"],
                        "revision": 1,
                        "source_format": "native",
                    },
                )
            if len(parts) == 3 and parts[2] == "favourite" and method == "PUT":
                self.scenarios[sid]["is_favourite"] = body["is_favourite"]
                return httpx.Response(200, json={})
            if len(parts) == 3 and parts[2] == "tags" and method == "PUT":
                self.scenarios[sid]["tags"] = body["tags"]
                return httpx.Response(200, json={})
            if len(parts) == 3 and parts[2] == "bind" and method == "POST":
                self.bindings[body["chat_id"]] = {
                    "chat_id": body["chat_id"],
                    "definition_id": sid,
                    "definition_name": self.scenarios[sid]["definition"]["name"],
                    "definition_exists": True,
                }
                return httpx.Response(201, json=self.bindings[body["chat_id"]])
        if parts[:2] == ["inspector", "chats"] and method == "GET":
            doc = {"chat": {"title": "Gate chat"}, "sections": {}}
            if len(parts) == 4 and parts[3] == "events":
                doc = {"total": 3, "kinds": {"message": 2, "flag": 1}}
            if len(parts) == 4 and parts[3] == "reasoning":
                doc = {"messages": 2, "statuses": {"recorded": 2}}
            return httpx.Response(200, json=doc)
        if parts == ["debug", "prompt-inspect"] and method == "POST":
            return httpx.Response(
                200,
                json={
                    "ledger": {
                        "context_limit": 4096,
                        "reserved_response": 512,
                        "overhead": 10,
                        "input_budget": 3574,
                        "total_input_tokens": 120,
                        "remaining_input_tokens": 3454,
                    },
                    "slots": [
                        {
                            "kind": "main_system",
                            "status": "included",
                            "tokens": 40,
                            "reason": "always present",
                        },
                        {
                            "kind": "lore_before",
                            "status": "included",
                            "tokens": 12,
                            "reason": None,
                            "trigger": "ember",
                            "provenance": "lorebook:Gate World@character",
                        },
                        {
                            "kind": "lore_after",
                            "status": "discarded",
                            "tokens": 30,
                            "reason": "over the lore budget",
                        },
                    ],
                    "lore_account": {
                        "tokens_used": 12,
                        "discarded_tokens": 30,
                        "entries": [{"slot_id": "lore/character/x"}],
                        "by_provenance": {
                            "lorebook:Gate World@character": {
                                "tokens_used": 12,
                                "discarded_tokens": 30,
                                "entries": 1,
                            }
                        },
                    },
                },
            )
        if parts == ["tools", "macros"] and method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "char",
                        "kind": "name",
                        "description": "The character's name",
                        "syntax": "{{char}}",
                        "example": "{{char}}",
                    }
                ],
            )
        if parts == ["tools", "macros", "expand"] and method == "POST":
            text = body["text"].replace("{{char}}", body["char"])
            text = text.replace("{{user}}", body["user"])
            return httpx.Response(200, json={"text": text})
        if parts == ["tools", "compose"] and method == "POST":
            messages = []
            if body["system"]:
                messages.append({"role": "system", "content": body["system"]})
            for line in body["history"]:
                messages.append({"role": "user", "content": line})
            return httpx.Response(
                200,
                json={
                    "messages": messages,
                    "ledger": {
                        "context_limit": body["context_limit"],
                        "total_input_tokens": 10,
                    },
                },
            )
        return httpx.Response(404, json={"detail": f"no road {method} {path}"})


def make_client():
    engine = FakeEngine()
    session = DesktopSession("http://test", **{"bearer" + "_token": TOKEN})
    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    return RunmalClient(session, http=http), engine


def test_memory_search_and_detail_words():
    client, _engine = make_client()
    flow = MemoryFlow(client)
    rows = flow.search(q="bees")
    assert len(rows) == 1 and rows[0].pinned is True
    assert "pinned" in memory_line(rows[0])
    words = detail_words(flow.detail("m1"))
    assert "Kind: fact" in words
    assert "extracted by fake-fx" in words
    assert "Provenance graph: 1 node(s), 0 edge(s)." in words
    assert flow.search(q="absent") == []


def test_scenario_compose_carries_structure():
    document = compose_definition(
        dict(SCENARIO_DEF), {"name": "Renamed", "scenario_text": "Rain."}
    )
    assert document["name"] == "Renamed"
    assert document["scenario_text"] == "Rain."
    assert document["roles"] == SCENARIO_DEF["roles"]
    assert document["bootstrap_messages"] == SCENARIO_DEF["bootstrap_messages"]
    words = carried_words(SCENARIO_DEF)
    assert "roles: 1" in words and "bootstrap messages: 1" in words
    assert "initial flags: 1" in words


def test_scenario_flow_crud_org_and_bindings():
    client, engine = make_client()
    flow = ScenarioFlow(client)
    created = flow.create(dict(SCENARIO_DEF))
    assert created.id == "s1"
    assert "1 role(s)" in scenario_line(flow.library()[0])
    flow.set_tags(created, ["gate", "night"])
    flow.set_favourite(created, True)
    assert engine.scenarios["s1"]["tags"] == ["gate", "night"]
    assert engine.scenarios["s1"]["is_favourite"] is True
    binding = flow.bind(created, "chat-9")
    assert binding["definition_name"] == "Gate Watch"
    assert "Bound scenario: Gate Watch" in binding_words(
        flow.chat_binding("chat-9")
    )
    lines = bindings_lines(flow.bindings())
    assert lines and "Gate Watch" in lines[0]
    flow.unbind("chat-9")
    assert flow.bindings() == []
    clone = flow.duplicate(created)
    assert clone.name.endswith("(copy)")
    flow.delete(created)
    assert [s.id for s in flow.library()] == [clone.id]


def test_inspector_words():
    client, _engine = make_client()
    flow = InspectorFlow(client)
    trace = flow.trace("chat-1", messages=["hello"])
    ledger = ledger_words(trace)
    assert "input budget 3574" in ledger and "remaining 3454" in ledger
    lines = slot_lines(trace)
    assert lines[0].startswith("main_system — Included")
    assert 'triggered by "ember"' in lines[1]
    assert "from lorebook:Gate World@character" in lines[1]
    assert "over the lore budget" in lines[2]
    account = lore_account_words(trace)
    assert account[0].startswith("Lore: 12 tokens used")
    assert "Gate World" in account[1]


def test_document_words_renderer():
    words = document_words(
        {"chat": {"title": "Gate"}, "counts": [1, 2], "ok": True,
         "empty": None}
    )
    text = "\n".join(words)
    assert "title: Gate" in text
    assert "ok: yes" in text
    assert "empty: —" in text


def test_compose_and_macros_words():
    client, _engine = make_client()
    flow = ComposeFlow(client)
    macros = flow.macros()
    assert macro_line(macros[0]).startswith("{{char}}")
    expanded = flow.expand("{{char}} greets {{user}}", char="Keeper", user="Volmarr")
    assert expansion_words(expanded) == "Keeper greets Volmarr"
    result = flow.compose(system="Be kind.", history=["Hello"])
    words = compose_words(result)
    assert "[system] Be kind." in words
    assert "total input tokens 10" in words
