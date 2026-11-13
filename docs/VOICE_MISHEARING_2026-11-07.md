# P-105 — Voice Mishearing Truth (Part VII, Voice the Voxta Way)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VII only its part line — "VII |
Voice, the Voxta Way | P-101 – P-116" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: the Voxta
census row VX-11 (mishearing is handled, not hidden —
detection, automatic replacement of often-missed words,
STT confidence markings [RN-1.9.0]), the delta table's
VX-11 row (MISSING: "no mishearing detection, replacement
list, or confidence surface"), the Part I gate (VX-11
"QUEUED to the Part VII definition queue"), and the
founding S503 seam as it stands. The keeper reviews this
derived scope at banking.

The gap, exactly: S503's Transcript carries per-word
confidence (TranscriptWord.probability; faster-whisper
supplies real probabilities with word timestamps on), but
P-101's VoiceTurnRecord.from_orchestrator persisted only
the transcript TEXT — every probability was dropped at the
persistence boundary, so no confidence marking, detection
or replacement could ever be honest afterwards. P-105
repairs the boundary and builds VX-11's truth layer on
the persisted evidence. It does not build the dialogue
layer (a character asking for a repeat) or a UI rendering:
both need this layer first and remain open.

The other named open items were weighed and NOT taken:
- L3 (P-091 TTS/STT plugin citizens unregistered in the
  running app): deliberate host-explicit law in P-091,
  re-affirmed by P-102, P-103 and P-104. No new evidence
  overturns it; this slice does not reopen it.
- VX-12 (affects/prosody): no affect seam exists in any
  TTS backend (VoiceInfo carries no affect field, no
  backend consumes one); it needs its own engine design.
- VX-13 (narrator voice): chats have no narration
  taxonomy consumer (VX-41 types are not chat citizens),
  so a narrator voice would have nothing lawful to read;
  the scenario interop's narrator field (P-026) stays
  data until that taxonomy exists.

Base: c53d053 (P-103 banking record; P-104 was being
banked concurrently and reconciles at banking).
Migration: NONE — head stays 0041.

## 1. What landed

- src/runmal/voice/session.py — WordConfidence (new,
  frozen; probability validated to [0, 1]) and
  VoiceTurnRecord.transcript_words: captured verbatim
  from the STT Transcript in from_orchestrator, accepted
  by record_turn, round-tripped by to_dict/from_dict.
  A pre-P-105 stored turn loads with no words.
- src/runmal/voice/mishearing.py (new) — the pure truth
  layer: the predeclared threshold, per-turn and
  per-session views, apply_replacements, and the
  ReplacementStore lexicon citizen.
- src/runmal/voice/mishearing_router.py (new) — the
  HTTP surface (section 3), included by app.py on the
  founding road.
- src/runmal/voice/router.py — the manual /turns road
  accepts an optional transcript_words field; malformed
  entries answer 422 through the existing road.
- src/runmal/voice/__init__.py — one docstring line.
- Battery: tests/test_p105_voice_mishearing.py (21 tests).

## 2. The truth law

- Evidence persists verbatim: the probability on the
  record is the backend's own estimate, never recomputed,
  rounded or upgraded. The turn's stt_backend rides on
  the record so a reader can judge the source (a backend
  that reports 1.0 for every word — the fake ear does —
  yields evidence that says exactly that). No calibration
  is claimed.
- No evidence is a fact, not a zero: a turn with no
  recorded words reports has_confidence_evidence false,
  needs_repeat false, and null min/mean — never "all
  words confident".
- Detection: LOW_CONFIDENCE_THRESHOLD = 0.5, predeclared
  in the module — below even odds the model's own
  estimate says the word is more likely wrong than
  right, so it is marked low. A turn with any low word
  carries needs_repeat: the detection data behind
  VX-11's "ask the user to repeat".
- Replacements suggest, never rewrite: the lexicon maps
  a misheard word to its intended word; the suggestion
  is a view over the stored transcript, which is never
  mutated. Matching is whole-word only, case-insensitive
  on the punctuation-stripped token core; leading
  capitalisation and surrounding punctuation are
  preserved ("lift," and "Lift!" suggest correctly;
  "lifting" never matches "lift").

## 3. HTTP surface (founding road, bearer-gated)

- GET /api/v1/voice/sessions/{id}/mishearings -> the
  session view {session_id, chat_id, threshold,
  turns_total, turns_with_evidence,
  turns_needing_repeat, low_confidence_words_total,
  turns: [{turn_no, stt_backend,
  has_confidence_evidence, words: [{text, probability,
  band}], low_confidence_words, min/mean probability,
  needs_repeat, transcript_text, suggested_text,
  replacements_applied}]}. Unknown and foreign sessions
  are 404 (the P-103 owner rule — existence never leaks).
- GET /api/v1/voice/mishearing-replacements -> the
  lexicon {replacements: [{misheard, replacement}]}.
- PUT /api/v1/voice/mishearing-replacements {misheard,
  replacement} -> the lexicon. A misheard that is not
  exactly one punctuation-free word, or an empty
  replacement, answers 422 — a phrase key could never
  fire under whole-word matching, so it is refused at
  the door instead of stored as a silent no-op.
- DELETE /api/v1/voice/mishearing-replacements/{word}
  -> {removed, replacements}; an absent pair is
  removed: false, not an error (housekeeping road).
- POST /api/v1/voice/sessions/{id}/turns gains the
  optional transcript_words [{text, probability}];
  a probability outside [0, 1], a non-object entry or a
  non-list value answers 422. Every founding field is
  unchanged.
- The lexicon is install-wide (a versioned JSON
  document, voice_mishearing_replacements.json — the
  settings/session house pattern), like voice settings:
  stated plainly, not per-user. Its load is tolerant —
  corrupt document reads as empty, a malformed pair is
  skipped; the store never bricks the voice surface.

## 4. Honest limitations

- Detection is data, not dialogue: needs_repeat names
  the turns a host should ask about, but no character
  asks for a repeat in this slice — the live responder
  is the honest-unavailable seam (P-102), and
  fabricating a repeat request would cross it.
- P-103 projection still lands the original transcript
  text; a projected message carries neither the
  suggestion nor a mishearing mark. Whether it should
  is a later slice's design question.
- The lexicon matches whole words only: no phrases,
  no stemming, no fuzzy matching. A mishearing the
  lexicon does not name stays only a low-confidence
  mark.
- Confidence markings are data on the HTTP surface;
  no UI renders them in this slice. VX-11's remaining
  surface (rendered markings, mid-dialogue detection)
  stays open on top of this truth layer.

## 5. Battery

tests/test_p105_voice_mishearing.py — 21 tests: the
evidence citizen (probability bounds, orchestrator
capture, no-transcript emptiness, round-trip incl.
store reload, the legacy stored shape), detection (the
predeclared threshold and its edge, low-word views,
all-confident turns, session aggregation), replacement
(whole-word/case/punctuation law, no-match and empty
roads, the never-mutates pin), the lexicon store
(round-trip, normalisation refusals, tolerant load),
the HTTP roads (the full mishearings flow with the
stored transcript proven unrewritten, optional-evidence
turns, the three 422 shapes, lexicon CRUD incl.
removed:false, unknown + foreign 404), and the 0041
migration pin. Neighbour and full-suite counts are
recorded from the run logs in
hidden_files/P105_EVIDENCE.md, never estimated here.
