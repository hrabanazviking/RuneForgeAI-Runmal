# P-160 - Character Face Chats: one character's chats and the face each one currently shows (Part X, DERIVED)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md) gives Part X only its part-table line - "X | Faces That Speak | P-155 - P-168" - and no verbatim P-160 entry exists anywhere in it. This scope is therefore DERIVED, not roadmap-verbatim, from Runmal's own in-tree record only (design: hidden_files/P160_DESIGN.md):

- The banked Part X grid resolves one chat's presentation (P-155), one character's roster (P-156), one chat's face + voice pairing (P-157) and one chat's kept selection history (P-158); P-159 (in flight) takes the per-character speaking roster. The one join no surface makes is character -> its chats. P-092's selections are per chat, so a character with several chats can be showing a different face in each, and nothing in-tree answers the character-side question: which chats does this character have, and what face is each one currently showing?
- The facts all exist with exactly one owner each - chats/service.list_chats (the owner's chats, creation order, message counts), characters/service.get_character (existence law), faces/presentation.resolve_presentation (each chat's face truth under the closed P-155 law). Only the composition was missing. This slice is that composition.
- Precedent: P-156 (compose the owning surface verbatim, closed state law, five notes) and P-158 (compose resolve_presentation verbatim rather than inventing a second binding law).

Base: 1975169349705df1dca6a38c369dd46a3a9100d7 (P-158 banking record; banked P-001..P-158). Migration: NONE - head stays 0041, no 0042.

## What landed

New modules in src/runmal/faces/ - no store, no migration:

- chats.py - resolve_character_face_chats(session, user_id, character_id, *, base_dir=None) -> dict | None, a pure read. None when the character is missing, foreign or deleted (get_character's law - existence never leaks). Otherwise the envelope (schema runmal-p160-character-face-chats-v1):
  * character - character_to_dict verbatim, the character service's own facts;
  * chats - one row per owned chat bound to this character, in list_chats order (creation order); chats bound to other characters and unbound chats never appear. Each row carries the chat's own facts (chat_id, title, message_count) plus P-155's presentation truth composed verbatim for that chat: presentation_state, current (with provenance), current_problem, and face - the P-155 descriptor, named only when that chat's state is ready, else None. The full entries roster is not restated per chat; it is P-155's / P-156's document.
  * state - the board under the closed BOARD_STATES law: no_chats (the character has no chats), none_ready (chats exist, none shows a ready face), some_ready (some ready, some not), all_ready (every chat shows a ready face);
  * counts - chat_count, ready_count, selection_count (chats whose current is not None), unbound_count (chats in current_unbound);
  * notes - five standing honesty notes in fixed order.
- chats_router.py - GET /faces/chats?character_id= on the /api/v1 mount: 404 when resolve returns None, 200 the envelope otherwise (every board state is data at 200, never an error).
- faces/__init__.py - subsystem map and exports extended for the chats surface (additive).
- app.py - chats router wired under /api/v1 with the local-auth dependency, after the history router.
- tests/test_p160_character_face_chats.py - battery (17 tests).

## Declined candidates (each with its reason)

- An owner-wide face census: aggregates what P-156 names per character; P-158's design weighed it and the history axis won that slice. It remains named open (a natural P-168 gate companion); the character -> chats join was consumed by nothing and is the missing cell of the Part X grid.
- A client stage/renderer surface: no renderer exists in-tree; a single-chat stage re-wraps P-155, and this board is the multi-chat data such a stage would stand on. Named open.
- A speaking board (this board plus each chat's voice): the voice half is per character (S512) and identical on every row; the character's voice is P-157's / P-159's document to name. Declined for this slice.
- Per-chat history inlined on the board: history is P-158's own document (a kept window of up to 100 events per chat); the board names current faces, P-158 names the past. Declined.
- Scenario VN stage integration: no record joins cast roles to characters or faces. Named open.
- Generated expression sprites via P-087: re-kinding is a P-087 contract change, not a faces read. Named open.
- Portrait animation / lip-sync: no timing contract exists in-tree. Declined.
- Automatic expression detection from message text: declined ABSOLUTELY (P-092 standing law).
- Playback/scripting execution: declined ABSOLUTELY (P-027).
- A new faces store / migration: every fact read has exactly one owner already; head stays 0041.

## Honest limitations

- Runmal renders nothing here; the board is data a client reads and carries no image bytes.
- A character has no single current face: the board never collapses its chats into one face, and a chat's face is named only under P-155's own law for that chat.
- The scope is DERIVED, not roadmap-verbatim. The keeper reviews this derived scope at banking.
- Disjointness: P-159 (in flight on team-02) owns faces/speaking_roster.py + speaking_roster_router.py; this slice never touches them. The shared touchpoints (faces/__init__.py, app.py) are additive at different anchors and reconcile as pure additive unions at banking, as the P-155..P-158 unions did. P-160 banks after P-159.
