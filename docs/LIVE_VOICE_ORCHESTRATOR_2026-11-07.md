# P-102 — Live Voice Orchestrator (Part VII, Voice the Voxta Way)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VII only its part line — "VII | Voice,
the Voxta Way | P-101 – P-116" — and no per-slice entries. This
slice's scope is therefore DERIVED, not roadmap-verbatim, from
in-tree sources only: P-101's slice doc (its section 5 honest
limitations), the Voxta census (VX-09 the real-time voice core
loop; VX-65 the per-chat inspector), VOICE_ARCHITECTURE sections
2/4/8/13, and the founding S501–S514 voice seams as they stand.
P-101 named three limitations as the road ahead: L1 no live
orchestrator wired into the app process; L2 session turns not
projected into chat messages; L3 the P-091 citizens
unregistered in the running app.

P-102 takes L1. L2 has nothing to project until live turns
exist (P-101 already persists the truth record; projection is
a history decision that should consume recorded live turns).
L3 is not a defect to fix here: P-091 states registration is
deliberately host-explicit and create_app stays registry-empty
by design — the live host drives the founding seams directly.
The keeper reviews this derived scope at banking.

Base: f722ffe (P-100 banking record). P-101 is NOT in this
base; it banks ahead of this slice and the keeper reconciles.
This slice therefore depends on P-101 at RUNTIME only: the new
live module imports only founding modules, consumes the
session citizen duck-typed, and the HTTP router imports the
session store lazily. Migration: NONE — head stays 0041.

## 1. What landed

- src/runmal/voice/orchestrator.py — ONE additive public
  method, speak_text(text) -> TurnRecord: the tail of a mic
  turn without STT/responder (SYNTHESIZING → SPEAKING →
  LISTENING; interruption and error recovery identical to the
  mic road). No existing behaviour changes.
- src/runmal/voice/live.py (new) — the live host:
  build_live_orchestrator (assembles one session's
  orchestrator from its settings snapshot through the registry
  factories, with the S508 PlaybackLedger subscribed to the
  chunk hooks) and LiveVoiceController (owns the live
  orchestrators of one app process, keyed by session).
- src/runmal/voice/live_router.py (new) — the HTTP surface
  (section 3), included by app.py on the founding road.
  voice/router.py is NOT touched by this slice.
- src/runmal/app.py — create_app constructs the controller,
  attaches it to the app, and includes the live router at
  /api/v1 behind the same bearer gate. Construction builds NO
  backend — backends build per session start, so boot cost
  and boot failure surface are unchanged.
- src/runmal/voice/__init__.py — one docstring line for the
  live modules (FLAGGED for the keeper's union check against
  P-101's one line for session.py; disjoint lines).
- Battery: tests/test_p102_live_voice.py.

## 2. The live host

build_live_orchestrator(settings, *, responder, tts, stt,
playback, segmenter, clock): explicit seams win; otherwise
build_tts_backend / build_stt_backend construct the REAL
backend named by the session's resolved snapshot, and
BackendUnavailable is wrapped in LiveVoiceError and surfaced —
never a silent fake, never an install. The VoiceInfo follows
the snapshot (the default voice carries its S512 prompt text).
The default segmenter is VadSegmenter(EnergyVadModel()) — the
model the founding benchmark itself drives; a deployment
injects a Silero-backed segmenter through the same parameter.
Playback has NO default: a build without an explicit sink
refuses plainly.

LiveWiring is the as-built record, as data: backend keys,
road labels ("fake" iff the BUILT backend's key names a fake,
else "registry"), the VAD model label, the responder label,
voice id + language. Labels follow the wiring, never upgraded.

The controller's roads:
- start(session, store?) — refuses a stopped session and a
  session already live; publishes the orchestrator to
  app.state.voice_session, the slot the founding /voice/status
  route has always read (until now it always read LISTENING/0
  because nothing ever set it).
- speak(session_id, text) — validates non-empty text BEFORE
  any synthesis, runs speak_text, persists the turn.
- feed_frames(session_id, frames) — the in-process mic road a
  capture loop calls: drives the orchestrator; every NEW
  completed turn persists in order. (HTTP carries no raw
  audio in this slice.)
- interrupt(session_id) — the orchestrator's one barge-in
  funnel, passed through.
- stop(session_id, note?) — removes the host; with a bound
  store it also stops the session citizen (first stop wins)
  and saves it; the app slot clears. Stopping a session that
  is not live is an error, not a silent no-op.
- status(session_id?) — the inspectable answer: per live
  session {session_id, chat_id, state, wiring, turns_live,
  turns_recorded} (the VX-65 shape).

Persistence: every completed live turn goes through the
citizen's own road — session.append_orchestrator_turn(record,
heard) with heard = the controller's ledger reconstruction
(ledger evidence present by construction, since the ledger
subscribed before the turn ran) — then store.save_session.
A per-host watermark counts orchestrator turns already
recorded, so batches and repeated speaks never double-record.
If the citizen's road refuses (the session was stopped
underneath the controller), the host drops and the refusal
surfaces: a stopped session cannot stay live.

## 3. HTTP surface (founding road, bearer-gated)

- POST /api/v1/voice/sessions/{id}/live/start → 201, the
  live status. Unknown session 404; stopped or already-live
  409; a backend or playback that cannot be built 503 with
  the plain reason (on a tree without P-101's session module,
  503 says so).
- GET /api/v1/voice/sessions/{id}/live → the live status;
  404 unknown session; 200 with live=false for a session
  that exists but is not live.
- POST /api/v1/voice/sessions/{id}/live/speak {text} → 201,
  the persisted turn. Unknown 404; not live 409; empty text
  422 (validated before any synthesis).
- POST /api/v1/voice/sessions/{id}/live/interrupt →
  {interrupted, ...status}.
- POST /api/v1/voice/sessions/{id}/live/stop {note?} → the
  final status (live=false), the citizen stopped via the
  store.
The store resolves per request: app.state.live_session_store
when a host or test sets it, else P-101's VoiceSessionStore
over the data dir (lazy import). The router's default playback
factory opens the app provider's sink for the resolved
companion_output role, falling back to user_playback; an
unassigned or remap-required role refuses with the RoleMap
truth (REMAP_REQUIRED is surfaced, never a silent default
device — INV-022).

## 4. Honesty rules

- Fakes only where a test wires them: nothing in live.py
  imports a fake backend; production defaults build real
  registry backends from the snapshot and refuse when a
  runtime is not installed.
- The default responder is unavailable_responder, labelled
  "unavailable", and it raises: the generation stack is async
  and DB-bound, and wiring it as the synchronous responder is
  a later slice's design. A mic turn without a responder runs
  through ERROR_RECOVERY and the error turn is recorded and
  persisted like any other — never a fabricated reply.
- /voice/status truth: once a session is live the founding
  route reports the live orchestrator's real state and turn
  count; after stop the slot clears and it reads LISTENING/0
  again. Its shape is unchanged.
- Live hosts are process state and die with the process;
  sessions and recorded turns persist in P-101's store and a
  session can be started live again after a restart.

## 5. Honest limitations

- No raw-audio HTTP transport and no browser capture wiring:
  the mic road is the in-process feed_frames / run_capture
  host road; streaming audio to the app is a later slice.
- The synchronous responder seam is injected, not yet the
  real generation stack (see section 4); speak turns — the
  companion speaking a known text — are fully live today.
- L2 (turns projected into chat messages) and L3 (P-091
  citizen registration) remain open exactly as P-101 left
  them; this slice neither projects turns nor registers
  citizens.
- One app.state.voice_session slot exists (the founding
  shape): with several sessions live, the slot holds the
  most recently started orchestrator; per-session truth is
  always available through status / the live routes.

## 6. Battery

tests/test_p102_live_voice.py — builder honesty (explicit
playback required, registry build + wiring labels,
BackendUnavailable wrapped, unavailable-responder label,
ledger subscription), the speak_text road (state sequence,
counts, empty text, mid-speak interruption, TTS failure
recovery), the controller against a labelled test-double
session + store implementing the P-101 protocol in shape
(start refusals, speak/feed persistence with ledger-backed
heard truth, honest error turns, stop semantics, the app
slot), the HTTP flow (start → founding status fills → speak
→ interrupt → stop; 404/409/422/503 roads; boot + the 0041
pin), and one guarded real-citizen round trip
(importorskip — skipped on a tree without P-101, live after
reconciliation). Neighbour and full-suite counts are
recorded from the run logs in hidden_files/P102_EVIDENCE.md,
never estimated here.
