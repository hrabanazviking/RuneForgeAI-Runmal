"""Dice & game-bridge plugin surface (P-096).

Roadmap line: "Dice & game-bridge plugin surface:
Sagnaskemma rolls and bridge events (VRChat/Skyrim)
exposed as plugin citizens."

A first-class P-081 citizen carrying two surfaces:

- DICE: durable, inspectable rolls in the P-036 honesty
  discipline (the repo's own name for that discipline is
  "the Sagnaskemma dice discipline"). A seeded roll is a
  pure function of (algorithm version, seed, context,
  canonical notation, roll key, die index) - SHA-256,
  first eight digest bytes / 2**64, face derived from
  the draw - so the same record reproduces forever, in
  isolation. Every persisted roll records its notation,
  every face, its draws, its seed and whether it was
  seeded. ``seed=None`` is the honest unseeded path:
  system entropy, ``seeded=False`` on the record,
  inspectable after the fact and never reproducible -
  and :func:`verify_roll` says exactly that.
- BRIDGE EVENTS: declared, inspectable records in the
  citizen's own store - roll results and chat events
  destined for a game client, plus inbound-shaped game
  occurrences - that an external bridge could consume
  through a poll/ack road modelled on the S609 outbox
  discipline (after-cursor poll, per-consumer
  checkpoints, bounded retention with the prune count
  kept honest on the inspect document).

Honest boundaries, stated plainly: this citizen opens
NO socket, imports NO network client and talks to NO
game client. The real transports already exist -
:mod:`runmal.bridge` (the credentialed bridge API) and
:mod:`runmal.bridges` (the VRChat OSC and Skyrim HTTP
adapters) - and this surface is the plugin-side record
layer they could carry, not a second bridge. A
``game.event`` record is never appended to a chat from
here (``chat.write`` is RESERVED in v1; turning game
events into chat turns is the bridge API's credentialed
job), and a ``dice.rolled`` record is minted ONLY by an
actual roll: the generic emit road refuses that kind,
so the log can never claim a roll that did not happen.

Storage is the P-089 durable file idiom: one JSON
document per owner at ``data_dir()/game_bridge/
<user_id>.json``, written atomically (tmp sibling,
chmod 0o600, replace). A corrupt store raises
:class:`DiceBridgeError` and is never silently reset.
No migration: head stays 0041.

Sandbox stance (P-082): only v1 surface permissions
are declared (``chat.read``, ``ui.contribute``), so the
derived resource grant set is EMPTY. The service
functions are trusted host wiring - in-tree code
calling in-tree code - not a plugin-API network
surface. Wiring: :func:`register_plugin` only.
``build_registry`` / ``create_app`` are unchanged; HTTP
routes ride the existing plugins router. See
docs/DICE_GAME_BRIDGE_2026-11-07.md.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.auth import data_dir
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.game-bridge"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "game-bridge-panel"
STORE_SCHEMA = "runmal-p096-game-bridge-v1"
STORE_DIR_NAME = "game_bridge"
DICE_ALGORITHM = "runmal-p096-dice-v1"
MAX_DICE_COUNT = 20
MAX_DICE_SIDES = 1000
MAX_MODIFIER = 10000
MAX_ROLLS_PER_CHAT = 500
MAX_EVENTS_PER_CHAT = 1000
MAX_TEXT_CHARS = 4000
MAX_PAGE_SIZE = 1000
MAX_LABEL_CHARS = 120
DEFAULT_ACTOR = "runmal.host"
BRIDGE_TARGETS = frozenset({"vrchat", "skyrim", "generic"})
BRIDGE_EVENT_KINDS = frozenset({"dice.rolled", "chat.message", "game.event"})
CHAT_MESSAGE_ROLES = frozenset({"user", "assistant", "environment"})
GAME_EVENT_KINDS = frozenset({"player_speech", "world_event"})
DECLARED_EVENTS = ("message.created", "chat.deleted")
MAX_OBSERVED_KEPT = 200
_ID_RE = re.compile(r"[0-9a-fA-F-]{1,64}")
_NOTATION_RE = re.compile(r"^(\d*)d(\d+)(?:(kh|kl)(\d+))?([+-]\d+)?$")
_ROLL_FIELDS = frozenset(
    {"id", "chat_id", "actor", "created_at", "notation", "canonical",
     "count", "sides", "keep", "keep_count", "modifier", "faces",
     "kept", "dropped", "draws", "total", "seed", "seeded",
     "context", "roll_key", "algorithm"})
_EVENT_FIELDS = frozenset(
    {"seq", "id", "kind", "target", "chat_id", "payload",
     "source", "created_at"})


class DiceBridgeError(ValueError):
    """A notation, roll, event or store refusal (house 422)."""


class DiceBridgeNotFoundError(DiceBridgeError):
    """The named roll does not exist in this chat."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_id(value, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise DiceBridgeError(f"invalid {what}: {value!r}")
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise DiceBridgeError(f"invalid {what}: {value!r}") from None
    return value


def _check_actor(value, what: str = "actor") -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiceBridgeError(f"{what} must be a non-empty string")
    if len(value) > MAX_LABEL_CHARS:
        raise DiceBridgeError(f"{what} is too long")
    return value


def _check_target(value) -> str:
    if value is None:
        return "generic"
    if not isinstance(value, str) or value not in BRIDGE_TARGETS:
        raise DiceBridgeError(
            f"unknown bridge target: {value!r} "
            f"(targets are {sorted(BRIDGE_TARGETS)})")
    return value


# -- Dice notation -------------------------------------------------------


@dataclass(frozen=True)
class DiceSpec:
    """One parsed dice notation, in canonical form."""

    count: int
    sides: int
    keep: str | None  # "kh" | "kl" | None
    keep_count: int | None
    modifier: int
    canonical: str

    def to_dict(self) -> dict:
        return {
            "count": self.count, "sides": self.sides,
            "keep": self.keep, "keep_count": self.keep_count,
            "modifier": self.modifier, "canonical": self.canonical,
        }


def parse_notation(text) -> DiceSpec:
    """Parse a dice notation, or refuse it plainly.

    Grammar (case-insensitive, spaces ignored): ``NdM``,
    ``dM``, ``NdM+K`` / ``NdM-K``, and the keep forms
    ``NdMkhJ`` / ``NdMklJ`` with an optional modifier.
    Anything else - empty, exploding (``!``), pooled, or
    multi-term (``2d6+1d4``) - raises DiceBridgeError
    naming the defect; nothing is half-parsed.
    """
    if not isinstance(text, str) or not text.strip():
        raise DiceBridgeError(f"dice notation must be a non-empty string: {text!r}")
    cleaned = re.sub(r"\s+", "", text).lower()
    match = _NOTATION_RE.match(cleaned)
    if match is None:
        raise DiceBridgeError(
            f"malformed dice notation: {text!r} (want NdM, NdM+K, "
            "NdM-K, NdMkhJ or NdMklJ; exploding, pooled and "
            "multi-term notations are not supported)")
    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    keep = match.group(3)
    keep_count = int(match.group(4)) if match.group(4) else None
    modifier = int(match.group(5)) if match.group(5) else 0
    if not 1 <= count <= MAX_DICE_COUNT:
        raise DiceBridgeError(
            f"dice count must be in 1..{MAX_DICE_COUNT}: {count}")
    if not 2 <= sides <= MAX_DICE_SIDES:
        raise DiceBridgeError(
            f"dice sides must be in 2..{MAX_DICE_SIDES}: {sides}")
    if keep is not None and not 1 <= keep_count <= count:
        raise DiceBridgeError(
            f"keep count must be in 1..{count} for {count} dice: {keep_count}")
    if abs(modifier) > MAX_MODIFIER:
        raise DiceBridgeError(
            f"dice modifier must be in -{MAX_MODIFIER}..{MAX_MODIFIER}: {modifier}")
    canonical = f"{count}d{sides}"
    if keep is not None:
        canonical += f"{keep}{keep_count}"
    if modifier > 0:
        canonical += f"+{modifier}"
    elif modifier < 0:
        canonical += f"{modifier}"
    return DiceSpec(count=count, sides=sides, keep=keep,
                    keep_count=keep_count, modifier=modifier,
                    canonical=canonical)


# -- Dice derivation (the P-036 discipline, own version) -----------------


def _check_seed(seed) -> int | None:
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise DiceBridgeError(f"seed must be an integer or None: {seed!r}")
    return seed


def _derive_draw(seed: int, context: str, canonical: str,
                 roll_key: str, die_index: int) -> float:
    """The seeded draw for one die, in [0.0, 1.0). Pure."""
    material = "\x00".join(
        [DICE_ALGORITHM, str(seed), context, canonical, roll_key,
         str(die_index)])
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


@dataclass(frozen=True)
class DiceRoll:
    """One inspectable dice roll: every face, every draw."""

    notation: str
    canonical: str
    count: int
    sides: int
    keep: str | None
    keep_count: int | None
    modifier: int
    faces: tuple
    kept: tuple
    dropped: tuple
    draws: tuple
    total: int
    seed: int | None
    seeded: bool
    context: str = ""
    roll_key: str = ""
    algorithm: str = DICE_ALGORITHM

    def to_dict(self) -> dict:
        return {
            "notation": self.notation, "canonical": self.canonical,
            "count": self.count, "sides": self.sides,
            "keep": self.keep, "keep_count": self.keep_count,
            "modifier": self.modifier, "faces": list(self.faces),
            "kept": list(self.kept), "dropped": list(self.dropped),
            "draws": list(self.draws), "total": self.total,
            "seed": self.seed, "seeded": self.seeded,
            "context": self.context, "roll_key": self.roll_key,
            "algorithm": self.algorithm,
        }


def _keep_split(spec: DiceSpec, faces: list[int]) -> tuple[list[int], list[int]]:
    """(kept, dropped) faces, each in draw order."""
    if spec.keep is None:
        return list(faces), []
    order = sorted(range(len(faces)),
                   key=lambda i: faces[i],
                   reverse=(spec.keep == "kh"))
    kept_idx = sorted(order[: spec.keep_count])
    kept_set = set(kept_idx)
    kept = [faces[i] for i in kept_idx]
    dropped = [face for i, face in enumerate(faces) if i not in kept_set]
    return kept, dropped


def roll_notation(notation, *, seed: int | None = None,
                  context: str = "", roll_key: str | None = None) -> DiceRoll:
    """Roll a notation (the pure road: no store, no event).

    With an integer ``seed`` every die's draw derives from
    (algorithm, seed, context, canonical notation, roll
    key, die index), so the roll reproduces forever from
    its record. ``roll_key`` defaults to the canonical
    notation itself on this road; the persisted road mints
    a fresh uuid per roll so two rolls of one notation
    under one seed stay distinct, each reproducible from
    its own stored key. With ``seed=None`` the draws come
    from system entropy and the record is labelled
    unseeded: inspectable, never reproducible.
    """
    spec = parse_notation(notation)
    seed = _check_seed(seed)
    if not isinstance(context, str):
        raise DiceBridgeError("roll context must be a string")
    if roll_key is None:
        roll_key = spec.canonical
    if not isinstance(roll_key, str) or not roll_key:
        raise DiceBridgeError("roll_key must be a non-empty string")
    entropy = random.Random()
    draws: list[float] = []
    faces: list[int] = []
    for die in range(spec.count):
        if seed is None:
            draw = entropy.random()
        else:
            draw = _derive_draw(seed, context, spec.canonical, roll_key, die)
        draws.append(draw)
        faces.append(min(int(draw * spec.sides), spec.sides - 1) + 1)
    kept, dropped = _keep_split(spec, faces)
    return DiceRoll(
        notation=str(notation), canonical=spec.canonical,
        count=spec.count, sides=spec.sides, keep=spec.keep,
        keep_count=spec.keep_count, modifier=spec.modifier,
        faces=tuple(faces), kept=tuple(kept), dropped=tuple(dropped),
        draws=tuple(draws), total=sum(kept) + spec.modifier,
        seed=seed, seeded=seed is not None, context=context,
        roll_key=roll_key)


def verify_roll(record) -> dict:
    """Re-judge one roll record against its own seed.

    Unseeded records answer ``verifiable: False`` with the
    reason named - they were drawn from system entropy and
    no recomputation can honestly reproduce them. Seeded
    records are re-rolled from (seed, context, canonical,
    roll_key) and the faces and total compared exactly.
    """
    if isinstance(record, DiceRoll):
        data = record.to_dict()
    elif isinstance(record, dict):
        data = record
    else:
        raise DiceBridgeError(f"cannot verify a non-record: {type(record).__name__}")
    if not data.get("seeded") or data.get("seed") is None:
        return {"verifiable": False, "reproduced": False,
                "faces": list(data.get("faces") or []),
                "total": data.get("total"),
                "reason": "unseeded roll: drawn from system entropy, "
                          "inspectable but never reproducible"}
    again = roll_notation(
        data["canonical"], seed=data["seed"],
        context=data.get("context") or "",
        roll_key=data.get("roll_key") or data["canonical"])
    reproduced = (list(again.faces) == list(data.get("faces") or [])
                  and again.total == data.get("total"))
    return {"verifiable": True, "reproduced": reproduced,
            "faces": list(again.faces), "total": again.total,
            "reason": "recomputed from the recorded seed, context, "
                      "canonical notation and roll key"}


# -- Durable per-owner store (file idiom, no migration) ------------------


def store_path(user_id: str, base_dir: Path | None = None) -> Path:
    """The owner's store file under the data dir. The user
    id is validated as a UUID before it becomes a path."""
    _check_id(user_id, "user_id")
    root = Path(base_dir) if base_dir is not None else data_dir()
    return root / STORE_DIR_NAME / f"{user_id}.json"


def _empty_doc() -> dict:
    return {"schema": STORE_SCHEMA, "chats": {}}


def _empty_chat() -> dict:
    return {"rolls": [], "events": [], "next_seq": 1,
            "cursors": {}, "pruned_events": 0}


def _load_doc(user_id: str, base_dir: Path | None = None) -> dict:
    path = store_path(user_id, base_dir)
    if not path.exists():
        return _empty_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiceBridgeError(
            f"game bridge store is unreadable: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != STORE_SCHEMA \
            or not isinstance(doc.get("chats"), dict):
        raise DiceBridgeError("game bridge store has an unknown shape")
    return doc


def _save_doc(user_id: str, doc: dict, base_dir: Path | None = None) -> None:
    path = store_path(user_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _chat_section(doc: dict, chat_id: str) -> dict:
    section = doc["chats"].get(chat_id)
    if section is None:
        return _empty_chat()
    if not isinstance(section, dict) \
            or not isinstance(section.get("rolls"), list) \
            or not isinstance(section.get("events"), list) \
            or not _is_int(section.get("next_seq")) \
            or not isinstance(section.get("cursors"), dict) \
            or not _is_int(section.get("pruned_events")):
        raise DiceBridgeError("game bridge store has an unknown shape")
    return section


def _stored_roll(row) -> dict:
    """A stored roll re-validated on read: corrupt rows
    raise, never silently vanish from the owner's store."""
    if not isinstance(row, dict):
        raise DiceBridgeError("stored roll is not an object")
    extra = set(row) - _ROLL_FIELDS
    if extra:
        raise DiceBridgeError(
            f"stored roll has unknown keys: {sorted(extra)}")
    if row.get("algorithm") != DICE_ALGORITHM:
        raise DiceBridgeError(
            f"stored roll has unknown algorithm: {row.get('algorithm')!r}")
    spec = parse_notation(row.get("canonical"))
    if spec.canonical != row.get("canonical"):
        raise DiceBridgeError("stored roll canonical does not parse back")
    faces = row.get("faces")
    if not isinstance(faces, list) or len(faces) != spec.count \
            or any(not _is_int(face) or not 1 <= face <= spec.sides
                   for face in faces):
        raise DiceBridgeError("stored roll has bad faces")
    kept, dropped = _keep_split(spec, list(faces))
    if row.get("kept") != kept or row.get("dropped") != dropped:
        raise DiceBridgeError("stored roll kept/dropped do not match its faces")
    if row.get("total") != sum(kept) + spec.modifier:
        raise DiceBridgeError("stored roll total does not match its faces")
    return dict(row)


def _stored_event(row) -> dict:
    if not isinstance(row, dict):
        raise DiceBridgeError("stored bridge event is not an object")
    extra = set(row) - _EVENT_FIELDS
    if extra:
        raise DiceBridgeError(
            f"stored bridge event has unknown keys: {sorted(extra)}")
    if row.get("kind") not in BRIDGE_EVENT_KINDS:
        raise DiceBridgeError(
            f"stored bridge event has unknown kind: {row.get('kind')!r}")
    if row.get("target") not in BRIDGE_TARGETS:
        raise DiceBridgeError(
            f"stored bridge event has unknown target: {row.get('target')!r}")
    if not _is_int(row.get("seq")) or row["seq"] < 1:
        raise DiceBridgeError("stored bridge event has a bad seq")
    if not isinstance(row.get("payload"), dict):
        raise DiceBridgeError("stored bridge event payload is not an object")
    return dict(row)


def _append_event(section: dict, chat_id: str, kind: str, target: str,
                  payload: dict, source: str) -> dict:
    row = {
        "seq": section["next_seq"], "id": str(uuid.uuid4()),
        "kind": kind, "target": target, "chat_id": chat_id,
        "payload": copy.deepcopy(payload), "source": source,
        "created_at": _now_iso(),
    }
    section["next_seq"] += 1
    section["events"].append(row)
    while len(section["events"]) > MAX_EVENTS_PER_CHAT:
        section["events"].pop(0)
        section["pruned_events"] += 1
    return copy.deepcopy(row)


# -- Persisted rolls -------------------------------------------------------


def roll_for_chat(user_id: str, chat_id: str, notation, *,
                  seed: int | None = None, context: str = "",
                  target=None, actor: str = DEFAULT_ACTOR,
                  base_dir: Path | None = None) -> dict:
    """Roll, persist and announce one roll for one chat.

    The roll is stored with a freshly minted roll key and
    a ``dice.rolled`` bridge event carrying the full roll
    record is appended in the SAME save - a persisted roll
    and its bridge announcement can never drift apart.
    Returns the stored roll row plus the minted event
    under ``bridge_event`` (the event is stored; the roll
    row itself stays a pure roll record).
    """
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    actor = _check_actor(actor)
    target = _check_target(target)
    roll_key = str(uuid.uuid4())
    roll = roll_notation(notation, seed=seed, context=context,
                         roll_key=roll_key)
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    rolls = [_stored_roll(row) for row in section["rolls"]]
    if len(rolls) >= MAX_ROLLS_PER_CHAT:
        raise DiceBridgeError(
            f"chat already holds {MAX_ROLLS_PER_CHAT} rolls; roll "
            "history is evidence and is never silently pruned - "
            "clear the chat explicitly to start again")
    row = dict(roll.to_dict())
    row.update({"id": roll_key, "chat_id": chat_id, "actor": actor,
                "created_at": _now_iso()})
    section["rolls"] = rolls + [row]
    event = _append_event(section, chat_id, "dice.rolled", target,
                          roll.to_dict(), actor)
    doc["chats"][chat_id] = section
    _save_doc(user_id, doc, base_dir)
    out = copy.deepcopy(row)
    out["bridge_event"] = event
    return out


def list_rolls(user_id: str, chat_id: str, *, limit: int = 100,
               base_dir: Path | None = None) -> list[dict]:
    """One chat's persisted rolls, oldest first."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    if not _is_int(limit) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise DiceBridgeError(
            f"limit must be an int in 1..{MAX_PAGE_SIZE}: {limit!r}")
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    rows = [_stored_roll(row) for row in section["rolls"]]
    return copy.deepcopy(rows[-limit:])


def get_roll(user_id: str, chat_id: str, roll_id: str, *,
             base_dir: Path | None = None) -> dict:
    """One persisted roll by id; a missing id raises
    DiceBridgeNotFoundError - a typo never reads as a roll."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    for row in section["rolls"]:
        stored = _stored_roll(row)
        if stored["id"] == roll_id:
            return copy.deepcopy(stored)
    raise DiceBridgeNotFoundError(f"no roll named {roll_id!r} in this chat")


def verify_persisted_roll(user_id: str, chat_id: str, roll_id: str, *,
                          base_dir: Path | None = None) -> dict:
    """The verification verdict for one persisted roll:
    the roll row plus its :func:`verify_roll` verdict."""
    row = get_roll(user_id, chat_id, roll_id, base_dir=base_dir)
    return {"roll": row, "verification": verify_roll(row)}


# -- Bridge events ---------------------------------------------------------


def _check_text(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiceBridgeError(f"{what} must be a non-empty string")
    if len(value) > MAX_TEXT_CHARS:
        raise DiceBridgeError(f"{what} exceeds {MAX_TEXT_CHARS} chars")
    return value


def _check_speaker(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_LABEL_CHARS:
        raise DiceBridgeError(f"speaker must be a string of at most {MAX_LABEL_CHARS} chars")
    return value


def _validate_payload(kind: str, payload) -> dict:
    """Per-kind payload validation: closed shapes, strict keys."""
    if not isinstance(payload, dict):
        raise DiceBridgeError("bridge event payload must be an object")
    if kind == "chat.message":
        extra = set(payload) - {"role", "speaker", "text"}
        if extra:
            raise DiceBridgeError(
                f"chat.message payload has unknown keys: {sorted(extra)}")
        role = payload.get("role")
        if role not in CHAT_MESSAGE_ROLES:
            raise DiceBridgeError(
                f"chat.message role must be one of {sorted(CHAT_MESSAGE_ROLES)}: {role!r}")
        return {"role": role,
                "speaker": _check_speaker(payload.get("speaker")),
                "text": _check_text(payload.get("text"), "chat.message text")}
    if kind == "game.event":
        extra = set(payload) - {"game_kind", "speaker", "text"}
        if extra:
            raise DiceBridgeError(
                f"game.event payload has unknown keys: {sorted(extra)}")
        game_kind = payload.get("game_kind")
        if game_kind not in GAME_EVENT_KINDS:
            raise DiceBridgeError(
                f"game.event game_kind must be one of {sorted(GAME_EVENT_KINDS)}: {game_kind!r}")
        return {"game_kind": game_kind,
                "speaker": _check_speaker(payload.get("speaker")),
                "text": _check_text(payload.get("text"), "game.event text")}
    raise DiceBridgeError(f"no payload shape for kind: {kind!r}")


def emit_bridge_event(user_id: str, chat_id: str, kind, payload, *,
                      target=None, source: str = DEFAULT_ACTOR,
                      base_dir: Path | None = None) -> dict:
    """Append one bridge event record for one chat.

    ``dice.rolled`` REFUSES here: that kind is minted only
    by :func:`roll_for_chat`, so the log can never claim
    a roll that did not happen. A ``game.event`` record is
    recorded only - it is never appended to the chat
    (``chat.write`` is reserved in v1; the credentialed
    bridge API owns turning game events into turns).
    """
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    source = _check_actor(source, "source")
    target = _check_target(target)
    if kind == "dice.rolled":
        raise DiceBridgeError(
            "dice.rolled events are minted only by an actual roll "
            "(roll_for_chat); the generic emit road never forges one")
    if not isinstance(kind, str) or kind not in BRIDGE_EVENT_KINDS:
        raise DiceBridgeError(
            f"unknown bridge event kind: {kind!r} "
            f"(kinds are {sorted(BRIDGE_EVENT_KINDS)})")
    clean = _validate_payload(kind, payload)
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    section["rolls"] = [_stored_roll(row) for row in section["rolls"]]
    section["events"] = [_stored_event(row) for row in section["events"]]
    row = _append_event(section, chat_id, kind, target, clean, source)
    doc["chats"][chat_id] = section
    _save_doc(user_id, doc, base_dir)
    return row


def list_bridge_events(user_id: str, chat_id: str, *,
                       after_seq: int = 0, limit: int = 100,
                       kind: str | None = None, target: str | None = None,
                       base_dir: Path | None = None) -> list[dict]:
    """The poll road (S609 discipline at plugin scale):
    events with ``seq > after_seq``, oldest first,
    optionally filtered by kind and/or target. A consumer
    resumes from its ack cursor and never re-reads what
    it has acknowledged; events pruned by retention are
    simply absent, with the prune count on the inspect
    document - never a silent gap dressed as complete."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    if not _is_int(after_seq) or after_seq < 0:
        raise DiceBridgeError(f"after_seq must be an int >= 0: {after_seq!r}")
    if not _is_int(limit) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise DiceBridgeError(
            f"limit must be an int in 1..{MAX_PAGE_SIZE}: {limit!r}")
    if kind is not None and kind not in BRIDGE_EVENT_KINDS:
        raise DiceBridgeError(f"unknown bridge event kind: {kind!r}")
    if target is not None:
        target = _check_target(target)
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    rows = [_stored_event(row) for row in section["events"]]
    out = [row for row in rows if row["seq"] > after_seq]
    if kind is not None:
        out = [row for row in out if row["kind"] == kind]
    if target is not None:
        out = [row for row in out if row["target"] == target]
    return copy.deepcopy(out[:limit])


def ack_bridge_events(user_id: str, chat_id: str, consumer, up_to_seq, *,
                      base_dir: Path | None = None) -> dict:
    """Advance one consumer's cursor (its checkpoint).

    Cursors are monotonic: acknowledging backwards
    refuses, because a checkpoint that could rewind
    would re-deliver acknowledged events - the exact
    failure the S609 checkpoint exists to prevent.
    Returns {consumer, cursor, next_seq}.
    """
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    consumer = _check_actor(consumer, "consumer")
    if not _is_int(up_to_seq) or up_to_seq < 0:
        raise DiceBridgeError(f"up_to_seq must be an int >= 0: {up_to_seq!r}")
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    current = section["cursors"].get(consumer, 0)
    if up_to_seq < current:
        raise DiceBridgeError(
            f"consumer cursor is monotonic: {consumer!r} is already "
            f"at {current}, cannot ack backwards to {up_to_seq}")
    section["cursors"][consumer] = up_to_seq
    doc["chats"][chat_id] = section
    _save_doc(user_id, doc, base_dir)
    return {"consumer": consumer, "cursor": up_to_seq,
            "next_seq": section["next_seq"]}


def consumer_cursor(user_id: str, chat_id: str, consumer, *,
                    base_dir: Path | None = None) -> int:
    """One consumer's ack cursor (0 = nothing acked)."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    consumer = _check_actor(consumer, "consumer")
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    return int(section["cursors"].get(consumer, 0))


def clear_chat(user_id: str, chat_id: str, *,
               base_dir: Path | None = None) -> dict:
    """Remove one chat's whole section; returns the counts
    removed. This explicit verb is the ONLY road that
    deletes durable rolls or bridge events in bulk."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    removed = {"rolls": len(section["rolls"]),
               "events": len(section["events"])}
    if chat_id in doc["chats"]:
        del doc["chats"][chat_id]
        _save_doc(user_id, doc, base_dir)
    return removed


def surface_document() -> dict:
    """The whole declared surface as data: what a bridge
    consumer or another plugin needs to speak to this
    citizen without reading its code."""
    return {
        "plugin_id": PLUGIN_ID, "plugin_version": PLUGIN_VERSION,
        "dice_algorithm": DICE_ALGORITHM,
        "notation": "NdM | dM | NdM+K | NdM-K | NdMkhJ[+-K] | NdMklJ[+-K]",
        "max_dice_count": MAX_DICE_COUNT,
        "max_dice_sides": MAX_DICE_SIDES,
        "max_modifier": MAX_MODIFIER,
        "bridge_event_kinds": sorted(BRIDGE_EVENT_KINDS),
        "bridge_targets": sorted(BRIDGE_TARGETS),
        "chat_message_roles": sorted(CHAT_MESSAGE_ROLES),
        "game_event_kinds": sorted(GAME_EVENT_KINDS),
        "max_rolls_per_chat": MAX_ROLLS_PER_CHAT,
        "max_events_per_chat": MAX_EVENTS_PER_CHAT,
        "transport": "none: records only - the runmal.bridge API and "
                     "the runmal.bridges adapters own transport",
    }


def inspect_chat(user_id: str, chat_id: str, *,
                 base_dir: Path | None = None) -> dict:
    """One chat's inspectable state: counts, cursors, the
    prune counter and the declared surface."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    section = _chat_section(doc, chat_id)
    return {
        "chat_id": chat_id,
        "rolls": len(section["rolls"]),
        "events": len(section["events"]),
        "pruned_events": section["pruned_events"],
        "next_seq": section["next_seq"],
        "cursors": dict(section["cursors"]),
        "surface": surface_document(),
    }


# -- The P-081 citizen ------------------------------------------------------


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Dice & Game Bridge",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Seeded, inspectable dice rolls and a "
                       "declared game-bridge event record surface "
                       "(VRChat/Skyrim targets) for plugins.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "chat.toolbar",
                "label": "Dice & Game Bridge",
                "order": 100,
                "payload": {"kind": "panel", "route": "game-bridge"},
            }
        ],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }


def build_manifest():
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


class GameBridgePlugin:
    """The citizen: a UI contribution plus declared chat
    events whose handler observes METADATA ONLY.

    A plugin event carries a chat id but no owner id, so
    no durable owner-scoped write can honestly be made
    from a bare event; the handler keeps a bounded
    in-memory observation list (event name, chat/message
    ids, role, content length - never message text) and
    the durable roads are the explicit service functions
    above. ``chat.deleted`` is observed the same way and
    removes NOTHING: durable rolls and bridge events are
    deleted only by the explicit :func:`clear_chat` verb
    (the P-089/P-093 stance). The observation list is
    process-local and lost on restart, stated plainly.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir
        self._observed: list[dict] = []

    @property
    def manifest(self):
        return build_manifest()

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    def observed_events(self) -> list[dict]:
        """The in-memory metadata observations, oldest first."""
        return copy.deepcopy(self._observed)

    async def on_event(self, event) -> None:
        data = event.data or {}
        self._observed.append({
            "name": event.name,
            "chat_id": event.chat_id,
            "message_id": event.message_id,
            "role": data.get("role"),
            "content_chars": data.get("content_chars"),
        })
        del self._observed[:-MAX_OBSERVED_KEPT]
        return None


def register_plugin(registry: PluginRegistry, *,
                    base_dir: Path | None = None,
                    enable: bool = False,
                    ) -> tuple[PluginRecord, GameBridgePlugin]:
    """Register the citizen into ``registry`` (trusted code only)."""
    plugin = GameBridgePlugin(base_dir)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "BRIDGE_EVENT_KINDS", "BRIDGE_TARGETS", "CHAT_MESSAGE_ROLES",
    "DECLARED_EVENTS", "DEFAULT_ACTOR", "DICE_ALGORITHM",
    "GAME_EVENT_KINDS", "MAX_DICE_COUNT", "MAX_DICE_SIDES",
    "MAX_EVENTS_PER_CHAT", "MAX_MODIFIER", "MAX_OBSERVED_KEPT",
    "MAX_PAGE_SIZE",
    "MAX_ROLLS_PER_CHAT", "PLUGIN_ID", "PLUGIN_VERSION",
    "STORE_DIR_NAME", "STORE_SCHEMA", "UI_LOCAL_ID", "VERSION",
    "DiceBridgeError", "DiceBridgeNotFoundError", "DiceRoll",
    "DiceSpec", "GameBridgePlugin", "ack_bridge_events",
    "build_manifest", "clear_chat", "consumer_cursor",
    "emit_bridge_event", "get_roll", "inspect_chat",
    "list_bridge_events", "list_rolls", "manifest_data",
    "parse_notation", "register_plugin", "roll_for_chat",
    "roll_notation", "sandbox_grants", "store_path",
    "surface_document", "verify_persisted_roll", "verify_roll",
]
