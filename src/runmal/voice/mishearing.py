"""Voice mishearing truth (P-105, Part VII - DERIVED scope, VX-11).

The Voxta census row VX-11: mishearing is handled, not hidden -
characters can detect misheard words, often-missed words are
replaced after transcription, and the UI shows STT confidence
markings. The delta table recorded Rúnmál MISSING on all three
(no detection, no replacement list, no confidence surface) and
the Part I gate queued the row to Part VII.

The founding S503 seam already produced the evidence this row
needs - TranscriptWord.probability, real from faster-whisper -
but P-101's persisted turn record dropped every probability at
the persistence boundary, so after a turn was recorded the
evidence no longer existed and nothing honest could be built
on it. P-105 repairs the boundary (session.py now persists
transcript_words verbatim) and builds this truth layer on it:

- DETECTION: a word is marked low-confidence when its own
  model probability falls below LOW_CONFIDENCE_THRESHOLD -
  predeclared below, by the model's own estimate more likely
  wrong than right. A turn with any low word carries
  needs_repeat: the detection data behind "ask the user to
  repeat". Detection is data, not dialogue - no character
  asks for a repeat from this module (the live responder is
  the honest-unavailable seam, P-102).
- REPLACEMENT: a user lexicon (ReplacementStore, a versioned
  JSON document - the voice house pattern) maps a misheard
  word to its intended word. apply_replacements produces a
  SUGGESTED text; the stored transcript is never mutated,
  and P-103 projection still lands the original text.
- NO EVIDENCE IS A FACT, not a zero: a turn recorded before
  P-105 (or by a road without word evidence) has no words,
  and every view says has_confidence_evidence False for it -
  never "all words confident".

Confidence is the STT backend's own estimate, persisted
verbatim and never recomputed or upgraded; the turn's
stt_backend rides on the record so a reader can judge the
source. No calibration is claimed. Storage is JSON-store
data; NO migration - the head stays 0041.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: Predeclared marking threshold (P-105 design): below even
#: odds, the model's own estimate says the word is more
#: likely wrong than right. Rúnmál's threshold, not a
#: Voxta fact; declared before any marking was built on it.
LOW_CONFIDENCE_THRESHOLD = 0.5

REPLACEMENTS_VERSION = 1
REPLACEMENTS_FILENAME = "voice_mishearing_replacements.json"

_PUNCTUATION = ".,!?;:\"'()[]{}<>“”‘’«»"


def replacements_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / REPLACEMENTS_FILENAME


def word_band(probability: float) -> str:
    """One word's confidence band under the predeclared law."""
    return "low" if probability < LOW_CONFIDENCE_THRESHOLD else "ok"


# ------------------------------------------------------ replacements


def _split_affixes(token: str) -> tuple[str, str, str]:
    """(leading punctuation, core, trailing punctuation)."""
    start = 0
    while start < len(token) and token[start] in _PUNCTUATION:
        start += 1
    end = len(token)
    while end > start and token[end - 1] in _PUNCTUATION:
        end -= 1
    return token[:start], token[start:end], token[end:]


def apply_replacements(text: str, pairs: dict[str, str]) -> tuple[str, list[dict]]:
    """The suggested correction of ``text`` under the lexicon.

    Whole-word matching only: a token matches when its
    punctuation-stripped core, lower-cased, is a lexicon key.
    Leading capitalisation and surrounding punctuation are
    preserved. Returns (suggested_text, applied) where
    applied names each replacement and its count, in
    first-use order. The input text is never mutated -
    a suggestion is a view, not a rewrite.
    """
    if not text or not pairs:
        return text, []
    counts: dict[str, int] = {}
    order: list[str] = []
    out_tokens: list[str] = []
    for token in text.split(" "):
        lead, core, trail = _split_affixes(token)
        key = core.lower()
        if core and key in pairs:
            replacement = pairs[key]
            if core[:1].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            out_tokens.append(lead + replacement + trail)
            if key not in counts:
                counts[key] = 0
                order.append(key)
            counts[key] += 1
        else:
            out_tokens.append(token)
    applied = [
        {"misheard": key, "replacement": pairs[key], "count": counts[key]}
        for key in order
    ]
    return " ".join(out_tokens), applied


# ------------------------------------------------------------ views


def turn_mishearing(turn, pairs: dict[str, str] | None = None) -> dict:
    """One recorded turn's mishearing truth, as data (pure).

    ``pairs`` is the replacement lexicon (misheard ->
    intended, normalised keys); without one the suggestion
    is the transcript itself with nothing applied.
    """
    words = list(getattr(turn, "transcript_words", ()) or ())
    entries = [
        {
            "text": w.text,
            "probability": w.probability,
            "band": word_band(w.probability),
        }
        for w in words
    ]
    low = [e for e in entries if e["band"] == "low"]
    probabilities = [e["probability"] for e in entries]
    suggested, applied = apply_replacements(
        turn.transcript_text, pairs or {})
    return {
        "turn_no": turn.turn_no,
        "stt_backend": turn.stt_backend,
        "has_confidence_evidence": bool(entries),
        "words": entries,
        "word_count": len(entries),
        "low_confidence_words": [e["text"] for e in low],
        "low_confidence_count": len(low),
        "min_probability": min(probabilities) if probabilities else None,
        "mean_probability": (
            round(sum(probabilities) / len(probabilities), 4)
            if probabilities else None
        ),
        "needs_repeat": bool(low),
        "transcript_text": turn.transcript_text,
        "suggested_text": suggested,
        "replacements_applied": applied,
    }


def session_mishearing(session, pairs: dict[str, str] | None = None) -> dict:
    """One session's mishearing truth, as data (pure)."""
    turns = [turn_mishearing(t, pairs) for t in session.turns]
    return {
        "session_id": session.session_id,
        "chat_id": session.chat_id,
        "threshold": LOW_CONFIDENCE_THRESHOLD,
        "turns_total": len(turns),
        "turns_with_evidence": sum(
            1 for t in turns if t["has_confidence_evidence"]),
        "turns_needing_repeat": [
            t["turn_no"] for t in turns if t["needs_repeat"]],
        "low_confidence_words_total": sum(
            t["low_confidence_count"] for t in turns),
        "turns": turns,
    }


# ------------------------------------------------------------ store


def normalize_misheard(raw: str) -> str:
    """A lexicon key: one lower-cased token, punctuation-free.

    Raises ValueError for anything that is not exactly one
    word - the lexicon matches whole words, so a phrase key
    could never fire and is refused at the door instead of
    being stored as a silent no-op.
    """
    key = str(raw or "").strip().lower()
    _lead, core, _trail = _split_affixes(key)
    if not core or core != key or any(ch.isspace() for ch in key):
        raise ValueError(
            "misheard word must be exactly one word without punctuation")
    return key


class ReplacementStore:
    """The user replacement lexicon: a versioned JSON document.

    Install-wide, like voice settings (stated plainly in the
    P-105 design - not per-user). Load is tolerant, the voice
    house pattern: a missing file is an empty lexicon; a
    corrupt document reads as empty; a malformed pair is
    skipped - the store never bricks the voice surface.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or replacements_path()
        self._pairs: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            doc = json.loads(self.path.read_text())
            entries = doc.get("replacements") if isinstance(doc, dict) else None
            if not isinstance(entries, dict):
                return
            for raw_key, raw_value in entries.items():
                try:
                    key = normalize_misheard(str(raw_key))
                except ValueError:
                    continue  # one bad pair never sinks the lexicon
                value = str(raw_value or "").strip()
                if value:
                    self._pairs[key] = value
        except (ValueError, TypeError, OSError):
            self._pairs = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "version": REPLACEMENTS_VERSION,
            "replacements": dict(sorted(self._pairs.items())),
        }
        self.path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    def pairs(self) -> dict[str, str]:
        return dict(self._pairs)

    def view(self) -> dict:
        return {
            "replacements": [
                {"misheard": key, "replacement": self._pairs[key]}
                for key in sorted(self._pairs)
            ]
        }

    def set(self, misheard: str, replacement: str) -> dict:
        """Add or replace one pair; returns the lexicon view."""
        key = normalize_misheard(misheard)
        value = str(replacement or "").strip()
        if not value:
            raise ValueError("replacement must not be empty")
        self._pairs[key] = value
        self.save()
        return self.view()

    def remove(self, misheard: str) -> bool:
        """Remove one pair (housekeeping: absence is not an error)."""
        try:
            key = normalize_misheard(misheard)
        except ValueError:
            return False
        if key not in self._pairs:
            return False
        del self._pairs[key]
        self.save()
        return True
