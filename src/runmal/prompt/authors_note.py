"""Author's note depth (P-056) -- clean-room.

An author's note is a per-chat instruction the author pins into the
prompt at a chosen *depth*: instead of sitting in its normal baseline
position it is spliced ``depth`` messages back from the end of the
surviving conversation history (the S206 depth-injection contract in
:mod:`runmal.prompt.slots` / :mod:`runmal.prompt.composer`). This
module is the note as data -- nothing more, nothing less:

- :class:`AuthorsNote` is the validated value object: the note text,
  its splice ``depth``, its ``frequency``, whether it is ``enabled``,
  and the ``role`` its slot is spoken in.
- :func:`note_from_data` / :func:`note_to_data` are the strict
  boundary with stored / supplied data (the shape persisted as one
  JSON document in ``chats.authors_note_json``, migration 0034):
  unknown keys, wrong types, and out-of-range values all raise
  ``ValueError`` -- a malformed note is refused, never repaired
  silently and never partially applied.
- ``frequency`` is how often the note fires: ``1`` means every
  prompt; ``N > 1`` means only when the chat's message count is a
  multiple of ``N``. A note that is due to stay silent on a given
  turn is not active (:func:`is_active_for` returns ``False``) and
  produces no slot (:func:`slot_for` returns ``None``); a caller
  recording it in the Prompt Trace uses :data:`FREQUENCY_REASON`.
- :func:`slot_for` builds the composer's slot when -- and only
  when -- the note is active: kind ``authors_note`` at the note's
  depth, so the existing layout lift (P-049) and composer splice
  do the rest. An empty, whitespace-only, or disabled note has no
  content (:func:`has_content`) and is never active.

Clean-room: written for P-056 from the Rúnmál slot/composer
contracts alone; no third-party author's-note implementation was
copied or consulted.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.prompt.slots import Slot, make_slot

#: Roles a note slot may speak in (mirrors the slot contract).
VALID_ROLES = frozenset({"system", "user", "assistant"})

#: Default splice depth: four messages back from the end of history.
DEFAULT_DEPTH = 4

#: Prompt Trace discard reason for a note silenced by its frequency.
FREQUENCY_REASON = "authors_note_frequency"

_FIELDS = frozenset({"text", "depth", "frequency", "enabled", "role"})


@dataclass(frozen=True)
class AuthorsNote:
    """One chat's author's note, as validated data."""

    text: str = ""
    depth: int = DEFAULT_DEPTH
    frequency: int = 1
    enabled: bool = True
    role: str = "system"

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("authors note text must be a string")
        if isinstance(self.depth, bool) or not isinstance(self.depth, int):
            raise ValueError("authors note depth must be an int")
        if self.depth < 0:
            raise ValueError("authors note depth must be >= 0")
        if isinstance(self.frequency, bool) or not isinstance(self.frequency, int):
            raise ValueError("authors note frequency must be an int")
        if self.frequency < 1:
            raise ValueError("authors note frequency must be >= 1")
        if not isinstance(self.enabled, bool):
            raise ValueError("authors note enabled must be a bool")
        if self.role not in VALID_ROLES:
            raise ValueError(f"invalid authors note role: {self.role!r}")


def note_from_data(data: object) -> AuthorsNote:
    """Validate stored / supplied ``data`` into an :class:`AuthorsNote`.

    ``None`` means no note was stored: the default (empty) note.
    Anything else must be a dict carrying only known keys; missing
    keys take the dataclass defaults.
    """
    if data is None:
        return AuthorsNote()
    if not isinstance(data, dict):
        raise ValueError("authors note data must be an object or None")
    unknown = set(data) - _FIELDS
    if unknown:
        raise ValueError(f"unknown authors note keys: {sorted(unknown)}")
    # Each present value is type-checked here so the error names the
    # field; AuthorsNote.__post_init__ re-checks the same invariants
    # for notes built directly in code.
    if "text" in data and not isinstance(data["text"], str):
        raise ValueError("authors note text must be a string")
    if "depth" in data:
        if isinstance(data["depth"], bool) or not isinstance(data["depth"], int):
            raise ValueError("authors note depth must be an int")
        if data["depth"] < 0:
            raise ValueError("authors note depth must be >= 0")
    if "frequency" in data:
        if isinstance(data["frequency"], bool) or not isinstance(data["frequency"], int):
            raise ValueError("authors note frequency must be an int")
        if data["frequency"] < 1:
            raise ValueError("authors note frequency must be >= 1")
    if "enabled" in data and not isinstance(data["enabled"], bool):
        raise ValueError("authors note enabled must be a bool")
    if "role" in data and data["role"] not in VALID_ROLES:
        raise ValueError(f"invalid authors note role: {data['role']!r}")
    return AuthorsNote(
        text=data.get("text", ""),
        depth=data.get("depth", DEFAULT_DEPTH),
        frequency=data.get("frequency", 1),
        enabled=data.get("enabled", True),
        role=data.get("role", "system"),
    )


def note_to_data(note: AuthorsNote) -> dict:
    """Serialise ``note`` with all five keys, always."""
    return {
        "text": note.text,
        "depth": note.depth,
        "frequency": note.frequency,
        "enabled": note.enabled,
        "role": note.role,
    }


def has_content(note: AuthorsNote) -> bool:
    """True only when the note is enabled and its text is non-blank."""
    return note.enabled and bool(note.text.strip())


def is_active_for(note: AuthorsNote, message_count: int) -> bool:
    """True when ``note`` should fire at ``message_count`` messages.

    Frequency 1 fires on every prompt; frequency N > 1 fires only
    when ``message_count`` is a multiple of N.
    """
    if isinstance(message_count, bool) or not isinstance(message_count, int):
        raise ValueError("message_count must be an int")
    if message_count < 0:
        raise ValueError("message_count must be >= 0")
    if not has_content(note):
        return False
    return note.frequency == 1 or message_count % note.frequency == 0


def slot_for(note: AuthorsNote, message_count: int) -> Slot | None:
    """The composer's depth slot for ``note``, or None when inactive."""
    if not is_active_for(note, message_count):
        return None
    return make_slot(
        "authors_note",
        note.role,
        note.text,
        id="authors_note/chat",
        depth=note.depth,
        provenance="chat:authors_note",
    )
