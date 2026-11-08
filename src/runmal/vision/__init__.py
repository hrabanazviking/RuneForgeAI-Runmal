"""Rúnmál vision subsystem (Part VIII — Vision Services).

- ``service`` — vision descriptions as first-class, persisted,
  chat-bound records behind an honest provider seam: the
  metadata provider (sniffed truth only, road "metadata"),
  the plain unavailable refusal when no provider is
  configured, and the durable JSON store with the
  last-description-per-chat read surface (P-117, VX-50).
- ``selection`` — provider selection + capability truth
  (P-119): the provider catalogue as data (no provider is
  semantic today, stated plainly), the deterministic labelled
  test provider (road "deterministic_test"), per-backend
  ``Capabilities.vision`` truth derived from the adapters'
  own declarations (P-053 road), and plain refusals for
  unknown or semantic requests.
- ``attachments`` — user-supplied images attached to a
  chat or one of its messages: bytes + honest sniffed
  metadata on the same JSON-store pattern, describable
  through the describe road (P-120); thumbnails are
  derived on read through the P-023 PNG engine - PNG-only,
  plain refusals, nothing derived stored (P-123);
  owner-wide history + literal search across chats
  (P-125) - owner-scoped first, literal substring over
  the filename and the image sha256 only, never semantic.
  describe-on-attach is an explicit opt-in on the attach
  road only - atomic, and the service still describes
  nothing on its own (P-126).
- ``service`` history + custody (P-122) - owner-scoped
  get / list / literal search over the description store,
  single-record remove, and purge_source source custody:
  descriptions derived from a deleted attachment die
  with it.
- ``router`` — the owner-scoped HTTP road
  (/api/v1/vision/*).
- ``watcher`` — folder-watcher registrations and the
  explicit polling scan that ingests new image files as
  P-120 chat attachments (P-121). No daemon: a scan is a
  deliberate operation, stated plainly.
- ``watcher`` custody & control (P-124) - forget_attachment
  (an attachment's death forgets its ingested records, so
  the dedupe memory never tombstones its source file) and
  set_enabled (the registration's enabled flag gains its
  first handle; the scan has always refused a disabled
  watch). P-129 completes that control surface:
  set_recursive gives the recursive flag the same handle
  (flipping scan depth no longer costs the dedupe memory
  a delete + re-register would destroy), and the watch
  delete road reports the ingested records it removes
  as a count in the sibling delete roads' shape.
- ``watcher`` history & search (P-127) - owner-wide
  history + literal search across chats: registrations
  searchable by folder path, ingested records by source
  path and sha256, owner-scoped first - the P-122/P-125
  parity surface for the watcher store. Nothing new is
  persisted; the scan report stays a synchronous result.
"""
