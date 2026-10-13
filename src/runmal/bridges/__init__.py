"""External reference bridges (Campaign VI, S605–S607).

Adapters that translate a platform's native protocol (VRChat OSC,
Source RCON, a game mod's HTTP API) into the stable Rúnmál bridge
contract (docs/BRIDGE_PROTOCOL.md). They live OUTSIDE the core: game
quirks stay here, and runmal.bridge never grows game-specific
branches (BRIDGE_PROTOCOL §11). Each module is deliberately small and
dependency-light so a third party can copy it as a starting point.
"""
