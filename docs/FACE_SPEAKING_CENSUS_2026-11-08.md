# P-167 - Face Speaking Census: one owner's current faces across every character and chat, each character row carrying its own current voice (Part X, DERIVED)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md) gives Part X only its part-table line - "X | Faces That Speak | P-155 - P-168" - and no verbatim P-167 entry exists anywhere in it. This scope is therefore DERIVED, not roadmap-verbatim, from Runmal's own in-tree record only (scout + design: hidden_files/P167_SCOUT.md / P167_DESIGN.md):

- The banked Part X grid fills every chat-keyed cell - the current face (P-155), the current face + voice (P-157), the kept history (P-158) and the kept history + today's voice (P-161) - and every character-keyed cell: the roster (P-156), the speaking roster (P-159), the current-face chats board (P-160), the kept-history board (P-162) and the speaking-history board (P-163) - and, per owner, the current census (P-164) and the history census (P-165) stand silent-only, while P-166 (character speaking chats, banking in parallel, not on this base) takes the last character speaking cell. The owner row's two speaking cells stand named open since P-164, contested by one objection, restated in P-165's banked record as unanswered: voice is per character under S512, so an owner speaking census would blur per-character voice into one pairing. P-167 is the last slice before the P-168 Part X gate.
- CHOSEN: OWNER x CURRENT x SPEAKING, in the one shape that answers the blur objection BY CONSTRUCTION. Each character row composes P-164's census row verbatim in substance (P-160's board) PLUS that character's OWN current S512 voice resolution, composed verbatim in substance exactly as P-157 / P-159 / P-161 / P-163 compose it, PLUS that row's OWN paired flag. Voice appears ONLY inside character rows; the census envelope carries no voice, no paired, no voice_scope and no face, so there is no owner-level voice for any row's voice to blur into. The census state stays P-164's face axis. If any of those construction lines could not hold, this cell would have been declined instead; each line is battery-pinned.
- DECLINED, the owner speaking-HISTORY census: constructible under the same per-row discipline, but the grid takes current speaking before history speaking in every row so far, the per-row discipline must first be proven where both halves are current and no past can be mis-dressed, and only one contested cell can land before the gate. It remains OPEN, named here and in the design for the P-168 gate record to carry honestly - Part X closes with one owner speaking cell unmade, and the gate must say so.
- DECLINED, an owner roster census (not a gap the record ever named; it would duplicate P-156 / P-159 ground) and an index-only honesty slice (the P-168 gate itself is that instrument). Full weighing in hidden_files/P167_SCOUT.md.
- Both halves are CURRENT, so - following P-157 / P-159 / P-166 - this document carries no voice_scope: current_only exists to keep a present voice from being claimed for past events, and this census reads no past. The law is untouched and binds wherever history is involved.
- Precedent: P-164 (the census composition), P-163 / P-166 (the voice half verbatim in substance, stated once per character subject, the paired law), P-159 (per-character current pairing).

Base: 6cea18798a245399a35cd93b725669e814012b1d (P-165 banking record; banked P-001..P-165). Migration: NONE - head stays 0041, no 0042. P-166 banks before this slice; the two are disjoint (speaking_census* vs speaking_chats*).

## What landed

New modules in src/runmal/faces/ - no store, no migration:

- speaking_census.py - resolve_face_speaking_census(session, user_id, *, base_dir=None) -> dict, a pure read. It never returns None: the subject is the caller themselves, so there is no foreign subject whose existence could leak, and an owner with nothing gets the honest empty census. Otherwise the envelope (schema runmal-p167-face-speaking-census-v1):
  * characters - one row per owned character, in list_characters order (creation order); a deleted character never appears, and another owner's characters never appear. Each row composes P-164's census row verbatim in substance - character_id, character (character_to_dict verbatim, carried by the board), board_state (the board's own state under P-160's BOARD_STATES), chats (the board's rows whole - chat_id, title, message_count, presentation_state, current, current_problem, face), chat_count, ready_count, selection_count, unbound_count - PLUS voice (that character's own current S512 resolution: state under the closed VOICE_STATES law - profile / profile_fallback / default_voice - profile_exists, stored_backend so a fallback is visible never silent, tts_backend, voice_id, language, params, and the P-109 affect view whole with consumed False) and paired (True exactly when that row's voice resolved and that row's ready_count > 0). No chat row carries any voice field.
  * state - the census under the closed SPEAKING_CENSUS_STATES law, the face axis only, judged exactly as P-164 judges: no_characters (the owner has no characters), no_chats (characters exist, none has any chat), none_ready (chats exist, none shows a ready face), some_ready (some chats ready, some not), all_ready (every chat shows a ready face). No voice state exists at census level: voice always resolves for an existing character, so one would be vacuous.
  * counts - character_count, characters_with_chats_count, chat_count, ready_count, selection_count, unbound_count, each summed from the P-160 boards' own arithmetic, PLUS paired_character_count - the count of rows whose own paired flag holds, carrying no voice value.
  * notes - five standing honesty notes in fixed order (see the module).
- speaking_census_router.py - GET /faces/speaking-census on the /api/v1 mount: always 200 the envelope (every census state is data, never an error; there is no id parameter and nothing to 404).
- faces/__init__.py - subsystem map and exports extended for the speaking-census surface (additive, after the history-census entries; the module's voice constants are not re-exported - they stay with the speaking module's exports, as P-163's do).
- app.py - speaking-census router wired under /api/v1 with the local-auth dependency, after the history-census router, in its own include block.
- tests/test_p167_face_speaking_census.py - battery, authored fresh.

## Declined candidates (each with its reason)

- Owner speaking-history census (owner x history x speaking): named OPEN for the P-168 gate - the current speaking pairing lands first, as in every grid row; the history pairing additionally carries the current_only hazard at owner scale and must not be the rushed second half of the last pre-gate slice.
- Census-level voice or paired keys: that IS the blur the P-164 objection names - declined by construction, and the battery pins their absence.
- Per-chat voice fields: S512 keys voice by character; a per-chat field would imply per-chat voice records that do not exist. Declined.
- An owner roster census: never named open in the record; duplicates P-156 / P-159 ground. Declined for this slice.
- A merged owner-wide chat or event stream: invents an ordering no owner recorded. Declined.
- A client stage/renderer surface: no renderer exists in-tree to extend. Named open.
- Generated expression sprites via P-087: a landing-contract change, not a faces read. Named open.
- Scenario VN stage integration: no record joins scenario cast roles to characters or faces. Named open.
- Portrait animation / lip-sync: no timing contract in-tree. Declined.
- Actual TTS synthesis on this road: a read must not forge a performance. Declined.
- Automatic expression detection from message text: declined ABSOLUTELY (P-092 standing law).
- Playback/scripting execution: declined ABSOLUTELY (P-027 law).
- A new faces store / migration: every fact read already has exactly one owner (P-160 / P-155, S512, P-109); head stays 0041.

## Honest limitations

- Runmal renders nothing here and synthesizes nothing; the census is current-face + per-character current-voice data a client reads and carries no image bytes - a ready face's descriptor carries the P-023 content and thumbnail URLs as data.
- There is no owner-wide face and no owner-wide voice: each chat's face is named only under P-155's own law for that chat, inside its character's row, and each voice is named only inside its own character's row.
- The census is current only: it reads no kept history and claims no earlier voice for any character. The owner speaking-history census remains open for the P-168 gate to record.
- The scope is DERIVED, not roadmap-verbatim. The keeper reviews this derived scope at banking.
- Disjointness: P-166 (banking in parallel on team-01) owns faces/speaking_chats.py + faces/speaking_chats_router.py and P-165 owns faces/history_census.py + faces/history_census_router.py; this slice never touches any of them. The shared touchpoints (faces/__init__.py, app.py, the clean-room log) are additive at this slice's own anchors (after the history-census entries / router; log appended) and reconcile as pure additive unions at banking, as the P-155..P-166 unions did. P-167 banks after P-166.
