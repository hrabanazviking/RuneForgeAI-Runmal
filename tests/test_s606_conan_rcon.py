"""S606 acceptance: Conan Exiles RCON reference bridge.

Proves the Source RCON handshake + command cycle against a fixture
server speaking the real protocol bytes, and the Conan translation
skeleton (pattern -> bridge turn, companion turn -> say template).
"""

from __future__ import annotations

import re
import socket
import struct
import threading

import pytest

from runmal.bridges.conan import (
    ConanCompanionRelay,
    ConanEventTranslator,
    GameEvent,
)
from runmal.bridges.rcon import (
    SERVERDATA_AUTH,
    SERVERDATA_AUTH_RESPONSE,
    SERVERDATA_EXECCOMMAND,
    SERVERDATA_RESPONSE_VALUE,
    RCONAuthError,
    RCONClient,
    build_packet,
    parse_packet,
)


def test_packet_bytes_golden() -> None:
    packet = build_packet(1, SERVERDATA_AUTH, "pw")
    assert packet == struct.pack("<i", 12) + struct.pack("<ii", 1, 3) + b"pw\x00\x00"
    assert parse_packet(packet[4:]) == (1, SERVERDATA_AUTH, "pw")


class _FakeRCONServer:
    """Speaks just enough Source RCON to fixture the client honestly."""

    def __init__(self, password: str, outputs: dict[str, list[str]]):
        self._password = password
        self._outputs = outputs
        self.commands: list[str] = []
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _recv_exact(self, conn, count):
        data = bytearray()
        while len(data) < count:
            piece = conn.recv(count - len(data))
            if not piece:
                raise ConnectionError("closed")
            data += piece
        return bytes(data)

    def _serve(self):
        try:
            conn, _ = self._listener.accept()
            with conn:
                conn.settimeout(5)
                while True:
                    header = self._recv_exact(conn, 4)
                    (size,) = struct.unpack("<i", header)
                    request_id, packet_type, body = parse_packet(self._recv_exact(conn, size))
                    if packet_type == SERVERDATA_AUTH:
                        if body == self._password:
                            conn.sendall(build_packet(request_id, SERVERDATA_RESPONSE_VALUE, ""))
                            conn.sendall(build_packet(request_id, SERVERDATA_AUTH_RESPONSE, ""))
                        else:
                            conn.sendall(build_packet(-1, SERVERDATA_AUTH_RESPONSE, ""))
                    elif packet_type == SERVERDATA_EXECCOMMAND:
                        self.commands.append(body)
                        for part in self._outputs.get(body, [""]):
                            conn.sendall(build_packet(request_id, SERVERDATA_RESPONSE_VALUE, part))
        except (TimeoutError, ConnectionError, OSError):
            pass
        finally:
            self._listener.close()


def _server_or_skip(password="pw", outputs=None):
    try:
        return _FakeRCONServer(password, outputs or {}).start()
    except PermissionError:
        pytest.skip("TCP loopback unavailable in this environment")


def test_rcon_handshake_and_multipacket_execute() -> None:
    server = _server_or_skip(outputs={"GetLog": ["line one\n", "line two\n"]})
    with RCONClient("127.0.0.1", server.port, "pw", timeout=5) as client:
        assert client.execute("GetLog") == "line one\nline two\n"
    assert server.commands == ["GetLog", ""]  # command + sentinel


def test_rcon_bad_password_rejected() -> None:
    server = _server_or_skip()
    client = RCONClient("127.0.0.1", server.port, "wrong", timeout=5)
    with pytest.raises(RCONAuthError):
        client.connect()
    client.close()


EXAMPLE_CHAT = re.compile(r"\[Chat\] (?P<speaker>[^:]+): (?P<content>.*)")


def test_translator_maps_configured_patterns() -> None:
    translator = ConanEventTranslator(chat_patterns=[EXAMPLE_CHAT])
    assert translator.translate_line("[Chat] Aella: Hail, strangers!") == GameEvent(
        kind="player_chat", speaker_name="Aella", content="Hail, strangers!"
    )
    assert translator.translate_line("[Info] server tick") is None
    block = "[Chat] Bo: one\n[noise]\n[Chat] Cy: two"
    assert [e.speaker_name for e in translator.translate_block(block)] == ["Bo", "Cy"]


class _FakeRCON:
    def __init__(self, read_output=""):
        self.read_output = read_output
        self.executed: list[str] = []

    def execute(self, command):
        self.executed.append(command)
        return self.read_output


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


def test_relay_both_directions() -> None:
    rcon = _FakeRCON(read_output="[Chat] Aella: Is anyone out there?")
    sink = _RecordingSink()
    source = _Source(
        [
            {"messages": [{"id": "m1", "role": "assistant", "content": "old"}]},
            {
                "messages": [
                    {"id": "m1", "role": "assistant", "content": "old"},
                    {"id": "m2", "role": "assistant", "content": "I am here."},
                ]
            },
        ]
    )
    relay = ConanCompanionRelay(
        rcon,
        ConanEventTranslator(chat_patterns=[EXAMPLE_CHAT]),
        sink,
        source,
        read_command="GetLog",
        say_template="Broadcast {text}",
    )
    events = relay.poll_game_to_runmal()
    assert events[0].speaker_name == "Aella"
    assert sink.turns == [("user", "Is anyone out there?", "Aella")]
    assert relay.poll_runmal_to_game() == []  # primes, no replay
    assert relay.poll_runmal_to_game() == ["I am here."]
    assert "Broadcast I am here." in rcon.executed
