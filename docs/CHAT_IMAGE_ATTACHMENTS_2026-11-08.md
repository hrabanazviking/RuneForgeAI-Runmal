# P-120 — Image Attachments on Chat Messages (Part VIII, Vision Services)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line —
"VIII | Vision Services | P-117 – P-130" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: the P-117
named-open list, the P-117 vision JSON-store pattern, the
P-023 character-asset byte-storage road, the sniff truth in
assets/imaging.py, the P-107 additive-view idiom, the P-118
custody idiom, and P-075's no-content law. The keeper reviews
this derived scope at banking.

Base: 8065234a (P-118 banking record). Migration: NONE —
head stays 0041; the provisional 0042 was eyed only if a
messages-table column proved unavoidable, and the P-117
store pattern proves it is not.

## The weighing (all six P-117 named-open items)

After P-119 (provider selection + capability truth, banking
in flight as this slice was built), P-117's named-open list
held: a real local semantic caption provider, screen
capture, folder watcher, camera flow, OCR, and image
attachments on chat messages. The scout weighed each against
the tree:

- **Semantic caption provider — declined, honestly.** No
  backend declares `Capabilities.vision`, there is no
  image-input wire in the backends or generation service,
  and no local vision model exists in-tree. A captioner
  built today could only fabricate text or re-label the
  metadata road. It stays named-open.
- **OCR — declined, honestly.** No OCR engine or recognition
  library exists in-tree; assets/imaging.py sniffs formats
  and decodes PNG for thumbnails — it does not read text.
  It stays named-open.
- **Screen capture / camera flow — declined.** No capture
  surface or client exists in this server-side tree, and no
  consent story to build on. Both stay named-open.
- **Folder watcher — declined for now.** No watcher or
  daemon machinery exists in-tree, and a watched folder had
  no first-class destination until this slice: attachments
  ARE that destination, so the watcher becomes the natural
  follow-on slice.
- **Image attachments on chat messages — taken.** The gap
  is real (an image shown to a chat was either discarded
  after a one-shot describe or forced into a character-
  scoped asset) and every load-bearing piece already exists
  in-tree.

## What landed

New truth layer `src/runmal/vision/attachments.py`:

- `ImageAttachment` — a user-supplied image bound to a chat,
  optionally to one message of that chat (`message_id` null
  = chat-level). The record claims ONLY sniffed truth
  (format, dimensions, byte size, sha256 — assets/imaging),
  plus owner, chat/message binding, and timestamp. The
  user-supplied filename is kept as data: never a filesystem
  path, never a content claim.
- `AttachmentStore` — the P-117 pattern: a versioned JSON
  index `vision_attachments.json` (version 1) in the data
  dir with tolerant load, and byte files under
  `vision_attachments/<id>.<ext>` with the extension from
  the SNIFFED format. Bytes land before the index row; an
  index failure removes the byte file best-effort. A missing
  byte file reads as None, stated plainly.
- `attach_image()` — plain total refusals that store
  NOTHING: empty bytes, bytes over the house 16 MiB cap
  (parity with MAX_ASSET_BYTES / MAX_AVATAR_BYTES), and
  bytes that do not sniff as a supported image.

HTTP surface (`src/runmal/vision/router.py`, `/api/v1/vision`,
bearer-gated; unknown OR foreign chat/attachment/message =
404, existence never leaks):

- `POST /vision/attachments` {chat_id, message_id?,
  filename?, image_b64} -> 201 + record. A message_id must
  name a message of that chat owned by the caller.
- `GET /vision/attachments?chat_id=` — the chat's records.
- `GET /vision/attachments/{id}` — one record, owner-checked.
- `GET /vision/attachments/{id}/content` — the stored bytes
  with the sniffed media type.
- `DELETE /vision/attachments/{id}` — row AND byte file.
- `POST /vision/describe` gains a third source:
  `attachment_id`, owner- and chat-checked, recorded as
  source_kind "attachment" (SOURCE_ATTACHMENT).

Message surface: `chats/router.py` gains the tolerant
additive `_with_attachment_views` beside `_with_voice_markings`
(P-107 idiom) on the history return points — a message dict
gains `attachments: [records]` when it has any; any store
failure leaves the dicts untouched. Chat-level attachments
surface on the vision list road only.

Custody (`chats/service.py`, lazy try/except in the P-118
idiom): deleting a message purges its attachments; deleting
a chat purges the chat's attachments alongside its vision
descriptions. Attachments are NOT rewritten on message
edit/move/copy — history is never rewritten; a copied
message starts with none.

## Honesty lines (P-075)

- Attaching generates NO description or caption. Describing
  an attachment remains a separate explicit describe call,
  and the metadata road still produces no semantic caption.
- Nothing here is a safety scan: bytes are sniffed as
  images, not moderated, and no record claims otherwise.
- Storage cost of the no-migration choice, stated plainly:
  attachment metadata is not SQL-queryable and does not ride
  the chat tables' backups; it lives and dies with the data
  dir, like the vision store it mirrors.

## Named open after P-120

A real local semantic caption provider (needs a vision model
+ an image-input wire; nothing in-tree can honestly serve
yet), OCR (needs a real engine), screen capture, camera
flow, and the folder watcher — for which attachments are now
the landing destination.
