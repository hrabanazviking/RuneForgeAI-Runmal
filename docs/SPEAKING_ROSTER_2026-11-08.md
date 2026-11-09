# P-159 - Speaking roster: face roster + voice resolution for one character (Part X, DERIVED)

Roadmap line: *X | Faces That Speak | P-155 - P-168* - the roadmap gives Part X only its part-table line and NO verbatim P-159 entry exists; this doc says so plainly. Scope is DERIVED from Runmal's own in-tree record only (hidden_files/P159_DESIGN.md): the banked Part X grid (P-155 per-chat presentation, P-156 per-character roster, P-157 per-chat speaking face), P-157's own design naming a per-character chat-less speaking document open, S512 per-character voice profiles, P-109 voice affects, P-092 expression binding, P-023 asset roads. Base d94e2a0 (P-157 banking record; P-001..P-157 banked). **No migration taken - head stays 0041.**

Clean-room: built from the roadmap line and Runmal's own contracts only - P-156's roster document composed whole, S512's resolution and fallback law, P-109's carried-affect truth, P-023's content/thumbnail roads, and the P-155/P-156/P-157 faces pattern (pure-read composition, closed state laws, five standing notes). No SillyTavern or Voxta source was read.

## What landed

`src/runmal/faces/speaking_roster.py` - `resolve_character_speaking_roster(session, user_id, character_id)` returns None for a missing or foreign character (existence never leaks) and otherwise one document (schema `runmal-p159-speaking-roster-v1`) pairing, on their one shared key - the character:

- **The roster half**, composed from P-156's `resolve_character_roster` whole: the character row, the declared set, every entry resolved to a presentation descriptor (name, label, notes, bound, problem, asset facts, renderable, and the P-023 content/thumbnail roads as URL data, present only when bound), the counts, the roster state under the same closed `ROSTER_STATES` law (`ready` / `no_renderable` / `empty_set` / `no_set`), `selection_scope: per_chat`, and the declared default + character avatar named as fallback data, never applied or substituted. No second roster or binding law is invented.
- **The voice half**, composed from S512 verbatim in substance, exactly as P-157 composes it: `resolve_character_voice` for the resolved reference (backend, voice id, language, params) and `get_character_voice` for the stored row, classified under the same closed voice-state law - `profile` (a stored row the resolution used, field-level defaults filling its gaps), `profile_fallback` (a stored row naming a backend outside the known registry - the legacy removed-backend case, where S512 falls the whole reference back to the default), `default_voice` (no stored row at all). The row's named backend rides as `stored_backend` so a fallback is visible, never silent. The P-109 affect view (`affect_from_params` + `affect_view`) rides whole: affect, source, `consumed: False` and the consumption truth. Voice resolution is keyed by character (S512), so no chat is needed for this half.
- **`paired`** - True exactly when the roster state is `ready` and a voice resolved. The halves are independent modalities: a voice resolving while no face is renderable is stated, never upgraded, and neither half is ever substituted for the other.
- **No current face** - the document carries no `current`, `face`, `current_binding` or `chat_id` key. Selection is per chat and always an explicit act (P-092); a chat's current face is P-155's / P-157's document to name.
- **Five standing honesty notes**, fixed order: pairing is data only (no synthesis, no rendering, no lip-sync or animation - no timing contract exists in-tree); this roster names no current face and selects/applies/scans nothing; a voice always resolves and the voice state names how; the affect is carried data with `consumed: False`; pure read - sets, selections and sprite bytes stay with P-092 and P-023, voice rows with S512.

`src/runmal/faces/speaking_roster_router.py` - `GET /faces/speaking-roster?character_id=` on the `/api/v1` mount, wired in `app.py` after the speaking router with the local-auth dependency: 404 for an unknown/foreign character, 200 with the envelope otherwise (every non-ready state is data, never an error).

`src/runmal/faces/__init__.py` - an additive speaking-roster section in the subsystem map, with the banking note: P-158's history modules (in flight on team-01) join it when the keeper banks P-158 -> P-159 in roadmap order; the two wirings are disjoint and reconcile as a pure additive union.

## Honest boundaries

- **No synthesis, no rendering, no lip-sync.** This document names which faces a character could show and which voice it would speak in, as data. Synthesis stays with the voice subsystem's live/session machinery; no timing, viseme or animation contract exists anywhere in-tree, so no synchronisation is claimed or faked.
- **No automatic expression detection** - declined ABSOLUTELY under P-092's standing law; nothing scans message text. **No playback or scripting execution** - declined ABSOLUTELY under P-027.
- **No per-expression voices.** S512 keys voice by character only; no per-expression voice record exists, and inventing one would be a new store and a migration - out of scope for this slice.
- **No new store, no migration.** Every fact read has exactly one owner already: P-092 for sets, S512 for voice rows, P-023 for sprite bytes (never read here).

## Declined candidates (from the design weighing)

Per-chat speaking history (rides P-158's footprint while it is in flight - not disjoint; named open after P-158 banks); a client stage/renderer surface (no renderer exists in-tree; a stage re-wraps P-155/P-156); generated expression sprites via P-087 (it lands kind `background` hardcoded through a live plugin instance the faces/app context does not hold - a P-087 landing-contract change, named open); scenario VN stage integration (no record joins scenario cast role names to characters or faces - named open); portrait animation / lip-sync (no timing contract in-tree - unbuildable honestly today); actual TTS synthesis on this road (a presentation read must not forge a performance).

## Tests

`tests/test_p159_speaking_roster.py` - owner scoping, all four roster states on the pairing axis, all three voice states (including a directly-stored legacy `kokoro-onnx` row falling back whole, and a partial profile staying `profile` with field-level defaults), the carried affect (profile/default sources, `consumed: False`), pairing true/untrue on both axes, the no-current-face law, the pure-read law (P-092 store byte-identical, voice row untouched, no history written), avatar fallback as data, the five notes, the HTTP flow end to end, and the migration-head pins (0041 last, no 0042). Neighbours fence: P-092, P-109, S512 and P-155/P-156/P-157 batteries.
