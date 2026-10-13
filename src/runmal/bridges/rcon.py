"""Source RCON protocol client (stdlib only).

The Source engine remote-console protocol, as used by many dedicated
game servers (including Conan Exiles'):

    packet := int32 size | int32 id | int32 type | body | 0x00 0x00
    (all little-endian; size counts everything after itself)

Types: SERVERDATA_RESPONSE_VALUE=0, SERVERDATA_AUTH_RESPONSE=2,
SERVERDATA_EXECCOMMAND=2, SERVERDATA_AUTH=3.

Authentication: send AUTH with the password; the server answers an
empty RESPONSE_VALUE followed by AUTH_RESPONSE with the request id
on success, or id -1 on failure. Command output may span several
RESPONSE_VALUE packets, so `execute` sends a sentinel empty command
behind the real one and reads until the sentinel's response arrives —
the standard end-of-response detection for this protocol.
"""

from __future__ import annotations

import socket
import struct

SERVERDATA_RESPONSE_VALUE = 0
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_AUTH = 3

_MAX_PACKET = 4096


class RCONError(RuntimeError):
    pass


class RCONAuthError(RCONError):
    pass


def build_packet(request_id: int, packet_type: int, body: str) -> bytes:
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


def parse_packet(data: bytes) -> tuple[int, int, str]:
    """Parse one packet body (after the size prefix): (id, type, body)."""
    if len(data) < 10:
        raise RCONError("short RCON packet")
    request_id, packet_type = struct.unpack_from("<ii", data, 0)
    body = data[8:-2] if data.endswith(b"\x00\x00") else data[8:]
    return request_id, packet_type, body.decode("utf-8", errors="replace")


class RCONClient:
    """One connection: authenticate once, then execute commands."""

    def __init__(self, host: str, port: int, password: str, timeout: float = 10.0):
        self._address = (host, port)
        self._password = password
        self._timeout = timeout
        self._socket: socket.socket | None = None
        self._next_id = 1

    def __enter__(self) -> RCONClient:
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def connect(self) -> None:
        if self._socket is not None:
            return
        sock = socket.create_connection(self._address, timeout=self._timeout)
        sock.settimeout(self._timeout)
        self._socket = sock
        try:
            self._authenticate()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    def _send(self, packet_type: int, body: str) -> int:
        if self._socket is None:
            raise RCONError("not connected")
        request_id = self._next_id
        self._next_id += 1
        self._socket.sendall(build_packet(request_id, packet_type, body))
        return request_id

    def _recv_exact(self, count: int) -> bytes:
        if self._socket is None:
            raise RCONError("not connected")
        chunks = bytearray()
        while len(chunks) < count:
            piece = self._socket.recv(count - len(chunks))
            if not piece:
                raise RCONError("connection closed by server")
            chunks += piece
        return bytes(chunks)

    def _recv_packet(self) -> tuple[int, int, str]:
        (size,) = struct.unpack("<i", self._recv_exact(4))
        if size < 10 or size > _MAX_PACKET * 4:
            raise RCONError(f"implausible RCON packet size: {size}")
        return parse_packet(self._recv_exact(size))

    def _authenticate(self) -> None:
        auth_id = self._send(SERVERDATA_AUTH, self._password)
        while True:
            request_id, packet_type, _body = self._recv_packet()
            if packet_type == SERVERDATA_AUTH_RESPONSE:
                if request_id == -1:
                    raise RCONAuthError("RCON authentication failed (bad password)")
                if request_id == auth_id:
                    return
            # The leading empty RESPONSE_VALUE is expected and ignored.

    def execute(self, command: str) -> str:
        """Run one command; returns its full (possibly multi-packet) output."""
        command_id = self._send(SERVERDATA_EXECCOMMAND, command)
        sentinel_id = self._send(SERVERDATA_EXECCOMMAND, "")
        parts: list[str] = []
        while True:
            request_id, packet_type, body = self._recv_packet()
            if request_id == sentinel_id:
                break
            if request_id == command_id and packet_type == SERVERDATA_RESPONSE_VALUE:
                parts.append(body)
        return "".join(parts)
