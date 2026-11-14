"""Persisted user name for ``{{user}}`` (R-03).

The engine resolves the ``{{user}}`` macro to a display name when it
composes a persona system prompt (``runmal.persona.slots``), and until
R-03 that name was always the hard-coded default ``"User"`` — no
client could set it. This module is the small persisted setting the
interface redo plan (§1.4/§2.3) calls for: ONE name, nothing more.
It is deliberately not a persona store: personas remain character
cards bound to chats (``chats.service.set_chat_persona``); this file
holds only the name the cast uses for the user.

Storage follows the voice-settings precedent (``runmal.voice.
settings``): a versioned JSON document, ``user_settings.json``, in
the application data dir (``runmal.auth.data_dir``, so
``RUNMAL_DATA_DIR`` is honoured). Load is tolerant — a missing,
corrupt, or empty setting reads as the default, never an error, so
a hand-edited file can never brick composition.
"""

from __future__ import annotations

import json
from pathlib import Path

from runmal.auth import data_dir

SETTINGS_VERSION = 1
SETTINGS_FILENAME = "user_settings.json"

#: The name composition uses when no name has been set (the S110
#: macro default, unchanged for every pre-R-03 road).
DEFAULT_USER_NAME = "User"

_MAX_NAME_LENGTH = 200


def settings_path() -> Path:
    return data_dir() / SETTINGS_FILENAME


def _stored_name() -> str:
    """The raw stored name ('' when unset/corrupt)."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    name = data.get("user_name")
    return name.strip() if isinstance(name, str) else ""


def get_user_name() -> str:
    """The effective ``{{user}}`` name: the stored name, or the
    default ``"User"`` when none is set."""
    return _stored_name() or DEFAULT_USER_NAME


def is_user_name_set() -> bool:
    return bool(_stored_name())


def set_user_name(name: str) -> str:
    """Persist ``name`` as the ``{{user}}`` name; returns the
    effective name afterwards.

    The name is stripped; an empty result CLEARS the setting (the
    effective name returns to the default). Names over 200
    characters or containing line breaks raise ValueError — a
    display name is one short line, and it lands inside prompts.
    """
    if not isinstance(name, str):
        raise ValueError("user name must be a string")
    cleaned = name.strip()
    if len(cleaned) > _MAX_NAME_LENGTH:
        raise ValueError(
            f"user name must be at most {_MAX_NAME_LENGTH} characters"
        )
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError("user name must be a single line")
    payload = {"version": SETTINGS_VERSION, "user_name": cleaned}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return cleaned or DEFAULT_USER_NAME
