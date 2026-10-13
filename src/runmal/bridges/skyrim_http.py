"""Skyrim-style HTTP bridge (S607, BRIDGE_PROTOCOL §11).

The pattern used by Skyrim AI-companion mods and their kin: **the mod
is an HTTP client, the adapter hosts a small local HTTP server.**

    game mod ── POST /events ──► adapter ── bridge API ──► Rúnmál
    game mod ◄── GET  /lines ─── adapter ◄── bridge state ── Rúnmál

- The mod pushes what happens in the game (the player's spoken line,
  world events) as simple JSON events; the adapter translates them
  into bridge turns (player speech -> `user` turn with the speaker
  name, world events -> `environment` turns).
- The mod polls `/lines` for companion lines to speak in-game; the
  adapter pumps new companion turns out of the bridge conversation
  state and hands each out exactly once.

The mod-facing endpoints require a shared local token
(`X-Mod-Token` header): the server binds loopback by default, and
the token keeps other local processes from impersonating the mod.
The full mod contract is docs/bridges/SKYRIM_HTTP.md.

Run:

    python -m runmal.bridges.skyrim_http \
        --base-url http://127.0.0.1:8000 --chat-id <chat-id> \
        --token-env RUNMAL_BRIDGE_TOKEN --mod-token-env RUNMAL_MOD_TOKEN
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol

MAX_BODY_BYTES = 64 * 1024


class BridgeSink(Protocol):
    def append_turn(
        self, speaker_kind: str, content: str, speaker_name: str | None = None
    ) -> None: ...


class StateSource(Protocol):
    def fetch_state(self) -> dict: ...


# --------------------------------------------------------------- translation


def translate_event(sink: BridgeSink, event: dict) -> None:
    """One mod event -> one bridge turn. ValueError on a bad event."""
    if not isinstance(event, dict):
        raise ValueError("event must be a JSON object")
    kind = event.get("kind")
    text = str(event.get("text") or "").strip()
    if not text:
        raise ValueError("event text must not be empty")
    if kind == "player_speech":
        sink.append_turn("user", text, speaker_name=event.get("speaker") or None)
    elif kind == "world_event":
        sink.append_turn("environment", text, speaker_name=event.get("speaker") or None)
    else:
        raise ValueError(f"unknown event kind: {kind!r}")


class CompanionLineQueue:
    """New companion turns from bridge state, handed out exactly once.

    Same cursor discipline as the VRChat follower: the first pump
    primes on history (nothing is replayed), later pumps enqueue
    only unseen assistant turns.
    """

    def __init__(self):
        self._pending: list[dict] = []
        self._seen: set[str] = set()
        self._primed = False
        self._lock = threading.Lock()

    def pump(self, source: StateSource) -> int:
        state = source.fetch_state()
        messages = state.get("messages", [])
        with self._lock:
            if not self._primed:
                self._seen = {m["id"] for m in messages}
                self._primed = True
                return 0
            added = 0
            for message in messages:
                if message["id"] in self._seen:
                    continue
                self._seen.add(message["id"])
                if message.get("role") != "assistant":
                    continue
                text = message.get("content", "")
                if not text:
                    continue
                self._pending.append(
                    {
                        "id": message["id"],
                        "text": text,
                        "speaker": message.get("speaker_name"),
                    }
                )
                added += 1
            return added

    def drain(self) -> list[dict]:
        with self._lock:
            lines, self._pending = self._pending, []
            return lines


# ------------------------------------------------------------------- server


def make_server(
    host: str, port: int, *, sink: BridgeSink, source: StateSource, mod_token: str
) -> ThreadingHTTPServer:
    queue = CompanionLineQueue()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep the adapter quiet
            pass

        def _authorized(self) -> bool:
            presented = self.headers.get("X-Mod-Token", "")
            return hmac.compare_digest(presented, mod_token)

        def _reply(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - http.server naming
            if self.path == "/health":
                self._reply(200, {"status": "ok", "bridge": "skyrim-http"})
                return
            if not self._authorized():
                self._reply(401, {"error": "bad or missing X-Mod-Token"})
                return
            if self.path == "/lines":
                try:
                    queue.pump(source)
                except Exception as exc:  # Rúnmál unreachable: say so
                    self._reply(502, {"error": f"bridge state unavailable: {exc}"})
                    return
                self._reply(200, {"lines": queue.drain()})
                return
            self._reply(404, {"error": "unknown path"})

        def do_POST(self):  # noqa: N802 - http.server naming
            if not self._authorized():
                self._reply(401, {"error": "bad or missing X-Mod-Token"})
                return
            if self.path != "/events":
                self._reply(404, {"error": "unknown path"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._reply(413, {"error": "event too large"})
                return
            raw = self.rfile.read(length) if length else b""
            try:
                event = json.loads(raw.decode("utf-8"))
                translate_event(sink, event)
            except (ValueError, UnicodeDecodeError) as exc:
                self._reply(400, {"error": str(exc)})
                return
            except Exception as exc:  # Rúnmál unreachable: say so
                self._reply(502, {"error": f"bridge write failed: {exc}"})
                return
            self._reply(202, {"accepted": True})

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skyrim-style HTTP bridge (S607)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--token-env", default="RUNMAL_BRIDGE_TOKEN")
    parser.add_argument("--mod-token-env", default="RUNMAL_MOD_TOKEN")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8770)
    args = parser.parse_args(argv)
    bridge_token = os.environ.get(args.token_env, "")
    mod_token = os.environ.get(args.mod_token_env, "")
    if not bridge_token or not mod_token:
        parser.error("both bridge and mod tokens must be set in the environment")
    from runmal.bridges.bridge_http import HTTPBridgeSink, HTTPBridgeSource

    server = make_server(
        args.listen_host,
        args.listen_port,
        sink=HTTPBridgeSink(args.base_url, bridge_token, args.chat_id, via="skyrim-http-bridge"),
        source=HTTPBridgeSource(args.base_url, bridge_token, args.chat_id),
        mod_token=mod_token,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
