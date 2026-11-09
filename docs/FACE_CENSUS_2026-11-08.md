# P-164 - Face Census: one owner's current faces across every character and chat (Part X, DERIVED)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md) gives Part X only its part-table line - "X | Faces That Speak | P-155 - P-168" - and no verbatim P-164 entry exists anywhere in it. This scope is therefore DERIVED, not roadmap-verbatim, from Runmal's own in-tree record only (design: hidden_files/P164_DESIGN.md):

- The banked Part X grid fills every chat-keyed cell - the current face (P-155), the current face + voice (P-157), the kept history (P-158) and the kept history + today's voice (P-161) - and every character-keyed cell: the roster (P-156), the speaking roster (P-159), the current-face chats board (P-160) and the kept history board (P-162). The one subject no banked surface takes is the OWNER: P-158, P-160 and P-162 each weighed an owner-wide face census and named it open, and nothing answers the owner-side question - across all of my characters and all of their chats, what face is each chat currently showing, and how many are ready?
- The facts all exist with exactly one owner each - characters/service.list_characters (the owner's characters, creation order, deleted excluded) and faces/chats.resolve_character_face_chats (P-160: each character's board, composing P-155's per-chat presentation truth verbatim, under its closed board law). Only the owner-level composition was missing. This slice is that composition: it enumerates and sums, and invents no new law of its own.
- Disjointness from P-163 (in flight on team-01, from base 3bc712b; its design had not landed when this slice scouted): P-162's own declined list names character speaking history - this board's board plus voice, carrying P-161's current_only law - as the later slice, making it P-163's most plausible cell, with character speaking chats the other plausible character-keyed pairing. This slice is owner-keyed, silent and current: a different subject, a different composition, and new files under different names, so it cannot collide with either. It is also the cell furthest from P-162's character-history ground in the grid (subject owner not character, time current not history, modality silent not a history pairing). P-164 banks after P-163.
- Precedent: P-160 (enumerate one subject's chats, compose the owning per-chat surface verbatim, closed board law, five notes) and P-162 (the same composition pattern one subject level down in time). The census applies P-160's pattern one subject level up.

Base: 362f44254a202996617225426b7c2c1a78fd16e0 (P-162 banking record; banked P-001..P-162). Migration: NONE - head stays 0041, no 0042.

## What landed

New modules in src/runmal/faces/ - no store, no migration:

- census.py - resolve_face_census(session, user_id, *, base_dir=None) -> dict, a pure read. It never returns None: the subject is the caller themselves, so there is no foreign subject whose existence could leak, and an owner with nothing gets the honest empty census. Otherwise the envelope (schema runmal-p164-face-census-v1):
  * characters - one row per owned character, in list_characters order (creation order); a deleted character never appears, and another owner's characters never appear. Each row composes P-160's board verbatim in substance: character_id, character (character_to_dict verbatim, carried by the board), board_state (the board's own state under P-160's BOARD_STATES), chats (the board's rows whole - chat_id, title, message_count, presentation_state, current, current_problem, face), chat_count, ready_count, selection_count, unbound_count.
  * state - the census under the closed CENSUS_STATES law: no_characters (the owner has no characters), no_chats (characters exist, none has any chat), none_ready (chats exist, none shows a ready face), some_ready (some chats ready, some not), all_ready (every chat shows a ready face);
  * counts - character_count, characters_with_chats_count, chat_count, ready_count, selection_count, unbound_count, each summed from the P-160 boards' own arithmetic;
  * notes - five standing honesty notes in fixed order.
- census_router.py - GET /faces/census on the /api/v1 mount: always 200 the envelope (every census state is data, never an error; there is no id parameter and nothing to 404).
- faces/__init__.py - subsystem map and exports extended for the census surface (additive, after the character-history entries).
- app.py - census router wired under /api/v1 with the local-auth dependency, after the character-history router.
- tests/test_p164_face_census.py - battery (15 tests).

## Declined candidates (each with its reason)

- Character speaking history (P-162's board plus voice): P-163's most plausible cell - taking it would collide in subject and in spirit; it also must carry P-161's voice honesty law (voice_scope current_only - S512 stores no voice history). Named open for P-163's road.
- Character speaking chats (P-160's board plus voice): the other plausible P-163 cell; also weighed and declined by P-160 and P-162 - the voice half is per character (S512). Not disjoint enough, and not this slice.
- An owner-wide history census: the history axis sits on P-162's own ground, and summing kept windows across characters would blur the per-chat kept-window law (P-158 / P-162) - the past stays in those documents. Named open.
- An owner-wide speaking census: voice is per character (S512), so there is no single owner-level pairing to state; restating P-159 per character inside a census would blur where the voice law lives. Named open.
- A merged owner-wide chat stream: chats stay grouped under the character that owns them, in that character's board order - flattening across characters would invent an ordering no owner recorded. Declined.
- A client stage/renderer surface: no renderer exists in-tree to extend. Named open.
- Generated expression sprites via P-087: re-kinding is a P-087 landing-contract change, not a faces read. Named open.
- Scenario VN stage integration: no record joins scenario cast role names to characters or faces. Named open.
- Portrait animation / lip-sync: no timing, viseme or animation contract exists in-tree. Declined.
- Automatic expression detection from message text: declined ABSOLUTELY (P-092 standing law).
- Playback/scripting execution: declined ABSOLUTELY (P-027 law).
- A new faces store / migration: every fact read already has exactly one owner (characters, chats, P-092 via P-155 / P-160); head stays 0041.

## Honest limitations

- Runmal renders nothing here; the census is current-face data a client reads and carries no image bytes - a ready face's descriptor carries the P-023 content and thumbnail URLs as data.
- There is no owner-wide face: the census never collapses its rows into one face, and a chat's face is named only under P-155's own law for that chat, inside its character's row.
- The census is silent and current by design: it reads no kept event and names no voice. History is P-158's / P-162's documents; voice is P-157's / P-159's / P-161's, under the current_only law where history is concerned.
- The scope is DERIVED, not roadmap-verbatim. The keeper reviews this derived scope at banking.
- Disjointness: P-163 (in flight on team-01) owns its own new module + router files under different names; this slice never touches them. The shared touchpoints (faces/__init__.py, app.py) are additive at different anchors (this slice after the character-history entries / router) and reconcile as pure additive unions at banking, as the P-155..P-162 unions did. P-164 banks after P-163.
