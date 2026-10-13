"""Versioned bridge API core (Campaign VI).

Implements the Rúnmál side of docs/BRIDGE_PROTOCOL.md: scoped and
revocable bridge credentials (S601), the conversation-state API (S602),
persona switching (S603), the TTS hook (S604), the durable event
outbox (S609) and idempotency/capability discovery (S610). Game- and
platform-specific adapters live OUTSIDE this package, in
runmal.bridges, and speak to this surface — core never grows
game-specific branches (BRIDGE_PROTOCOL §11).
"""
