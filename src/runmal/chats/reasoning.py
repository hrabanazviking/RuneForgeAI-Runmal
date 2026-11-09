"""Message-level reasoning record (P-205): the model's own
emitted thinking for each message -- captured, streamed, stored.

P-203's design named the prerequisite for Part XIII's Assistant
View verbatim: it "becomes buildable only after a slice gives
backends a reasoning-content record". This module is the record
half of that slice (the capture half is the ReasoningDelta
backend event; the stream half is the generation service's
{"type": "reasoning"} bridge dict).

A reasoning document is ONE JSON object stored per message in
``messages.reasoning_json`` (PROVISIONAL 0042), mirroring the
provenance document (P-075, ``messages.provenance_json``). The
grain is the SWIPE: alternates of one message are produced by
different generations and think differently:

    {"schema": REASONING_SCHEMA, "recorded": True,
     "recorded_at": <iso>, "swipes": {"0": <record>, ...}}

A record is ``{"status": ..., "text": ...}`` with ``text``
present ONLY when the status is ``recorded``. The status
vocabulary is closed, in the P-075 honesty idiom:

- ``recorded``: this swipe's generation produced thinking and
  the producing road captured it; ``text`` is the verbatim
  concatenation of that generation's ReasoningDelta texts, in
  arrival order.
- ``not_present``: the producing road DID capture (it ran the
  P-205 seam) and the generation produced no thinking -- a
  positive fact about that generation.
- ``not_recorded``: the road never captured (legacy rows,
  manual / imported messages, producers not yet wired).
- ``unknown``: stored data was missing, corrupt or foreign;
  readers land here, never on an exception.

CONTENT LAW, stated plainly because it differs from
provenance: a provenance record never records message or
prompt CONTENT, and reasoning text could not ride it without
breaking that module's founding law. This module's whole
purpose is one content-class fact -- the model's OWN emitted
thinking. It records never prompt text, never message answer
text, never secrets or provider payloads beyond the reasoning
field itself.

Builders are STRICT: non-string text, ``recorded`` without
text, a status outside the vocabulary, or a ``text`` key on a
non-recorded record all raise ValueError -- a record that
would lie is refused. Readers are TOLERANT:
:func:`parse_document` turns missing, legacy (``'{}'``),
corrupt or foreign stored data into the explicit not_recorded
document, so stored data can never break a history read.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

REASONING_SCHEMA = "runmal-p205-message-reasoning-v1"

STATUSES = frozenset({"recorded", "not_present", "not_recorded", "unknown"})

__all__ = [
    "REASONING_SCHEMA", "STATUSES",
    "build_record", "not_recorded_record", "unknown_record",
    "build_document", "dump_document", "parse_document",
    "parse_reasoning", "active_view", "full_view",
    "with_record_for_swipe", "without_swipe", "document_for_copy",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# -- Builders (strict) ----------------------------------------------------


def build_record(*, status, text=None) -> dict:
    """One swipe's reasoning record (STRICT). ``text`` is
    required (a string) exactly when ``status`` is
    ``recorded``, and refused for every other status."""
    if status not in STATUSES:
        raise ValueError(f"unknown reasoning status: {status!r}")
    if status == "recorded":
        if not isinstance(text, str):
            raise ValueError("recorded reasoning needs string text")
        return {"status": "recorded", "text": text}
    if text is not None:
        raise ValueError("reasoning text is only allowed on a recorded record")
    return {"status": status}


def _validate_record(record) -> dict:
    """STRICT check of a record dict (used by the document
    builders so a hand-assembled record cannot smuggle a lie
    past build_record)."""
    if not isinstance(record, dict):
        raise ValueError("reasoning record must be an object")
    extra = set(record) - {"status", "text"}
    if extra:
        raise ValueError(f"reasoning record has unknown keys: {sorted(extra)}")
    status = record.get("status")
    if status not in STATUSES:
        raise ValueError(f"unknown reasoning status: {status!r}")
    if status == "recorded":
        if not isinstance(record.get("text"), str):
            raise ValueError("recorded reasoning needs string text")
    elif "text" in record:
        raise ValueError("reasoning text is only allowed on a recorded record")
    return copy.deepcopy(record)


def not_recorded_record() -> dict:
    """The record for a swipe whose road never captured."""
    return {"status": "not_recorded"}


def unknown_record() -> dict:
    """The record readers substitute for stored data that was
    present but missing, corrupt or foreign."""
    return {"status": "unknown"}


def build_document(record, *, swipe_index=0, recorded_at=None) -> dict:
    if isinstance(swipe_index, bool) or not isinstance(swipe_index, int):
        raise ValueError("swipe_index must be an integer")
    if swipe_index < 0:
        raise ValueError("swipe_index must be >= 0")
    return {
        "schema": REASONING_SCHEMA,
        "recorded": True,
        "recorded_at": recorded_at or _now_iso(),
        "swipes": {str(swipe_index): _validate_record(record)},
    }


def dump_document(document) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True)


# -- Reading (tolerant) ---------------------------------------------------


def _tolerant_record(raw) -> dict:
    """Normalise one stored record for reading: a well-formed
    record survives verbatim; anything missing or malformed
    reads as ``unknown``. Never raises."""
    if not isinstance(raw, dict):
        return unknown_record()
    status = raw.get("status")
    if status not in STATUSES:
        return unknown_record()
    if status == "recorded":
        text = raw.get("text")
        if not isinstance(text, str):
            return unknown_record()
        return {"status": "recorded", "text": text}
    if "text" in raw:
        return unknown_record()
    return {"status": status}


def parse_document(raw) -> dict:
    """Parse stored reasoning (TOLERANT). Accepts the stored
    JSON text, a dict, or None. Missing/legacy/corrupt/foreign
    data reads as the unrecorded document: ``recorded`` False
    and no swipe records -- readers resolve every swipe against
    the explicit not_recorded record, so gaps surface as gaps."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, dict) or raw.get("schema") != REASONING_SCHEMA:
        return {"schema": REASONING_SCHEMA, "recorded": False,
                "recorded_at": None, "swipes": {}}
    swipes = {}
    raw_swipes = raw.get("swipes")
    if isinstance(raw_swipes, dict):
        for key, value in raw_swipes.items():
            if str(key).isdigit():
                swipes[str(int(key))] = _tolerant_record(value)
    return {
        "schema": REASONING_SCHEMA,
        "recorded": bool(raw.get("recorded")) and bool(swipes),
        "recorded_at": raw.get("recorded_at")
        if isinstance(raw.get("recorded_at"), str) else None,
        "swipes": swipes,
    }


def parse_reasoning(source) -> dict:
    """The document for a Message row, a raw string, or a dict."""
    if source is None or isinstance(source, (str, dict)):
        return parse_document(source)
    return parse_document(getattr(source, "reasoning_json", None))


def active_view(source, swipe_id=0) -> dict:
    """The view of ONE swipe's reasoning record: the document's
    record for the swipe at ``swipe_id`` (the active alternate
    by default at the service layer), with the explicit
    not_recorded record substituted when that swipe has none.
    Selecting a swipe changes only which record this view
    resolves; storage is never rewritten."""
    document = parse_reasoning(source)
    record = document["swipes"].get(str(swipe_id))
    recorded = record is not None and document["recorded"]
    if record is None:
        record = not_recorded_record()
    view = {
        "schema": REASONING_SCHEMA,
        "reasoning_status": record["status"],
        "recorded": recorded,
        "recorded_at": document["recorded_at"] if recorded else None,
        "swipe_id": swipe_id,
        "swipes_recorded": sorted(
            int(key) for key in document["swipes"]),
    }
    view.update(copy.deepcopy(record))
    return view


def full_view(source) -> dict:
    """The whole stored document, tolerantly normalised: every
    recorded swipe's record, for the per-message endpoint."""
    document = parse_reasoning(source)
    return {
        "schema": REASONING_SCHEMA,
        "reasoning_status": "recorded" if document["recorded"]
        else "not_recorded",
        "recorded": document["recorded"],
        "recorded_at": document["recorded_at"],
        "swipes": copy.deepcopy(document["swipes"]),
    }


# -- Document mutation helpers (pure) -------------------------------------


def with_record_for_swipe(document, swipe_index, record) -> dict:
    out = parse_document(document) if not isinstance(document, dict) \
        or document.get("swipes") is None else copy.deepcopy(document)
    out["schema"] = REASONING_SCHEMA
    out.setdefault("swipes", {})
    out["swipes"][str(swipe_index)] = _validate_record(record)
    out["recorded"] = True
    out["recorded_at"] = out.get("recorded_at") or _now_iso()
    return out


def without_swipe(document, index) -> dict:
    """Drop one deck index's record and renumber higher ones
    down -- the map always keys the CURRENT deck, exactly as
    the deck's own texts shift on a swipe deletion."""
    doc = parse_reasoning(document)
    swipes = {}
    for key, record in doc["swipes"].items():
        position = int(key)
        if position == index:
            continue
        swipes[str(position - 1 if position > index else position)] = record
    doc["swipes"] = swipes
    doc["recorded"] = bool(swipes) and doc["recorded"]
    return doc


def document_for_copy(source) -> dict:
    """The document for a COPIED message (branch / copy-to-
    branch). The source swipes' reasoning records carry over
    verbatim: they describe the thinking that produced the
    copied texts, which copying does not change. A source with
    no record copies as an explicit not_recorded record at
    swipe 0 -- the copy is a fact, the original production
    stays unrecorded."""
    source_doc = parse_reasoning(source)
    swipes = {}
    keys = sorted(source_doc["swipes"], key=int) or ["0"]
    for key in keys:
        record = source_doc["swipes"].get(key)
        swipes[key] = copy.deepcopy(record) if record is not None \
            else not_recorded_record()
    return {"schema": REASONING_SCHEMA, "recorded": True,
            "recorded_at": _now_iso(), "swipes": swipes}
