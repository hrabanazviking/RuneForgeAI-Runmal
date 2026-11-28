"""W-11 acceptance: the entry-box sweep (Volmarr's final slice).

Every data entry box in the web face gets four things:
(1) auto-expanding size, (2) Copy + Paste buttons with no
confirmation, (3) a Clear button that asks "are you sure?"
first, (4) auto-saved drafts. ONE shared control set:
static/entrybox.js enhances every .entry-box element (the
pwtoggle.js precedent, MutationObserver included); the draft
roads are webface-local and session-only (w11.py + the store's
drafts table, keyed by account + draft key).

Per-kind law asserted here and in the DOM battery:
- textarea / text-like inputs: all four parts (drafts only
  with a data-draft-key).
- password inputs: NO companions, NO drafts (a secret is never
  button-copied or draft-saved; W-05B's toggle lives there).
- number inputs / selects: no companions, no grow, no drafts.
- checkbox / file inputs: ruled out of scope BY KIND in the
  slice report - nothing to copy, grow, or draft; the W-10
  inventory's 17 such fields keep their house confirm patterns.

Restore semantics (stated in w11.py): a draft fills a box only
when the box is still empty - a value the page itself loaded
is never clobbered. Retire points: the page's successful
submit/send for the box, and a confirmed Clear.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from runmal.webface import w11
from runmal.webface.app import WebfaceApp, make_handler
from runmal.webface.store import Store

REPO = Path(__file__).parent.parent
STATIC = REPO / "src" / "runmal" / "webface" / "static"
SCRIPT_TAG = '<script src="/static/entrybox.js"></script>'


class _StubEngine:
    def list_characters(self):
        return [{"id": "char-1", "name": "Stub Character"}]

    def list_chats(self):
        return []

    def list_messages(self, chat_id):
        return []


@pytest.fixture()
def face(tmp_path):
    store = Store(tmp_path)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(WebfaceApp(store, _StubEngine())))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, store
    server.shutdown()


def _client(base):
    return httpx.Client(base_url=base, follow_redirects=False,
                        trust_env=False)


def _register(client, name="w11user", pw="long-enough-1"):
    reg = client.post("/register", data={"username": name, "password": pw})
    assert reg.status_code == 303
    return client


# ------------------------------------------------ unit: draft store


def _user(store, name="drafter"):
    return store.create_user(name, "hash")


def test_store_draft_save_restore_retire(tmp_path):
    store = Store(tmp_path)
    user = _user(store)
    assert store.get_draft(user["id"], "chat:c1:composer") is None
    store.set_draft(user["id"], "chat:c1:composer", "half a thought")
    assert store.get_draft(user["id"], "chat:c1:composer") == "half a thought"
    store.set_draft(user["id"], "chat:c1:composer", "a fuller thought")
    assert store.get_draft(user["id"], "chat:c1:composer") == "a fuller thought"
    assert store.delete_draft(user["id"], "chat:c1:composer") is True
    assert store.get_draft(user["id"], "chat:c1:composer") is None
    assert store.delete_draft(user["id"], "chat:c1:composer") is False


def test_store_draft_empty_text_retires_and_lists_no_ghosts(tmp_path):
    store = Store(tmp_path)
    user = _user(store)
    store.set_draft(user["id"], "k", "words")
    store.set_draft(user["id"], "k", "")
    assert store.get_draft(user["id"], "k") is None
    assert store.list_draft_keys(user["id"]) == []


def test_store_draft_per_account_and_per_key_isolation(tmp_path):
    store = Store(tmp_path)
    a = _user(store, "anna")
    b = _user(store, "boris")
    store.set_draft(a["id"], "chat:c1:composer", "anna's words")
    store.set_draft(a["id"], "chat:c2:composer", "other chat")
    store.set_draft(b["id"], "chat:c1:composer", "boris's words")
    assert store.get_draft(a["id"], "chat:c1:composer") == "anna's words"
    assert store.get_draft(b["id"], "chat:c1:composer") == "boris's words"
    assert store.get_draft(b["id"], "chat:c2:composer") is None
    keys = {r["draft_key"] for r in store.list_draft_keys(a["id"])}
    assert keys == {"chat:c1:composer", "chat:c2:composer"}


def test_w11_key_and_size_validation(tmp_path):
    store = Store(tmp_path)
    user = _user(store)
    ok, payload = w11.save_draft(store, user["id"], "  chat:c1:composer ", "x")
    assert ok and payload["key"] == "chat:c1:composer"
    ok, payload = w11.save_draft(store, user["id"], "", "x")
    assert not ok and "key" in payload["error"]
    ok, payload = w11.save_draft(store, user["id"], "k" * 201, "x")
    assert not ok
    ok, payload = w11.save_draft(store, user["id"], "k", "x" * (w11.MAX_DRAFT_TEXT + 1))
    assert not ok and "too long" in payload["error"]
    assert w11.get_draft(store, user["id"], "bad\nkey") == {"key": None, "text": None}
    ok, payload = w11.save_draft(store, user["id"], "k", "")
    assert ok and payload["saved"] is False  # empty retires, no ghost


# ------------------------------------------------ HTTP: draft roads


def test_http_drafts_require_a_session(face):
    base, _store = face
    with _client(base) as anon:
        assert anon.get("/webface/drafts").status_code == 401
        assert anon.get("/webface/draft", params={"key": "k"}).status_code == 401
        assert anon.put("/webface/draft", json={"key": "k", "text": "x"}).status_code == 401
        assert anon.request("DELETE", "/webface/draft", json={"key": "k"}).status_code == 401


def test_http_draft_round_trip_and_isolation(face):
    base, _store = face
    with _client(base) as c:
        _register(c)
        put = c.put("/webface/draft", json={
            "key": "chat:c1:composer", "text": "unsent brilliance"})
        assert put.status_code == 200 and put.json()["saved"] is True
        got = c.get("/webface/draft", params={"key": "chat:c1:composer"})
        assert got.json() == {"key": "chat:c1:composer", "text": "unsent brilliance"}
        listing = c.get("/webface/drafts")
        assert [d["draft_key"] for d in listing.json()["drafts"]] == ["chat:c1:composer"]
        # a second account sees none of it
        with _client(base) as other:
            _register(other, name="w11other")
            got2 = other.get("/webface/draft", params={"key": "chat:c1:composer"})
            assert got2.json()["text"] is None
            assert other.get("/webface/drafts").json()["drafts"] == []
        # retire by DELETE, and by saving empty
        gone = c.request("DELETE", "/webface/draft", json={"key": "chat:c1:composer"})
        assert gone.json()["retired"] is True
        assert c.get("/webface/draft", params={"key": "chat:c1:composer"}).json()["text"] is None
        c.put("/webface/draft", json={"key": "k2", "text": "temp"})
        c.put("/webface/draft", json={"key": "k2", "text": ""})
        assert c.get("/webface/draft", params={"key": "k2"}).json()["text"] is None
        bad = c.put("/webface/draft", json={"key": "", "text": "x"})
        assert bad.status_code == 422


def test_http_agent_token_is_not_a_session_for_drafts(face):
    base, _store = face
    with _client(base) as c:
        _register(c)
        made = c.post("/account/agent-tokens", data={"name": "Yrsa"})
        found = re.findall(r"rma_[A-Za-z0-9_\-]+", made.text)
        assert len(found) == 1
        auth = {"Authorization": f"Bearer {found[0]}"}
    with _client(base) as agent_only:
        assert agent_only.get("/webface/draft", params={"key": "k"},
                              headers=auth).status_code == 401
        assert agent_only.put("/webface/draft", headers=auth,
                              json={"key": "k", "text": "x"}).status_code == 401
        assert agent_only.get("/webface/drafts", headers=auth).status_code == 401


# --------------------------------------- served markup + factories


def test_served_markup_loads_entrybox_and_companions_ride(face):
    base, _store = face
    with _client(base) as c:
        for path in ("/", "/login", "/register"):
            page = c.get(path)
            assert page.status_code == 200 and SCRIPT_TAG in page.text, path
        script = c.get("/static/entrybox.js")
        assert script.status_code == 200
        text = script.text
        for needle in ("MutationObserver", "RunmalEntryBox", "entry-box",
                       "Are you sure?", "Ctrl+C copies it", "Ctrl+V pastes as usual",
                       "Draft saved", "data-draft-key", "/webface/draft"):
            assert needle in text, needle
    with _client(base) as c:
        _register(c)
        for path in ("/chat", "/characters", "/groups", "/lorebooks",
                     "/tools", "/account"):
            page = c.get(path)
            assert page.status_code == 200 and SCRIPT_TAG in page.text, path
        chat = c.get("/chat")
        assert 'id="composer"' in chat.text and 'class="entry-box"' in chat.text
        tools = c.get("/tools")
        assert 'data-draft-key="tools:context:system"' in tools.text


def test_js_factories_carry_entry_box():
    expectations = {
        "characters.js": ["entry-box", "character:", "data-draft-key"],
        "chat.js": ["entry-box", ":composer", "authors-note", "data-draft-key"],
        "connections.js": ["entry-box"],
        "firstrun.js": ["entry-box"],
        "generation.js": ["entry-box"],
        "groups.js": ["entry-box", "group:", ":say", "data-draft-key"],
        "plugins.js": ["entry-box"],
        "lorebooks.js": ["entry-box", "lorebook:", "data-draft-key"],
        "scenarios.js": ["entry-box", "scenario:", "data-draft-key"],
    }
    for name, needles in expectations.items():
        text = (STATIC / name).read_text()
        for needle in needles:
            assert needle in text, f"{name}: missing {needle}"


# --------------------------------------- behaviour: headless DOM

_DOM_TEST = r"""
const fs = require("fs");
const { JSDOM } = require("jsdom");
const src = fs.readFileSync(process.argv[2], "utf8");
const dom = new JSDOM(`<!DOCTYPE html><body>
<textarea id="ta1" class="entry-box" data-draft-key="chat:c1:composer" rows="2"></textarea>
<textarea id="ta2" class="entry-box"
 data-draft-key="chat:c1:edit:m1" rows="2">saved content</textarea>
<input id="tx1" class="entry-box" type="text" value="hello">
<input id="pw1" class="entry-box" type="password" value="secret">
<input id="num1" class="entry-box" type="number" value="3">
<select id="sel1" class="entry-box"><option>a</option></select>
<input id="cb1" class="entry-box" type="checkbox">
<div id="dyn"></div></body>`,
  { runScripts: "outside-only", url: "http://x/", pretendToBeVisual: true });
const { window } = dom;
const calls = [];
const drafts = { "chat:c1:composer": "draft words", "chat:c1:edit:m1": "DRAFT MUST NOT WIN" };
window.fetch = (url, opts) => {
  const method = (opts && opts.method) || "GET";
  calls.push(method + " " + url + " " + ((opts && opts.body) || ""));
  if (method === "GET") {
    const key = decodeURIComponent(url.split("key=")[1] || "");
    return Promise.resolve({ ok: true,
      json: () => Promise.resolve({ key, text: drafts[key] != null ? drafts[key] : null }) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};
Object.defineProperty(window.HTMLTextAreaElement.prototype, "scrollHeight",
  { configurable: true, get() { return 20 + (this.value || "").length * 2; } });
window.eval(src);
const fails = [];
const ok = (n, c) => { if (!c) fails.push(n); console.log((c ? "PASS " : "FAIL ") + n); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
window.addEventListener("load", () => setTimeout(async () => {
  const EB = window.RunmalEntryBox;
  const d = window.document;
  ok("shared control present", !!EB);
  const ta1 = d.getElementById("ta1"), ta2 = d.getElementById("ta2");
  await sleep(80);
  ok("textarea wrapped with tools",
     !!ta1.closest(".entrybox-wrap") && !!ta1.parentNode.querySelector(".eb-copy"));
  ok("three companions present",
     !!ta1.parentNode.querySelector(".eb-paste") && !!ta1.parentNode.querySelector(".eb-clear"));
  ok("draft status word element present", !!ta1.parentNode.querySelector(".entrybox-status"));
  ok("draft restores into an EMPTY box", ta1.value === "draft words");
  ok("draft does NOT clobber a loaded value", ta2.value === "saved content");
  const tx1 = d.getElementById("tx1");
  ok("text input gets companions", !!tx1.closest(".entrybox-wrap"));
  ok("password gets NO companions", !d.getElementById("pw1").closest(".entrybox-wrap"));
  ok("number gets NO companions", !d.getElementById("num1").closest(".entrybox-wrap"));
  ok("select gets NO companions", !d.getElementById("sel1").closest(".entrybox-wrap"));
  ok("checkbox gets NO companions", !d.getElementById("cb1").closest(".entrybox-wrap"));
  // auto-grow: height follows content on input
  const before = ta1.style.height;
  ta1.value = "x".repeat(120);
  ta1.dispatchEvent(new window.Event("input", { bubbles: true }));
  ok("auto-grow changes height with content",
     ta1.style.height !== before && parseInt(ta1.style.height, 10) > parseInt(before || "0", 10));
  // debounced draft save fires for the box's key
  await sleep(600);
  ok("typing saves a draft (debounced PUT)",
     calls.some((c) => c.startsWith("PUT /webface/draft")
       && c.includes("chat:c1:composer") && c.includes("xxx")));
  // copy ladder (a): clipboard API present -> writes, status word
  const written = [];
  Object.defineProperty(window.navigator, "clipboard",
    { configurable: true, value: { writeText: (t) => { written.push(t); return Promise.resolve(); },
      readText: () => Promise.resolve("pasted!") } });
  const statusOf = (el) => el.parentNode.querySelector(".entrybox-status").textContent;
  ta1.parentNode.querySelector(".eb-copy").click();
  await sleep(30);
  ok("copy writes the whole content", written.length === 1 && written[0] === ta1.value);
  ok("copy lands a status word", statusOf(ta1) === "Copied");
  // paste via clipboard API inserts at the caret
  ta1.value = "AB"; ta1.selectionStart = ta1.selectionEnd = 1;
  ta1.parentNode.querySelector(".eb-paste").click();
  await sleep(30);
  ok("paste inserts clipboard text", ta1.value === "Apasted!B");
  ok("paste lands a status word", statusOf(ta1) === "Pasted");
  // copy ladder (b): no clipboard API -> honest words, text selected
  Object.defineProperty(window.navigator, "clipboard", { configurable: true, value: undefined });
  ta1.parentNode.querySelector(".eb-copy").click();
  await sleep(30);
  ok("copy without clipboard says so in words", statusOf(ta1).includes("Ctrl+C copies it"));
  ok("copy fallback selects the text",
     ta1.selectionStart === 0 && ta1.selectionEnd === ta1.value.length);
  // paste without clipboard -> honest words, field still native-pasteable
  ta1.parentNode.querySelector(".eb-paste").click();
  await sleep(30);
  ok("paste without clipboard says Ctrl+V works", statusOf(ta1).includes("Ctrl+V pastes as usual"));
  // clear: decline keeps text; confirm clears + retires the draft
  EB.confirmClear = () => false;
  const keepVal = ta1.value;
  ta1.parentNode.querySelector(".eb-clear").click();
  await sleep(30);
  ok("clear DECLINED keeps the text", ta1.value === keepVal);
  ok("clear decline lands words", statusOf(ta1).includes("untouched"));
  EB.confirmClear = () => true;
  calls.length = 0;
  ta1.parentNode.querySelector(".eb-clear").click();
  await sleep(30);
  ok("clear CONFIRMED empties the box", ta1.value === "");
  ok("confirmed clear retires the draft",
     calls.some((c) => c.startsWith("DELETE /webface/draft") && c.includes("chat:c1:composer")));
  // retire-on-submit hook (pages call this after a successful send/save)
  calls.length = 0;
  await EB.retireDraft(ta2);
  ok("retireDraft hook fires DELETE for the box key",
     calls.some((c) => c.startsWith("DELETE") && c.includes("chat:c1:edit:m1")));
  // dynamic fields are born enhanced (MutationObserver)
  const dyn = d.createElement("textarea");
  dyn.className = "entry-box"; dyn.setAttribute("data-draft-key", "group:g1:say");
  d.getElementById("dyn").appendChild(dyn);
  await sleep(80);
  ok("dynamic textarea enhanced by observer",
     !!dyn.closest(".entrybox-wrap") && !!dyn.parentNode.querySelector(".eb-clear"));
  console.log(fails.length ? "DOMTEST FAILED" : "DOMTEST ALL PASS");
  process.exit(fails.length ? 1 : 0);
}, 30));
"""


def test_entrybox_behaviour_in_headless_dom(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on this machine")
    probe = subprocess.run([node, "-e", "require.resolve('jsdom')"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("jsdom is not resolvable by node on this machine")
    test_js = tmp_path / "entrybox_dom_test.js"
    test_js.write_text(_DOM_TEST)
    run = subprocess.run(
        [node, str(test_js), str(STATIC / "entrybox.js")],
        capture_output=True, text=True, timeout=60, cwd=str(Path.home()))
    assert "DOMTEST ALL PASS" in run.stdout, run.stdout + run.stderr
    assert run.returncode == 0, run.stdout + run.stderr
