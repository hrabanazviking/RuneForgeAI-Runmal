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

from . import templates, w02
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
            raw = self._read_body()
            if not raw:
                return {}
            try:
                payload = json.loads(raw.decode("utf-8"))
            except ValueError:
                return {}
            return payload if isinstance(payload, dict) else {}

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
                    "/static/characters.js", "/static/library.js"):
                return self._static(path)
            if path == "/chat":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.chat_page(user))
                return
            if path == "/characters":
                user = self._require_user_page()
                if user is not None:
                    return self._html(200, templates.characters_page(user))
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
            try:
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
            return self._api_write("PUT")

        def do_PATCH(self):  # noqa: N802 - stdlib name
            return self._api_write("PATCH")

        def do_DELETE(self):  # noqa: N802 - stdlib name
            return self._api_write("DELETE")


        # -- POST -------------------------------------------------------------

        def do_POST(self):  # noqa: N802 - stdlib name
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
            try:
                for kind, event in app.engine.stream_generate(
                        chat_id, request_id):
                    if kind == "started":
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
            if done_clean and not saw_error and reply:
                try:
                    saved = app.engine.append_message(
                        chat_id, "assistant", reply)
                    emit({"type": "landed", "message": saved})
                except EngineError as exc:
                    emit({"type": "error",
                          "message": f"reply could not be saved: {exc.message}"})
            elif not saw_error:
                emit({"type": "error",
                      "message": "the stream ended without a clean done; "
                                 "no reply was saved"})

    return Handler
