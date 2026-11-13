# P-110 — Voice Turn Latency Evidence (Part VII, Voice the Voxta Way)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VII only its part line — "VII | Voice,
the Voxta Way | P-101 – P-116" — and no per-slice entries. This
slice's scope is therefore DERIVED, not roadmap-verbatim, from
in-tree sources only: VOICE_ARCHITECTURE section 2 (transitions
are logged with monotonic timestamps for latency measurement)
and section 10 (the metrics to record; p50/p95 reporting), the
S505 orchestrator's clock-stamped transition log, S510's
percentile, and the P-101 session citizen — whose persisted
turns carried no latency evidence at all. The keeper reviews
this derived scope at banking.

Base: 462a675 (P-107 banking record). Migration: NONE — head
stays 0041 (see section 4).

## 1. What landed

- src/runmal/voice/latency.py (new), pure views:
  turn_durations derives one turn's durations ONLY from the
  orchestrator transitions stamped with that turn_id —
  stt_seconds (FINALIZING_STT→THINKING), response_seconds
  (THINKING→SYNTHESIZING), synth_to_first_audio_seconds
  (SYNTHESIZING→SPEAKING), playback_seconds (SPEAKING→ the
  turn's closing transition), turn_seconds (first→last stamp
  of the turn). A duration appears only when both endpoints
  were stamped; a negative span is dropped, never clamped.
  turn_latency_view / session_latency_view shape the
  persisted evidence: per-turn evidence flags plus the
  aggregate {count, p50, p95} per duration key via S510's
  own percentile — imported, never reimplemented.
  clean_durations is the tolerant stored-read: known keys,
  finite numbers ≥ 0 only; anything else is dropped.
- src/runmal/voice/session.py — VoiceTurnRecord gains
  durations (default empty = NO evidence, never zeros).
  to_dict carries it additively; from_dict reads it through
  clean_durations (a stored session never bricks).
  from_orchestrator and append_orchestrator_turn accept the
  transition log and derive at record time.
- src/runmal/voice/live.py — the live host's persist road
  passes its orchestrator's transitions into the citizen's
  append road (one additive argument), so live speak and mic
  turns persist their evidence through the store.
- src/runmal/voice/router.py — GET /voice/sessions/{id}/
  latency on the founding road (404 unknown session, the
  router's own session law); session payloads carry turn
  durations additively through the record's to_dict.
- tests/test_p102_live_voice.py — the labelled session
  double's append road accepts the new transitions argument
  (it ignores it, exactly as a shape double should); no
  assertion in that battery changed.
- Battery tests/test_p110_voice_latency.py.

## 2. Laws held

- One truth source: the orchestrator's own transition
  stamps. No wall clock is read for evidence, no stage is
  estimated, nothing is zero-filled.
- response_seconds is the whole responder call as stamped —
  generation duration, NOT time-to-first-token; the first
  token is never stamped and is never claimed, here or in
  any view.
- Evidence-or-nothing: a manually recorded turn (the P-101
  HTTP road has no orchestrator) carries empty durations
  and the views report has_latency_evidence False — the
  absence is data, not a silent clean bill.
- Content and heard-truth laws unchanged: durations are
  timing evidence about a turn, never text evidence.

## 3. Items weighed and NOT taken

Recorded in full in the scout (hidden_files/P110_SCOUT.md):
VX-12's engine half (P-109 took the carried-data step; no
backend affect seam exists), VX-13 narrator (scenarios are
file-interop models only; no narration taxonomy consumer
honestly exists), the character-asks half of the repeat
request (P-102 responder seam), P-108's limitations (event
vocabulary closed by law; per-host acks would weaken its
do-not-ask-twice point), L3 P-091 registration (deliberate
host-explicit law, no new evidence), the generation bridge
behind live.py's seam (no bounded non-hollow part), P-104's
by-design items and P-107's limitations (by design /
client scope), and feeding the founding /voice/status
global MetricsCollector from the live host (a process-global
second truth that dies on restart and mixes all chats —
the persisted per-session record is the citizen-shaped fix).

## 4. Honest limitations

- Stage coverage is the transition log's coverage: VAD
  speech-on latency, endpoint hangover and LLM TTFT (all
  section 10) are not stamped per turn and stay unrecorded;
  interruption detection→stop is not derivable (interrupt()
  stamps no turn_id) and is not claimed.
- The founding /voice/status global MetricsCollector
  remains unfed, exactly as banked — named here, not
  silently half-wired.
- Durations ride the orchestrator's injected clock: real
  elapsed seconds under the production monotonic clock;
  under a test clock, the test's own. The source field
  (orchestrator_transitions) names the origin either way.
- Speak turns carry no STT/response stages because they
  take none; their evidence is partial by construction and
  reads as such.

## 5. Battery

tests/test_p110_voice_latency.py — 16 tests: derivation
(full chain exact spans, speak-turn partial stages, missing
endpoint absence, other-turn isolation, negative-span drop,
direct-orchestrator derivation), the stored-read cleaner,
persistence (from_orchestrator with/without transitions,
round-trip + legacy shape, malformed entries never brick),
the live flow (speak + mic turns persist durations through
the store, reloaded), the views (evidence flags, exact
aggregate percentiles over a known series), the HTTP road
(payload carries durations, /latency view, unknown-session
404, manual turn reports no evidence), and the 0041 pin.
Neighbour and full-suite counts are recorded from the run
logs in hidden_files/P110_EVIDENCE.md, never estimated.
