# P-114 - Voice Mishearing Session Report (Part VII)

## Derivation statement (binding honesty)
The governing roadmap gives Part VII only its part line -
VII | Voice, the Voxta Way | P-101..P-116 - and no per-slice
entries. This scope is DERIVED, not roadmap verbatim, from
in-tree sources only: P-105's recorded leftover (its
confidence evidence carried per-turn views and session
totals, but no session-level aggregate) and P-110's house
pattern for exactly this shape (latency pairs per-turn
evidence with an aggregate block; confidence evidence
never got its aggregate half). The scout weighed three
other candidates and recorded why each was not taken
(hidden_files/P114_SCOUT.md): per-session affect history
(no per-turn affect was ever recorded - a history surface
could only restate the one snapshot P-109 already
surfaces, and inventing one would fabricate truth), the
repeat-request digest/aging view (second place - it
summarises a signal derived from this same evidence, and
aging needs invented buckets where this slice needs no
new threshold), and session lifecycle custody (verified
already complete: deletion drops the whole session record
and P-111 prunes its orphaned acknowledgements in the
same act). The keeper reviews this derived scope at
banking. Base b70b3bc (P-112 banking record). Migration:
NONE.

## 1. The gap, exactly
P-105 built the mishearing truth layer: per-word evidence,
per-turn views, and a session view carrying totals only
(turns_total, turns_with_evidence, turns_needing_repeat,
low_confidence_words_total) plus the full per-turn detail.
Nothing pooled the evidence: no probability statistics
over a session's evidenced words, no often-missed-word
table (which words fell low, how often, in which turns),
and no lexicon-coverage view (how many low occurrences
the replacement lexicon already answers). That mattered
for VX-11 itself: often-missed words are replaced after
transcription, but without a frequency view nobody -
host or user - could learn WHICH words are often missed
except by reading every turn word by word, so the P-105
lexicon could not be curated from evidence.

## 2. What lands
- src/runmal/voice/mishearing.py (extended) - the pure
  aggregate layer, derived ONLY from turn_mishearing
  views (one truth source):
  - mishearing_aggregate(session, pairs=None): pooled
    probability statistics over every evidenced word
    (count, mean, min, and nearest-rank p50/p95 via the
    house runmal.voice.metrics.percentile - the same
    function P-110 latency uses); words_total /
    words_low / words_ok and low_rate; the
    frequent_low_words table (group key, count, turns
    ascending and unique, min/mean probability,
    has_replacement / replacement), sorted by count
    descending then word ascending; lexicon_coverage
    (low / covered / uncovered occurrences, distinct
    low words, covered and uncovered word keys);
    and the per-backend split (words, words_low,
    mean probability per stt_backend, backends with
    no evidenced words omitted).
  - session_mishearing_report(session, pairs=None):
    the light read surface - exactly the totals
    session_mishearing already states, plus the
    aggregate, and NO per-turn detail.
  - session_mishearing gains the same aggregate block
    additively under the key aggregate; every existing
    field is untouched.
- src/runmal/voice/mishearing_router.py (extended) -
  GET /voice/sessions/{session_id}/mishearing-report:
  the report view, owner-scoped exactly like the
  sibling mishearings road (unknown or foreign session
  answers 404; existence never leaks), with lexicon
  pairs from the same ReplacementStore.
- src/runmal/voice/__init__.py - the module-map line
  for mishearing names the P-114 report surface.
- Battery tests/test_p114_voice_mishearing_report.py
  (18 tests).

## 3. Laws held
- One truth source: every number derives from
  turn_mishearing, which owns the threshold, the bands
  and the per-word views. The aggregate never re-bands
  a word and never recomputes a probability; it pools
  what the per-turn views already state. The battery
  pins report aggregate == session view aggregate ==
  direct aggregate.
- No evidence is not zero: a session (or turn) with no
  recorded words reports has_confidence_evidence False,
  zero evidenced words, and None for every statistic -
  never a 0.0 mean, never all-confident. (An evidenced
  all-confident session honestly reports low_rate 0.0.)
- Word grouping uses the lexicon law: the group key is
  the punctuation-stripped, lower-cased core (the same
  _split_affixes split apply_replacements and
  normalize_misheard use), so a frequent-low-word key
  IS the key a lexicon entry must use. A token with no
  core groups under its lower-cased text.
- Data only: no dialogue, no responder call, no chat
  message, no transcript mutation (P-075 + P-105 law) -
  the battery pins transcripts unchanged after every
  view. No new store, no migration (head stays 0041,
  pinned in the battery).

## 4. Honest limitations
- Confidence stays the backend's own uncalibrated
  estimate (fake ears report 1.0; pooled statistics
  inherit that - they describe the recorded evidence,
  not hearing truth).
- The aggregate describes ONE session; no cross-session
  or install-wide roll-up is built. The repeat-request
  digest/aging candidate weighed in the scout stays
  open likewise.
- Grouping is whole-word only, like the lexicon: no
  stemming, no fuzzy match.
- No UI renders the report in this slice.

## 5. Battery
tests/test_p114_voice_mishearing_report.py - 18 tests:
the no-evidence law pins (empty session, evidence-free
turns), pooled statistics including nearest-rank
p50/p95, the all-confident low_rate distinction,
frequent grouping across case and punctuation with
counts / turns / min / mean and the sort law, the
no-core token grouping, coverage at occurrence and
distinct level with and without a lexicon, the
per-backend split and its empty-turn omission, report
totals equal to the session view with no turns key,
the cross-view consistency pins, transcript
non-mutation, the HTTP report flow, the mishearings
road's additive aggregate, unknown / foreign 404, and
the 0041 migration pin. Neighbour and full-suite
counts are recorded from the run logs in
hidden_files/P114_EVIDENCE.md, never estimated here.
