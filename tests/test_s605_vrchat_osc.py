"""S605 acceptance: VRChat OSC reference bridge.

OSC codec golden + round-trip tests, a live UDP fixture proving the
datagrams a VRChat client would receive, and the follower pattern's
cursor behavior (history primed, only new companion turns mirrored).
"""

from __future__ import annotations

import socket
import threading

import pytest

from runmal.bridges.osc import decode_message, encode_message
from runmal.bridges.vrchat_osc import (
    CompanionFollower,
    OSCClient,
    chunk_for_chatbox,
)


def test_osc_golden_bytes() -> None:
    assert encode_message("/chatbox/typing", (True,)) == (b"/chatbox/typing\x00" + b",T\x00\x00")


def test_osc_round_trip_all_types() -> None:
    address, args = decode_message(
        encode_message("/avatar/parameters/Mood", (3, 0.5, "calm", b"\x01\x02", False, None))
    )
    assert address == "/avatar/parameters/Mood"
    assert args == [3, 0.5, "calm", b"\x01\x02", False, None]


def test_osc_rejects_bundles_and_bad_addresses() -> None:
    with pytest.raises(ValueError):
        decode_message(b"#bundle\x00" + b"\x00" * 8)
    with pytest.raises(ValueError):
        encode_message("no-leading-slash", ())


def test_chatbox_chunking() -> None:
    text = "word " * 60  # 300 chars of words
    chunks = chunk_for_chatbox(text.strip())
    assert len(chunks) >= 3
    assert all(len(c) <= 144 for c in chunks)
    assert " ".join(chunks) == text.strip()
    assert chunk_for_chatbox("") == []


class _UDPCollector:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.datagrams: list[bytes] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.sock.settimeout(0.05)
        while not self._stop.is_set():
            try:
                data, _ = self.sock.recvfrom(65535)
                self.datagrams.append(data)
            except TimeoutError:
                continue

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2)
        self.sock.close()


def test_osc_client_speaks_vrchat_fixture() -> None:
    try:
        collector = _UDPCollector()
    except PermissionError:
        pytest.skip("UDP loopback unavailable in this environment")
    with collector:
        client = OSCClient("127.0.0.1", collector.port)
        try:
            client.set_parameter("CompanionSpeaking", True)
            client.chatbox("Hail, traveller. " * 12)  # 216 chars -> 2 chunks
            client.set_typing(False)
        except PermissionError:
            pytest.skip("UDP send unavailable in this environment")
        finally:
            client.close()
        import time

        deadline = time.monotonic() + 3
        while len(collector.datagrams) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
    decoded = [decode_message(d) for d in collector.datagrams]
    assert decoded[0] == ("/avatar/parameters/CompanionSpeaking", [True])
    chatbox = [d for d in decoded if d[0] == "/chatbox/input"]
    assert len(chatbox) == 2
    assert all(args[1:] == [True, False] for _, args in chatbox)
    assert " ".join(args[0] for _, args in chatbox) == ("Hail, traveller. " * 12).strip()
    assert decoded[-1] == ("/chatbox/typing", [False])


class _RecordingOSC:
    def __init__(self):
        self.chatbox_texts: list[str] = []
        self.parameters: list[tuple[str, object]] = []

    def chatbox(self, text, **kw):
        self.chatbox_texts.append(text)

    def set_parameter(self, name, value):
        self.parameters.append((name, value))


class _ScriptedSource:
    def __init__(self, states):
        self._states = list(states)

    def fetch_state(self):
        return self._states.pop(0) if self._states else {"messages": []}


def _msg(mid, role, content):
    return {"id": mid, "role": role, "content": content}


def test_follower_mirrors_only_new_companion_turns() -> None:
    history = {"messages": [_msg("m1", "assistant", "old news")]}
    grown = {
        "messages": [
            _msg("m1", "assistant", "old news"),
            _msg("m2", "user", "the user speaks"),
            _msg("m3", "assistant", "a fresh reply"),
            _msg("m4", "system", "the river rises"),
        ]
    }
    osc = _RecordingOSC()
    follower = CompanionFollower(osc, _ScriptedSource([history, grown, grown]))
    assert follower.poll_once() == []  # primes on history, replays nothing
    assert follower.poll_once() == ["a fresh reply"]
    assert follower.poll_once() == []  # nothing new
    assert osc.chatbox_texts == ["a fresh reply"]
    assert osc.parameters == [
        ("CompanionSpeaking", True),
        ("CompanionSpeaking", False),
    ]
