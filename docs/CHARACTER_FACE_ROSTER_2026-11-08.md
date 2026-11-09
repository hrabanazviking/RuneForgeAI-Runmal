# P-156 — Character face roster (Part X, Faces That Speak)

**DERIVED scope — stated plainly:** the governing roadmap
gives Part X only its part-table line (*X | Faces That
Speak | P-155 – P-168*) and no verbatim P-156 entry
exists. This slice's scope is derived from Rúnmál's own
in-tree record only, per the P-101/P-117/P-131 precedent:
P-155's design names per-character (chat-less)
presentation as the open candidate it declined as the
Part X opener; P-092's `binding_report` is the banked
character-keyed join of a declared expression set to its
P-023 sprite assets; the character service owns the
avatar facts. Clean-room: public behaviour and in-tree
specs only — no SillyTavern or Voxta source was read.
Base 8824e95 (P-154 banking record, Part IX complete),
migration head 0041. **No migration taken.**

## What landed

`src/runmal/faces/roster.py` — a pure read,
`resolve_character_roster(session, user_id, character_id)`:

- **None for a missing or foreign character** —
  `binding_report`'s own law; existence never leaks.
- **Entries resolved to descriptors** in the same shape
  P-155's presentation descriptors use: `{name, label,
  notes, bound, problem, asset, renderable, content_url,
  thumbnail_url}` — the P-092 binding row verbatim in
  substance, the asset facts verbatim, and the P-023
  content/thumbnail roads as URL data, present only when
  the entry is bound. `renderable == bound`.
- **A closed roster state law** (`ROSTER_STATES`):
  `ready` (a set is declared and at least one entry is
  renderable), `no_renderable` (a set with entries, none
  bound), `empty_set` (a declared set with zero entries),
  `no_set` (no set declared for the character).
- **Fallbacks named as data, never substituted:** the
  declared default's descriptor (`default_entry`) and the
  character's avatar (`{has_avatar, avatar_asset,
  avatar_url}` from `character_to_dict`'s own facts;
  the URL only when an avatar exists).
- **Counts:** `entry_count` / `bound_count` carried from
  the binding report; `renderable_count` /
  `unbound_count` summed from the descriptors.
- **No current face — deliberately.** Expression
  selection is per chat and always an explicit act
  (P-092's standing law). The document carries
  `selection_scope: "per_chat"` and no `current`/`face`
  key at all: a roster names what a character *can*
  show; which face a chat is showing is P-155's chat
  presentation document's to name.
- **Five standing honesty notes** ride in fixed order:
  Rúnmál renders nothing; no current face is named and
  no message text is scanned; the default is fallback
  data only; a bound entry's thumbnail road 404s
  honestly unless its P-023 `thumbnail_status` is
  ready; the surface is a pure read.

`src/runmal/faces/roster_router.py` + `app.py` wiring —
`GET /api/v1/faces/roster?character_id=`, bearer-gated
like every API: 404 when the resolve returns None,
200 with the document otherwise (every roster state is
data at 200, never an error).

## Honest boundaries

- No renderer, stage, animation or lip-sync is
  invented; the roster is data a client renders, like
  its P-155 sibling.
- No generation: P-087 still lands kind `background`
  only; generated expression sprites remain a named
  open candidate, not this slice.
- No store and no migration: P-092's store stays the
  one truth for sets; head stays 0041.
- One character per document: no multi-character face
  index is shipped — no in-tree consumer names one yet.

## Banking note

P-155 (team-01) creates `src/runmal/faces/` with its
chat-keyed `presentation` module and router on the same
base and banks first. This slice's `faces/__init__.py`,
`roster.py` and `roster_router.py` join that package and
its `app.py` wiring lands beside P-155's; the keeper
reconciles the two halves at banking (overlap flagged
in hidden_files/P156_EVIDENCE.md).

## Tests

`tests/test_p156_character_face_roster.py` — existence
and owner scoping, the four-state law, descriptor shape
and URL roads, wrong-kind / missing / unbound problems
stated honestly, the no-current-face law, pure-read
idempotence, the avatar fallback, the HTTP flow, and
the migration-head neighbour (0041, no 0042). Counts
are recorded in hidden_files/P156_EVIDENCE.md.
