# Character-Book Binding (P-039) — 2026-11-06

Roadmap line: *Character-book binding: a card's own lorebook travels
with it and merges with the world's by declared precedence.*

## The gap

`CharacterCard.character_book` was parsed (`cards/parser.py`) and
re-exported verbatim (`cards/exporter.py`), and the stored
`card_json` carried it through the library — but nothing ever
interpreted it. No `Lorebook`/`LoreEntry` rows were created, no code
path activated its entries, and `persona/slots.py` said so plainly:
"character_book / extensions belong to future lorebook handling."
P-039 is that handling.

## Travel: materialise on the way in, serialise on the way out

- `lorebooks/binding.py::materialise_character_book` runs inside
  `characters/service.create_character_from_card` (the single funnel
  for API creation, bulk library import, PNG and CHARX) after the
  P-025 duplicate check, inside the caller's transaction. A card
  whose embedded book has entries gains a real owned `Lorebook` +
  `LoreEntry` rows (real UUIDs, so chat entry state, budget
  tie-breaks and P-036 probability rolls all work unchanged) plus a
  binding row. A malformed embedded book never refuses an
  otherwise-valid card (the P-022 asset discipline): the partial
  rows are expunged, creation continues unbound, and `card_json`
  still carries the book verbatim at the file layer.
- Entry normalisation accepts both attested shapes — the v3
  list form (`keys`, `insertion_order`, `enabled`) and the v2
  uid-dict form (`key`, `order`, `disable`, `comment`) — and the
  public position codes (0 → `before_char`, 1 → `after_char`,
  4 → `at_depth`, the code P-005 pinned).
- On the way out, `serialise_bound_book` rebuilds the travelling
  `character_book` dict from the *bound lorebook's current rows*, so
  an entry edited in the lorebook editor is what travels — the DB
  book is the source of truth once bound; `card_json`'s snapshot is
  the fallback for unbound characters. `GET
  /characters/{id}/character-book` serves exactly that dict.
- `duplicate_character` gives the clone its **own** materialised
  copy of the book (never a shared mutable book), at the same
  precedence.

## Binding storage

Migration **0031 (PROVISIONAL** — P-037 took 0029 and P-038 took
0030, both banking before P-039; the keeper confirms/renumbers at
banking; in this tree the sequence runs 0028 → 0031) creates
`character_book_bindings`: one row per character (`character_id`
UNIQUE, FK CASCADE), pointing at the bound `lorebook_id` (FK
CASCADE), carrying the declared `precedence`. Deleting the lorebook
unbinds by cascade; unbinding never deletes the book — it survives
as an ordinary library lorebook.

## Declared precedence merge

`merge_entry_dicts(world, character, precedence)` is a pure
function. Entries from both books are pooled and scope-tagged
(`character` / `world`). A **collision** is two entries from
different scopes sharing a non-empty name (stripped, case-folded);
unnamed entries never collide and always coexist. The loser of a
collision is never silently dropped: it is reported in `shadowed`
with kept/dropped scope and ids.

Three declared modes, stored on the binding, default
`character_first`:

- `character_first` — the character's entry wins collisions; the
  merged order is character entries first, then world entries,
  each by (−priority, name, id).
- `world_first` — the mirror image.
- `priority` — higher `priority` wins collisions (tie → character
  wins, declared); merged order is (−priority, character before
  world, name, id).

The winners, in merged order, run through **one**
`preview_activation` call — one scan, one activation tick, one
budget (the shared engine the prompt pipeline uses). The world
book's `scan_depth` / `token_budget` govern the merged tick,
falling back to the character book's when unset (P-040 owns
per-scope budgets). Every result row carries its `scope`; the
result carries `precedence`, both book ids, and `shadowed`.

## API (characters router)

- `GET /characters/{id}/lorebook-binding` — bound state, binding,
  lorebook summary, entry count (unbound → `{"bound": false}`).
- `PUT /characters/{id}/lorebook-binding` — bind an existing owned
  lorebook, with optional precedence.
- `PATCH /characters/{id}/lorebook-binding` — change precedence.
- `DELETE /characters/{id}/lorebook-binding` — unbind (book survives).
- `GET /characters/{id}/character-book` — the travelling book.
- `POST /characters/{id}/lorebook-preview` — merged activation
  preview against a named world lorebook.

Ownership is checked on both character and lorebook throughout;
bad precedence is a 422; an unowned character is a 404.

## Clean-room basis

Built from Rúnmál's own public shapes only: the card `character_book`
field as recorded by P-015/P-016's public-spec import work and the
P-005 authored corpus, and the world-info entry field set P-019
recorded from public documentation. No mirror source code was read.
