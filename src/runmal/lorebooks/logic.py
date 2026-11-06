"""Selective key logic for lorebook entries (P-032).

Pure-domain module: no DB, no I/O, no network, no runmal imports.
It owns the four selective-logic modes that refine how an entry's
secondary keys gate a primary-key hit (see S202's scanner), the
canonical name <-> world-info code mapping for those modes, and
the single gate function the scanner consults.

The four modes (``matched`` of ``secondary_count`` usable secondary
keys matched, at least one primary key already matched):

- ``and_any``: fire when at least one secondary key matches
  (``matched >= 1``).
- ``and_all``: fire only when every secondary key matches
  (``matched == secondary_count``).
- ``not_any``: fire only when no secondary key matches
  (``matched == 0``).
- ``not_all``: fire when at least one secondary key does not match
  (``matched < secondary_count``).

Truth-table summary (secondary_count, matched -> and_any / and_all /
not_any / not_all):

- (0, 0) -> True / True / True / True (empty-secondary rule, below)
- (1, 0) -> False / False / True / True
- (1, 1) -> True / True / False / False
- (2, 0) -> False / False / True / True
- (2, 1) -> True / False / False / True
- (2, 2) -> True / True / False / False

Empty-secondary rule: when an entry has no usable secondary keys
(``secondary_count == 0``), the selective logic is not applied at
all and the gate passes (``True``) in every mode -- the primary
match alone decides, exactly as entries behaved before P-032.

World-info codes are the public file-format codes for the modes;
they are NOT in prose order: ``and_any`` is 0, ``not_all`` is 1,
``not_any`` is 2, and ``and_all`` is 3.
"""

from __future__ import annotations

LOGIC_AND_ANY = "and_any"
LOGIC_AND_ALL = "and_all"
LOGIC_NOT_ANY = "not_any"
LOGIC_NOT_ALL = "not_all"

SELECTIVE_LOGICS = frozenset(
    {LOGIC_AND_ANY, LOGIC_AND_ALL, LOGIC_NOT_ANY, LOGIC_NOT_ALL}
)

DEFAULT_SELECTIVE_LOGIC = LOGIC_AND_ANY

WORLDINFO_CODE_BY_LOGIC = {
    "and_any": 0,
    "not_all": 1,
    "not_any": 2,
    "and_all": 3,
}

LOGIC_BY_WORLDINFO_CODE = {code: name for name, code in WORLDINFO_CODE_BY_LOGIC.items()}

__all__ = [
    "LOGIC_AND_ANY",
    "LOGIC_AND_ALL",
    "LOGIC_NOT_ANY",
    "LOGIC_NOT_ALL",
    "SELECTIVE_LOGICS",
    "DEFAULT_SELECTIVE_LOGIC",
    "WORLDINFO_CODE_BY_LOGIC",
    "LOGIC_BY_WORLDINFO_CODE",
    "check_selective_logic",
    "normalise_selective_logic",
    "selective_logic_from_code",
    "worldinfo_code",
    "secondary_gate",
]


def check_selective_logic(value) -> str:
    """Strict validation: return ``value`` if it is a canonical mode.

    Raises ValueError for anything else (wrong case, separators,
    codes, None, non-strings).
    """
    if isinstance(value, str) and value in SELECTIVE_LOGICS:
        return value
    raise ValueError(
        f"invalid selective_logic: {value!r} (valid: {sorted(SELECTIVE_LOGICS)})"
    )


def normalise_selective_logic(value) -> str:
    """Tolerant name normaliser: canonical name -> itself, else default."""
    if isinstance(value, str) and value in SELECTIVE_LOGICS:
        return value
    return DEFAULT_SELECTIVE_LOGIC


def selective_logic_from_code(value) -> str:
    """Tolerant world-info code coercion -> canonical mode name.

    Mirrors the tolerant int discipline used for imported files
    without importing it: booleans and None mean the default code,
    ints pass through, floats truncate, numeric strings parse
    (float-shaped strings included), and anything unparsable or
    out of the known code table falls back to the default mode.
    """
    if isinstance(value, bool) or value is None:
        code = 0
    elif isinstance(value, int):
        code = value
    elif isinstance(value, float):
        code = int(value)
    elif isinstance(value, str):
        try:
            code = (
                int(float(value))
                if ("." in value or "e" in value.lower())
                else int(value)
            )
        except ValueError:
            code = 0
    else:
        code = 0
    return LOGIC_BY_WORLDINFO_CODE.get(code, DEFAULT_SELECTIVE_LOGIC)


def worldinfo_code(mode) -> int:
    """Return the public world-info code for a canonical mode name."""
    return WORLDINFO_CODE_BY_LOGIC[check_selective_logic(mode)]


def secondary_gate(mode, *, secondary_count, matched_count) -> bool:
    """Decide whether the secondary keys let a primary hit fire.

    ``mode`` is validated strictly; both counts must be real ints
    (not bools), non-negative, with ``matched_count`` no greater
    than ``secondary_count``. With no usable secondary keys the
    gate always passes (see the module docstring).
    """
    mode = check_selective_logic(mode)
    for name, count in (
        ("secondary_count", secondary_count),
        ("matched_count", matched_count),
    ):
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError(f"{name} must be an integer")
        if count < 0:
            raise ValueError(f"{name} must be >= 0")
    if matched_count > secondary_count:
        raise ValueError("matched_count must be <= secondary_count")
    if secondary_count == 0:
        return True
    if mode == LOGIC_AND_ANY:
        return matched_count >= 1
    if mode == LOGIC_AND_ALL:
        return matched_count == secondary_count
    if mode == LOGIC_NOT_ANY:
        return matched_count == 0
    # LOGIC_NOT_ALL
    return matched_count < secondary_count
