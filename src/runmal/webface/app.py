"""Webface HTTP handler: account-first entry, tabbed shell, chat.

Routes (the webface's own surface — the engine gains none):
  GET  /                       account page (logged out) or -> /chat
  GET/POST /login, /register   (register auto-logs-in)
  POST /logout
  GET  /account                the Account tab
  GET  /chat                   the Chat tab
  GET  /<tab>                  honest "arrives in W-NN" pages
  GET  /static/webface.css, /static/chat.js
  GET  /webface/characters     engine character list (JSON)
  GET  /webface/chats          engine chat list (JSON)
  POST /webface/chats          create a chat bound to a character
  GET  /webface/chats/{id}/messages
  POST /webface/chats/{id}/send    the composed send-turn, SSE relay
  POST /webface/chats/{id}/cancel  stop the in-flight turn

Auth: pages redirect to / when logged out; the JSON/SSE roads answer
401 JSON. Sessions are the store's digest rows behind an HttpOnly
SameSite=Lax cookie.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import stub_guard, templates, w02, w03, w04, w05, w06, w07
from .cards import import_report_words
from .engine import EngineError
from .security import hash_password, verify_password
from .store import SESSION_TTL_SECONDS

COOKIE_NAME = "webface_session"
STATIC_DIR = Path(__file__).parent / "static"
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")


class WebfaceApp:
    """Everything a request needs: the account store + engine client."""

    def __init__(self, store, engine):
        self.store = store
        self.engine = engine


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime(
        "%Y-%m-%d %H:%M UTC")


def make_handler(app: WebfaceApp):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "RunmalWebface/1.0"

        # -- plumbing -----------------------------------------------------

        def log_message(self, format, *args):  # noqa: A002 - stdlib name
            pass  # quiet: no request lines (and never any credential)

        def _send(self, status, body: bytes, content_type,
                  extra_headers=None, set_cookie=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if set_cookie:
                self.send_header("Set-Cookie", set_cookie)
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _html(self, status, page, set_cookie=None):
            self._send(status, page.encode("utf-8"),
                       "text/html; charset=utf-8", set_cookie=set_cookie)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload).encode("utf-8"),
                       "application/json")

        def _redirect(self, location, set_cookie=None):
            self._send(HTTPStatus.SEE_OTHER, b"",
                       "text/plain; charset=utf-8",
                       extra_headers={"Location": location},
                       set_cookie=set_cookie)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length > 0 else b""

        def _form(self) -> dict:
            raw = self._read_body().decode("utf-8", "replace")
            return {k: v[0] for k, v in parse_qs(raw).items()}

        def _json_body(self) -> dict:
            cached = getattr(self, "_json_cache", None)
            if cached is not None:
                return cached
            raw = self._read_body()
            payload: dict = {}
            if raw:
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                    if isinstance(parsed, dict):
                        payload = parsed
                except ValueError:
                    payload = {}
            self._json_cache = payload
            return payload

        def _session_token(self):
            cookie = SimpleCookie(self.headers.get("Cookie") or "")
            morsel = cookie.get(COOKIE_NAME)
            return morsel.value if morsel else None

        def _user(self):
            token = self._session_token()
            if not token:
                return None
            return app.store.user_for_session(token)

        def _session_cookie(self, token: str) -> str:
            return (f"{COOKIE_NAME}={token}; Path=/; HttpOnly; "
                    f"SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}")

        def _clear_cookie(self) -> str:
            return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"

        def _require_user_page(self):
            user = self._user()
            if user is None:
                self._redirect("/")
            return user

        def _require_user_api(self):
            user = self._user()
            if user is None:
                self._json(401, {"error": "not signed in"})
            return user

        # -- GET ------------------------------------------------------------

        def do_GET(self):  # noqa: N802 - stdlib name
            self._json_cache = None
            path = urlparse(self.path).path
            if path == "/":
                if self._user() is not None:
                    return self._redirect("/chat")
                return self._html(200, templates.landing_page())
            if path == "/login":
                if self._user() is not None:
                    return self._redirect("/chat")
                return self._html(200, templates.login_page())
            if path == "/register":
                if self._user() is not None:
                    return self._redirect("/chat")
                return self._html(200, templates.register_page())
            if path in ("/static/webface.css", "/static/chat.js",
                    "/static/characters.js", "/static/library.js",
                    "/static/groups.js", "/static/connections.js",
                    "/static/generation.js", "/static/firstrun.js",
                    "/static/personas.js", "/static/lorebooks.js",
                    "/static/memory.js", "/static/scenarios.js",
                    "/static/inspector.js", "/static/tools.js",
                    "/static/pwtoggle.js"):
                return self._static(path)
            if path == "/chat":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.chat_page(user))
                return
            if path == "/groups":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.groups_page(user))
                return
            if path == "/characters":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.characters_page(user))
                return
            if path == "/connections":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.connections_page(user))
                return
            if path == "/generation":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.generation_page(user))
                return
            if path == "/personas":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.personas_page(user))
                return
            if path == "/lorebooks":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.lorebooks_page(user))
                return
            if path == "/memory":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.memory_page(user))
                return
            if path == "/scenarios":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.scenarios_page(user))
                return
            if path == "/inspector":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.inspector_page(user))
                return
            if path == "/tools":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.tools_page(user))
                return
            if path == "/firstrun":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.firstrun_page(user))
                return
            if path == "/library":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.library_page(user))
                return
            if path == "/account":
                user = self._require_user_page()
                if user is None:
                    return
                row = app.store.session_row(self._session_token() or "")
                expires = _fmt_ts(row["expires"]) if row else "unknown"
                return self._html(
                    200, templates.account_page(user, expires))
            if path.startswith("/webface/"):
                return self._api_get(path)
            slug = path.lstrip("/")
            if slug in templates.PENDING:
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.pending_page(user, slug))
                return
            return self._json(404, {"error": "no such page"})

        def _static(self, path):
            name = path.rsplit("/", 1)[-1]
            file_path = STATIC_DIR / name
            if not file_path.is_file():
                return self._json(404, {"error": "no such file"})
            content_type = ("text/css; charset=utf-8" if name.endswith(".css")
                            else "text/javascript; charset=utf-8")
            self._send(200, file_path.read_bytes(), content_type,
                       extra_headers={"Cache-Control": "no-cache"})

        def _send_bytes(self, status, data, content_type, filename=None):
            extra = {}
            if filename:
                extra["Content-Disposition"] = (
                    f'attachment; filename="{filename}"')
            self._send(status, data, content_type, extra_headers=extra)

        def _multipart(self):
            body = self._read_body()
            return w02.parse_multipart(
                body, self.headers.get("Content-Type") or "")

        def _api_get(self, path):
            user = self._require_user_api()
            if user is None:
                return
            query = parse_qs(urlparse(self.path).query)
            def q1(name, default=""):
                values = query.get(name)
                return values[0] if values else default
            try:
                if path == "/webface/characters":
                    return self._json(200, app.engine.list_characters())
                if path == "/webface/chats":
                    return self._json(200, app.engine.list_chats())
                match = re.fullmatch(r"/webface/chats/([^/]+)/messages", path)
                if match:
                    return self._json(
                        200, app.engine.list_messages(match.group(1)))
                match = re.fullmatch(r"/webface/chats/([^/]+)/mind", path)
                if match:
                    return self._json(200, stub_guard.chat_mind(
                        app.engine, match.group(1)))
                match = re.fullmatch(r"/webface/groups/([^/]+)/mind", path)
                if match:
                    return self._json(200, stub_guard.room_mind(
                        app.engine, match.group(1)))
                if path == "/webface/library/cards":
                    params = {"tag_mode": "any", "sort": "name",
                              "limit": 200, "offset": 0,
                              "favourites_only": q1("favourites_only", "false")}
                    if q1("q"):
                        params["q"] = q1("q")
                    tags = query.get("tag") or []
                    if tags:
                        params["tag"] = tags
                    return self._json(200, app.engine.request(
                        "GET", "/api/v1/library/cards", params=params))
                if path == "/webface/library/tags":
                    return self._json(200, app.engine.request(
                        "GET", "/api/v1/library/tags"))
                if path == "/webface/lorebooks":
                    return self._json(200, app.engine.request(
                        "GET", "/api/v1/lorebooks"))
                if path == "/webface/chats/search":
                    params = {"q": q1("q"), "limit": 20}
                    if q1("chat_id"):
                        params["chat_id"] = q1("chat_id")
                    return self._json(200, app.engine.request(
                        "GET", "/api/v1/chats/search", params=params))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/pinned", path)
                if match:
                    return self._json(200, app.engine.request(
                        "GET", f"/api/v1/chats/{match.group(1)}"
                        "/pinned-messages"))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/authors-note", path)
                if match:
                    return self._json(200, app.engine.request(
                        "GET", f"/api/v1/chats/{match.group(1)}"
                        "/authors-note"))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/checkpoints", path)
                if match:
                    return self._json(200, app.engine.request(
                        "GET", f"/api/v1/chats/{match.group(1)}"
                        "/checkpoints"))
                match = re.fullmatch(r"/webface/chats/([^/]+)/undo", path)
                if match:
                    return self._json(200, app.engine.request(
                        "GET", f"/api/v1/chats/{match.group(1)}/undo"))
                if path == "/webface/groups":
                    return self._json(200, app.engine.request(
                        "GET", "/api/v1/groups"))
                match = re.fullmatch(r"/webface/groups/([^/]+)", path)
                if match:
                    return self._json(200, app.engine.request(
                        "GET", f"/api/v1/groups/{match.group(1)}"))
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/messages", path)
                if match:
                    rows = app.engine.request(
                        "GET", f"/api/v1/groups/{match.group(1)}/messages")
                    rows = rows if isinstance(rows, list) else []
                    return self._json(200, {
                        "messages": rows,
                        "lines": w03.transcript_lines(rows)})
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/deepening", path)
                if match:
                    return self._json(200, app.engine.request(
                        "GET", f"/api/v1/groups/{match.group(1)}/deepening"))
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/presence", path)
                if match:
                    rows = app.engine.request(
                        "GET", f"/api/v1/groups/{match.group(1)}/presence")
                    rows = rows if isinstance(rows, list) else []
                    return self._json(200, {
                        "records": rows, "lines": w03.presence_words(rows)})
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/members/([^/]+)/peek", path)
                if match:
                    peek = app.engine.request(
                        "GET", f"/api/v1/groups/{match.group(1)}/members"
                        f"/{match.group(2)}/peek")
                    peek = peek if isinstance(peek, dict) else {}
                    return self._json(200, {
                        "peek": peek, "words": w03.peek_words(peek)})
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/members/([^/]+)/digest", path)
                if match:
                    digest = app.engine.request(
                        "GET", f"/api/v1/groups/{match.group(1)}/members"
                        f"/{match.group(2)}/digest")
                    digest = digest if isinstance(digest, dict) else {}
                    return self._json(200, {
                        "digest": digest, "words": w03.digest_words(digest)})
                if path == "/webface/profiles":
                    rows = app.engine.request("GET", "/api/v1/backend-profiles")
                    rows = rows if isinstance(rows, list) else []
                    return self._json(200,
                        [w04.public_profile(r) for r in rows if isinstance(r, dict)])
                match = re.fullmatch(r"/webface/profiles/([^/]+)/probe", path)
                if match:
                    return self._json(200, w04.probe(app.engine, match.group(1)))
                if path == "/webface/presets":
                    rows = app.engine.request("GET", "/api/v1/presets")
                    rows = rows if isinstance(rows, list) else []
                    return self._json(200,
                        [w04.preset_view(r) for r in rows if isinstance(r, dict)])
                if path == "/webface/sampler-form":
                    return self._json(200, w04.sampler_form_model())
                if path == "/webface/bundles":
                    rows = app.engine.request("GET", "/api/v1/presets/bundles")
                    rows = rows if isinstance(rows, list) else []
                    return self._json(200,
                        [w04.bundle_view(r) for r in rows if isinstance(r, dict)])
                if path == "/webface/overrides":
                    return self._json(200, app.engine.request("GET", "/api/v1/presets/overrides"))
                if path == "/webface/resolve":
                    chat_id = q1("chat_id")
                    if not chat_id:
                        return self._json(422, {"error": "chat_id is required"})
                    return self._json(200, w04.resolve_preview(app.engine, chat_id))
                if path == "/webface/firstrun/status":
                    return self._json(200, w04.first_run_status(app.engine))
                if path == "/webface/firstrun/options":
                    options = [{
                        "kind": o.kind, "title": o.title,
                        "blurb": o.blurb,
                        "profile_name": o.profile_name,
                        "needs_api_key": o.needs_api_key,
                        "needs_base_url": o.needs_base_url,
                        "default_base_url": o.default_base_url,
                        "default_model": o.default_model}
                        for o in w04.BACKEND_OPTIONS]
                    return self._json(200, options)
                if path == "/webface/persona/user-name":
                    return self._json(200, w05.user_name_state(app.engine))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/persona", path)
                if match:
                    return self._json(200, w05.persona_view(
                        app.engine, match.group(1)))
                if path == "/webface/memories":
                    return self._json(200, w06.list_memories(
                        app.engine, q=q1("q"), state=q1("state") or None,
                        kind=q1("kind") or None))
                match = re.fullmatch(r"/webface/memories/([^/]+)", path)
                if match:
                    return self._json(200, w06.memory_detail(
                        app.engine, match.group(1)))
                if path == "/webface/scenarios":
                    return self._json(200, w06.list_scenarios(
                        app.engine, q=q1("q"),
                        favourites_only=q1("favourites_only") == "true"))
                if path == "/webface/scenarios/editor-model":
                    return self._json(200, w06.editor_model())
                if path == "/webface/scenarios/bindings":
                    return self._json(200, w06.list_bindings(app.engine))
                match = re.fullmatch(
                    r"/webface/scenarios/([^/]+)/export-file", path)
                if match:
                    fmt = q1("format", "native") or "native"
                    env = app.engine.request(
                        "GET", f"/api/v1/scenarios/{match.group(1)}/export",
                        params={"format": fmt})
                    doc = env.get("file") if isinstance(env, dict) else {}
                    return self._send_bytes(
                        200, json.dumps(doc).encode(), "application/json",
                        filename=f"runmal-scenario-{match.group(1)}.json")
                match = re.fullmatch(r"/webface/scenarios/([^/]+)", path)
                if match:
                    return self._json(200, w06.scenario_detail(
                        app.engine, match.group(1)))
                match = re.fullmatch(
                    r"/webface/inspector/chats/([^/]+)/messages/([^/]+)/provenance", path)
                if match:
                    return self._json(200, w07.message_provenance(
                        app.engine, match.group(1), match.group(2)))
                match = re.fullmatch(r"/webface/inspector/chats/([^/]+)", path)
                if match:
                    return self._json(200, w07.inspector_documents(
                        app.engine, match.group(1)))
                if path == "/webface/tools/macros":
                    return self._json(200, w07.list_macros(app.engine))
                if path == "/webface/tools/variables":
                    return self._json(200, w07.list_variables(app.engine))
                if path == "/webface/lorebooks/schema":
                    return self._json(200, w05.census(app.engine))
                match = re.fullmatch(
                    r"/webface/lorebooks/([^/]+)/export", path)
                if match:
                    doc = app.engine.request(
                        "GET", f"/api/v1/lorebooks/{match.group(1)}/export")
                    return self._send_bytes(
                        200, json.dumps(doc).encode(),
                        "application/json",
                        filename=f"runmal-lorebook-{match.group(1)}.json")
                match = re.fullmatch(
                    r"/webface/lorebooks/([^/]+)/pack", path)
                if match:
                    doc = app.engine.request(
                        "GET", f"/api/v1/lorebooks/{match.group(1)}/pack")
                    return self._send_bytes(
                        200, json.dumps(doc).encode(),
                        "application/json",
                        filename=f"runmal-lorebook-pack-{match.group(1)}.json")
                match = re.fullmatch(r"/webface/lorebooks/([^/]+)", path)
                if match:
                    return self._json(200, w05.book_detail(
                        app.engine, match.group(1)))
                if path == "/webface/user-name":
                    return self._json(200, app.engine.request("GET", "/api/v1/user-name"))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/editor", path)
                if match:
                    return self._json(
                        200, w02.editor_bundle(app.engine, match.group(1)))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/export", path)
                if match:
                    cid = match.group(1)
                    text = w02.export_text(app.engine, cid)
                    return self._send_bytes(
                        200, text.encode(), "application/json",
                        filename=f"runmal-character-{cid}.json")
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/avatar", path)
                if match:
                    data, ctype = app.engine.request_bytes(
                        "GET", f"/api/v1/characters/{match.group(1)}/avatar")
                    return self._send_bytes(200, data, ctype)
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/assets/([^/]+)/content", path)
                if match:
                    data, ctype = app.engine.request_bytes(
                        "GET", f"/api/v1/characters/{match.group(1)}"
                        f"/assets/{match.group(2)}/content")
                    return self._send_bytes(200, data, ctype)
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            return self._json(404, {"error": "no such road"})

        def _api_write(self, method):
            """W-02 write roads (POST/PUT/PATCH/DELETE under /webface/)."""
            user = self._require_user_api()
            if user is None:
                return
            path = urlparse(self.path).path
            # Drain the request body up front (cached for the
            # branches): a body left unread corrupts the next
            # request on this keep-alive connection. Multipart
            # roads read their own body via _multipart().
            if not (path.endswith("/imports") or path.endswith("/import") or "/avatar" in path
                    or path.endswith("/assets")):
                self._json_body()
            try:
                # ---- W-03 chat actions ----
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/messages/([^/]+)", path)
                if match and method == "PATCH":
                    body = self._json_body()
                    content = str(body.get("content") or "").strip()
                    if not content:
                        return self._json(422, {
                            "error": "a message cannot be emptied by editing"})
                    return self._json(200, app.engine.request(
                        "PATCH", f"/api/v1/chats/{match.group(1)}/messages"
                        f"/{match.group(2)}", json_body={"content": content}))
                if match and method == "DELETE":
                    return self._json(200, app.engine.request(
                        "DELETE", f"/api/v1/chats/{match.group(1)}/messages"
                        f"/{match.group(2)}"))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/messages/([^/]+)/swipes", path)
                if match and method == "POST":
                    body = self._json_body()
                    content = str(body.get("content") or "").strip()
                    if not content:
                        return self._json(422, {
                            "error": "a swipe alternate cannot be empty"})
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/messages"
                        f"/{match.group(2)}/swipes",
                        json_body={"content": content}))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/messages/([^/]+)/swipes/select",
                    path)
                if match and method == "POST":
                    body = self._json_body()
                    payload = {}
                    if body.get("action"):
                        payload["action"] = str(body["action"])
                    if body.get("index") is not None:
                        payload["index"] = int(body["index"])
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/messages"
                        f"/{match.group(2)}/swipes/select", json_body=payload))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/messages/([^/]+)/swipes/(\d+)",
                    path)
                if match and method == "DELETE":
                    return self._json(200, app.engine.request(
                        "DELETE", f"/api/v1/chats/{match.group(1)}/messages"
                        f"/{match.group(2)}/swipes/{match.group(3)}"))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/messages/([^/]+)/pin", path)
                if match and method in ("POST", "DELETE"):
                    return self._json(200, w03.set_pinned(
                        app.engine, match.group(1), match.group(2),
                        pinned=(method == "POST")))
                match = re.fullmatch(r"/webface/chats/([^/]+)/branches", path)
                if match and method == "POST":
                    body = self._json_body()
                    payload = {}
                    if body.get("message_id"):
                        payload["message_id"] = str(body["message_id"])
                    if body.get("name"):
                        payload["name"] = str(body["name"])
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/branches",
                        json_body=payload))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/authors-note", path)
                if match and method == "POST":
                    return self._json(200, w03.save_authors_note(
                        app.engine, match.group(1), self._json_body()))
                match = re.fullmatch(r"/webface/chats/([^/]+)/continue", path)
                if match and method == "POST":
                    blocked = stub_guard.blocked_chat_payload(
                        app.engine, match.group(1))
                    if blocked is not None:
                        return self._json(409, {
                            "error": blocked["words"], "no_mind": blocked})
                    body = self._json_body()
                    payload = {"mode": str(body.get("mode") or "auto")}
                    if body.get("instruction"):
                        payload["instruction"] = str(body["instruction"])
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/continue",
                        json_body=payload))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/impersonate", path)
                if match and method == "POST":
                    blocked = stub_guard.blocked_chat_payload(
                        app.engine, match.group(1))
                    if blocked is not None:
                        return self._json(409, {
                            "error": blocked["words"], "no_mind": blocked})
                    body = self._json_body()
                    payload = {}
                    if body.get("instruction"):
                        payload["instruction"] = str(body["instruction"])
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/impersonate",
                        json_body=payload))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/impersonate/(accept|discard)", path)
                if match and method == "POST":
                    body = self._json_body()
                    payload = {}
                    if match.group(2) == "accept":
                        content = str(body.get("content") or "").strip()
                        if not content:
                            return self._json(422, {
                                "error": "an accepted impersonation "
                                         "cannot be empty"})
                        payload["content"] = content
                    if body.get("draft_id"):
                        payload["draft_id"] = str(body["draft_id"])
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/impersonate"
                        f"/{match.group(2)}", json_body=payload))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/checkpoints", path)
                if match and method == "POST":
                    body = self._json_body()
                    payload = {}
                    if body.get("name"):
                        payload["name"] = str(body["name"])
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/checkpoints",
                        json_body=payload))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/checkpoints/([^/]+)/restore", path)
                if match and method == "POST":
                    body = self._json_body()
                    payload = {}
                    if body.get("name"):
                        payload["name"] = str(body["name"])
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/checkpoints"
                        f"/{match.group(2)}/restore", json_body=payload))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/checkpoints/([^/]+)", path)
                if match and method == "DELETE":
                    return self._json(200, app.engine.request(
                        "DELETE", f"/api/v1/chats/{match.group(1)}/checkpoints"
                        f"/{match.group(2)}"))
                match = re.fullmatch(r"/webface/chats/([^/]+)/undo", path)
                if match and method == "POST":
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/chats/{match.group(1)}/undo",
                        json_body={}))
                # ---- W-03 groups ----
                if method == "POST" and path == "/webface/groups":
                    body = self._json_body()
                    name = str(body.get("name") or "").strip()
                    members = body.get("member_character_ids")
                    members = ([str(m) for m in members]
                               if isinstance(members, list) else [])
                    if not name:
                        return self._json(422, {"error": "the room needs a name"})
                    if not members:
                        return self._json(422, {
                            "error": "tick at least one character for the roster"})
                    return self._json(200, app.engine.request(
                        "POST", "/api/v1/groups", json_body={
                            "name": name, "member_character_ids": members}))
                match = re.fullmatch(r"/webface/groups/([^/]+)", path)
                if match and method == "PATCH":
                    body = self._json_body()
                    payload = {}
                    for key in ("name", "speaker_policy", "speaker_config"):
                        if key in body:
                            payload[key] = body[key]
                    return self._json(200, app.engine.request(
                        "PATCH", f"/api/v1/groups/{match.group(1)}",
                        json_body=payload))
                if match and method == "DELETE":
                    return self._json(200, app.engine.request(
                        "DELETE", f"/api/v1/groups/{match.group(1)}"))
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/messages", path)
                if match and method == "POST":
                    body = self._json_body()
                    content = str(body.get("content") or "").strip()
                    if not content:
                        return self._json(422, {"error": "write something first"})
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/groups/{match.group(1)}/messages",
                        json_body={"speaker": "user", "content": content}))
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/members", path)
                if match and method == "POST":
                    body = self._json_body()
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/groups/{match.group(1)}/members",
                        json_body={"character_id": str(
                            body.get("character_id") or "")}))
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/members/([^/]+)", path)
                if match and method == "PATCH":
                    body = self._json_body()
                    payload = {}
                    if body.get("talkativeness") is not None:
                        payload["talkativeness"] = float(body["talkativeness"])
                    if body.get("muted") is not None:
                        payload["muted"] = bool(body["muted"])
                    return self._json(200, app.engine.request(
                        "PATCH", f"/api/v1/groups/{match.group(1)}/members"
                        f"/{match.group(2)}", json_body=payload))
                if match and method == "DELETE":
                    return self._json(200, app.engine.request(
                        "DELETE", f"/api/v1/groups/{match.group(1)}/members"
                        f"/{match.group(2)}"))
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/members/([^/]+)/override", path)
                if match and method == "PATCH":
                    return self._json(200, app.engine.request(
                        "PATCH", f"/api/v1/groups/{match.group(1)}/members"
                        f"/{match.group(2)}/override",
                        json_body=self._json_body()))
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/members/([^/]+)/(leave|return)",
                    path)
                if match and method == "POST":
                    payload = {} if match.group(3) == "return" else None
                    result = app.engine.request(
                        "POST", f"/api/v1/groups/{match.group(1)}/members"
                        f"/{match.group(2)}/{match.group(3)}",
                        json_body=payload)
                    if match.group(3) == "return":
                        # The engine's return road IS the digest
                        # delivery (the standalone preview only
                        # answers while the member is away).
                        digest = result if isinstance(result, dict) else {}
                        return self._json(200, {
                            "digest": digest,
                            "words": w03.digest_words(digest)})
                    return self._json(200, result)
                match = re.fullmatch(
                    r"/webface/groups/([^/]+)/deepening", path)
                if match and method == "PUT":
                    gid = match.group(1)
                    stored = app.engine.request(
                        "GET", f"/api/v1/groups/{gid}/deepening")
                    stored = stored if isinstance(stored, dict) else {}
                    body = self._json_body()
                    document = w03.compose_deepening(
                        stored,
                        generation_mode=str(body.get("generation_mode") or "swap"),
                        allow_self_responses=bool(body.get("allow_self_responses")),
                        auto_enabled=bool(body.get("auto_enabled")),
                        auto_max_turns=int(body.get("auto_max_turns", 3)),
                        join_prefix=str(body.get("join_prefix") or ""),
                        join_suffix=str(body.get("join_suffix") or ""),
                        scenario_override=str(body.get("scenario_override") or ""))
                    saved = app.engine.request(
                        "PUT", f"/api/v1/groups/{gid}/deepening",
                        json_body=document)
                    return self._json(200, {
                        "deepening": saved,
                        "group": app.engine.request(
                            "GET", f"/api/v1/groups/{gid}")})
                match = re.fullmatch(r"/webface/groups/([^/]+)/(next|run)", path)
                if match and method == "POST":
                    body = self._json_body()
                    if body.get("generate"):
                        blocked = stub_guard.blocked_room_payload(
                            app.engine, match.group(1))
                        if blocked is not None:
                            return self._json(409, {
                                "error": blocked["words"],
                                "no_mind": blocked})
                    if match.group(2) == "next":
                        payload = {"generate": bool(body.get("generate"))}
                        if body.get("user_text"):
                            payload["user_text"] = str(body["user_text"])
                        if body.get("manual_speaker_id"):
                            payload["manual_speaker_id"] = str(
                                body["manual_speaker_id"])
                        result = app.engine.request(
                            "POST", f"/api/v1/groups/{match.group(1)}/next",
                            json_body=payload)
                        result = result if isinstance(result, dict) else {}
                        return self._json(200, {
                            "result": result, "words": w03.turn_words(result)})
                    payload = {"turns": int(body.get("turns", 1)),
                               "generate": bool(body.get("generate"))}
                    result = app.engine.request(
                        "POST", f"/api/v1/groups/{match.group(1)}/run",
                        json_body=payload)
                    result = result if isinstance(result, dict) else {}
                    return self._json(200, {
                        "result": result, "words": w03.run_words(result)})
                # ---- W-04 connections ----
                if method == "POST" and path == "/webface/profiles":
                    return self._json(200, w04.save_profile(app.engine, None, self._json_body()))
                match = re.fullmatch(r"/webface/profiles/([^/]+)", path)
                if match and method == "PATCH":
                    return self._json(200,
                        w04.save_profile(app.engine, match.group(1), self._json_body()))
                if match and method == "DELETE":
                    return self._json(200,
                        app.engine.request("DELETE", f"/api/v1/backend-profiles/{match.group(1)}"))
                match = re.fullmatch(r"/webface/chats/([^/]+)/backend-profile", path)
                if match and method == "POST":
                    body = self._json_body()
                    pid = body.get("profile_id")
                    return self._json(200,
                        app.engine.request("POST",
                            f"/api/v1/chats/{match.group(1)}/backend-profile",
                                json_body={"profile_id": str(pid) if pid else None}))
                match = re.fullmatch(r"/webface/chats/([^/]+)/preset", path)
                if match and method == "POST":
                    body = self._json_body()
                    pid = body.get("preset_id")
                    return self._json(200,
                        app.engine.request("POST", f"/api/v1/chats/{match.group(1)}/preset",
                            json_body={"preset_id": str(pid) if pid else None}))
                # ---- W-04 generation ----
                if method == "POST" and path == "/webface/presets":
                    return self._json(200,
                        w04.preset_view(w04.save_preset(app.engine, None, self._json_body())))
                match = re.fullmatch(r"/webface/presets/([^/]+)", path)
                if match and method == "PATCH":
                    return self._json(200,
                        w04.preset_view(w04.save_preset(app.engine, match.group(1),
                            self._json_body())))
                if match and method == "DELETE":
                    return self._json(200,
                        app.engine.request("DELETE", f"/api/v1/presets/{match.group(1)}"))
                if method == "POST" and path == "/webface/bundles":
                    body = self._json_body()
                    doc = w04.compose_bundle(None, name=str(body.get("name") or ""),
                        sampler_values=body.get("sampler") or {}, extra=body.get("extra") or {},
                            template_ref=str(body.get("template_ref") or ""))
                    return self._json(200,
                        app.engine.request("POST", "/api/v1/presets/bundles",
                            json_body={"bundle": doc}))
                match = re.fullmatch(r"/webface/bundles/([^/]+)", path)
                if match and method == "PATCH":
                    body = self._json_body()
                    row = app.engine.request("GET", f"/api/v1/presets/bundles/{match.group(1)}")
                    stored = row.get("bundle") if isinstance(row, dict) else {}
                    doc = w04.compose_bundle(stored if isinstance(stored, dict) else {},
                        name=str(body.get("name") or (stored or {}).get("name") or ""),
                            sampler_values=body.get("sampler") or {},
                                extra=body.get("extra") or {},
                                    template_ref=str(body.get("template_ref") or ""))
                    return self._json(200,
                        app.engine.request("PATCH", f"/api/v1/presets/bundles/{match.group(1)}",
                            json_body={"bundle": doc}))
                if match and method == "DELETE":
                    return self._json(200,
                        app.engine.request("DELETE", f"/api/v1/presets/bundles/{match.group(1)}"))
                match = re.fullmatch(r"/webface/overrides/(chat|character)/([^/]+)", path)
                if match and method == "PUT":
                    body = self._json_body()
                    known = w04.parse_sampler_form(body.get("sampler") or {})
                    extra = body.get("extra") or {}
                    extra = {k: v for k,
                        v in (extra if isinstance(extra,
                            dict) else {}).items() if k not in w04.SAMPLER_FIELD_BY_KEY}
                    delta = {}
                    sampler = w04.merge_bag(known, extra)
                    if sampler:
                        delta["sampler"] = sampler
                    return self._json(200,
                        app.engine.request("PUT",
                            f"/api/v1/presets/overrides/{match.group(1)}/{match.group(2)}",
                                json_body={"bundle_id": str(body.get("bundle_id") or ""),
                                    "overrides": delta}))
                if match and method == "DELETE":
                    return self._json(200,
                        app.engine.request("DELETE",
                            f"/api/v1/presets/overrides/{match.group(1)}/{match.group(2)}"))
                # ---- W-05 personas ----
                if method == "PUT" and path == "/webface/persona/user-name":
                    body = self._json_body()
                    return self._json(200, w05.set_user_name(
                        app.engine, str(body.get("user_name") or ""),
                        clear=bool(body.get("clear"))))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/persona", path)
                if match and method == "POST":
                    body = self._json_body()
                    return self._json(200, w05.set_persona(
                        app.engine, match.group(1),
                        body.get("character_id")))
                # ---- W-06 scenarios ----
                if method == "POST" and path == "/webface/scenarios":
                    return self._json(200, w06.save_scenario(
                        app.engine, None, self._json_body()))
                if method == "POST" and path == "/webface/scenarios/import-check":
                    body = self._json_body()
                    return self._json(200, w06.check_import(
                        app.engine, body.get("document")))
                if method == "POST" and path == "/webface/scenarios/export":
                    body = self._json_body()
                    return self._json(200, w06.export_document(
                        app.engine, body.get("definition") or {},
                        str(body.get("format") or "native")))
                match = re.fullmatch(r"/webface/scenarios/([^/]+)", path)
                if match and method == "PUT":
                    return self._json(200, w06.save_scenario(
                        app.engine, match.group(1), self._json_body()))
                if match and method == "DELETE":
                    return self._json(200, w06.delete_scenario(
                        app.engine, match.group(1)))
                match = re.fullmatch(
                    r"/webface/scenarios/([^/]+)/duplicate", path)
                if match and method == "POST":
                    return self._json(200, w06.duplicate_scenario(
                        app.engine, match.group(1)))
                match = re.fullmatch(
                    r"/webface/scenarios/([^/]+)/favourite", path)
                if match and method == "PUT":
                    body = self._json_body()
                    return self._json(200, w06.set_favourite(
                        app.engine, match.group(1),
                        bool(body.get("is_favourite"))))
                match = re.fullmatch(r"/webface/scenarios/([^/]+)/tags", path)
                if match and method == "PUT":
                    body = self._json_body()
                    tags = body.get("tags")
                    return self._json(200, w06.set_tags(
                        app.engine, match.group(1), tags or []))
                match = re.fullmatch(r"/webface/scenarios/([^/]+)/apply", path)
                if match and method == "POST":
                    body = self._json_body()
                    return self._json(200, w06.apply_scenario(
                        app.engine, match.group(1),
                        str(body.get("character_id") or "")))
                match = re.fullmatch(
                    r"/webface/scenarios/bindings/([^/]+)", path)
                if match and method == "DELETE":
                    return self._json(200, w06.unbind_scenario(
                        app.engine, match.group(1)))
                # ---- W-07 inspector trace + tools ----
                match = re.fullmatch(r"/webface/inspector/chats/([^/]+)/trace", path)
                if match and method == "POST":
                    return self._json(200, w07.inspector_trace(
                        app.engine, match.group(1)))
                if method == "POST" and path == "/webface/tools/macros/expand":
                    return self._json(200, w07.expand_macros(
                        app.engine, self._json_body()))
                if method == "POST" and path == "/webface/tools/resolve":
                    return self._json(200, w07.resolve_variables(
                        app.engine, self._json_body()))
                if method == "POST" and path == "/webface/tools/compose":
                    return self._json(200, w07.compose_preview(
                        app.engine, self._json_body()))
                # ---- W-05 lorebooks ----
                if method == "POST" and path == "/webface/lorebooks":
                    return self._json(200, w05.save_book(
                        app.engine, None, self._json_body()))
                if method == "POST" and path == "/webface/lorebooks/import":
                    body = self._json_body()
                    return self._json(200, w05.import_book(
                        app.engine, body.get("document")))
                if method == "POST" and path == "/webface/lorebooks/import-pack":
                    body = self._json_body()
                    return self._json(200, w05.import_pack(
                        app.engine, body.get("document"),
                        str(body.get("on_conflict") or "create_new")))
                if method == "POST" and path == "/webface/lorebooks/pack/inspect":
                    body = self._json_body()
                    return self._json(200, w05.inspect_pack(
                        app.engine, body.get("document")))
                if method == "POST" and path == "/webface/lorebooks/upgrade/inspect":
                    body = self._json_body()
                    return self._json(200, w05.inspect_upgrade(
                        app.engine, body.get("document")))
                if method == "POST" and path == "/webface/lorebooks/upgrade":
                    body = self._json_body()
                    return self._json(200, w05.upgrade_book(
                        app.engine, body.get("document")))
                match = re.fullmatch(r"/webface/lorebooks/([^/]+)", path)
                if match and method == "PATCH":
                    return self._json(200, w05.save_book(
                        app.engine, match.group(1), self._json_body()))
                if match and method == "DELETE":
                    return self._json(200, w05.delete_book(
                        app.engine, match.group(1)))
                match = re.fullmatch(
                    r"/webface/lorebooks/([^/]+)/entries", path)
                if match and method == "POST":
                    return self._json(200, w05.save_entry(
                        app.engine, match.group(1), None,
                        self._json_body()))
                match = re.fullmatch(
                    r"/webface/lorebooks/([^/]+)/entries/([^/]+)", path)
                if match and method == "PATCH":
                    return self._json(200, w05.save_entry(
                        app.engine, match.group(1), match.group(2),
                        self._json_body()))
                if match and method == "DELETE":
                    return self._json(200, w05.delete_entry(
                        app.engine, match.group(1), match.group(2)))
                match = re.fullmatch(
                    r"/webface/lorebooks/([^/]+)/scope", path)
                if match and method == "PUT":
                    return self._json(200, w05.assign_scope(
                        app.engine, match.group(1), self._json_body()))
                if match and method == "DELETE":
                    query = parse_qs(urlparse(self.path).query)
                    kind = (query.get("scope_kind") or [""])[0]
                    owner = (query.get("owner_id") or [None])[0]
                    return self._json(200, w05.unassign_scope(
                        app.engine, match.group(1), kind, owner))
                match = re.fullmatch(
                    r"/webface/lorebooks/([^/]+)/preview", path)
                if match and method == "POST":
                    body = self._json_body()
                    msgs = body.get("messages")
                    msgs = msgs if isinstance(msgs, list) else []
                    return self._json(200, w05.preview_book(
                        app.engine, match.group(1), msgs))
                match = re.fullmatch(
                    r"/webface/chats/([^/]+)/lore-preview", path)
                if match and method == "POST":
                    body = self._json_body()
                    msgs = body.get("messages")
                    msgs = msgs if isinstance(msgs, list) else []
                    return self._json(200, w05.preview_chat(
                        app.engine, match.group(1), msgs))
                # ---- W-04 first-run ----
                if method == "POST" and path == "/webface/firstrun/connect":
                    body = self._json_body()
                    return self._json(200,
                        w04.connect_mind(app.engine, body,
                            draft_id=str(body.get("draft_id") or "")))
                if method == "POST" and path == "/webface/firstrun/prove":
                    body = self._json_body()
                    return self._json(200, w04.probe(app.engine, str(body.get("profile_id") or "")))
                if method == "POST" and path == "/webface/firstrun/meet":
                    body = self._json_body()
                    character = w04.meet_someone(app.engine, body)
                    greeted = w04.open_greeted_chat(app.engine, str(character.get("id") or ""),
                        profile_id=str(body.get("profile_id") or ""))
                    return self._json(200, {"character": character, **greeted})
                if method == "POST" and path == "/webface/firstrun/import":
                    _fields, files = self._multipart()
                    if not files:
                        return self._json(422, {"error": "pick a card file"})
                    report = app.engine.request("POST", "/api/v1/library/imports",
                        files=[("files", (name, data)) for _f, name, data in files],
                            data={"dry_run": "false"})
                    return self._json(200,
                        import_report_words(report if isinstance(report, dict) else {}))
                if method == "PUT" and path == "/webface/user-name":
                    body = self._json_body()
                    return self._json(200,
                        w04.set_user_name(app.engine, str(body.get("user_name") or "")))
                if method == "POST" and path == "/webface/characters":
                    return self._json(200, w02.create_character(
                        app.engine, self._json_body()))
                if method == "POST" and path == "/webface/library/imports":
                    _fields, files = self._multipart()
                    if not files:
                        return self._json(422, {"error": "pick at least one card file"})
                    report = app.engine.request(
                        "POST", "/api/v1/library/imports",
                        files=[("files", (name, data))
                               for _f, name, data in files],
                        data={"dry_run": "false"})
                    return self._json(200, import_report_words(
                        report if isinstance(report, dict) else {}))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)", path)
                if match and method == "PATCH":
                    return self._json(200, w02.save_character(
                        app.engine, match.group(1), self._json_body()))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/(duplicate|restore)", path)
                if match and method == "POST":
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/characters/{match.group(1)}"
                        f"/{match.group(2)}", json_body={}))
                match = re.fullmatch(r"/webface/characters/([^/]+)", path)
                if match and method == "DELETE":
                    return self._json(200, app.engine.request(
                        "DELETE", f"/api/v1/characters/{match.group(1)}"))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/versions/(\d+)/restore", path)
                if match and method == "POST":
                    return self._json(200, w02.restore_version(
                        app.engine, match.group(1), int(match.group(2))))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/avatar", path)
                if match and method == "POST":
                    _fields, files = self._multipart()
                    if not files:
                        return self._json(422, {"error": "pick an avatar file"})
                    _f, name, data = files[0]
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/characters/{match.group(1)}/avatar",
                        files=[("file", (name, data))]))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/assets", path)
                if match and method == "POST":
                    fields, files = self._multipart()
                    if not files:
                        return self._json(422, {"error": "pick an asset file"})
                    _f, name, data = files[0]
                    return self._json(200, app.engine.request(
                        "POST", f"/api/v1/characters/{match.group(1)}/assets",
                        files=[("file", (name, data))],
                        data={"kind": fields.get("kind", "embedded"),
                              "name": fields.get("name", name)}))
                match = re.fullmatch(
                    r"/webface/characters/([^/]+)/binding", path)
                if match and method in ("PUT", "PATCH", "DELETE"):
                    road = f"/api/v1/characters/{match.group(1)}/lorebook-binding"
                    if method == "DELETE":
                        return self._json(200, app.engine.request("DELETE", road))
                    return self._json(200, app.engine.request(
                        method, road, json_body=self._json_body()))
                match = re.fullmatch(
                    r"/webface/library/cards/([^/]+)/(tags|favourite)", path)
                if match and method == "PUT":
                    return self._json(200, app.engine.request(
                        "PUT", f"/api/v1/library/cards/{match.group(1)}"
                        f"/{match.group(2)}", json_body=self._json_body()))
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            return self._json(404, {"error": "no such road"})

        def do_PUT(self):  # noqa: N802 - stdlib name
            self._json_cache = None
            return self._api_write("PUT")

        def do_PATCH(self):  # noqa: N802 - stdlib name
            self._json_cache = None
            return self._api_write("PATCH")

        def do_DELETE(self):  # noqa: N802 - stdlib name
            self._json_cache = None
            return self._api_write("DELETE")


        # -- POST -------------------------------------------------------------

        def do_POST(self):  # noqa: N802 - stdlib name
            self._json_cache = None
            path = urlparse(self.path).path
            if path == "/register":
                return self._register()
            if path == "/login":
                return self._login()
            if path == "/logout":
                token = self._session_token()
                if token:
                    app.store.delete_session(token)
                return self._redirect("/", set_cookie=self._clear_cookie())
            if path == "/webface/chats":
                return self._create_chat()
            match = re.fullmatch(r"/webface/chats/([^/]+)/send", path)
            if match:
                return self._send_turn(match.group(1))
            match = re.fullmatch(r"/webface/chats/([^/]+)/regenerate", path)
            if match:
                return self._regenerate(match.group(1))
            match = re.fullmatch(r"/webface/chats/([^/]+)/cancel", path)
            if match:
                return self._cancel(match.group(1))
            if path.startswith("/webface/"):
                return self._api_write("POST")
            return self._json(404, {"error": "no such road"})

        def _register(self):
            form = self._form()
            username = (form.get("username") or "").strip()
            password = form.get("password") or ""
            if not _USERNAME_RE.match(username):
                return self._html(200, templates.register_page(
                    "Usernames are 3–32 letters, digits, '.', '_' or '-'."))
            if len(password) < 8:
                return self._html(200, templates.register_page(
                    "Passwords need at least 8 characters."))
            user = app.store.create_user(username, hash_password(password))
            if user is None:
                return self._html(200, templates.register_page(
                    "That username is taken."))
            token = app.store.create_session(user["id"])
            return self._redirect("/chat", set_cookie=self._session_cookie(token))

        def _login(self):
            form = self._form()
            username = (form.get("username") or "").strip()
            password = form.get("password") or ""
            user = app.store.get_user_by_name(username)
            if user is None or not verify_password(password, user["pass_hash"]):
                return self._html(200, templates.login_page(
                    "Username or password did not match."))
            token = app.store.create_session(user["id"])
            return self._redirect("/chat", set_cookie=self._session_cookie(token))

        def _create_chat(self):
            user = self._require_user_api()
            if user is None:
                return
            body = self._json_body()
            character_id = str(body.get("character_id") or "").strip()
            if not character_id:
                return self._json(
                    422, {"error": "a chat is always bound to a character"})
            try:
                chat = app.engine.create_chat(
                    character_id=character_id,
                    title=str(body.get("title") or ""))
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            return self._json(200, chat)

        def _cancel(self, chat_id):
            user = self._require_user_api()
            if user is None:
                return
            body = self._json_body()
            request_id = str(body.get("request_id") or "").strip()
            if not request_id:
                return self._json(422, {"error": "request_id is required"})
            try:
                cancelled = app.engine.cancel_generate(request_id)
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            return self._json(200, {"cancelled": cancelled})

        def _regenerate(self, chat_id):
            """Regenerate, the desktop's lossless composition as SSE:
            journaled-delete the last assistant reply, stream a fresh
            composed turn, land only on a clean finish; on any other
            ending restore the old reply (undo journal first,
            re-append fallback) and say so in words."""
            user = self._require_user_api()
            if user is None:
                return
            body = self._json_body()
            request_id = str(body.get("request_id") or "").strip() \
                or uuid.uuid4().hex
            try:
                mind = stub_guard.chat_mind(app.engine, chat_id)
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            if mind["state"] == "none":
                # FIX-STUB pre-guard: nothing set aside, nothing generated.
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Request-ID", request_id)
                self.end_headers()
                self.wfile.write(
                    f"data: {json.dumps(mind['no_mind'])}\n\n".encode())
                self.wfile.flush()
                return
            try:
                old = w03.regenerate_plan(app.engine, chat_id)
                deleted = app.engine.request(
                    "DELETE",
                    f"/api/v1/chats/{chat_id}/messages/{old['id']}")
                if not (isinstance(deleted, dict) and deleted.get("deleted")):
                    return self._json(502, {
                        "error": "the last reply could not be set aside"})
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Request-ID", request_id)
            self.end_headers()

            def emit(payload):
                line = f"data: {json.dumps(payload)}\n\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()

            text_parts: list[str] = []
            done_clean = False
            saw_error = False
            stubbed = False
            try:
                for kind, event in app.engine.stream_generate(
                        chat_id, request_id):
                    if kind == "started":
                        if (event.get("backend_key")
                                == stub_guard.FAKE_BACKEND_KIND
                                and mind["state"] != "demo"):
                            # FIX-STUB safety net: a fake stream for
                            # a chat that is not explicitly Demo must
                            # never land — cancel it and say so.
                            stubbed = True
                            try:
                                app.engine.cancel_generate(request_id)
                            except EngineError:
                                pass
                            emit(stub_guard.no_mind_payload(mind))
                            break
                        emit({"type": "started",
                              "backend_key": event.get("backend_key", ""),
                              "mode": event.get("mode", ""),
                              "request_id": request_id})
                        continue
                    emit(event)
                    if kind == "token":
                        text = event.get("text")
                        if isinstance(text, str):
                            text_parts.append(text)
                    elif kind == "done":
                        done_clean = True
                    elif kind == "error":
                        saw_error = True
            except EngineError as exc:
                saw_error = True
                try:
                    emit({"type": "error", "message": exc.message})
                except OSError:
                    pass
            reply = "".join(text_parts)
            if stubbed:
                restored = w03.restore_reply(app.engine, chat_id, old)
                if not restored:
                    emit({"type": "error",
                          "message": "the fake stream was refused and "
                                     "the previous reply could NOT be "
                                     "restored"})
                return
            if done_clean and not saw_error and reply:
                try:
                    saved = app.engine.append_message(
                        chat_id, "assistant", reply)
                    emit({"type": "landed", "message": saved})
                except EngineError as exc:
                    emit({"type": "error",
                          "message": f"reply could not be saved: {exc.message}"})
                return
            restored = w03.restore_reply(app.engine, chat_id, old)
            emit({"type": "restored", "restored": restored,
                  "message": ("the regenerated stream did not finish "
                              "cleanly, so the previous reply was "
                              "restored" if restored else
                              "the regenerated stream did not finish "
                              "cleanly and the previous reply could "
                              "NOT be restored")})

        def _send_turn(self, chat_id):
            """The composed send-turn, relayed as SSE.

            Desktop discipline (chat_logic.send_turn): the request id
            is fixed first, the user message lands, the composed
            stream runs, and the assistant message lands ONLY on a
            clean done — an errored or stopped stream lands no reply
            and the terminal SSE event says so.
            """
            user = self._require_user_api()
            if user is None:
                return
            body = self._json_body()
            content = str(body.get("content") or "").strip()
            if not content:
                return self._json(422, {"error": "write a message first"})
            request_id = str(body.get("request_id") or "").strip() \
                or uuid.uuid4().hex
            try:
                mind = stub_guard.chat_mind(app.engine, chat_id)
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            if mind["state"] == "none":
                # FIX-STUB pre-guard: user message NOT appended, nothing generated.
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Request-ID", request_id)
                self.end_headers()
                self.wfile.write(
                    f"data: {json.dumps(mind['no_mind'])}\n\n".encode())
                self.wfile.flush()
                return
            try:
                app.engine.append_message(chat_id, "user", content)
            except EngineError as exc:
                return self._json(exc.status, {"error": exc.message})
            # SSE from here on; the connection closes at stream end.
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Request-ID", request_id)
            self.end_headers()

            def emit(payload):
                line = f"data: {json.dumps(payload)}\n\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()

            text_parts: list[str] = []
            done_clean = False
            saw_error = False
            stubbed = False
            try:
                for kind, event in app.engine.stream_generate(
                        chat_id, request_id):
                    if kind == "started":
                        if (event.get("backend_key")
                                == stub_guard.FAKE_BACKEND_KIND
                                and mind["state"] != "demo"):
                            # FIX-STUB safety net: a fake stream for
                            # a chat that is not explicitly Demo must
                            # never land — cancel it and say so.
                            stubbed = True
                            try:
                                app.engine.cancel_generate(request_id)
                            except EngineError:
                                pass
                            emit(stub_guard.no_mind_payload(mind))
                            break
                        emit({"type": "started",
                              "backend_key": event.get("backend_key", ""),
                              "mode": event.get("mode", ""),
                              "request_id": request_id})
                        continue
                    emit(event)
                    if kind == "token":
                        text = event.get("text")
                        if isinstance(text, str):
                            text_parts.append(text)
                    elif kind == "done":
                        done_clean = True
                    elif kind == "error":
                        saw_error = True
            except EngineError as exc:
                saw_error = True
                try:
                    emit({"type": "error", "message": exc.message})
                except OSError:
                    pass
            reply = "".join(text_parts)
            if done_clean and not saw_error and not stubbed and reply:
                try:
                    saved = app.engine.append_message(
                        chat_id, "assistant", reply)
                    emit({"type": "landed", "message": saved})
                except EngineError as exc:
                    emit({"type": "error",
                          "message": f"reply could not be saved: {exc.message}"})
            elif not saw_error and not stubbed:
                emit({"type": "error",
                      "message": "the stream ended without a clean done; "
                                 "no reply was saved"})

    return Handler
