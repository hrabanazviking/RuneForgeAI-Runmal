"""Prompt Trace + token ledger (roadmap S214).

The trace is the explainability artifact for one composition
(PROMPT_COMPOSER.md §9): a safe manifest that answers "what went into the
prompt, what was left out, and why" without ever carrying prompt content
or secrets (§10). It joins the composer's manifest (budgets, included /
discarded slots, discard reasons) back to the source slots for kind,
provenance and lore-trigger metadata, and attaches whitelisted backend
metadata.

Safety contract:
- Slot *content* is never copied into the trace -- only ids, kinds,
  token counts, statuses, reasons, triggers and provenance labels.
- Backend metadata passes a key whitelist with scalar values only, so
  credentials or provider wire objects cannot ride along.
- The serialized form is plain JSON-shaped data, stable enough to pin
  as golden fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.prompt.composer import ComposedPrompt
from runmal.prompt.slots import Slot
from runmal.tokens import TokenQuality

#: Backend metadata keys allowed into a trace. Anything else (api keys,
#: headers, URLs with credentials, provider payloads) is dropped.
BACKEND_KEYS = ("backend", "model", "profile", "provider")

LORE_KINDS = frozenset({"lore_before", "lore_after"})
MEMORY_KINDS = frozenset({"memory_nucleus", "memory_retrieved"})


@dataclass(frozen=True)
class TraceSlot:
    slot_id: str
    kind: str
    role: str
    status: str  # "included" | "discarded"
    tokens: int
    reason: str | None = None  # discard reason; None when included
    trigger: str | None = None  # lore trigger metadata, when applicable
    provenance: str = ""
    trimmed_parts: int = 0


@dataclass(frozen=True)
class TokenLedger:
    context_limit: int
    reserved_response: int
    overhead: int
    input_budget: int
    total_input_tokens: int
    remaining_input_tokens: int
    count_quality: TokenQuality


@dataclass(frozen=True)
class PromptTrace:
    ledger: TokenLedger
    backend: dict
    slots: tuple[TraceSlot, ...]

    @property
    def lore_triggers(self) -> tuple[TraceSlot, ...]:
        """Lore slots in the trace, with their trigger metadata."""
        return tuple(s for s in self.slots if s.kind in LORE_KINDS)

    @property
    def memory_slots(self) -> tuple[TraceSlot, ...]:
        """Memory slots (placeholders until Campaign IV fills them)."""
        return tuple(s for s in self.slots if s.kind in MEMORY_KINDS)


def _sanitize_backend(backend: dict | None) -> dict:
    if not backend:
        return {}
    clean: dict = {}
    for key in BACKEND_KEYS:
        value = backend.get(key)
        if isinstance(value, str) and value:
            clean[key] = value
    return clean


def build_trace(
    composed: ComposedPrompt,
    slots: list[Slot],
    backend: dict | None = None,
) -> PromptTrace:
    """Build the safe trace for a composed prompt.

    ``slots`` are the composer's inputs (joined by id for metadata);
    ``backend`` is raw backend metadata, whitelisted before inclusion.
    """
    manifest = composed.manifest
    source = {s.id: s for s in slots}

    def describe(slot_id: str, status: str, tokens: int, reason, trimmed=0):
        slot = source.get(slot_id)
        return TraceSlot(
            slot_id=slot_id,
            kind=slot.kind if slot else "",
            role=slot.role if slot else "",
            status=status,
            tokens=tokens,
            reason=reason,
            trigger=(slot.trigger or None) if slot else None,
            provenance=slot.provenance if slot else "",
            trimmed_parts=trimmed,
        )

    traced = [
        describe(u.slot_id, "included", u.tokens, None, u.trimmed_parts) for u in manifest.included
    ]
    traced += [describe(d.slot_id, "discarded", d.tokens, d.reason) for d in manifest.discarded]
    ledger = TokenLedger(
        context_limit=manifest.context_limit,
        reserved_response=manifest.reserved_response,
        overhead=manifest.overhead,
        input_budget=manifest.input_budget,
        total_input_tokens=manifest.total_input_tokens,
        remaining_input_tokens=manifest.input_budget - manifest.total_input_tokens,
        count_quality=manifest.count_quality,
    )
    return PromptTrace(ledger=ledger, backend=_sanitize_backend(backend), slots=tuple(traced))


def trace_to_dict(trace: PromptTrace) -> dict:
    """Serialize a trace to plain JSON-shaped data (golden-fixture form)."""
    ledger = trace.ledger
    return {
        "ledger": {
            "context_limit": ledger.context_limit,
            "reserved_response": ledger.reserved_response,
            "overhead": ledger.overhead,
            "input_budget": ledger.input_budget,
            "total_input_tokens": ledger.total_input_tokens,
            "remaining_input_tokens": ledger.remaining_input_tokens,
            "count_quality": ledger.count_quality.value,
        },
        "backend": dict(trace.backend),
        "slots": [
            {
                "slot_id": s.slot_id,
                "kind": s.kind,
                "role": s.role,
                "status": s.status,
                "tokens": s.tokens,
                "reason": s.reason,
                "trigger": s.trigger,
                "provenance": s.provenance,
                "trimmed_parts": s.trimmed_parts,
            }
            for s in trace.slots
        ],
        "lore_triggers": [
            {"slot_id": s.slot_id, "trigger": s.trigger, "status": s.status}
            for s in trace.lore_triggers
        ],
        "memory_slots": [
            {"slot_id": s.slot_id, "kind": s.kind, "status": s.status} for s in trace.memory_slots
        ],
    }
