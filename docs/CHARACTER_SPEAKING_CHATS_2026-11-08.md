# P-166 - Character Speaking Chats: one character current faces across all of its chats, paired with its current voice (Part X, DERIVED)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md) gives Part X only its part-table line - "X | Faces That Speak | P-155 - P-168" - and no verbatim P-166 entry exists anywhere in it. This scope is therefore DERIVED, not roadmap-verbatim, from Runmal own in-tree record only (design: hidden_files/P166_DESIGN.md):

- The banked Part X grid fills every chat-keyed cell - the current face (P-155), the current face + voice (P-157), the kept history (P-158) and the kept history + today voice (P-161) - and, per character, the roster (P-156), the speaking roster (P-159), the current-face chats board (P-160), the kept-history board (P-162) and the speaking-history board (P-163) - and, per owner, the current census (P-164), with the history census (P-165) banking in parallel. The one subject x time x voice cell no surface fills is CHARACTER x CURRENT x SPEAKING: P-160 weighed the speaking board and declined it, P-162, P-163 and P-164 each named it open, and P-165 scout declined it as its cell 4 while naming it a real gap. In every grid row the silent cell lands first and its speaking pairing follows (P-155 to P-157, P-156 to P-159, P-158 to P-161, P-162 to P-163); P-160 pairing is this slice. Nothing answered the character-side present question - for this character, what face is each of its chats currently showing, and in what voice does the character speak?
- The board half has exactly one owner: P-160 (faces/chats.resolve_character_face_chats), which itself composes P-155 presentation truth verbatim per chat under its closed board law. This slice composes P-160 resolver whole, exactly as P-164 composes it - it enumerates nothing itself and invents no second board, presentation or selection law.
- The voice half has exactly one owner: S512 (voice keyed by CHARACTER only, resolved with field-level fallback; a legacy removed backend falls back whole; resolution never errors), with P-109 affect carried as data, consumed False. The voice is stated ONCE at board level: S512 keys voice by character, identical for every row, and repeating it per row would imply per-chat voice records that do not exist.
- Both halves are CURRENT: this board reads no kept history, so the P-161 / P-163 voice_scope: current_only field - which exists to keep a present voice from being claimed for past events - has no past here to guard. Following P-157 / P-159, the two earlier current pairings (neither carries voice_scope), this document carries no voice_scope either; its notes state plainly that the voice is the character current resolution. The current_only law itself is untouched and binds wherever history is involved.
- Precedent: P-160 (the board), P-163 (the voice half verbatim in substance, stated once, paired law), P-159 (per-character current pairing), P-164 (composing P-160 whole).

Base: ceab179f43210938c2e9b772b3ffb5332bf4352e (P-164 banking record; banked P-001..P-164). Migration: NONE - head stays 0041, no 0042. P-165 (face history census, team-03) banks before this slice; the two are disjoint (speaking_chats* vs history_census*).

## What landed

New modules in src/runmal/faces/ - no store, no migration:

- speaking_chats.py - resolve_character_speaking_chats(session, user_id, character_id, *, base_dir=None) -> dict | None, a pure read. None exactly when P-160 board is None (missing, foreign or deleted character - existence never leaks). Otherwise the envelope (schema runmal-p166-character-speaking-chats-v1):
  * character - the character own facts verbatim, carried by P-160 board (character_to_dict via P-160);
  * chats - P-160 board rows whole, in list_chats order: chat_id, title, message_count, presentation_state, current, current_problem, face (the current descriptor named only when that chat is ready, carrying the P-023 content and thumbnail URLs as data). Rows carry NO voice field of any kind;
  * state - the board under the closed SPEAKING_CHATS_STATES law: no_chats / none_ready / some_ready / all_ready - the same strings as P-160 BOARD_STATES under distinct export names, and P-160 own judgement carried, not recomputed;
  * counts - chat_count, ready_count, selection_count, unbound_count, carried from P-160 board own arithmetic;
  * voice - the character CURRENT S512 resolution, composed verbatim in substance exactly as P-157 / P-159 / P-161 / P-163 compose it: state under the closed VOICE_STATES law (profile / profile_fallback / default_voice), profile_exists, stored_backend (the stored row named backend, so a fallback is visible, never silent), tts_backend, voice_id, language, params, and the P-109 affect view whole with consumed False. Stated once, at board level only; never None on a resolved document (a missing profile is the default voice);
  * paired - True exactly when a voice resolved and at least one chat shows a ready face (ready_count > 0): P-157 pairing law at board level. A board whose chats hold selections but none ready never pairs; a voice beside an empty or unready board is stated, never upgraded;
  * notes - five standing honesty notes in fixed order.
- speaking_chats_router.py - GET /faces/speaking-chats?character_id= on the /api/v1 mount: 404 when resolve returns None, 200 the envelope otherwise (every board state is data at 200, never an error).
- faces/__init__.py - subsystem map and exports extended for the speaking-chats surface (additive, after the census entries).
- app.py - speaking-chats router wired under /api/v1 with the local-auth dependency, after the census router.
- tests/test_p166_character_speaking_chats.py - battery (24 tests).

## Declined candidates (each with its reason)

- Owner speaking census (owner x current x speaking): voice is per character under S512, so there is no single owner-level pairing to state; P-164 declined it. Named open.
- Owner speaking-history census (owner x history x speaking): sits on P-165 ground and adds per-character voices; it would blur where the current_only law lives. Named open.
- Per-row voice fields: S512 keys voice by character; a per-row field would imply per-chat voice records that do not exist. Declined.
- A single merged character face: a character has no single current face - selection is per chat (P-160 law). Declined.
- A client stage/renderer surface: no renderer exists in-tree to extend. Named open.
- Generated expression sprites via P-087: a P-087 landing-contract change, not a faces read. Named open.
- Scenario VN stage integration: no record joins scenario cast role names to characters or faces. Named open.
- Portrait animation / lip-sync: no timing, viseme or animation contract exists in-tree. Declined.
- Actual TTS synthesis on this road: a read must not forge a performance. Declined.
- Automatic expression detection from message text: declined ABSOLUTELY (P-092 standing law).
- Playback/scripting execution: declined ABSOLUTELY (P-027 law).
- A new faces store / migration: every fact read already has exactly one owner (P-160 / P-155, S512, P-109); head stays 0041.

## Honest limitations

- Runmal renders nothing here; the board is current-face + current-voice data a client reads and carries no image bytes - a ready face descriptor carries the P-023 content and thumbnail URLs as data.
- A character has no single current face: each row face is named only under P-155 own law for that chat, and the board never collapses its rows into one face.
- The voice is the character current resolution only in the plain sense - it is what S512 resolves today for this character; the board makes no claim about any earlier voice, and it reads no kept history at all. Where history is involved, P-161 / P-163 documents carry the binding voice_scope: current_only law; this current-current pairing follows P-157 / P-159 and carries no voice_scope field.
- The scope is DERIVED, not roadmap-verbatim. The keeper reviews this derived scope at banking.
- Disjointness: P-165 (banking in parallel on team-03) owns faces/history_census.py + faces/history_census_router.py; this slice never touches them. The shared touchpoints (faces/__init__.py, app.py, the clean-room log) are additive at this slice own anchors (after the census entries / router; log appended) and reconcile as pure additive unions at banking, as the P-155..P-164 unions did. P-166 banks after P-165.
