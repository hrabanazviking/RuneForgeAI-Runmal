"""Voice repeat-request signal (P-108, Part VII - DERIVED scope, VX-11).

The Voxta census row VX-11: mishearing is handled, not
hidden - characters can detect misheard words and ask the
user to repeat. Part VII has built the row in halves, each
honest about what it is: P-105 detection (the truth layer:
per-word confidence persisted, needs_repeat as data),
P-106 the receipt (the mark in projected provenance and
status), P-107 the rendering (confidence markings in the
founding web thread). The remaining named half - "ask the
user to repeat" - splits in two:

- The CHARACTER half (a character speaks the ask inside
  the dialogue) stays open: the live responder is P-102's
  honest-unavailable seam, and fabricating the ask would
  cross it. This module does not fabricate dialogue, does
  not create a chat message, and never calls a responder.
- The HOST half (something outside the dialogue learns a
  repeat is needed and decides what to do) is what lands
  here, as a SIGNAL: pending repeat requests derived from
  P-105's truth, plus a durable record of which requests
  a host has already handled, so two hosts sharing one
  install do not ask twice.

Laws held (see docs/VOICE_REPEAT_REQUESTS_2026-11-08.md):

- ONE TRUTH SOURCE: every fact here is derived from
  runmal.voice.mishearing.turn_mishearing - the threshold,
  the bands, the suggestion view. Nothing is recomputed
  and no second threshold exists, so the signal can never
  disagree with P-105's view, P-106's receipt or P-107's
  rendering.
- NO EVIDENCE IS NOT A REQUEST: a turn with no recorded
  word evidence has needs_repeat False under P-105's law,
  so it never appears here - the signal never invents
  doubt.
- ACKNOWLEDGEMENT IS HANDLING, NOT TRUTH: the store below
  records that a host acted (and when, and an optional
  host note). Detection is recomputed from the evidence
  on every read; acknowledging never changes it, and
  clearing an acknowledgement returns the request to
  pending with the truth untouched.
- CONTENT LAW UNCHANGED: the stored transcript is never
  rewritten; the suggested text rides as a view only.

P-115 adds the cross-session DIGEST over this signal:
the roll-up a host polls for all of its sessions at once,
with wall-clock aging derived only from the stamps this
module and the session record already persist (turn
recorded_at, acknowledgement acknowledged_at) against an
injected now - plain arithmetic seconds, no age buckets
and no staleness threshold invented.

Storage is one versioned JSON document in the voice house
pattern (the P-105 lexicon stance); NO migration - the
head stays 0041.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from runmal.voice.mishearing import (
    LOW_CONFIDENCE_THRESHOLD,
    turn_mishearing,
)

ACK_VERSION = 1
ACK_FILENAME = "voice_repeat_acknowledgements.json"

STATE_PENDING = "pending"
STATE_ACKNOWLEDGED = "acknowledged"


def acks_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / ACK_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ views


def turn_repeat_request(turn, pairs=None, ack=None) -> dict | None:
    """One turn's repeat request, or None when it is not one.

    A turn is a request exactly when P-105's own view says
    needs_repeat. ``ack`` is the acknowledgement record for
    this turn ({"acknowledged_at": ..., "note": ...}) or
    None; it decides the state field and nothing else.
    """
    view = turn_mishearing(turn, pairs or {})
    if not view["needs_repeat"]:
        return None
    handled = bool(ack)
    return {
        "turn_no": view["turn_no"],
        "stt_backend": view["stt_backend"],
        "state": STATE_ACKNOWLEDGED if handled else STATE_PENDING,
        "low_confidence_words": view["low_confidence_words"],
        "low_confidence_count": view["low_confidence_count"],
        "word_count": view["word_count"],
        "min_probability": view["min_probability"],
        "mean_probability": view["mean_probability"],
        "transcript_text": view["transcript_text"],
        "suggested_text": view["suggested_text"],
        "replacements_applied": view["replacements_applied"],
        "recorded_at": str(getattr(turn, "recorded_at", "") or ""),
        "acknowledged_at": (ack or {}).get("acknowledged_at", ""),
        "acknowledged_note": (ack or {}).get("note", ""),
    }


def session_repeat_requests(session, pairs=None, store=None) -> dict:
    """One session's repeat-request signal, as data (pure
    apart from reading ``store``'s in-memory records).

    The signal a host polls: has_pending / pending_count
    say whether anything still needs a repeat; requests
    lists every request in turn order, pending and
    acknowledged alike - the acknowledged ones are the
    record that a host already acted, which is the point.
    """
    acks = store.acks_for(session.session_id) if store is not None else {}
    requests = []
    for turn in session.turns:
        request = turn_repeat_request(
            turn, pairs, acks.get(int(turn.turn_no)))
        if request is not None:
            requests.append(request)
    pending = [r for r in requests if r["state"] == STATE_PENDING]
    return {
        "session_id": session.session_id,
        "chat_id": session.chat_id,
        "threshold": LOW_CONFIDENCE_THRESHOLD,
        "has_pending": bool(pending),
        "pending_count": len(pending),
        "acknowledged_count": len(requests) - len(pending),
        "pending_turns": [r["turn_no"] for r in pending],
        "requests": requests,
    }


# ------------------------------------------------------------ store


class AcknowledgementStore:
    """The host handling record: a versioned JSON document.

    Install-wide, like the P-105 lexicon (stated plainly -
    not per-host): two hosts sharing one install share one
    handling record, which is precisely the do-not-ask-
    twice protection. Load is tolerant, the voice house
    pattern: a missing file is an empty record; a corrupt
    document reads as empty; a malformed entry is skipped -
    the store never bricks the voice surface.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or acks_path()
        # session_id -> {turn_no (int): {"acknowledged_at", "note"}}
        self._acks: dict[str, dict[int, dict]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            doc = json.loads(self.path.read_text())
            sessions = (
                doc.get("acknowledgements") if isinstance(doc, dict)
                else None)
            if not isinstance(sessions, dict):
                return
            for session_id, turns in sessions.items():
                if not isinstance(turns, dict):
                    continue
                loaded: dict[int, dict] = {}
                for raw_no, record in turns.items():
                    if not isinstance(record, dict):
                        continue
                    try:
                        turn_no = int(raw_no)
                    except (TypeError, ValueError):
                        continue
                    loaded[turn_no] = {
                        "acknowledged_at": str(
                            record.get("acknowledged_at", "") or ""),
                        "note": str(record.get("note", "") or ""),
                    }
                if loaded:
                    self._acks[str(session_id)] = loaded
        except (ValueError, TypeError, OSError):
            self._acks = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "version": ACK_VERSION,
            "acknowledgements": {
                session_id: {
                    str(turn_no): self._acks[session_id][turn_no]
                    for turn_no in sorted(self._acks[session_id])
                }
                for session_id in sorted(self._acks)
                if self._acks[session_id]
            },
        }
        self.path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    def acks_for(self, session_id: str) -> dict[int, dict]:
        """This session's records, keyed by turn number."""
        return {
            turn_no: dict(record)
            for turn_no, record in self._acks.get(session_id, {}).items()
        }

    def get(self, session_id: str, turn_no: int) -> dict | None:
        record = self._acks.get(session_id, {}).get(int(turn_no))
        return dict(record) if record is not None else None

    def acknowledge(
        self, session_id: str, turn_no: int,
        note: str = "", *, at: str = "",
    ) -> dict:
        """Record that a host handled one request.

        Idempotent - first acknowledgement wins: when a
        record already exists it is returned unchanged, so
        the receipt names when a host FIRST acted and a
        second host's call changes nothing (and never
        overwrites the first host's note).
        """
        existing = self.get(session_id, turn_no)
        if existing is not None:
            return existing
        record = {
            "acknowledged_at": at or _now_iso(),
            "note": str(note or ""),
        }
        self._acks.setdefault(session_id, {})[int(turn_no)] = record
        self.save()
        return dict(record)

    def clear(self, session_id: str, turn_no: int) -> bool:
        """Remove one record (housekeeping: absence is not
        an error). Returns whether a record existed. The
        request itself, if its evidence still says so,
        returns to pending - handling removed, truth kept."""
        turns = self._acks.get(session_id)
        if not turns or int(turn_no) not in turns:
            return False
        del turns[int(turn_no)]
        if not turns:
            del self._acks[session_id]
        self.save()
        return True

    def session_ids(self) -> list[str]:
        """Session ids that carry at least one record, sorted."""
        return sorted(sid for sid, turns in self._acks.items() if turns)

    def record_count(self) -> int:
        """Total acknowledgement records in the store."""
        return sum(len(turns) for turns in self._acks.values())

    def prune_orphans(self, live_session_ids) -> dict:
        """Remove every record naming a session that is not live
        (P-111 housekeeping: the inert-record cleanup).

        A record is inert exactly when its session id is not in
        ``live_session_ids`` - the session was deleted (its chat's
        sessions were dropped) and the record drives nothing: no
        session view can ever show it, and it can never return a
        request to pending. Live sessions' records are never
        touched, order and content alike. Saves only when
        something was actually removed, so a no-op prune leaves
        the document byte-identical. Returns the removed session
        ids (sorted) and the removed record count.
        """
        live = {str(sid) for sid in live_session_ids}
        removed_sessions = sorted(
            sid for sid in self.session_ids() if sid not in live)
        removed_records = sum(
            len(self._acks[sid]) for sid in removed_sessions)
        for sid in removed_sessions:
            del self._acks[sid]
        if removed_sessions:
            self.save()
        return {
            "removed_sessions": removed_sessions,
            "removed_records": removed_records,
        }


# ------------------------------------------------------- housekeeping


def housekeeping_view(store, live_session_ids) -> dict:
    """The acknowledgement store's housekeeping truth, as data.

    Splits the store's records into live (their session still
    exists in the session store) and inert (P-108's recorded
    limitation: the session is gone, the record names nothing
    and drives nothing). Counts are read from the store, never
    estimated; inert session ids are named so a host can see
    exactly what a prune would remove before calling it.
    """
    live = {str(sid) for sid in live_session_ids}
    per_session = {
        sid: len(store.acks_for(sid)) for sid in store.session_ids()}
    inert_ids = sorted(sid for sid in per_session if sid not in live)
    return {
        "acknowledged_sessions": len(per_session),
        "acknowledged_records": sum(per_session.values()),
        "live_acknowledged_sessions": len(per_session) - len(inert_ids),
        "inert_sessions": len(inert_ids),
        "inert_records": sum(per_session[sid] for sid in inert_ids),
        "inert_session_ids": inert_ids,
    }


def prune_inert_acknowledgements(store, live_session_ids) -> dict:
    """Prune inert records and report before/after in one view."""
    before = housekeeping_view(store, live_session_ids)
    removed = store.prune_orphans(live_session_ids)
    after = housekeeping_view(store, live_session_ids)
    return {
        **after,
        "inert_sessions_before": before["inert_sessions"],
        "inert_records_before": before["inert_records"],
        "removed_sessions": removed["removed_sessions"],
        "removed_records": removed["removed_records"],
    }


# ------------------------------------------------------------- digest


def _parse_stamp(value) -> datetime | None:
    """Parse a stored ISO stamp, tolerantly (house law: a
    stored stamp never bricks a view). Naive stamps are
    read as UTC - the stores stamp UTC ISO (_now_iso,
    AcknowledgementStore.acknowledge). Anything missing
    or unparseable yields None: no age is claimed."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _age_seconds(now: datetime, stamp) -> float | None:
    """now - stamp in seconds, or None when no honest age
    exists: stamp missing/unparseable, or stamp after now
    (clock skew - a negative age is dropped, never clamped
    to zero, the P-110 negative-span law)."""
    parsed = _parse_stamp(stamp)
    if parsed is None:
        return None
    age = (now - parsed).total_seconds()
    return age if age >= 0 else None


def _delay_seconds(start, end) -> float | None:
    """end - start in seconds with the same honesty law."""
    first, last = _parse_stamp(start), _parse_stamp(end)
    if first is None or last is None:
        return None
    delay = (last - first).total_seconds()
    return delay if delay >= 0 else None


def _age_stats(ages: list, total: int) -> dict:
    """One aging stat block: plain arithmetic over exactly
    the items that carry an age. No buckets, no thresholds,
    no staleness verdict - the digest reports how long,
    never "too long"."""
    return {
        "count": len(ages),
        "without_count": total - len(ages),
        "oldest_seconds": max(ages) if ages else None,
        "newest_seconds": min(ages) if ages else None,
        "mean_seconds": (sum(ages) / len(ages)) if ages else None,
    }


def repeat_digest(sessions, pairs=None, store=None, *, now=None) -> dict:
    """The cross-session repeat-request digest (P-115).

    Rolls the P-108 per-session signal up over ``sessions``
    (the caller scopes the set - the HTTP road passes only
    the owner's sessions) and adds wall-clock aging derived
    ONLY from stamps the tree already persists: each turn's
    recorded_at and each acknowledgement's acknowledged_at.
    ``now`` is the injected clock (datetime, ISO string, or
    None for the wall clock); every age is arithmetic from
    it, so a test - or a host with its own clock - pins the
    answer exactly. Detection truth is never recomputed:
    every request comes from session_repeat_requests, and
    the digest counts are its sums by construction.
    """
    now_dt = _parse_stamp(now) if now is not None else None
    if now_dt is None:
        now_dt = datetime.now(UTC)
    ordered = sorted(
        sessions, key=lambda s: (str(s.created_at), str(s.session_id)))
    session_entries = []
    pending_flat = []
    pending_ages: list[float] = []
    ack_ages: list[float] = []
    delay_values: list[float] = []
    pending_total = 0
    ack_total = 0
    with_requests = 0
    with_pending = 0
    for session in ordered:
        view = session_repeat_requests(session, pairs, store)
        recorded = {int(turn.turn_no): str(turn.recorded_at or "")
                    for turn in session.turns}
        pending_ages_here: list[float] = []
        oldest_pending_recorded = ""
        last_ack = ""
        for request in view["requests"]:
            stamp = recorded.get(int(request["turn_no"]), "")
            if request["state"] == STATE_PENDING:
                age = _age_seconds(now_dt, stamp)
                if age is not None:
                    pending_ages.append(age)
                    pending_ages_here.append(age)
                if not oldest_pending_recorded or (
                        stamp and stamp < oldest_pending_recorded):
                    if stamp:
                        oldest_pending_recorded = stamp
                pending_flat.append({
                    "session_id": session.session_id,
                    "chat_id": session.chat_id,
                    "turn_no": request["turn_no"],
                    "recorded_at": stamp,
                    "age_seconds": age,
                })
            else:
                ack_at = request.get("acknowledged_at", "")
                ack_age = _age_seconds(now_dt, ack_at)
                if ack_age is not None:
                    ack_ages.append(ack_age)
                delay = _delay_seconds(stamp, ack_at)
                if delay is not None:
                    delay_values.append(delay)
                if ack_at and ack_at > last_ack:
                    last_ack = ack_at
        pending_total += view["pending_count"]
        ack_total += view["acknowledged_count"]
        if view["requests"]:
            with_requests += 1
        if view["has_pending"]:
            with_pending += 1
        session_entries.append({
            "session_id": session.session_id,
            "chat_id": session.chat_id,
            "has_pending": view["has_pending"],
            "pending_count": view["pending_count"],
            "acknowledged_count": view["acknowledged_count"],
            "pending_turns": view["pending_turns"],
            "oldest_pending_age_seconds": (
                max(pending_ages_here) if pending_ages_here else None),
            "newest_pending_age_seconds": (
                min(pending_ages_here) if pending_ages_here else None),
            "oldest_pending_recorded_at": oldest_pending_recorded,
            "last_acknowledged_at": last_ack,
        })
    return {
        "generated_at": now_dt.isoformat(),
        "threshold": LOW_CONFIDENCE_THRESHOLD,
        "sessions_total": len(ordered),
        "sessions_with_requests": with_requests,
        "sessions_with_pending": with_pending,
        "requests_total": pending_total + ack_total,
        "pending_count": pending_total,
        "acknowledged_count": ack_total,
        "pending": pending_flat,
        "pending_age_seconds": _age_stats(pending_ages, pending_total),
        "acknowledged_age_seconds": _age_stats(ack_ages, ack_total),
        "acknowledgement_delay_seconds": _age_stats(delay_values, ack_total),
        "sessions": session_entries,
    }
