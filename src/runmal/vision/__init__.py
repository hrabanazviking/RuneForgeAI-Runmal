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
"""
