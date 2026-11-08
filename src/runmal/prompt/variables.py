"""Prompt variables (S307): the composer's variable model + resolver.

The registry extends the S110 card macros (``{{char}}``, ``{{user}}``,
``{{original}}``) with clock variables (``{{time}}``, ``{{date}}``,
``{{weekday}}``) and, since P-118, the vision variable
``{{last_vision_description}}`` — the VX-43/VX-50 template variable:
the last vision description bound to the chat, as laid by P-117.
Resolution substitutes known variables and *flags* unknown ones --
an unknown ``{{...}}`` is left in place and reported, never silently
dropped, so the tools UI can show it as an error.

The vision variable's value is SUPPLIED by the caller (pure
resolver, same as char/user): :func:`resolve_variables_for_chat`
fills it from the vision store via
:mod:`runmal.prompt.vision_link`. With no description on record
the value is the empty string — an honest empty, never a
fabricated caption (P-075 no-content law).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Variable:
    name: str
    description: str
    example: str


VARIABLES: tuple[Variable, ...] = (
    Variable("char", "The character's name", "Yrsa"),
    Variable("user", "The user's display name", "Volmarr"),
    Variable("original", "The text before substitution (self-reference)", ""),
    Variable("time", "Current local time (HH:MM)", "21:47"),
    Variable("date", "Current local date (ISO)", "2026-10-12"),
    Variable("weekday", "Current weekday name", "Monday"),
    Variable(
        "last_vision_description",
        "The chat's last vision description (empty when the chat has none)",
        "",
    ),
)

VARIABLE_NAMES = frozenset(v.name for v in VARIABLES)

_ANY_MACRO_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


@dataclass
class Resolution:
    text: str
    resolved: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"text": self.text, "resolved": self.resolved,
                "unknown": self.unknown}


def resolve_variables(
    text: str,
    *,
    char_name: str = "",
    user_name: str = "User",
    now: datetime | None = None,
    last_vision_description: str = "",
) -> Resolution:
    """Substitute known variables; flag (and preserve) unknown ones."""
    now = now or datetime.now()
    values = {
        "char": char_name,
        "user": user_name,
        "original": text,
        "time": now.strftime("%H:%M"),
        "date": now.date().isoformat(),
        "weekday": now.strftime("%A"),
        "last_vision_description": last_vision_description,
    }
    resolved: list[str] = []
    unknown: list[str] = []

    def _replace(match: re.Match) -> str:
        name = match.group(1).lower()
        if name in values:
            if name not in resolved:
                resolved.append(name)
            return values[name]
        if name not in unknown:
            unknown.append(name)
        return match.group(0)

    out = _ANY_MACRO_RE.sub(_replace, text)
    return Resolution(text=out, resolved=resolved, unknown=unknown)


def resolve_variables_for_chat(
    text: str,
    *,
    chat_id: str,
    data_dir: Path | None = None,
    **kwargs,
) -> Resolution:
    """Resolve with the vision variable filled from the chat's store.

    The value is the chat's last stored vision description
    (P-117's store, read via vision_link), or "" when the chat
    has none. An explicit ``last_vision_description`` in kwargs
    wins over the store lookup.
    """
    if "last_vision_description" not in kwargs:
        from runmal.prompt.vision_link import last_description_text

        kwargs["last_vision_description"] = last_description_text(
            chat_id, data_dir)
    return resolve_variables(text, **kwargs)


def list_variables() -> list[dict]:
    return [
        {"name": v.name, "description": v.description, "example": v.example}
        for v in VARIABLES
    ]
