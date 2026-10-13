"""Shared HTTP plumbing for reference bridges.

The two directions every HTTP-based adapter needs against the stable
bridge API (docs/BRIDGE_PROTOCOL.md):

- :class:`HTTPBridgeSink` — append turns (game -> Rúnmál, S602).
- :class:`HTTPBridgeSource` — fetch conversation state (Rúnmál ->
  game, S602), the shape the follower/relay cursors consume.
"""

from __future__ import annotations


class HTTPBridgeSink:
    """Appends turns to a Rúnmál chat via the bridge API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        chat_id: str,
        *,
        timeout: float = 10.0,
        via: str = "reference-bridge",
    ):
        self._url = f"{base_url.rstrip('/')}/api/v1/bridge/chats/{chat_id}/turns"
        self._token = token
        self._timeout = timeout
        self._via = via

    def append_turn(self, speaker_kind: str, content: str, speaker_name: str | None = None) -> None:
        import httpx

        response = httpx.post(
            self._url,
            headers={"Authorization": f"Bearer {self._token}"},
            json={
                "speaker_kind": speaker_kind,
                "content": content,
                "speaker_name": speaker_name,
                "metadata": {"via": self._via},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()


class HTTPBridgeSource:
    """Fetches conversation state from a running Rúnmál."""

    def __init__(self, base_url: str, token: str, chat_id: str, timeout: float = 10.0):
        self._url = f"{base_url.rstrip('/')}/api/v1/bridge/chats/{chat_id}"
        self._token = token
        self._timeout = timeout

    def fetch_state(self) -> dict:
        import httpx

        response = httpx.get(
            self._url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()
