# P-106 — Voice Projection Mishearing Mark (Part VII, Voice the Voxta Way)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VII only its part line — "VII |
Voice, the Voxta Way | P-101 – P-116" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: P-105's slice
doc (docs/VOICE_MISHEARING_2026-11-07.md §4), which states
in its honest limitations that P-103 projection still
lands the original transcript text and a projected message
carries neither the suggestion nor a mishearing mark, and
that whether it should is a later slice's design question.
P-106 is that later slice. It takes the MARK half and
declines the suggestion half, for the reason in section 2.
The keeper reviews this derived scope at banking.

Base: c067a57 (P-104 banking record). P-105 banks before
this slice in roadmap order and reconciles at banking;
this slice builds on the P-104 base exactly as designed,
reading P-105's persisted word evidence duck-typed so the
same code reads the real evidence unchanged once P-105
banks. Migration: NONE — head stays 0041.

## 1. What landed

- src/runmal/voice/projection.py — the only code file
  changed: the pure transcript_mishearing_mark(turn), the
  scalar mishearing facts on transcript_provenance, and
  the additive per-turn marks + aggregates on
  projection_status and the project_session_turns report.
  P-104 inherits all of it unchanged through the one
  projection service — no second road.
- Battery: tests/test_p106_voice_projection_mishearing.py
  (18 tests).
- This slice doc and one appended clean-room log entry.

## 2. The mark law

- transcript_mishearing_mark(turn) is pure. It reads the
  turn's word evidence duck-typed via getattr
  (transcript_words; entries may be P-105 WordConfidence
  objects, dicts, or any object with text/probability)
  and returns {has_confidence_evidence, word_count,
  low_confidence_words, low_confidence_count,
  min_probability, mean_probability, needs_repeat,
  threshold}. Detection uses P-105's predeclared
  LOW_CONFIDENCE_THRESHOLD, imported from
  runmal.voice.mishearing when that module is present;
  on the P-104 base the same value 0.5 stands as the
  module fallback, and a battery test pins the two equal
  whenever the import succeeds.
- An entry whose probability is not a real number in
  [0, 1] is not evidence and is skipped (strings, None,
  booleans, NaN, infinities and out-of-range values all
  fail this test). A turn left with no usable entries
  reports NO evidence — never "all words confident"
  (the P-105 law). Mean probability is rounded to 4
  places, exactly as P-105's own view rounds it; min is
  the verbatim minimum. No calibration is claimed.
- transcript_provenance gains scalar origin facts from
  the mark, ALWAYS present (P-075: a gap is recorded,
  never silently absent): mishearing_evidence (bool),
  mishearing_needs_repeat (bool), mishearing_word_count
  (int), mishearing_low_word_count (int),
  mishearing_min_probability (float|null),
  mishearing_mean_probability (float|null),
  mishearing_threshold (float). Scalars only —
  build_record refuses anything else, and the P-075 law
  records no content: no word texts and no suggested
  text ride in provenance.
- projection_status: each turn gains a "mishearing"
  mark; the session view gains
  turns_with_mishearing_evidence (int),
  turns_needing_repeat (list of turn numbers) and
  low_confidence_words_total (int). Additive keys only.
- project_session_turns report: each turn entry gains
  the same "mishearing" mark (including
  already-projected entries); the report gains
  turns_needing_repeat (list) and
  low_confidence_words_total (int), computed over the
  whole session. Additive keys only.
- Content law UNCHANGED: the transcript lands verbatim;
  P-105's suggested text NEVER lands as message content
  and the stored transcript is never rewritten. The
  suggestion half of P-105's named gap is DECLINED, on
  the record: provenance holds no content (P-075), and
  landing a rewrite would put words in the user's mouth
  in their own chat history. The suggestion stays where
  P-105 put it — a view on the mishearings surface.
- Word texts of low-confidence words appear ONLY in the
  status/report mark (receipt data about the session,
  like P-105's own session view) — never in provenance.

## 3. Honest limitations

- On the P-104 base every stored turn has no word
  evidence (P-105's persistence repair is in P-105's
  tree), so every mark produced on this base says
  has_confidence_evidence false. That is the truth of
  this base, stated plainly; once P-105 banks, the same
  code reads the real persisted evidence with no change.
  The battery therefore attaches evidence duck-typed,
  exactly the shape P-105 persists.
- The mark is a receipt, not a rendering: no UI shows
  it in this slice (VX-11's rendered markings stay
  open), and no character asks for a repeat (the
  responder is still P-102's honest-unavailable seam).
- Already-projected turns are not back-marked: a landed
  message's provenance is its production receipt
  (P-075). Turns projected before P-105/P-106 keep the
  receipt they were produced with; the session store's
  mishearings surface remains the place to read evidence
  for those turns. The report/status marks, being views
  over the session store, do show the mark for such
  turns — view data, not a rewritten receipt.
- Response side untouched: the mark concerns what the
  ear heard of the USER; response provenance already
  carries its own heard-split facts (P-103).
- No migration, no new store, no new HTTP road: the
  existing projection status/report roads carry the
  mark because they serialise projection.py's dicts.

## 4. Battery

tests/test_p106_voice_projection_mishearing.py — 18
tests: the mark (no evidence / legacy turn / empty and
None evidence / all-confident / low words / threshold
edge at exactly 0.5 / malformed entries skipped /
all-malformed is no-evidence / dict-shaped words /
threshold agreement with P-105 when importable / mean
rounding and integer probabilities), provenance (mark
facts on a low turn, explicit no-evidence facts,
scalars-only + tolerant-reader round trip, no word
texts and no suggested text in provenance), status +
report (per-turn marks, aggregates, service landing
with the mark asserted on the stored message's
provenance and the content law pinned, idempotent
re-projection), and the 0041 pin. Neighbour and
full-suite counts are recorded from the run logs in
hidden_files/P106_EVIDENCE.md, never estimated here.
