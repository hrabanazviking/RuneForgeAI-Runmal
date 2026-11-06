"""Lorebook file interop (P-019).

ST world-info JSON in/out: entries, keys, and settings preserved.
Part III deepens *behaviour* (selective logic, probability,
recursion, groups, at-depth placement); this slice is the file
layer — nothing a world-info file carries is silently dropped on
the way in, and the way back out hands it back.

Two shapes are read:

1. **World-info** — ``{"name": ..., "entries": {"<uid>": {...}}}``
   (``entries`` may also be a list), the SillyTavern-style shape
   `transfer.parse_import` already maps a subset of.
2. **Native** — Rúnmál's own ``runmal-lorebook`` shape, as
   `transfer.export_book` produces it.

Clean-room basis: the world-info shape and field set are as
recorded by P-005's authored corpus (fixtures authored fresh from
public documentation) and P-002's census of SillyTavern's official
public documentation (ST-15–ST-27). No mirror source code was read.

Preservation discipline (INV-009, the P-018 persona pattern):

- Every entry keeps its complete original mapping in ``raw``;
  export starts from ``raw`` and overlays the normalized known
  fields, so unknown-but-valid fields survive verbatim.
- The per-entry fields Part III owns (probability, recursion
  flags, scan depth, filters,
  triggers, decorators, budget and outlet fields, source ``id`` /
  ``displayIndex``) are carried in ``extra`` as data, never
  interpreted here and never dropped.
- Position codes attested in-tree are mapped as data:
  0 -> ``before_char``, 1 -> ``after_char``, 4 -> ``at_depth``
  (P-005's pinned at-depth code; the native shape already carries
  ``at_depth`` as a position string). Any other code is preserved
  verbatim in ``position_code`` with the native position left at
  ``before_char`` and no semantics claimed — the code hands back
  unchanged on export.
- Inclusion groups (P-034): world-info ``group`` /
  ``groupWeight`` are first-class fields (promoted out of
  ``extra``), mapped to native ``inclusion_group`` /
  ``group_weight``; ``groupOverride`` / ``useGroupScoring`` stay
  preserved-as-data in ``extra``, uninterpreted (deterministic
  resolution is Rúnmál's semantics; see lorebooks/groups.py).
- Probability (P-036): world-info ``probability`` (integer
  percent) / ``useProbability`` are first-class fields (promoted
  out of ``extra``), mapped to native ``probability`` /
  ``use_probability``; the tolerant percent normaliser is
  lorebooks/rng.py's. The DB store carries only the effective
  percent (see transfer.py); this file layer carries both
  fields losslessly.
- At-depth companions ``depth`` / ``role`` are first-class
  modelled fields (P-038): ``depth`` is a tolerant int-or-None
  and ``role`` is normalised to a role NAME via placement's
  code table {0: system, 1: user, 2: assistant} -- Runmal's own
  table, defined by P-038 (P-019 preserved the codes as data
  and left the table to Part III). On world-info export the
  role is written back as its code under the no-fabrication
  rule; the companions are preserved as data
  (``depth`` tolerantly coerced, ``role`` normalised to
  its name by the table above); neither is fabricated when
  absent.
- Book-level unknowns and the book's ``originalData`` mapping
  survive verbatim the same way.

The interop model itself is a file model, like P-018's. Since
P-038 the DB store holds the placement fields too (migration
0030), so the DB import path (`transfer.import_book`) stores
them alongside the file layer; the file round trip loses
nothing.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from runmal.lorebooks.groups import (
    DEFAULT_GROUP_WEIGHT,
    normalise_group_weight,
    normalise_inclusion_group,
)
from runmal.lorebooks.logic import (
    DEFAULT_SELECTIVE_LOGIC,
    normalise_selective_logic,
    selective_logic_from_code,
    worldinfo_code,
)
from runmal.lorebooks.placement import (
    CODE_FROM_POSITION,
    CODE_FROM_ROLE,
    DEFAULT_ROLE,
    POSITION_FROM_CODE,
    normalise_depth,
    normalise_role,
)
from runmal.lorebooks.rng import DEFAULT_PROBABILITY, normalise_probability
from runmal.lorebooks.transfer import _as_int
from runmal.safety import SafetyError, safe_json_loads

MAX_LOREBOOK_BYTES = 32 * 1024 * 1024

#: World-info fields this slice maps to Rúnmál's native entry
#: fields (the P-005 mapped set, plus the at-depth companions).
WORLDINFO_MAPPED_FIELDS = frozenset(
    {
        "comment",
        "name",
        "content",
        "key",
        "keysecondary",
        "selectiveLogic",
        "group",
        "groupWeight",
        "probability",
        "useProbability",
        "constant",
        "vectorized",
        "disable",
        "order",
        "position",
        "caseSensitive",
        "matchWholeWords",
        "sticky",
        "cooldown",
        "delay",
        "depth",
        "role",
    }
)

#: Native entry fields mapped by this slice (the export_book set).
NATIVE_MAPPED_FIELDS = frozenset(
    {
        "name",
        "content",
        "keys",
        "secondary_keys",
        "selective_logic",
        "inclusion_group",
        "group_weight",
        "probability",
        "use_probability",
        "priority",
        "position",
        "enabled",
        "constant",
        "vectorised",
        "vectorized",
        "case_sensitive",
        "whole_word",
        "depth",
        "role",
        "sticky_prompts",
        "cooldown_prompts",
        "delay_prompts",
    }
)

# Attested world-info position codes <-> native position strings
# The tables themselves are owned by runmal.lorebooks.placement
# (P-038), imported above and re-exported under these names.


class LorebookParseError(ValueError):
    """A lorebook file import failed for a clear, testable reason."""


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(k) for k in value]
    return []


def _position_code(value: object) -> int | None:
    """Tolerant position code: null/absent/non-numeric -> None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


@dataclass
class WorldInfoEntry:
    """One lorebook entry, as exchanged in lorebook files."""

    name: str = ""
    content: str = ""
    keys: list[str] = field(default_factory=list)
    secondary_keys: list[str] = field(default_factory=list)
    selective_logic: str = "and_any"
    inclusion_group: str = ""
    group_weight: int = DEFAULT_GROUP_WEIGHT
    probability: int = DEFAULT_PROBABILITY
    use_probability: bool = True
    priority: int = 100
    position: str = "before_char"
    position_code: int | None = None
    enabled: bool = True
    constant: bool = False
    vectorised: bool = False
    case_sensitive: bool = False
    whole_word: bool = True
    sticky_prompts: int = 0
    cooldown_prompts: int = 0
    delay_prompts: int = 0
    depth: int | None = None
    role: str = "system"
    uid: str | None = None
    extra: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict, compare=False)
    source: str = "worldinfo"

    def native_fields(self) -> dict:
        """The natively-modelled subset, in parse_import's shape."""
        return {
            "name": self.name,
            "content": self.content,
            "keys": list(self.keys),
            "secondary_keys": list(self.secondary_keys),
            "selective_logic": self.selective_logic,
            "inclusion_group": self.inclusion_group,
            "group_weight": self.group_weight,
            "probability": self.probability,
            "use_probability": self.use_probability,
            "priority": self.priority,
            "position": self.position,
            "depth": self.depth,
            "role": self.role,
            "enabled": self.enabled,
            "constant": self.constant,
            "vectorised": self.vectorised,
            "case_sensitive": self.case_sensitive,
            "whole_word": self.whole_word,
            "sticky_prompts": self.sticky_prompts,
            "cooldown_prompts": self.cooldown_prompts,
            "delay_prompts": self.delay_prompts,
        }


@dataclass
class LorebookFile:
    """A whole lorebook file: book settings + entries, whole."""

    name: str
    entries: list[WorldInfoEntry] = field(default_factory=list)
    description: str = ""
    scan_depth: int | None = None
    token_budget: int | None = None
    original_data: dict | None = None
    extra: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict, compare=False)
    source_format: str = "worldinfo"

    def native_book_fields(self) -> dict:
        """Book fields in parse_import's shape (mapped subset)."""
        book: dict = {"name": self.name}
        if self.source_format == "native":
            book["description"] = self.description
            book["scan_depth"] = self.scan_depth if self.scan_depth is not None else 4
            book["token_budget"] = self.token_budget
        return book


def _entry_from_worldinfo(raw: dict, uid: str | None) -> WorldInfoEntry:
    if not isinstance(raw, dict):
        raise LorebookParseError("world-info entry must be a JSON object")
    code = _position_code(raw.get("position"))
    whole_word = raw.get("matchWholeWords")
    return WorldInfoEntry(
        name=_as_str(raw.get("comment") or raw.get("name") or ""),
        content=_as_str(raw.get("content")),
        keys=_as_str_list(raw.get("key")),
        secondary_keys=_as_str_list(raw.get("keysecondary")),
        selective_logic=selective_logic_from_code(raw.get("selectiveLogic")),
        inclusion_group=normalise_inclusion_group(raw.get("group")),
        group_weight=normalise_group_weight(raw.get("groupWeight")),
        probability=normalise_probability(raw.get("probability")),
        use_probability=(
            True if raw.get("useProbability") is None else bool(raw.get("useProbability"))
        ),
        priority=_as_int(raw.get("order"), 100),
        position=POSITION_FROM_CODE.get(code, "before_char"),
        position_code=code,
        enabled=not bool(raw.get("disable", False)),
        constant=bool(raw.get("constant", False)),
        vectorised=bool(raw.get("vectorized", False)),
        case_sensitive=bool(raw.get("caseSensitive", False)),
        whole_word=True if whole_word is None else bool(whole_word),
        sticky_prompts=_as_int(raw.get("sticky"), 0),
        cooldown_prompts=_as_int(raw.get("cooldown"), 0),
        delay_prompts=_as_int(raw.get("delay"), 0),
        depth=normalise_depth(raw.get("depth")),
        role=normalise_role(raw.get("role")),
        uid=uid,
        extra={
            k: copy.deepcopy(v)
            for k, v in raw.items()
            if k not in WORLDINFO_MAPPED_FIELDS
        },
        raw=copy.deepcopy(raw),
    )


def _entry_from_native(raw: dict) -> WorldInfoEntry:
    if not isinstance(raw, dict):
        raise LorebookParseError("native lorebook entry must be a JSON object")
    position = _as_str(raw.get("position")) or "before_char"
    return WorldInfoEntry(
        name=_as_str(raw.get("name")),
        content=_as_str(raw.get("content")),
        keys=_as_str_list(raw.get("keys")),
        secondary_keys=_as_str_list(raw.get("secondary_keys")),
        selective_logic=normalise_selective_logic(raw.get("selective_logic")),
        inclusion_group=normalise_inclusion_group(raw.get("inclusion_group")),
        group_weight=normalise_group_weight(raw.get("group_weight")),
        probability=normalise_probability(raw.get("probability")),
        use_probability=bool(raw.get("use_probability", True)),
        priority=_as_int(raw.get("priority"), 100),
        position=position,
        position_code=CODE_FROM_POSITION.get(position),
        depth=normalise_depth(raw.get("depth")),
        role=normalise_role(raw.get("role")),
        enabled=bool(raw.get("enabled", True)),
        constant=bool(raw.get("constant", False)),
        vectorised=bool(raw.get("vectorised", raw.get("vectorized", False))),
        case_sensitive=bool(raw.get("case_sensitive", False)),
        whole_word=bool(raw.get("whole_word", True)),
        sticky_prompts=_as_int(raw.get("sticky_prompts"), 0),
        cooldown_prompts=_as_int(raw.get("cooldown_prompts"), 0),
        delay_prompts=_as_int(raw.get("delay_prompts"), 0),
        extra={
            k: copy.deepcopy(v)
            for k, v in raw.items()
            if k not in NATIVE_MAPPED_FIELDS
        },
        raw=copy.deepcopy(raw),
        source="native",
    )


def parse_lorebook_file(data: bytes | str | dict) -> LorebookFile:
    """Parse a world-info or native lorebook file, whole."""
    if isinstance(data, (bytes, bytearray)):
        if len(data) > MAX_LOREBOOK_BYTES:
            raise LorebookParseError(
                f"lorebook file is {len(data)} bytes, exceeding limit of {MAX_LOREBOOK_BYTES} bytes"
            )
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LorebookParseError(f"lorebook file is not UTF-8: {exc}") from exc
        data = text
    if isinstance(data, str):
        try:
            data = safe_json_loads(data, limit=MAX_LOREBOOK_BYTES)
        except SafetyError as exc:
            raise LorebookParseError(str(exc)) from exc
    if not isinstance(data, dict):
        raise LorebookParseError("lorebook file must be a JSON object")
    raw_entries = data.get("entries")
    if raw_entries is None:
        raise LorebookParseError("lorebook file has no 'entries'")

    if isinstance(raw_entries, dict):
        ordered = [
            (k, raw_entries[k])
            for k in sorted(raw_entries, key=lambda k: (len(str(k)), str(k)))
        ]
        entries = [_entry_from_worldinfo(e, uid=str(k)) for k, e in ordered]
        source_format = "worldinfo"
    elif isinstance(raw_entries, list):
        if raw_entries and isinstance(raw_entries[0], dict) and (
            "key" in raw_entries[0] or "keysecondary" in raw_entries[0]
        ):
            entries = [_entry_from_worldinfo(e, uid=None) for e in raw_entries]
            source_format = "worldinfo"
        else:
            # A list of native-shaped entries is the native shape,
            # with or without the format marker (parse_import's own
            # rule treats it so).
            entries = [_entry_from_native(e) for e in raw_entries]
            source_format = "native"
    else:
        raise LorebookParseError("'entries' must be an object or a list")

    if source_format == "native":
        name = _as_str(data.get("name"))
        if not name:
            raise LorebookParseError("lorebook file needs a name")
        return LorebookFile(
            name=name,
            entries=entries,
            description=_as_str(data.get("description")),
            scan_depth=_as_int(data.get("scan_depth"), 4),
            token_budget=data.get("token_budget"),
            extra={
                k: copy.deepcopy(v)
                for k, v in data.items()
                if k
                not in (
                    "name",
                    "entries",
                    "description",
                    "scan_depth",
                    "token_budget",
                    "format",
                    "version",
                )
            },
            raw=copy.deepcopy(data),
            source_format="native",
        )

    original = data.get("originalData")
    return LorebookFile(
        name=_as_str(data.get("name")) or "Imported lorebook",
        entries=entries,
        original_data=copy.deepcopy(original) if isinstance(original, dict) else None,
        extra={
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in ("name", "entries", "originalData")
        },
        raw=copy.deepcopy(data),
        source_format="worldinfo",
    )


def _export_worldinfo_entry(entry: WorldInfoEntry) -> dict:
    # Only a world-info-shaped raw may seed the export; a native
    # entry's raw carries native spellings that are not world-info
    # fields and must not leak in as duplicates.
    obj: dict = copy.deepcopy(entry.raw) if entry.source == "worldinfo" and entry.raw else {}
    # World-info spellings are overlaid from the normalized fields;
    # fields that arrived in the file keep their place, fields that
    # never arrived are written only when they carry a value the
    # defaults would lose (the persona no-fabrication rule).
    obj["comment"] = entry.name
    obj["content"] = entry.content
    obj["key"] = list(entry.keys)
    obj["keysecondary"] = list(entry.secondary_keys)
    obj["constant"] = entry.constant
    obj["disable"] = not entry.enabled
    obj["order"] = entry.priority
    code = entry.position_code
    if code is None:
        code = CODE_FROM_POSITION.get(entry.position, 0)
    obj["position"] = code
    if "caseSensitive" in obj or entry.case_sensitive:
        obj["caseSensitive"] = entry.case_sensitive
    if "matchWholeWords" in obj or not entry.whole_word:
        obj["matchWholeWords"] = entry.whole_word
    for src, value in (
        ("sticky", entry.sticky_prompts),
        ("cooldown", entry.cooldown_prompts),
        ("delay", entry.delay_prompts),
    ):
        if src in obj or value:
            obj[src] = value
    if entry.depth is not None:
        obj["depth"] = entry.depth
    # Role (P-038): written back as its world-info CODE under the
    # no-fabrication rule -- only when the source file carried a
    # role or the entry's role differs from the default (system).
    if "role" in obj or entry.role != DEFAULT_ROLE:
        obj["role"] = CODE_FROM_ROLE[entry.role]
    if "selectiveLogic" in obj or entry.selective_logic != DEFAULT_SELECTIVE_LOGIC:
        obj["selectiveLogic"] = worldinfo_code(entry.selective_logic)
    # Inclusion groups (P-034): same no-fabrication rule -- write
    # the world-info spellings only when the source file carried
    # them or the values differ from the defaults.
    if "group" in obj or entry.inclusion_group:
        obj["group"] = entry.inclusion_group
    if "groupWeight" in obj or entry.group_weight != DEFAULT_GROUP_WEIGHT:
        obj["groupWeight"] = entry.group_weight
    # Entry states (P-035): same no-fabrication rule -- write the
    # world-info spelling only when the source carried it or the
    # entry carries the vectorised flag.
    if "vectorized" in obj or entry.vectorised:
        obj["vectorized"] = entry.vectorised
    # Probability (P-036): same no-fabrication rule.
    if "probability" in obj or entry.probability != DEFAULT_PROBABILITY:
        obj["probability"] = entry.probability
    if "useProbability" in obj or not entry.use_probability:
        obj["useProbability"] = entry.use_probability
    # Part III fields and unknowns ride back verbatim.
    for key, value in entry.extra.items():
        obj[key] = copy.deepcopy(value)
    return obj


def export_worldinfo(book: LorebookFile) -> dict:
    """Export as a world-info JSON object (uid-keyed entries)."""
    obj: dict = {}
    if book.source_format == "worldinfo" and book.raw:
        obj = copy.deepcopy(book.raw)
    obj["name"] = book.name
    entries_obj: dict = {}
    for index, entry in enumerate(book.entries):
        uid = entry.uid if entry.uid is not None else str(index)
        entries_obj[uid] = _export_worldinfo_entry(entry)
    obj["entries"] = entries_obj
    if book.original_data is not None:
        obj["originalData"] = copy.deepcopy(book.original_data)
    for key, value in book.extra.items():
        obj.setdefault(key, copy.deepcopy(value))
    return obj


def export_worldinfo_bytes(book: LorebookFile) -> bytes:
    return json.dumps(export_worldinfo(book), ensure_ascii=False, indent=2).encode("utf-8")


def export_native(book: LorebookFile) -> dict:
    """Export in Rúnmál's native shape (transfer.export_book's set)."""
    return {
        "format": "runmal-lorebook",
        "version": 1,
        "name": book.name,
        "description": book.description,
        "scan_depth": book.scan_depth if book.scan_depth is not None else 4,
        "token_budget": book.token_budget,
        "entries": [e.native_fields() for e in book.entries],
    }


def worldinfo_from_native(book: dict, entries: list[dict]) -> dict:
    """World-info export for a book held as native API dicts.

    Used by the export endpoint's ``format=worldinfo`` shape: only
    the natively-modelled fields exist on that side, so only they
    are written — nothing is fabricated from nothing.
    """
    # API dicts carry DB bookkeeping (ids, timestamps) that is not
    # file content; it must not leak into the exported file.
    bookkeeping = {"id", "lorebook_id", "created_at", "updated_at", "activation_kind"}
    file = LorebookFile(
        name=_as_str(book.get("name")) or "Imported lorebook",
        description=_as_str(book.get("description")),
        scan_depth=_as_int(book.get("scan_depth"), 4),
        token_budget=book.get("token_budget"),
        entries=[
            _entry_from_native({k: v for k, v in e.items() if k not in bookkeeping})
            for e in entries
        ],
        source_format="native",
    )
    return export_worldinfo(file)
