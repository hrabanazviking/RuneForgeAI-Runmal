"""Bridge scope grammar (BRIDGE_PROTOCOL §2, S601).

A scope string is ``<capability>`` or ``<capability>:<resource>``:

- ``chat:read:<chat-id>``    — read conversation state for one chat
- ``chat:write:<chat-id>``   — append turns / request generation for one chat
- ``events:read:<chat-id>``  — poll and acknowledge the event outbox for one chat
- ``persona:select:<id>``    — select a persona (character id, or ``*``)
- ``tts:request``            — request TTS synthesis (takes no resource)

The resource ``*`` is a wildcard within its capability only: a grant of
``chat:read:*`` says nothing about ``chat:write``. Matching is exact on
capability and exact-or-wildcard on resource — no prefix games, so a
grant can never quietly widen (INV-029).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Capabilities that must carry a resource segment.
RESOURCE_CAPABILITIES = frozenset({"chat:read", "chat:write", "events:read", "persona:select"})
#: Capabilities that must NOT carry a resource segment.
PLAIN_CAPABILITIES = frozenset({"tts:request"})
KNOWN_CAPABILITIES = RESOURCE_CAPABILITIES | PLAIN_CAPABILITIES

WILDCARD = "*"


@dataclass(frozen=True)
class Scope:
    capability: str
    resource: str | None = None

    def __str__(self) -> str:
        if self.resource is None:
            return self.capability
        return f"{self.capability}:{self.resource}"


def parse_scope(raw: str) -> Scope:
    """Parse one scope string; ValueError on anything outside the grammar."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"invalid scope: {raw!r}")
    text = raw.strip()
    for capability in sorted(KNOWN_CAPABILITIES, key=len, reverse=True):
        if text == capability:
            if capability in RESOURCE_CAPABILITIES:
                raise ValueError(f"scope {capability!r} requires a resource")
            return Scope(capability=capability)
        prefix = capability + ":"
        if text.startswith(prefix):
            if capability in PLAIN_CAPABILITIES:
                raise ValueError(f"scope {capability!r} takes no resource")
            resource = text[len(prefix) :]
            if not resource or ":" in resource:
                raise ValueError(f"invalid scope resource: {raw!r}")
            return Scope(capability=capability, resource=resource)
    raise ValueError(f"unknown scope capability: {raw!r}")


def validate_scopes(raw_scopes: list[str]) -> list[str]:
    """Validate a scope set for credential creation; returns it normalized
    (parsed and re-rendered, order preserved, duplicates removed)."""
    seen: list[str] = []
    for raw in raw_scopes:
        rendered = str(parse_scope(raw))
        if rendered not in seen:
            seen.append(rendered)
    return seen


def scope_allows(
    granted: list[str] | tuple[str, ...], capability: str, resource: str | None = None
) -> bool:
    """True iff the granted scope set allows `capability` on `resource`."""
    for raw in granted:
        try:
            scope = parse_scope(raw)
        except ValueError:
            continue  # a malformed stored grant allows nothing
        if scope.capability != capability:
            continue
        if scope.resource is None:
            return resource is None
        if scope.resource == WILDCARD or scope.resource == resource:
            return True
    return False
