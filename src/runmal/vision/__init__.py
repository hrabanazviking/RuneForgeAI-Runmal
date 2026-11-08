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
- ``router`` — the owner-scoped HTTP road
  (/api/v1/vision/*).
"""
