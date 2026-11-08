"""Message-level provenance (P-075): which model/preset/lore
produced each message — recorded.

Roadmap line: *Message-level provenance: which model/preset/
lore produced each message — recorded (Inspector consumes;
Yggdrasil receipts are kin).*

A provenance document is ONE JSON object stored per message in
``messages.provenance_json`` (PROVISIONAL 0040), mirroring the
character provenance document (P-029, ``characters.
provenance_json``) and the chat metadata document (P-073).
The grain is the SWIPE: a message's content is its active
alternate (``content == swipes[swipe_id]``, P-065), and
alternates can have different producers, so the document holds
one production record per deck index:

    {"schema": PROVENANCE_SCHEMA, "recorded": True,
     "recorded_at": <iso>, "swipes": {"0": <record>, ...}}

Honesty law (the whole slice): a record states ONLY what the
producing road actually knew at production time. Every section
carries an explicit status; a fact the road did not hold is a
recorded GAP (``unknown`` / ``not_run`` / ``not_applicable`` /
``not_recorded``), never an invented value and never silently
absent. In particular, live generation in this tree does not
route through the prompt composer or lore activation (the
P-059/P-062/P-069 boundary), so bridge/continue generation
records lore ``not_run``; the one live road that runs lore —
groupchat deepening (P-070) — records the actual included
entries from its own lore report. Nothing here ever records
message or prompt CONTENT, secrets, or provider payloads: a
record is a receipt for production, not a copy of the text.

Builders are STRICT: an unknown origin kind, a malformed lore
row, or a non-scalar fact raises ValueError — a record that
would lie is refused at build time. Readers are TOLERANT:
:func:`parse_document` turns missing, legacy (``'{}'``),
corrupt, or foreign stored data into the explicit unknown
document, so stored data can never break a history read.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

PROVENANCE_SCHEMA = "runmal-p075-message-provenance-v1"

ORIGIN_KINDS = frozenset({
    "manual", "generated", "bridge", "bridge_generated",
    "continue", "impersonate_accepted", "group_generated",
    "group_declared", "imported", "copied", "swipe_manual",
    "generation_session", "unknown",
})
MODEL_STATUSES = frozenset({"recorded", "unknown", "not_applicable"})
PRESET_STATUSES = frozenset({"recorded", "unknown", "not_applicable"})
LORE_STATUSES = frozenset({
    "included", "ran_none_included", "not_run", "unknown",
    "not_applicable",
})
AMENDMENT_KINDS = frozenset({"edit", "continuation", "swipe_import"})

_LORE_ENTRY_KEYS = frozenset({
    "entry_id", "lorebook_id", "scope", "via", "trigger", "roll",
})
_ROLL_KEYS = frozenset({
    "entry_id", "probability", "roll", "passed", "seed",
    "seeded", "context", "algorithm",
})
_GENERATION_KEYS = frozenset({
    "request_id", "fingerprint", "mode", "finish_reason",
})

__all__ = [
    "PROVENANCE_SCHEMA", "ORIGIN_KINDS", "MODEL_STATUSES",
    "PRESET_STATUSES", "LORE_STATUSES", "AMENDMENT_KINDS",
    "model_section", "preset_section", "lore_section",
    "lore_from_report", "lore_from_inspection",
    "build_record", "unknown_record", "build_document",
    "dump_document", "parse_document", "parse_provenance",
    "active_view", "full_view", "with_record_for_swipe",
    "with_amendment", "without_swipe", "active_record", "document_for_copy",
    "summarise_provenance", "backend_model_fields",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _scalar(value) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _clean_str(value, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{what} must be a string or None")
    return value or None

# -- Section builders (strict) ------------------------------------------


def model_section(*, status=None, backend_key=None, model_id=None,
                  backend_profile_id=None, backend_profile_name=None,
                  model_profile=None) -> dict:
    """The model section. Status is inferred as ``recorded``
    when a backend or model fact is present; an explicit status
    must agree with the facts it labels."""
    backend_key = _clean_str(backend_key, "backend_key")
    model_id = _clean_str(model_id, "model_id")
    backend_profile_id = _clean_str(
        backend_profile_id, "backend_profile_id")
    backend_profile_name = _clean_str(
        backend_profile_name, "backend_profile_name")
    model_profile = _clean_str(model_profile, "model_profile")
    if status is None:
        status = "recorded" if (backend_key or model_id) else "unknown"
    if status not in MODEL_STATUSES:
        raise ValueError(f"unknown model status: {status!r}")
    if status == "recorded" and not (backend_key or model_id):
        raise ValueError("model status recorded needs a backend or model fact")
    if status != "recorded" and (backend_key or model_id):
        raise ValueError("model facts present but status is not recorded")
    return {
        "status": status, "backend_key": backend_key,
        "model_id": model_id,
        "backend_profile_id": backend_profile_id,
        "backend_profile_name": backend_profile_name,
        "model_profile": model_profile,
    }


def preset_section(*, status=None, preset_id=None, name=None,
                   params=None) -> dict:
    """The preset section: id + name + the sampler params the
    preset row carried at production time (a receipt fact;
    params are the preset's own non-secret configuration)."""
    preset_id = _clean_str(preset_id, "preset_id")
    name = _clean_str(name, "preset name")
    if params is not None:
        if not isinstance(params, dict):
            raise ValueError("preset params must be an object or None")
        try:
            json.dumps(params)
        except (TypeError, ValueError) as exc:
            raise ValueError("preset params are not JSON-serializable") from exc
        params = copy.deepcopy(params)
    if status is None:
        status = "recorded" if preset_id else "unknown"
    if status not in PRESET_STATUSES:
        raise ValueError(f"unknown preset status: {status!r}")
    if status == "recorded" and not preset_id:
        raise ValueError("preset status recorded needs a preset_id")
    if status != "recorded" and preset_id:
        raise ValueError("preset_id present but status is not recorded")
    return {"status": status, "preset_id": preset_id,
            "name": name, "params": params}


def _lore_entry(row) -> dict:
    if not isinstance(row, dict):
        raise ValueError("lore entry must be an object")
    extra = set(row) - _LORE_ENTRY_KEYS
    if extra:
        raise ValueError(f"lore entry has unknown keys: {sorted(extra)}")
    entry_id = row.get("entry_id")
    if not isinstance(entry_id, str) or not entry_id:
        raise ValueError("lore entry needs a non-empty entry_id")
    out = {
        "entry_id": entry_id,
        "lorebook_id": _clean_str(row.get("lorebook_id"), "lorebook_id"),
        "scope": _clean_str(row.get("scope"), "lore scope"),
        "via": _clean_str(row.get("via"), "lore via"),
        "trigger": _clean_str(row.get("trigger"), "lore trigger"),
        "roll": None,
    }
    roll = row.get("roll")
    if roll is not None:
        if not isinstance(roll, dict):
            raise ValueError("lore roll must be an object or None")
        extra_roll = set(roll) - _ROLL_KEYS
        if extra_roll:
            raise ValueError(
                f"lore roll has unknown keys: {sorted(extra_roll)}")
        for key, value in roll.items():
            if not _scalar(value):
                raise ValueError(f"lore roll {key} must be a scalar")
        out["roll"] = copy.deepcopy(roll)
    return out


def lore_section(*, status="unknown", entries=None, reason=None) -> dict:
    """The lore section. ``included`` requires at least one
    entry; ``ran_none_included`` is the honest record of a lore
    pass that ran and included nothing; ``not_run`` says the
    producing road never ran lore activation."""
    if status not in LORE_STATUSES:
        raise ValueError(f"unknown lore status: {status!r}")
    rows = [_lore_entry(row) for row in (entries or [])]
    if status == "included" and not rows:
        raise ValueError("lore status included needs at least one entry")
    if status != "included" and rows:
        raise ValueError("lore entries present but status is not included")
    return {"status": status, "entries": rows,
            "reason": _clean_str(reason, "lore reason")}


def lore_from_report(report) -> dict:
    """A lore section from a group-lore report (P-070): rows of
    {scope, lorebook_id, entry_id} for the entries the layered
    preview actually included in one generated turn."""
    rows = []
    for row in report or []:
        if not isinstance(row, dict) or not row.get("entry_id"):
            continue
        rows.append({
            "entry_id": row["entry_id"],
            "lorebook_id": row.get("lorebook_id"),
            "scope": row.get("scope"),
            "via": None, "trigger": None, "roll": None,
        })
    if rows:
        return lore_section(status="included", entries=rows)
    return lore_section(
        status="ran_none_included",
        reason="lore activation ran; no entry was included")


def lore_from_inspection(payload) -> dict:
    """A lore section from a P-043 activation-inspection payload:
    the entries whose explanation status is ``included``, with
    their recorded probability roll when the payload carries
    one (P-036). For a production road that composes through
    the inspector; the live roads in this tree do not, and say
    ``not_run`` instead of calling this."""
    rows = []
    for book in (payload or {}).get("lorebook_inspections", []) or []:
        for expl in book.get("entries", []) or []:
            if expl.get("status") != "included":
                continue
            prob = expl.get("probability") or {}
            roll = prob.get("roll") if isinstance(prob, dict) else None
            rows.append({
                "entry_id": expl.get("entry_id"),
                "lorebook_id": book.get("lorebook_id"),
                "scope": expl.get("scope"),
                "via": expl.get("via"),
                "trigger": None,
                "roll": roll if isinstance(roll, dict) else None,
            })
    if rows:
        return lore_section(status="included", entries=rows)
    return lore_section(
        status="ran_none_included",
        reason="activation inspection ran; no entry was included")


def _generation_section(value) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("generation must be an object or None")
    extra = set(value) - _GENERATION_KEYS
    if extra:
        raise ValueError(f"generation has unknown keys: {sorted(extra)}")
    out = {key: _clean_str(value.get(key), f"generation {key}")
           for key in sorted(_GENERATION_KEYS)}
    return out if any(out.values()) else None


def _speaker_section(value) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("speaker must be an object or None")
    out = {
        "speaker_id": _clean_str(value.get("speaker_id"), "speaker_id"),
        "speaker_name": _clean_str(
            value.get("speaker_name"), "speaker_name"),
    }
    return out if any(out.values()) else None


def _origin_section(kind, facts) -> dict:
    if kind not in ORIGIN_KINDS:
        raise ValueError(f"unknown provenance origin kind: {kind!r}")
    out = {"kind": kind}
    for key, value in (facts or {}).items():
        if key == "kind":
            raise ValueError("origin facts must not repeat kind")
        if key == "source_provenance":
            if not isinstance(value, dict):
                raise ValueError("source_provenance must be a record object")
            out[key] = copy.deepcopy(value)
        elif _scalar(value):
            out[key] = value
        else:
            raise ValueError(f"origin fact {key!r} must be a scalar")
    return out


def build_record(*, origin_kind, origin=None, model=None, preset=None,
                 lore=None, generation=None, speaker=None,
                 amendments=None) -> dict:
    """One swipe's production record (STRICT). Sections default
    to their gap forms: model/preset ``unknown``, lore
    ``unknown``. A caller that knows a section passes the
    section built by the helpers above."""
    record = {
        "origin": _origin_section(origin_kind, origin),
        "model": model if model is not None else model_section(),
        "preset": preset if preset is not None else preset_section(),
        "lore": lore if lore is not None else lore_section(),
        "generation": _generation_section(generation),
        "speaker": _speaker_section(speaker),
        "amendments": [],
    }
    for amendment in amendments or []:
        record["amendments"].append(_amendment(amendment))
    return record


def _amendment(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("amendment must be an object")
    kind = value.get("kind")
    if kind not in AMENDMENT_KINDS:
        raise ValueError(f"unknown amendment kind: {kind!r}")
    out = {"kind": kind}
    for key, item in value.items():
        if key == "kind":
            continue
        if not _scalar(item):
            raise ValueError(f"amendment fact {key!r} must be a scalar")
        out[key] = item
    out.setdefault("at", _now_iso())
    return out


def unknown_record() -> dict:
    """The explicit gap record: nothing about production is
    known, and the record says so in every section."""
    return build_record(origin_kind="unknown")


def build_document(record, *, swipe_index=0, recorded_at=None) -> dict:
    if isinstance(swipe_index, bool) or not isinstance(swipe_index, int):
        raise ValueError("swipe_index must be an integer")
    if swipe_index < 0:
        raise ValueError("swipe_index must be >= 0")
    return {
        "schema": PROVENANCE_SCHEMA,
        "recorded": True,
        "recorded_at": recorded_at or _now_iso(),
        "swipes": {str(swipe_index): copy.deepcopy(record)},
    }


def dump_document(document) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True)

# -- Reading (tolerant) ---------------------------------------------------


def _tolerant_record(raw) -> dict:
    """Normalise one stored record for reading: recognised
    facts survive verbatim; anything missing or malformed
    falls back to that section's gap form. Never raises."""
    if not isinstance(raw, dict):
        return unknown_record()
    record = unknown_record()
    origin = raw.get("origin")
    if isinstance(origin, dict) and origin.get("kind") in ORIGIN_KINDS:
        kept = {"kind": origin["kind"]}
        for key, value in origin.items():
            if key == "kind":
                continue
            if key == "source_provenance" and isinstance(value, dict):
                kept[key] = _tolerant_record(value)
            elif _scalar(value):
                kept[key] = value
        record["origin"] = kept
    for section, statuses, builder in (
        ("model", MODEL_STATUSES, model_section),
        ("preset", PRESET_STATUSES, preset_section),
        ("lore", LORE_STATUSES, lore_section),
    ):
        raw_section = raw.get(section)
        if not isinstance(raw_section, dict):
            continue
        try:
            if section == "lore":
                record[section] = builder(
                    status=raw_section.get("status", "unknown"),
                    entries=raw_section.get("entries") or [],
                    reason=raw_section.get("reason"))
            else:
                fields = {k: v for k, v in raw_section.items()
                          if k != "status"}
                record[section] = builder(
                    status=raw_section.get("status"), **fields)
        except (ValueError, TypeError):
            continue  # keep the gap form for this section
    try:
        record["generation"] = _generation_section(raw.get("generation"))
    except ValueError:
        record["generation"] = None
    try:
        record["speaker"] = _speaker_section(raw.get("speaker"))
    except ValueError:
        record["speaker"] = None
    amendments = raw.get("amendments")
    if isinstance(amendments, list):
        kept_amendments = []
        for item in amendments:
            try:
                kept_amendments.append(_amendment(item))
            except ValueError:
                continue
        record["amendments"] = kept_amendments
    return record


def parse_document(raw) -> dict:
    """Parse stored provenance (TOLERANT). Accepts the stored
    JSON text, a dict, or None. Missing/legacy/corrupt data
    reads as the unrecorded document: ``recorded`` False and
    no swipe records — readers resolve every swipe against
    :func:`unknown_record`, so gaps surface as gaps."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, dict) or raw.get("schema") != PROVENANCE_SCHEMA:
        return {"schema": PROVENANCE_SCHEMA, "recorded": False,
                "recorded_at": None, "swipes": {}}
    swipes = {}
    raw_swipes = raw.get("swipes")
    if isinstance(raw_swipes, dict):
        for key, value in raw_swipes.items():
            if str(key).isdigit():
                swipes[str(int(key))] = _tolerant_record(value)
    return {
        "schema": PROVENANCE_SCHEMA,
        "recorded": bool(raw.get("recorded")) and bool(swipes),
        "recorded_at": raw.get("recorded_at")
        if isinstance(raw.get("recorded_at"), str) else None,
        "swipes": swipes,
    }


def parse_provenance(source) -> dict:
    """The document for a Message row, a raw string, or a dict."""
    if source is None or isinstance(source, (str, dict)):
        return parse_document(source)
    return parse_document(getattr(source, "provenance_json", None))


def active_view(source, swipe_id=0) -> dict:
    """The Inspector-shaped view of ONE swipe's record: the
    document's facts for the swipe at ``swipe_id`` (the active
    alternate by default at the service layer), with the gap
    record substituted — and ``recorded`` False — when that
    swipe has no record. Selecting a swipe changes only which
    record this view resolves; storage is never rewritten."""
    document = parse_provenance(source)
    record = document["swipes"].get(str(swipe_id))
    recorded = record is not None and document["recorded"]
    if record is None:
        record = unknown_record()
    view = {
        "schema": PROVENANCE_SCHEMA,
        "provenance_status": "recorded" if recorded else "not_recorded",
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
    document = parse_provenance(source)
    return {
        "schema": PROVENANCE_SCHEMA,
        "provenance_status": "recorded" if document["recorded"]
        else "not_recorded",
        "recorded": document["recorded"],
        "recorded_at": document["recorded_at"],
        "swipes": copy.deepcopy(document["swipes"]),
    }


# -- Document mutation helpers (pure) -------------------------------------


def with_record_for_swipe(document, swipe_index, record) -> dict:
    out = parse_document(document) if not isinstance(document, dict) \
        or document.get("swipes") is None else copy.deepcopy(document)
    out["schema"] = PROVENANCE_SCHEMA
    out.setdefault("swipes", {})
    out["swipes"][str(swipe_index)] = copy.deepcopy(record)
    out["recorded"] = True
    out["recorded_at"] = out.get("recorded_at") or _now_iso()
    return out


def with_amendment(document, swipe_index, amendment) -> dict:
    """Append an amendment to one swipe's record, starting
    from the gap record when that swipe has none — an edit or
    continuation of a legacy message is a fact about NOW, and
    recording it must not invent the original production."""
    doc = parse_provenance(document)
    key = str(swipe_index)
    record = doc["swipes"].get(key) or unknown_record()
    record = copy.deepcopy(record)
    record["amendments"].append(_amendment(amendment))
    doc["swipes"][key] = record
    doc["recorded"] = True
    doc["recorded_at"] = doc["recorded_at"] or _now_iso()
    return doc


def without_swipe(document, index) -> dict:
    """Drop one deck index's record and renumber higher ones
    down — the map always keys the CURRENT deck, exactly as
    the deck's own texts shift on a swipe deletion."""
    doc = parse_provenance(document)
    swipes = {}
    for key, record in doc["swipes"].items():
        position = int(key)
        if position == index:
            continue
        swipes[str(position - 1 if position > index else position)] = record
    doc["swipes"] = swipes
    doc["recorded"] = bool(swipes) and doc["recorded"]
    return doc


def active_record(source) -> dict:
    """The clean production record of a message's ACTIVE
    swipe (gap record when unrecorded)."""
    document = parse_provenance(source)
    swipe_id = getattr(source, "swipe_id", 0) or 0
    record = document["swipes"].get(str(swipe_id))
    return copy.deepcopy(record) if record is not None else unknown_record()


def document_for_copy(source, *, source_chat_id, source_message_id,
                      source_content_sha256=None) -> dict:
    """The document for a COPIED message (branch / copy-to-
    branch). Per source swipe: origin ``copied`` carrying the
    source ids (and the source text's sha256 when the caller
    computed it — a hash, never the text), with the source
    record nested as ``source_provenance``; the model/preset/
    lore/generation sections are the SOURCE record's, because
    they describe the text's production, which copying does
    not change. A source with no record copies as origin
    ``copied`` over gap sections — the copy is a fact, the
    original production stays unknown."""
    source_doc = parse_provenance(source)
    swipes = {}
    keys = sorted(source_doc["swipes"], key=int) or ["0"]
    for key in keys:
        source_record = source_doc["swipes"].get(key) or unknown_record()
        origin = {
            "source_chat_id": source_chat_id,
            "source_message_id": source_message_id,
            "source_swipe_id": int(key),
            "source_provenance": copy.deepcopy(source_record),
        }
        if source_content_sha256:
            origin["source_content_sha256"] = source_content_sha256
        swipes[key] = {
            "origin": _origin_section("copied", origin),
            "model": copy.deepcopy(source_record["model"]),
            "preset": copy.deepcopy(source_record["preset"]),
            "lore": copy.deepcopy(source_record["lore"]),
            "generation": copy.deepcopy(source_record["generation"]),
            "speaker": copy.deepcopy(source_record["speaker"]),
            "amendments": copy.deepcopy(source_record["amendments"]),
        }
    return {"schema": PROVENANCE_SCHEMA, "recorded": True,
            "recorded_at": _now_iso(), "swipes": swipes}


def summarise_provenance(views) -> dict:
    """Aggregate ACTIVE-swipe views (from :func:`active_view`)
    into a chat-level summary. Pure. Counts only — no content,
    no facts beyond the records' own statuses."""
    views = list(views or [])
    by_origin: dict = {}
    by_model_status: dict = {}
    recorded = 0
    with_lore = 0
    for view in views:
        if view.get("recorded"):
            recorded += 1
        kind = (view.get("origin") or {}).get("kind", "unknown")
        by_origin[kind] = by_origin.get(kind, 0) + 1
        status = (view.get("model") or {}).get("status", "unknown")
        by_model_status[status] = by_model_status.get(status, 0) + 1
        if (view.get("lore") or {}).get("status") == "included":
            with_lore += 1
    return {
        "total": len(views), "recorded": recorded,
        "not_recorded": len(views) - recorded,
        "messages_with_unknown_model": by_model_status.get("unknown", 0),
        "by_origin": by_origin, "by_model_status": by_model_status,
        "with_lore_included": with_lore,
    }


def backend_model_fields(backend) -> tuple[str | None, str | None]:
    """(backend_key, model_id) from a backend object — the
    model facts a generation road actually holds. A backend
    without a declared default model yields model_id None:
    a gap, never a guess from configuration."""
    if backend is None:
        return None, None
    backend_key = getattr(backend, "backend_key", None)
    model = getattr(backend, "default_model", None)
    model_id = getattr(model, "model_id", None) if model else None
    return (backend_key if isinstance(backend_key, str) else None,
            model_id if isinstance(model_id, str) else None)
