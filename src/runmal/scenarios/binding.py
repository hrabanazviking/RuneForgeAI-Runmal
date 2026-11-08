"""Scenario-to-chat binding (P-132, Part IX — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record — see the P-132 slice doc.
P-131 made scenario definitions stored truth and named
this seam in its own weighing: "Instantiation / seeding —
declined, named seam… The P-093 seed_variables contract
is the named next slice's seam." This module is that
slice. What binding honestly is here:

- a stored definition attaches to ONE chat the same owner
  owns, and the attachment is itself a stored, versioned,
  owner-scoped record (the house JSON pattern: a
  ``scenario_bindings.json`` document beside P-131's
  ``scenarios.json``; NO migration, head stays 0041).
- the definition's declared setup materialises through
  the machinery that already exists, and through nothing
  else: bootstrap messages the author wrote become the
  chat's opening messages via the chat service's append
  road (the P-079 greeting precedent — placed author
  text, one P-075 provenance record per message, origin
  facts naming the definition, its pinned revision and
  the bootstrap index); initial flags and variables seed
  through P-093's ``seed_variables`` with the scenario
  writer, missing keys only, exactly as that contract
  was written for Part IX.
- nothing is fabricated and nothing is executed: no word
  is written that the author did not write (blank
  bootstrap entries seed nothing and are recorded as
  skipped), no condition is evaluated, no scripting is
  run (P-027: stored content is data, never code — a
  stored definition's unmappable machinery lives only in
  its P-131 report and never reaches this module),
  template / system-prompt text is NOT installed as chat
  configuration, and the cast is recorded as data and
  used only to attribute the author's own lines to the
  role that was declared to speak them.
- binding is an opening act: the chat must be empty and
  one-to-one (the P-079 law — an opening setup cannot
  honestly land mid-conversation, and a group room has
  no single scenario seat in this slice), and a chat
  carries at most one active binding. Every refusal is
  decided before any write of any kind.
- unbinding removes only the binding record. Seeded
  messages and variables are the chat's own truth by
  then and stay; the DELETE road's answer says so.
"""

from __future__ import annotations

import copy
import json
import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from runmal.scenarios.store import ScenarioStore

BINDINGS_VERSION = 1
BINDINGS_FILENAME = "scenario_bindings.json"

#: Bootstrap kind -> chat role. Kinds are the P-026 native
#: set (the parser coerces anything else to "message" at
#: the store door, with the warning carried in the P-131
#: report); this map is the whole placement law.
_KIND_TO_ROLE = {
    "user": "user",
    "instructions": "system",
}
_DEFAULT_ROLE = "assistant"


class ScenarioBindingError(ValueError):
    """A binding operation the state of the world forbids."""


class BindingNotFoundError(ScenarioBindingError):
    """Unknown or foreign definition / chat (never leaks)."""


class BindingConflictError(ScenarioBindingError):
    """The chat cannot take a binding as it stands."""


def bindings_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / BINDINGS_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ record


@dataclass(frozen=True)
class ScenarioBinding:
    """One chat's binding to one stored definition.

    ``definition_revision`` is pinned at bind time: if the
    definition is later replaced, this record still says
    which revision actually materialised. ``cast`` is the
    definition's declared roles, as data. The seeded /
    skipped lists are the materialisation's own account,
    read back from what actually landed — never intended
    counts.
    """

    id: str
    owner_id: str
    chat_id: str
    definition_id: str
    definition_name: str
    definition_revision: int
    bound_at: str
    cast: list = field(default_factory=list)
    seeded_messages: list = field(default_factory=list)
    seeded_keys: list = field(default_factory=list)
    skipped: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "chat_id": self.chat_id,
            "definition_id": self.definition_id,
            "definition_name": self.definition_name,
            "definition_revision": self.definition_revision,
            "bound_at": self.bound_at,
            "cast": copy.deepcopy(self.cast),
            "seeded_messages": copy.deepcopy(self.seeded_messages),
            "seeded_keys": list(self.seeded_keys),
            "skipped": copy.deepcopy(self.skipped),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioBinding:
        return cls(
            id=str(data.get("id", "")),
            owner_id=str(data.get("owner_id", "")),
            chat_id=str(data.get("chat_id", "")),
            definition_id=str(data.get("definition_id", "")),
            definition_name=str(data.get("definition_name", "")),
            definition_revision=int(data.get("definition_revision", 0)),
            bound_at=str(data.get("bound_at", "")),
            cast=copy.deepcopy(data.get("cast")) if isinstance(data.get("cast"), list) else [],
            seeded_messages=(
                copy.deepcopy(data["seeded_messages"])
                if isinstance(data.get("seeded_messages"), list) else []
            ),
            seeded_keys=(
                [str(k) for k in data["seeded_keys"]]
                if isinstance(data.get("seeded_keys"), list) else []
            ),
            skipped=(
                copy.deepcopy(data["skipped"])
                if isinstance(data.get("skipped"), list) else []
            ),
        )


# ------------------------------------------------------------- store


class ScenarioBindingStore:
    """Durable binding store: scenario_bindings.json."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> list[ScenarioBinding]:
        try:
            doc = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(doc, dict):
            return []
        rows = doc.get("bindings")
        if not isinstance(rows, list):
            return []
        return [ScenarioBinding.from_dict(r) for r in rows if isinstance(r, dict)]

    def _save(self, rows: list[ScenarioBinding]) -> None:
        doc = {
            "version": BINDINGS_VERSION,
            "bindings": [row.to_dict() for row in rows],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    def add(self, record: ScenarioBinding) -> ScenarioBinding:
        rows = self._load()
        rows.append(record)
        self._save(rows)
        return record

    def get_for_chat(
        self, chat_id: str, owner_id: str
    ) -> ScenarioBinding | None:
        """The chat's active binding for this owner, or None
        — a foreign chat answers exactly like an unbound one."""
        for row in self._load():
            if row.chat_id == chat_id and row.owner_id == owner_id:
                return row
        return None

    def list_for_owner(self, owner_id: str) -> list[ScenarioBinding]:
        return [row for row in self._load() if row.owner_id == owner_id]

    def list_for_definition(
        self, definition_id: str, owner_id: str
    ) -> list[ScenarioBinding]:
        return [
            row for row in self._load()
            if row.definition_id == definition_id and row.owner_id == owner_id
        ]

    def remove_for_chat(
        self, chat_id: str, owner_id: str
    ) -> ScenarioBinding | None:
        """Remove the chat's binding record; return it or None.
        Only the record goes — seeded content is the chat's."""
        rows = self._load()
        removed = [
            row for row in rows
            if row.chat_id == chat_id and row.owner_id == owner_id
        ]
        if not removed:
            return None
        self._save([
            row for row in rows
            if not (row.chat_id == chat_id and row.owner_id == owner_id)
        ])
        return removed[0]


# ------------------------------------------------- materialisation plan


def _speaker_name(definition: dict, entry: dict, chat_role: str) -> str | None:
    """Who the author declared to speak this line.

    The entry's own role label, resolved against the
    declared cast (a name match speaks under the role's
    character_name when one is declared); an unmatched
    label rides verbatim — it is the author's own word
    for the speaker. No label: the narrator for placed
    lines, the impersonation name for user lines, else
    no speaker. An id is never fabricated.
    """
    label = entry.get("role")
    if isinstance(label, str) and label.strip():
        for role in definition.get("roles") or []:
            if not isinstance(role, dict):
                continue
            if role.get("name") == label:
                return role.get("character_name") or label
            if role.get("character_name") == label:
                return label
        return label
    if chat_role == "user":
        name = definition.get("impersonation_name")
        return name if isinstance(name, str) and name else None
    if chat_role == "assistant":
        name = definition.get("narrator_name")
        return name if isinstance(name, str) and name else None
    return None


def _seedable(where: str, key, value) -> str | None:
    """None when the P-093 store can take this entry, else
    the honest reason it is skipped. The store's own law
    decides: its key resolution and its value check are
    called, never re-implemented here."""
    from runmal.plugins.variables import ChatVariableError, resolve_key

    try:
        resolve_key(key, "scenario", "runmal.scenario")
    except ChatVariableError as exc:
        return f"key refused by the P-093 store: {exc}"
    if where == "initial_flags" and not isinstance(value, bool):
        return "flag value is not a bool; flags hold bool only"
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        from runmal.plugins.variables import MAX_VALUE_CHARS

        if len(value) > MAX_VALUE_CHARS:
            return f"string value exceeds {MAX_VALUE_CHARS} chars"
        return None
    if isinstance(value, int):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "numeric value is not finite"
    return f"value is {type(value).__name__}, not a typed scalar"


def plan_materialisation(definition: dict) -> dict:
    """The bind plan for one stored definition (pure).

    Returns {"messages": [{bootstrap_index, kind,
    chat_role, text, speaker_name}], "flags": {..},
    "variables": {..}, "skipped": [{where, key_or_index,
    reason}]}. Only what the author actually declared is
    planned; everything unplannable is accounted in
    ``skipped`` with its reason, in declaration order.
    """
    messages: list[dict] = []
    skipped: list[dict] = []
    bootstrap = definition.get("bootstrap_messages")
    if isinstance(bootstrap, list):
        for index, entry in enumerate(bootstrap):
            if not isinstance(entry, dict):
                skipped.append({
                    "where": "bootstrap", "key_or_index": index,
                    "reason": "bootstrap entry is not an object",
                })
                continue
            text = entry.get("text")
            if not isinstance(text, str):
                skipped.append({
                    "where": "bootstrap", "key_or_index": index,
                    "reason": "bootstrap text is not a string",
                })
                continue
            if not text.strip():
                skipped.append({
                    "where": "bootstrap", "key_or_index": index,
                    "reason": "bootstrap text is blank; nothing is fabricated to fill it",
                })
                continue
            kind = entry.get("kind")
            kind = kind if isinstance(kind, str) and kind else "message"
            chat_role = _KIND_TO_ROLE.get(kind, _DEFAULT_ROLE)
            messages.append({
                "bootstrap_index": index,
                "kind": kind,
                "chat_role": chat_role,
                "text": text,
                "speaker_name": _speaker_name(definition, entry, chat_role),
            })
    seedable: dict[str, dict] = {"initial_flags": {}, "initial_variables": {}}
    for where in ("initial_flags", "initial_variables"):
        mapping = definition.get(where)
        if not isinstance(mapping, dict):
            continue
        for key, value in mapping.items():
            reason = _seedable(where, key, value)
            if reason is None:
                seedable[where][key] = value
            else:
                skipped.append({
                    "where": where, "key_or_index": str(key),
                    "reason": reason,
                })
    return {
        "messages": messages,
        "flags": seedable["initial_flags"],
        "variables": seedable["initial_variables"],
        "skipped": skipped,
    }


# ------------------------------------------------------------ service


async def bind_scenario(
    session,
    user_id: str,
    definition_id: str,
    chat_id: str,
    *,
    definitions: ScenarioStore | None = None,
    bindings: ScenarioBindingStore | None = None,
    variables_base_dir: Path | None = None,
    now: str | None = None,
) -> ScenarioBinding:
    """Bind one owned definition to one owned empty chat.

    Refusals (all decided before any write): unknown or
    foreign definition or chat -> BindingNotFoundError;
    group room, already-bound chat, non-empty chat ->
    BindingConflictError. On success the definition's
    flags and variables seed through P-093 (missing keys
    only), its bootstrap lines land as the chat's opening
    messages with P-075 provenance, and the binding
    record — written last, from what actually landed —
    is returned.
    """
    from sqlalchemy import select

    from runmal.chats import provenance as prov_mod
    from runmal.chats import service as chat_service
    from runmal.db.models import Chat
    from runmal.plugins.variables import seed_variables
    from runmal.scenarios.store import definitions_path

    definitions = definitions or ScenarioStore(definitions_path())
    bindings = bindings or ScenarioBindingStore(bindings_path())

    record = definitions.get(definition_id, user_id)
    if record is None:
        raise BindingNotFoundError("scenario definition not found")
    result = await session.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise BindingNotFoundError("chat not found")
    if chat.group_id is not None:
        raise BindingConflictError(
            "group rooms take no scenario binding in this slice")
    if bindings.get_for_chat(chat_id, user_id) is not None:
        raise BindingConflictError("chat already has a scenario binding")
    history = await chat_service.get_history(session, user_id, chat_id)
    if history:
        raise BindingConflictError(
            "chat already has messages; a scenario binding is an opening act")

    definition = record.definition
    plan = plan_materialisation(definition)
    skipped = list(plan["skipped"])

    seeded_keys: list[str] = []
    for where, mapping in (
        ("initial_flags", plan["flags"]),
        ("initial_variables", plan["variables"]),
    ):
        if not mapping:
            continue
        landed = seed_variables(
            user_id, chat_id, mapping, base_dir=variables_base_dir)
        seeded_keys.extend(landed)
        for key in mapping:
            from runmal.plugins.variables import resolve_key

            full_key, _, _ = resolve_key(key, "scenario", "runmal.scenario")
            if full_key not in landed:
                skipped.append({
                    "where": where, "key_or_index": str(key),
                    "reason": "already present; seeding never overwrites live state",
                })

    preset = await chat_service._preset_snapshot(session, user_id, chat)
    seeded_messages: list[dict] = []
    for step in plan["messages"]:
        provenance = prov_mod.build_record(
            origin_kind="manual",
            origin={
                "source": "scenario_bootstrap",
                "definition_id": record.id,
                "definition_revision": record.revision,
                "bootstrap_index": step["bootstrap_index"],
                "bootstrap_kind": step["kind"],
            },
            model=prov_mod.model_section(status="not_applicable"),
            preset=preset,
            lore=prov_mod.lore_section(status="not_applicable"),
            speaker={
                "speaker_id": None,
                "speaker_name": step["speaker_name"],
            },
        )
        message = await chat_service.append_message(
            session, user_id, chat_id,
            step["chat_role"], step["text"],
            speaker_name=step["speaker_name"],
            event_data={
                "scenario": True,
                "definition_id": record.id,
                "definition_revision": record.revision,
                "bootstrap_index": step["bootstrap_index"],
                "bootstrap_kind": step["kind"],
            },
            provenance=provenance,
        )
        seeded_messages.append({
            "message_id": message.id,
            "bootstrap_index": step["bootstrap_index"],
            "kind": step["kind"],
            "chat_role": step["chat_role"],
            "speaker_name": step["speaker_name"],
        })

    binding = ScenarioBinding(
        id=str(uuid.uuid4()),
        owner_id=user_id,
        chat_id=chat_id,
        definition_id=record.id,
        definition_name=record.name,
        definition_revision=record.revision,
        bound_at=now or _now_iso(),
        cast=(
            copy.deepcopy(definition.get("roles"))
            if isinstance(definition.get("roles"), list) else []
        ),
        seeded_messages=seeded_messages,
        seeded_keys=seeded_keys,
        skipped=skipped,
    )
    return bindings.add(binding)


def get_binding(
    bindings: ScenarioBindingStore, user_id: str, chat_id: str
) -> ScenarioBinding | None:
    """The chat's active binding for this owner, or None."""
    return bindings.get_for_chat(chat_id, user_id)


def unbind(
    bindings: ScenarioBindingStore, user_id: str, chat_id: str
) -> ScenarioBinding | None:
    """Remove the chat's binding record only; return it or
    None. Seeded messages and variables stay with the chat."""
    return bindings.remove_for_chat(chat_id, user_id)


__all__ = [
    "BINDINGS_FILENAME",
    "BINDINGS_VERSION",
    "BindingConflictError",
    "BindingNotFoundError",
    "ScenarioBinding",
    "ScenarioBindingError",
    "ScenarioBindingStore",
    "bind_scenario",
    "bindings_path",
    "get_binding",
    "plan_materialisation",
    "unbind",
]
