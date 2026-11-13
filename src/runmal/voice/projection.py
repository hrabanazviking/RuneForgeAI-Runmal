"""Voice turn projection (P-103, Part VII - DERIVED scope, L2).

P-101 persisted voice turns in the session store and named
the open question: whether and how a heard turn becomes a
chat message. P-102 made turns live and left L2 open. This
module is the projection road: a recorded session turn lands
in its chat as ordinary messages through the one append road
(``chats.service.append_message``), so history, export,
memory and prompt context finally see the conversation the
user actually had out loud.

What lands, per turn (see the P-103 design):
- the transcript, exactly as transcribed, as a user message;
- the HEARD response - ``VoiceTurnRecord.history_text()``,
  certain text plus the explicit uncertainty marker - as an
  assistant message. Unplayed text NEVER lands (S508 /
  INV-020 carried into the transcript); an error turn with
  no heard text lands no assistant message; nothing is
  fabricated to fill a turn.

Provenance follows P-075 under the P-089 closed-vocabulary
doctrine: the origin kind stays ``manual`` and scalar origin
facts name the voice road (via / voice_session_id /
voice_turn_no / voice_side + the side's backend facts). The
response's model section is the recorded gap ``unknown`` -
the persisted turn holds no generation model, so none is
claimed. Projection state rides on the turn record itself
(projected flag + per-side message ids, P-101 JSON store -
no migration), making projection idempotent and per-side
resumable: a half-projected turn resumes with only the
missing side, and the store is saved after every turn.

Projection is EXPLICIT: the P-102 live controller is
synchronous and DB-free by design, so no auto-projection
hook is wired into its persist road; a host calls
:func:`project_session_turns` (or the HTTP road) after turns
complete. The session store stays the truth record -
projected messages are its transcript shadow, and later
edits or deletes of a message never write back to it.

P-106 adds the mishearing mark: when a turn is projected,
its persisted per-word STT confidence (P-105) is read back
as scalar provenance facts and as per-turn data on the
status/report views, so a doubted transcript no longer
looks identical in history to a certain one. The content
law is unchanged: the transcript lands verbatim, P-105's
suggested text never lands, and the stored transcript is
never rewritten. The mark itself holds counts, flags and
probability summaries only in provenance (P-075 scalars);
word texts appear only in the status/report receipt data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from runmal.chats import provenance as prov_mod

__all__ = [
    "ProjectionError",
    "transcript_mishearing_mark",
    "transcript_provenance",
    "response_provenance",
    "plan_turn",
    "projection_status",
    "project_session_turns",
]


class ProjectionError(ValueError):
    """A projection the session's ownership forbids."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# -------------------------------------------------- mishearing mark

_FALLBACK_THRESHOLD = 0.5


def _threshold() -> float:
    try:
        from runmal.voice.mishearing import LOW_CONFIDENCE_THRESHOLD
        value = float(LOW_CONFIDENCE_THRESHOLD)
    except Exception:
        return _FALLBACK_THRESHOLD
    if 0.0 <= value <= 1.0:
        return value
    return _FALLBACK_THRESHOLD


def _entry_text_prob(entry):
    if isinstance(entry, dict):
        text = entry.get("text", "")
        prob = entry.get("probability")
    else:
        text = getattr(entry, "text", "")
        prob = getattr(entry, "probability", None)
    if isinstance(prob, bool) or not isinstance(prob, (int, float)):
        return None
    prob_f = float(prob)
    if not (0.0 <= prob_f <= 1.0):
        return None
    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = str(text)
    return text, prob_f


def transcript_mishearing_mark(turn) -> dict:
    threshold = _threshold()
    raw = getattr(turn, "transcript_words", None) or ()
    try:
        entries_in = list(raw)
    except TypeError:
        entries_in = []
    usable = []
    for entry in entries_in:
        parsed = _entry_text_prob(entry)
        if parsed is not None:
            usable.append(parsed)
    probs = [prob for _txt, prob in usable]
    low = [(txt, prob) for txt, prob in usable if prob < threshold]
    return {
        "has_confidence_evidence": bool(usable),
        "word_count": len(usable),
        "low_confidence_words": [txt for txt, _p in low],
        "low_confidence_count": len(low),
        "min_probability": min(probs) if probs else None,
        "mean_probability": (round(sum(probs) / len(probs), 4) if probs else None),
        "needs_repeat": bool(low),
        "threshold": threshold,
    }


# ----------------------------------------------------- provenance


def transcript_provenance(session, turn) -> dict:
    """The P-075 record for the user's spoken line.

    The words are the user's own (kind ``manual``, the P-089
    doctrine); the STT fact is named in origin facts, so the
    model section is honestly not_applicable.
    """
    mark = transcript_mishearing_mark(turn)
    return prov_mod.build_record(
        origin_kind="manual",
        origin={
            "via": "voice_session",
            "voice_session_id": session.session_id,
            "voice_turn_no": turn.turn_no,
            "voice_side": "transcript",
            "stt_backend": turn.stt_backend or session.settings.stt_backend,
            "transcript_language": turn.transcript_language or None,
            "mishearing_evidence": bool(mark["has_confidence_evidence"]),
            "mishearing_needs_repeat": bool(mark["needs_repeat"]),
            "mishearing_word_count": int(mark["word_count"]),
            "mishearing_low_word_count": int(mark["low_confidence_count"]),
            "mishearing_min_probability": mark["min_probability"],
            "mishearing_mean_probability": mark["mean_probability"],
            "mishearing_threshold": float(mark["threshold"]),
        },
        model=prov_mod.model_section(status="not_applicable"),
        preset=prov_mod.preset_section(status="unknown"),
        lore=prov_mod.lore_section(status="not_applicable"),
        speaker={"speaker_id": session.user_id, "speaker_name": None},
    )


def response_provenance(session, turn) -> dict:
    """The P-075 record for the companion's heard response.

    Kind stays ``manual`` (closed vocabulary); the model
    section is ``unknown`` - the persisted turn records no
    generation model, and a gap is recorded, never filled.
    The heard split is receipt data: which spans were
    certain / uncertain is exactly what the landed text
    claims, so the counts ride as scalar facts.
    """
    return prov_mod.build_record(
        origin_kind="manual",
        origin={
            "via": "voice_session",
            "voice_session_id": session.session_id,
            "voice_turn_no": turn.turn_no,
            "voice_side": "response",
            "tts_backend": session.settings.tts_backend,
            "voice_id": session.settings.voice_id,
            "heard_certain_chars": len(turn.heard_certain),
            "heard_uncertain_chars": len(turn.heard_uncertain),
            "heard_unplayed_chars": len(turn.heard_unplayed),
            "interrupted": bool(turn.interrupted),
        },
        model=prov_mod.model_section(status="unknown"),
        preset=prov_mod.preset_section(status="unknown"),
        lore=prov_mod.lore_section(status="not_applicable"),
        speaker={"speaker_id": session.character_id, "speaker_name": None},
    )


# --------------------------------------------------------- planning


def plan_turn(session, turn) -> list[dict]:
    """The messages one turn should land, in order (pure).

    Each entry: {side, role, content, provenance}. A side
    already landed (its id is on the turn) is omitted, so a
    resumed projection plans only what is missing. Content
    follows the landing law exactly: the transcript verbatim;
    the response as history_text() - never the unplayed span.
    """
    plan: list[dict] = []
    if turn.transcript_text.strip() and not turn.projected_user_message_id:
        plan.append({
            "side": "transcript", "role": "user",
            "content": turn.transcript_text,
            "provenance": transcript_provenance(session, turn),
        })
    heard = turn.history_text()
    if heard and not turn.projected_assistant_message_id:
        plan.append({
            "side": "response", "role": "assistant",
            "content": heard,
            "provenance": response_provenance(session, turn),
        })
    return plan


def projection_status(session) -> dict:
    """Per-turn projection state, as data (pure)."""
    turns = []
    messages = 0
    marks = []
    for turn in session.turns:
        mark = transcript_mishearing_mark(turn)
        marks.append((turn, mark))
        ids = [turn.projected_user_message_id,
               turn.projected_assistant_message_id]
        messages += sum(1 for i in ids if i)
        turns.append({
            "turn_no": turn.turn_no,
            "projected": bool(turn.projected),
            "user_message_id": turn.projected_user_message_id or None,
            "assistant_message_id": (
                turn.projected_assistant_message_id or None),
            "projected_at": turn.projected_at or None,
            "mishearing": mark,
        })
    return {
        "session_id": session.session_id,
        "chat_id": session.chat_id,
        "turns_total": len(session.turns),
        "turns_projected": sum(1 for t in session.turns if t.projected),
        "messages_projected": messages,
        "turns_with_mishearing_evidence": sum(
            1 for _t, m in marks if m["has_confidence_evidence"]),
        "turns_needing_repeat": [
            turn.turn_no for turn, m in marks if m["needs_repeat"]],
        "low_confidence_words_total": sum(
            m["low_confidence_count"] for _t, m in marks),
        "turns": turns,
    }


# ---------------------------------------------------------- service


async def project_session_turns(db, *, user_id: str, session, store=None) -> dict:
    """Project one session's unprojected turns into its chat.

    ``db`` is an AsyncSession; ``session`` is a P-101
    VoiceSession; ``store`` (optional) is saved after every
    turn so progress is durable turn by turn. Raises
    ProjectionError when the session belongs to another
    owner and KeyError when the chat is missing/foreign
    (the append road's own ownership check is the backstop).
    Returns the projection report (see the P-103 design).
    """
    from runmal.chats import service as chats_svc
    from runmal.characters.service import get_character

    if session.user_id != user_id:
        raise ProjectionError(
            "voice session belongs to a different owner")
    chat = await chats_svc.get_chat(db, user_id, session.chat_id)
    if chat is None:
        raise KeyError(session.chat_id)
    char_name = None
    if session.character_id:
        character = await get_character(db, user_id, session.character_id)
        if character is not None:
            char_name = character.name or None
    all_marks = {t.turn_no: transcript_mishearing_mark(t) for t in session.turns}
    report = {
        "session_id": session.session_id,
        "chat_id": session.chat_id,
        "projected_turns": 0,
        "already_projected": 0,
        "no_content_turns": 0,
        "messages_created": 0,
        "turns_needing_repeat": [
            t.turn_no for t in sorted(session.turns, key=lambda x: x.turn_no)
            if all_marks[t.turn_no]["needs_repeat"]],
        "low_confidence_words_total": sum(
            m["low_confidence_count"] for m in all_marks.values()),
        "turns": [],
    }
    for turn in sorted(session.turns, key=lambda t: t.turn_no):
        if turn.projected:
            report["already_projected"] += 1
            report["turns"].append({
                "turn_no": turn.turn_no, "outcome": "already_projected",
                "user_message_id": turn.projected_user_message_id or None,
                "assistant_message_id": (
                    turn.projected_assistant_message_id or None),
                "mishearing": all_marks[turn.turn_no],
            })
            continue
        plan = plan_turn(session, turn)
        for step in plan:
            record = step["provenance"]
            if step["side"] == "response" and char_name and record.get("speaker"):
                record["speaker"]["speaker_name"] = char_name
            message = await chats_svc.append_message(
                db, user_id, session.chat_id, step["role"], step["content"],
                speaker_id=(session.user_id if step["side"] == "transcript"
                            else session.character_id),
                speaker_name=(char_name if step["side"] == "response" else None),
                provenance=record,
            )
            if step["side"] == "transcript":
                turn.projected_user_message_id = message.id
            else:
                turn.projected_assistant_message_id = message.id
            report["messages_created"] += 1
        turn.projected = True
        turn.projected_at = _now_iso()
        if store is not None:
            store.save_session(session)
        if plan:
            report["projected_turns"] += 1
            outcome = "projected"
        else:
            report["no_content_turns"] += 1
            outcome = "no_content"
        report["turns"].append({
            "turn_no": turn.turn_no, "outcome": outcome,
            "user_message_id": turn.projected_user_message_id or None,
            "assistant_message_id": (
                turn.projected_assistant_message_id or None),
            "mishearing": all_marks[turn.turn_no],
        })
    return report
