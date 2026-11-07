"""Macros (P-055): the documented text-macro engine for prompt text.

Clean-room semantics, written from the mirrors' *public* macro
behaviour: prompt text carries ``{{name}}`` and
``{{name::arg1::arg2}}`` macros that expand at composition /
inspection time. This module is the one documented engine for new
callers; the older partial surfaces stay untouched for compat --
S110 (:mod:`runmal.persona.slots`) expands char/user/original in
card slots, S307 (:mod:`runmal.prompt.variables`) resolves the
simple clock registry for the tools preview.

Pure domain: no DB, no I/O, no network. The only wall-clock read
is the injectable ``now`` default; the only entropy is the
labelled unseeded random path.

Syntax (normative):

- ``{{name}}`` / ``{{name::arg1::arg2}}`` -- the name is
  case-insensitive; whitespace around the name and each argument
  is trimmed. ``::`` separates arguments.
- ``\\{{...}}`` escapes expansion: it renders literally as
  ``{{...}}`` and is not recorded as an expansion or an unknown.
- ``<char>`` / ``<user>`` angle aliases expand exactly like
  ``{{char}}`` / ``{{user}}`` unless the context flag
  ``expand_angle_aliases`` is off.
- A lone unclosed ``{{`` is not a macro token: it is left
  byte-identical and unreported.
- Expansion is a SINGLE pass: macro arguments are literal text
  and expanded values are never re-scanned, so a character named
  ``{{user}}`` stays literal and ``{{upper::{{char}}}}`` treats
  ``{{char}}`` as argument text (the macro token ends at the
  first ``}}``).

The macro set (registry: :data:`MACROS`):

- Identity: ``char``, ``user``, ``persona`` (the persona name,
  falling back to the user name), ``original`` (the text before
  expansion, or the context's explicit original), ``model``,
  ``chatId``, ``lastMessage``, ``lastUserMessage``,
  ``lastCharMessage``.
- Clock, all from the injectable ``now``: ``time`` (HH:MM),
  ``isotime`` (HH:MM:SS), ``date`` (ISO date), ``datetime``
  (ISO date + space + HH:MM:SS), ``weekday`` (full name),
  ``year`` / ``month`` / ``day`` / ``hour`` / ``minute`` /
  ``second`` (zero-padded numbers).
- Random -- each consumes exactly one recorded roll occurrence:
  ``{{random::a::b::...}}`` picks one of its choices;
  ``{{roll::NdM}}`` / ``{{roll::NdM+K}}`` / ``{{roll::NdM-K}}``
  sums N dice of M sides plus the optional modifier.
- Variables, over a WORKING COPY of the context's variable map
  (the caller's dict is never mutated; the final map is returned
  on the report): ``{{getvar::name}}``, ``{{setvar::name::value}}``
  (expands to the empty string), ``{{addvar::name::delta}}``
  (numeric; a missing variable starts at 0; expands to "").
- Transforms / utilities: ``{{upper::text}}``, ``{{lower::text}}``,
  ``{{reverse::text}}`` (arguments rejoined with ``::``),
  ``{{newline}}`` / ``{{newline::N}}``, ``{{comment::...}}``
  (expands to the empty string).

RNG honesty (the P-036 discipline, applied to text): a seeded
roll is a pure function of (algorithm version, seed, roll
context, occurrence index, the raw macro text, die index) --
SHA-256 over the canonical material, first eight digest bytes
as an unsigned integer divided by 2**64. The same seed +
context + text reproduces every pick and every die, in
isolation, forever. Every random expansion produces a
:class:`MacroRoll` record on the report: the roll value, the
seed, whether it was seeded, the choices or dice, and the
outcome. ``seed=None`` is the honest unseeded path: the value
is drawn from system entropy and the record carries
``seeded=False`` -- inspectable after the fact, never
reproducible, and the record says so.

Unknown / malformed discipline (never silent, never disguised):

- Report mode (the default): an unknown macro stays
  BYTE-IDENTICAL in the output and is listed in
  ``report.unknown``; a malformed known macro (a bad roll spec,
  a bad newline count, ``getvar`` of an unset variable, a
  non-numeric ``addvar``) likewise stays byte-identical and is
  listed in ``report.errors`` with its reason. Nothing vanishes
  and nothing is rewritten into a plausible-looking lie.
- Strict mode (``strict=True``): expansion collects every
  unknown and malformed macro in the text, then raises
  :class:`MacroError` naming them all.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field, replace
from datetime import datetime

#: Roll-derivation algorithm version, part of the roll material.
MACRO_ALGORITHM = "runmal-p055-macro-v1"

__all__ = [
    "MACRO_ALGORITHM",
    "MACROS",
    "MacroContext",
    "MacroError",
    "MacroExpansion",
    "MacroReport",
    "MacroResult",
    "MacroRoll",
    "MacroSpec",
    "expand_macros",
    "list_macros",
]


class MacroError(ValueError):
    """Strict-mode refusal: unknown or malformed macros in text."""


@dataclass(frozen=True)
class MacroSpec:
    name: str
    kind: str  # identity | clock | random | variable | transform
    description: str
    syntax: str
    example: str


MACROS: tuple[MacroSpec, ...] = (
    MacroSpec("char", "identity", "The character's name", "{{char}}", "Yrsa"),
    MacroSpec("user", "identity", "The user's display name", "{{user}}", "Volmarr"),
    MacroSpec(
        "persona",
        "identity",
        "The persona name (falls back to the user name)",
        "{{persona}}",
        "Volmarr",
    ),
    MacroSpec(
        "original",
        "identity",
        "The text before expansion (self-reference)",
        "{{original}}",
        "",
    ),
    MacroSpec("model", "identity", "The model id in play, as data", "{{model}}", ""),
    MacroSpec("chatid", "identity", "The chat id in play, as data", "{{chatId}}", ""),
    MacroSpec(
        "lastmessage",
        "identity",
        "The last message in the chat, either side",
        "{{lastMessage}}",
        "",
    ),
    MacroSpec(
        "lastusermessage",
        "identity",
        "The last message sent by the user",
        "{{lastUserMessage}}",
        "",
    ),
    MacroSpec(
        "lastcharmessage",
        "identity",
        "The last message sent by the character",
        "{{lastCharMessage}}",
        "",
    ),
    MacroSpec("time", "clock", "Current local time (HH:MM)", "{{time}}", "21:47"),
    MacroSpec("isotime", "clock", "Current local time (HH:MM:SS)", "{{isotime}}", "21:47:03"),
    MacroSpec("date", "clock", "Current local date (ISO)", "{{date}}", "2026-10-12"),
    MacroSpec(
        "datetime",
        "clock",
        "Current local date and time (ISO, space-separated)",
        "{{datetime}}",
        "2026-10-12 21:47:03",
    ),
    MacroSpec("weekday", "clock", "Current weekday name", "{{weekday}}", "Monday"),
    MacroSpec("year", "clock", "Current year (zero-padded)", "{{year}}", "2026"),
    MacroSpec("month", "clock", "Current month (zero-padded)", "{{month}}", "10"),
    MacroSpec("day", "clock", "Current day of month (zero-padded)", "{{day}}", "12"),
    MacroSpec("hour", "clock", "Current hour, 24h (zero-padded)", "{{hour}}", "21"),
    MacroSpec("minute", "clock", "Current minute (zero-padded)", "{{minute}}", "47"),
    MacroSpec("second", "clock", "Current second (zero-padded)", "{{second}}", "03"),
    MacroSpec(
        "random",
        "random",
        "Pick one of the :: choices by a recorded roll",
        "{{random::a::b}}",
        "a",
    ),
    MacroSpec(
        "roll",
        "random",
        "Roll N dice of M sides, optional +/-K modifier, by recorded rolls",
        "{{roll::2d6+1}}",
        "9",
    ),
    MacroSpec("getvar", "variable", "The value of a prompt variable", "{{getvar::mood}}", ""),
    MacroSpec(
        "setvar",
        "variable",
        "Set a prompt variable (expands to nothing)",
        "{{setvar::mood::calm}}",
        "",
    ),
    MacroSpec(
        "addvar",
        "variable",
        "Add a number to a prompt variable (expands to nothing)",
        "{{addvar::score::2}}",
        "",
    ),
    MacroSpec("upper", "transform", "Uppercase the argument text", "{{upper::abc}}", "ABC"),
    MacroSpec("lower", "transform", "Lowercase the argument text", "{{lower::ABC}}", "abc"),
    MacroSpec("reverse", "transform", "Reverse the argument text", "{{reverse::abc}}", "cba"),
    MacroSpec("newline", "transform", "One newline, or N newlines", "{{newline::2}}", "\n\n"),
    MacroSpec(
        "comment",
        "transform",
        "An author comment; expands to nothing",
        "{{comment::note}}",
        "",
    ),
)

_MACRO_NAMES = frozenset(spec.name for spec in MACROS)


def list_macros() -> list[dict]:
    """The macro registry as JSON-shaped dicts (the helper UI's chips)."""
    return [
        {
            "name": spec.name,
            "kind": spec.kind,
            "description": spec.description,
            "syntax": spec.syntax,
            "example": spec.example,
        }
        for spec in MACROS
    ]


@dataclass
class MacroContext:
    """Everything a macro may read, supplied as data by the caller."""

    char_name: str = ""
    user_name: str = "User"
    persona_name: str = ""
    original_text: str | None = None
    model: str = ""
    chat_id: str = ""
    last_message: str = ""
    last_user_message: str = ""
    last_char_message: str = ""
    variables: dict = field(default_factory=dict)
    now: datetime | None = None
    seed: int | None = None
    roll_context: str = ""
    expand_angle_aliases: bool = True


@dataclass(frozen=True)
class MacroExpansion:
    """One successful expansion, as recorded on the report."""

    raw: str
    name: str
    args: tuple
    value: str
    kind: str

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "name": self.name,
            "args": list(self.args),
            "value": self.value,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class MacroRoll:
    """One inspectable random roll made for one macro occurrence."""

    raw: str
    name: str  # "random" | "roll"
    roll: float  # the primary drawn value in [0.0, 1.0)
    seed: int | None
    seeded: bool  # False = system-entropy roll, not reproducible
    context: str = ""
    occurrence: int = 0
    algorithm: str = MACRO_ALGORITHM
    choices: tuple = ()  # random: the candidate values
    chosen_index: int | None = None  # random: which choice won
    dice: tuple = ()  # roll: the individual die faces
    outcome: str = ""  # the expanded text this roll produced

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "name": self.name,
            "roll": self.roll,
            "seed": self.seed,
            "seeded": self.seeded,
            "context": self.context,
            "occurrence": self.occurrence,
            "algorithm": self.algorithm,
            "choices": list(self.choices),
            "chosen_index": self.chosen_index,
            "dice": list(self.dice),
            "outcome": self.outcome,
        }


@dataclass
class MacroReport:
    """The full inspection record of one expansion pass."""

    expansions: list = field(default_factory=list)
    rolls: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "expansions": [row.to_dict() for row in self.expansions],
            "rolls": [row.to_dict() for row in self.rolls],
            "unknown": list(self.unknown),
            "errors": list(self.errors),
            "variables": dict(self.variables),
        }


@dataclass
class MacroResult:
    text: str
    report: MacroReport

    def to_dict(self) -> dict:
        return {"text": self.text, "report": self.report.to_dict()}


def _check_seed(seed) -> int | None:
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise MacroError(f"seed must be an integer or None: {seed!r}")
    return seed


def _derive_roll(seed: int, context: str, occurrence: int, raw: str, sub: int = 0) -> float:
    """The seeded roll for one macro occurrence, in [0.0, 1.0). Pure."""
    material = "\x00".join(
        [MACRO_ALGORITHM, str(seed), context, str(occurrence), raw, str(sub)]
    )
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


#: One scan step: an escaped \{{...}} or a {{...}} token (first }} ends it).
_TOKEN_RE = re.compile(r"\\(\{\{.*?\}\})|\{\{(.*?)\}\}", re.DOTALL)
_ANGLE_RE = re.compile(r"<(char|user)>", re.IGNORECASE)
_ROLL_RE = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$")


class _MalformedError(Exception):
    """Internal: a known macro whose arguments do not parse."""


class _Expander:
    def __init__(self, text: str, ctx: MacroContext):
        self.original = ctx.original_text if ctx.original_text is not None else text
        self.ctx = ctx
        self.now = ctx.now or datetime.now()
        self.variables = dict(ctx.variables or {})
        self.report = MacroReport(variables=self.variables)
        self.occurrence = 0
        self.entropy = random.Random()
        self.seed = _check_seed(ctx.seed)

    # -- rolls ------------------------------------------------------
    def _draw(self, raw: str, sub: int = 0) -> float:
        if self.seed is None:
            return self.entropy.random()
        return _derive_roll(self.seed, self.ctx.roll_context, self.occurrence, raw, sub)

    # -- one macro --------------------------------------------------
    def expand_one(self, raw: str, inner: str) -> str | None:
        """Expand one token; None means 'leave raw verbatim'."""
        inner = inner.strip()
        if not inner:
            self.report.errors.append(f"{raw}: empty macro")
            return None
        parts = [part.strip() for part in inner.split("::")]
        name = parts[0].lower()
        args = parts[1:]
        if name not in _MACRO_NAMES:
            self.report.unknown.append(raw)
            return None
        try:
            value, kind = self._dispatch(raw, name, args)
        except _MalformedError as exc:
            self.report.errors.append(f"{raw}: {exc}")
            return None
        self.report.expansions.append(
            MacroExpansion(raw=raw, name=name, args=tuple(args), value=value, kind=kind)
        )
        return value

    def _dispatch(self, raw: str, name: str, args: list) -> tuple:
        ctx, now = self.ctx, self.now
        if name == "char":
            return ctx.char_name, "identity"
        if name == "user":
            return ctx.user_name, "identity"
        if name == "persona":
            return ctx.persona_name or ctx.user_name, "identity"
        if name == "original":
            return self.original, "identity"
        if name == "model":
            return ctx.model, "identity"
        if name == "chatid":
            return ctx.chat_id, "identity"
        if name == "lastmessage":
            return ctx.last_message, "identity"
        if name == "lastusermessage":
            return ctx.last_user_message, "identity"
        if name == "lastcharmessage":
            return ctx.last_char_message, "identity"
        if name == "time":
            return now.strftime("%H:%M"), "clock"
        if name == "isotime":
            return now.strftime("%H:%M:%S"), "clock"
        if name == "date":
            return now.date().isoformat(), "clock"
        if name == "datetime":
            return now.strftime("%Y-%m-%d %H:%M:%S"), "clock"
        if name == "weekday":
            return now.strftime("%A"), "clock"
        if name == "year":
            return now.strftime("%Y"), "clock"
        if name == "month":
            return now.strftime("%m"), "clock"
        if name == "day":
            return now.strftime("%d"), "clock"
        if name == "hour":
            return now.strftime("%H"), "clock"
        if name == "minute":
            return now.strftime("%M"), "clock"
        if name == "second":
            return now.strftime("%S"), "clock"
        if name == "random":
            return self._macro_random(raw, args), "random"
        if name == "roll":
            return self._macro_roll(raw, args), "random"
        if name == "getvar":
            return self._macro_getvar(args), "variable"
        if name == "setvar":
            return self._macro_setvar(args), "variable"
        if name == "addvar":
            return self._macro_addvar(args), "variable"
        if name == "upper":
            return "::".join(args).upper(), "transform"
        if name == "lower":
            return "::".join(args).lower(), "transform"
        if name == "reverse":
            return "::".join(args)[::-1], "transform"
        if name == "newline":
            return self._macro_newline(args), "transform"
        if name == "comment":
            return "", "transform"
        raise AssertionError(f"unhandled macro {name!r}")  # registry-guarded

    # -- random -----------------------------------------------------
    def _macro_random(self, raw: str, args: list) -> str:
        if not args:
            raise _MalformedError("random needs at least one :: choice")
        roll = self._draw(raw)
        index = min(int(roll * len(args)), len(args) - 1)
        outcome = args[index]
        self.report.rolls.append(
            MacroRoll(
                raw=raw,
                name="random",
                roll=roll,
                seed=self.seed,
                seeded=self.seed is not None,
                context=self.ctx.roll_context,
                occurrence=self.occurrence,
                choices=tuple(args),
                chosen_index=index,
                outcome=outcome,
            )
        )
        self.occurrence += 1
        return outcome

    def _macro_roll(self, raw: str, args: list) -> str:
        if len(args) != 1:
            raise _MalformedError("roll needs exactly one :: NdM argument")
        match = _ROLL_RE.match(args[0].replace(" ", ""))
        if not match:
            raise _MalformedError(f"bad dice spec {args[0]!r} (want NdM, NdM+K or NdM-K)")
        count = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))
        modifier = int(match.group(3)) if match.group(3) else 0
        if not 1 <= count <= 100:
            raise _MalformedError("dice count must be in 1..100")
        if not 2 <= sides <= 1000:
            raise _MalformedError("dice sides must be in 2..1000")
        dice = []
        first_roll = None
        for die in range(count):
            draw = self._draw(raw, sub=die)
            if die == 0:
                first_roll = draw
            dice.append(min(int(draw * sides), sides - 1) + 1)
        outcome = str(sum(dice) + modifier)
        self.report.rolls.append(
            MacroRoll(
                raw=raw,
                name="roll",
                roll=first_roll,
                seed=self.seed,
                seeded=self.seed is not None,
                context=self.ctx.roll_context,
                occurrence=self.occurrence,
                dice=tuple(dice),
                outcome=outcome,
            )
        )
        self.occurrence += 1
        return outcome

    # -- variables --------------------------------------------------
    def _macro_getvar(self, args: list) -> str:
        if len(args) != 1 or not args[0]:
            raise _MalformedError("getvar needs exactly one :: name")
        if args[0] not in self.variables:
            raise _MalformedError(f"variable {args[0]!r} is not set")
        return str(self.variables[args[0]])

    def _macro_setvar(self, args: list) -> str:
        if len(args) < 2 or not args[0]:
            raise _MalformedError("setvar needs :: name :: value")
        self.variables[args[0]] = "::".join(args[1:])
        self.report.variables = self.variables
        return ""

    def _macro_addvar(self, args: list) -> str:
        if len(args) != 2 or not args[0]:
            raise _MalformedError("addvar needs :: name :: delta")
        try:
            delta = float(args[1])
        except ValueError:
            raise _MalformedError(f"addvar delta {args[1]!r} is not a number") from None
        current = self.variables.get(args[0], 0)
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            try:
                current = float(current)
            except (TypeError, ValueError):
                raise _MalformedError(
                    f"variable {args[0]!r} is not numeric: {current!r}"
                ) from None
        total = float(current) + delta
        self.variables[args[0]] = int(total) if total == int(total) else total
        self.report.variables = self.variables
        return ""

    # -- utilities --------------------------------------------------
    def _macro_newline(self, args: list) -> str:
        if not args:
            return "\n"
        if len(args) != 1:
            raise _MalformedError("newline takes at most one :: count")
        try:
            count = int(args[0])
        except ValueError:
            raise _MalformedError(f"newline count {args[0]!r} is not an integer") from None
        if not 0 <= count <= 100:
            raise _MalformedError("newline count must be in 0..100")
        return "\n" * count


def expand_macros(
    text: str,
    context: MacroContext | None = None,
    *,
    strict: bool = False,
    **overrides,
) -> MacroResult:
    """Expand every macro in ``text`` and return text + report.

    ``context`` carries the caller's data; keyword ``overrides``
    name :class:`MacroContext` fields and win over the context.
    Report mode (default) preserves unknown/malformed macros
    verbatim and reports them; ``strict=True`` raises
    :class:`MacroError` naming every one found.
    """
    if not isinstance(text, str):
        raise MacroError(f"text must be a string: {type(text).__name__}")
    ctx = context or MacroContext()
    if overrides:
        ctx = replace(ctx, **overrides)
    expander = _Expander(text, ctx)
    out: list[str] = []
    cursor = 0
    for match in _TOKEN_RE.finditer(text):
        out.append(text[cursor:match.start()])
        if match.group(1) is not None:  # escaped \{{...}}
            out.append(match.group(1))
        else:
            value = expander.expand_one(match.group(0), match.group(2))
            out.append(match.group(0) if value is None else value)
        cursor = match.end()
    out.append(text[cursor:])
    result_text = "".join(out)
    if ctx.expand_angle_aliases:
        result_text = _expand_angle_aliases(result_text, ctx, expander.report)
    expander.report.variables = expander.variables
    if strict and (expander.report.unknown or expander.report.errors):
        problems = [f"unknown {raw}" for raw in expander.report.unknown]
        problems += expander.report.errors
        raise MacroError("macro expansion refused: " + "; ".join(problems))
    return MacroResult(text=result_text, report=expander.report)


def _expand_angle_aliases(text: str, ctx: MacroContext, report: MacroReport) -> str:
    def _replace(match: re.Match) -> str:
        name = match.group(1).lower()
        value = ctx.char_name if name == "char" else ctx.user_name
        report.expansions.append(
            MacroExpansion(
                raw=match.group(0), name=name, args=(), value=value, kind="identity"
            )
        )
        return value

    return _ANGLE_RE.sub(_replace, text)
