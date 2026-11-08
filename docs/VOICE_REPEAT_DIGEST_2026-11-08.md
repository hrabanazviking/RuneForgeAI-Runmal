# Voice Repeat-Request Digest & Aging - P-115 (Part VII, DERIVED scope)

Part VII's fifteenth slice. The roadmap gives Part VII only
its part line ("Voice, the Voxta Way", P-101..P-116; P-116
is the gate) - no verbatim P-115 entry exists, and this
doc says so plainly. The scope is DERIVED from Runmal's own
in-tree record, the way P-101..P-114 were: P-114's scout
weighed this candidate second and left it named-open -
"what is missing is only cross-session roll-up and
wall-clock aging (acknowledged_at / recorded_at are
stored, so aging IS derivable with an injected now)".
P-115 is that slice. The keeper reviews this derived
scope at banking.

## 1. The gap, verified at the P-113 base (93229da)

- The only repeat-request surfaces were per-session:
  session_repeat_requests(session) and
  GET /voice/sessions/{id}/repeat-requests. A host
  watching many sessions had to poll every session id
  it happened to know; no cross-session roll-up existed.
- Aging was underivable by any client: every turn
  persists recorded_at and every acknowledgement
  persists acknowledged_at, but P-108's per-request
  view did not even carry recorded_at.
- P-114 scout's stated cost - an aging view "needs
  invented age buckets/thresholds" - is answered by
  design: ages are reported as plain arithmetic
  seconds with no bucket and no threshold (section 3).

Items weighed and NOT taken (scout, hidden record):
L3 auto-registration of the P-091 voice citizens is a
deliberate host-explicit LAW, not a gap (P-112/P-113
record it; this slice registers nothing); the VX-12
engine half still has no backend seam (affects.py:
consumed: False on every surface; no backend reads an
affect), so it stays declined as P-108..P-114 left it.

## 2. What landed

- src/runmal/voice/repeat_requests.py (extended) -
  repeat_digest(sessions, pairs=None, store=None, *,
  now=None): the cross-session roll-up. Sessions emit
  in VoiceSessionStore order (created_at, session_id)
  regardless of input order. Counts are the per-session
  P-108 views' sums BY CONSTRUCTION (the digest calls
  session_repeat_requests per session; the battery pins
  the agreement), so the digest can never disagree
  with the poll view, P-105's truth, P-106's receipt
  or P-107's rendering. turn_repeat_request gains
  recorded_at additively - the turn record's own stamp,
  the timestamp its requests age from; no existing key
  changes meaning.
- src/runmal/voice/repeat_router.py (extended) -
  GET /voice/repeat-requests/digest: OWNER-SCOPED, like
  the per-session P-108 roads - it rolls up only the
  caller's sessions, so no other owner's session, chat
  or pending turn is ever named. (The P-111
  housekeeping roads stay install-wide: they expose
  only counts and inert ids of the install-wide
  acknowledgement store; the digest names live
  sessions, so it follows the P-108 road.) A pure read
  against the wall clock.
- src/runmal/voice/__init__.py - module-map line.
- tests/test_p115_voice_repeat_digest.py - new battery.

## 3. Aging, stated plainly

Three stat blocks, one shape {count, without_count,
oldest_seconds, newest_seconds, mean_seconds}:
pending_age_seconds (now - recorded_at over pending
requests), acknowledged_age_seconds (now -
acknowledged_at), acknowledgement_delay_seconds
(acknowledged_at - recorded_at). now is INJECTED
(datetime, ISO string, or None for the wall clock);
generated_at echoes it. A stamp that is missing,
unparseable, or after now (clock skew) yields NO age:
the item is counted in without_count and excluded from
oldest/newest/mean - never clamped, never zero-claimed
(the P-110 negative-span law on wall clock). Naive
stamps are read as UTC; the stores stamp UTC ISO.
The per-session entries carry oldest/newest pending
ages, oldest_pending_recorded_at and
last_acknowledged_at; the flat pending list names every
pending turn (session, chat, turn, recorded_at,
age_seconds-or-None) in session then turn order.

## 4. Honest limitations

- The digest reports how long, never "too long": no
  staleness verdict exists in this slice, and any
  threshold a host wants is the host's own policy.
- Ages inherit the wall clock's honesty: a session
  store written under a skewed clock ages under that
  skew, and future stamps are counted as without-age
  rather than repaired.
- record_turn stamps an empty recorded_at with the
  wall clock by design (P-101), so a missing stamp can
  only arrive via a stored record that lacks the
  field (the loader's default) - the battery builds
  that case the way it can actually exist.
- The digest is a snapshot read, not a subscription:
  a host polls it the way it polled per-session views,
  just once instead of per session. No UI renders it
  in this slice.
- The character half of VX-11's ask - a character
  speaking the repeat request in dialogue - stays
  open on the P-102 responder seam, exactly where
  P-105..P-108 left it; nothing here fabricates
  dialogue (P-075 law). No migration: head stays 0041.
