"""User-persona file interop (P-018).

ST-shaped persona files in/out. A user persona is the *user's own*
identity (ST-08), distinct from a character card: name, description,
prompt, system prompt and title, plus the placement fields users
expect (ST-09): where the description goes — disabled, in the
prompt, at the top or bottom of the Author's Note, or in-chat at a
chosen depth and role.

Clean-room basis: the exchanged shape and the position set are as
recorded in P-002's census from SillyTavern's official public
documentation and as carried by P-005's authored corpus fixture
(`persona_st.json`). No mirror source code was read.

Unknown-but-valid fields survive a round trip verbatim (INV-009):
export starts from the persona's `raw` mapping and overlays the
normalized known fields. Absent depth/role are never fabricated.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from runmal.prompt.slots import VALID_ROLES, make_slot
from runmal.safety import SafetyError, safe_json_loads

MAX_PERSONA_BYTES = 8 * 1024 * 1024

#: Canonical description positions (ST-09, in Rúnmál's words).
DESCRIPTION_POSITIONS = (
    "disabled",
    "in_prompt",
    "authors_note_top",
    "authors_note_bottom",
    "in_chat",
)

# Spellings accepted on import and normalized to the canonical set.
# Only the canonical names plus the fixture's attested spelling and
# plain synonyms of the census wording are mapped; anything else is
# preserved verbatim in `raw` and rejected as a position, never
# silently reinterpreted.
_POSITION_ALIASES = {
    "": "in_prompt",
    "none": "disabled",
    "disabled": "disabled",
    "in_prompt": "in_prompt",
    "prompt": "in_prompt",
    "story_string": "in_prompt",
    "prompt_manager": "in_prompt",
    "authors_note_top": "authors_note_top",
    "an_top": "authors_note_top",
    "authors_note_bottom": "authors_note_bottom",
    "an_bottom": "authors_note_bottom",
    "in_chat": "in_chat",
    "chat": "in_chat",
}

_KNOWN_FIELDS = (
    "name",
    "description",
    "prompt",
    "system_prompt",
    "title",
    "description_position",
    "position",
)


class PersonaParseError(ValueError):
    """A persona import failed for a clear, testable reason."""


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_depth(value: object) -> int | None:
    """Tolerant depth: null/absent -> None, numeric strings coerced."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise PersonaParseError(f"persona depth must be a number, got {value!r}")
    if isinstance(value, int):
        depth = value
    elif isinstance(value, float) and value.is_integer():
        depth = int(value)
    elif isinstance(value, str) and value.strip().lstrip("-").isdigit():
        depth = int(value.strip())
    else:
        raise PersonaParseError(f"persona depth must be a number, got {value!r}")
    if depth < 0:
        raise PersonaParseError(f"persona depth must be >= 0, got {depth}")
    return depth


def _as_position_int(value: object) -> int | None:
    """The fixture's legacy numeric `position`, preserved verbatim.

    No semantics are claimed for it in Rúnmál (the canonical
    placement is `description_position`); it is carried so a file
    that arrived with it hands it back unchanged.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def normalize_description_position(value: object) -> str:
    """Normalize an imported position spelling to the canonical set."""
    key = _as_str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if key in _POSITION_ALIASES:
        return _POSITION_ALIASES[key]
    raise PersonaParseError(
        f"unknown persona description_position {value!r}; "
        f"canonical positions are {DESCRIPTION_POSITIONS}"
    )


@dataclass
class UserPersona:
    """The user's own identity, as exchanged in persona files."""

    name: str
    description: str = ""
    prompt: str = ""
    system_prompt: str = ""
    title: str = ""
    description_position: str = "in_prompt"
    depth: int | None = None
    role: str = ""
    position: int | None = None
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.description_position = normalize_description_position(
            self.description_position
        )
        if self.role:
            role = self.role.strip().lower()
            if role not in VALID_ROLES:
                raise PersonaParseError(
                    f"unknown persona role {self.role!r}; roles are {sorted(VALID_ROLES)}"
                )
            self.role = role


def parse_persona(data: bytes | str | dict) -> UserPersona:
    """Parse an ST-shaped persona file (bytes, text, or mapping)."""
    if isinstance(data, (bytes, bytearray)):
        if len(data) > MAX_PERSONA_BYTES:
            raise PersonaParseError(
                f"persona file is {len(data)} bytes, exceeding limit of {MAX_PERSONA_BYTES} bytes"
            )
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PersonaParseError(f"persona file is not UTF-8: {exc}") from exc
        data = text
    if isinstance(data, str):
        try:
            data = safe_json_loads(data, limit=MAX_PERSONA_BYTES)
        except SafetyError as exc:
            raise PersonaParseError(str(exc)) from exc
    if not isinstance(data, dict):
        raise PersonaParseError("persona file must be a JSON object")
    name = _as_str(data.get("name")).strip()
    if not name:
        raise PersonaParseError("persona has no name")
    depth_raw = data.get("depth", data.get("description_depth"))
    role_raw = data.get("role", data.get("description_role"))
    return UserPersona(
        name=name,
        description=_as_str(data.get("description")),
        prompt=_as_str(data.get("prompt")),
        system_prompt=_as_str(data.get("system_prompt")),
        title=_as_str(data.get("title")),
        description_position=normalize_description_position(
            data.get("description_position", "in_prompt")
        ),
        depth=_as_depth(depth_raw),
        role=_as_str(role_raw),
        position=_as_position_int(data.get("position")),
        raw=copy.deepcopy(data),
    )


def export_persona(persona: UserPersona) -> bytes:
    """Export as ST-shaped persona JSON.

    Starts from `raw` (unknown fields survive verbatim) and overlays
    the normalized known fields. `depth`/`role` are written only
    when the persona carries them — never fabricated.
    """
    obj: dict = copy.deepcopy(persona.raw)
    for key in _KNOWN_FIELDS:
        obj[key] = getattr(persona, key)
    obj.pop("depth", None)
    obj.pop("description_depth", None)
    obj.pop("role", None)
    obj.pop("description_role", None)
    if persona.depth is not None:
        obj["depth"] = persona.depth
    if persona.role:
        obj["role"] = persona.role
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def persona_description_slot(persona: UserPersona):
    """The prompt slot the persona's description becomes, if any.

    `description_position` governs the *description* (its name says
    so): disabled -> no slot; in_prompt -> the baseline persona
    slot; Author's Note positions -> an authors_note slot ordered
    just before/after the baseline Author's Note position;
    in_chat -> a persona slot spliced at the persona's depth with
    its role (defaults: depth 0, system role). Empty descriptions
    produce no slot. The separate `prompt` field is preserved by
    interop and not substituted here.
    """
    text = persona.description
    if not text or persona.description_position == "disabled":
        return None
    if persona.description_position == "in_prompt":
        return make_slot("persona", "system", text, id="persona")
    if persona.description_position in ("authors_note_top", "authors_note_bottom"):
        slot = make_slot("authors_note", "system", text, id="persona_authors_note")
        delta = -1 if persona.description_position == "authors_note_top" else 1
        object.__setattr__(slot, "order", slot.order + delta)
        return slot
    # in_chat
    return make_slot(
        "persona",
        persona.role or "system",
        text,
        id="persona",
        depth=persona.depth if persona.depth is not None else 0,
    )
