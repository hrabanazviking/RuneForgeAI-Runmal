# P-162 - Character Face History: one character's kept face history across all of its chats (Part X, DERIVED)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md) gives Part X only its part-table line - "X | Faces That Speak | P-155 - P-168" - and no verbatim P-162 entry exists anywhere in it. This scope is therefore DERIVED, not roadmap-verbatim, from Runmal's own in-tree record only (design: hidden_files/P162_DESIGN.md):

- The Part X grid, read on this base (banked P-001..P-160, P-161 in flight on team-01): per chat, the current face (P-155), the current face + voice (P-157), the kept history (P-158) and the kept history + today's voice (P-161) all exist; per character, the roster (P-156), the speaking roster (P-159) and the current-face chats board (P-160) exist. The one subject x time cell no banked or in-flight surface fills is character x history: P-158 is scoped to one chat, P-160 to current faces, and nothing composes a character's kept history across its chats - which faces were shown across all of this character's chats, in what order, why, and would each still render today?
- The facts all exist with exactly one owner each - chats/service.list_chats (the owner's chats, creation order, message counts; P-160's enumeration), characters/service.get_character (existence law), faces/history.resolve_face_history (P-158: each chat's kept events verbatim with provenance, entry states judged against today, the kept window named honestly). Only the composition was missing. This slice is that composition.
- Precedent: P-160 (enumerate the character's chats, compose the owning per-chat surface verbatim, closed board law, five notes) and P-158 (compose, never invent a second history or binding law). The silent cell lands before its speaking pairing in every grid row so far (P-155 -> P-157, P-158 -> P-161, P-156 -> P-159); this slice is silent for the same reason.

Base: d1fb6104bbdf75f43e926cff1162ca1cfd336954 (P-160 banking record; banked P-001..P-160). Migration: NONE - head stays 0041, no 0042.

## What landed

New modules in src/runmal/faces/ - no store, no migration:

- character_history.py - resolve_character_face_history(session, user_id, character_id, *, base_dir=None) -> dict | None, a pure read. None when the character is missing, foreign or deleted (get_character's law - existence never leaks). Otherwise the envelope (schema runmal-p162-character-face-history-v1):
  * character - character_to_dict verbatim, the character service's own facts;
  * chats - one row per owned chat bound to this character, in list_chats order (creation order); chats bound to other characters and unbound chats never appear. Each row carries the chat's own facts (chat_id, title, message_count) plus that chat's P-158 history document composed verbatim in substance: presentation_state, current, events (the P-092 rows whole with provenance, plus entry_state / problem_now / descriptor exactly as P-158 judged them), event_count, selection_count, cleared_count, still_ready_count, kept_limit, at_kept_limit. Events are never merged into one cross-chat stream: interleaving chats would invent an ordering no owner recorded; they stay grouped under the chat that made them, in that chat's own order.
  * state - the board under the closed HISTORY_BOARD_STATES law: no_chats (the character has no chats), no_history (chats exist, none holds a kept event), some_history (some chats hold kept events, some hold none), all_history (every chat holds at least one kept event);
  * counts - chat_count, chats_with_history_count, event_count, selection_count, cleared_count, still_ready_count (each summed from P-158's own per-chat arithmetic), chats_at_kept_limit (rows at the kept limit), and kept_limit (P-092's MAX_HISTORY_KEPT) named once for the board;
  * notes - five standing honesty notes in fixed order.
- character_history_router.py - GET /faces/character-history?character_id= on the /api/v1 mount: 404 when resolve returns None, 200 the envelope otherwise (every board state is data at 200, never an error).
- faces/__init__.py - subsystem map and exports extended for the character-history surface (additive, after the chats entries).
- app.py - character-history router wired under /api/v1 with the local-auth dependency, after the chats router.
- tests/test_p162_character_face_history.py - battery (19 tests).

## Declined candidates (each with its reason)

- Character speaking history (this board plus voice): the silent cell lands first in every grid row (P-155 -> P-157, P-158 -> P-161, P-156 -> P-159); the pairing stays a later slice and must carry P-161's voice honesty law (voice_scope current_only - S512 stores no voice history). Named open.
- Character speaking chats (P-160's board plus voice): P-160 weighed the speaking board and declined it - the voice half is per character (S512), identical on every row, and is P-157's / P-159's document to name. Named open.
- An owner-wide face census: aggregates across characters; named open by P-158 / P-160 as a P-168 gate companion, wider than this grid cell.
- A merged cross-chat event stream: invents an ordering no owner recorded. Declined.
- Per-chat history inlined into P-160's board: P-160 declined it - history is a kept window and its own document; this slice is that document on the character axis, not an inline expansion.
- A client stage/renderer surface: no renderer exists in-tree to extend. Named open.
- Generated expression sprites via P-087: re-kinding is a P-087 landing-contract change, not a faces read. Named open.
- Scenario VN stage integration: no record joins scenario cast role names to characters or faces. Named open.
- Portrait animation / lip-sync: no timing, viseme or animation contract exists in-tree. Declined.
- Automatic expression detection from message text: declined ABSOLUTELY (P-092 standing law).
- Playback/scripting execution: declined ABSOLUTELY (P-027 law).
- A new faces store / migration: every fact read already has exactly one owner (chats, characters, P-092 via P-158); head stays 0041.

## Honest limitations

- Runmal renders nothing here; the board is history data a client reads and carries no image bytes - a still-declared entry's descriptor carries the P-023 content and thumbnail URLs as data.
- A character has no single face history stream: events stay grouped per chat, and the kept window applies per chat - the board never claims a complete record of a character's faces.
- The board is silent on voice by design (the grid's silent cell); the character's voice is P-157's / P-159's document, and any speaking pairing of this board must state P-161's current_only law.
- The scope is DERIVED, not roadmap-verbatim. The keeper reviews this derived scope at banking.
- Disjointness: P-161 (in flight on team-01) owns faces/speaking_history.py + speaking_history_router.py; this slice never touches them. The shared touchpoints (faces/__init__.py, app.py) are additive at different anchors (this slice after the chats entries / chats router; P-161 after the speaking-roster entries / router) and reconcile as pure additive unions at banking, as the P-155..P-160 unions did. P-162 banks after P-161.
