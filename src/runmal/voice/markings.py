"""Voice rendered confidence markings (P-107, Part VII - DERIVED scope, VX-11).

The Voxta census row VX-11 ends: the UI shows speech-to-text
confidence markings. P-105 built the truth layer as data on
an HTTP surface and named the remainder plainly - no UI
renders the markings; P-106 carries the same facts into
projected-message provenance as a receipt and states the
mark is not a rendering. This module is the rendering's
server half: the marking view for ONE landed chat message.

The marking is a VIEW over two banked citizens, never a
second truth:

- the message's P-075 provenance record (P-103) names the
  voice session and turn a landed transcript came from
  (origin via=voice_session, voice_side=transcript,
  voice_session_id, voice_turn_no);
- the turn's mishearing truth is P-105's own turn_mishearing
  view - threshold, bands and suggested hearing are imported
  from runmal.voice.mishearing, never redeclared here, so
  this rendering and P-106's provenance receipt read the
  same persisted evidence and cannot disagree.

Honesty law (P-075/P-105): no evidence is a FACT, not a
zero. A voice transcript whose session or turn can no longer
be resolved (store moved on, legacy record) gets the GAP
marking - evidence_available False - never a silent clean
bill and never a fabricated doubt. A turn with no recorded
words reports has_confidence_evidence False exactly as
P-105 does. Content law is untouched: the stored message
text is the verbatim transcript; the suggested hearing
rides inside the marking only, never as content.

The response side carries NO marking: it concerns what the
ear heard of the user; a response's heard split is P-103's
own provenance fact. No migration - head stays 0041.
"""

from __future__ import annotations

from runmal.voice import mishearing as mis_mod

__all__ = [
    "voice_origin",
    "message_marking",
    "markings_for_messages",
]


def voice_origin(provenance_view) -> dict | None:
    """The voice-transcript origin facts of a message's
    provenance active_view, or None when the message is not
    a landed voice transcript (not recorded, not via a voice
    session, the response side, or a malformed view)."""
    if not isinstance(provenance_view, dict):
        return None
    if provenance_view.get("recorded") is not True:
        return None
    origin = provenance_view.get("origin")
    if not isinstance(origin, dict):
        return None
    facts = origin  # P-075: origin facts ride flat on the section
    if facts.get("via") != "voice_session":
        return None
    if facts.get("voice_side") != "transcript":
        return None
    session_id = facts.get("voice_session_id")
    turn_no = facts.get("voice_turn_no")
    if not session_id or not isinstance(turn_no, int):
        return None
    return {
        "voice_session_id": session_id,
        "voice_turn_no": turn_no,
        "stt_backend": facts.get("stt_backend"),
    }


def _gap_marking(origin: dict) -> dict:
    """The recorded gap: the message IS a voice transcript
    but its evidence can no longer be resolved."""
    return {
        "voice_session_id": origin["voice_session_id"],
        "voice_turn_no": origin["voice_turn_no"],
        "evidence_available": False,
        "has_confidence_evidence": False,
        "needs_repeat": False,
        "threshold": mis_mod.LOW_CONFIDENCE_THRESHOLD,
        "word_count": 0,
        "low_confidence_words": [],
        "low_confidence_count": 0,
        "min_probability": None,
        "mean_probability": None,
        "words": [],
        "suggested_text": None,
        "replacements_applied": [],
    }


def message_marking(provenance_view, store, pairs=None) -> dict | None:
    """One landed message's rendered-marking view (pure).

    None for any message that is not a voice transcript.
    store is a VoiceSessionStore; pairs the P-105
    replacement lexicon (misheard -> intended), used only
    for the suggested hearing inside the marking.
    """
    origin = voice_origin(provenance_view)
    if origin is None:
        return None
    session = store.get(origin["voice_session_id"]) if store else None
    turn = None
    if session is not None:
        for candidate in session.turns:
            if candidate.turn_no == origin["voice_turn_no"]:
                turn = candidate
                break
    if session is None or turn is None:
        return _gap_marking(origin)
    view = mis_mod.turn_mishearing(turn, pairs or {})
    return {
        "voice_session_id": origin["voice_session_id"],
        "voice_turn_no": origin["voice_turn_no"],
        "evidence_available": True,
        "has_confidence_evidence": view["has_confidence_evidence"],
        "needs_repeat": view["needs_repeat"],
        "threshold": mis_mod.LOW_CONFIDENCE_THRESHOLD,
        "word_count": view["word_count"],
        "low_confidence_words": view["low_confidence_words"],
        "low_confidence_count": view["low_confidence_count"],
        "min_probability": view["min_probability"],
        "mean_probability": view["mean_probability"],
        "words": view["words"],
        "suggested_text": view["suggested_text"],
        "replacements_applied": view["replacements_applied"],
    }


def markings_for_messages(message_dicts, store, pairs=None) -> int:
    """Attach voice_marking additively to each message
    dict that is a landed voice transcript; returns how many
    were attached. Dicts without a qualifying provenance
    view are left byte-identical."""
    attached = 0
    for entry in message_dicts:
        if not isinstance(entry, dict):
            continue
        marking = message_marking(entry.get("provenance"), store, pairs)
        if marking is not None:
            entry["voice_marking"] = marking
            attached += 1
    return attached
