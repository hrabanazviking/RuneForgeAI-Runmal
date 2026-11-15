"""Persona panel logic for the desktop shell (R-10) — Qt-free.

Persona in this engine is exactly two mechanisms (plan §1.4, the
R-03 roads in ``persona/router.py``): the persisted ``{{user}}``
name, and a chat's active persona — the character card the chat
speaks with, switched through ``chats.service.set_chat_persona``.
Switching affects FUTURE turns only; stored messages keep their
original speaker snapshots. The engine library also defines a
persona-file interop format, but no route serves it, so this
panel does not offer persona import/export — it names the fact.

This module is the panel's testable core: user-name read/write
with the engine's own default semantics, chat-persona read/switch
over the typed client, and the words the panel renders. No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.desktop.client import RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.client.models import PersonaView

DEFAULT_USER_NAME = "User"


@dataclass(frozen=True)
class UserNameState:
    """The persisted ``{{user}}`` name (``GET /user-name``)."""

    name: str
    is_set: bool

    @property
    def words(self) -> str:
        if self.is_set:
            return f"Your name in chats: {self.name}"
        return (
            f"Your name in chats: {self.name} "
            "(the built-in default — no name saved yet)"
        )


def persona_words(persona: PersonaView | None) -> str:
    """The open chat's persona, in words."""
    if persona is None or not persona.present:
        return "This chat has no persona character."
    return f"Persona: {persona.name or persona.character_id}"


class PersonaFlow:
    """Persona operations over the typed client (R-10)."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    # ------------------------------------------------------- user name

    def user_name(self) -> UserNameState:
        payload = self._client.get_user_name()
        return UserNameState(
            name=str(payload.get("user_name", DEFAULT_USER_NAME)),
            is_set=bool(payload.get("is_set", False)),
        )

    def set_user_name(self, name: str) -> UserNameState:
        """Save the ``{{user}}`` name; an empty name clears it back
        to the engine default (the route's own semantics)."""
        payload = self._client.set_user_name((name or "").strip())
        return UserNameState(
            name=str(payload.get("user_name", DEFAULT_USER_NAME)),
            is_set=bool(payload.get("is_set", False)),
        )

    # ---------------------------------------------------- chat persona

    def chat_persona(self, chat_id: str) -> PersonaView:
        return self._client.get_chat_persona(chat_id)

    def set_chat_persona(
        self, chat_id: str, character_id: str | None
    ) -> PersonaView:
        """Switch (or clear, with ``None``) the chat's persona.
        Affects future turns only."""
        if not chat_id:
            raise ClientError("Open a chat before changing its persona.")
        return self._client.set_chat_persona(chat_id, character_id)
