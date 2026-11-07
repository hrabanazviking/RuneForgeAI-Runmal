"""P-058 token budget governor -- the whole prompt's budget by
section, visible before sending, plus trimming by declared policy.

Pure-domain module: no DB, no I/O. It answers, before anything is
sent to a backend, what the WHOLE prompt costs per section
(context / lore / memory / history), and -- when a declared trim
policy is in play -- it applies that policy to the slot list
deterministically, recording every sacrifice it makes.

The honesty contract:

- One counter: every count in this module comes from
  :mod:`runmal.tokens` -- :func:`estimate_tokens` by default, via
  the existing ``prompt/slots.py`` ``slot_tokens`` seam, or the
  caller's supplied ``counter`` labelled EXACT when supplied and
  ESTIMATED otherwise. This module never re-implements the
  heuristic locally (no ``len(text) // 4`` here), so governor
  counts equal composer spend for the same slots.
- Required slots are never trimmed or dropped. If required slots
  alone exceed the budget, the governor returns them untouched;
  it never manufactures a fit by eating the framing.
- Nothing is silent: every drop and every trim yields a
  ``GovernorAction``. A slot the governor did not touch yields
  none. Budgets and actions carry ids, sections, counts and
  reasons only -- never content (S214).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from runmal.prompt.slots import slot_tokens
from runmal.tokens import TokenQuality

__all__ = [
    "SECTIONS",
    "SECTION_CAP_REASON",
    "TOTAL_BUDGET_REASON",
    "DEFAULT_TRIM_ORDER",
    "SectionBudget",
    "WholePromptBudget",
    "BudgetPolicy",
    "GovernorAction",
    "GovernedSlots",
    "section_for_kind",
    "budget_from_slots",
    "budget_from_trace",
    "default_policy",
    "policy_from_data",
    "policy_to_data",
    "apply_policy",
]

SECTIONS = ("context", "lore", "memory", "history")
SECTION_CAP_REASON = "governor_section_cap"
TOTAL_BUDGET_REASON = "governor_total_budget"
DEFAULT_TRIM_ORDER = ("lore", "memory", "history", "context")

_KIND_TO_SECTION = {
    "lore_before": "lore",
    "lore_after": "lore",
    "memory_nucleus": "memory",
    "memory_retrieved": "memory",
    "history": "history",
}


def section_for_kind(kind) -> str:
    """Section for a slot ``kind``; every other kind is context."""
    return _KIND_TO_SECTION.get(kind, "context")


@dataclass(frozen=True)
class SectionBudget:
    section: str
    tokens: int
    slots: int
    slot_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "tokens": self.tokens,
            "slots": self.slots,
            "slot_ids": list(self.slot_ids),
        }


@dataclass(frozen=True)
class WholePromptBudget:
    sections: dict
    total_tokens: int
    input_budget: int
    remaining: int
    over_budget: bool
    count_quality: TokenQuality

    def to_dict(self) -> dict:
        quality = self.count_quality
        return {
            "sections": {
                name: {
                    "tokens": row.tokens,
                    "slots": row.slots,
                    "slot_ids": list(row.slot_ids),
                }
                for name, row in self.sections.items()
            },
            "total_tokens": self.total_tokens,
            "input_budget": self.input_budget,
            "remaining": self.remaining,
            "over_budget": self.over_budget,
            "count_quality": (
                quality.value if isinstance(quality, TokenQuality) else quality
            ),
        }


def budget_from_slots(slots, *, input_budget, counter=None) -> WholePromptBudget:
    """Whole-prompt budget grouped by section, counted once per slot."""
    if isinstance(input_budget, bool) or not isinstance(input_budget, int):
        raise ValueError("input_budget must be an int")
    if input_budget < 0:
        raise ValueError("input_budget must be >= 0")
    grouped = {name: [] for name in SECTIONS}
    total = 0
    for slot in slots:
        tokens = slot_tokens(slot, counter)
        total += tokens
        grouped[section_for_kind(slot.kind)].append((slot.id, tokens))
    sections = {}
    for name in SECTIONS:
        rows = grouped[name]
        sections[name] = SectionBudget(
            section=name,
            tokens=sum(t for _sid, t in rows),
            slots=len(rows),
            slot_ids=tuple(sid for sid, _t in rows),
        )
    return WholePromptBudget(
        sections=sections,
        total_tokens=total,
        input_budget=input_budget,
        remaining=input_budget - total,
        over_budget=total > input_budget,
        count_quality=(
            TokenQuality.EXACT if counter is not None else TokenQuality.ESTIMATED
        ),
    )


def budget_from_trace(trace: dict) -> dict:
    """Per-section budget summed from an inspect trace dict.

    Pure function over the ``trace_to_dict`` shape: it counts
    nothing itself, it sums the composer's own manifest numbers
    carried in the trace, so included totals reconcile exactly
    with ``ledger["total_input_tokens"]``.
    """
    ledger = trace["ledger"]
    sections = {
        name: {"included_tokens": 0, "discarded_tokens": 0, "slots": 0}
        for name in SECTIONS
    }
    for row in trace.get("slots", []):
        section = section_for_kind(row.get("kind") or "")
        summary = sections[section]
        summary["slots"] += 1
        tokens = row.get("tokens") or 0
        if row.get("status") == "included":
            summary["included_tokens"] += tokens
        elif row.get("status") == "discarded":
            summary["discarded_tokens"] += tokens
    return {
        "sections": sections,
        "total_input_tokens": ledger["total_input_tokens"],
        "input_budget": ledger["input_budget"],
        "remaining_input_tokens": ledger["remaining_input_tokens"],
        "count_quality": ledger["count_quality"],
    }


def _validate_cap(section, value) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"section cap for {section!r} must be None or an int >= 1"
        )


def _validate_trim_order(names) -> tuple:
    seen = set()
    order = []
    for name in names:
        if name not in SECTIONS:
            raise ValueError(f"unknown section in trim_order: {name!r}")
        if name in seen:
            raise ValueError(f"duplicate section in trim_order: {name!r}")
        seen.add(name)
        order.append(name)
    for name in DEFAULT_TRIM_ORDER:
        if name not in seen:
            order.append(name)
    return tuple(order)


@dataclass(frozen=True)
class BudgetPolicy:
    section_caps: dict = field(default_factory=dict)
    trim_order: tuple = DEFAULT_TRIM_ORDER

    def __post_init__(self) -> None:
        if not isinstance(self.section_caps, dict):
            raise ValueError("section_caps must be a dict")
        unknown = [k for k in self.section_caps if k not in SECTIONS]
        if unknown:
            raise ValueError(f"unknown section(s) in section_caps: {unknown!r}")
        for section, value in self.section_caps.items():
            _validate_cap(section, value)
        object.__setattr__(self, "section_caps", dict(self.section_caps))
        if isinstance(self.trim_order, str) or not hasattr(self.trim_order, "__iter__"):
            raise ValueError("trim_order must be a sequence of section names")
        object.__setattr__(
            self, "trim_order", _validate_trim_order(tuple(self.trim_order))
        )


def default_policy() -> BudgetPolicy:
    return BudgetPolicy(
        section_caps={s: None for s in SECTIONS},
        trim_order=DEFAULT_TRIM_ORDER,
    )


def policy_from_data(data) -> BudgetPolicy:
    """Strict boundary: a malformed policy is refused, never repaired."""
    if data is None:
        return default_policy()
    if not isinstance(data, dict):
        raise ValueError("budget policy must be a dict")
    allowed = {"section_caps", "trim_order"}
    unknown_keys = [k for k in data if k not in allowed]
    if unknown_keys:
        raise ValueError(f"unknown budget policy key(s): {unknown_keys!r}")
    caps_in = data.get("section_caps", {})
    if not isinstance(caps_in, dict):
        raise ValueError("section_caps must be a dict")
    unknown_sections = [k for k in caps_in if k not in SECTIONS]
    if unknown_sections:
        raise ValueError(f"unknown section(s) in section_caps: {unknown_sections!r}")
    for section, value in caps_in.items():
        _validate_cap(section, value)
    caps = {s: caps_in.get(s) for s in SECTIONS}
    if "trim_order" in data and data["trim_order"] is not None:
        raw_order = data["trim_order"]
        if not isinstance(raw_order, list):
            raise ValueError("trim_order must be a list of section names")
        trim_order = _validate_trim_order(raw_order)
    else:
        trim_order = DEFAULT_TRIM_ORDER
    return BudgetPolicy(section_caps=caps, trim_order=trim_order)


def policy_to_data(policy: BudgetPolicy) -> dict:
    return {
        "section_caps": {s: policy.section_caps.get(s) for s in SECTIONS},
        "trim_order": list(policy.trim_order),
    }


@dataclass(frozen=True)
class GovernorAction:
    slot_id: str
    section: str
    tokens_before: int
    tokens_after: int
    action: str
    reason: str
    trimmed_parts: int = 0

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "section": self.section,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "action": self.action,
            "reason": self.reason,
            "trimmed_parts": self.trimmed_parts,
        }


@dataclass(frozen=True)
class GovernedSlots:
    kept: tuple
    actions: tuple


def _sacrifice_sorted(entries):
    """Priority asc, then order desc, then id desc (stable sorts)."""
    result = sorted(entries, key=lambda e: e["slot"].id, reverse=True)
    result = sorted(result, key=lambda e: e["slot"].order, reverse=True)
    result = sorted(result, key=lambda e: e["slot"].priority)
    return result


def apply_policy(slots, policy, *, input_budget, counter=None) -> GovernedSlots:
    if isinstance(input_budget, bool) or not isinstance(input_budget, int):
        raise ValueError("input_budget must be an int")
    if input_budget < 0:
        raise ValueError("input_budget must be >= 0")
    if policy is None:
        policy = default_policy()
    entries = [
        {
            "slot": slot,
            "tokens": slot_tokens(slot, counter),
            "orig_parts": len(slot.parts) if slot.splittable else 0,
        }
        for slot in slots
    ]
    actions: list = []

    def total():
        return sum(e["tokens"] for e in entries)

    def section_total(name):
        return sum(
            e["tokens"] for e in entries if section_for_kind(e["slot"].kind) == name
        )

    def record(records, entry, before, trimmed_delta, dropped):
        key = id(entry)
        rec = records.get(key)
        if rec is None:
            rec = {
                "slot_id": entry["slot"].id,
                "section": section_for_kind(entry["slot"].kind),
                "tokens_before": before,
                "trimmed": 0,
                "dropped": False,
                "orig_parts": entry["orig_parts"],
                "splittable": bool(entry["slot"].splittable),
                "entry": entry,
            }
            records[key] = rec
        rec["trimmed"] += trimmed_delta
        if dropped:
            rec["dropped"] = True
        return rec

    def finalize(records, reason):
        for rec in records.values():
            if rec["dropped"]:
                trimmed = rec["orig_parts"] if rec["splittable"] else 0
                actions.append(GovernorAction(
                    slot_id=rec["slot_id"], section=rec["section"],
                    tokens_before=rec["tokens_before"], tokens_after=0,
                    action="dropped", reason=reason, trimmed_parts=trimmed,
                ))
            else:
                actions.append(GovernorAction(
                    slot_id=rec["slot_id"], section=rec["section"],
                    tokens_before=rec["tokens_before"],
                    tokens_after=rec["entry"]["tokens"],
                    action="trimmed", reason=reason,
                    trimmed_parts=rec["trimmed"],
                ))

    def sacrifice_one(section, records):
        cands = [
            e for e in entries
            if not e["slot"].required
            and section_for_kind(e["slot"].kind) == section
        ]
        if not cands:
            return False
        splittable = [e for e in cands if e["slot"].splittable and e["slot"].parts]
        if splittable:
            entry = _sacrifice_sorted(splittable)[0]
            before = entry["tokens"]
            new_parts = entry["slot"].parts[1:]
            if new_parts:
                new_slot = replace(entry["slot"], parts=new_parts)
                entry["slot"] = new_slot
                entry["tokens"] = slot_tokens(new_slot, counter)
                record(records, entry, before, 1, False)
            else:
                record(records, entry, before, 1, True)
                entries.remove(entry)
            return True
        victim = _sacrifice_sorted(cands)[0]
        record(records, victim, victim["tokens"], 0, True)
        entries.remove(victim)
        return True

    # Phase 1: section caps, in SECTIONS order.
    for section in SECTIONS:
        cap = policy.section_caps.get(section)
        if cap is None:
            continue
        records: dict = {}
        while section_total(section) > cap:
            if not sacrifice_one(section, records):
                break
        finalize(records, SECTION_CAP_REASON)

    # Phase 2: total budget, walking trim_order, one step per section.
    records2: dict = {}
    while total() > input_budget:
        progressed = False
        for section in policy.trim_order:
            if total() <= input_budget:
                break
            if sacrifice_one(section, records2):
                progressed = True
        if not progressed:
            break
    finalize(records2, TOTAL_BUDGET_REASON)

    return GovernedSlots(
        kept=tuple(e["slot"] for e in entries),
        actions=tuple(actions),
    )
