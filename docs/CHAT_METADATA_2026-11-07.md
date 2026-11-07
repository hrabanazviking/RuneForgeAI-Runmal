# Chat metadata — P-073 (2026-11-07)

Titles, tags, and summaries for every chat: auto-generated,
always editable, and served through a library view that stays
fast at scale. Roadmap: docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md, P-073 (Part V, Chat Surgery).

## What a chat carries now

- **Title** — the existing `chats.title`, renamed as before and
  now also editable through the metadata road.
- **Summary** — new per-chat text ('' = none yet).
- **Tags** — normalised tag rows, the same display/key discipline
  as the character library (P-024): whitespace-collapsed display
  form, casefolded key, duplicates impossible.
- **Favourite** — a per-chat flag for library filtering.
- **Provenance** — one JSON document recording, per field,
  whether the value is `manual`, `auto`, or `unset`, plus the
  generator id, when generation last ran, and how many messages
  it read.

## Auto-generation is honest

Generation is **deterministic and extractive** (generator id
`extractive-v1`), computed from the chat's own messages with
plain string work in `runmal/chats/metadata.py`:

- the title is the first user message, trimmed at a word
  boundary (fallbacks: first assistant message, the character's
  name, "Untitled chat");
- the summary is the opening sentence plus the later sentence
  whose content words are most frequent across the chat,
  length-capped;
- tags are the most frequent content words (stopwords removed),
  ranked by frequency then alphabetically; fewer than two
  distinct candidates yields no tags.

No model is called and no backend is consulted; nothing in the
payloads pretends otherwise. Editing a field by hand marks it
`manual`, and regeneration skips manual fields unless the
caller passes `force` for the request. Regeneration reports
`generated` and `skipped` lists so the outcome is inspectable.
Tag lists are presented in key (alphabetical) order, as in
the character library; the generation ranking decides which
tags are chosen. Events `chat.metadata_generated`, `chat.metadata_updated`, and
`chat.favourite_changed` record field names and counts only —
never content.

## The library view at scale

`GET /chats/library` returns `{total, items}` with SQL-side
filtering, sorting, and pagination (limit clamped to 1..200):

- `q` matches title, summary, and tag text;
- `tags` (repeatable) with `tag_mode=any|all`;
- `favourites_only`, `character_id` filters;
- sorts: `recent` (last message activity, falling back to
  creation), `newest`, `oldest`, `title`, `title_desc`,
  `favourites_first`.

Items carry the full metadata payload plus `message_count` and
`last_activity`. `GET /chats/tags` lists every chat tag with
its chat count. The plain chat read (`GET /chats/{id}` and the
chat list) now also carries `summary` and the provenance
`metadata` object; tags ride the metadata and library payloads.

## HTTP surface

- `GET /chats/library`, `GET /chats/tags`
- `GET /chats/{chat_id}/metadata`
- `PUT /chats/{chat_id}/metadata` — partial edit of
  `title` / `summary` / `tags` (unknown or invalid → 422)
- `POST /chats/{chat_id}/metadata/regenerate` —
  `{fields?, force?}`
- `PUT /chats/{chat_id}/favourite` — `{is_favourite}`

Every route is owner-scoped: another user's chat is a 404.

## Storage — PROVISIONAL 0039

Migration `0039` is **PROVISIONAL** (the keeper composes final
numbering at banking; P-072 takes no migration, so 0039 is
expected to stand). It adds `chats.summary`,
`chats.metadata_json`, the `chat_tags` table, and the
`chat_organisation` table. A migration is unavoidable: tags
must be filterable and countable in SQL at library scale, which
a JSON blob cannot do — the P-024 lesson.

## Boundaries

The library view is a query contract, not a rendered page; the
web UI consuming it is out of scope. Summaries of empty chats
are empty. Generation quality is extractive by design — a
model-written summary would be a different, honestly-labelled
feature.
