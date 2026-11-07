# P-089 — Quick Replies (Part VI, Extensions Row)

Roadmap line: *Quick Replies: user-defined one-tap macros
incl. chained actions and input senders.*

Clean-room: built from the roadmap line and Rúnmál's own
contracts only — the P-081 Plugin API v1 citizen pattern,
the P-082 sandbox policy, the P-055 macro engine, the
chats append road with its P-075 provenance and P-076 undo
contracts. Base 700da52 (P-087 banking record), migration
head 0041. **No migration taken.**

## What landed

`src/runmal/plugins/quick_replies.py` — a first-class P-081
citizen, id `runmal.quick-replies`, plus routes appended to
the plugins router (`/quick-replies...`, mounted under
`/api/v1` by the existing include; `app.py` untouched):

- capabilities `chat.events`, `ui.slots`; permissions
  `chat.read`, `ui.contribute` (`chat.write` NOT declared —
  reserved in v1; execution is trusted host wiring, the
  P-084 session-factory trust class, not a plugin surface);
- events `chat.created` / `chat.deleted` declared; the
  handler abstains — chat deletion never silently deletes
  durable user definitions, and execution is an explicit
  owner verb, never event-driven;
- one UI contribution `quick-replies-panel` in
  `chat.toolbar` — the one-tap surface;
- sandbox grants EMPTY (proven in the battery).

Registration stays `register_plugin`-only; `build_registry`
/ `create_app` are unchanged (the keeper reconciles liveness
at banking, as for P-086/P-087).

## Definitions: stored, durable, per user

One JSON document per owner at
`data_dir()/quick_replies/<user_id>.json` (the P-076/P-083
file idiom: atomic tmp + chmod 0o600 + replace; the user id
is UUID-validated before it becomes a path). A corrupt store
raises and is never silently reset. Cap: 200 replies/owner.

A reply is `{name (1..120), steps (1..8), scope, chat_id,
enabled}`. `scope` is `user` (offered in every chat) or
`chat` (bound to one chat; `chat_id` required iff chat
scope). A `text` shorthand in place of `steps` means one
user-role input-sender step; `text` and `steps` together
reject. Duplicate names within a scope reject. A step is
`{kind: "message" (the only v1 kind), role:
user|assistant|system, text (1..4000), sender:
input_sender|quick_reply}` with defaults role `user`, sender
`input_sender` for user role else `quick_reply`. An explicit
`input_sender` with a non-user role rejects outright.

CRUD is owner-scoped service functions (`create_reply`,
`list_replies` — user-scope always, chat-scope when the chat
is named — `get_reply`, `update_reply`, `delete_reply`) and
the HTTP surface in the house idiom: `GET/POST
/quick-replies`, `GET /quick-replies/executions`,
`GET/PUT/DELETE /quick-replies/{id}`,
`POST /quick-replies/{id}/execute`; invalid -> 422, unknown
reply/chat -> 404, create -> 201. Creating a chat-scoped
reply over HTTP verifies the chat is the owner's.

## Execution: the chat road, in declared order

`execute_reply(session, user_id, chat_id, reply_id)` returns
`None` for a missing/foreign chat or reply, or a chat-scoped
reply asked into another chat; a disabled reply refuses
loudly before any write. The P-055 `MacroContext` is built
from the chat itself (bound character name, owner name,
last / last-user / last-assistant messages) — nothing is
invented for a macro to read.

Steps run in declared order. Each expands through P-055
`expand_macros(strict=True)`: an unknown or malformed macro
fails the step BEFORE anything is appended for it — raw
`{{...}}` is never posted as content. Variables thread
across steps via the expansion reports (`setvar` in step 1
is readable by `getvar` in step 2). Each successful step
appends via `chats.service.append_message` with an explicit
P-075 record and quick-reply event data, so the P-076
journal (undo works per appended step, newest first) and
the plugin `message.created` dispatch apply exactly as for
a hand-sent message. The first failure stops the chain:
applied steps stay applied, the failed step records its
error, later steps are `skipped`, and the execution record
`{id, reply_id, reply_name, chat_id, status:
ok|partial|failed, started_at, steps[], variables}` is
persisted (newest 50 kept per owner) and returned. An
expansion yielding empty text fails its step with that
reason recorded.

## Input-sender semantics (plain)

- `sender: input_sender`: the expanded text lands as a USER
  message — the user's own message in the transcript,
  exactly what a following generation call consumes,
  indistinguishable in role and authorship from typed input.
  The P-075 receipt still tells the truth: origin kind
  `manual` (the closed P-075 vocabulary has no quick-reply
  kind and none is forged) with origin facts
  `via="quick_reply"`, `quick_reply_id`, `quick_reply_name`,
  `step_index`, `sender="input_sender"`.
- `sender: quick_reply`: lands with its declared role under
  the same receipt shape (`sender="quick_reply"`).
- Quick replies never call a model: no hidden generation.
  An input-sender step produces the input; the normal
  generation road does the rest.

## The P-055 line

P-055 macros are the text-expansion engine; quick replies
are the stored user-facing definitions + execution built on
it. There is no second macro engine.
