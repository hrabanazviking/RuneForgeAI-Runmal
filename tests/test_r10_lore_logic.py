"""R-10 acceptance (lore + persona logic): the Qt-free flows over
a fake transport — the schema-driven form model (fields follow
the P-042 census; ``activation_kind`` derived, never sent),
book/entry saves composing over the stored document (unknown
fields survive), scope assign/unassign payloads, preview verdict
words for every status, and the persona flow (user-name
default/set/clear, chat persona switch/clear)."""

import json

import httpx
import pytest

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.client.models import PreviewRow
from runmal.desktop.lore_logic import (
    LoreFlow,
    activation_kind_words,
    collect_fields,
    layer_words,
    schema_fields,
    scope_words,
    verdict_words,
)
from runmal.desktop.persona_logic import PersonaFlow

TOKEN = "test-" + "token-r10"

SCHEMA = {
    "slice": "P-042",
    "surfaces": {
        "book": [
            {"name": "name", "kind": "text", "options": []},
            {"name": "description", "kind": "longtext", "options": []},
            {"name": "scan_depth", "kind": "int", "options": []},
            {"name": "token_budget", "kind": "int_or_null", "options": []},
            {"name": "scan_mode", "kind": "select",
             "options": ["depth", "whole_chat"]},
            {"name": "scan_external_context", "kind": "bool", "options": []},
        ],
        "entry": [
            {"name": "name", "kind": "text", "options": []},
            {"name": "content", "kind": "longtext", "options": []},
            {"name": "keys", "kind": "keys", "options": []},
            {"name": "probability", "kind": "int", "options": []},
            {"name": "constant", "kind": "bool", "options": []},
            {"name": "vectorised", "kind": "bool", "options": []},
            {"name": "activation_kind", "kind": "derived",
             "options": ["constant", "selective", "vectorised"]},
            {"name": "vendor_future_field", "kind": "text", "options": []},
        ],
    },
}


class FakeEngine:
    """The lorebook + persona roads, in-memory."""

    def __init__(self):
        self.books: dict[str, dict] = {}
        self.entries: dict[str, dict] = {}
        self.scopes: list[dict] = []
        self.user_name = {"user_name": "User", "is_set": False}
        self.chat_persona: dict[str, dict | None] = {}
        self.requests: list[tuple[str, str, object]] = []
        self._seq = 0

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body = {}
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}
        self.requests.append((request.method, path, body))
        parts = [p for p in path.split("/") if p]

        if path == "/api/v1/user-name":
            if request.method == "GET":
                return httpx.Response(200, json=self.user_name)
            name = (body.get("user_name") or "").strip()
            self.user_name = {
                "user_name": name or "User",
                "is_set": bool(name),
            }
            return httpx.Response(200, json=self.user_name)

        if parts[:3] == ["api", "v1", "chats"] and len(parts) == 5:
            chat_id, tail = parts[3], parts[4]
            if tail == "persona":
                if request.method == "GET":
                    return httpx.Response(200, json={
                        "chat_id": chat_id,
                        "persona": self.chat_persona.get(chat_id),
                    })
                persona = None
                if body.get("character_id"):
                    persona = {
                        "character_id": body["character_id"],
                        "name": f"Char {body['character_id']}",
                    }
                self.chat_persona[chat_id] = persona
                return httpx.Response(
                    200, json={"chat_id": chat_id, "persona": persona})
            if tail == "lore-preview" and request.method == "POST":
                return httpx.Response(200, json={
                    "layered": True,
                    "scopes": [{
                        "scope": "character", "books": [
                            {"lorebook_id": "b1", "name": "World",
                             "via": "scope", "budget": None,
                             "position": 0}],
                        "budget": None, "tokens_used": 7,
                        "included": 1, "discarded": 0,
                    }],
                    "layers": {"character": {"entries": [{
                        "entry_id": "e1", "name": "Ember fact",
                        "status": "included",
                        "matched_primary": ["ember"],
                        "matched_secondary": [], "via": "keyword",
                        "tokens": 7, "discard_reason": None,
                        "scope": "character", "lorebook_id": "b1",
                    }]}},
                    "shadowed": [],
                    "tokens_used": 7,
                })

        if parts[:3] == ["api", "v1", "lorebooks"]:
            return self._lorebooks(request, parts, body)
        return httpx.Response(404, json={"detail": f"no road {path}"})

    def _lorebooks(self, request, parts, body):
        if len(parts) == 4 and parts[3] == "editor-schema":
            return httpx.Response(200, json=SCHEMA)
        if len(parts) == 3:
            if request.method == "GET":
                return httpx.Response(200, json=[
                    {**b, "entry_count": sum(
                        1 for e in self.entries.values()
                        if e["lorebook_id"] == b["id"])}
                    for b in self.books.values()
                ])
            if request.method == "POST":
                book = {
                    "id": self._id("b"), "name": body.get("name", ""),
                    "description": body.get("description", ""),
                    "scan_depth": body.get("scan_depth", 4),
                    "token_budget": body.get("token_budget"),
                    "scan_mode": body.get("scan_mode", "depth"),
                    "scan_external_context": body.get(
                        "scan_external_context", False),
                }
                self.books[book["id"]] = book
                return httpx.Response(201, json={**book, "entry_count": 0})
        if len(parts) == 4:
            book_id = parts[3]
            book = self.books.get(book_id)
            if book is None:
                return httpx.Response(404, json={"detail": "no book"})
            if request.method == "GET":
                return httpx.Response(200, json={**book, "entry_count": 0})
            if request.method == "PATCH":
                book.update(body)
                return httpx.Response(200, json={**book, "entry_count": 0})
            if request.method == "DELETE":
                del self.books[book_id]
                return httpx.Response(200, json={"deleted": True})
        if len(parts) == 5 and parts[4] == "entries":
            book_id = parts[3]
            if request.method == "GET":
                return httpx.Response(200, json=[
                    e for e in self.entries.values()
                    if e["lorebook_id"] == book_id
                ])
            if request.method == "POST":
                entry = {
                    "id": self._id("e"), "lorebook_id": book_id,
                    "name": "", "content": "", "keys": [],
                    "secondary_keys": [], "selective_logic": "and_any",
                    "inclusion_group": "", "group_weight": 100,
                    "probability": 100, "priority": 100,
                    "position": "before_char", "depth": None,
                    "role": "system", "enabled": True, "constant": False,
                    "vectorised": False, "activation_kind": "keyword",
                    "case_sensitive": False, "whole_word": True,
                    "sticky_prompts": 0, "cooldown_prompts": 0,
                    "delay_prompts": 0,
                }
                entry.update(body)
                entry["activation_kind"] = (
                    "constant" if entry["constant"]
                    else "vectorised" if entry["vectorised"] else "keyword"
                )
                self.entries[entry["id"]] = entry
                return httpx.Response(201, json=entry)
        if len(parts) == 6 and parts[4] == "entries":
            entry = self.entries.get(parts[5])
            if entry is None:
                return httpx.Response(404, json={"detail": "no entry"})
            if request.method == "PATCH":
                entry.update(body)
                return httpx.Response(200, json=entry)
            if request.method == "DELETE":
                del self.entries[parts[5]]
                return httpx.Response(200, json={"deleted": True})
        if len(parts) == 5 and parts[4] == "scopes":
            book_id = parts[3]
            return httpx.Response(200, json={
                "lorebook_id": book_id,
                "scopes": [s for s in self.scopes
                           if s["lorebook_id"] == book_id],
            })
        if len(parts) == 5 and parts[4] == "scope":
            book_id = parts[3]
            if request.method == "PUT":
                scope = {
                    "id": self._id("s"), "lorebook_id": book_id,
                    "scope_kind": body.get("scope_kind"),
                    "owner_id": body.get("owner_id"),
                    "token_budget": body.get("token_budget"),
                    "position": body.get("position", 0),
                    "lorebook": {"name": self.books[book_id]["name"]},
                }
                self.scopes.append(scope)
                return httpx.Response(201, json=scope)
            if request.method == "DELETE":
                kind = request.url.params.get("scope_kind")
                owner = request.url.params.get("owner_id")
                self.scopes = [
                    s for s in self.scopes
                    if not (s["lorebook_id"] == book_id
                            and s["scope_kind"] == kind
                            and s["owner_id"] == owner)
                ]
                return httpx.Response(200, json={"deleted": True})
        if len(parts) == 5 and parts[4] == "preview":
            rows = []
            for entry in self.entries.values():
                if entry["lorebook_id"] != parts[3]:
                    continue
                hit = any(
                    key.lower() in message.lower()
                    for key in entry["keys"]
                    for message in body.get("messages", [])
                )
                rows.append({
                    "entry_id": entry["id"], "name": entry["name"],
                    "status": "included" if hit else "not_triggered",
                    "matched_primary": list(entry["keys"]) if hit else [],
                    "matched_secondary": [], "via": "keyword" if hit else None,
                    "tokens": 5 if hit else None, "discard_reason": None,
                })
            return httpx.Response(200, json={"entries": rows})
        return httpx.Response(404, json={"detail": "no lore road"})


def make_flow():
    engine = FakeEngine()
    session = DesktopSession("http://test", **{"bearer" + "_token": TOKEN})
    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    client = RunmalClient(session, http=http)
    return LoreFlow(client), PersonaFlow(client), engine


# ------------------------------------------------------------- schema


def test_schema_fields_follow_the_census() -> None:
    flow, _persona, _engine = make_flow()
    schema = flow.schema()
    book_fields = schema_fields(schema, "book")
    assert [f.name for f in book_fields] == [
        "name", "description", "scan_depth", "token_budget",
        "scan_mode", "scan_external_context",
    ]
    assert book_fields[4].options == ["depth", "whole_chat"]
    entry_fields = schema_fields(schema, "entry")
    derived = [f for f in entry_fields if f.derived]
    assert [f.name for f in derived] == ["activation_kind"]
    assert schema_fields({}, "book") == []


def test_collect_fields_carries_unknown_and_skips_derived() -> None:
    flow, _persona, _engine = make_flow()
    fields = schema_fields(flow.schema(), "entry")
    base = {"name": "Old", "vendor_future_field": "keep-me",
            "activation_kind": "keyword", "future_blob": {"x": 1}}
    out = collect_fields(fields, {"name": "New"}, base)
    assert out["name"] == "New"
    assert out["vendor_future_field"] == "keep-me"
    assert out["future_blob"] == {"x": 1}
    # The derived field is the stored document's own business on a
    # raw collect — the FLOW strips it before sending (next test).


def test_activation_kind_words() -> None:
    assert activation_kind_words({"constant": True}) == "constant (always on)"
    assert activation_kind_words({"vectorised": True}) == (
        "vectorised (similarity)")
    assert activation_kind_words({}) == "keyword"


# -------------------------------------------------------------- books


def test_book_create_and_update_payloads() -> None:
    flow, _persona, engine = make_flow()
    fields = schema_fields(flow.schema(), "book")
    book = flow.save_book(None, fields, {
        "name": "World", "description": "d", "scan_depth": 4,
        "token_budget": None, "scan_mode": "depth",
        "scan_external_context": False,
    }, None)
    assert book.name == "World"
    posts = [r for r in engine.requests if r[0] == "POST"]
    assert posts[0][2]["name"] == "World"
    # No-change save sends nothing.
    same = flow.save_book(book.id, fields, book.fields_dict(), book)
    assert same.id == book.id
    assert not [r for r in engine.requests if r[0] == "PATCH"]
    # A change sends only the changed field.
    updated = flow.save_book(book.id, fields, {
        **book.fields_dict(), "scan_depth": 9,
    }, book)
    assert updated.scan_depth == 9
    patches = [r for r in engine.requests if r[0] == "PATCH"]
    assert patches[0][2] == {"scan_depth": 9}


def test_book_validation_words() -> None:
    flow, _persona, _engine = make_flow()
    fields = schema_fields(flow.schema(), "book")
    with pytest.raises(ClientError, match="needs a name"):
        flow.save_book(None, fields, {"name": "  "}, None)
    with pytest.raises(ClientError, match="Scan depth"):
        flow.save_book(None, fields, {"name": "X", "scan_depth": 0}, None)


# ------------------------------------------------------------ entries


def test_entry_save_strips_identity_and_derived() -> None:
    flow, _persona, engine = make_flow()
    fields = schema_fields(flow.schema(), "entry")
    entry = flow.save_entry("bX", None, fields, {
        "name": "Ember fact", "content": "Embers remember.",
        "keys": ["ember"], "probability": 100, "constant": False,
        "vectorised": False,
    }, None)
    assert entry.name == "Ember fact"
    posts = [r for r in engine.requests
             if r[0] == "POST" and r[1].endswith("/entries")]
    sent = posts[0][2]
    assert "activation_kind" not in sent
    assert "id" not in sent and "lorebook_id" not in sent
    assert sent["keys"] == ["ember"]


def test_entry_validation_words() -> None:
    flow, _persona, _engine = make_flow()
    fields = schema_fields(flow.schema(), "entry")
    with pytest.raises(ClientError, match="Probability"):
        flow.save_entry("bX", None, fields, {"probability": 140}, None)


# ------------------------------------------------------------- scopes


def test_scope_assign_and_unassign() -> None:
    flow, _persona, engine = make_flow()
    fields = schema_fields(flow.schema(), "book")
    book = flow.save_book(None, fields, {"name": "World"}, None)
    with pytest.raises(ClientError, match="needs an owner"):
        flow.assign_scope(book.id, "character", None)
    scope = flow.assign_scope(book.id, "character", "k1", token_budget=50)
    assert scope.scope_kind == "character"
    assert scope_words(scope, "Gate Keeper") == (
        "Character (chats with this character) — Gate Keeper"
        " · budget 50 tokens"
    )
    global_scope = flow.assign_scope(book.id, "global", None)
    assert global_scope.owner_id is None
    assert flow.unassign_scope(book.id, "character", "k1") is True
    remaining = flow.list_scopes(book.id)
    assert [s.scope_kind for s in remaining] == ["global"]


# ------------------------------------------------------------ preview


def test_preview_words_for_every_status() -> None:
    def row(status, **kw):
        return PreviewRow(entry_id="e1", name="Ember fact",
                          status=status, **kw)

    assert verdict_words(row("included", matched_primary=["ember"],
                             via="keyword", tokens=7)) == (
        "Ember fact: Included · matched ember · via keyword · 7 tokens"
    )
    assert verdict_words(row("not_triggered")) == "Ember fact: Not triggered"
    assert verdict_words(row("discarded", tokens=9,
                             discard_reason="over budget")) == (
        "Ember fact: Discarded · 9 tokens · reason: over budget"
    )
    assert verdict_words(row("disabled")) == "Ember fact: Disabled"
    assert verdict_words(row("group_excluded")) == (
        "Ember fact: Excluded by its inclusion group"
    )


def test_book_preview_and_layered_words() -> None:
    flow, _persona, _engine = make_flow()
    book_fields = schema_fields(flow.schema(), "book")
    entry_fields = schema_fields(flow.schema(), "entry")
    book = flow.save_book(None, book_fields, {"name": "World"}, None)
    flow.save_entry(book.id, None, entry_fields, {
        "name": "Ember fact", "content": "Embers remember.",
        "keys": ["ember"],
    }, None)
    rows = flow.preview_book(book.id, ["tell me of the ember"])
    assert rows[0].status == "included"
    rows = flow.preview_book(book.id, ["nothing relevant"])
    assert rows[0].status == "not_triggered"
    rows, summaries, shadowed = flow.preview_chat(
        "c1", ["tell me of the ember"])
    assert rows[0].status == "included"
    assert rows[0].scope == "character"
    assert layer_words(summaries[0]) == (
        "Character (chats with this character): World"
        " · 7 tokens used · 1 included · 0 discarded"
    )
    assert shadowed == []


# ------------------------------------------------------------ persona


def test_persona_user_name_round_trip() -> None:
    _lore, persona, _engine = make_flow()
    state = persona.user_name()
    assert state.name == "User" and state.is_set is False
    assert "built-in default" in state.words
    state = persona.set_user_name("Volmarr")
    assert state.name == "Volmarr" and state.is_set is True
    state = persona.set_user_name("")
    assert state.name == "User" and state.is_set is False


def test_persona_chat_switch_and_clear() -> None:
    _lore, persona, engine = make_flow()
    view = persona.set_chat_persona("c1", "k9")
    assert view.present and view.character_id == "k9"
    view = persona.chat_persona("c1")
    assert view.name == "Char k9"
    view = persona.set_chat_persona("c1", None)
    assert view.present is False
    with pytest.raises(ClientError, match="Open a chat"):
        persona.set_chat_persona("", "k9")
