# Lore scopes — global + persona + chat layers (P-040)

Roadmap line: *Global + persona + chat lore scopes, layered like
the mirrors' (world → character → chat) with per-scope budgets.*

Clean-room basis: the layering (a world layer that applies
everywhere, a character layer, a per-chat layer) and per-layer
budgeting are public behaviour of world-info systems as recorded
in the P-002 census from the mirrors' official public
documentation. No mirror source code was read. The persona layer
is Rúnmál's own placement: in the mirrors the user's persona is
a first-class layer of the prompt, and in Rúnmál a chat's persona
is the character the user plays as (`chats.character_id`,
switched by `set_chat_persona`), so persona scopes key on a
character id and sit between the character and chat layers.

## The model

Migration 0032 creates `lorebook_scopes`:

| column | meaning |
| --- | --- |
| `lorebook_id` | the scoped book (cascade-deletes with it) |
| `scope_kind` | `global` / `character` / `persona` / `chat` |
| `owner_id` | `''` for global; a character id for character/persona; a chat id for chat |
| `token_budget` | per-scope budget: NULL unlimited, 0 mutes the layer, else the layer's cap |
| `position` | order of the book inside its layer |

The triple (lorebook, scope kind, owner) is unique — assigning
the same triple again updates budget/position in place. A book
may hold several assignments (e.g. global *and* pinned to one
chat); see dedupe below. Books with no rows are exactly as
before P-040.

The P-039 character-book binding needs no row: the bound book
*is* the character layer's first book (`via: "binding"`,
unlimited assignment budget; the book's own `token_budget`
still applies inside its preview).

## Layering and budgets

Activation gathers layers in declared order:

```
global (world) → character → persona → chat
```

Each layer is previewed on the shared engine
(`preview_activation`, so scan windows, selective logic, groups,
probability and placement all behave identically), with each
book's own budget applied inside its preview first. The layer's
scope budget is then enforced as a second, independent gate over
the layer's included rows: rows pack in deterministic order
until the budget is spent; the rest are `discarded` with
`discard_reason: "scope_over_budget"`. One layer's budget never
starves another: a muted (0) or exhausted chat layer leaves the
world layer's inclusions untouched.

When a layer holds several assignments with budgets, the
layer's enforced budget is the *minimum* declared — one dial
per layer, and the strictest assignment wins, so a layer can
never silently exceed a budget any of its assignments declared.

Dedupe: the same book assigned into several applicable layers
survives only in the most specific one (chat > persona >
character > global); the shadowed assignments are reported in
`shadowed` with kept/dropped scopes — never double-counted,
never silently dropped.

## Inspectability

`layered_preview` returns, per layer, the full preview rows
(each tagged `lorebook_id`, `scope`, `scope_owner_id`,
`scope_via`) plus a `scopes` summary: per scope, its books,
the enforced budget, tokens used, and included/discarded
counts. The prompt inspector (`inspect_prompt`) accepts a
`chat_id` (and an optional `persona_character_id` override):
it gathers the scoped layers for that chat, adds their included
entries as lore slots with provenance `lorebook:<name>@<scope>`,
their excluded entries as trace discards, and a `lore_scopes`
summary (the same per-scope shape) on the trace dict. Without
`chat_id`, inspection is byte-for-byte the pre-P-040 behaviour.

## API

- `PUT /lorebooks/{id}/scope` — assign/upsert
  `{scope_kind, owner_id?, token_budget?, position?}` → 201.
- `DELETE /lorebooks/{id}/scope?scope_kind=…&owner_id=…` →
  `{deleted: true}` or 404.
- `GET /lorebooks/{id}/scopes` — every assignment of the book.
- `GET /lore-scopes?scope_kind=…&owner_id=…` — one layer's books.
- `POST /chats/{id}/lore-preview` `{messages, seed?}` — the
  layered preview for the chat.
- `POST /debug/prompt-inspect` gains `chat_id` /
  `persona_character_id`.

Ownership discipline matches the rest of the lorebook surface:
an unowned book, character or chat is indistinguishable from a
missing one (404 at the router, `ValueError("… not found")` in
the service).
