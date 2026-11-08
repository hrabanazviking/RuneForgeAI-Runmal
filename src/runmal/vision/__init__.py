"""Rúnmál vision subsystem (Part VIII — Vision Services).

- ``service`` — vision descriptions as first-class, persisted,
  chat-bound records behind an honest provider seam: the
  metadata provider (sniffed truth only, road "metadata"),
  the plain unavailable refusal when no provider is
  configured, and the durable JSON store with the
  last-description-per-chat read surface (P-117, VX-50).
- ``attachments`` — user-supplied images attached to a
  chat or one of its messages: bytes + honest sniffed
  metadata on the same JSON-store pattern, describable
  through the describe road (P-120).
- ``router`` — the owner-scoped HTTP road
  (/api/v1/vision/*).
"""
