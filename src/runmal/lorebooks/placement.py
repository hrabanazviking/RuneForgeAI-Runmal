"""Position & depth placement for lorebook entries (P-038).

Pure semantics module: no I/O, no database, no service imports,
following the shape of ``rng.py`` (P-036) and ``states.py`` (P-035).
This module is the single vocabulary owner for entry placement;
the service layer, the file legs (transfer/interop) and the
prompt inspector all import from here, so the split that gate
finding F1 recorded (the file layer knew ``at_depth`` while the
DB layer rejected it) cannot recur.

A lorebook entry has a ``position`` naming where its content is
injected in the prompt:

* ``before_char`` -- before the character definition (the
  composer's ``lore_before`` slot);
* ``after_char`` -- after the character definition (the
  composer's ``lore_after`` slot);
* ``at_depth`` -- spliced into the conversation history at a
  declared depth, as a message carrying a declared role (the
  composer's S206 depth injection).

Only ``at_depth`` entries consult the two companion fields:

* ``depth``: a non-negative int counting history messages back
  from the end of the surviving history (the S206 splice count),
  or ``None`` when undeclared. Undeclared stays undeclared in
  storage and in files; :func:`placement_for` materialises
  ``DEFAULT_AT_DEPTH_DEPTH`` only at placement time.
* ``role``: one of ``system`` / ``user`` / ``assistant``, the
  role of the injected message. Stored for every entry
  (default ``system``); placement forces ``system`` for
  before/after entries, so a stored role never leaks into a
  slot it does not belong to.

The world-info numeric codes (position 0/1/4, role 0/1/2) are
mapped by the tables below. The role code table is Runmal's own,
defined by this slice (P-019 preserved the codes as data and
left the table to Part III): 0 -> system, 1 -> user,
2 -> assistant -- Runmal's own VALID_ROLES vocabulary in
baseline order.

The ``check_*`` functions are strict (canonical values only,
``ValueError`` otherwise) for the service/API write path. The
``normalise_*`` functions are tolerant for the file/import
legs: they never raise, and they degrade asymmetrically on
purpose -- a bad depth becomes ``None`` (undeclared; never an
invented number) while a bad role becomes ``system`` (role has
no absence sentinel: the store column is NOT NULL and the
composer needs a concrete role for every emitted message).
A negative depth degrades to ``None``, never clamped to 0:
clamping would invent the most intrusive placement.
"""

from __future__ import annotations

from dataclasses import dataclass

POSITION_BEFORE_CHAR = "before_char"
POSITION_AFTER_CHAR = "after_char"
POSITION_AT_DEPTH = "at_depth"

POSITIONS = (POSITION_BEFORE_CHAR, POSITION_AFTER_CHAR, POSITION_AT_DEPTH)
VALID_POSITIONS = frozenset(POSITIONS)
DEFAULT_POSITION = POSITION_BEFORE_CHAR

VALID_ROLES = ("system", "user", "assistant")
DEFAULT_ROLE = "system"

#: Fallback depth for an at_depth entry whose stored depth is
#: missing or unusable, materialised by placement_for() only.
DEFAULT_AT_DEPTH_DEPTH = 4

#: World-info position codes -> native position names (the
#: codes attested by P-005's authored corpus).
POSITION_FROM_CODE = {
    0: POSITION_BEFORE_CHAR,
    1: POSITION_AFTER_CHAR,
    4: POSITION_AT_DEPTH,
}
CODE_FROM_POSITION = {name: code for code, name in POSITION_FROM_CODE.items()}

#: World-info role codes -> role names (Runmal's table, above).
ROLE_FROM_CODE = {0: "system", 1: "user", 2: "assistant"}
CODE_FROM_ROLE = {name: code for code, name in ROLE_FROM_CODE.items()}


def check_position(value: object) -> str:
    """Return ``value`` if it is a valid position name, else raise."""
    if isinstance(value, str) and value in VALID_POSITIONS:
        return value
    raise ValueError(
        f"invalid position: {value!r} (valid: {sorted(VALID_POSITIONS)})"
    )


def check_depth(value: object) -> int | None:
    """Return ``value`` if it is ``None`` or an ``int >= 0``, else raise."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"invalid depth: {value!r} (valid: None or int >= 0)")
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError(f"invalid depth: {value!r} (valid: None or int >= 0)")


def check_role(value: object) -> str:
    """Return ``value`` if it is an exact valid role name, else raise."""
    if isinstance(value, str) and value in VALID_ROLES:
        return value
    raise ValueError(f"invalid role: {value!r} (valid: {list(VALID_ROLES)})")


def normalise_position(value: object) -> str:
    """Coerce ``value`` to a position name, defaulting to before_char."""
    if isinstance(value, bool):
        return DEFAULT_POSITION
    if isinstance(value, str):
        name = value.strip().lower()
        if name in VALID_POSITIONS:
            return name
        return _position_from_code_text(name)
    if isinstance(value, int):
        return POSITION_FROM_CODE.get(value, DEFAULT_POSITION)
    if isinstance(value, float) and value.is_integer():
        return POSITION_FROM_CODE.get(int(value), DEFAULT_POSITION)
    return DEFAULT_POSITION


def _position_from_code_text(text: str) -> str:
    if not text:
        return DEFAULT_POSITION
    try:
        code = int(text)
    except ValueError:
        try:
            as_float = float(text)
        except ValueError:
            return DEFAULT_POSITION
        if not as_float.is_integer():
            return DEFAULT_POSITION
        code = int(as_float)
    return POSITION_FROM_CODE.get(code, DEFAULT_POSITION)


def normalise_depth(value: object) -> int | None:
    """Coerce ``value`` to an ``int >= 0`` or ``None``; never raises."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value.is_integer() and value >= 0:
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = int(text)
        except ValueError:
            try:
                as_float = float(text)
            except ValueError:
                return None
            if as_float.is_integer() and as_float >= 0:
                return int(as_float)
            return None
        return parsed if parsed >= 0 else None
    return None


def normalise_role(value: object) -> str:
    """Coerce ``value`` to a role name, defaulting to ``system``."""
    if value is None or isinstance(value, bool):
        return DEFAULT_ROLE
    if isinstance(value, str):
        name = value.strip().lower()
        if name in VALID_ROLES:
            return name
        if name in ("0", "1", "2"):
            return ROLE_FROM_CODE[int(name)]
        return DEFAULT_ROLE
    if isinstance(value, int):
        return ROLE_FROM_CODE.get(value, DEFAULT_ROLE)
    if isinstance(value, float) and value.is_integer():
        return ROLE_FROM_CODE.get(int(value), DEFAULT_ROLE)
    return DEFAULT_ROLE


@dataclass(frozen=True)
class Placement:
    """Where an entry injects: slot kind, plus depth/role for at_depth."""

    kind: str
    depth: int | None
    role: str


def placement_for(position: object, depth: object, role: object) -> Placement:
    """Resolve a stored position/depth/role triple to a Placement.

    Defensive by design: stored values are checked upstream, so
    an unknown position resolves as before_char rather than
    raising inside prompt composition. Depth and role are
    consulted only for at_depth; before/after placements always
    carry depth None and role system, whatever is stored.
    """
    if position == POSITION_AFTER_CHAR:
        return Placement("lore_after", None, DEFAULT_ROLE)
    if position == POSITION_AT_DEPTH:
        resolved_depth = (
            depth
            if isinstance(depth, int) and not isinstance(depth, bool) and depth >= 0
            else DEFAULT_AT_DEPTH_DEPTH
        )
        resolved_role = role if role in VALID_ROLES else DEFAULT_ROLE
        return Placement("lore_before", resolved_depth, resolved_role)
    return Placement("lore_before", None, DEFAULT_ROLE)
