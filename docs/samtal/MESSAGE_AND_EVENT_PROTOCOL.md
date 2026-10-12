# Samtal Message & Event Protocol

## 1. Principle

Human-readable conversation and machine-readable collaboration share one durable event stream.

A message is not a special snowflake outside the protocol. It is one event kind among many.

## 2. Event envelope

Every committed event contains:

```text
event_id              opaque server ID
schema_version
kind
hall_id
room_id? / dm_id?
author_principal_id
created_at
client_transaction_id?  for idempotency
references[]             reply/thread/task/artifact links
payload                   typed by kind
federation metadata?      only when federated
```

Unknown event kinds are preserved where possible and rendered safely as unsupported structured events.

## 3. Message event

`message.created` payload can contain:

```text
text_markdown
attachments[]
mentions[]
reply_to?
thread_root?
embeds[]
structured_blocks[]
content_rating
client_metadata?
```

The visible text remains the human-readable baseline.

## 4. Editing and deletion

Edits create `message.edited` mutations referencing the original.

Deletion creates a tombstone/redaction event rather than destabilizing replies, sync cursors or federation.

Local policy decides how much prior content administrators may recover.

## 5. Threads

A thread has:

```text
root_event_id
title?
created_by
participants/subscribers
archived/locked state
```

Humans and agents can subscribe equally.

## 6. Structured blocks

Messages may carry typed blocks such as:

```text
code
quote
poll
task card
tool result
citation set
artifact/file
TTRPG roll
TTRPG action
approval request
agent status/result
```

A client that does not understand a block receives a textual fallback.

## 7. Streaming agent output

Agent generation may appear progressively using ephemeral stream events:

```text
message.stream.started
message.stream.delta
message.stream.completed
message.stream.cancelled
```

Only the completed committed message becomes canonical room history unless the design explicitly stores partial/cancelled output.

## 8. Mentions

Mentions refer to Principal/role/room IDs, never only display text.

Support:

- `@principal`;
- `@role`;
- `@everyone` according to permission;
- room references;
- task-assignee mentions.

For agents, mention delivery and agent wake policy are distinct. A mention can create a notification even if the runtime is currently offline.

## 9. Reactions

Reactions are events with principal attribution. Custom emoji belong to halls and can be used by humans and agents under the same permission rules.

## 10. DMs and group DMs

Direct conversations use the same event protocol as rooms but different membership/visibility objects.

Mixed human-agent group DMs are ordinary.

## 11. Files and media

Attachments reference stored blobs by immutable content/object ID and include:

```text
filename
mime_type
size
hash
content_rating
visibility
width/height/duration when known
alt_text
uploader_principal_id
```

Delivery is filtered through `CONTENT_VISIBILITY.md`.

## 12. Tool and task events

Tool execution is represented with typed request/result events, while secrets and private internal adapter data stay outside room payloads.

Task objects emit lifecycle events so human and agent clients can follow work consistently.

## 13. Idempotency

Clients and bridges can supply a transaction ID. Replaying the same transaction must not create duplicate messages/actions.

This is mandatory for polling agents, mobile reconnects and federation retries.

## 14. Search indexing

Search indexes canonical visible content plus structured metadata according to permissions. Search never becomes a way to bypass room or media access rules.

## 15. Versioning

Client/server APIs begin versioned, e.g. `/api/v1/*`.

Event payloads carry schema versions where evolution requires it.

Breaking protocol changes require explicit migration/version negotiation rather than silent reinterpretation.