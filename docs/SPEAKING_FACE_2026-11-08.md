# P-157 - Speaking face: face + voice resolution for one chat (Part X, DERIVED)

Roadmap line: *X | Faces That Speak | P-155 - P-168* - the roadmap gives Part X only its part-table line and NO verbatim P-157 entry exists; this doc says so plainly. Scope is DERIVED from Runmal's own in-tree record only (hidden_files/P157_SCOUT.md / P157_DESIGN.md): the part title itself (the faces P-155 and P-156 resolve are silent - neither touches voice), S512 per-character voice profiles, P-109 voice affects, P-092 expression inspection, P-023 asset roads. Base 8824e95 (P-154 banking record, PART IX COMPLETE). **No migration taken - head stays 0041.**

Clean-room: built from the roadmap line and Runmal's own contracts only - P-092's inspect surface and explicit-selection law, S512's resolution and fallback law, P-109's carried-affect truth, P-023's content/thumbnail roads, and the P-155/P-156 faces pattern (pure-read composition, closed state law, five standing notes). No SillyTavern or Voxta source was read.

## What landed

`src/runmal/faces/speaking.py` - `resolve_speaking_face(session, user_id, chat_id)` returns None for a missing or foreign chat (existence never leaks) and otherwise one document (schema `runmal-p157-speaking-face-v1`) pairing, on their one shared key - the chat's bound character:

- **The face half**, composed from P-092 `inspect_state` verbatim in substance and classified under the same closed five-state law P-155 uses (`ready` / `current_unbound` / `no_selection` / `no_set` / `no_character`, with `not_declared` for a selection outliving its set). `current` rides verbatim with its provenance; `face` names the current entry's descriptor (the P-155 shape: name, label, notes, bound, problem, asset facts, renderable, and the P-023 content/thumbnail roads as URL data) only when the state is `ready`, else None. The full entries roster is not restated - it is P-155's / P-156's document; this document names the face that would speak.
- **The voice half**, composed from S512 verbatim: `resolve_character_voice` for the resolved reference (backend, voice id, language, params) and `get_character_voice` for the stored row, classified under a closed voice-state law - `profile` (a stored row the resolution used, field-level defaults filling its gaps), `profile_fallback` (a stored row naming a backend outside the known registry - the legacy removed-backend case, where S512 falls the whole reference back to the default), `default_voice` (no stored row at all). The row's named backend rides as `stored_backend` so a fallback is visible, never silent. The P-109 affect view (`affect_from_params` + `affect_view`) rides whole: affect, source, `consumed: False` and the consumption truth.
- **`paired`** - True exactly when the face state is `ready` and a voice resolved. The halves are independent modalities (S512 doctrine: voice selection is never the chat backend and never derived from the face): a voice resolving while the face is unbound is stated, never upgraded, and neither half is ever substituted for the other.
- **Five standing honesty notes**, fixed order: pairing is data only (no synthesis, no rendering, no lip-sync or animation - no timing contract exists in-tree); selection stays P-092's explicit act and this read selects/applies/stores/scans nothing; a voice always resolves and the voice state names how; the affect is carried data with `consumed: False`; a character can speak without a ready face.

`src/runmal/faces/speaking_router.py` - `GET /faces/speaking?chat_id=` on the `/api/v1` mount, wired in `app.py` after the vision router with the local-auth dependency: 404 for an unknown/foreign chat, 200 with the envelope otherwise (every non-ready state is data, never an error).

`src/runmal/faces/__init__.py` - the subsystem map for this third of the package, with the banking note: P-155's `presentation` and P-156's `roster` modules join it when the keeper banks P-155 -> P-156 -> P-157 in roadmap order.

## Honest boundaries

- **No synthesis, no rendering, no lip-sync.** This document names which face would be seen and which voice would be heard, as data. Synthesis stays with the voice subsystem's live/session machinery; no timing, viseme or animation contract exists anywhere in-tree, so no synchronisation is claimed or faked.
- **No automatic expression detection** - declined ABSOLUTELY under P-092's standing law; nothing scans message text. **No playback or scripting execution** - declined ABSOLUTELY under P-027.
- **No new store, no migration.** Every fact read has exactly one owner already: P-092 for sets/selections, S512 for voice rows, P-023 for sprite bytes (never read here).

## Declined candidates (from the design weighing)

A client stage/renderer surface (no renderer exists in-tree; a single-face stage re-wraps P-155 and a multi-face stage has no persisted truth - chats bind one character, P-132 refuses group rooms, group chat is in-memory); generated expression sprites via P-087 (it lands kind `background` hardcoded through a live plugin instance the faces/app context does not hold - a P-087 landing-contract change, named open); scenario VN stage integration (no record joins scenario cast role names to characters or faces - named open); portrait animation / lip-sync (no timing contract in-tree - unbuildable honestly today); actual TTS synthesis on this road (a presentation read must not forge a performance); a per-character chat-less speaking document (the roster axis is P-156's; the speaking face is a chat fact - named open).

## Tests

`tests/test_p157_speaking_face.py` - owner scoping, all five face states on the pairing axis, all three voice states (including a directly-stored legacy `kokoro-onnx` row falling back whole, and a partial profile staying `profile` with field-level defaults), the carried affect (profile/default sources, `consumed: False`), pairing true/untrue on both axes, the pure-read law (P-092 store byte-identical, voice row untouched, no history written), the five notes, the HTTP flow end to end, and the migration-head pins (0041 last, no 0042). Neighbours fence: P-092, P-109, S512 and P-117 batteries. The P-155 battery is absent on this base and runs at banking, after P-155 lands.
