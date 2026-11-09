# P-165 - Face History Census: one owner's kept face history across every character and chat (Part X, DERIVED)

- The roadmap gives Part X one line only ("Faces That Speak", P-155..P-168); there is no verbatim P-165 entry. This slice's scope is derived from Runmal's own in-tree record (hidden_files/P165_SCOUT.md / P165_DESIGN.md) and is stated here as derivation, never as roadmap verbatim.
- The banked Part X grid fills every chat-keyed cell - the current face (P-155), the current face + voice (P-157), the kept history (P-158) and the kept history + today's voice (P-161) - and every character-keyed cell: the roster (P-156), the speaking roster (P-159), the current-face chats board (P-160), the kept-history board (P-162) and the speaking-history board (P-163) - and P-164 took the owner's CURRENT faces as a silent census while naming an owner-wide history census open in its own record. The one subject x time cell no surface takes is OWNER x HISTORY: across all of my characters and all of their chats, which faces were shown, in what order, and would each still render today?
- The facts all exist with exactly one owner each - characters/service.list_characters (the owner's characters, creation order, deleted excluded) and faces/character_history.resolve_character_face_history (P-162: each character's board, composing P-158's per-chat history verbatim, under its closed board law). Only the owner-level composition was missing. This slice is that composition: it enumerates and sums, and invents no new law of its own.
- Disjointness from P-163 / P-164 (both banked at this slice's base): P-163 is character-keyed, speaking, and pairs one board with a voice; P-164 is owner-keyed but current and silent. This slice is owner-keyed and past, silent on voice, and its new files (history_census.py, history_census_router.py) sit under different names from census* and character_speaking_history*, so it cannot collide with either.
- Declined cells (reasons in hidden_files/P165_SCOUT.md): an owner-wide speaking census - P-164 declined it on substance (restating P-159 per character would blur where the voice law lives) and that objection stands unanswered, so it is left open for a later slice; an owner-wide speaking-history census - two joins at once, against the grid's one-join-at-a-time pattern; a character speaking-chats board - the owner row is the frontier P-164 opened, and this census is its smallest honest next join; a merged owner-wide event stream - flattening across characters would invent an ordering no owner recorded.

## Design

- history_census.py - resolve_face_history_census(session, user_id, *, base_dir=None) -> dict, a pure read. It never returns None: the subject is the caller themselves, so there is no foreign subject whose existence could leak, and an owner with nothing gets the honest empty census. Otherwise the envelope (schema runmal-p165-face-history-census-v1):
  * characters - one row per owned character, in list_characters order (creation order); a deleted character never appears, and another owner's characters never appear. Each row composes P-162's board verbatim in substance: character_id, character (character_to_dict verbatim, carried by the board), board_state (the board's own state under P-162's HISTORY_BOARD_STATES), chats (the board's rows whole - chat_id, title, message_count, presentation_state, current, events, event_count, selection_count, cleared_count, still_ready_count, kept_limit, at_kept_limit), chat_count, chats_with_history_count, event_count, selection_count, cleared_count, still_ready_count, chats_at_kept_limit, kept_limit.
  * state - the census under the closed HISTORY_CENSUS_STATES law: no_characters (the owner has no characters), no_chats (characters exist, none has any chat), no_history (chats exist, none holds any kept event), some_history (some chats hold kept events, some do not), all_history (every chat holds at least one kept event);
  * counts - character_count, characters_with_chats_count, characters_with_history_count, chat_count, chats_with_history_count, event_count, selection_count, cleared_count, still_ready_count, chats_at_kept_limit; kept_limit = P-092's MAX_HISTORY_KEPT, the per-chat law stated once, never summed into an owner window.
  * notes - five honesty notes: renders nothing; rows are P-162 verbatim; kept window per chat, never a complete owner record; events never merged, no owner-wide history stream; silent and past only, owner scoped, pure read.
- history_census_router.py - GET /faces/history-census on the /api/v1 mount: always 200 the envelope (every census state is data, never an error; there is no id parameter and nothing to 404).
- faces/__init__.py - subsystem map and exports extended for the history census surface (additive, after the census entries).
- app.py - history census router wired under /api/v1 with the local-auth dependency, after the census router.
- tests/test_p165_face_history_census.py - battery (15 tests).

## Declined

- An owner-wide speaking census and an owner-wide speaking-history census: named open, left for later slices (see the declined list above).
- A merged owner-wide event stream: events stay grouped per chat inside their character row. Declined.
- A new faces store / migration: every fact read already has exactly one owner (characters, chats, P-092 via P-158 / P-162); head stays 0041.

## Honesty

- Runmal renders nothing here; the census is kept-history data a client reads and carries no image bytes - a kept event's descriptor carries the P-023 content and thumbnail URLs as data.
- There is no owner-wide face and no owner-wide history stream: the census never collapses its rows into one face or one timeline, and a chat's events are named only under P-158's own law for that chat, inside its character's row.
- The census is silent and past only: it names no voice. Voice is P-157's / P-159's / P-161's / P-163's pairings, under the current_only law where history is concerned. The kept window is P-092's per-chat law; this census never claims a complete record of an owner's faces.
