# P-155 — Face Presentation Foundation (Part X, Faces That Speak — opener)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part X only its part-table line —
"X | Faces That Speak | P-155 – P-168" — and no verbatim
P-155 entry exists anywhere in it. This slice's scope is
therefore DERIVED, not roadmap-verbatim, from Runmal's own
in-tree record only (full survey: hidden_files/P155_SCOUT.md;
design: hidden_files/P155_DESIGN.md):

- P-092 (plugins/expressions.py) declares expression sets per
  character, binds each entry by reference to a P-023 sprite
  asset, selects the current expression per chat with
  provenance — and states plainly that no renderer is
  invented there because Part X owns rendering, naming
  `inspect_state` "the inspectable surface Part X reads".
  Its banking record repeats it: "No renderer was invented
  — Part X owns rendering."
- P-023 stores the sprites and serves their bytes through
  its content / thumbnail roads; its slice doc defers:
  "Part X animates what this slice stores."
- P-087 (image generation) and the delta rows ST-65 / VX-03
  name Part X as the consumer of the expression surface and
  the stored assets.
- Precedent for a new subsystem package + service + router +
  app wiring as a part opener: P-117 (vision).

What did NOT exist: any consumer of `inspect_state` outside
P-092's own tests and router, and any presentation document.
A client wanting to show a chat's current face had to call
inspect, interpret binding problems itself, construct the
P-023 URLs itself, and decide fallback law itself — the
resolution work P-092 deferred had no accountable owner.
This slice is that owner. The keeper reviews this derived
scope at banking.

Base: 8824e95191ba0a71c6467a880805c413131dd4c7 (P-154 banking
record; PART IX COMPLETE; P-001..P-154 banked + the
commissioned slice). Migration: NONE — head stays 0041,
no 0042.

## What landed

New package `src/runmal/faces/` — no store, no migration:

- `presentation.py` — `resolve_presentation(session, user_id,
  chat_id, *, base_dir=None) -> dict | None`, a pure read.
  None when the chat is missing or foreign (P-092's inspect
  law — existence never leaks). Otherwise it composes
  `inspect_state` VERBATIM (its set / bindings / current /
  counts ride whole; no second binding or selection law is
  invented) and resolves it into the presentation document
  (schema `runmal-p155-face-presentation-v1`):
  * `entries` — one descriptor per binding row, in set
    order: {name, label, notes, bound, problem, asset
    (verbatim or None), renderable, content_url,
    thumbnail_url}. The URLs are the P-023 roads as DATA
    (`/api/v1/characters/{cid}/assets/{aid}/content` and
    `/thumbnail`), present only when the entry is bound,
    else None. `renderable == bound`.
  * `state` — exactly one of the closed PRESENTATION_STATES:
    `ready` (a current selection exists and its binding is
    bound), `current_unbound` (a current selection exists
    but is not bound — `current_problem` carries the binding
    problem verbatim, or `not_declared` when the selection
    names no entry in the current set, e.g. the set was
    deleted or replaced after selection), `no_selection`
    (a set is declared, nothing is current), `no_set` (a
    character is bound, no set declared), `no_character`
    (the chat has no bound character).
  * `face` — the current entry's descriptor when the state
    is `ready`, else None. NEVER substituted.
  * `fallbacks` — data, not decisions: `default_entry` (the
    declared default's descriptor or None) and `avatar`
    {has_avatar, avatar_asset, avatar_url} from
    `get_character`'s own facts; `avatar_url` only when
    `has_avatar`.
  * `counts` — entry_count / bound_count carried from
    inspect; renderable_count summed from the descriptors.
  * `notes` — the five standing honesty notes, fixed order:
    (1) Runmal renders nothing — this document is data a
    client renders; no bytes are carried, URLs are roads.
    (2) Selection is P-092's explicit act only — this read
    selects nothing, applies no default, and scans no
    message text. (3) face is None unless the current
    selection is bound; fallbacks are named, never silently
    substituted. (4) A bound entry's thumbnail road 404s
    honestly unless its P-023 thumbnail_status is ready
    (the asset facts are carried). (5) Pure read: nothing
    is stored, generated or animated by this surface.
- `router.py` — `GET /faces/presentation?chat_id=`, wired
  in app.py under /api/v1 with the local-auth dependency,
  after the vision router: 404 when resolve returns None
  (an unknown or foreign chat never leaks); every non-ready
  state is DATA at 200, never an error.
- `__init__.py` — the subsystem map + exports.
- `src/runmal/app.py` — the faces router import + include
  under /api/v1 (additive, after vision).
- Battery: tests/test_p155_face_presentation.py (14 tests).

## Declined candidates (each with its reason)

Named in full in hidden_files/P155_DESIGN.md: a real
renderer / sprite stage / compositor (no client renderer
exists in-tree to extend; the honest first step is the
presentation DATA a renderer consumes — later Part X slices
may build a stage ON this document); portrait animation /
lip-sync (VX-48 — no timing or animation contract in-tree);
video / 3D avatars, VRM, video generation, generation
plumbing (VX-49 / VX-52 / VX-53 — no viewer, model format
or engine in-tree; VX-52/53 sit under the Part I founding
licence gate); generating expression sprites via P-087
(generation is banked and lands kind background, never
expression; existing stored sprites must first be
presentable); automatic expression detection from message
text (declined ABSOLUTELY by P-092's standing law);
applying the declared default inside this read (apply_default
is P-092's explicit WRITE road — a read that mutated
selection would forge provenance; the default rides as
fallback data); a new faces store / migration (P-092's
store is the one truth; a second store would fork it);
folding in the P-095 gallery (it lists a chat's images with
provenance; it does not resolve a face); scenario VN stage
integration (no record joins scenarios to faces yet);
per-character chat-less presentation (inspect_state is
chat-keyed and selection is per chat).

## Honest limitations

- Runmal renders, selects, animates, stores and generates
  NOTHING in this slice. The document is the contract a
  client renders; no client renderer exists in-tree yet,
  and building one is a later Part X slice's work, on top
  of this document.
- A bound entry's URLs are named, not fetched: whether the
  thumbnail road serves bytes or 404s depends on the
  asset's P-023 thumbnail_status at fetch time; the asset
  facts (including thumbnail_status) ride in the descriptor
  so a client can decide without guessing.
- The avatar fallback names the character's avatar road
  only; it is never promoted to `face`, and a client that
  prefers showing nothing over showing the avatar can do
  so from the named state alone.
- Playback / execution of any stored content remains
  declined ABSOLUTELY (P-027: content is data, never code).
- Migration: NONE (head stays 0041, battery-pinned).
