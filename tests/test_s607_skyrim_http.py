"""S607 acceptance: Skyrim-style HTTP bridge — mock game client
contract tests against the real adapter server (loopback HTTP)."""

from __future__ import annotations

import http.client
import json
import threading

import pytest

from runmal.bridges.skyrim_http import CompanionLineQueue, make_server, translate_event

MOD_TOKEN = "mod-secret"


class _RecordingSink:
    def __init__(self):
        self.turns: list[tuple] = []

    def append_turn(self, speaker_kind, content, speaker_name=None):
        self.turns.append((speaker_kind, content, speaker_name))


class _Source:
    def __init__(self, states):
        self._states = list(states)

    def fetch_state(self):
        return self._states.pop(0) if self._states else {"messages": []}


def _msg(mid, role, content, speaker=None):
    return {"id": mid, "role": role, "content": content, "speaker_name": speaker}


@pytest.fixture()
def server():
    sink = _RecordingSink()
    source = _Source(
        [
            {"messages": [_msg("m1", "assistant", "history")]},
            {
                "messages": [
                    _msg("m1", "assistant", "history"),
                    _msg("m2", "user", "ignored for lines"),
                    _msg("m3", "assistant", "Then we run.", "Aella"),
                ]
            },
        ]
    )
    try:
        httpd = make_server("127.0.0.1", 0, sink=sink, source=source, mod_token=MOD_TOKEN)
    except PermissionError:
        pytest.skip("TCP loopback unavailable in this environment")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, sink
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def _call(httpd, method, path, body=None, token=MOD_TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Mod-Token"] = token
    conn.request(
        method,
        path,
        body=json.dumps(body) if body is not None else None,
        headers=headers,
    )
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    return response.status, json.loads(raw) if raw else {}


def test_mock_game_client_contract(server) -> None:
    httpd, sink = server
    status, body = _call(httpd, "GET", "/health", token=None)
    assert (status, body["status"]) == (200, "ok")

    # The mod token guards everything else.
    status, _ = _call(httpd, "GET", "/lines", token="wrong")
    assert status == 401
    status, _ = _call(httpd, "POST", "/events", {"kind": "player_speech", "text": "hi"}, token=None)
    assert status == 401

    # Player speech and world events become bridge turns.
    status, body = _call(
        httpd,
        "POST",
        "/events",
        {"kind": "player_speech", "speaker": "Dovahkiin", "text": "We need to move."},
    )
    assert (status, body) == (202, {"accepted": True})
    status, _ = _call(
        httpd,
        "POST",
        "/events",
        {"kind": "world_event", "text": "A dragon appears over the ridge."},
    )
    assert status == 202
    assert sink.turns == [
        ("user", "We need to move.", "Dovahkiin"),
        ("environment", "A dragon appears over the ridge.", None),
    ]

    # Bad events are rejected, not translated.
    status, _ = _call(httpd, "POST", "/events", {"kind": "explosion", "text": "boom"})
    assert status == 400
    status, _ = _call(httpd, "POST", "/events", {"kind": "player_speech", "text": "  "})
    assert status == 400

    # Lines: first poll primes on history; the fresh companion line is
    # handed out exactly once.
    status, body = _call(httpd, "GET", "/lines")
    assert status == 200 and body["lines"] == []  # priming poll
    status, body = _call(httpd, "GET", "/lines")
    assert body["lines"] == [{"id": "m3", "text": "Then we run.", "speaker": "Aella"}]
    status, body = _call(httpd, "GET", "/lines")
    assert body["lines"] == []


def test_translate_event_validation() -> None:
    sink = _RecordingSink()
    with pytest.raises(ValueError):
        translate_event(sink, {"kind": "player_speech", "text": ""})
    with pytest.raises(ValueError):
        translate_event(sink, {"kind": "mystery", "text": "?"})
    with pytest.raises(ValueError):
        translate_event(sink, ["not", "a", "dict"])
    assert sink.turns == []


def test_line_queue_cursor() -> None:
    queue = CompanionLineQueue()
    source = _Source(
        [
            {"messages": [_msg("a", "assistant", "old")]},
            {"messages": [_msg("a", "assistant", "old"), _msg("b", "assistant", "new")]},
        ]
    )
    assert queue.pump(source) == 0
    assert queue.drain() == []
    assert queue.pump(source) == 1
    assert queue.drain() == [{"id": "b", "text": "new", "speaker": None}]
    assert queue.drain() == []
