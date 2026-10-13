"""Conan Exiles RCON reference bridge — skeleton (S606).

Translates between a Conan Exiles dedicated server (Source RCON,
:mod:`runmal.bridges.rcon`) and the stable Rúnmál bridge API:

- **Game -> Rúnmál:** server output lines (polled through a
  deployer-chosen RCON read command, e.g. a log tail) are matched
  against deployer-configured line patterns; a matched player-chat
  line becomes a bridge `user` turn whose speaker is the player name.
- **Rúnmál -> game:** new companion turns are sent back through a
  deployer-configured RCON command template (e.g. a broadcast/say
  command with a `{text}` placeholder).

Why patterns and templates are configuration, not code: exact log
formats and RCON command vocabularies differ across server versions
and mod stacks, and this skeleton invents none of them. The deployer
copies their server's documented formats into the config — the
translation machinery (this module) is what the slice proves. Rúnmál
core contains no Conan-specific branches (BRIDGE_PROTOCOL §11); if
you are reading core code looking for "conan", you are lost — it is
all here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


class BridgeSink(Protocol):
    """Where translated game events go (the bridge API, in production)."""

    def append_turn(
        self, speaker_kind: str, content: str, speaker_name: str | None = None
    ) -> None: ...


class HTTPBridgeSink:
    """Appends turns to a Rúnmál chat via the bridge API (S602)."""

    def __init__(self, base_url: str, token: str, chat_id: str, timeout: float = 10.0):
        self._url = f"{base_url.rstrip('/')}/api/v1/bridge/chats/{chat_id}/turns"
        self._token = token
        self._timeout = timeout

    def append_turn(self, speaker_kind: str, content: str, speaker_name: str | None = None) -> None:
        import httpx

        response = httpx.post(
            self._url,
            headers={"Authorization": f"Bearer {self._token}"},
            json={
                "speaker_kind": speaker_kind,
                "content": content,
                "speaker_name": speaker_name,
                "metadata": {"via": "conan-rcon-bridge"},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()


@dataclass(frozen=True)
class GameEvent:
    """One translated game-side event, pre-bridge-API."""

    kind: str  # "player_chat" for the skeleton's one translation
    speaker_name: str
    content: str


@dataclass
class ConanEventTranslator:
    """Line-pattern -> GameEvent translation (patterns are config).

    A pattern must define named groups `speaker` and `content`.
    Lines matching nothing are ignored by design: server logs are
    mostly noise to a companion.
    """

    chat_patterns: list[re.Pattern] = field(default_factory=list)

    def translate_line(self, line: str) -> GameEvent | None:
        for pattern in self.chat_patterns:
            match = pattern.search(line)
            if match:
                return GameEvent(
                    kind="player_chat",
                    speaker_name=match.group("speaker").strip(),
                    content=match.group("content").strip(),
                )
        return None

    def translate_block(self, text: str) -> list[GameEvent]:
        events = []
        for line in text.splitlines():
            event = self.translate_line(line)
            if event is not None:
                events.append(event)
        return events


class ConanCompanionRelay:
    """Both directions for one polling cycle, over an RCON-like client.

    `rcon` is anything with `execute(command) -> str` (RCONClient in
    production). `state_source` is the S605 StateSource shape.
    """

    def __init__(
        self,
        rcon,
        translator: ConanEventTranslator,
        sink: BridgeSink,
        state_source,
        *,
        read_command: str,
        say_template: str,
    ):
        if "{text}" not in say_template:
            raise ValueError("say_template must contain a {text} placeholder")
        self._rcon = rcon
        self._translator = translator
        self._sink = sink
        self._source = state_source
        self._read_command = read_command
        self._say_template = say_template
        self._seen: set[str] = set()
        self._primed = False

    def poll_game_to_runmal(self) -> list[GameEvent]:
        """Read new server output, translate, forward chat events."""
        output = self._rcon.execute(self._read_command)
        events = self._translator.translate_block(output)
        for event in events:
            if event.kind == "player_chat":
                self._sink.append_turn("user", event.content, speaker_name=event.speaker_name)
        return events

    def poll_runmal_to_game(self) -> list[str]:
        """Send new companion turns into the game via the say template."""
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
            if text:
                self._rcon.execute(self._say_template.format(text=text))
                sent.append(text)
        return sent
