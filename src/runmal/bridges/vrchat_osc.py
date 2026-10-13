"""VRChat OSC reference bridge (S605, BRIDGE_PROTOCOL §10).

Drives a VRChat client over OSC so a Rúnmál companion can be present
in-world on a **second account** (the follower pattern): the user
plays on their own account; a second VRChat account, wearing the
companion's avatar, follows them; this bridge mirrors the companion's
new chat turns into that client's chatbox and drives avatar
parameters (e.g. a "speaking" flag an avatar animator can consume).

VRChat OSC facts this stands on: the client receives OSC on UDP
**9000** and sends on 9001. `/chatbox/input` takes (text, direct,
notify); `/chatbox/typing` takes a bool; avatar parameters live at
`/avatar/parameters/<Name>` with bool/int/float values. The VRChat
chatbox shows at most **144 characters**, so long turns are chunked
on word boundaries.

**OSC is not room-voice capture.** Nothing here hears the room: OSC
carries text and parameters only. Hearing other participants is the
PC-host audio ingress of S611 — a separate, explicitly routed path.

Run as a follower:

    python -m runmal.bridges.vrchat_osc \
        --base-url http://127.0.0.1:8000 --chat-id <chat-id> \
        --token-env RUNMAL_BRIDGE_TOKEN
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
from typing import Protocol

from runmal.bridges.osc import encode_message

VRCHAT_OSC_IN_PORT = 9000
CHATBOX_LIMIT = 144


def chunk_for_chatbox(text: str, limit: int = CHATBOX_LIMIT) -> list[str]:
    """Split text into <=limit pieces on word boundaries (order kept)."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = word
    chunks.append(current)
    # A single word longer than the limit is hard-split as a last resort.
    out: list[str] = []
    for chunk in chunks:
        while len(chunk) > limit:
            out.append(chunk[:limit])
            chunk = chunk[limit:]
        if chunk:
            out.append(chunk)
    return out


class OSCClient:
    """UDP sender for VRChat's OSC input port."""

    def __init__(self, host: str = "127.0.0.1", port: int = VRCHAT_OSC_IN_PORT):
        self.host = host
        self.port = port
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, address: str, *args) -> None:
        self._socket.sendto(encode_message(address, args), (self.host, self.port))

    def chatbox(self, text: str, *, direct: bool = True, notify: bool = False) -> None:
        """Show text in the chatbox, chunked to the 144-char limit."""
        for piece in chunk_for_chatbox(text):
            self.send("/chatbox/input", piece, direct, notify)

    def set_typing(self, typing: bool) -> None:
        self.send("/chatbox/typing", bool(typing))

    def set_parameter(self, name: str, value) -> None:
        """Set an avatar parameter (bool/int/float) by name."""
        self.send(f"/avatar/parameters/{name}", value)

    def close(self) -> None:
        self._socket.close()


class StateSource(Protocol):
    """Anything that can return bridge conversation state (S602 shape)."""

    def fetch_state(self) -> dict: ...


class HTTPBridgeStateSource:
    """Fetches state from a running Rúnmál via the bridge API.

    Kept as the VRChat module's public name; the implementation is
    the shared one in runmal.bridges.bridge_http.
    """

    def __init__(self, base_url: str, token: str, chat_id: str, timeout: float = 10.0):
        from runmal.bridges.bridge_http import HTTPBridgeSource

        self._impl = HTTPBridgeSource(base_url, token, chat_id, timeout)

    def fetch_state(self) -> dict:
        return self._impl.fetch_state()


class CompanionFollower:
    """Mirrors NEW companion turns from bridge state into VRChat.

    The cursor is the set of already-mirrored message ids, primed from
    the first fetched state (history is not replayed into the world).
    Only assistant-role turns are mirrored — the user's own lines and
    environment notes never appear as companion speech.
    """

    def __init__(
        self, osc: OSCClient, source: StateSource, *, speaking_parameter: str = "CompanionSpeaking"
    ):
        self._osc = osc
        self._source = source
        self._speaking_parameter = speaking_parameter
        self._seen: set[str] = set()
        self._primed = False

    def poll_once(self) -> list[str]:
        """Fetch state once; mirror any new companion turns. Returns
        the texts sent to the chatbox this poll."""
        state = self._source.fetch_state()
        messages = state.get("messages", [])
        if not self._primed:
            self._seen = {m["id"] for m in messages}
            self._primed = True
            return []
        sent: list[str] = []
        for message in messages:
            if message["id"] in self._seen:
                continue
            self._seen.add(message["id"])
            if message.get("role") != "assistant":
                continue
            text = message.get("content", "")
            if not text:
                continue
            self._osc.set_parameter(self._speaking_parameter, True)
            try:
                self._osc.chatbox(text)
            finally:
                self._osc.set_parameter(self._speaking_parameter, False)
            sent.append(text)
        return sent

    def run(self, *, interval: float = 1.0, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            self.poll_once()
            stop.wait(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VRChat OSC follower bridge (S605)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--chat-id", required=True)
    parser.add_argument(
        "--token-env",
        default="RUNMAL_BRIDGE_TOKEN",
        help="environment variable holding the bridge token",
    )
    parser.add_argument("--osc-host", default="127.0.0.1")
    parser.add_argument("--osc-port", type=int, default=VRCHAT_OSC_IN_PORT)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)
    token = os.environ.get(args.token_env, "")
    if not token:
        parser.error(f"environment variable {args.token_env} is empty or unset")
    source = HTTPBridgeStateSource(args.base_url, token, args.chat_id)
    osc = OSCClient(args.osc_host, args.osc_port)
    follower = CompanionFollower(osc, source)
    try:
        follower.run(interval=args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        osc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
